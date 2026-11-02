"""Alternate-version hints never replace recording-specific evidence or licensing."""
import re
import unicodedata
from collections import defaultdict
from .project import cue

_VERSION=re.compile(r'\b(?:instrumental|instrumentals|vocal|vocals|original|version|mix|full|main|underscore|alternate|alt|edit)\b',re.I)
CONTINUITY_TOLERANCE=.12


def family_title(track):
    title=track['metadata'].get('title','')
    def bracket(match):
        content=match.group()[1:-1]
        return ' ' if not re.sub(r'[^\w]+','',_VERSION.sub('',content)) else match.group()
    text=re.sub(r'\([^)]*\)|\[[^]]*\]',bracket,title)
    text=re.sub(r'(?:\s*[-–—_:]\s*|\s+)(?:(?:instrumental|instrumentals|vocal|vocals|original|version|mix|full|main|underscore|alternate|alt|edit)\s*)+$','',text,flags=re.I)
    text=text or title
    return re.sub(r'\s+',' ',text).strip(' -_·')


def family_key(track):
    text=unicodedata.normalize('NFKC',family_title(track)).casefold()
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in text).split())


def related(a,b):
    if a['id']==b['id']:return True
    key=family_key(a)
    if not key or key!=family_key(b):return False
    # Conflicting provenance prevents unrelated same-title songs being grouped.
    for field in ('provider','library','catalog','artist','composer'):
        left=str(a['metadata'].get(field,'')).strip().casefold();right=str(b['metadata'].get(field,'')).strip().casefold()
        if left and right and left!=right:return False
    return True


def offset(candidate):return candidate['reference_start']-candidate['program_start']


def covers_interval(candidate,item):
    if 'evidence_start' not in candidate:return True  # Earlier saved proposals have no coverage measures.
    return (candidate['evidence_start']<=item['start']+1 and candidate['evidence_end']>=item['end']-1
            and candidate.get('max_evidence_gap',0)<=1)


def candidates(entry):
    """Keep original and AI evidence separately; one best selectable anchor per recording."""
    choices={}
    for source in ('separated','original'):
        for c in entry.get(source,[]):
            old=choices.get(c['track'])
            if source=='original' or old is None or c['support']>old['support']:choices[c['track']]=c
    return list(choices.values())


def annotate(entry,tracks,rows=(),anchors=None,min_support=8):
    tracks={t['id']:t for t in tracks} if not isinstance(tracks,dict) else tracks
    choices=candidates(entry)
    if not choices:return entry
    # Neighbors corroborate audio evidence, never create a match from a title.
    neighbors=[];item=entry['cue'];anchors=anchors or {}
    for neighbor in rows:
        if not neighbor['track'] or neighbor['id']==item['id']:continue
        if min(abs(neighbor['end']-item['start']),abs(neighbor['start']-item['end']))>1e-6:continue
        anchor=anchors.get(neighbor['id'],{})
        for c in choices:
            if c['track']!=neighbor['track'] or anchor.get('track')!=c['track']:continue
            if abs(offset(c)-offset(anchor))<=CONTINUITY_TOLERANCE:
                neighbors.append({'id':neighbor['id'],'track':c['track'],'title':neighbor['title'],'continuous':True})
    entry['neighbors']=neighbors
    original={c['track']:c for c in entry.get('original',[])}
    separated={c['track']:c for c in entry.get('separated',[])}
    def score(c):
        a=original.get(c['track'],{}).get('support',0);b=separated.get(c['track'],{}).get('support',0)
        base=max(a,b)+min(a,b)*.25
        return base*(1.2 if any(n['track']==c['track'] for n in neighbors) else 1)
    leader=max(choices,key=score);track=tracks[leader['track']]
    family=[t for t in tracks.values() if related(track,t)]
    family_ids={t['id'] for t in family}
    originals=sorted((c for c in original.values() if c['track'] in family_ids),key=lambda c:(c['support'],c['votes']),reverse=True)
    # Strong, distinguishing original-mix evidence takes priority within a song.
    clear=bool(len(originals)==1 and originals[0]['support']>=min_support*2)
    preferred=originals[0] if clear else leader
    unresolved=len(family)>1 and not clear
    entry['recommendation']={'preferred':preferred['track'],'version_unresolved':unresolved,
                             'family_title':family_title(track),'version_tracks':sorted(family_ids),
                             'reason':'Version needs review' if unresolved else ('Original mix supports this version' if len(family)>1 and clear else 'Reference proposal')}
    if any(n['track']==preferred['track'] for n in neighbors) and not unresolved:
        entry['recommendation']['reason']+=' · neighbor position agrees'
    if not unresolved and not covers_interval(preferred,item):entry['recommendation']['reason']+=' · review cue boundaries'
    return entry


def review_choices(entry):
    choices=candidates(entry);rec=entry.get('recommendation',{})
    ordered=sorted(choices,key=lambda c:(c['track']==rec.get('preferred'),c['support'],c['votes']),reverse=True)
    by_id={c['track']:c for c in choices}
    for alt in entry.get('version_alternatives',[]):
        if alt['track'] not in by_id:ordered.append(alt)
    if rec.get('version_unresolved'):
        ordered.insert(0,{'track':None,'title':rec['family_title']+' · Version needs review','support':0,'votes':0,
                          'reference_start':0,'program_start':entry['cue']['start'],'version_unresolved':True,
                          'version_tracks':rec['version_tracks'],'version_candidates':[c for c in ordered if c['track'] in rec['version_tracks']]})
    return ordered


def annotate_results(result,project):
    tracks={t['id']:t for t in project.tracks()};hidden=project.excluded_cue_ids();rows=[c for c in project.cues() if c['id'] not in hidden]
    anchors=project.get('cue_matches',{})
    for entry in result['items']:
        annotate(entry,tracks,rows,anchors,int(project.settings['min_support']))
        rec=entry.get('recommendation',{});present={c['track'] for c in candidates(entry)}
        entry['version_alternatives']=[{'track':tid,'title':tracks[tid]['metadata']['title'],'support':0,'votes':0,
            'reference_start':0,'program_start':entry['cue']['start'],'comparison_only':True}
            for tid in rec.get('version_tracks',[]) if tid not in present]
    result['strict_neighbor_merge']=True
    return result


def collapse_versions(rows,tracks,min_support,source='original'):
    """Collapse substantially overlapping observations of alternate recordings for review."""
    tracks={t['id']:t for t in tracks};groups=[]
    for row in sorted(rows,key=lambda c:c['start']):
        target=None
        for group in groups:
            if not all(related(tracks[c['track']],tracks[row['track']]) for c in group):continue
            if any(min(c['end'],row['end'])-max(c['start'],row['start'])>=min(2,(min(c['end']-c['start'],row['end']-row['start']))*.5) for c in group):target=group;break
        if target is None:groups.append([row])
        else:target.append(row)
    output=[];reviews={}
    for group in groups:
        entry={'cue':{'start':min(c['start'] for c in group),'end':max(c['end'] for c in group),'id':''},'original':[],'separated':[]}
        evidence=defaultdict(list)
        for c in group:evidence[c['track']].append(c)
        for tid,items in evidence.items():
            strongest=max(items,key=lambda c:c.get('_support',0));start=entry['cue']['start'];shift=strongest.get('_reference_offset',0)
            entry[source].append({'track':tid,'title':tracks[tid]['metadata']['title'],'support':max(c.get('_support',0) for c in items),
                                  'votes':max(c.get('_support',0) for c in items),'program_start':max(start,-shift),'reference_start':max(0,start+shift)})
        annotate(entry,tracks,min_support=min_support);rec=entry['recommendation']
        if rec['version_unresolved']:
            row=cue(None,entry['cue']['start'],entry['cue']['end'],title=rec['family_title']+' · Version needs review',status='Needs review',
                    note='Song identified; recording version needs listening confirmation. No recording-specific license has been assigned.')
            output.append(row);reviews[row['id']]=entry[source]
        else:
            # Keep only the original-supported recording within this overlapping group.
            output.extend(c for c in group if c['track']==rec['preferred'])
    return output,reviews
