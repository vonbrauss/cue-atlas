"""Review, delivery, and recovery services shared by the desktop screens."""
from datetime import datetime,timezone
from contextlib import closing
from pathlib import Path
import json
import math
import os
import re
import shutil
import sqlite3
import tempfile
import uuid


def review_queue(project,threshold=None):
    threshold=project.settings.get('review_threshold',60) if threshold is None else threshold
    result=[];version_reviews=project.get('version_reviews',{})
    for cue in project.included_cues():
        reasons=[]
        if not cue['track']:reasons.append('Version needs review' if cue['id'] in version_reviews else 'Unknown')
        elif cue['status']!='Reviewed':
            reasons.append('Needs review')
            if cue['confidence']<threshold:reasons.append('Weak match')
        if reasons:result.append(cue|{'reasons':reasons})
    return result


def validate_cues(project):
    tracks={t['id']:t for t in project.tracks()};issues=[];valid=[]
    duration=project.get('program',{}).get('duration',0)
    valid_duration=isinstance(duration,(int,float)) and math.isfinite(duration) and duration>0
    def add(c,code,message,severity='warning'):
        issues.append({'cue_id':c['id'],'title':c['title'],'code':code,'message':message,'severity':severity})
    for c in project.included_cues():
        if not valid_duration or not all(isinstance(c[k],(int,float)) and math.isfinite(c[k]) for k in ('start','end')) or not 0<=c['start']<c['end']<=duration:
            add(c,'timing','Cue must have a positive duration within the program.','error');continue
        valid.append(c)
        t=tracks.get(c['track'])
        if not t:
            add(c,'unknown','No reference is assigned.');continue
        for field in ('composer','publisher'):
            if not str(t['metadata'].get(field) or '').strip():add(c,field,f'Missing {field} metadata.')
        if c['status']!='Reviewed':add(c,'unreviewed','Reference assignment has not been reviewed.')
    active=[]
    for c in sorted(valid,key=lambda item:(item['start'],item['end'])):
        active=[a for a in active if a['end']>c['start']+1e-8]
        for a in active:
            add(c,'overlap',f'Overlaps “{a["title"]}” ({a["id"][:8]}) by {min(a["end"],c["end"])-c["start"]:.3f} s; confirm the transition.')
        active.append(c)
    return issues


def snapshot_folder(project):
    identity=project.get('recovery_id')
    if not identity:
        identity=uuid.uuid4().hex;project.set('recovery_id',identity)
    if not re.fullmatch('[a-f0-9]{32}',identity):raise ValueError('Invalid project recovery identity.')
    return project.path.parent/'.cueatlas-snapshots'/identity


def list_snapshots(project):
    if not project.get('recovery_id'):return []
    result=[]
    for path in snapshot_folder(project).glob('*.cueatlas'):
        try:
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
                row=db.execute("SELECT value FROM info WHERE key='snapshot_details'").fetchone()
                details=json.loads(row[0]) if row else {}
            result.append(details|{'path':str(path),'size':path.stat().st_size})
        except (OSError,sqlite3.Error,ValueError):continue
    return sorted(result,key=lambda s:s.get('created_utc',''),reverse=True)


def create_snapshot(project,reason,force=False):
    if project.db.in_transaction:raise ValueError('Finish the current transaction before taking a snapshot.')
    snapshots=list_snapshots(project)
    now=datetime.now(timezone.utc)
    if not force and snapshots:
        latest=datetime.fromisoformat(snapshots[0]['created_utc'])
        if (now-latest).total_seconds()<300:return None
    folder=snapshot_folder(project);folder.mkdir(parents=True,exist_ok=True)
    name=now.strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid.uuid4().hex[:8]
    final=folder/(name+'.cueatlas');temp=folder/(name+'.tmp')
    try:
        project.backup(temp)
        with closing(sqlite3.connect(temp)) as db:
            with db:
                db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('snapshot_details',json.dumps({
                    'created_utc':now.isoformat(),'reason':reason,'project':project.path.name})))
        os.replace(temp,final)
    finally:
        if temp.exists():temp.unlink()
    for old in list_snapshots(project)[20:]:Path(old['path']).unlink()
    return final


def restore_snapshot(project,path):
    path=Path(path).resolve()
    if path.parent!=snapshot_folder(project).resolve() or path.suffix!='.cueatlas':
        raise ValueError('Choose a recovery point from this project’s snapshot list.')
    source=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    try:
        if source.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Snapshot integrity check failed.')
        if source.execute('PRAGMA user_version').fetchone()[0]!=1:raise ValueError('Unsupported snapshot format.')
        source.execute('SELECT id,track,start,end,title FROM cues LIMIT 1')
        source.execute('SELECT id,metadata FROM tracks LIMIT 1')
        identity=project.get('recovery_id');previous=create_snapshot(project,'Before restoring a recovery point',force=True)
        try:source.backup(project.db)
        except Exception:
            with closing(sqlite3.connect(previous)) as rollback:rollback.backup(project.db)
            raise
        project.set('recovery_id',identity);project._store_name()
    finally:source.close()


def save_marker(project,position,text,marker_id=None):
    duration=project.get('program',{}).get('duration',0)
    if not math.isfinite(position) or not 0<=position<=duration:raise ValueError('Marker must be inside the program.')
    if not text.strip():raise ValueError('Enter a marker comment.')
    markers=project.get('markers',[]);marker_id=marker_id or uuid.uuid4().hex
    record={'id':marker_id,'position':position,'text':text.strip()}
    markers=[m for m in markers if m['id']!=marker_id]+[record]
    create_snapshot(project,'Before editing markers')
    project.set('markers',sorted(markers,key=lambda m:m['position']))
    return record


def base_title(track):
    title=track['metadata'].get('title') or Path(track['path']).stem
    title=re.sub(r'\([^)]*\)|\[[^]]*\]',' ',title.casefold())
    title=re.sub(r'\b(instrumental|underscore|alternate|alt|mix|version|full|main|vocal|vocals|edit)\b',' ',title)
    return re.sub(r'[^a-z0-9]+',' ',title).strip()


def duplicate_report(tracks):
    checksums={};titles={};result=[]
    for t in tracks:
        checksum=t['metadata'].get('_content_sha256');title=base_title(t)
        for other in checksums.get(checksum,[]) if checksum else []:
            result.append({'kind':'Exact duplicate','left':other['id'],'right':t['id'],
                           'reason':'Identical file SHA-256 checksum.'})
        if title:
            for other in titles.get(title,[]):
                if checksum and checksum==other['metadata'].get('_content_sha256'):continue
                result.append({'kind':'Possible alternate mix','left':other['id'],'right':t['id'],
                               'reason':'Similar base title; listen to confirm. This is not an audio match.'})
            titles.setdefault(title,[]).append(t)
        if checksum:checksums.setdefault(checksum,[]).append(t)
    return result


def create_handoff(project_path,options,progress=lambda *a:None,cancel=lambda:False):
    """Create a portable folder atomically, leaving the source project untouched."""
    from .project import Project
    from .export import export
    from .audio import Cancelled
    destination=Path(options['destination']).resolve();media=options.get('media','none')
    if media not in ('none','program','all'):raise ValueError('Invalid media selection.')
    if destination.exists():raise ValueError('Choose a new handoff folder; existing folders are preserved.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.cueatlas-handoff-',dir=destination.parent))
    p=Project(project_path);copy=None
    try:
        project_name=p.path.name
        source_tracks=p.tracks();source_program=p.get('program',{})
        p.backup(stage/project_name);copy=Project(stage/project_name)
        # A source may itself be a portable handoff. Resolve its links before
        # placing the database in a different directory.
        with copy.db:
            for t in source_tracks:copy.db.execute('UPDATE tracks SET path=? WHERE id=?',(t['path'],t['id']))
            if source_program:copy.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('program',json.dumps(source_program)))
        issues=validate_cues(copy)
        if any(i['severity']=='error' for i in issues):raise ValueError('Fix invalid cue timing before packaging.')
        # Freeze the project database first. Exports, markers and media links all
        # come from this same copy, even if the original is opened elsewhere.
        tracks=copy.tracks();program=copy.get('program',{})
        export(copy,stage/'cue-sheet.csv')
        (stage/'validation.json').write_text(json.dumps(issues,indent=2),encoding='utf-8')
        (stage/'markers.json').write_text(json.dumps(copy.get('markers',[]),indent=2),encoding='utf-8')
        entries=[];copied={};requests=[]
        if media in ('program','all') and program.get('path'):requests.append(('program',None,program['path']))
        if media=='all':requests.extend(('reference',t['id'],t['path']) for t in tracks)
        for index,(kind,tid,original) in enumerate(requests):
            if cancel():raise Cancelled()
            path=Path(original);entry={'kind':kind,'track':tid,'original':str(path),'status':'missing'}
            progress(index/max(1,len(requests)),f'Collecting {path.name}')
            if path.is_file():
                key=str(path.resolve())
                if key not in copied:
                    relative=Path('media')/(str(len(copied)+1).zfill(4)+'-'+path.name)
                    target=stage/relative;target.parent.mkdir(exist_ok=True)
                    with path.open('rb') as src,target.open('wb') as dst:
                        while chunk:=src.read(4*1024*1024):
                            if cancel():raise Cancelled()
                            dst.write(chunk)
                    shutil.copystat(path,target);copied[key]=relative.as_posix()
                entry.update(status='included',path=copied[key])
                if kind=='program':program['path']=copied[key]
                else:
                    with copy.db:copy.db.execute('UPDATE tracks SET path=? WHERE id=?',(copied[key],tid))
            entries.append(entry)
        with copy.db:
            copy.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('portable_paths','true'))
            if program:copy.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('program',json.dumps(program)))
            # An export opens with clean cue history; recovery copies stay at the source.
            copy.db.execute("DELETE FROM info WHERE key IN ('recovery_id','snapshot_details')")
        # CSV media links use package-relative names rather than staging paths.
        import csv
        with (stage/'cue-sheet.csv').open(encoding='utf-8-sig',newline='') as file:csv_rows=list(csv.reader(file))
        reference_column=csv_rows[0].index('Reference File')
        for row in csv_rows[1:]:
            if row[reference_column] in copied:row[reference_column]=copied[row[reference_column]]
        with (stage/'cue-sheet.csv').open('w',encoding='utf-8-sig',newline='') as file:csv.writer(file).writerows(csv_rows)
        missing=[e for e in entries if e['status']=='missing']
        (stage/'manifest.json').write_text(json.dumps({'project':project_name,'media_mode':media,
            'created_utc':datetime.now(timezone.utc).isoformat(),'files':entries,
            'validation_issues':len(issues)},indent=2),encoding='utf-8')
        (stage/'README.txt').write_text('Open '+project_name+' in Cue Atlas.\n'
            'Keep the media folder beside the project. Included media uses relative paths.\n'
            'Media not included remains linked to its original location.\n'
            f'{len(missing)} requested media file(s) were missing; see manifest.json.\n',encoding='utf-8')
        copy.close();copy=None
        if cancel():raise Cancelled()
        if destination.exists():raise ValueError('The handoff destination now exists. Choose another folder.')
        os.rename(stage,destination)
        return {'handoff':True,'path':str(destination),'missing':len(missing)}
    finally:
        if copy:copy.close()
        p.close()
        if stage.exists():shutil.rmtree(stage)
