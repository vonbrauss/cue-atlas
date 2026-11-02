import json
from pathlib import Path
import numpy as np
import pytest
from scipy.io.wavfile import write
from cueatlas.audio import SR,decode,Cancelled,waveform
from cueatlas import separation as ai
from cueatlas.engine import analyze
from test_timeline import fixture_project,open_window
from test_retry_comparison import retry_project


@pytest.fixture(autouse=True)
def isolated_ai(tmp_path,monkeypatch):
    monkeypatch.setenv('CUEATLAS_AI_HOME',str(tmp_path/'ai'));monkeypatch.setattr(ai,'installed',lambda:True)


def identity_engine(monkeypatch):
    jobs=[]
    def events(request,cancel):
        for job in json.loads(Path(request).read_text())['jobs']:
            jobs.append(job);data=decode(job['input'],sample_rate=48000)
            write(job['output'],48000,data)
            yield {'type':'done','id':job['id'],'seconds':.01}
    monkeypatch.setattr(ai,'_events',events)
    return jobs


def test_full_program_stitching_cache_and_final_fractional_block(tmp_path,monkeypatch):
    samples=SR*125+103;data=np.sin(np.arange(samples)*.017).astype(np.float32)*.2
    source=tmp_path/'program.wav';write(source,SR,data);jobs=identity_engine(monkeypatch)
    output=ai.separate_program(source,samples)
    assert len(output)==samples and len(jobs)==3
    # Resampling changes high-frequency edges slightly; no missing/duplicated time at joins.
    for center in [10*SR,60*SR,120*SR,samples-200]:
        assert np.max(np.abs(data[center-50:center+50]-output[center-50:center+50]))<.002
    monkeypatch.setattr(ai,'_events',lambda *a:pytest.fail('Must reuse cached separation'))
    assert np.array_equal(ai.separate_program(source,samples),output)
    assert not list(ai.home().glob('program-*'))


def test_ai_analysis_matches_separated_audio_but_preserves_original_monitor(tmp_path,monkeypatch):
    p,track,old=retry_project(tmp_path);source=Path(p.get('program')['path']);original=decode(source)
    # The AI estimate is louder, while the monitor must retain the quieter source.
    write(source,SR,original*.001)
    separated=original.copy();calls=[]
    def separate(path,samples,progress,cancel):
        calls.append(path);assert samples==len(original);progress(1,'Separated');return separated
    monkeypatch.setattr(ai,'separate_program',separate)
    p.set('settings',p.settings|{'silence_db':-100})
    result=ai.analyze_program(p.path)
    assert result['ai_analysis'] and calls==[str(source)]
    assert any(c['track']==track['id'] for c in p.cues())
    program=p.get('program');assert program['path']==str(source)
    assert program['waveform']==waveform(decode(source)) and p.get('analysis_mode')=='ai_separation'
    assert p.track(track['id'])['metadata']==track['metadata'];p.close()


@pytest.mark.parametrize('failure',['cancel','helper','short','source_changed'])
def test_ai_failure_never_replaces_cues_or_exclusions(tmp_path,monkeypatch,failure):
    p,rows=fixture_project(tmp_path);p.set_cues_excluded([rows[0]['id']]);before=p._edit_state();history=p.edit_history();program=p.get('program')
    def separate(path,samples,**kwargs):
        if failure=='cancel':raise Cancelled()
        if failure=='helper':raise ValueError('Helper failed')
        if failure=='source_changed':Path(path).write_bytes(b'changed');return np.zeros(samples,dtype=np.float32)
        return np.zeros(samples-100,dtype=np.float32)
    monkeypatch.setattr(ai,'separate_program',separate)
    with pytest.raises((ValueError,Cancelled)):ai.analyze_program(p.path)
    assert p._edit_state()==before and p.edit_history()==history and p.get('program')==program;p.close()


def test_standard_analysis_does_not_require_or_run_ai(tmp_path,monkeypatch):
    p,track,rows=retry_project(tmp_path)
    monkeypatch.setattr(ai,'separate_program',lambda *a,**k:pytest.fail('Standard analysis must not run AI'))
    result=analyze(p.path);assert not result['ai_analysis'] and p.get('analysis_mode')=='standard';p.close()


@pytest.mark.parametrize('mode',['standard','ai_separation',None])
def test_analyze_mode_selection_dispatches_correct_worker(tmp_path,monkeypatch,mode):
    from PySide6.QtWidgets import QMessageBox,QDialog
    from cueatlas.ai_ui import AnalysisModeDialog
    from cueatlas.engine import analyze
    app,w,rows=open_window(tmp_path);calls=[]
    def choose(dialog):
        assert isinstance(dialog,AnalysisModeDialog)
        if mode is None:return QDialog.Rejected
        dialog.choose(mode);return QDialog.Accepted
    monkeypatch.setattr(AnalysisModeDialog,'exec',choose)
    monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.Yes)
    monkeypatch.setattr(w,'start_worker',lambda fn,*a:calls.append(fn))
    w.run_analysis();assert calls==([] if mode is None else [ai.analyze_program if mode=='ai_separation' else analyze])
    assert w.p.cues()==rows;w.close();app.processEvents()


def test_helper_must_finish_all_program_sections(tmp_path,monkeypatch):
    source=tmp_path/'program.wav';write(source,SR,np.ones(SR,dtype=np.float32)*.1)
    monkeypatch.setattr(ai,'_events',lambda *args:iter([]))
    with pytest.raises(ValueError,match='before the full program'):ai.separate_program(source,SR)
    assert not list(ai.home().glob('program-*'))



def test_ai_cannot_create_music_cues_over_source_silence(tmp_path,monkeypatch):
    p,track,rows=retry_project(tmp_path);source=Path(p.get('program')['path']);estimate=decode(source)
    write(source,SR,np.zeros_like(estimate))
    monkeypatch.setattr(ai,'separate_program',lambda *a,**k:estimate)
    result=ai.analyze_program(p.path)
    assert result['matched']==0 and p.cues()==[]
    assert all(value==0 for value in p.get('program')['waveform']);p.close()
