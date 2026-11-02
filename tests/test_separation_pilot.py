import sqlite3
import pytest
from experiments.separation_pilot.compare import ReadOnlyProject,identify
from cueatlas import engine
from test_timeline import fixture_project


def test_pilot_reads_project_without_allowing_database_writes(tmp_path):
    p,rows=fixture_project(tmp_path);path=p.path;p.close()
    original=path.read_bytes();pilot=ReadOnlyProject(path)
    assert pilot.cues()==rows and pilot.get('name')==path.stem and pilot.settings
    with pytest.raises(sqlite3.OperationalError,match='readonly'):
        pilot.db.execute('DELETE FROM cues')
    pilot.close();assert path.read_bytes()==original


def test_pilot_uses_excerpt_origin_and_restores_engine_on_failure(tmp_path,monkeypatch):
    p,rows=fixture_project(tmp_path);path=p.path;media=tmp_path/'program.wav';p.close()
    actual_factory=engine.Project
    sample={'cue':rows[1],'duration':3.}
    def fail(project_path,cue_id):
        pilot=engine.Project(project_path)
        try:
            assert pilot.cues()[0]['start']==0 and pilot.cues()[0]['end']==3
            assert pilot.get('program')['path']==str(media)
            assert pilot.get('program')['size']==media.stat().st_size
            raise ValueError('Test decoder failure')
        finally:pilot.close()
    monkeypatch.setattr(engine,'identify_cue',fail)
    with pytest.raises(ValueError,match='Test decoder failure'):identify(path,sample,media)
    assert engine.Project is actual_factory
    pilot=ReadOnlyProject(path);assert pilot.cues()==rows;pilot.close()
