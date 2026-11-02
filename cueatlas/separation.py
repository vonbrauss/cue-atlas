"""Optional AI setup, isolated inference, cached proposals, and explicit apply."""
import hashlib,json,os,platform,queue,shutil,subprocess,sys,tarfile,tempfile,threading,time,uuid
from pathlib import Path
from scipy.io.wavfile import write
from .audio import SR,Cancelled,content_hash,decode
from .engine import identify_cue
from .project import Project

MODEL_ID='bandit-v2-multilingual-v1'
MODEL_SHA='abcfccf65446752a057f4a302c941479a54b7560ebf8d7bca039d2ea98e64cfc'
MODEL_BYTES=446680129
MODEL_URL='https://zenodo.org/records/12701995/files/checkpoint-multi.ckpt'
PYTHON_URL='https://github.com/astral-sh/python-build-standalone/releases/download/20261026/cpython-3.13.18%2B20261026-aarch64-apple-darwin-install_only_stripped.tar.gz'
PYTHON_SHA='8392b6ea51d94391befb2c31ebe75463f045d0b69dfcf5e1bb3234e1f5fa3405'
ASSETS=Path(__file__).with_name('ai_assets')
MAX_SECONDS=300


def home():
    override=os.environ.get('CUEATLAS_AI_HOME')
    if override:return Path(override).expanduser().resolve()
    return Path.home()/'Library'/'Application Support'/'CueAtlas'/'AI'


def installed():
    root=home()/'engine'
    try:
        info=json.loads((root/'installation.json').read_text())
        return info.get('model')==MODEL_ID and (root/'venv/bin/python').is_file() and (root/'model.ckpt').stat().st_size==MODEL_BYTES
    except (OSError,ValueError):return False


def _run(command,cancel,progress=lambda *a:None,label='Processing…',details=False):
    with tempfile.TemporaryFile(mode='w+b') as log:
        child=subprocess.Popen([str(c) for c in command],stdout=log,stderr=log)
        try:
            while child.poll() is None:
                if cancel():raise Cancelled()
                message=label
                if details:
                    length=os.fstat(log.fileno()).st_size
                    lines=os.pread(log.fileno(),1500,max(0,length-1500)).decode(errors='replace').splitlines()
                    if lines:message+='\n'+lines[-1][-180:]
                progress(message);time.sleep(.1)
            if child.returncode:
                log.seek(0);details=log.read()[-3000:].decode(errors='replace')
                raise ValueError(label+'\n'+details)
        finally:
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=2)
                except subprocess.TimeoutExpired:child.kill();child.wait()


def _download(url,target,checksum,cancel,progress,label,total=None):
    def report(_):
        count=target.stat().st_size if target.exists() else 0
        fraction=min(1,count/total) if total else 0
        progress(fraction,f'{label} · {count/1e6:.1f} / {total/1e6:.1f} MB · {fraction:.0%}' if total else f'{label} · {count/1e6:.0f} MB')
    _run(['/usr/bin/curl','--fail','--location','--silent','--show-error','--retry','2','--connect-timeout','15','--output',target,url],cancel,
         report)
    progress(-1,'Verifying download…')
    if content_hash(target,cancel)!=checksum:raise ValueError('Downloaded component failed its checksum check.')


def install_engine(project_path=None,options=None,progress=lambda *a:None,cancel=lambda:False):
    if sys.platform!='darwin' or platform.machine()!='arm64':raise ValueError('This AI installer currently supports Apple Silicon Macs.')
    if installed():return {'ai_install':True}
    parent=home();parent.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(parent).free<3*1024**3:raise ValueError('AI installation needs at least 3 GB of free disk space for setup.')
    with tempfile.TemporaryDirectory(prefix='install-',dir=parent) as folder:
        stage=Path(folder);archive=stage/'python.tar.gz'
        _download(PYTHON_URL,archive,PYTHON_SHA,cancel,progress,'Downloading AI Python',total=25265774)
        if cancel():raise Cancelled()
        progress(-1,'Preparing isolated AI runtime…')
        with tarfile.open(archive) as bundle:bundle.extractall(stage,filter='data')
        _run([stage/'python/bin/python3','-m','venv',stage/'venv'],cancel)
        shutil.copytree(ASSETS,stage/'assets',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        _run([stage/'venv/bin/python','-m','pip','install','--disable-pip-version-check','--no-input','--no-cache-dir','-r',stage/'assets/requirements.txt'],cancel,
             lambda s:progress(-1,s),'Installing AI libraries…',details=True)
        _download(MODEL_URL,stage/'model.ckpt',MODEL_SHA,cancel,progress,'Downloading BandIt model',total=MODEL_BYTES)
        probe=stage/'probe.json';probe.write_text(json.dumps({'checkpoint':str(stage/'model.ckpt'),'jobs':[]}))
        _run([stage/'venv/bin/python','-I',stage/'assets/runner.py',probe],cancel,
             lambda s:progress(-1,s),'Verifying AI engine…')
        archive.unlink();probe.unlink()
        # Venv launchers contain absolute interpreter paths: retain the staged
        # runtime at its final location and rewrite these after the atomic move.
        (stage/'installation.json').write_text(json.dumps({'model':MODEL_ID,'sha256':MODEL_SHA}))
        target=parent/'engine'
        if target.exists():raise ValueError('An incomplete AI engine exists. Uninstall it before installing again.')
        os.rename(stage,target)
        config=target/'venv/pyvenv.cfg';config.write_text(config.read_text().replace(str(stage),str(target)))
        for entry in (target/'venv/bin').iterdir():
            if entry.is_symlink():
                link=os.readlink(entry)
                if str(stage) in link:entry.unlink();entry.symlink_to(link.replace(str(stage),str(target)))
        relocated=target/'relocation-check.json';relocated.write_text(json.dumps({'checkpoint':str(target/'model.ckpt'),'jobs':[]}))
        try:_run([target/'venv/bin/python','-I',target/'assets/runner.py',relocated],cancel,lambda s:progress(-1,s),'Finishing installation…')
        except BaseException:
            shutil.rmtree(target);raise
        finally:relocated.unlink(missing_ok=True)
        # pip entry points are not used after installation. Python uses the
        # portable interpreter retained in engine/python and this venv config.
    progress(1,'AI music separation installed')
    return {'ai_install':True}


def clear_cache():
    path=home()/'cache'
    if path.exists():shutil.rmtree(path)


def uninstall_engine():
    path=home()/'engine'
    if path.exists():shutil.rmtree(path)


def cache_key(source_digest,item):
    data=[source_digest,item['start'],item['end'],MODEL_ID,MODEL_SHA,'mono-48k-window8-hop4-reflect4']
    return hashlib.sha256(json.dumps(data,separators=(',',':')).encode()).hexdigest()


def _events(request,cancel):
    root=home()/'engine';messages=queue.Queue()
    with tempfile.TemporaryFile(mode='w+b') as errors:
        child=subprocess.Popen([str(root/'venv/bin/python'),'-I',str(root/'assets/runner.py'),str(request)],stdout=subprocess.PIPE,stderr=errors,text=True)
        def read():
            for line in child.stdout:
                try:messages.put(json.loads(line))
                except ValueError:pass
            messages.put(None)
        reader=threading.Thread(target=read,daemon=True);reader.start()
        try:
            while True:
                if cancel():raise Cancelled()
                try:message=messages.get(timeout=.1)
                except queue.Empty:continue
                if message is None:break
                yield message
            child.wait()
            if child.returncode:
                errors.seek(0);raise ValueError('AI processing failed. '+errors.read()[-2000:].decode(errors='replace'))
        finally:
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=2)
                except subprocess.TimeoutExpired:child.kill();child.wait()
            child.stdout.close();reader.join(timeout=2)


def result_path(project_path):
    key=hashlib.sha256(str(Path(project_path).resolve()).encode()).hexdigest()
    return home()/'results'/(key+'.json')


def _save_result(project_path,result):
    path=result_path(project_path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(result));os.replace(temporary,path)


def library_signature(project):
    # Small reference records suffice: importing/replacing landmarks changes
    # the source identity. Avoid scanning the large fingerprint table.
    records=[{k:t[k] for k in ('id','size','mtime','duration','metadata')} for t in project.tracks()]
    return hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest()


def separate_program(source,samples,progress=lambda *a:None,cancel=lambda:False,start_seconds=0,total_samples=None,source_digest=None):
    """Separate bounded overlapping blocks, stitch their cores on the source clock."""
    import numpy as np
    if not installed():raise ValueError('Install AI music separation in Project settings first.')
    if samples<=0:raise ValueError('The program has no audio to separate.')
    progress(0,'Checking program audio cache…');digest=source_digest or content_hash(source,cancel)
    cache=home()/'cache';cache.mkdir(parents=True,exist_ok=True)
    output=np.empty(samples,dtype=np.float32);block=60*SR;context=4*SR
    base=round(start_seconds*SR);total_samples=samples if total_samples is None else total_samples
    if base<0 or base+samples>total_samples:raise ValueError('AI range lies outside the program.')
    chunks=[]
    for start in range(0,samples,block):
        end=min(samples,start+block);a=max(0,base+start-context);b=min(total_samples,base+end+context)
        path=cache/(cache_key(digest+'full-program-60-context4-v1',{'start':a/SR,'end':b/SR})+'.wav')
        chunks.append({'id':str(start),'start':start,'end':end,'a':a,'b':b,'output':str(path)})
    def consume(chunk):
        data=decode(chunk['output'],cancel=cancel)
        expected=chunk['b']-chunk['a']
        if abs(len(data)-expected)>1 or not np.isfinite(data).all():
            raise ValueError('Separated audio length does not match the program timeline.')
        # Resampling can round the final endpoint by one sample, never a block.
        if len(data)<expected:data=np.pad(data,(0,expected-len(data)))
        first=base+chunk['start']-chunk['a']
        output[chunk['start']:chunk['end']]=data[first:first+chunk['end']-chunk['start']]
        from .monitor_audio import register
        register(source,(base+chunk['start'])/SR,(base+chunk['end'])/SR,chunk['output'],first/SR,digest=digest)
    pending=[]
    for chunk in chunks:
        if cancel():raise Cancelled()
        if Path(chunk['output']).exists():
            try:consume(chunk)
            except (OSError,ValueError):Path(chunk['output']).unlink(missing_ok=True)
            else:continue
        pending.append(chunk)
    if not pending:progress(1,'Reusing AI music for the full program');return output
    # Inputs and cached float WAV outputs coexist until the helper completes.
    required=sum((c['b']-c['a'])/SR*48000*8 for c in pending)+256*1024**2
    if shutil.disk_usage(cache).free<required:raise ValueError(f'Full-program AI analysis needs about {required/1024**3:.1f} GB of free space for temporary and cached audio.')
    with tempfile.TemporaryDirectory(prefix='program-',dir=home()) as folder:
        folder=Path(folder);jobs=[]
        for index,chunk in enumerate(pending):
            if cancel():raise Cancelled()
            progress(.15*index/len(pending),f'Preparing AI audio · {index+1}/{len(pending)}')
            audio=decode(source,start=chunk['a']/SR,duration=(chunk['b']-chunk['a'])/SR,cancel=cancel,sample_rate=48000)
            if abs(len(audio)/48000-(chunk['b']-chunk['a'])/SR)>.002:raise ValueError('Program audio could not be decoded completely for AI analysis.')
            path=folder/(chunk['id']+'.wav');write(path,48000,audio)
            jobs.append({'id':chunk['id'],'input':str(path),'output':chunk['output']})
        request=folder/'request.json';request.write_text(json.dumps({'checkpoint':str(home()/'engine/model.ckpt'),'jobs':jobs}))
        by_id={c['id']:c for c in pending};completed=set()
        for message in _events(request,cancel):
            if message['type']=='ready':progress(.15,'AI engine ready · '+message['device'])
            elif message['type']=='progress':progress(.15+.85*(len(completed)+message['fraction'])/len(pending),f'Separating full program · {len(completed)+1}/{len(pending)}')
            elif message['type']=='error':raise ValueError('AI separation failed: '+message['message'])
            elif message['type']=='done':
                chunk=by_id[message['id']]
                try:consume(chunk)
                except (ValueError,OSError):Path(chunk['output']).unlink(missing_ok=True);raise
                completed.add(message['id']);Path(next(j['input'] for j in jobs if j['id']==message['id'])).unlink(missing_ok=True)
        if len(completed)!=len(pending):raise ValueError('AI separation ended before the full program was processed.')
    if cancel():raise Cancelled()
    progress(1,'Full-program music ready');return output


def analyze_program(project_path,progress=lambda *a:None,cancel=lambda:False):
    from .engine import analyze
    return analyze(project_path,progress=progress,cancel=cancel,use_separation=True)


def hybrid_analysis(project_path,progress=lambda *a:None,cancel=lambda:False):
    """Commit the standard pass, then propose AI matches only for unresolved intervals."""
    from .engine import analyze
    from .versions import annotate_results
    if not installed():raise ValueError('Install AI music separation in Project settings first.')
    baseline=analyze(project_path,progress=lambda n,s:progress(n*.4,'Standard pass · '+s),cancel=cancel,
                     version_aware=True,unknown_max_seconds=120)
    p=Project(project_path)
    try:
        p.set('analysis_mode','standard_ai_followup')
        unknown=[c['id'] for c in p.included_cues() if c['track'] is None and c['status']=='Unknown']
        pending=p.get('version_reviews',{})
        result={'ai_batch':True,'project':str(p.path),'settings':p.settings,'program':p.get('program'),
                'library':library_signature(p),'items':[],'cancelled':bool(cancel())}
    finally:p.close()
    if unknown and not result['cancelled']:
        try:result=analyze_separated(project_path,{'ids':unknown},progress=lambda n,s:progress(.4+.6*n,'AI follow-up · '+s),cancel=cancel)
        except Cancelled:result['cancelled']=True
        except Exception as exc:result['failure']=str(exc)
    p=Project(project_path)
    try:
        for row in p.cues():
            if row['id'] in pending:
                result['items'].append({'cue':row,'original':pending[row['id']],'separated':[],'error':None,'pending':False,'not_separated':True})
        result.update(hybrid=True,standard_cues=baseline['cues'],unknown_searched=len(unknown))
        annotate_results(result,p);_save_result(project_path,result)
    finally:p.close()
    progress(1,'Standard pass saved · follow-up ready for review');return result


def analyze_separated(project_path,request,progress=lambda *a:None,cancel=lambda:False):
    if not installed():raise ValueError('Install AI music separation in Project → Project settings first.')
    p=Project(project_path)
    try:
        rows=p.cues();program=p.get('program',{});settings=p.settings;hidden=p.excluded_cue_ids()
        ids=set(request['ids']) if request.get('ids') is not None else {c['id'] for c in rows if not c['track'] and c['status']=='Unknown'}
        items=[c for c in rows if c['id'] in ids and c['id'] not in hidden]
        if not items:raise ValueError('No eligible cues to analyze.')
        path=Path(program.get('path',''))
        if not path.is_file():raise ValueError('Relink the program media first.')
        st=path.stat()
        if 'size' in program and (st.st_size!=program['size'] or st.st_mtime_ns!=program.get('mtime')):raise ValueError('Program media changed; relink or analyze the original cut first.')
        progress(0,'Checking source for reusable AI audio…');digest=content_hash(path,cancel)
        result={'ai_batch':True,'project':str(Path(project_path).resolve()),'settings':settings,'program':program,'library':library_signature(p),'items':[],'cancelled':False}
        cache=home()/'cache';cache.mkdir(parents=True,exist_ok=True)
        pending_seconds=sum(min(program['duration'],c['end']+4)-max(0,c['start']-4) for c in items
                            if c['end']-c['start']<=MAX_SECONDS and not (cache/(cache_key(digest+'cue-context4-v1',c)+'.wav')).exists())
        required=pending_seconds*48000*8+256*1024**2
        if pending_seconds and shutil.disk_usage(cache).free<required:raise ValueError(f'AI follow-up needs about {required/1024**3:.1f} GB of free space for temporary and cached audio.')
        try:
            with tempfile.TemporaryDirectory(prefix='cueatlas-ai-',dir=home()) as folder:
                folder=Path(folder);jobs=[];by_id={}
                for i,item in enumerate(items):
                    if cancel():raise Cancelled()
                    entry={'cue':item,'original':[],'separated':[],'error':None,'pending':True};result['items'].append(entry);by_id[item['id']]=entry
                    if item['end']-item['start']>MAX_SECONDS:
                        entry['error']='Split cues longer than five minutes before AI processing.';entry['pending']=False;continue
                    progress(.05+.25*i/len(items),f'Searching original audio · {i+1}/{len(items)}')
                    entry['original']=identify_cue(project_path,item['id'],cancel=cancel)['candidates']
                    output=cache/(cache_key(digest+'cue-context4-v1',item)+'.wav');entry['audio']=str(output)
                    if output.exists():
                        try:entry['separated']=identify_cue(project_path,item['id'],cancel=cancel,audio_override=decode(output,cancel=cancel))['candidates']
                        except (OSError,ValueError):output.unlink(missing_ok=True)
                        else:
                            from .monitor_audio import register
                            register(path,item['start'],item['end'],output,digest=digest)
                            entry['cached']=True;entry['pending']=False;continue
                    source=folder/(item['id']+'.wav')
                    context_start=max(0,item['start']-4);context_end=min(program['duration'],item['end']+4)
                    audio=decode(path,start=context_start,duration=context_end-context_start,cancel=cancel,sample_rate=48000)
                    if len(audio)/48000<context_end-context_start-.25:raise ValueError('The cue could not be decoded completely.')
                    write(source,48000,audio)
                    entry['context_start']=context_start
                    jobs.append({'id':item['id'],'input':str(source),'output':str(folder/(item['id']+'-music.wav'))})
                _save_result(project_path,result)
                if jobs:
                    manifest=folder/'request.json';manifest.write_text(json.dumps({'checkpoint':str(home()/'engine/model.ckpt'),'jobs':jobs}))
                    done=0
                    try:
                        for message in _events(manifest,cancel):
                            if message['type']=='ready':progress(.3,'AI engine ready · '+message['device'])
                            elif message['type']=='progress':progress(.3+.65*(done+message['fraction'])/len(jobs),f'Separating music · {done+1}/{len(jobs)}')
                            elif message['type'] in ('done','error'):
                                entry=by_id[message['id']];done+=1
                                entry['pending']=False
                                if message['type']=='error':entry['error']=message['message']
                                else:
                                    entry['seconds']=message['seconds']
                                    raw=next(j['output'] for j in jobs if j['id']==entry['cue']['id'])
                                    music=decode(raw,cancel=cancel,sample_rate=48000)
                                    first=round((entry['cue']['start']-entry['context_start'])*48000);count=round((entry['cue']['end']-entry['cue']['start'])*48000)
                                    music=music[first:first+count]
                                    if len(music)<count-2:raise ValueError('Separated cue audio is incomplete.')
                                    temporary=Path(entry['audio']).with_suffix('.partial.wav');write(temporary,48000,music);os.replace(temporary,entry['audio'])
                                    from .monitor_audio import register
                                    register(path,entry['cue']['start'],entry['cue']['end'],entry['audio'],digest=digest)
                                    entry['separated']=identify_cue(project_path,entry['cue']['id'],cancel=cancel,audio_override=decode(entry['audio'],cancel=cancel))['candidates']
                                    for job in jobs:
                                        if job['id']==entry['cue']['id']:
                                            Path(job['input']).unlink(missing_ok=True);Path(job['output']).unlink(missing_ok=True);break
                                _save_result(project_path,result)
                    except Cancelled:result['cancelled']=True
                    except Exception as exc:result['failure']=str(exc)
        except Cancelled:result['cancelled']=True
        from .versions import annotate_results
        annotate_results(result,p)
        _save_result(project_path,result);progress(1,'AI batch cancelled' if result['cancelled'] else 'AI batch ready for review')
        return result
    finally:p.close()


def merged_proposals(project,results,choices):
    """Return rows with chosen matches and touching same-reference neighbors joined."""
    current=project.cues();hidden=project.excluded_cue_ids();changed=set()
    entries={r['cue']['id']:r for r in results['items']}
    for row in current:
        cid=row['id']
        if cid not in choices:continue
        if cid not in entries or row!=entries[cid]['cue']:raise ValueError('A cue changed after the search. Run AI analysis again.')
        candidate=choices[cid]
        from .versions import review_choices
        allowed=entries[cid]['original']+entries[cid]['separated']+review_choices(entries[cid])
        if candidate not in allowed:raise ValueError('Unknown reference proposal.')
        if cid in hidden:raise ValueError('Restore excluded cues before applying matches.')
        if candidate.get('version_unresolved'):
            names=[project.track(tid)['metadata']['title'] for tid in candidate['version_tracks']]
            note='Version needs review: '+', '.join(names)+'. No recording-specific license assigned.'
            row.update(track=None,title=candidate['title'],status='Needs review',confidence=0,
                       note='\n'.join(dict.fromkeys(filter(None,[row['note'],note]))))
            changed.add(cid);continue
        reference=project.track(candidate['track'])
        if reference is None:raise ValueError('A proposed reference was removed. Run analysis again.')
        row.update(track=reference['id'],title=reference['metadata']['title'],status='Needs review',confidence=0,
                   note='\n'.join(filter(None,[row['note'],'AI-assisted reference proposal; verify by listening.'])))
        changed.add(cid)
    missing=set(choices)-{c['id'] for c in current}
    if missing:raise ValueError('A cue was removed after the search.')
    # Full chronological adjacency prevents merging across an intervening
    # different-reference or excluded row, including overlapping material.
    groups=[]
    anchors=project.get('cue_matches',{})
    def continuous(left,right):
        if not results.get('strict_neighbor_merge'):return True
        a=choices.get(left['id'],anchors.get(left['id'],{}));b=choices.get(right['id'],anchors.get(right['id'],{}))
        if a.get('comparison_only') or b.get('comparison_only'):return False
        if a.get('track')!=left['track'] or b.get('track')!=right['track']:return False
        if not all('reference_start' in c and 'program_start' in c for c in (a,b)):return False
        from .versions import offset,covers_interval,CONTINUITY_TOLERANCE
        if left['id'] in choices and not covers_interval(a,left):return False
        if right['id'] in choices and not covers_interval(b,right):return False
        return abs(offset(a)-offset(b))<=CONTINUITY_TOLERANCE
    for row in current:
        if groups and row['track'] and row['id'] not in hidden:
            group=groups[-1]
            if all(c['track']==row['track'] and c['id'] not in hidden for c in group) and abs(max(c['end'] for c in group)-row['start'])<=1e-6 and continuous(group[-1],row):
                group.append(row);continue
        groups.append([row])
    output=[];joined=0
    for group in groups:
        if len(group)>1 and any(c['id'] in changed for c in group):
            joined+=len(group)-1
            row=group[0]|{'id':uuid.uuid4().hex,'end':max(c['end'] for c in group),'status':'Needs review','confidence':0,
                         'note':'\n'.join(dict.fromkeys(c['note'] for c in group if c['note']))+'\nJoined adjoining cues after AI review.'}
            output.append(row)
        else:output.extend(group)
    return output,joined


def apply_matches(project,results,choices):
    if not choices:return 0
    if results['project']!=str(project.path.resolve()):raise ValueError('These results belong to another project.')
    if library_signature(project)!=results['library']:raise ValueError('The reference library changed. Run analysis again.')
    if project.settings!=results['settings'] or project.get('program',{})!=results['program']:raise ValueError('Project settings or program changed. Run analysis again.')
    program=results['program'];path=Path(program.get('path',''))
    if path.is_file() and 'size' in program:
        st=path.stat()
        if st.st_size!=program['size'] or st.st_mtime_ns!=program.get('mtime'):raise ValueError('Program media changed since the AI search.')
    rows,joined=merged_proposals(project,results,choices)
    state=project._edit_state();before=state['cues'];matches=project.get('cue_matches',{});matches_before=dict(matches)
    versions=project.get('version_reviews',{});versions_before=dict(versions)
    entries={e['cue']['id']:e for e in results['items']}
    for cid,candidate in choices.items():
        if candidate.get('version_unresolved'):
            versions[cid]=candidate['version_candidates']
            matches.pop(cid,None)
        else:versions.pop(cid,None)
    existing={c['id'] for c in before}
    for row in rows:
        if row['track'] is None:continue
        if choices.get(row['id'],{}).get('comparison_only'):
            matches.pop(row['id'],None);continue
        if row['id'] in existing and row['id'] not in choices:continue
        first=next((c for c in before if c['start']==row['start'] and c['track']==row['track'] and c['id'] not in choices),None)
        saved=matches.get(first['id'],{}) if first else {}
        if saved.get('track')==row['track']:
            matches[row['id']]=dict(saved);continue
        for original in before:
            if original['id'] not in choices:continue
            if row['track']!=choices[original['id']]['track'] or not row['start']<=original['start']<row['end']:continue
            anchor=choices[original['id']]
            offset=anchor['reference_start']-anchor['program_start']
            matches[row['id']]={'track':row['track'],'reference_start':max(0,row['start']+offset),'program_start':max(row['start'],-offset)}
            break
    with project.db:
        project.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('cue_matches',json.dumps(matches)))
        project.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('version_reviews',json.dumps(versions)))
        project._write_cues(rows)
        project.db.execute("DELETE FROM info WHERE key IN ('undo_trim','undo_merge')")
        project._record_edit('Apply AI matches and merge',state,matches_before,versions_before)
    return joined
