import pytest
from PySide6.QtCore import Qt,QItemSelectionModel,QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox,QApplication
from test_timeline import open_window,center


@pytest.mark.parametrize('surface,key',[('sheet',Qt.Key_Backspace),('timeline',Qt.Key_Delete)])
def test_delete_excluded_selection_confirmation_and_undo(tmp_path,monkeypatch,surface,key):
    app,w,rows=open_window(tmp_path);ids={rows[0]['id'],rows[1]['id']}
    w.p.set_cues_excluded(ids);w.refresh();w.filter.setCurrentText('Excluded')
    flags=QItemSelectionModel.Select|QItemSelectionModel.Rows
    for row in range(2):w.cue_table.selectionModel().select(w.cue_table.model().index(row,0),flags)
    if surface=='sheet':w.set_waveform_focus(False)
    target=w.cue_table if surface=='sheet' else w.timeline
    app.processEvents();assert w.timeline.selected==ids
    before=w.p._edit_state();history=w.p.edit_history();tracks=w.p.tracks();questions=[]
    def decline(*args):questions.append(args);return QMessageBox.No
    monkeypatch.setattr(QMessageBox,'question',decline)
    QTest.keyClick(target,key)
    assert len(questions)==1 and '2 selected cues' in questions[0][2]
    assert questions[0][-1]==QMessageBox.No
    assert w.p._edit_state()==before and w.p.edit_history()==history
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Yes)
    QTest.keyClick(target,key)
    assert w.p.cues()==[rows[2]] and not w.p.excluded_cue_ids()
    assert w.p.tracks()==tracks and w.undo_action.text()=='Undo Delete cues'
    assert w.filter.currentText()=='Excluded' and not w.cue_rows
    w.undo_cue_edit();assert w.p._edit_state()==before
    assert w.filter.currentText()=='Excluded' and w.timeline.selected==ids
    w.redo_cue_edit();assert w.p.cues()==[rows[2]] and not w.p.excluded_cue_ids()
    w.close();app.processEvents()


def test_delete_normal_cue_leaves_gap_and_text_fields_keep_delete(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);t=w.timeline
    QTest.mouseClick(t,Qt.LeftButton,Qt.NoModifier,center(t,rows[1]['id']))
    questions=[]
    def confirm(*args):questions.append(args);return QMessageBox.Yes
    monkeypatch.setattr(QMessageBox,'question',confirm)
    # Holding Delete must not repeatedly present confirmation dialogs.
    event=QKeyEvent(QEvent.KeyPress,Qt.Key_Backspace,Qt.NoModifier,'',True,1)
    QApplication.sendEvent(t,event);assert not questions
    QTest.keyClick(t,Qt.Key_Backspace)
    assert len(questions)==1 and 'Neon evenings' in questions[0][2]
    assert w.p.cues()==[rows[0],rows[2]]
    assert w.undo_action.text()=='Undo Delete cue'
    QTest.keyClick(t,Qt.Key_Delete);assert len(questions)==1  # No selection.
    w.search.setFocus();QTest.keyClicks(w.search,'abc');QTest.keyClick(w.search,Qt.Key_Backspace)
    assert w.search.text()=='ab' and len(questions)==1
    assert w.p.cues()==[rows[0],rows[2]]
    w.close();app.processEvents()


def test_delete_ignored_during_drag_or_when_timeline_not_editable(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);t=w.timeline;questions=[]
    monkeypatch.setattr(QMessageBox,'question',lambda *args:questions.append(args) or QMessageBox.Yes)
    QTest.mouseClick(t,Qt.LeftButton,Qt.NoModifier,center(t,rows[1]['id']))
    t.editable=False;QTest.keyClick(t,Qt.Key_Delete)
    assert not questions and w.p.cues()==rows
    t.editable=True;t.begin_drag(next(c for c in t.cues if c['id']==rows[1]['id']),'end')
    QTest.keyClick(t,Qt.Key_Backspace);assert t.drag and not questions
    t.cancel_drag();w.close();app.processEvents()
