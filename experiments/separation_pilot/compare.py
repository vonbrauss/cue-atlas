"""Read-only separation pilot; deliberately separate from the desktop app.

Prepare: main app Python, compare.py prepare PROJECT OUTPUT
Compare: main app Python, compare.py compare PROJECT OUTPUT
Separated files should be OUTPUT/music/<sample_id>.wav.
"""
import argparse
import json
import sqlite3
import subprocess
import time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from cueatlas.project import Project
from cueatlas import engine
from cueatlas.audio import ffmpeg


class ReadOnlyProject(Project):
    def __init__(self,path,item=None,media=None):
        self.path=Path(path).resolve()
        self.db=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)
        self.db.row_factory=sqlite3.Row
        st=self.path.stat();self._identity=(st.st_dev,st.st_ino);self._history_summary_cache=None
        self.item=item;self.media=media
        if self.db.execute('PRAGMA user_version').fetchone()[0]!=1:
            raise ValueError('Unsupported project format')
    def cues(self):
        return [dict(self.item)] if self.item else super().cues()
    def get(self,key,default=None):
        value=super().get(key,default)
        if key=='program' and self.media:
            st=self.media.stat()
            return dict(value or {},path=str(self.media),size=st.st_size,mtime=st.st_mtime_ns,
                        duration=self.item['end']-self.item['start'])
        return value


def identify(project,sample,audio):
    item=sample['cue']|{'start':0.,'end':sample['duration']}
    original=engine.Project
    engine.Project=lambda path:ReadOnlyProject(path,item,audio)
    started=time.perf_counter()
    try:result=engine.identify_cue(project,item['id'])
    finally:engine.Project=original
    return {'candidates':result['candidates'],'seconds':time.perf_counter()-started}


def prepare(project,out):
    if (out/'manifest.json').exists():raise ValueError('Use a new output directory to preserve earlier results.')
    p=ReadOnlyProject(project)
    try:
        program=p.get('program');rows=p.cues();hidden=p.excluded_cue_ids()
        tracks={t['id']:t for t in p.tracks()}
        if not program or not Path(program['path']).is_file():raise ValueError('Program media is missing.')
        st=Path(program['path']).stat()
        if 'size' in program and (program['size']!=st.st_size or program.get('mtime')!=st.st_mtime_ns):
            raise ValueError('Program media differs from the analyzed file.')
        reviewed=[c for c in rows if c['track'] in tracks and c['status']=='Reviewed' and c['id'] not in hidden and c['end']-c['start']>=10]
        unknown=[c for c in rows if not c['track'] and c['id'] not in hidden and c['end']-c['start']>=10]
        def spread(items,n):
            if not items:return []
            return [items[i] for i in sorted({round(k*(len(items)-1)/max(1,n-1)) for k in range(min(n,len(items)))})]
        chosen=[('reviewed',c) for c in spread(reviewed,5)]+[('unknown',c) for c in spread(unknown,3)]
        samples=[];(out/'original').mkdir(parents=True,exist_ok=True);(out/'music').mkdir(exist_ok=True)
        for index,(group,c) in enumerate(chosen,1):
            duration=min(20.,c['end']-c['start']);start=(c['start']+c['end']-duration)/2
            sid=f'{index:02}-{group}';audio=out/'original'/f'{sid}.wav'
            subprocess.run([ffmpeg(),'-v','error','-ss',str(start),'-i',program['path'],'-t',str(duration),'-vn','-ac','1','-ar','48000','-c:a','pcm_f32le',str(audio)],check=True)
            sample={'id':sid,'group':group,'cue':c,'source_start':start,'duration':duration,
                    'expected_track':c['track'] if group=='reviewed' else None,
                    'expected_title':tracks[c['track']]['metadata']['title'] if group=='reviewed' else None}
            sample['original']=identify(project,sample,audio)
            samples.append(sample)
            print(json.dumps({'sample':sid,'start':start,'expected':sample['expected_title'],'baseline':sample['original']}),flush=True)
        manifest={'project':str(project),'program':program['path'],'settings':p.settings,'samples':samples,
                  'source_size':st.st_size,'source_mtime_ns':st.st_mtime_ns,'note':'Reviewed assignments are provisional ground truth. Unknown matches require listening review. No no-music control has been labeled.'}
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    finally:p.close()


def run_comparison(project,out):
    manifest=json.loads((out/'manifest.json').read_text());results=[]
    p=ReadOnlyProject(project)
    try:
        if p.settings!=manifest['settings']:raise ValueError('Matching settings changed since baseline.')
        program=p.get('program');st=Path(program['path']).stat()
        if program['path']!=manifest['program'] or st.st_size!=manifest['source_size'] or st.st_mtime_ns!=manifest['source_mtime_ns']:
            raise ValueError('Program media changed since baseline.')
    finally:p.close()
    for sample in manifest['samples']:
        music=out/'music'/f"{sample['id']}.wav"
        if not music.exists():continue
        after=identify(project,sample,music)
        expected=sample['expected_track']
        def rank(result):return next((i+1 for i,c in enumerate(result['candidates']) if c['track']==expected),None) if expected else None
        result={'id':sample['id'],'source_start':sample['source_start'],'duration':sample['duration'],
                'expected_title':sample['expected_title'],'original':sample['original'],'separated':after,
                'original_correct_rank':rank(sample['original']),'separated_correct_rank':rank(after)}
        results.append(result);print(json.dumps(result),flush=True)
    (out/'results.json').write_text(json.dumps(results,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','compare']);parser.add_argument('project',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();args.output=args.output.resolve()
    (prepare if args.mode=='prepare' else run_comparison)(args.project.resolve(),args.output)
