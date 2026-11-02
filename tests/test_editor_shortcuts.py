import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from test_timeline import open_window


@pytest.mark.parametrize('target',['timeline','cue_table'])
def test_seek_step_marks_create_and_escape(tmp_path,target):
    app,w,rows=open_window(tmp_path);t=w.timeline;widget=getattr(w,target)
    w.seek(3)
    QTest.keyClick(widget,Qt.Key_Right,Qt.KeypadModifier)
    assert t.position==pytest.approx(91/(30000/1001),abs=.001)
    QTest.keyClick(widget,Qt.Key_Left,Qt.KeypadModifier)
    assert t.position==pytest.approx(90/(30000/1001),abs=.001)
    QTest.keyClick(widget,Qt.Key_Right,Qt.ShiftModifier|Qt.KeypadModifier)
    assert t.position==pytest.approx(90/(30000/1001)+1,abs=.002)
    QTest.keyClick(widget,Qt.Key_Home,Qt.KeypadModifier);assert t.position==0
    QTest.keyClick(widget,Qt.Key_Left);assert t.position==0
    QTest.keyClick(widget,Qt.Key_End,Qt.KeypadModifier);assert t.position==12
    QTest.keyClick(widget,Qt.Key_Right);assert t.position==12
    t.set_view(4,2);QTest.keyClick(widget,Qt.Key_Backslash)
    assert t.view_start==0 and t.view_span==12
    before=w.p.cues();QTest.keyClick(widget,Qt.Key_N);assert w.p.cues()==before
    w.seek(3);QTest.keyClick(widget,Qt.Key_I)
    w.seek(5);QTest.keyClick(widget,Qt.Key_O)
    assert (t.mark_in,t.mark_out)==(3,5)
    QTest.keyClick(widget,Qt.Key_N)
    new=next(c for c in w.p.cues() if c['id'] not in {r['id'] for r in before})
    assert (new['start'],new['end'])==(3,5)
    assert t.mark_in is None and t.mark_out is None
    w.undo_cue_edit();assert w.p.cues()==before
    QTest.keyClick(widget,Qt.Key_I);QTest.keyClick(widget,Qt.Key_Escape)
    assert t.mark_in is None and not w.selected_cues() and not t.selected
    w.close();app.processEvents()


@pytest.mark.parametrize('target',['timeline','cue_table'])
def test_review_identify_exclude_shortcuts_and_typing(tmp_path,monkeypatch,target):
    app,w,rows=open_window(tmp_path);widget=getattr(w,target)
    w.cue_table.selectRow(1)
    calls=[]
    monkeypatch.setattr(w,'retry_selected_cue',lambda:calls.append('identify'))
    monkeypatch.setattr(w,'edit_cue',lambda:calls.append('review'))
    QTest.keyClick(widget,Qt.Key_F);QTest.keyClick(widget,Qt.Key_Return)
    QTest.keyClick(widget,Qt.Key_Enter,Qt.KeypadModifier)
    assert calls==['identify','review','review']
    QTest.keyClick(widget,Qt.Key_X);assert rows[1]['id'] in w.p.excluded_cue_ids()
    w.filter.setCurrentText('Excluded');w.cue_table.selectRow(0)
    QTest.keyClick(widget,Qt.Key_X);assert not w.p.excluded_cue_ids()
    w.search.clear();w.search.setFocus();QTest.keyClicks(w.search,'inofx')
    assert w.search.text()=='inofx' and calls==['identify','review','review']
    assert w.timeline.mark_in is None and w.timeline.mark_out is None
    w.close();app.processEvents()


def test_invalid_marks_and_drag_escape(tmp_path):
    app,w,rows=open_window(tmp_path);t=w.timeline;before=w.p.cues()
    w.seek(5);QTest.keyClick(t,Qt.Key_I)
    w.seek(3);QTest.keyClick(t,Qt.Key_O);QTest.keyClick(t,Qt.Key_N)
    assert w.p.cues()==before
    t.begin_drag(t.cues[1],'start');t.cues[1]['start']=3
    QTest.keyClick(t,Qt.Key_F);assert t.drag
    QTest.keyClick(t,Qt.Key_Escape)
    assert t.drag is None and t.cues[1]['start']==2
    w.close();app.processEvents()
