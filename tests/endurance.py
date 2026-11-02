"""Optional one-hour synthesized endurance check. Run: python tests/endurance.py"""
import sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_core import music
from cueatlas.audio import SR
from cueatlas.project import Project
from cueatlas.engine import import_files,analyze
from cueatlas.coverage import covered_seconds
from scipy.io.wavfile import write
import numpy as np
start=time.monotonic()
with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory);p=Project(directory/'hour.cueatlas',True,'Hour test')
    a,b=music(33),music(44)
    for name,data in [('A',a),('B',b)]:write(directory/f'{name}.wav',SR,data)
    import_files(p.path,[str(directory/'A.wav'),str(directory/'B.wav')])
    block=np.concatenate([a[2*SR:10*SR],np.zeros(2*SR),b[3*SR:11*SR],np.zeros(2*SR)])
    write(directory/'hour.wav',SR,np.tile(block,180).astype(np.float32))
    p.set('program',{'path':str(directory/'hour.wav')});result=analyze(p.path)
    matched=[c for c in p.cues() if c['track']]
    print({'seconds':result['duration'],'matched_uses':len(matched),'expected':360,'elapsed_seconds':round(time.monotonic()-start,2)})
    assert len(matched)==360
    assert abs(covered_seconds(p.cues(),3600)-3600)<1e-7
    assert p.cues()[0]['start']==0 and max(c['end'] for c in p.cues())==3600
    p.close()
