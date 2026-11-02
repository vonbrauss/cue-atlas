import hashlib
import sqlite3
from pathlib import Path
import pytest
from PySide6.QtWidgets import QMessageBox,QFileDialog,QInputDialog
from cueatlas.project import Project
from cueatlas.projects import ProjectManager,project_info
from test_timeline import open_window


def setup_manager(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path)
    other=tmp_path/'other.cueatlas';p=Project(other,True,'Other project');p.close()
    w.recent=[str(w.p.path),str(other)];stored=[]
    monkeypatch.setattr(w.prefs,'setValue',lambda key,value:stored.append((key,list(value) if isinstance(value,list) else value)))
    d=ProjectManager(w);d.show();app.processEvents()
    return app,w,rows,other,d,stored


def select(d,path):
    row=next(i for i,info in enumerate(d.rows) if info['path']==str(path));d.table.selectRow(row)


def test_listing_is_read_only_missing_entries_can_be_forgotten(tmp_path,monkeypatch):
    app,w,rows,other,d,stored=setup_manager(tmp_path,monkeypatch)
    original=other.read_bytes();mtime=other.stat().st_mtime_ns
    assert project_info(other)['name']=='other' and project_info(other)['valid']
    assert other.read_bytes()==original and other.stat().st_mtime_ns==mtime
    missing=tmp_path/'missing.cueatlas';bad=tmp_path/'invalid.cueatlas';bad.write_text('Not a database')
    w.recent += [str(missing),str(bad)];d.refresh()
    assert not missing.exists() and not project_info(bad)['valid'] and bad.read_text()=='Not a database'
    select(d,missing);assert not d.buttons['Move to Trash…'].isEnabled() and d.buttons['Remove from Recents'].isEnabled()
    d.forget_selected();assert str(missing) not in w.recent and stored[-1]==('recent',w.recent)
    d.search.setText('other');assert sum(not d.table.isRowHidden(i) for i in range(len(d.rows)))==1
    d.close();w.close();app.processEvents()


def test_remove_from_recents_keeps_open_project_and_database(tmp_path,monkeypatch):
    app,w,rows,other,d,stored=setup_manager(tmp_path,monkeypatch);path=w.p.path
    select(d,path);before=path.read_bytes();d.forget_selected()
    assert str(path) not in w.recent and w.p.path==path and path.read_bytes()==before
    select(d,path);assert not d.buttons['Remove from Recents'].isEnabled()
    assert d.table.item(d.table.currentRow(),2).text()=='Open · not in Recents'
    d.close();w.close();app.processEvents()


def test_trash_current_project_confirms_closes_and_preserves_media(tmp_path,monkeypatch):
    app,w,rows,other,d,stored=setup_manager(tmp_path,monkeypatch);path=w.p.path;old=w.p
    media=Path(w.p.get('program')['path']);media_hash=hashlib.sha256(media.read_bytes()).hexdigest();before=path.read_bytes()
    select(d,path);questions=[]
    monkeypatch.setattr(QMessageBox,'question',lambda *args:questions.append(args) or QMessageBox.No)
    d.trash_selected();assert path.exists() and w.p is old and questions[0][-1]==QMessageBox.No
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Yes)
    trash=tmp_path/'test-trash';trash.mkdir()
    def move(file):
        assert w.p is None
        with pytest.raises(sqlite3.ProgrammingError):old.db.execute('SELECT 1')
        target=trash/Path(file).name;Path(file).rename(target);return True,str(target)
    monkeypatch.setattr('cueatlas.projects.QFile.moveToTrash',move)
    d.trash_selected()
    assert not path.exists() and (trash/path.name).read_bytes()==before
    assert hashlib.sha256(media.read_bytes()).hexdigest()==media_hash and other.exists()
    assert str(path) not in w.recent and w.p is None and not w.export_button.isEnabled()
    assert w.cue_table.rowCount()==0 and w.reference_table.rowCount()==0 and w.timeline.duration==0
    assert not w.undo_action.isEnabled() and not w.redo_action.isEnabled()
    d.close();w.close();app.processEvents()


def test_trash_failure_reopens_project_and_keeps_recent(tmp_path,monkeypatch):
    app,w,rows,other,d,stored=setup_manager(tmp_path,monkeypatch);path=w.p.path;state=w.p._edit_state();select(d,path)
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Yes)
    errors=[];monkeypatch.setattr(QMessageBox,'warning',lambda *args:errors.append(args))
    monkeypatch.setattr('cueatlas.projects.QFile.moveToTrash',lambda path:(False,''))
    d.trash_selected()
    assert path.exists() and w.p.path==path and w.p._edit_state()==state and str(path) in w.recent
    assert errors and 'original location' in errors[0][2]
    d.close();w.close();app.processEvents()


def test_trash_inactive_project_keeps_current_open(tmp_path,monkeypatch):
    app,w,rows,other,d,stored=setup_manager(tmp_path,monkeypatch);current=w.p;state=current._edit_state();select(d,other)
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Yes)
    target=tmp_path/'trashed.cueatlas'
    def move(path):Path(path).rename(target);return True,str(target)
    monkeypatch.setattr('cueatlas.projects.QFile.moveToTrash',move)
    d.trash_selected()
    assert not other.exists() and target.exists() and w.p is current and w.p._edit_state()==state
    assert str(other) not in w.recent
    d.close();w.close();app.processEvents()


def test_add_open_rename_and_backup(tmp_path,monkeypatch):
    app,w,rows,other,d,stored=setup_manager(tmp_path,monkeypatch)
    third=tmp_path/'third.cueatlas';p=Project(third,True,'Third');p.close()
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *args:(str(third),''))
    d.add_project();assert str(third) in w.recent and w.p.path!=third
    select(d,third);monkeypatch.setattr(QInputDialog,'getText',lambda *args,**kwargs:('Renamed third',True))
    d.rename_selected();renamed=tmp_path/'Renamed third.cueatlas';assert not third.exists() and project_info(renamed)['name']=='Renamed third'
    backup=tmp_path/'backup.cueatlas';monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(backup),''))
    d.backup_selected();assert backup.exists() and project_info(backup)['name']=='backup' and str(backup) in w.recent
    select(d,renamed);d.open_selected();assert w.p.path==renamed and w.heading.text()=='Renamed third'
    # Renaming the open project also renames the database file.
    d=ProjectManager(w);select(d,renamed)
    monkeypatch.setattr(QInputDialog,'getText',lambda *args,**kwargs:('Open project renamed',True))
    d.rename_selected();assert w.heading.text()=='Open project renamed' and w.p.path==tmp_path/'Open project renamed.cueatlas'
    d.grab().save('/private/tmp/cueatlas-project-manager.png')
    d.close();w.close();app.processEvents()
