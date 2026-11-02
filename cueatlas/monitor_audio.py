"""Disposable, source-aligned timeline audition. Project cues are never changed."""
import hashlib,json,os,tempfile
from pathlib import Path
import numpy as np
from scipy.io.wavfile import write
from .audio import SR,decode,decode_program,waveform,Cancelled,content_hash
from . import separation as ai
from .project import Project


def stamp(path):
    path=Path(path).resolve();s=path.stat()
    return {'path':str(path),'size':s.st_size,'mtime':s.st_mtime_ns}


def directory(source):
    key=hashlib.sha256(json.dumps(stamp(source),sort_keys=True).encode()).hexdigest()
    return ai.home()/'cache'/'timeline'/key


def read_index(source):
    try:return json.loads((directory(source)/'index.json').read_text())
    except (OSError,ValueError):return {'segments':[]}


def save_index(source,index):
    root=directory(source);root.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',suffix='.json',dir=root,delete=False) as file:
        temporary=Path(file.name);file.write(json.dumps(index))
    try:os.replace(temporary,root/'index.json')
    finally:temporary.unlink(missing_ok=True)


def register(source,start,end,audio,audio_start=0,digest=None):
    index=read_index(source);segment={'start':start,'end':end,'audio':str(Path(audio).resolve()),'audio_start':audio_start,'digest':digest}
    if segment in index['segments']:return
    rows=[s for s in index['segments'] if s['start']!=start or s['end']!=end]
    index['segments']=rows+[segment];save_index(source,index)


def signature(segments):
    return hashlib.sha256(json.dumps(segments,sort_keys=True).encode()).hexdigest()


def descriptor(program):
    try:
        if 'size' in program and stamp(program['path'])!={k:program[k] for k in ('path','size','mtime')}:return None
        index=read_index(program['path']);preview=index.get('preview',{})
        if preview.get('signature')==signature(index['segments']) and Path(preview.get('path','')).is_file():return preview
    except (OSError,KeyError,ValueError):pass
    return None


def timeline_audio(project_path,request,progress=lambda *a:None,cancel=lambda:False):
    p=Project(project_path)
    try:program=p.get('program',{})
    finally:p.close()
    source=program.get('path','');initial=stamp(source)
    if 'size' in program and (initial['size'],initial['mtime'])!=(program['size'],program.get('mtime')):raise ValueError('Program media changed. Relink or analyze the correct source first.')
    progress(.01,'Reading original program audio…');original,duration,_=decode_program(source,cancel=cancel)
    digest=content_hash(source,cancel)
    selected=request.get('range')
    if selected:
        start,end=selected
        if not np.isfinite([start,end]).all() or not 0<=start<end<=duration:raise ValueError('Mark a valid interval within the program.')
        ai.separate_program(source,round(end*SR)-round(start*SR),progress=lambda n,s:progress(.05+.8*n,s),cancel=cancel,
                            start_seconds=start,total_samples=len(original),source_digest=digest)
    else:
        # Reconstruct indexes for caches created before timeline audition existed.
        for start in range(0,len(original),60*SR):
            if cancel():raise Cancelled()
            end=min(len(original),start+60*SR);a=max(0,start-4*SR);b=min(len(original),end+4*SR)
            path=ai.home()/'cache'/(ai.cache_key(digest+'full-program-60-context4-v1',{'start':a/SR,'end':b/SR})+'.wav')
            if path.is_file():register(source,start/SR,end/SR,path,(start-a)/SR,digest=digest)
        try:
            result=json.loads(ai.result_path(project_path).read_text())
            for entry in result['items']:
                c=entry['cue'];path=Path(entry.get('audio',''))
                expected={ai.cache_key(digest+'cue-context4-v1',c)+'.wav',ai.cache_key(digest,c)+'.wav'}
                if path.name in expected and path.is_file():register(source,c['start'],c['end'],path,digest=digest)
        except (OSError,ValueError,KeyError):pass
    index=read_index(source);segments=[s for s in index['segments'] if s.get('digest')==digest and Path(s['audio']).is_file()]
    if not segments:raise ValueError('No AI audio is available. Mark a range with I/O or Option-drag, then choose Separate range.')
    # Audition at the model's native sample rate; matching uses a smaller decode.
    del original
    sample_rate=48000;original=decode(source,cancel=cancel,sample_rate=sample_rate)
    mixed=original.copy();coverage=[]
    for i,s in enumerate(segments):
        if cancel():raise Cancelled()
        progress(.85+.1*i/len(segments),'Building timeline comparison audio…')
        a=round(s['start']*sample_rate);b=round(s['end']*sample_rate)
        if not 0<=a<b<=len(original):continue
        music=decode(s['audio'],cancel=cancel,sample_rate=sample_rate);first=round(s['audio_start']*sample_rate);values=music[first:first+b-a]
        if abs(len(values)-(b-a))>1 or not np.isfinite(values).all():raise ValueError('Cached AI audio is incomplete; separate that range again.')
        if len(values)<b-a:values=np.pad(values,(0,b-a-len(values)))
        mixed[a:b]=values[:b-a];coverage.append((a,b))
    if not coverage:raise ValueError('No separated sections match this program timeline.')
    regions=[]
    for a,b in sorted(coverage):
        if regions and a<=regions[-1][1]:regions[-1][1]=max(regions[-1][1],b)
        else:regions.append([a,b])
    # Short edge blends avoid clicks, without moving a sample or reintroducing
    # dialogue at the internal joins of a completely separated program.
    for a,b in regions:
        n=min(round(.01*sample_rate),(b-a)//2)
        if n:
            ramp=np.linspace(0,1,n,dtype=np.float32)
            if a:mixed[a:a+n]=original[a:a+n]*(1-ramp)+mixed[a:a+n]*ramp
            if b<len(original):mixed[b-n:b]=mixed[b-n:b]*(1-ramp)+original[b-n:b]*ramp
    if cancel():raise Cancelled()
    if stamp(source)!=initial:raise ValueError('Program media changed during separation. Previous audio was preserved.')
    key=signature(segments);root=directory(source);root.mkdir(parents=True,exist_ok=True);target=root/(key+'.wav')
    with tempfile.NamedTemporaryFile(suffix='.wav',dir=root,delete=False) as file:temporary=Path(file.name)
    try:
        write(temporary,sample_rate,mixed)
        if cancel():raise Cancelled()
        os.replace(temporary,target)
    finally:temporary.unlink(missing_ok=True)
    preview={'path':str(target),'signature':key,'waveform':waveform(mixed),'regions':[[a/sample_rate,b/sample_rate] for a,b in regions],'source':initial}
    index.update(segments=segments,preview=preview);save_index(source,index)
    progress(1,'AI timeline audio ready');return {'timeline_audio':True,'preview':preview}
