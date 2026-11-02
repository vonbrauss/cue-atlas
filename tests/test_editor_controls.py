import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtMultimedia import QMediaPlayer
from test_timeline import open_window,center


def fake_player(w,monkeypatch):
    state={'value':QMediaPlayer.StoppedState};calls=[]
    def play():state['value']=QMediaPlayer.PlayingState;calls.append(('play',))
    def pause():state['value']=QMediaPlayer.PausedState;calls.append(('pause',))
    monkeypatch.setattr(w.player,'playbackState',lambda:state['value'])
    monkeypatch.setattr(w.player,'play',play);monkeypatch.setattr(w.player,'pause',pause)
    monkeypatch.setattr(w.player,'setPosition',lambda ms:calls.append(('seek',ms)))
    return state,calls


def test_play_button_and_space_share_mode_and_label(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);t=w.timeline;state,calls=fake_player(w,monkeypatch)
    QTest.mouseClick(t,Qt.LeftButton,Qt.NoModifier,center(t,rows[1]['id']))
    w.play_button.click();assert ('seek',2000) in calls and w.stop_at==6
    assert 'Playing · Preview: Neon evenings'==w.playback_label.text()
    QTest.keyClick(t,Qt.Key_Space);assert state['value']==QMediaPlayer.PausedState and 'Paused' in w.playback_label.text()
    QTest.mouseClick(t,Qt.LeftButton,Qt.NoModifier,QPoint(round(t.x_at(1)),t.height()-20))
    assert not w.selected_cues() and 'Free playback' in w.playback_label.text()
    before=len(calls);w.play_button.click()
    assert calls[before:]==[('play',)] and w.stop_at is None
    assert w.playback_label.text()=='Playing · Free playback'
    w.close();app.processEvents()


def test_audition_in_out_loop_pause_and_source_edges(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);t=w.timeline;state,calls=fake_player(w,monkeypatch)
    QTest.mouseClick(t,Qt.LeftButton,Qt.NoModifier,center(t,rows[1]['id']))
    w.audition_button.click()
    assert calls[-2:]==[('seek',0),('play',)] and w.stop_at==4
    assert 'Audition In: Neon evenings' in w.playback_label.text()
    w.position_changed(4000);assert calls[-1]==('pause',) and w.stop_at is None
    w.audition_transition('end');assert calls[-2:]==[('seek',4000),('play',)] and w.stop_at==8
    w.loop_button.click();assert w.loop_start==4 and w.stop_at==8
    assert 'Loop Out' in w.playback_label.text()
    w.position_changed(8000);assert calls[-2:]==[('seek',4000),('play',)] and w.stop_at==8
    w.media_status_changed(QMediaPlayer.EndOfMedia);assert calls[-2:]==[('seek',4000),('play',)]
    QTest.keyClick(t,Qt.Key_Space);before=len(calls)
    w.media_status_changed(QMediaPlayer.EndOfMedia);assert len(calls)==before
    assert state['value']==QMediaPlayer.PausedState
    QTest.keyClick(t,Qt.Key_Space);assert calls[-2:]==[('seek',4000),('play',)]
    w.loop_button.click();assert w.loop_start is None and w.stop_at is None
    # Source edges clamp the listening window.
    w.cue_table.selectRow(0);w.audition_transition('start');assert w.audition_context['start']==0
    w.cue_table.selectRow(2);w.audition_transition('end');assert w.audition_context['end']==12
    w.seek(1);assert w.audition_context is None and w.loop_start is None
    w.close();app.processEvents()


def test_standard_history_shortcuts_and_frame_nudge(tmp_path):
    app,w,rows=open_window(tmp_path);t=w.timeline
    w.activateWindow();t.setFocus();app.processEvents()
    w.cue_table.selectRow(1);t.setFocus()
    w.nudge_boundary(1);after=w.p.cues();assert after!=rows
    assert w.undo_action.text()=='Undo Trim cue'
    QTest.keyClick(t,Qt.Key_Z,Qt.ControlModifier);assert w.p.cues()==rows
    QTest.keyClick(t,Qt.Key_Z,Qt.ControlModifier|Qt.ShiftModifier);assert w.p.cues()==after
    # Text input retains native undo and must not alter cue history.
    history=w.p.edit_history();w.search.setFocus();QTest.keyClicks(w.search,'abc')
    QTest.keyClick(w.search,Qt.Key_Z,Qt.ControlModifier)
    assert w.search.text()=='' and w.p.edit_history()==history
    w.close();app.processEvents()


def test_drag_offset_threshold_and_neighbor_preview(tmp_path):
    app,w,rows=open_window(tmp_path);t=w.timeline
    QTest.mouseClick(t,Qt.LeftButton,Qt.NoModifier,center(t,rows[1]['id']))
    rect=next(r for c,r in t.regions() if c['id']==rows[1]['id'])
    grab=QPoint(round(rect.left())+7,round(rect.center().y()))
    history=w.p.edit_history()
    QTest.mousePress(t,Qt.LeftButton,Qt.NoModifier,grab)
    QTest.mouseMove(t,grab+QPoint(1,0));QTest.mouseRelease(t,Qt.LeftButton,Qt.NoModifier,grab+QPoint(1,0))
    assert w.p.cues()==rows and w.p.edit_history()==history
    QTest.mousePress(t,Qt.LeftButton,Qt.NoModifier,grab)
    dest=QPoint(round(t.x_at(1))+7,grab.y());QTest.mouseMove(t,dest)
    preview={c['id']:c for c in t.cues}
    assert preview[rows[1]['id']]['start']==pytest.approx(1,abs=.04)
    assert preview[rows[0]['id']]['end']==rows[0]['end']
    assert w.p.cues()==rows
    QTest.keyClick(t,Qt.Key_Escape);QTest.mouseRelease(t,Qt.LeftButton,Qt.NoModifier,dest)
    assert w.p.cues()==rows
    w.close();app.processEvents()


def test_roll_frame_nudge_and_undo_during_drag(tmp_path):
    from cueatlas.timecode import RATES
    app,w,rows=open_window(tmp_path);t=w.timeline
    w.activateWindow();app.processEvents();w.cue_table.selectRow(1)
    rect=next(r for c,r in t.regions() if c['id']==rows[1]['id'])
    QTest.mouseClick(t,Qt.LeftButton,Qt.NoModifier,QPoint(round(t.x_at(6)),round(rect.center().y())))
    assert w.audition_button.text()=='Audition edit'
    w.nudge_boundary(1)
    after={c['id']:c for c in w.p.cues()};fps=RATES[w.p.settings['rate']][0]
    assert after[rows[1]['id']]['end']==pytest.approx(6+1/fps)
    assert after[rows[2]['id']]['start']==after[rows[1]['id']]['end']
    history=w.p.edit_history();rect=next(r for c,r in t.regions() if c['id']==rows[1]['id'])
    point=QPoint(round(t.x_at(after[rows[1]['id']]['end'])),round(rect.center().y()))
    QTest.mousePress(t,Qt.LeftButton,Qt.NoModifier,point);QTest.mouseMove(t,point+QPoint(50,0))
    QTest.keyClick(t,Qt.Key_Z,Qt.ControlModifier)
    QTest.mouseRelease(t,Qt.LeftButton,Qt.NoModifier,point+QPoint(50,0))
    assert t.drag is None and w.p.edit_history()==history
    assert {c['id']:c for c in w.p.cues()}==after
    w.close();app.processEvents()


def test_undo_cancels_first_pending_drag_without_committed_history(tmp_path):
    app,w,rows=open_window(tmp_path);t=w.timeline
    w.p.set('edit_history',{'undo':[],'redo':[]});w.refresh();w.activateWindow();t.setFocus();app.processEvents()
    assert not w.undo_action.isEnabled()
    QTest.mouseClick(t,Qt.LeftButton,Qt.NoModifier,center(t,rows[1]['id']))
    rect=next(r for c,r in t.regions() if c['id']==rows[1]['id'])
    point=QPoint(round(rect.left()),round(rect.center().y()))
    QTest.mousePress(t,Qt.LeftButton,Qt.NoModifier,point);QTest.mouseMove(t,point-QPoint(50,0))
    QTest.keyClick(t,Qt.Key_Z,Qt.ControlModifier)
    assert t.drag is None and w.p.cues()==rows
    QTest.mouseRelease(t,Qt.LeftButton,Qt.NoModifier,point-QPoint(50,0))
    assert not w.p.edit_history()['undo']
    w.close();app.processEvents()
