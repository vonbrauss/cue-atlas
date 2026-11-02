import pytest
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtMultimedia import QMediaPlayer
from cueatlas.timeline import Timeline
from test_timeline import open_window
from test_editor_controls import fake_player


def test_trackpad_pan_stays_away_from_playhead(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);t=w.timeline
    state,calls=fake_player(w,monkeypatch)
    state['value']=QMediaPlayer.PlayingState
    t.set_view(0,4);t.position=1
    point=QPointF(100,100)
    for delta in (QPoint(-120,0),QPoint(0,-120)):
        event=QWheelEvent(point,point,delta,QPoint(),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False)
        before=t.view_start
        QApplication.sendEvent(t,event)
        assert t.view_start>before and t.view_span==4
        start=t.view_start
        w.position_changed(1000)
        assert t.view_start==start
    w.seek(10)
    assert not t.follow_suspended
    w.position_changed(10000)
    assert t.view_start>start
    w.close();app.processEvents()


@pytest.mark.parametrize('playing',[False,True])
def test_complete_trackpad_gesture_keeps_pan_after_release(tmp_path,monkeypatch,playing):
    app,w,rows=open_window(tmp_path);t=w.timeline
    state,calls=fake_player(w,monkeypatch)
    state['value']=QMediaPlayer.PlayingState if playing else QMediaPlayer.PausedState
    t.set_view(0,2);t.position=1
    point=QPointF(100,100)
    for phase,delta in [(Qt.ScrollBegin,QPoint()),
                        (Qt.ScrollUpdate,QPoint(1,-400)),
                        (Qt.ScrollMomentum,QPoint(0,-400)),
                        (Qt.ScrollEnd,QPoint())]:
        before=t.view_start
        event=QWheelEvent(point,point,delta,QPoint(),Qt.NoButton,Qt.NoModifier,phase,False)
        QApplication.sendEvent(t,event)
        assert t.view_span==2
        if delta.isNull():assert t.view_start==before
        else:assert t.view_start>before
    assert t.view_start>t.position
    start=t.view_start;w.position_changed(1000)
    assert t.view_start==start
    w.close();app.processEvents()


def test_arrows_seek_strict_next_previous_edit_across_gaps(tmp_path):
    app,w,rows=open_window(tmp_path);t=w.timeline
    t.cues=[rows[0],rows[1]|{'start':3},rows[2]]
    t.set_view(0,2);w.seek(2)
    QTest.keyClick(t,Qt.Key_Down)
    assert t.position==3
    QTest.keyClick(t,Qt.Key_Down)
    assert t.position==6
    QTest.keyClick(t,Qt.Key_Up)
    assert t.position==3
    w.seek(0);QTest.keyClick(t,Qt.Key_Up);assert t.position==0
    w.seek(12);QTest.keyClick(t,Qt.Key_Down);assert t.position==12
    w.close();app.processEvents()


@pytest.mark.parametrize('target',['timeline','cue_table'])
def test_native_arrow_modifier_and_media_clock_rounding(tmp_path,target):
    app,w,rows=open_window(tmp_path);t=w.timeline;widget=getattr(w,target)
    t.cues=[rows[0]|{'end':2.123456},rows[1]|{'start':2.123456,'end':6.654321},
            rows[2]|{'start':6.654321}]
    w.activateWindow();widget.setFocus();app.processEvents()
    w.seek(1)
    QTest.keyClick(app.focusWidget(),Qt.Key_Down,Qt.KeypadModifier)
    assert t.position==pytest.approx(2.123456,abs=.001)
    # The media player reports integer milliseconds after seeking.
    w.position_changed(2123)
    QTest.keyClick(app.focusWidget(),Qt.Key_Down,Qt.KeypadModifier)
    assert t.position==pytest.approx(6.654321,abs=.001)
    w.position_changed(6655)
    QTest.keyClick(app.focusWidget(),Qt.Key_Up,Qt.KeypadModifier)
    assert t.position==pytest.approx(2.123456,abs=.001)
    w.close();app.processEvents()


def test_q_w_trim_only_target_and_support_undo(tmp_path):
    app,w,rows=open_window(tmp_path);t=w.timeline
    w.seek(3);QTest.keyClick(t,Qt.Key_Q)
    after=w.p.cues()
    assert [(c['start'],c['end']) for c in after]==[(0,2),(3,6),(6,12)]
    w.seek(5);QTest.keyClick(t,Qt.Key_W)
    assert [(c['start'],c['end']) for c in w.p.cues()]==[(0,2),(3,5),(6,12)]
    w.undo_cue_edit();assert w.p.cues()==after
    w.undo_cue_edit();assert w.p.cues()==rows
    w.seek(2);QTest.keyClick(t,Qt.Key_Q);assert w.p.cues()==rows
    t.editable=False;w.seek(3);QTest.keyClick(t,Qt.Key_Q);assert w.p.cues()==rows
    w.close();app.processEvents()


def test_page_follow_forward_reverse_jumps_and_source_limits():
    app=QApplication.instance() or QApplication([]);t=Timeline();t.set_source(None,100)
    t.set_view(20,10);t.position=29;t.follow_playhead();assert t.view_start==20
    t.position=29.3;t.follow_playhead();assert t.view_start==pytest.approx(28.1)
    start=t.view_start;t.position=29.4;t.follow_playhead();assert t.view_start==start
    assert t.view_span==10
    t.set_view(40,10);t.position=40.7;t.follow_playhead(-1)
    assert t.view_start==pytest.approx(31.9) and t.view_span==10
    # Loop seeks and jumps can land outside either side of the current page.
    t.set_view(70,10);t.position=10;t.follow_playhead();assert t.view_start==pytest.approx(8.8)
    t.position=80;t.follow_playhead(-1);assert t.view_start==pytest.approx(71.2)
    t.set_view(90,10);events=[];t.viewChanged.connect(lambda *args:events.append(args))
    t.position=99.5;t.follow_playhead();assert t.view_start==90 and not events
    t.set_view(0,10);events.clear();t.position=.5;t.follow_playhead(-1)
    assert t.view_start==0 and not events
    t.set_view(0,100);t.position=99;t.follow_playhead();assert t.view_span==100 and t.view_start==0
    t.shutdown()


def test_follow_disable_and_drag_guard():
    app=QApplication.instance() or QApplication([]);t=Timeline();t.set_source(None,100);t.set_view(0,10)
    t.position=30;t.follow_enabled=False;t.follow_playhead();assert t.view_start==0
    t.follow_enabled=True;t.drag={};t.follow_playhead()  # Empty dict is not a real drag.
    t.set_view(0,10);t.drag={'pending':True};t.follow_playhead();assert t.view_start==0
    t.drag=None;t.follow_playhead();assert t.view_start==pytest.approx(28.8)
    t.shutdown()


def test_wheel_and_buttons_zoom_to_playhead_not_hover(tmp_path):
    app,w,rows=open_window(tmp_path);t=w.timeline
    t.set_view(0,12);t.position=6
    point=QPointF(t.x_at(1),t.height()-20)
    event=QWheelEvent(point,QPointF(t.mapToGlobal(point.toPoint())),QPoint(),QPoint(0,120),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False)
    QApplication.sendEvent(t,event)
    assert t.view_start+t.view_span/2==pytest.approx(6)
    t.position=0;t.zoom(2);assert t.view_start==0
    t.position=12;t.zoom(2);assert t.view_start+t.view_span==12
    w.close();app.processEvents()


def test_follow_runs_only_during_playback_and_toggle_is_saved(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);t=w.timeline;state,calls=fake_player(w,monkeypatch)
    t.follow_enabled=True;t.set_view(0,4)
    w.position_changed(3800);assert t.view_start==0  # Paused seek stays put.
    state['value']=QMediaPlayer.PlayingState;w.position_changed(3800)
    assert t.view_start==pytest.approx(3.32) and t.view_span==4
    page=t.view_start;w.position_changed(3900);assert t.view_start==page
    state['value']=QMediaPlayer.PausedState;w.position_changed(9000);assert t.view_start==page
    w.reverse.active=True;w.position_changed(200,reverse=True)
    assert t.view_start==0 and t.view_span==4
    w.reverse.stop()
    stored=[];monkeypatch.setattr(w.prefs,'setValue',lambda key,value:stored.append((key,value)))
    w.follow_action.setChecked(True);w.follow_action.setChecked(False)
    assert not t.follow_enabled and stored[-1]==('follow_playhead',False)
    state['value']=QMediaPlayer.PlayingState;w.position_changed(9000);assert t.view_start==0
    w.follow_action.setChecked(True)
    assert t.follow_enabled and stored[-1]==('follow_playhead',True)
    w.close();app.processEvents()
