import json
from pathlib import Path
import numpy as np
import pytest
from cueatlas import separation as ai
from cueatlas.project import cue
from cueatlas.audio import Cancelled,SR
from scipy.io.wavfile import write
from test_timeline import fixture_project,open_window


@pytest.fixture(autouse=True)
def isolated_ai(tmp_path,monkeypatch):monkeypatch.setenv('CUEATLAS_AI_HOME',str(tmp_path/'ai'))


def proposal(p,row):
    t=next(t for t in p.tracks() if t['metadata']['title']=='Neon evenings')
    return {'track':t['id'],'title':t['metadata']['title'],'support':12,'votes':50,'reference_start':3,'program_start':row['start']}


def result_for(p,rows):
    return {'ai_batch':True,'project':str(p.path),'settings':p.settings,'program':p.get('program'),'library':ai.library_signature(p),
            'items':[{'cue':r,'original':[],'separated':[proposal(p,r)],'error':None} for r in rows]}


def test_apply_merges_known_and_new_neighbors_preserves_license_single_undo(tmp_path):
    p,rows=fixture_project(tmp_path);result=result_for(p,[rows[0],rows[2]]);before=p._edit_state();history=len(p.edit_history()['undo'])
    choices={r['id']:proposal(p,r) for r in (rows[0],rows[2])}
    assert ai.apply_matches(p,result,choices)==2
    assert len(p.cues())==1
    merged=p.cues()[0];assert (merged['start'],merged['end'],merged['track'],merged['status'])==(0,12,rows[1]['track'],'Needs review')
    assert p.track(merged['track'])['metadata']['license']=='Keep license'
    assert len(p.edit_history()['undo'])==history+1
    after=p._edit_state();p.undo_edit();assert p._edit_state()==before
    p.redo_edit();assert p._edit_state()==after;p.close()


@pytest.mark.parametrize('barrier',['gap','excluded','different'])
def test_apply_respects_gaps_exclusions_and_different_references(tmp_path,barrier):
    p,rows=fixture_project(tmp_path)
    (tmp_path/'other.wav').write_bytes(b'reference')
    if barrier=='gap':rows[1]['start']=2.1;p.save_cues(rows)
    elif barrier=='excluded':p.set_cues_excluded([rows[1]['id']])
    else:
        tid=p.save_track(tmp_path/'other.wav',12,{'title':'Other'},[])
        rows[1]['track']=tid;p.save_cues(rows)
    result=result_for(p,[rows[0]])
    assert ai.apply_matches(p,result,{rows[0]['id']:proposal(p,rows[0])})==0
    assert len(p.cues())==3
    assert p.cues()[1]==rows[1];p.close()


@pytest.mark.parametrize('change',['cue','settings','library','removed','excluded','source'])
def test_stale_results_are_rejected_atomically(tmp_path,change):
    p,rows=fixture_project(tmp_path);source=Path(p.get('program')['path']);st=source.stat()
    (tmp_path/'other.wav').write_bytes(b'reference')
    p.set('program',p.get('program')|{'size':st.st_size,'mtime':st.st_mtime_ns})
    result=result_for(p,[rows[0]])
    if change=='cue':p.trim_cue(rows[0]['id'],0,1)
    elif change=='settings':p.set('settings',p.settings|{'min_votes':50})
    elif change=='library':p.save_track(tmp_path/'other.wav',12,{'title':'Other'},[])
    elif change=='removed':p.save_cues(rows[1:])
    elif change=='excluded':p.set_cues_excluded([rows[0]['id']])
    else:source.write_bytes(b'changed')
    before=p._edit_state();history=p.edit_history()
    with pytest.raises(ValueError):ai.apply_matches(p,result,{rows[0]['id']:proposal(p,rows[0])})
    assert p._edit_state()==before and p.edit_history()==history;p.close()


def fake_backend(monkeypatch,p):
    calls=[]
    monkeypatch.setattr(ai,'installed',lambda:True)
    def identify(path,cid,**kwargs):
        calls.append((cid,kwargs.get('audio_override') is not None));row=next(c for c in p.cues() if c['id']==cid)
        return {'candidates':[proposal(p,row)] if kwargs.get('audio_override') is not None else []}
    monkeypatch.setattr(ai,'identify_cue',identify)
    def events(manifest,cancel):
        for job in json.loads(Path(manifest).read_text())['jobs']:
            row=next(c for c in p.cues() if c['id']==job['id']);write(job['output'],SR,np.zeros(round((row['end']-row['start'])*SR),dtype=np.float32))
            yield {'type':'done','id':job['id'],'seconds':.1}
    monkeypatch.setattr(ai,'_events',events)
    return calls


def test_batch_unknown_only_caches_audio_and_never_changes_cues(tmp_path,monkeypatch):
    p,rows=fixture_project(tmp_path);p.set_cues_excluded([rows[2]['id']]);before=p._edit_state();history=p.edit_history()
    calls=fake_backend(monkeypatch,p)
    result=ai.analyze_separated(p.path,{'ids':None})
    assert [e['cue']['id'] for e in result['items']]==[rows[0]['id']]
    assert calls==[(rows[0]['id'],False),(rows[0]['id'],True)]
    monkeypatch.setattr(ai,'_events',lambda *a:pytest.fail('cached audio must avoid inference'))
    again=ai.analyze_separated(p.path,{'ids':[rows[0]['id']]})
    assert again['items'][0]['cached'] and again['items'][0]['separated']==result['items'][0]['separated']
    assert p._edit_state()==before and p.edit_history()==history
    assert json.loads(ai.result_path(p.path).read_text())==again
    assert ai.cache_key('source',rows[0])!=ai.cache_key('changed',rows[0])
    assert ai.cache_key('source',rows[0])!=ai.cache_key('source',rows[0]|{'end':1})
    p.close()


def test_cancel_retains_completed_results_and_helper_failure_leaves_project_untouched(tmp_path,monkeypatch):
    p,rows=fixture_project(tmp_path);before=p._edit_state();fake_backend(monkeypatch,p);original=ai._events
    def partial(manifest,cancel):
        yield next(original(manifest,cancel));raise Cancelled()
    monkeypatch.setattr(ai,'_events',partial)
    result=ai.analyze_separated(p.path,{'ids':None})
    assert result['cancelled'] and result['items'][0]['separated'] and result['items'][1]['pending']
    ai.clear_cache()
    def failed(*args):raise ValueError('Helper failed');yield
    monkeypatch.setattr(ai,'_events',failed)
    result=ai.analyze_separated(p.path,{'ids':None})
    assert result['failure']=='Helper failed' and p._edit_state()==before;p.close()


def test_review_requires_explicit_apply_and_setup_does_not_download(tmp_path,monkeypatch):
    from cueatlas.ai_ui import AIResultsDialog,AISetupDialog
    app,w,rows=open_window(tmp_path);result=result_for(w.p,[rows[0]]);before=w.p._edit_state()
    monkeypatch.setattr(ai,'install_engine',lambda *a,**k:pytest.fail('No automatic installation'))
    setup=AISetupDialog(w);assert setup.worker is None;setup.reject()
    dialog=AIResultsDialog(w,result);dialog.apply();assert w.p._edit_state()==before
    dialog.select_all(True);dialog.apply();assert len(w.p.cues())==2
    w.p.undo_edit();assert w.p._edit_state()==before
    w.close();app.processEvents()


def test_installer_cancellation_cleans_staging_and_no_install_marker(tmp_path,monkeypatch):
    monkeypatch.setattr(ai.sys,'platform','darwin');monkeypatch.setattr(ai.platform,'machine',lambda:'arm64')
    def cancelled(url,target,*args,**kwargs):
        target.write_bytes(b'partial');raise Cancelled()
    monkeypatch.setattr(ai,'_download',cancelled)
    with pytest.raises(Cancelled):ai.install_engine()
    assert not ai.installed() and list(ai.home().iterdir())==[]


def test_clearing_cache_and_uninstall_keep_results_and_unrelated_files(tmp_path):
    root=ai.home();(root/'engine').mkdir(parents=True);(root/'cache').mkdir();(root/'results').mkdir()
    (root/'engine/model.ckpt').write_bytes(b'model');(root/'cache/music.wav').write_bytes(b'audio')
    saved=root/'results/batch.json';saved.write_text('{}');unrelated=root/'keep.txt';unrelated.write_text('keep')
    ai.uninstall_engine();assert not (root/'engine').exists() and (root/'cache/music.wav').exists()
    ai.clear_cache();assert not (root/'cache').exists() and saved.exists() and unrelated.read_text()=='keep'


def test_join_preserves_first_known_alignment_and_undo_restores_anchors(tmp_path):
    p,rows=fixture_project(tmp_path);saved={'track':rows[1]['track'],'reference_start':40,'program_start':2}
    p.set('cue_matches',{rows[1]['id']:saved});before=p.get('cue_matches')
    result=result_for(p,[rows[2]])
    assert ai.apply_matches(p,result,{rows[2]['id']:proposal(p,rows[2])})==1
    joined=p.cues()[1];assert p.get('cue_matches')[joined['id']]==saved
    after=p.get('cue_matches');p.undo_edit();assert p.get('cue_matches')==before
    p.redo_edit();assert p.get('cue_matches')==after;p.close()


def test_install_button_starts_worker_reports_progress_and_finishes(tmp_path,monkeypatch):
    import time,threading
    from PySide6.QtWidgets import QApplication,QWidget
    from cueatlas.ai_ui import AISetupDialog
    app=QApplication.instance() or QApplication([]);owner=QWidget();started=threading.Event();release=threading.Event();ready=[]
    monkeypatch.setattr(ai,'installed',lambda:bool(ready))
    def install(*args,progress,cancel):
        started.set();progress(.4,'Downloading model · 12 MB')
        assert release.wait(3)
        ready.append(True);return {'ai_install':True}
    monkeypatch.setattr(ai,'install_engine',install)
    dialog=AISetupDialog(owner);dialog.show();dialog.install.click()
    assert dialog.state.text()=='Starting installation…'
    assert not dialog.install.isEnabled() and dialog.close_button.text()=='Cancel'
    deadline=time.monotonic()+3
    try:
        while dialog.progress.value()!=40 and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        assert started.is_set() and dialog.state.text()=='Downloading model · 12 MB'
    finally:release.set()
    while dialog.worker is not None and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert dialog.worker is None
    assert dialog.state.text().startswith('Installed') and dialog.close_button.text()=='Done'
    assert dialog.progress.isHidden();dialog.reject();owner.close()


def test_settings_can_install_without_project(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication,QPushButton,QDialog
    from cueatlas.gui import Window,SettingsDialog
    from cueatlas.ai_ui import AISetupDialog
    app=QApplication.instance() or QApplication([]);w=Window();w.update_project_menu()
    assert w.p is None and w.project_settings_action.isEnabled()
    calls=[]
    def execute(dialog):
        if isinstance(dialog,SettingsDialog):
            assert dialog.settings is None
            next(b for b in dialog.findChildren(QPushButton) if b.text()=='AI music separation…').click()
        elif isinstance(dialog,AISetupDialog):calls.append('setup')
        return QDialog.Rejected
    monkeypatch.setattr(QDialog,'exec',execute)
    w.project_settings_action.trigger();assert calls==['setup'] and w.p is None
    assert not list(tmp_path.glob('*.cueatlas'));w.close();app.processEvents()


def test_installer_reports_download_bytes_percentage_and_busy_steps(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication,QWidget
    from cueatlas.ai_ui import AISetupDialog
    target=tmp_path/'download';target.write_bytes(b'x'*50);messages=[]
    def run(command,cancel,progress):progress('tick')
    monkeypatch.setattr(ai,'_run',run);monkeypatch.setattr(ai,'content_hash',lambda *a:'checksum')
    ai._download('https://example.invalid/model',target,'checksum',lambda:False,lambda n,s:messages.append((n,s)),'Downloading model',total=100)
    assert messages[0][0]==.5 and '50%' in messages[0][1] and ' / ' in messages[0][1]
    assert messages[-1]==(-1,'Verifying download…')
    app=QApplication.instance() or QApplication([]);owner=QWidget();dialog=AISetupDialog(owner)
    dialog.update_progress(-1,'Installing AI libraries…');assert dialog.progress.maximum()==0
    dialog.update_progress(.5,messages[0][1]);assert dialog.progress.maximum()==100 and dialog.progress.value()==50
    dialog.reject();owner.close()
