import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from test_timeline import open_window,center


def drag_box(t,start,end,modifiers=Qt.NoModifier,release=True):
    QTest.mousePress(t,Qt.LeftButton,modifiers,start)
    QTest.mouseMove(t,end)
    if release:QTest.mouseRelease(t,Qt.LeftButton,modifiers,end)


@pytest.mark.parametrize('reverse',[False,True])
def test_lasso_touches_cues_syncs_sheet_without_editing_or_seeking(tmp_path,reverse):
    app,w,rows=open_window(tmp_path);t=w.timeline;history=w.p.edit_history();t.position=10
    first,last=(5,1) if reverse else (1,5)
    start=QPoint(round(t.x_at(first)),t.height()-20);end=QPoint(round(t.x_at(last)),29)
    drag_box(t,start,end,release=False);app.processEvents()
    assert t.drag['kind']=='lasso' and t.drag['moved']
    assert t.selected=={rows[0]['id'],rows[1]['id']}
    assert {c['id'] for c in w.selected_cues()}==t.selected and w.merge_button.isEnabled()
    w.grab().save('/private/tmp/cueatlas-lasso.png')
    QTest.mouseRelease(t,Qt.LeftButton,Qt.NoModifier,end)
    assert t.drag is None and t.position==10
    assert w.p.cues()==rows and w.p.edit_history()==history
    w.close();app.processEvents()


@pytest.mark.parametrize('modifier',[Qt.ControlModifier,Qt.MetaModifier])
def test_lasso_adds_to_selection_and_escape_restores_it(tmp_path,modifier):
    app,w,rows=open_window(tmp_path);t=w.timeline
    QTest.mouseClick(t,Qt.LeftButton,Qt.NoModifier,center(t,rows[2]['id']))
    start=QPoint(round(t.x_at(.3)),t.height()-20);end=QPoint(round(t.x_at(1.2)),29)
    drag_box(t,start,end,modifier,release=False)
    assert t.selected=={rows[0]['id'],rows[2]['id']}
    QTest.keyClick(t,Qt.Key_Escape);QTest.mouseRelease(t,Qt.LeftButton,modifier,end)
    assert t.drag is None and t.selected=={rows[2]['id']}
    assert {c['id'] for c in w.selected_cues()}==t.selected
    drag_box(t,start,end,modifier)
    assert t.selected=={rows[0]['id'],rows[2]['id']}
    assert w.p.cues()==rows
    w.close();app.processEvents()


def test_lasso_in_excluded_view_selects_only_visible_cues(tmp_path):
    app,w,rows=open_window(tmp_path);t=w.timeline
    w.p.set_cues_excluded([rows[1]['id']]);w.refresh(cues_only=True)
    start=QPoint(round(t.x_at(.2)),t.height()-20);end=QPoint(round(t.x_at(11)),29)
    drag_box(t,start,end)
    assert t.selected=={rows[0]['id'],rows[2]['id']}
    w.filter.setCurrentText('Excluded');drag_box(t,start,end)
    assert t.selected=={rows[1]['id']} and not w.merge_button.isEnabled()
    w.close();app.processEvents()


def test_lasso_respects_overlapping_cue_lanes(tmp_path):
    app,w,rows=open_window(tmp_path);t=w.timeline
    rows[0].update(start=0,end=5);rows[1].update(start=1,end=6);rows[2].update(start=3,end=12)
    w.p.save_cues(rows);w.refresh(cues_only=True)
    rects={c['id']:rect for c,rect in t.regions()}
    start=QPoint(round(t.x_at(.5)),22)
    end=QPoint(round(t.x_at(4)),round(rects[rows[1]['id']].bottom()-1))
    drag_box(t,start,end)
    assert t.selected=={rows[0]['id'],rows[1]['id']}
    assert w.p.cues()==rows
    w.close();app.processEvents()
