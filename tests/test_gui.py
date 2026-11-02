import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
from scipy.io.wavfile import write
from PySide6.QtWidgets import QApplication
from cueatlas.gui import Window,SettingsDialog,MetadataDialog,CueDialog,STYLE
from cueatlas.project import Project,cue
from cueatlas.audio import SR
from cueatlas.engine import import_files,analyze
from test_core import music


def test_gui_project_loading_and_dialogs(tmp_path):
    app=QApplication.instance() or QApplication([]);app.setStyleSheet(STYLE)
    path=tmp_path/'demo.cueatlas';p=Project(path,True,'The evening show')
    file=tmp_path/'Song.wav';write(file,SR,music(78,6));p.close()
    import_files(path,[str(file)]);p=Project(path);p.set('program',{'path':str(file)});p.close();analyze(path)
    w=Window();w.load(str(path));w.show();app.processEvents()
    assert w.heading.text()=='demo';assert w.reference_table.rowCount()==1;assert w.cue_table.rowCount()>=1
    d=SettingsDialog(w.p,w);d.origin.setText('10:00:00;00');d.accept();assert d.settings['origin']=='10:00:00;00'
    m=MetadataDialog(w.p.tracks()[0],w);m.inputs['publisher'].setText('Publisher');m.accept();assert m.metadata['publisher']=='Publisher'
    c=w.p.cues()[0];d=CueDialog(c,w.p.tracks(),6,w);d.status.setCurrentText('Reviewed');d.accept();assert d.c['status']=='Reviewed'
    w.search.setText('does not exist');assert w.cue_table.rowCount()==0
    w.search.clear();w.filter.setCurrentText('Reviewed');assert w.cue_table.rowCount()==0
    w.filter.setCurrentText('All cues');w.cue_table.selectRow(0);assert w.selected_cue()
    w.grab().save(str(tmp_path/'populated.png'))
    w.close();app.processEvents()


def test_multiselect_merge_and_coverage_summary(tmp_path,monkeypatch):
    from PySide6.QtCore import QItemSelectionModel
    from PySide6.QtWidgets import QDialog,QDialogButtonBox
    from cueatlas.gui import MergeDialog
    app=QApplication.instance() or QApplication([])
    path=tmp_path/'merge.cueatlas';p=Project(path,True,'Merge test')
    f=tmp_path/'ref.wav';write(f,SR,music(7,6));tid=p.save_track(f,6,{'title':'Known','raw':{}},[])
    p.set('program',{'path':str(f),'duration':6})
    p.save_cues([cue(tid,0,3,title='Known'),cue(None,3,6,title='Unknown 001')]);p.close()
    w=Window();w.load(str(path));app.processEvents()
    assert 'Coverage 100.00%' in w.summary.text()
    flags=QItemSelectionModel.Select|QItemSelectionModel.Rows
    for row in [0,1]:w.cue_table.selectionModel().select(w.cue_table.model().index(row,0),flags)
    assert len(w.selected_cues())==2 and w.merge_button.isEnabled()
    def accept_merge(self):
        assert self.reference.currentData()==tid
        assert not self.buttons.button(QDialogButtonBox.Save).isEnabled()
        self.confirm.setChecked(True);assert self.buttons.button(QDialogButtonBox.Save).isEnabled()
        self.accept();return QDialog.Accepted
    monkeypatch.setattr(MergeDialog,'exec',accept_merge)
    w.merge_button.click();assert len(w.p.cues())==1;assert w.p.cues()[0]['status']=='Reviewed'
    assert w.undo_action.isEnabled();w.undo_last_merge();assert len(w.p.cues())==2
    w.filter.setCurrentText('Reviewed');assert '(filtered)' in w.summary.text()
    w.load(str(path));assert w.filter.currentText()=='All cues'
    w.close();app.processEvents()


def test_cue_focus_keyboard_navigation_preview_and_merge(tmp_path,monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDialog
    from PySide6.QtMultimedia import QMediaPlayer
    from cueatlas.gui import MergeDialog
    app=QApplication.instance() or QApplication([])
    path=tmp_path/'keyboard.cueatlas';p=Project(path,True,'Keyboard')
    p.set('program',{'path':str(tmp_path/'missing.wav'),'duration':9})
    p.save_cues([cue(None,0,3),cue(None,3,6),cue(None,6,9)]);p.close()
    w=Window();w.load(str(path));w.show();app.processEvents()
    original_height=w.cue_table.height()
    w.focus_button.click();app.processEvents()
    assert w.focus_action.isChecked() and w.tabs.currentIndex()==0
    assert w.program_card.isHidden() and w.project_heading.isHidden()
    assert w.tabs.tabBar().isHidden() and w.cue_table.height()>original_height
    assert w.cue_table.currentRow()==0
    QTest.keyClick(w.cue_table,Qt.Key_Down)
    assert w.timeline.position==3 and w.cue_table.currentRow()==0
    QTest.keyClick(w.cue_table,Qt.Key_Up)
    assert w.timeline.position==0 and w.cue_table.currentRow()==0
    calls=[]
    monkeypatch.setattr(w.player,'setPosition',lambda ms:calls.append(('seek',ms)))
    monkeypatch.setattr(w.player,'play',lambda:calls.append(('play',)))
    monkeypatch.setattr(w.player,'pause',lambda:calls.append(('pause',)))
    QTest.keyClick(w.cue_table,Qt.Key_Space)
    assert calls==[('seek',0),('play',)] and w.stop_at==3
    monkeypatch.setattr(w.player,'playbackState',lambda:QMediaPlayer.PlayingState)
    QTest.keyClick(w.cue_table,Qt.Key_Space)
    assert calls[-1]==('pause',)
    w.position_changed(3000);assert w.stop_at is None
    QTest.keyClick(w.cue_table,Qt.Key_Down,Qt.ShiftModifier)
    assert len(w.selected_cues())==2
    def accept_merge(self):
        self.accept();return QDialog.Accepted
    monkeypatch.setattr(MergeDialog,'exec',accept_merge)
    QTest.keyClick(w.cue_table,Qt.Key_M)
    assert len(w.p.cues())==2 and w.p.cues()[0]['end']==6
    w.search.setFocus();QTest.keyClicks(w.search,'m ')
    assert w.search.text()=='m ' and len(w.p.cues())==2
    w.focus_button.click();app.processEvents()
    assert not w.program_card.isHidden() and not w.tabs.tabBar().isHidden()
    assert not w.focus_action.isChecked()
    w.close();app.processEvents()


def test_import_library_picker_and_background_completion(tmp_path,monkeypatch):
    import time
    from PySide6.QtWidgets import QFileDialog
    app=QApplication.instance() or QApplication([])
    source=Project(tmp_path/'source.cueatlas',True,'Library')
    reference=tmp_path/'reference.wav';reference.write_bytes(b'fixture')
    source.save_track(reference,6,{'title':'Reusable','license':'License 42','raw':{}},[(42,3)])
    source.close()
    target=Project(tmp_path/'target.cueatlas',True,'Destination');target.close()
    w=Window();assert not w.importlibrary_action.isEnabled()
    w.load(str(tmp_path/'target.cueatlas'));w.show();app.processEvents()
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *args:(str(tmp_path/'source.cueatlas'),''))
    w.importlibrary_button.click()
    assert not w.importlibrary_button.isEnabled() and not w.importlibrary_action.isEnabled()
    deadline=time.monotonic()+5
    while w.worker is not None and time.monotonic()<deadline:
        app.processEvents();time.sleep(.01)
    assert w.worker is None and w.reference_table.rowCount()==1
    assert 'Imported 1 references' in w.status.text()
    assert w.p.tracks()[0]['metadata']['license']=='License 42'
    assert w.importlibrary_action.isEnabled()
    w.close();app.processEvents()


def test_exclude_and_restore_multiple_cues(tmp_path):
    from PySide6.QtCore import QItemSelectionModel
    app=QApplication.instance() or QApplication([])
    path=tmp_path/'exclude.cueatlas';p=Project(path,True,'Exclude')
    p.set('program',{'path':str(tmp_path/'missing.wav'),'duration':9})
    original=[cue(None,0,3),cue(None,3,6),cue(None,6,9)];p.save_cues(original);p.close()
    w=Window();w.load(str(path));w.show();app.processEvents()
    flags=QItemSelectionModel.Select|QItemSelectionModel.Rows
    for row in [0,1]:w.cue_table.selectionModel().select(w.cue_table.model().index(row,0),flags)
    w.exclude_button.click()
    assert len(w.cue_rows)==1 and len(w.p.cues())==3
    assert '2 excluded' in w.summary.text() and w.cue_rows[0]['id']==original[2]['id']
    w.filter.setCurrentText('Excluded')
    assert len(w.cue_rows)==2 and w.exclude_button.text()=='Restore'
    w.cue_table.selectRow(0);w.exclude_button.click()
    assert len(w.cue_rows)==1
    w.filter.setCurrentText('All cues');assert len(w.cue_rows)==2
    assert w.p.cues()==original
    w.close();app.processEvents()
