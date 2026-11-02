import csv
from copy import deepcopy
import json
from pathlib import Path
import pytest
from cueatlas.project import Project,cue
from cueatlas.export import export_reference_library,export
from cueatlas.json_metadata import metadata_import_plan
from cueatlas.enrichment import apply_plan
from cueatlas.workflow import list_snapshots


@pytest.fixture
def library(tmp_path):
    p=Project(tmp_path/'roundtrip.cueatlas',True);media=tmp_path/'ref.wav';media.write_bytes(b'reference')
    tid=p.save_track(media,10,{'title':'Song','composer':'Original writer','publisher':'Old publisher',
        'license':'Old license','raw':{'IPUB':'Old publisher'},'_content_sha256':'preserved'},[(123,2)])
    p.set('program',{'path':str(media),'duration':10});p.save_cues([cue(tid,0,5,title='Song'),cue(tid,5,10,title='Song')])
    path=tmp_path/'metadata.json';export_reference_library(p,path)
    try:yield p,tid,path
    finally:p.close()


def test_roundtrip_replaces_clears_and_preserves_cues_hashes_raw(library,tmp_path):
    p,tid,path=library;before=p.cues();data=json.loads(path.read_text());entry=data['tracks'][0]
    assert metadata_import_plan(p,path)==([],[])
    entry['metadata'].update(license='License 2026-001',publisher='New publisher',copyright='',title='Corrected song')
    entry['metadata']['raw']={'IPUB':'do not replace'};entry['metadata']['_content_sha256']='do not replace'
    path.write_text(json.dumps(data));plan,skipped=metadata_import_plan(p,path)
    assert len(plan)==1 and not skipped;assert p.tracks()[0]['metadata']['license']=='Old license'
    apply_plan(p,plan);m=p.tracks()[0]['metadata']
    assert m['publisher']=='New publisher' and m['license']=='License 2026-001'
    assert m['raw']=={'IPUB':'Old publisher'} and m['_content_sha256']=='preserved'
    assert m['provenance'][-1]['source'].startswith('JSON edit:')
    assert p.cues()==before and tuple(p.db.execute('SELECT hash,frame FROM hashes').fetchone())==(123,2)
    assert list_snapshots(p)
    output=tmp_path/'cues.csv';export(p,output)
    with output.open(encoding='utf-8-sig') as file:rows=list(csv.DictReader(file))
    assert len(rows)==2 and all(r['License']=='License 2026-001' and r['Track']=='Corrected song' for r in rows)


def test_baseline_leaves_unedited_fields_and_blocks_stale_changes(library):
    p,tid,path=library;data=json.loads(path.read_text())
    current=deepcopy(p.tracks()[0]['metadata']);current['license']='Changed in project';p.update_metadata(tid,current)
    data['tracks'][0]['metadata']['source_url']='https://example.com/song';path.write_text(json.dumps(data))
    plan,skipped=metadata_import_plan(p,path);assert len(plan)==1 and not skipped
    apply_plan(p,plan);assert p.tracks()[0]['metadata']['license']=='Changed in project'
    data['tracks'][0]['metadata']['license']='Changed externally';path.write_text(json.dumps(data))
    plan,skipped=metadata_import_plan(p,path);assert not plan and 'since export' in skipped[0]


def test_patch_omitted_fields_preserved_blank_clears_and_unknown_id_skipped(library):
    p,tid,path=library
    path.write_text(json.dumps({'tracks':[{'reference_id':tid,'metadata':{'license':''}}]}))
    plan,skipped=metadata_import_plan(p,path);apply_plan(p,plan)
    assert p.tracks()[0]['metadata']['license']=='' and p.tracks()[0]['metadata']['publisher']=='Old publisher'
    path.write_text(json.dumps({'tracks':[{'reference_id':'missing','reference_file':p.tracks()[0]['path'],'metadata':{'publisher':'Wrong'}}]}))
    assert not metadata_import_plan(p,path)[0]  # Stale IDs do not fall back to a different identity.
    path.write_text(json.dumps({'tracks':[{'metadata':{'title':'Song','license':'Wrong'}}]}))
    assert not metadata_import_plan(p,path)[0]
    path.write_text(json.dumps({'tracks':[{'reference_file':p.tracks()[0]['path'],'metadata':{'license':'Path matched'}}]}))
    assert len(metadata_import_plan(p,path)[0])==1


def test_parties_edit_resummarizes_credits_and_preserves_zero_ipi(library):
    p,tid,path=library;export_reference_library(p,path);data=json.loads(path.read_text())
    data['tracks'][0]['metadata']['parties']=[{'role':'composer','name':'New writer','pro':'BMI','ipi':'00012345678','share_percent':100},
        {'role':'publisher','name':'New publisher','pro':'ASCAP','ipi':'00000000123','share_percent':100}]
    path.write_text(json.dumps(data));plan,skipped=metadata_import_plan(p,path);assert len(plan)==1 and not skipped
    apply_plan(p,plan);m=p.tracks()[0]['metadata']
    assert m['composer']=='New writer (BMI) 100%' and m['publisher']=='New publisher (ASCAP) 100%'
    assert m['parties'][0]['ipi']=='00012345678'
    export_reference_library(p,path);assert metadata_import_plan(p,path)==([],[])
    data=json.loads(path.read_text());data['tracks'][0]['metadata']['parties'][0]['pro']='PRS'
    path.write_text(json.dumps(data));plan,skipped=metadata_import_plan(p,path);assert len(plan)==1 and not skipped


@pytest.mark.parametrize('document',[
    {'schema_version':2,'tracks':[]}, {'tracks':[{'metadata':{'license':None}}]},
    {'tracks':[{'metadata':{'parties':[{'role':'composer','name':'A','ipi':123}]}}]},
    {'tracks':[{'metadata':{'parties':[{'role':'composer','name':'A','share_percent':101}]}}]},
])
def test_bad_json_rejected_without_changes(library,document):
    p,tid,path=library;before=p.tracks();path.write_text(json.dumps(document))
    with pytest.raises(ValueError):metadata_import_plan(p,path)
    assert p.tracks()==before


def test_duplicate_entries_stale_preview_and_fill_mode(library):
    p,tid,path=library;entry={'reference_id':tid,'metadata':{'license':'New license'}}
    path.write_text(json.dumps({'tracks':[entry,entry]}))
    with pytest.raises(ValueError,match='multiple'):metadata_import_plan(p,path)
    path.write_text(json.dumps({'tracks':[entry]}));plan,skipped=metadata_import_plan(p,path,'fill');assert not plan and skipped
    plan,skipped=metadata_import_plan(p,path);p.update_metadata(tid,p.tracks()[0]['metadata']|{'artist':'New artist'})
    with pytest.raises(ValueError,match='changed'):apply_plan(p,plan)


def test_json_import_ui_cancel_preview_and_apply(library,monkeypatch):
    from PySide6.QtWidgets import QApplication,QDialog,QFileDialog
    from cueatlas.gui import Window
    from cueatlas.metadata_ui import MetadataImportDialog,MetadataPreview
    p,tid,path=library;app=QApplication.instance() or QApplication([]);w=Window();w.load(str(p.path))
    try:
        data=json.loads(path.read_text());data['tracks'][0]['metadata']['license']='External edit';path.write_text(json.dumps(data))
        monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *args:(str(path),''))
        monkeypatch.setattr(MetadataImportDialog,'exec',lambda self:QDialog.Accepted)
        monkeypatch.setattr(MetadataPreview,'exec',lambda self:QDialog.Rejected)
        w.import_library_metadata();assert p.tracks()[0]['metadata']['license']=='Old license'
        monkeypatch.setattr(MetadataPreview,'exec',lambda self:QDialog.Accepted)
        w.import_library_metadata();assert p.tracks()[0]['metadata']['license']=='External edit'
    finally:w.close();app.processEvents()
