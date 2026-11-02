import shutil
import pytest
import numpy as np
from scipy.io.wavfile import write
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaPlayer
from cueatlas.project import Project,cue
from cueatlas.audio import SR,Cancelled
from cueatlas.engine import import_files,identify_cue,analyze
from cueatlas.gui import CueDialog,SettingsDialog
from test_core import music
from test_timeline import open_window


def retry_project(tmp_path):
    p=Project(tmp_path/'retry.cueatlas',True,'Retry')
    source=tmp_path/'reference.wav';reference=music(112,12);write(source,SR,reference)
    import_files(p.path,[str(source)]);track=p.tracks()[0]
    program=tmp_path/'program.wav';write(program,SR,np.concatenate([np.zeros(SR*2),reference[3*SR:9*SR],np.zeros(SR)]))
    p.set('program',{'path':str(program),'duration':9})
    rows=[cue(None,0,2,title='Other'),cue(None,2,8,title='Drawn interval')];p.save_cues(rows)
    return p,track,rows


def test_retry_offline_library_preserves_every_cue_and_history(tmp_path):
    p,track,rows=retry_project(tmp_path);state=p._edit_state();history=p.edit_history()
    # Matching uses stored landmarks; reference playback remains optional.
    original=tmp_path/'reference.wav';original.rename(tmp_path/'moved.wav')
    result=identify_cue(p.path,rows[1]['id'])
    assert result['cue_retry'] and result['candidates'][0]['track']==track['id']
    assert result['candidates'][0]['reference_start']==pytest.approx(3,abs=.15)
    assert p._edit_state()==state and p.edit_history()==history
    with pytest.raises(Cancelled):identify_cue(p.path,rows[1]['id'],cancel=lambda:True)
    assert p._edit_state()==state and p.edit_history()==history
    assert not identify_cue(p.path,rows[0]['id'])['candidates']
    with pytest.raises(ValueError):identify_cue(p.path,'missing')
    p.close()


def test_reconnect_verifies_content_preserves_fingerprints_and_metadata(tmp_path):
    p,track,rows=retry_project(tmp_path);before=p.tracks()[0];history=p.edit_history()
    hashes=list(p.db.execute('SELECT * FROM hashes'));new=tmp_path/'reconnected.wav';shutil.copy2(track['path'],new)
    p.relink_reference(track['id'],new)
    after=p.tracks()[0];assert after['path']==str(new)
    assert after['metadata']==before['metadata'] and p.cues()==rows and p.edit_history()==history
    assert [tuple(r) for r in p.db.execute('SELECT * FROM hashes')]==[tuple(r) for r in hashes]
    bad=tmp_path/'bad.wav';bad.write_bytes(new.read_bytes()[:-1]+b'!')
    with pytest.raises(ValueError,match='differs'):p.relink_reference(track['id'],bad)
    p.close()


def test_comparison_level_overrides_availability_and_cancellation(tmp_path):
    app,w,rows=open_window(tmp_path);c=rows[1]
    d=CueDialog(c,w.p.tracks(),12,w);comparison=d.comparison
    assert comparison.reference_button.isEnabled()
    assert comparison.gain.value()==-12
    assert comparison.reference_output.volume()==pytest.approx(.75*10**(-12/20),abs=1e-6)
    comparison.gain.setValue(-20);assert not comparison.use_default.isChecked()
    assert comparison.reference_output.volume()==pytest.approx(.075,abs=1e-6)
    d.reject();assert not w.p.get('reference_gains')
    comparison.save()  # Main review invokes this only after Save was accepted.
    assert w.p.get('reference_gains')[c['track']]==-20
    d=CueDialog(c,w.p.tracks(),12,w);assert d.comparison.gain.value()==-20
    d.comparison.use_default.setChecked(True);d.comparison.save()
    assert c['track'] not in w.p.get('reference_gains')
    assert d.comparison.gain.value()==-12
    d.reject()
    # Missing or changed references disable comparison without disabling review.
    tracks=w.p.tracks();tracks[0]['path']=str(tmp_path/'offline.wav')
    d=CueDialog(c,tracks,12,w)
    assert not d.comparison.reference_button.isEnabled() and not d.comparison.relink_button.isHidden()
    d.accept();assert d.c==c
    settings=SettingsDialog(w.p,w);settings.values['reference_gain_db'].setValue(-18);settings.accept()
    assert settings.settings['reference_gain_db']==-18
    w.close();app.processEvents()


def test_comparison_switches_sources_and_stops_at_bounds(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);d=CueDialog(rows[1],w.p.tracks(),12,w);comparison=d.comparison
    states={};calls=[]
    for name,player in [('program',comparison.program_player),('reference',comparison.reference_player)]:
        states[name]=QMediaPlayer.StoppedState
        monkeypatch.setattr(player,'playbackState',lambda key=name:states[key])
        monkeypatch.setattr(player,'pause',lambda key=name:states.update({key:QMediaPlayer.PausedState}))
        monkeypatch.setattr(player,'play',lambda key=name:states.update({key:QMediaPlayer.PlayingState}))
        monkeypatch.setattr(player,'setPosition',lambda ms,key=name:calls.append((key,ms)))
    def wait_ready():
        import time
        from PySide6.QtTest import QTest
        deadline=time.monotonic()+5
        while comparison.loading and time.monotonic()<deadline:QTest.qWait(10)
        assert comparison.loading is None
    comparison.play_program();wait_ready();assert calls[-1]==('program',0)
    comparison.offset.setValue(4);comparison.play_reference();wait_ready()
    assert states['program']==QMediaPlayer.PausedState and calls[-1]==('reference',0)
    comparison.reference_position(8000);assert states['reference']==QMediaPlayer.PausedState
    comparison.play_program();wait_ready();comparison.program_position(4000);assert states['program']==QMediaPlayer.PausedState
    d.reject();w.close();app.processEvents()


def test_analysis_records_reference_alignment(tmp_path):
    p,track,rows=retry_project(tmp_path);analyze(p.path)
    known=next(c for c in p.cues() if c['track']==track['id'])
    alignment=p.get('cue_matches')[known['id']]
    assert alignment['track']==track['id']
    assert alignment['reference_start']-alignment['program_start']==pytest.approx(1,abs=.15)
    p.close()


def test_background_retry_review_acceptance_and_undo(tmp_path,monkeypatch):
    import time
    from PySide6.QtWidgets import QDialog
    from cueatlas.gui import Window,STYLE
    app=QApplication.instance() or QApplication([]);app.setStyleSheet(STYLE)
    p,track,rows=retry_project(tmp_path);path=p.path;p.close()
    w=Window();w.load(str(path));w.show();app.processEvents();w.cue_table.selectRow(1)
    before=w.p._edit_state();history=w.p.edit_history()
    def cancelled(dialog):return QDialog.Rejected
    monkeypatch.setattr(QDialog,'exec',cancelled)
    def wait_done():
        deadline=time.monotonic()+8
        while w.worker is not None and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        assert w.worker is None
    w.retry_selected_cue();wait_done()
    assert w.p._edit_state()==before and w.p.edit_history()==history
    def accepted(dialog):
        if isinstance(dialog,CueDialog):
            assert dialog.title.text()==track['metadata']['title']
            assert dialog.comparison.offset.value()==pytest.approx(3,abs=.15)
            dialog.status.setCurrentText('Reviewed');dialog.comparison.gain.setValue(-18)
            dialog.grab().save('/private/tmp/cueatlas-reference-review.png')
        dialog.accept();return QDialog.Accepted
    monkeypatch.setattr(QDialog,'exec',accepted)
    w.cue_table.selectRow(1);w.retry_selected_cue();wait_done()
    saved=w.p.cues();assert saved[0]==rows[0]
    assert saved[1]['id']==rows[1]['id'] and saved[1]['start']==2 and saved[1]['end']==8
    assert saved[1]['track']==track['id'] and saved[1]['status']=='Reviewed'
    assert saved[1]['title']==track['metadata']['title']
    assert w.p.get('reference_gains')[track['id']]==-18
    assert w.p.get('cue_matches')[rows[1]['id']]['reference_start']==pytest.approx(3,abs=.15)
    w.p.undo_edit();assert w.p.cues()==rows
    w.p.redo_edit();assert w.p.cues()==saved
    w.close();app.processEvents()
