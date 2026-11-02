"""Preview edits to reference metadata exported for external catalog tools."""
from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path
from .metadata import FIELDS,parse_parties
from .enrichment import validate_parties,party_credits,enrichment_plan

FORMAT='cueatlas.reference-metadata'


def editable_values(metadata):
    values={field:str(metadata.get(field) or '') for field in FIELDS}
    if 'parties' in metadata:values['parties']=deepcopy(metadata['parties'])
    return values


def _validate(values,label):
    if not isinstance(values,dict):raise ValueError(f'{label} must be an object.')
    result={}
    for field in FIELDS:
        if field in values:
            if not isinstance(values[field],str):raise ValueError(f'{label}.{field} must be text; use "" to clear it, not null.')
            result[field]=values[field]
    if 'parties' in values:result['parties']=validate_parties(values['parties'])
    return result


def _sync_credits(old,changes):
    """Prefer explicit party edits; keep IPI on matching parties for text edits."""
    changes=deepcopy(changes)
    if 'parties' in changes:
        credits=party_credits(changes['parties'])
        for key,value in credits.items():
            if key in changes and changes[key]!=value:
                raise ValueError(f'Edited {key} conflicts with edited parties. Edit parties and leave its text summary unchanged or omit it.')
            changes[key]=value
        return changes
    if any(key in changes for key in ('composer','publisher')):
        parties=deepcopy(old.get('parties') or parse_parties(old.get('composer',''),'composer')+parse_parties(old.get('publisher',''),'publisher'))
        for field,roles in [('composer',{'composer','author','composer_author','arranger'}),('publisher',{'publisher','subpublisher'})]:
            if field not in changes:continue
            former=[p for p in parties if p.get('role') in roles]
            replacement=[]
            for parsed in parse_parties(changes[field],field):
                matches=[p for p in former if p.get('name','').casefold()==parsed['name'].casefold()]
                if len(matches)==1:
                    known=deepcopy(matches[0]);known['name']=parsed['name']
                    if parsed.get('pro'):known['pro']=parsed['pro']
                    if parsed.get('share_percent') is not None:known['share_percent']=parsed['share_percent']
                    replacement.append(known)
                else:replacement.append(parsed)
            parties=[p for p in parties if p.get('role') not in roles]+replacement
        changes['parties']=parties
        credits=party_credits(parties)
        for field in ('composer','publisher'):
            if field in changes:changes[field]=credits[field]
        if 'pro' in changes and changes['pro']!=credits['pro']:
            raise ValueError('Edited PRO conflicts with the party affiliations. Edit each party’s PRO instead.')
        changes['pro']=credits['pro']
    elif 'pro' in changes and old.get('parties') and changes['pro']!=party_credits(old['parties'])['pro']:
        raise ValueError('Edit PRO affiliations in parties so each affiliation stays with the correct writer or publisher.')
    return changes


def metadata_import_plan(project,path,mode='update'):
    if mode not in ('update','fill'):raise ValueError('Choose apply edits or fill blanks.')
    def reject_constant(value):raise ValueError(f'{value} is not valid JSON. Use null for an unknown party share.')
    def unique_keys(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError(f'Duplicate JSON key: {key}')
            result[key]=value
        return result
    data=json.loads(Path(path).read_text(encoding='utf-8-sig'),parse_constant=reject_constant,object_pairs_hook=unique_keys)
    if not isinstance(data,dict) or not isinstance(data.get('tracks'),list):raise ValueError('Expected an object containing a tracks array.')
    if 'schema_version' in data and (type(data['schema_version']) is not int or data['schema_version']!=1):
        raise ValueError('Unsupported schema_version. This importer accepts version 1.')
    if data.get('format',FORMAT)!=FORMAT:raise ValueError('This is not a Cue Atlas reference-metadata file.')
    if mode=='fill':return enrichment_plan(project,path)
    tracks=project.tracks();by_id={t['id']:t for t in tracks};seen=set();plan=[];skipped=[]
    for number,entry in enumerate(data['tracks'],1):
        if not isinstance(entry,dict):raise ValueError(f'Track {number} must be an object.')
        candidate=_validate(entry.get('metadata'),f'Track {number} metadata')
        original=_validate(entry['original_metadata'],f'Track {number} original_metadata') if 'original_metadata' in entry else None
        tid=entry.get('reference_id')
        if tid is not None and not isinstance(tid,str):raise ValueError(f'Track {number}: reference_id must be text.')
        target=by_id.get(tid)
        if not tid:
            provider=candidate.get('provider');provider_id=candidate.get('provider_track_id')
            matches=[t for t in tracks if provider and provider_id and t['metadata'].get('provider')==provider and t['metadata'].get('provider_track_id')==provider_id]
            if not matches and entry.get('reference_file'):
                file=entry['reference_file']
                if not isinstance(file,str):raise ValueError(f'Track {number}: reference_file must be text.')
                if Path(file).is_absolute():matches=[t for t in tracks if Path(t['path']).resolve()==Path(file).resolve()]
            if len(matches)==1:target=matches[0]
        if target is None:
            skipped.append(f'Track {number}: no unique existing reference matched. Keep reference_id from the export; titles alone cannot match.');continue
        if target['id'] in seen:raise ValueError('The JSON contains multiple entries for the same reference. Combine them before importing.')
        seen.add(target['id']);old=target['metadata'];current=_validate(editable_values(old),'Stored metadata')
        changes={key:value for key,value in candidate.items() if value!=current.get(key,[] if key=='parties' else '')
                 and (original is None or key not in original or value!=original[key])}
        if original is not None:
            stale=[key for key in changes if key in original and current.get(key,[] if key=='parties' else '')!=original[key]]
            if stale:
                skipped.append(f'{old.get("title",number)}: changed in this project since export ({", ".join(stale)}). Export again to reconcile edits.');continue
        if not changes:continue
        try:changes=_sync_credits(old,changes)
        except ValueError as exc:
            skipped.append(f'{old.get("title",number)}: {exc}');continue
        fields=[key for key,value in changes.items() if value!=current.get(key,[] if key=='parties' else '')]
        if not fields:continue
        if original is not None:
            stale=[key for key in fields if key in original and current.get(key,[] if key=='parties' else '')!=original[key]]
            if stale:
                skipped.append(f'{old.get("title",number)}: related credits changed since export ({", ".join(stale)}). Export again to reconcile edits.');continue
        updated=deepcopy(old);updated.update(changes)
        updated.setdefault('provenance',[]).append({'source':'JSON edit: '+Path(path).name,
            'retrieved_at':datetime.now(timezone.utc).isoformat(),'status':'user_edited','fields':fields})
        plan.append({'reference_id':target['id'],'title':old.get('title',''),'fields':fields,'before':deepcopy(old),'metadata':updated})
    return plan,skipped
