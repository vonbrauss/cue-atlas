import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QComboBox
from cueatlas.project import Project
from test_timeline import open_window,fixture_project,center


def test_gaps_survive_review_merge_reopen_and_history(tmp_path):
    p,rows=fixture_project(tmp_path)
    p.trim_cue(rows[2]['id'],8,10)
    trimmed=p.cues();assert len(trimmed)==3
    edited=[c|{'note':'checked'} if c['id']==rows[1]['id'] else c for c in trimmed]
    p.save_cues(edited,label='Review cue')
    p.merge_cues([rows[0]['id'],rows[1]['id']],track=rows[1]['track'],reviewed=True)
    merged=p.cues();assert [(c['start'],c['end']) for c in merged]==[(0,6),(8,10)]
    path=p.path;p.close();p=Project(path)
    assert p.cues()==merged
    p.undo_edit();assert p.cues()==edited
    p.redo_edit();assert p.cues()==merged
    p.close()


@pytest.mark.parametrize('reverse',[False,True])
def test_shift_drag_draws_exactly_one_cue_with_undo_redo(tmp_path,reverse):
    app,w,rows=open_window(tmp_path);t=w.timeline
    # Drawing over empty space remains possible after removing all cues.
    w.p.save_cues([]);w.refresh();app.processEvents()
    a,b=(7,3) if reverse else (3,7)
    start=QPoint(round(t.x_at(a)),t.height()-40);end=QPoint(round(t.x_at(b)),start.y())
    history=w.p.edit_history()
    QTest.mousePress(t,Qt.LeftButton,Qt.ShiftModifier,start)
    QTest.mouseMove(t,end)
    assert not w.p.cues() and w.p.edit_history()==history
    assert t.drag['kind']=='draw' and t.drag['moved']
    QTest.mouseRelease(t,Qt.LeftButton,Qt.ShiftModifier,end)
    drawn=w.p.cues();assert len(drawn)==1
    assert drawn[0]['start']==pytest.approx(3,abs=.04)
    assert drawn[0]['end']==pytest.approx(7,abs=.04)
    assert t.selected=={drawn[0]['id']} and w.undo_action.text()=='Undo Add cue'
    w.undo_cue_edit();assert not w.p.cues()
    w.redo_cue_edit();assert w.p.cues()==drawn
    w.close();app.processEvents()


def test_draw_cancel_click_and_busy_do_not_add_cues(tmp_path):
    app,w,rows=open_window(tmp_path);t=w.timeline
    w.activateWindow();t.setFocus();app.processEvents()
    start=QPoint(round(t.x_at(3)),t.height()-40);end=QPoint(round(t.x_at(7)),start.y())
    before=w.p.edit_history()
    QTest.mouseClick(t,Qt.LeftButton,Qt.ShiftModifier,start)
    assert w.p.cues()==rows and w.p.edit_history()==before
    for key,modifier in [(Qt.Key_Escape,Qt.NoModifier),(Qt.Key_Z,Qt.ControlModifier)]:
        QTest.mousePress(t,Qt.LeftButton,Qt.ShiftModifier,start);QTest.mouseMove(t,end)
        QTest.keyClick(t,key,modifier);QTest.mouseRelease(t,Qt.LeftButton,Qt.ShiftModifier,end)
        assert w.p.cues()==rows and w.p.edit_history()==before and t.drag is None
    t.editable=False
    QTest.mousePress(t,Qt.LeftButton,Qt.ShiftModifier,start);assert t.drag is None
    QTest.mouseMove(t,end);QTest.mouseRelease(t,Qt.LeftButton,Qt.ShiftModifier,end)
    assert w.p.cues()==rows
    w.close();app.processEvents()


def test_shift_click_selection_and_shift_drag_over_cue(tmp_path):
    app,w,rows=open_window(tmp_path);t=w.timeline
    QTest.mouseClick(t,Qt.LeftButton,Qt.NoModifier,center(t,rows[0]['id']))
    QTest.mouseClick(t,Qt.LeftButton,Qt.ShiftModifier,center(t,rows[2]['id']))
    assert len(t.selected)==3 and w.p.cues()==rows
    start=center(t,rows[1]['id']);end=start+QPoint(50,0)
    QTest.mousePress(t,Qt.LeftButton,Qt.ShiftModifier,start);QTest.mouseMove(t,end)
    QTest.mouseRelease(t,Qt.LeftButton,Qt.ShiftModifier,end)
    assert len(w.p.cues())==4
    assert all(c in w.p.cues() for c in rows)  # No replacement of existing cues.
    w.close();app.processEvents()


def test_cursor_modes_and_consolidated_controls(tmp_path):
    app,w,rows=open_window(tmp_path);t=w.timeline
    assert not w.program_card.findChildren(QComboBox)
    rect=next(r for c,r in t.regions() if c['id']==rows[1]['id'])
    for offset,side,label in [(-8,'A','Audition Out'),(0,'roll','Audition edit'),(8,'B','Audition In')]:
        point=QPoint(round(t.x_at(6))+offset,round(rect.center().y()))
        QTest.mouseMove(t,point,10);app.processEvents()
        assert bool(t.hover_pair)==(side=='roll')
        QTest.mouseClick(t,Qt.LeftButton,Qt.NoModifier,point)
        assert t.active_edit['side']==side and w.audition_button.text()==label
        assert w.p.cues()==rows
    # A frame nudge uses the clicked B side and leaves A untouched.
    QTest.keyClick(t,Qt.Key_Period)
    after={c['id']:c for c in w.p.cues()}
    assert after[rows[1]['id']]==rows[1]
    assert after[rows[2]['id']]['start']>6 and len(after)==3
    w.close();app.processEvents()
