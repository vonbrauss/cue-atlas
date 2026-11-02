import csv
import struct
import subprocess
from pathlib import Path
import numpy as np
import pytest
from scipy.io.wavfile import write
from cueatlas.audio import SR,decode,ffmpeg,Cancelled
from cueatlas.engine import import_files,analyze
from cueatlas.project import Project,cue
from cueatlas.timecode import RATES,parse,format_tc
from cueatlas.metadata import read_metadata
from cueatlas.export import export

def music(seed,seconds=18):
    rng=np.random.default_rng(seed);a=np.zeros(int(seconds*SR),np.float32)
    # A changing polyphonic signal with transients; no copyrighted fixture media.
    for start in np.arange(0,seconds,.21):
        n=min(int(.65*SR),len(a)-int(start*SR));t=np.arange(n)/SR
        tone=np.zeros(n)
        for _ in range(4):
            f=rng.uniform(150,3800)
            tone+=np.sin(2*np.pi*f*t+rng.uniform(0,6))*np.exp(-t*rng.uniform(3,12))
        tone+=rng.normal(0,.1,n)*np.exp(-t*25)
        a[int(start*SR):int(start*SR)+n]+=tone*.07
    return a

@pytest.mark.parametrize('rate',RATES)
def test_timecode_round_trip(rate):
    fps,_,_=RATES[rate]
    for frame in [0,1,1799,1800,17982,107892,215784,500000]:
        assert abs(parse(format_tc(frame/fps,rate),rate)-frame/fps)<1e-8

def test_drop_boundary():
    assert format_tc(1800/(30000/1001),'29.97 DF')=='00:01:00;02'
    assert format_tc(17982/(30000/1001),'29.97 DF')=='00:10:00;00'
    with pytest.raises(ValueError):parse('00:01:00;00','29.97 DF')

def test_isolation_persistence_and_export(tmp_path):
    a=Project(tmp_path/'a.cueatlas',True,'Project A');b=Project(tmp_path/'b.cueatlas',True,'Project B')
    f=tmp_path/'test.wav';write(f,SR,music(1,3))
    tid=a.save_track(f,3,{'title':'=BAD()','publisher':'Publisher','license':'License 123','raw':{'custom':'value'}},[(42,3)])
    a.save_cues([cue(tid,0,2,title='Test')]);assert not b.tracks();assert not b.cues()
    backup=tmp_path/'backup.cueatlas';a.backup(backup);a.close();a=Project(backup)
    assert a.get('name')=='backup';assert a.tracks()[0]['metadata']['license']=='License 123'
    out=tmp_path/'cues.csv';export(a,out)
    with out.open(encoding='utf-8-sig') as file:rows=list(csv.DictReader(file))
    assert rows[0]['Track']=="'=BAD()";assert rows[0]['License']=='License 123';assert rows[0]['Publisher']=='Publisher'
    assert float(rows[0]['Duration Seconds'])==2
    a.remove_track(tid);assert a.cues()[0]['track'] is None;assert a.cues()[0]['status']=='Unknown'
    a.close();b.close()

def test_riff_metadata(tmp_path):
    file=tmp_path/'metadata.wav';write(file,SR,music(2,1))
    def chunk(key,data):return key+struct.pack('<I',len(data))+data+(b'\0' if len(data)%2 else b'')
    info=chunk(b'LIST',b'INFO'+chunk(b'INAM',b'Test title\0')+chunk(b'ICOP',b'Copyright owner\0')+chunk(b'IPUB',b'Example Publisher\0'))
    data=file.read_bytes()+info;data=data[:4]+struct.pack('<I',len(data)-8)+data[8:];file.write_bytes(data)
    meta=read_metadata(file)
    assert meta['title']=='Test title';assert meta['publisher']=='Example Publisher';assert meta['copyright']=='Copyright owner'

def test_mp3_tags(tmp_path):
    file=tmp_path/'source.wav';write(file,SR,music(3,3));mp3=tmp_path/'ref.mp3'
    subprocess.run([ffmpeg(),'-v','error','-i',str(file),'-metadata','title=Track Title','-metadata','composer=Composer Name','-metadata','publisher=Publisher Name','-metadata','license=ABC-123',str(mp3)],check=True)
    meta=read_metadata(mp3)
    assert meta['title']=='Track Title';assert meta['composer']=='Composer Name';assert meta['publisher']=='Publisher Name';assert meta['license']=='ABC-123'

def test_match_repeated_edits_and_unknown(tmp_path):
    p=Project(tmp_path/'match.cueatlas',True,'Test')
    refs=[];signals=[]
    for seed in [12,56]:
        f=tmp_path/f'track{seed}.wav';sig=music(seed);write(f,SR,sig);refs.append(str(f));signals.append(sig)
    result=import_files(p.path,refs);assert result['added']==2;assert not result['failures']
    assert import_files(p.path,refs)['skipped']==2
    # A from 3–10, silence, unknown music, B from 2–11, A again from 5–11.
    program=np.concatenate([signals[0][3*SR:10*SR],np.zeros(SR),music(99,4),signals[1][2*SR:11*SR],signals[0][5*SR:11*SR]])
    wav=tmp_path/'program.wav';write(wav,SR,program*.6)
    mp3=tmp_path/'program.mp3';subprocess.run([ffmpeg(),'-v','error','-i',str(wav),'-b:a','96k',str(mp3)],check=True)
    p.set('program',{'path':str(mp3)});result=analyze(p.path)
    cues=p.cues();matched=[c for c in cues if c['track']];unknown=[c for c in cues if not c['track']]
    print('MATCH RESULTS',[(c['title'],round(c['start'],2),round(c['end'],2)) for c in cues])
    for name,start,end in [('track12',0,7),('track56',12,21),('track12',21,27)]:
        candidates=[c for c in matched if c['title']==name and abs(c['start']-start)<.5 and abs(c['end']-end)<.6]
        assert candidates,(name,start,end,cues)
    assert any(7.8<=c['start']<=8.2 and c['end']>=11.5 for c in unknown)
    assert not any(c['start']<=7.5<c['end'] for c in cues)
    assert all(not(c['start']<10<c['end']) for c in matched)
    assert p.get('program')['waveform'];assert not p.get('stale');p.close()

def test_cancel_preserves_results(tmp_path):
    p=Project(tmp_path/'cancel.cueatlas',True,'Cancel');file=tmp_path/'a.wav';write(file,SR,music(1,3))
    import_files(p.path,[str(file)]);p.set('program',{'path':str(file)});old=cue(None,0,1,title='Keep me');p.save_cues([old])
    with pytest.raises(Cancelled):analyze(p.path,cancel=lambda:True)
    assert p.cues()[0]['id']==old['id'];p.close()

def test_crossfade_and_no_false_match(tmp_path):
    p=Project(tmp_path/'cross.cueatlas',True,'Crossfade')
    a,b=music(121,18),music(443,18)
    files=[]
    for name,data in [('A',a),('B',b)]:
        f=tmp_path/f'{name}.wav';write(f,SR,data);files.append(str(f))
    import_files(p.path,files)
    # A plays 0-12, B plays 10-22, with a two-second crossfade.
    x=np.zeros(22*SR,np.float32);x[:12*SR]=a[:12*SR];fade=np.linspace(1,0,2*SR)
    x[10*SR:12*SR]*=fade;bseg=b[:12*SR].copy();bseg[:2*SR]*=1-fade;x[10*SR:]+=bseg
    f=tmp_path/'mix.wav';write(f,SR,x);p.set('program',{'path':str(f)});analyze(p.path)
    cues=[c for c in p.cues() if c['track']]
    assert any(c['title']=='A' and c['start']<.5 and c['end']>11 for c in cues)
    assert any(c['title']=='B' and c['start']<11 and c['end']>21 for c in cues)
    other=tmp_path/'unknown.wav';write(other,SR,music(989,10));p.set('program',{'path':str(other)});analyze(p.path)
    assert not [c for c in p.cues() if c['track']]
    assert len(p.cues())==1 and p.cues()[0]['end']==10
    p.close()

def test_excel_export(tmp_path):
    from openpyxl import load_workbook
    p=Project(tmp_path/'excel.cueatlas',True,'Excel project');p.save_cues([cue(None,3,7,title='Unknown 001')])
    out=tmp_path/'cues.xlsx';export(p,out)
    wb=load_workbook(out);ws=wb.active
    assert ws.cell(2,2).value=='Unknown 001';assert ws.cell(2,7).value==4
    assert ws.freeze_panes=='A2';p.close()
