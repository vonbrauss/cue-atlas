from pathlib import Path
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QFileDialog
from cueatlas.project import Project
from cueatlas.projects import ProjectManager
from test_timeline import open_window


def test_full_history_filters_sort_favorites_and_selection(tmp_path,monkeypatch):
    app,w,_=open_window(tmp_path)
    try:
        for i in range(20):
            path=tmp_path/f'Episode {i:02}.cueatlas';p=Project(path,True);p.close();w.remember_project(str(path))
        assert len(w.recent)==21
        d=ProjectManager(w);d.show();app.processEvents()
        d.search.setText('Episode 04');assert d.selected()['name']=='Episode 04'
        d.toggle_favorite();favorite=d.selected()['path'];assert favorite in w.favorite_projects
        d.search.clear();d.navigation.setCurrentRow(1);assert d.selected()['path']==favorite
        assert sum(not d.table.isRowHidden(i) for i in range(len(d.rows)))==1
        d.toggle_favorite();assert d.selected() is None and not d.buttons['Open'].isEnabled()
        d.navigation.setCurrentRow(0);d.sort.setCurrentIndex(1)
        assert [r['name'] for r in d.rows]==sorted([r['name'] for r in d.rows],key=str.casefold)
        d.search.setText('not found');assert d.selected() is None and not d.buttons['Move to Trash…'].isEnabled()
        missing=tmp_path/'Missing.cueatlas';w.remember_project(str(missing));d.search.clear();d.refresh();d.navigation.setCurrentRow(2)
        assert d.selected()['path']==str(missing) and not d.buttons['Open'].isEnabled()
        d.close()
    finally:w.close();app.processEvents()


def test_menu_bounded_same_name_and_favorite_rename(tmp_path,monkeypatch):
    app,w,_=open_window(tmp_path)
    try:
        paths=[]
        for i in range(18):
            directory=tmp_path/str(i);directory.mkdir();path=directory/'Episode.cueatlas'
            p=Project(path,True);p.close();w.remember_project(str(path));paths.append(path)
        w.update_project_menu()
        quick=[a for a in w.recent_projects_menu.actions() if a.isCheckable()]
        assert len(quick)==6 and len({a.text() for a in quick})==6
        opened=[];monkeypatch.setattr(w,'load',lambda path:opened.append(path))
        quick[-1].trigger();assert opened==[str(paths[-6])]
        current=str(w.p.path);w.set_project_favorite(current,True)
        renamed=w.rename_project_file(current,'Renamed favorite')
        assert str(renamed) in w.favorite_projects and current not in w.favorite_projects
        w.forget_project(str(renamed));assert str(renamed) not in w.favorite_projects
        w.close_project();w.update_project_menu();assert all(not a.isEnabled() for a in w.current_project_actions)
    finally:w.close();app.processEvents()


def test_metadata_menu_accessible_at_compact_width(tmp_path,monkeypatch):
    app,w,_=open_window(tmp_path)
    try:
        w.set_waveform_focus(False);w.resize(950,650);w.tabs.setCurrentIndex(1);app.processEvents()
        assert w.width()==950
        for button in [w.addfolder_button,w.addfiles_button,w.importlibrary_button,w.metadata_button,w.relink_button,w.removeref_button]:
            assert button.isVisible() and button.isEnabled()
            origin=button.mapTo(w.centralWidget(),QPoint(0,0))
            assert origin.x()>=0 and origin.x()+button.width()<=w.centralWidget().width()
        assert w.metadata_button.geometry().center().y()==w.addfolder_button.geometry().center().y()==w.removeref_button.geometry().center().y()
        assert w.metadata_button.menu() is w.metadata_menu
        assert w.enrichmetadata_action in w.metadata_menu.actions()
        assert w.exportlibrary_action in w.metadata_menu.actions()
        dialogs=[];monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *args:dialogs.append(args[1]) or ('',''))
        w.enrichmetadata_action.trigger();assert dialogs==['Import reference metadata JSON']
        w.grab().save('/private/tmp/cueatlas-library-062.png')
        w.close_project();assert not w.metadata_button.isEnabled() and not w.enrichmetadata_action.isEnabled()
    finally:w.close();app.processEvents()
