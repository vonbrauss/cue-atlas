import numpy as np
import pytest
from pathlib import Path
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from cueatlas import monitor_audio as monitor
from cueatlas.audio import decode,SR,Cancelled
from test_ai_program_analysis import identity_engine
from test_timeline import fixture_project,open_window
from test_lasso import drag_box

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setenv('CUEATLAS_AI_HOME',str(tmp_path/'ai'))
    monkeypatch.setattr(monitor.ai,'installed',lambda:True)

def test_range_aligned_original_preserved_cache_reused(tmp_path,monkeypatch):
    p,rows=fixture_project(tmp_path);source=Path(p.get('program')['path']);before=source.read_bytes();state=p._edit_state();history=p.edit_history()
    jobs=identity_engine(monkeypatch)
    result=monitor.timeline_audio(p.path,{'range':[2,5]})['preview']
    assert len(jobs)==1 and result['regions']==[[2,5]]
    original=decode(source,sample_rate=48000);mixed=decode(result['path'],sample_rate=48000)
    assert len(mixed)==len(original)
    assert np.allclose(mixed[:2*48000],original[:2*48000],atol=.0001)
    assert np.allclose(mixed[5*48000:],original[5*48000:],atol=.0001)
    assert np.max(abs(mixed[3*48000:4*48000]-original[3*48000:4*48000]))<.002
    assert monitor.descriptor(p.get('program'))==result
    monitor.timeline_audio(p.path,{'range':[2,5]});assert len(jobs)==1
    assert source.read_bytes()==before and p._edit_state()==state and p.edit_history()==history
    p.close()

def test_disjoint_coverage_and_cancel_preserves_preview(tmp_path,monkeypatch):
    p,rows=fixture_project(tmp_path);identity_engine(monkeypatch)
    monitor.timeline_audio(p.path,{'range':[1,3]})
    ready=monitor.timeline_audio(p.path,{'range':[7,9]})['preview']
    assert ready['regions']==[[1,3],[7,9]]
    with pytest.raises(Cancelled):monitor.timeline_audio(p.path,{},cancel=lambda:True)
    assert monitor.descriptor(p.get('program'))==ready
    Path(p.get('program')['path']).write_bytes(b'changed')
    assert monitor.descriptor(p.get('program')) is None;p.close()

def test_legacy_full_cache_rebuilt_without_ai(tmp_path,monkeypatch):
    import shutil
    p,rows=fixture_project(tmp_path);source=p.get('program')['path'];identity_engine(monkeypatch)
    monitor.ai.separate_program(source,12*SR)
    shutil.rmtree(monitor.directory(source))
    monkeypatch.setattr(monitor.ai,'_events',lambda *a:pytest.fail('Must reuse cache'))
    ready=monitor.timeline_audio(p.path,{})['preview'];assert ready['regions']==[[0,12]];p.close()

def test_range_drag_no_cue_edits_and_monitor_preserves_view(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);identity_engine(monkeypatch);t=w.timeline
    history=w.p.edit_history();t.set_view(0,12)
    drag_box(t,QPoint(round(t.x_at(2)),t.height()-25),QPoint(round(t.x_at(5)),t.height()-25),Qt.AltModifier)
    assert abs(t.mark_in-2)<.05 and abs(t.mark_out-5)<.05
    assert t.selected==set() and w.separate_range_button.isEnabled()
    assert w.p.cues()==rows and w.p.edit_history()==history
    w.monitor_descriptor=monitor.timeline_audio(w.p.path,{'range':[2,5]})['preview']
    t.position=3.5;t.set_view(1,7);old=(t.view_start,t.view_span,t.mark_in,t.mark_out)
    w.set_monitor_mode(True)
    assert t.position==3.5 and (t.view_start,t.view_span,t.mark_in,t.mark_out)==old
    assert w.monitor_mode and 'AI music' in w.playback_label.text()
    w.seek(1);assert not w._monitor_pending or w._monitor_pending['position']==1
    assert 'outside AI sections' in w.playback_label.text()
    w.set_monitor_mode(False);assert t.position==1 and not w.monitor_mode
    assert w.p.cues()==rows;w.close();app.processEvents()

def test_actual_music_replacement_and_overlapping_ranges(tmp_path,monkeypatch):
    import json
    from scipy.io.wavfile import write
    p,rows=fixture_project(tmp_path);gain=[.2]
    def events(request,cancel):
        for job in json.loads(Path(request).read_text())['jobs']:
            write(job['output'],48000,decode(job['input'],sample_rate=48000)*gain[0])
            yield {'type':'done','id':job['id'],'seconds':.01}
    monkeypatch.setattr(monitor.ai,'_events',events)
    monitor.timeline_audio(p.path,{'range':[1,5]});gain[0]=.4
    preview=monitor.timeline_audio(p.path,{'range':[3,8]})['preview']
    original=decode(p.get('program')['path']);mixed=decode(preview['path'])
    assert preview['regions']==[[1,8]]
    for a,b,g in [(0,.8,1),(1.5,2.5,.2),(3.5,7.5,.4),(8.2,11,1)]:
        a,b=round(a*SR),round(b*SR)
        assert np.max(abs(mixed[a:b]-original[a:b]*g))<.002
    p.close()

def test_nonzero_range_multiple_chunks_remains_aligned(tmp_path,monkeypatch):
    from scipy.io.wavfile import write
    source=tmp_path/'long.wav';data=np.sin(np.arange(130*SR)*.014).astype(np.float32)*.2;write(source,SR,data)
    jobs=identity_engine(monkeypatch)
    out=monitor.ai.separate_program(source,110*SR,start_seconds=10,total_samples=len(data))
    assert len(jobs)==2 and len(out)==110*SR
    for sec in [1,59,60,61,109]:
        a=sec*SR;assert np.max(abs(out[a:a+100]-data[10*SR+a:10*SR+a+100]))<.002

def test_range_escape_restores_marks_selection_and_pending_controls(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);t=w.timeline
    t.mark_in=1;t.mark_out=3;t.selected={rows[0]['id']};t.current_id=rows[0]['id'];t.selectionChanged.emit(list(t.selected))
    drag_box(t,QPoint(round(t.x_at(4)),t.height()-25),QPoint(round(t.x_at(8)),t.height()-25),Qt.AltModifier,release=False)
    QTest.keyClick(t,Qt.Key_Escape)
    assert (t.mark_in,t.mark_out)==(1,3) and t.selected=={rows[0]['id']}
    w._monitor_pending={'position':2,'playing':True,'reverse':False,'rate':1,'path':t.path}
    w.preview_cue();assert not w._monitor_pending['playing']
    w.shuttle(-1);assert w._monitor_pending['reverse'] and not w._monitor_pending['playing']
    w.shuttle(0);assert not w._monitor_pending['reverse']
    w.seek(4);assert w._monitor_pending is None or w._monitor_pending['position']==4
    assert t.position==4
    w.close_project();assert w._monitor_pending is None and not w.monitor_mode
    w.close();app.processEvents()
