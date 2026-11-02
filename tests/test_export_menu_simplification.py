from PySide6.QtWidgets import QDialog
from PySide6.QtGui import QAction
from cueatlas.workflow_ui import CueExportDialog,ValidationDialog
from cueatlas.workflow import validate_cues
from test_timeline import open_window


def test_settings_have_one_menu_home(tmp_path):
    app,w,_=open_window(tmp_path)
    menus={a.text():a.menu() for a in w.menuBar().actions() if a.menu()}
    assert [a.text() for a in w.program_settings.actions() if not a.isSeparator()]==[
        'Choose / relink audio or video…','Analyze program…','Snap edits to playhead']
    assert 'Project settings…' in [a.text() for a in menus['Project'].actions()]
    assert next(a for a in menus['Project'].actions() if a.text()=='Project settings…').menuRole()==QAction.NoRole
    assert 'Keyboard shortcuts…' in [a.text() for a in menus['Edit'].actions()]
    assert 'Reconnect selected reference…' in [a.text() for a in menus['Library'].actions()]
    assert 'Reference duplicates and alternate mixes…' in [a.text() for a in menus['Library'].actions()]
    assert 'Review queue…' in [a.text() for a in menus['Cue sheet'].actions()]
    assert 'Shortcut reference…' in [a.text() for a in menus['Help'].actions()]
    assert sum(a.text()=='Project settings…' for m in menus.values() for a in m.actions())==1
    w.close();app.processEvents()


def test_export_warnings_are_optional_in_save_dialog(tmp_path,monkeypatch):
    app,w,_=open_window(tmp_path);output=tmp_path/'delivered.csv';seen=[]
    assert validate_cues(w.p) and not any(i['severity']=='error' for i in validate_cues(w.p))
    monkeypatch.setattr(ValidationDialog,'exec',lambda self:seen.append('warnings') or QDialog.Rejected)
    def save(dialog):
        assert dialog.warnings_button.isEnabled()
        assert not seen
        dialog.selectFile(str(output));return QDialog.Accepted
    monkeypatch.setattr(CueExportDialog,'exec',save)
    w.export_cues();assert output.is_file() and not seen
    dialog=CueExportDialog(w,validate_cues(w.p));dialog.warnings_button.click();assert seen==['warnings']
    dialog.selectFile(str(tmp_path/'report.csv'));dialog.change_format('Excel (*.xlsx)')
    assert dialog.selectedFiles()[0].endswith('report.xlsx') and dialog.defaultSuffix()=='xlsx'
    dialog.close();w.close();app.processEvents()


def test_export_cancel_and_invalid_timings_do_not_write(tmp_path,monkeypatch):
    import cueatlas.gui as gui
    app,w,rows=open_window(tmp_path);seen=[]
    monkeypatch.setattr(gui,'export',lambda *args:seen.append('export'))
    monkeypatch.setattr(CueExportDialog,'exec',lambda self:QDialog.Rejected)
    w.export_cues();assert not seen
    rows[0]['start']=-1;w.p.save_cues(rows)
    def unexpected(self):raise AssertionError('Invalid timings reached the save dialog')
    monkeypatch.setattr(CueExportDialog,'exec',unexpected)
    monkeypatch.setattr(ValidationDialog,'exec',lambda self:seen.append('errors') or QDialog.Rejected)
    w.export_cues();assert seen==['errors']
    w.close();app.processEvents()
