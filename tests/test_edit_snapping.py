import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from test_timeline import open_window


def isolated_window(tmp_path):
    app,w,rows=open_window(tmp_path);w.p.save_cues([rows[1]]);w.refresh();app.processEvents()
    w.timeline.snap_enabled=True
    return app,w,rows[1]


@pytest.mark.parametrize('edge,span',[('start',12),('end',4)])
def test_edge_magnet_exact_cursor_commit_and_undo(tmp_path,edge,span):
    app,w,c=isolated_window(tmp_path);t=w.timeline;t.set_view(0 if span==12 else 2,span)
    cursor=3.123 if edge=='start' else 5.123;t.position=cursor
    rect=next(r for item,r in t.regions() if item['id']==c['id'])
    grab_offset=5 if edge=='start' else -5
    grab=QPoint(round(t.x_at(c[edge]))+grab_offset,round(rect.center().y()))
    QTest.mousePress(t,Qt.LeftButton,Qt.NoModifier,grab)
    # Use the actual grab offset after pixel rounding, so the edge is 6 px away.
    destination=QPoint(round(t.x_at(cursor)+t.drag['offset']+6),grab.y())
    QTest.mouseMove(t,destination)
    assert t.drag['snapped_to_playhead'] and t.cues[0][edge]==cursor
    assert w.p.cues()==[c]
    QTest.mouseRelease(t,Qt.LeftButton,Qt.NoModifier,destination)
    assert w.p.cues()[0][edge]==cursor
    assert w.p.cues()[0]['end' if edge=='start' else 'start']==c['end' if edge=='start' else 'start']
    w.undo_cue_edit();assert w.p.cues()==[c]
    w.close();app.processEvents()


@pytest.mark.parametrize('side,offset,cursor',[('A',-8,4.123),('B',8,8.123),('roll',0,4.123)])
def test_shared_edit_sides_snap_without_affecting_opposite_side(tmp_path,side,offset,cursor):
    app,w,rows=open_window(tmp_path);t=w.timeline;t.snap_enabled=True;t.position=cursor
    left,right=rows[1:];rect=next(r for c,r in t.regions() if c['id']==left['id'])
    grab=QPoint(round(t.x_at(6))+offset,round(rect.center().y()))
    QTest.mousePress(t,Qt.LeftButton,Qt.NoModifier,grab);assert t.drag['side']==side
    destination=QPoint(round(t.x_at(cursor)+t.drag['offset']-5),grab.y());QTest.mouseMove(t,destination)
    assert t.drag['snapped_to_playhead'] and w.p.cues()==rows
    QTest.mouseRelease(t,Qt.LeftButton,Qt.NoModifier,destination)
    after={c['id']:c for c in w.p.cues()}
    assert after[left['id']]['end']==(cursor if side in ('A','roll') else 6)
    assert after[right['id']]['start']==(cursor if side in ('B','roll') else 6)
    w.undo_cue_edit();assert w.p.cues()==rows
    w.close();app.processEvents()


def test_snap_holds_near_cursor_releases_and_cancels(tmp_path):
    app,w,c=isolated_window(tmp_path);t=w.timeline;t.position=3.123
    rect=t.regions()[0][1];grab=QPoint(round(rect.left()),round(rect.center().y()))
    QTest.mousePress(t,Qt.LeftButton,Qt.NoModifier,grab)
    def move(distance):QTest.mouseMove(t,QPoint(round(t.x_at(t.position)+t.drag['offset']+distance),grab.y()))
    move(6);assert t.drag['snapped_to_playhead']
    move(12);assert t.drag['snapped_to_playhead'] and t.cues[0]['start']==t.position
    move(20);assert not t.drag['snapped_to_playhead'] and t.cues[0]['start']>t.position
    QTest.keyClick(t,Qt.Key_Escape);QTest.mouseRelease(t,Qt.LeftButton,Qt.NoModifier,grab)
    assert w.p.cues()==[c] and t.drag is None
    w.close();app.processEvents()


def test_disabled_snapping_and_invalid_cursor_still_respect_boundaries(tmp_path):
    app,w,c=isolated_window(tmp_path);t=w.timeline;t.position=3.123;t.snap_enabled=False
    rect=t.regions()[0][1];grab=QPoint(round(rect.left()),round(rect.center().y()))
    QTest.mousePress(t,Qt.LeftButton,Qt.NoModifier,grab)
    destination=QPoint(round(t.x_at(t.position))+6,grab.y());QTest.mouseMove(t,destination)
    assert not t.drag['snapped_to_playhead'] and t.cues[0]['start']!=t.position
    t.cancel_drag();QTest.mouseRelease(t,Qt.LeftButton,Qt.NoModifier,destination)
    # Snapping must never collapse a cue to zero duration.
    t.snap_enabled=True;t.position=c['end']
    QTest.mousePress(t,Qt.LeftButton,Qt.NoModifier,grab)
    QTest.mouseMove(t,QPoint(round(t.x_at(t.position)),grab.y()))
    assert not t.drag['snapped_to_playhead'] and t.cues[0]['start']<c['end']
    t.cancel_drag();QTest.mouseRelease(t,Qt.LeftButton,Qt.NoModifier,grab)
    assert w.p.cues()==[c]
    w.close();app.processEvents()


def test_settings_toggle_saves_app_preference(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);stored=[]
    monkeypatch.setattr(w.prefs,'setValue',lambda key,value:stored.append((key,value)))
    assert w.snap_action in w.program_settings.actions()
    w.snap_action.setChecked(True);w.snap_action.setChecked(False)
    assert not w.timeline.snap_enabled and stored[-1]==('snap_to_playhead',False)
    w.snap_action.setChecked(True)
    assert w.timeline.snap_enabled and stored[-1]==('snap_to_playhead',True)
    w.close();app.processEvents()
