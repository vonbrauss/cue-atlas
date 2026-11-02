"""Local spectral-landmark matching, version 1. Timings are estimates for review."""
from collections import defaultdict, Counter
from pathlib import Path
import numpy as np
from scipy.ndimage import maximum_filter
from scipy.signal import stft, correlate
from .audio import SR, decode, waveform, Cancelled, content_hash, decode_program
from .metadata import read_metadata
from .project import Project, cue
from .coverage import ensure_coverage,audible_spans,trim_automatic_cues
HOP=256
STEP=HOP/SR
NFFT=1024

def fingerprints(audio):
    if len(audio)<NFFT:return []
    _,_,z=stft(audio,fs=SR,nperseg=NFFT,noverlap=NFFT-HOP,boundary=None,padded=False)
    mag=np.abs(z)
    db=20*np.log10(np.maximum(mag,1e-9))
    peaks=(db==maximum_filter(db,size=(13,9))) & (db>np.max(db,axis=0,keepdims=True)-38) & (db>-78)
    peaks[:4,:]=False;peaks[-3:,:]=False
    freq,times=np.nonzero(peaks)
    order=np.argsort(times,kind='stable');freq=freq[order];times=times[order]
    # Pair a peak with a handful of future peaks. dt encoded at native hop precision.
    pairs=[]
    for i,(f,t) in enumerate(zip(freq,times)):
        j=i+1;count=0
        while j<len(times) and times[j]-t<=65 and count<8:
            dt=int(times[j]-t)
            if dt>=3:
                h=(int(f)<<18)|(int(freq[j])<<9)|dt
                pairs.append((h,int(t)));count+=1
            j+=1
    return pairs

def import_files(project_path,files,progress=lambda *a:None,cancel=lambda:False):
    p=Project(project_path); failures=[];added=0;skipped=0;duplicates=[]
    try:
        existing={t['path']:t for t in p.tracks()}
        checksums={t['metadata'].get('_content_sha256'):t['path'] for t in existing.values() if t['metadata'].get('_content_sha256')}
        for i,path in enumerate(files):
            if cancel():raise Cancelled()
            progress(i/max(1,len(files)),f'Fingerprinting {i+1}/{len(files)} · {Path(path).name}')
            try:
                stat=Path(path).stat();old=existing.get(str(Path(path).resolve()))
                if old and old['size']==stat.st_size and old['mtime']==stat.st_mtime_ns:
                    checksum=old['metadata'].get('_content_sha256')
                    if not checksum:
                        checksum=content_hash(path,cancel)
                        p.update_metadata(old['id'],old['metadata']|{'_content_sha256':checksum})
                    checksums[checksum]=str(Path(path).resolve())
                    skipped+=1;continue
                checksum=content_hash(path,cancel)
                for known in existing.values():
                    if known['size']==stat.st_size and not known['metadata'].get('_content_sha256') and known['path']!=str(Path(path).resolve()):
                        try:
                            digest=content_hash(known['path'],cancel)
                            known['metadata']['_content_sha256']=digest;checksums[digest]=known['path']
                            p.update_metadata(known['id'],known['metadata'])
                        except OSError:pass
                if checksum in checksums and checksums[checksum]!=str(Path(path).resolve()):
                    skipped+=1;duplicates.append(f'{Path(path).name} duplicates {checksums[checksum]}');continue
                audio=decode(path,cancel=cancel);fp=fingerprints(audio)
                if cancel():raise Cancelled()
                meta=read_metadata(path)
                meta['_content_sha256']=checksum
                if old:
                    # Preserve user edits, but update original imported tags.
                    meta.update({k:v for k,v in old['metadata'].items() if k not in {'raw','import_warnings','_content_sha256'}})
                p.save_track(path,len(audio)/SR,meta,fp);added+=1
                checksums[checksum]=str(Path(path).resolve())
            except Cancelled:raise
            except Exception as e:failures.append(f'{Path(path).name}: {e}')
        if added and p.cues():p.set('stale',True)
        return {'added':added,'skipped':skipped,'failures':failures,'duplicates':duplicates}
    finally:p.close()

def import_library(project_path,source_path,progress=lambda *a:None,cancel=lambda:False):
    """Copy an indexed library atomically from a read-only project snapshot."""
    import sqlite3
    import json
    import uuid
    target_path=Path(project_path).resolve();source_path=Path(source_path).resolve()
    if source_path==target_path or (source_path.exists() and source_path.samefile(target_path)):
        raise ValueError('Choose a different project to import its reference library.')
    source=sqlite3.connect(source_path.as_uri()+'?mode=ro',uri=True)
    source.row_factory=sqlite3.Row
    p=None
    try:
        source.execute('BEGIN')
        if source.execute('PRAGMA user_version').fetchone()[0]!=1:
            raise ValueError('Unsupported Cue Atlas project version.')
        row=source.execute("SELECT value FROM info WHERE key='name'").fetchone()
        if not row or not json.loads(row[0]):raise ValueError('Invalid Cue Atlas project.')
        tracks=source.execute('SELECT * FROM tracks ORDER BY path').fetchall()
        portable=source.execute("SELECT value FROM info WHERE key='portable_paths'").fetchone()
        portable=bool(portable and json.loads(portable[0]))
        p=Project(target_path)
        existing=p.tracks();paths={t['path'] for t in existing}
        if existing or p.cues():p.snapshot('Before importing a reference library',force=True)
        checksums={t['metadata'].get('_content_sha256') for t in existing}-{None,''}
        added=skipped=0
        with p.db:
            for index,t in enumerate(tracks):
                if cancel():raise Cancelled()
                progress(index/max(1,len(tracks)),f"Importing reference {index+1}/{len(tracks)} · {Path(t['path']).name}")
                metadata=json.loads(t['metadata']);checksum=metadata.get('_content_sha256')
                reference_path=str((source_path.parent/t['path']).resolve()) if portable else t['path']
                if reference_path in paths or (checksum and checksum in checksums):
                    skipped+=1;continue
                tid=uuid.uuid4().hex
                p.db.execute('INSERT INTO tracks VALUES(?,?,?,?,?,?)',
                    (tid,reference_path,t['size'],t['mtime'],t['duration'],t['metadata']))
                hashes=source.execute('SELECT hash,frame FROM hashes WHERE track=?',(t['id'],))
                while True:
                    if cancel():raise Cancelled()
                    batch=hashes.fetchmany(10000)
                    if not batch:break
                    p.db.executemany('INSERT INTO hashes VALUES(?,?,?)',((h['hash'],tid,h['frame']) for h in batch))
                paths.add(reference_path)
                if checksum:checksums.add(checksum)
                added+=1
            if cancel():raise Cancelled()
            if added and p.cues():
                p.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('stale',json.dumps(True)))
        return {'library_import':True,'added':added,'skipped':skipped,'failures':[]}
    finally:
        source.close()
        if p:p.close()


def supported_frames(frames):
    """Keep sorted, unique frames with at least three neighbors within 22 hops."""
    dense=[];left=right=0
    for t in frames:
        while frames[left]<t-22:left+=1
        while right<len(frames) and frames[right]<=t+22:right+=1
        if right-left>=3:dense.append(t)
    return dense


def match_chunk(db,fp,min_votes):
    query=defaultdict(list)
    for h,t in fp:query[h].append(t)
    votes=defaultdict(list)
    hashes=list(query)
    for start in range(0,len(hashes),700):
        keys=hashes[start:start+700]
        rows=db.execute(f'SELECT hash,track,frame FROM hashes WHERE hash IN ({",".join("?" for _ in keys)})',keys)
        # Repetitious tonal hashes are not discriminating; cap their fan-out.
        counts=Counter()
        for h,tid,rt in rows:
            counts[h]+=1
            if counts[h]>100 or len(query[h])>100:continue
            for qt in query[h]:votes[tid].append((rt-qt,qt,h))
    result=[]
    for tid,matches in votes.items():
        counts=Counter(offset for offset,_,_ in matches)
        peaks=sorted(counts,key=lambda x:sum(counts[x+d] for d in (-1,0,1)),reverse=True)
        used=[]
        for peak in peaks[:80]:
            if any(abs(peak-u)<=3 for u in used):continue
            used.append(peak)
            aligned=[(t,h,o) for o,t,h in matches if abs(o-peak)<=1]
            if len({(t,h) for t,h,_ in aligned})<min_votes:continue
            offset=float(np.median([o for _,_,o in aligned]))
            frames=sorted(set(t for t,_,_ in aligned))
            # Only keep locally supported spans; sparse isolated collisions are discarded.
            dense=supported_frames(frames)
            if not dense:continue
            result.append((tid,offset*STEP,np.array(dense)*STEP,len(aligned)))
    return result

def refine_region(program,reference,start,end,offset):
    """Refine fingerprint support with locally aligned waveform correlation.

    Still an estimate: heavily remixed/time-stretched audio needs manual review.
    A missing source is handled by the caller by keeping fingerprint boundaries.
    """
    middle=(start+end)/2
    qs=max(0,int((middle-.4)*SR));n=min(int(.8*SR),len(program)-qs)
    expected=int(qs+offset*SR);low=max(0,expected-int(.06*SR));high=min(len(reference),expected+n+int(.06*SR))
    if n<SR//5 or high-low<n:return start,end
    q=program[qs:qs+n];search=reference[low:high]
    corr=correlate(search,q,mode='valid',method='fft')
    lag=int(np.argmax(np.abs(corr)));r=search[lag:lag+n]
    quality=abs(float(np.dot(q,r)))/max(1e-12,float(np.linalg.norm(q)*np.linalg.norm(r)))
    if quality<.35:return start,end
    shift=low+lag-qs
    window=int(.10*SR);left=max(0,int((start-1.5)*SR));right=min(len(program),int((end+1.5)*SR))
    supported=[]
    for pos in range(left,right-window+1,window):
        rp=pos+shift
        if rp<0 or rp+window>len(reference):continue
        a=program[pos:pos+window];b=reference[rp:rp+window]
        score=abs(float(np.dot(a,b)))/max(1e-12,float(np.linalg.norm(a)*np.linalg.norm(b)))
        if score>.23 and float(np.mean(a*a))>1e-10:supported.append(pos)
    if not supported:return start,end
    spans=[]
    for pos in supported:
        if spans and pos-spans[-1][-1]<=window*2:spans[-1].append(pos)
        else:spans.append([pos])
    eligible=[span for span in spans if len(span)>=3 and span[0]/SR<=middle<=(span[-1]+window)/SR]
    if not eligible:return start,end
    span=max(eligible,key=len)
    return max(0,min(start,span[0]/SR)),min(len(program)/SR,max(end,(span[-1]+window)/SR))

def analyze(project_path,progress=lambda *a:None,cancel=lambda:False,use_separation=False,version_aware=True,unknown_max_seconds=None):
    p=Project(project_path)
    try:
        program=p.get('program');settings=p.settings
        if not program or not Path(program['path']).is_file():raise ValueError('Choose an available program audio file first.')
        if not p.tracks():raise ValueError('Add reference music to this project first.')
        if unknown_max_seconds is not None and (not np.isfinite(unknown_max_seconds) or unknown_max_seconds<=0):raise ValueError('Unknown search intervals must have a positive maximum length.')
        source_stat=Path(program['path']).stat()
        progress(0,'Decoding program audio…')
        audio,duration,reported_duration=decode_program(program['path'],cancel=cancel)
        search_audio=audio
        if use_separation:
            from .separation import separate_program
            search_audio=separate_program(program['path'],len(audio),progress=lambda value,message:progress(.05+.65*value,message),cancel=cancel)
            if search_audio.ndim!=1 or len(search_audio)!=len(audio):raise ValueError('Separated audio does not match the program timeline. Previous cues were preserved.')
        observations=defaultdict(list)
        chunk_seconds=24;stride=20
        for start in range(0,int(np.ceil(duration)),stride):
            if cancel():raise Cancelled()
            progress((.7 if use_separation else .05)+(.25 if use_separation else .85)*start/max(duration,1),f'Searching project library · {start//60:02}:{start%60:02} / {int(duration)//60:02}:{int(duration)%60:02}')
            fp=fingerprints(search_audio[int(start*SR):int((start+chunk_seconds)*SR)])
            for tid,offset,times,count in match_chunk(p.db,fp,int(settings['min_votes'])):
                # Global reference-minus-program offset; coalesce across chunk edges.
                observations[tid].append((offset-start,times+start,count))
        del search_audio
        cues=[];tracks={t['id']:t for t in p.tracks()}
        for tid,hits in observations.items():
            if cancel():raise Cancelled()
            reference=None
            try:
                reference=decode(tracks[tid]['path'],cancel=cancel)
            except Cancelled:raise
            except (OSError,ValueError):pass
            groups=[]
            for offset,times,count in sorted(hits,key=lambda h:h[0]):
                if groups and abs(np.median(groups[-1][0])-offset)<.12:
                    groups[-1][0].append(offset);groups[-1][1].extend(times.tolist())
                else:groups.append(([offset],times.tolist()))
            for offsets,times in groups:
                frames=np.array(sorted(set(times)))
                splits=np.where(np.diff(frames)>float(settings['gap']))[0]+1
                for region in np.split(frames,splits):
                    if len(region)<int(settings['min_support']):continue
                    start=max(0,float(region[0])-.06)
                    end=min(duration,float(region[-1])+NFFT/SR)
                    if end-start<float(settings['min_cue']):continue
                    if reference is not None:
                        start,end=refine_region(audio,reference,start,end,float(np.median(offsets)))
                    # Evidence score, deliberately not presented as calibrated probability.
                    density=len(region)/max(1,end-start)
                    score=min(99,round(45+min(35,density*3)+min(19,(end-start)*.6)))
                    cues.append(cue(tid,start,end,score,tracks[tid]['metadata']['title'])|{'_reference_offset':float(np.median(offsets)),'_support':len(region)})
        # Consolidate duplicate observations of same track, preserve real overlaps between tracks.
        merged=[]
        for c in sorted(cues,key=lambda c:(c['track'],c['start'])):
            if merged and merged[-1]['track']==c['track'] and c['start']<=merged[-1]['end']+.12:
                merged[-1]['end']=max(merged[-1]['end'],c['end']);merged[-1]['confidence']=max(merged[-1]['confidence'],c['confidence'])
            else:merged.append(c)
        version_reviews={}
        if version_aware or use_separation:
            from .versions import collapse_versions
            merged,version_reviews=collapse_versions(merged,list(tracks.values()),int(settings['min_support']),source='separated' if use_separation else 'original')
        activity=audible_spans(audio,duration,settings['silence_db'])
        version_regions=[(c,version_reviews[c['id']]) for c in merged if c['id'] in version_reviews]
        merged=trim_automatic_cues(merged,activity,float(settings['min_cue']))
        version_reviews={c['id']:evidence for c in merged for original,evidence in version_regions
                         if c['title']==original['title'] and original['start']<=c['start'] and c['end']<=original['end']}
        merged=ensure_coverage(merged,duration,audio,settings['silence_db'],activity=activity)
        if unknown_max_seconds:
            bounded=[]
            for row in merged:
                if row['track'] is not None or row['status']!='Unknown' or row['end']-row['start']<=unknown_max_seconds:
                    bounded.append(row);continue
                start=row['start']
                while start<row['end']:
                    end=min(row['end'],start+unknown_max_seconds)
                    bounded.append(cue(None,start,end,title=row['title']));start=end
            merged=bounded
            number=0
            for row in sorted(merged,key=lambda c:(c['start'],c['end'])):
                if row['track'] is None and row['status']=='Unknown':number+=1;row['title']=f'Unknown {number:03}'
        if cancel():raise Cancelled()
        progress(.97,'Saving cues and waveform…')
        stat=Path(program['path']).stat()
        if (stat.st_size,stat.st_mtime_ns)!=(source_stat.st_size,source_stat.st_mtime_ns):raise ValueError('Program media changed during analysis. Previous cues were preserved.')
        p.snapshot('Before replacing analysis',force=True)
        if cancel():raise Cancelled()
        program.update(duration=duration,reported_duration=reported_duration,decoded_duration=duration,waveform=waveform(audio),size=stat.st_size,mtime=stat.st_mtime_ns)
        # One atomic transaction: cancellation/errors never erase prior results.
        with p.db:
            p.db.execute("DELETE FROM info WHERE key='excluded_cues'")
            p.db.execute("DELETE FROM info WHERE key='edit_history'")
            p.db.execute("DELETE FROM info WHERE key='undo_trim'")
            p.db.execute("DELETE FROM info WHERE key='undo_merge'")
            p.db.execute('DELETE FROM cues')
            p.db.executemany('INSERT INTO cues VALUES(:id,:track,:start,:end,:confidence,:status,:note,:title)',merged)
            import json
            for k,v in [('program',program),('stale',False),('analysis_settings',settings),('analysis_mode','ai_separation' if use_separation else 'standard'),('version_reviews',version_reviews),('cue_matches',{c['id']:{'track':c['track'],'program_start':max(c['start'],-c['_reference_offset']),'reference_start':max(0,c['start']+c['_reference_offset'])} for c in merged if '_reference_offset' in c})]:
                p.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',(k,json.dumps(v)))
        return {'cues':len(merged),'matched':sum(c['track'] is not None for c in merged),'duration':duration,'ai_analysis':use_separation}
    finally:p.close()


def repair_coverage(project_path,progress=lambda *a:None,cancel=lambda:False):
    """Recheck full audio length and fill gaps without re-identifying music."""
    p=Project(project_path)
    try:
        program=p.get('program',{})
        if not program.get('path') or not Path(program['path']).is_file():
            raise ValueError('Choose or relink the program audio first.')
        # Existing cues belong to the analyzed source. Do not silently attach
        # them to a changed program cut via this repair operation.
        stat=Path(program['path']).stat()
        if program.get('size') is not None and (stat.st_size!=program['size'] or stat.st_mtime_ns!=program.get('mtime')):
            raise ValueError('The program file changed since analysis. Analyze the new cut rather than repairing old cue timings.')
        progress(.05,'Checking full source duration and decoding audio…')
        audio,duration,reported=decode_program(program['path'],cancel)
        before=p.cues();after=ensure_coverage(before,duration,audio,p.settings['silence_db'])
        if cancel():raise Cancelled()
        program.update(duration=duration,reported_duration=reported,decoded_duration=duration,
            waveform=waveform(audio),size=stat.st_size,mtime=stat.st_mtime_ns)
        progress(.95,'Saving continuous cue coverage…')
        p.snapshot('Before repairing source coverage',force=True)
        import json
        with p.db:
            p.db.execute("DELETE FROM info WHERE key='edit_history'")
            p.db.execute("DELETE FROM info WHERE key='undo_trim'")
            p.db.execute("DELETE FROM info WHERE key='undo_merge'")
            p.db.execute('DELETE FROM cues')
            p.db.executemany('INSERT INTO cues VALUES(:id,:track,:start,:end,:confidence,:status,:note,:title)',after)
            p.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('program',json.dumps(program)))
        return {'repaired':True,'added':len(after)-len(before),'duration':duration}
    finally:p.close()


def identify_cue(project_path,cue_id,progress=lambda *a:None,cancel=lambda:False,audio_override=None):
    """Search one exact saved interval; return proposals without editing cues."""
    p=Project(project_path)
    try:
        item=next((c for c in p.cues() if c['id']==cue_id),None)
        if item is None:raise ValueError('The cue no longer exists.')
        program=p.get('program',{});path=Path(program.get('path',''))
        if not path.is_file():raise ValueError('Relink the program media in Settings first.')
        stat=path.stat()
        if program.get('size') is not None and (stat.st_size!=program['size'] or stat.st_mtime_ns!=program.get('mtime')):
            raise ValueError('The program media changed. Relink the original cut or analyze the new cut first.')
        tracks={t['id']:t for t in p.tracks()}
        if not tracks:raise ValueError('Add or import a reference library first.')
        progress(.02,'Decoding selected cue…')
        duration=item['end']-item['start']
        audio=decode(path,start=item['start'],duration=duration,cancel=cancel) if audio_override is None else np.asarray(audio_override,dtype=np.float32)
        if len(audio)/SR<duration-.25:raise ValueError('The selected cue could not be decoded completely. Existing cues were preserved.')
        settings=p.settings;groups=defaultdict(list)
        for start in range(0,int(np.ceil(duration)),20):
            if cancel():raise Cancelled()
            progress(.1+.85*start/max(1,duration),'Searching selected cue…')
            fp=fingerprints(audio[int(start*SR):int((start+24)*SR)])
            for tid,offset,times,count in match_chunk(p.db,fp,int(settings['min_votes'])):
                groups[tid].append((offset-start,times+start,count))
        candidates=[]
        for tid,hits in groups.items():
            if cancel():raise Cancelled()
            clusters=[]
            for offset,times,count in sorted(hits,key=lambda hit:hit[0]):
                if clusters and abs(np.median(clusters[-1]['offsets'])-offset)<.12:cluster=clusters[-1]
                else:
                    cluster={'offsets':[],'frames':set(),'votes':0};clusters.append(cluster)
                cluster['offsets'].append(offset);cluster['frames'].update(round(t/STEP) for t in times);cluster['votes']+=count
            best=max(clusters,key=lambda cluster:(len(cluster['frames']),cluster['votes']))
            frames=best['frames']
            if len(frames)<int(settings['min_support']):continue
            if (max(frames)-min(frames))*STEP+NFFT/SR<float(settings['min_cue']):continue
            offset=float(np.median(best['offsets']))
            candidates.append({'track':tid,'title':tracks[tid]['metadata']['title'],'votes':best['votes'],
                'support':len(frames),'reference_start':max(0,offset),'program_start':item['start']+max(0,-offset),
                'evidence_start':item['start']+max(0,min(frames)*STEP-.06),
                'evidence_end':item['start']+min(duration,max(frames)*STEP+NFFT/SR),
                'max_evidence_gap':max(np.diff(sorted(frames)),default=0)*STEP})
        candidates.sort(key=lambda c:(c['support'],c['votes']),reverse=True)
        if cancel():raise Cancelled()
        return {'cue_retry':True,'cue':item,'candidates':candidates[:12]}
    finally:p.close()
