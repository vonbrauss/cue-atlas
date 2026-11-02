import math
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from cueatlas.project import cue
from cueatlas.coverage import covered_seconds
from test_timeline import fixture_project,open_window


@pytest.mark.parametrize('side,point', [('roll',4),('roll',8),('A',4),('B',8)])
def test_edit_point_sides_persistence_coverage_and_undo(tmp_path,side,point):
    p,rows=fixture_project(tmp_path)
    # Include an Unknown B side to verify a single-side trim leaves it intact.
    a,b=rows[1:]
    p.adjust_edit_point(a['id'],b['id'],point,side)
    after={c['id']:c for c in p.cues()}
    assert after[a['id']]['end']==(point if side in ('A','roll') else 6)
    assert after[b['id']]['start']==(point if side in ('B','roll') else 6)
    assert after[a['id']]['start']==a['start'] and after[b['id']]['end']==b['end']
    assert {k:v for k,v in after[a['id']].items() if k!='end'}=={k:v for k,v in a.items() if k!='end'}
    assert {k:v for k,v in after[b['id']].items() if k!='start'}=={k:v for k,v in b.items() if k!='start'}
    assert covered_seconds(p.cues(),12)==(12 if side=='roll' else 10)
    assert len(p.cues())==len(rows)
    path=p.path;p.close()
    from cueatlas.project import Project
    p=Project(path);p.undo_trim();assert p.cues()==rows;p.close()


def test_roll_rejects_invalid_or_ambiguous_edits(tmp_path):
    p,rows=fixture_project(tmp_path);a,b=rows[1:]
    for point in [a['start'],b['end'],-1,math.nan,math.inf]:
        with pytest.raises(ValueError):p.adjust_edit_point(a['id'],b['id'],point)
        assert p.cues()==rows
    with pytest.raises(ValueError):p.adjust_edit_point(b['id'],a['id'],5)
    with pytest.raises(ValueError):p.adjust_edit_point(rows[0]['id'],b['id'],5)
    p.set_cues_excluded([b['id']])
    with pytest.raises(ValueError,match='Restore'):p.adjust_edit_point(a['id'],b['id'],5)
    p.set_cues_excluded([b['id']],False)
    for start in [5,7]:
        changed=[rows[0],a,b|{'start':start}];p.save_cues(changed)
        before=p.cues()
        with pytest.raises(ValueError):p.adjust_edit_point(a['id'],b['id'],8)
        assert p.cues()==before
    p.close()


@pytest.mark.parametrize('side',['A','B','roll'])
def test_shared_boundary_cursor_targets(tmp_path,side):
    app,w,rows=open_window(tmp_path);t=w.timeline
    offset={'A':-8,'B':8,'roll':0}[side];app.processEvents()
    a,b=rows[1:];rect=next(r for c,r in t.regions() if c['id']==a['id'])
    edge=QPoint(round(t.x_at(6))+offset,round(rect.center().y()))
    point=4 if side=='A' else 8
    destination=QPoint(round(t.x_at(point))+offset,edge.y())
    QTest.mousePress(t,Qt.LeftButton,Qt.NoModifier,edge)
    assert t.drag['side']==side
    original_tops={c['id']:r.top() for c,r in t.regions()}
    QTest.mouseMove(t,destination)
    assert w.p.cues()==rows  # One atomic save on release.
    assert {c['id']:r.top() for c,r in t.regions()}==original_tops
    QTest.mouseRelease(t,Qt.LeftButton,Qt.NoModifier,destination)
    after={c['id']:c for c in w.p.cues()}
    assert after[a['id']]['end']==pytest.approx(point if side in ('A','roll') else 6,abs=.04)
    assert after[b['id']]['start']==pytest.approx(point if side in ('B','roll') else 6,abs=.04)
    assert w.undo_action.isEnabled()
    w.undo_boundary_edit();assert w.p.cues()==rows
    # Escape cancels both sides, with no saved changes.
    QTest.mousePress(t,Qt.LeftButton,Qt.NoModifier,edge);QTest.mouseMove(t,destination)
    QTest.keyClick(t,Qt.Key_Escape);QTest.mouseRelease(t,Qt.LeftButton,Qt.NoModifier,destination)
    assert w.p.cues()==rows
    assert [(c['start'],c['end']) for c in t.cues]==[(c['start'],c['end']) for c in rows]
    w.close();app.processEvents()


def test_shared_join_rolls_with_both_cues_selected(tmp_path):
    app,w,rows=open_window(tmp_path);t=w.timeline
    a,b=rows[1:]
    for item,mod in [(a,Qt.NoModifier),(b,Qt.ControlModifier)]:
        rect=next(r for c,r in t.regions() if c['id']==item['id'])
        QTest.mouseClick(t,Qt.LeftButton,mod,rect.center().toPoint())
    assert t.selected=={a['id'],b['id']}
    rect=next(r for c,r in t.regions() if c['id']==a['id'])
    edge=QPoint(round(t.x_at(6)),round(rect.center().y()))
    QTest.mousePress(t,Qt.LeftButton,Qt.NoModifier,edge);assert t.drag['side']=='roll'
    dest=QPoint(round(t.x_at(7)),edge.y());QTest.mouseMove(t,dest);QTest.mouseRelease(t,Qt.LeftButton,Qt.NoModifier,dest)
    after={c['id']:c for c in w.p.cues()}
    assert after[a['id']]['end']==after[b['id']]['start']
    assert after[a['id']]['end']==pytest.approx(7,abs=.04)
    assert len(after)==3
    w.close();app.processEvents()
