import json

from PySide6.QtWidgets import QApplication, QFileDialog

from cueatlas.export import export_reference_library
from cueatlas.gui import Window
from cueatlas.metadata import FIELDS
from cueatlas.project import Project


def test_library_export_includes_unused_offline_references(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    project_path=tmp_path/'library.cueatlas'
    p=Project(project_path,True,'Library')
    source=tmp_path/'CEZ_MAG_6110_01201.wav'
    source.write_bytes(b'reference')
    metadata={'title':'Real Homies Instrumental','composer':'Vincent Théo Leibovitz',
              'publisher':'Cezame Metro Park','isrc':'FRZPA2571920',
              'raw':{'IART':'APM Music','ICMT':'Instrumental version. '},
              '_content_sha256':'internal fingerprint'}
    tid=p.save_track(source,123.5,metadata,[])
    other=tmp_path/'other.wav';other.write_bytes(b'other')
    p.save_track(other,10,{'title':'Other'},[])
    p.close();source.unlink();other.unlink()
    w=Window()
    assert not w.exportlibrary_action.isEnabled()
    w.load(str(project_path))
    target=tmp_path/'export'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a: (str(target),'JSON (*.json)'))
    try:
        assert w.exportlibrary_action.isEnabled()
        w.exportlibrary_action.trigger()
        data=json.loads(target.with_suffix('.json').read_text(encoding='utf-8'))
        assert data['schema_version']==1
        assert len(data['tracks'])==2
        track=next(t for t in data['tracks'] if t['reference_id']==tid)
        assert track['reference_file']==str(source)
        assert track['duration_seconds']==123.5
        assert track['metadata']=={**dict.fromkeys(FIELDS,''),**{k:v for k,v in metadata.items() if not k.startswith('_')}}
        assert not w.p.cues()
        assert w.p.tracks()[0]['metadata']==metadata
        monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a: ('',''))
        w.export_library_metadata()
    finally:
        w.close();app.processEvents()


def test_empty_library_export(tmp_path):
    p=Project(tmp_path/'empty.cueatlas',True,'Empty')
    try:
        target=tmp_path/'empty.json'
        assert export_reference_library(p,target)==0
        assert json.loads(target.read_text())['tracks']==[]
    finally:
        p.close()
