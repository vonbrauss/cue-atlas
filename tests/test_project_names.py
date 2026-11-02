import json
import sqlite3
from pathlib import Path
import pytest
from PySide6.QtWidgets import QInputDialog
from cueatlas.project import Project
from cueatlas.projects import ProjectManager,project_info
from test_timeline import fixture_project,open_window


def test_filename_wins_creation_external_rename_and_backup(tmp_path):
    path=tmp_path/'Final show.cueatlas';p=Project(path,True,'A different typed name')
    assert p.get('name')=='Final show';p.close()
    external=tmp_path/'Final show v2.cueatlas';path.rename(external)
    assert project_info(external)['name']=='Final show v2'
    p=Project(external)
    assert p.get('name')=='Final show v2'
    assert json.loads(p.db.execute("SELECT value FROM info WHERE key='name'").fetchone()[0])=='Final show v2'
    backup=tmp_path/'Delivery backup.cueatlas';p.backup(backup);p.close()
    p=Project(backup);assert p.get('name')=='Delivery backup';p.close()


def test_rename_preserves_cues_history_licensing_media_and_reopens_connection(tmp_path):
    p,rows=fixture_project(tmp_path);p.set_cues_excluded([rows[0]['id']]);p.trim_cue(rows[1]['id'],3,5)
    before=p._edit_state();history=p.edit_history();tracks=p.tracks();hashes=[tuple(row) for row in p.db.execute('SELECT * FROM hashes')]
    settings=p.settings;program=p.get('program');old=p.path;connection=p.db
    target=p.rename('New edit.cueatlas')
    assert target==tmp_path/'New edit.cueatlas' and target.exists() and not old.exists()
    assert p.get('name')=='New edit' and p.path==target
    with pytest.raises(sqlite3.ProgrammingError):connection.execute('SELECT 1')
    assert p._edit_state()==before and p.edit_history()==history and p.tracks()==tracks
    assert p.settings==settings and p.get('program')==program and Path(program['path']).exists()
    assert [tuple(row) for row in p.db.execute('SELECT * FROM hashes')]==hashes
    p.undo_edit();assert p.cues()==rows;p.redo_edit();assert p._edit_state()==before
    p.close();p=Project(target);assert p._edit_state()==before;p.close()


def test_rename_collision_invalid_and_filesystem_failure_keep_original(tmp_path,monkeypatch):
    p,rows=fixture_project(tmp_path);old=p.path;other=tmp_path/'Other.cueatlas'
    q=Project(other,True);q.close();other_bytes=other.read_bytes();before=old.read_bytes()
    for name in ['Other','../escape','..','', 'Bad/name', 'Bad\\name','Bad\x00name']:
        with pytest.raises(ValueError):p.rename(name)
        assert old.exists() and p.path==old and p.cues()==rows and other.read_bytes()==other_bytes
    def fail(*args):raise PermissionError('No write permission')
    monkeypatch.setattr(Project,'_move_without_replace',staticmethod(fail))
    with pytest.raises(PermissionError):p.rename('No access')
    assert old.exists() and old.read_bytes()==before and p.cues()==rows and p.path==old
    assert not (tmp_path/'No access.cueatlas').exists();p.close()


def test_case_only_rename(tmp_path):
    p=Project(tmp_path/'Scene A.cueatlas',True);target=p.rename('scene a')
    assert p.path.name=='scene a.cueatlas' and p.get('name')=='scene a'
    assert target.name in {item.name for item in tmp_path.iterdir()}
    p.close()


def test_finder_rename_of_open_project_updates_window_recents_and_manager(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);old=w.p.path;state=w.p._edit_state()
    w.recent=[str(old)];stored=[];monkeypatch.setattr(w.prefs,'setValue',lambda key,value:stored.append((key,value)))
    d=ProjectManager(w);d.show();app.processEvents()
    new=tmp_path/'Finder renamed.cueatlas';old.rename(new)
    # The same check is run by the one-second location timer.
    w.check_project_location();app.processEvents()
    assert w.p.path==new and w.heading.text()=='Finder renamed' and w.windowTitle()=='Finder renamed · Cue Atlas'
    assert w.recent==[str(new)] and str(old) not in w.recent and stored[-1]==('recent',[str(new)])
    assert w.p._edit_state()==state and d.rows[0]['path']==str(new)
    w.p.set('test_after_rename',True);assert w.p.get('test_after_rename')
    d.close();w.close();app.processEvents()


def test_main_project_rename_updates_actual_file_and_recents(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);old=w.p.path;w.recent=[str(old)]
    monkeypatch.setattr(w.prefs,'setValue',lambda *args:None)
    monkeypatch.setattr(QInputDialog,'getText',lambda *args,**kwargs:('App renamed',True))
    w.rename_project();target=tmp_path/'App renamed.cueatlas'
    assert not old.exists() and target.exists() and w.p.path==target and w.recent==[str(target)]
    assert w.heading.text()=='App renamed' and w.p.cues()==rows
    w.close();app.processEvents()


@pytest.mark.parametrize('case_only',[False,True])
def test_failed_metadata_update_rolls_file_rename_back(tmp_path,monkeypatch,case_only):
    p,rows=fixture_project(tmp_path);original=p.path
    def fail():raise OSError('Simulated database write failure')
    monkeypatch.setattr(p,'_store_name',fail)
    with pytest.raises(OSError,match='Simulated'):p.rename(original.stem.upper() if case_only else 'Another name')
    assert p.path==original and original.name in {item.name for item in tmp_path.iterdir()}
    assert p.cues()==rows
    p.set('still_editable',True);assert p.get('still_editable') is True
    p.close()
