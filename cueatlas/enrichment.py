"""Reviewable, fill-only metadata recovery and catalog JSON imports."""
import json
import math
from pathlib import Path
from .metadata import FIELDS,fill_metadata,normalize,parse_parties,merge_parties

PARTY_ROLES={'composer','author','composer_author','arranger','publisher','subpublisher'}


def validate_parties(parties):
    if not isinstance(parties,list):raise ValueError('Parties must be a list.')
    result=[]
    for party in parties:
        if not isinstance(party,dict):raise ValueError('Each party must be an object.')
        if party.get('role') not in PARTY_ROLES:raise ValueError('Choose a supported party role.')
        if not isinstance(party.get('name'),str) or not party['name'].strip():raise ValueError('Each party needs a name.')
        for key in ('pro','ipi'):
            if not isinstance(party.get(key,''),str):raise ValueError(f'Party {key.upper()} must be text.')
        ipi=party.get('ipi','').strip()
        if ipi and (not ipi.isascii() or not ipi.isdigit()):raise ValueError('IPI must contain digits; keep leading zeros.')
        share=party.get('share_percent')
        if share is not None and (isinstance(share,bool) or not isinstance(share,(int,float)) or not math.isfinite(share) or not 0<=share<=100):
            raise ValueError('Each party share must be between 0 and 100, or blank.')
        result.append(dict(party,ipi=ipi))
    return result


def party_credits(parties):
    result={}
    for field,roles in [('composer',{'composer','author','composer_author','arranger'}),('publisher',{'publisher','subpublisher'})]:
        texts=[]
        for p in parties:
            if p['role'] not in roles:continue
            text=p['name']
            if p.get('pro'):text+=f" ({p['pro']})"
            if p.get('share_percent') is not None:text+=f" {p['share_percent']:g}%"
            texts.append(text)
        result[field]=' / '.join(texts)
    result['pro']='; '.join(dict.fromkeys(p['pro'] for p in parties if p.get('pro')))
    return result


def recovery_plan(project):
    plan=[]
    for track in project.tracks():
        old=track['metadata'];candidate=normalize(old.get('raw',{}),track['path'])
        # Legacy edited credits are authoritative over embedded credits.
        candidate['parties']=parse_parties(old.get('composer') or candidate['composer'],'composer')+parse_parties(old.get('publisher') or candidate['publisher'],'publisher')
        candidate['pro']=party_credits(old.get('parties') or candidate['parties'])['pro']
        updated,fields=fill_metadata(old,candidate,'embedded tags')
        if fields:plan.append({'reference_id':track['id'],'title':old.get('title',''),'fields':fields,'metadata':updated,'before':old})
    return plan


def enrichment_plan(project,path):
    data=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(data,dict) or not isinstance(data.get('tracks'),list):raise ValueError('Expected a JSON object with a tracks list, as in a reference library export.')
    tracks=project.tracks();by_id={t['id']:t for t in tracks};plan=[];skipped=[];seen=set()
    for number,entry in enumerate(data['tracks'],1):
        if not isinstance(entry,dict) or not isinstance(entry.get('metadata'),dict):raise ValueError(f'Track {number} needs a metadata object.')
        candidate=dict(entry['metadata'])
        for field in FIELDS:
            if field in candidate and not isinstance(candidate[field],str):raise ValueError(f'Track {number}: {field} must be text.')
        if 'parties' in candidate:candidate['parties']=validate_parties(candidate['parties'])
        tid=entry.get('reference_id')
        if tid is not None and not isinstance(tid,str):raise ValueError('Reference IDs must be text.')
        target=by_id.get(tid)
        if target is None and not tid:
            provider=candidate.get('provider');provider_id=candidate.get('provider_track_id')
            matches=[t for t in tracks if provider and provider_id and t['metadata'].get('provider')==provider and t['metadata'].get('provider_track_id')==provider_id]
            if not matches and entry.get('reference_file'):
                file=entry['reference_file']
                if not isinstance(file,str):raise ValueError('Reference file paths must be text.')
                if Path(file).is_absolute():matches=[t for t in tracks if Path(t['path']).resolve()==Path(file).resolve()]
            if len(matches)==1:target=matches[0]
        if target is None:
            skipped.append(f'Track {number}: no unique reference ID, provider/track ID, or absolute file-path match.');continue
        if target['id'] in seen:raise ValueError('The JSON contains multiple entries for the same reference. Combine them before importing.')
        seen.add(target['id'])
        old=target['metadata'];candidate=dict(candidate)
        if candidate.get('parties'):
            credits=party_credits(candidate['parties'])
            for key,value in credits.items():
                if not old.get(key) and not candidate.get(key):candidate[key]=value
        else:
            candidate['parties']=parse_parties(candidate.get('composer',''),'composer')+parse_parties(candidate.get('publisher',''),'publisher')
            candidate['pro']=candidate.get('pro') or party_credits(candidate['parties'])['pro']
        # A fill-only import cannot replace established structured credits. A
        # difference requires explicit editing in the reference metadata dialog.
        merged,party_conflicts=merge_parties(old.get('parties',[]),candidate.get('parties',[]))
        conflicts=['parties: '+c for c in party_conflicts]
        for key in FIELDS:
            if old.get(key) and candidate.get(key) and old[key]!=candidate[key]:conflicts.append(key)
        if conflicts:
            skipped.append(f"{old.get('title',number)}: conflicts in {', '.join(conflicts)}; entry skipped.");continue
        if candidate.get('parties') and not old.get('parties') and (old.get('composer') or old.get('publisher')):
            legacy=parse_parties(old.get('composer',''),'composer')+parse_parties(old.get('publisher',''),'publisher')
            merged,conflicts=merge_parties(legacy,candidate['parties'])
            if conflicts:
                skipped.append(f"{old.get('title',number)}: existing text credits need review before importing parties.");continue
            candidate['parties']=merged
        updated,fields=fill_metadata(old,candidate,f'JSON import: {Path(path).name}',candidate.get('source_url',''))
        if fields:plan.append({'reference_id':target['id'],'title':old.get('title',''),'fields':fields,'metadata':updated,'before':old})
    return plan,skipped


def apply_plan(project,plan):
    if not plan:return 0
    current={t['id']:t['metadata'] for t in project.tracks()}
    if any(current.get(item['reference_id'])!=item['before'] for item in plan):raise ValueError('Reference metadata changed. Preview the changes again.')
    project.snapshot('Before enriching reference metadata',force=True)
    with project.db:
        project.db.execute('BEGIN IMMEDIATE')
        current={t['id']:t['metadata'] for t in project.tracks()}
        if any(current.get(item['reference_id'])!=item['before'] for item in plan):raise ValueError('Reference metadata changed. Preview the changes again.')
        for item in plan:
            project.db.execute('UPDATE tracks SET metadata=? WHERE id=?',(json.dumps(item['metadata']),item['reference_id']))
    return len(plan)
