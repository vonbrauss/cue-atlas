"""Keep GUI verification out of the user's Recents and app preferences."""
import pytest
from PySide6.QtCore import QSettings


@pytest.fixture(autouse=True)
def isolated_app_preferences(tmp_path,monkeypatch):
    import cueatlas.gui as gui
    path=str(tmp_path/'app-preferences.ini')
    monkeypatch.setattr(gui,'QSettings',lambda *args,**kwargs:QSettings(path,QSettings.IniFormat))
