import json
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialogButtonBox
from cueatlas.shortcuts import DEFAULTS,conflicts,ShortcutDialog,load_bindings
from test_timeline import open_window


def test_shortcut_conflicts_reserved_defaults_and_disable():
    app=QApplication.instance() or QApplication([])
    assert not conflicts(DEFAULTS)
    assert conflicts(DEFAULTS|{'play':'J'})
    assert conflicts(DEFAULTS|{'play':'Ctrl+O'})
    dialog=ShortcutDialog(DEFAULTS)
    dialog.editors['play'].setKeySequence(QKeySequence('J'))
    assert not dialog.buttons.button(QDialogButtonBox.Save).isEnabled()
    dialog.reset();assert dialog.buttons.button(QDialogButtonBox.Save).isEnabled()
    dialog.editors['play'].setKeySequence(QKeySequence())
    assert dialog.bindings()['play']=='';dialog.close()


def test_remap_applies_without_old_handler_and_does_not_intercept_text(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);calls=[]
    monkeypatch.setattr(w,'preview_cue',lambda:calls.append('play'))
    w.shortcut_bindings=DEFAULTS|{'play':'P'}
    for widget in (w.timeline,w.cue_table):
        QTest.keyClick(widget,Qt.Key_Space);assert not calls
    QTest.keyClick(w.timeline,Qt.Key_P);QTest.keyClick(w.cue_table,Qt.Key_P);assert calls==['play','play']
    w.search.setFocus();QTest.keyClicks(w.search,'p');assert len(calls)==2
    w.prefs.setValue('keyboard_shortcuts',json.dumps(w.shortcut_bindings))
    assert load_bindings(w.prefs)['play']=='P'
    w.close();app.processEvents()
