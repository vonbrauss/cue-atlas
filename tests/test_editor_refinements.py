import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from cueatlas.timeline import Timeline
from test_timeline import open_window


def test_space_on_buttons_only_controls_playback(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);calls=[]
    monkeypatch.setattr(w,'preview_cue',lambda:calls.append('play'))
    for button in (w.monitor_button,w.waveform_focus_button,w.project_button,w.play_button):
        clicked=[];button.clicked.connect(lambda *a:clicked.append(True));checked=button.isChecked()
        button.setFocus();QTest.keyClick(button,Qt.Key_Space)
        assert not clicked and button.isChecked()==checked
    assert calls==['play']*4
    w.search.setFocus();QTest.keyClicks(w.search,' ');assert w.search.text()==' ' and len(calls)==4
    w.close();app.processEvents()


@pytest.mark.parametrize('key,position,expected',[(Qt.Key_Q,1,(1,6)),(Qt.Key_W,8,(2,8)),(Qt.Key_Q,3,(3,6)),(Qt.Key_W,4,(2,4))])
def test_trim_and_extend_selected_cue_undo(tmp_path,key,position,expected):
    app,w,rows=open_window(tmp_path);t=w.timeline
    w.cue_table.selectRow(1);t.position=position;t.setFocus();QTest.keyClick(t,key)
    current=w.p.cues();selected=next(c for c in current if c['id']==rows[1]['id'])
    assert (selected['start'],selected['end'])==expected
    assert [c for c in current if c['id']!=selected['id']]==[rows[0],rows[2]]
    w.p.undo_edit();assert w.p.cues()==rows
    w.close();app.processEvents()


def test_clear_marks_shortcuts_keep_selection_and_history(tmp_path):
    app,w,rows=open_window(tmp_path);t=w.timeline;w.cue_table.selectRow(1)
    selected=set(t.selected);history=w.p.edit_history()
    for key,expected in [(Qt.Key_I,(None,7)),(Qt.Key_O,(1,None)),(Qt.Key_X,(None,None))]:
        t.mark_in=1;t.mark_out=7
        QTest.keyClick(t,key,Qt.AltModifier)
        assert (t.mark_in,t.mark_out)==expected
        assert t.selected==selected and w.p.edit_history()==history
    w.close();app.processEvents()


def test_song_colors_are_unique_repeated_and_unknown_yellow():
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    t=Timeline();colors=[t.color({'id':str(i),'track':str(i)}).name() for i in range(40)]
    assert len(set(colors))==40
    assert t.color({'id':'repeat','track':'2'}).name()==colors[2]
    assert t.color({'id':'u1','track':None}).name()==t.color({'id':'u2','track':None}).name()=='#f5d65c'
    assert '#f5d65c' not in colors
