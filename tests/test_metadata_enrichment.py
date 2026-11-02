import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import pytest
from PySide6.QtWidgets import QApplication,QDialog
from cueatlas.metadata import normalize,parse_parties
from cueatlas.enrichment import recovery_plan,enrichment_plan,apply_plan,validate_parties
from cueatlas.project import Project,cue
from cueatlas.export import export,export_reference_library,COLUMNS
from cueatlas.gui import MetadataDialog,Window


def test_nested_xml_and_provider_ids():
    raw={'TIT2':'In The Trap House','TCOM':'Andre Tavarez [BMI], Sebastian Robertson [BMI]',
         'TPUB':'Killer Tracks [BMI]','TALB':'Trap House 2','TOAL':'SBR073_006','TRCK':'6',
         'ICOP':'2017 https://universalproductionmusic.com',
         'iXML':'<BWFXML><STEINBERG><ATTR_LIST><ATTR><NAME>MediaLibrary</NAME><VALUE>Sonic Beat Records</VALUE></ATTR><ATTR><NAME>MediaAlbum</NAME><VALUE>Trap House 2</VALUE></ATTR></ATTR_LIST></STEINBERG></BWFXML>'}
    m=normalize(raw,'track.wav')
    assert m['library']=='Sonic Beat Records'
    assert m['album_title']=='Trap House 2' and m['catalog_code']=='SBR073'
    assert m['provider_track_id']=='SBR073_006'
    assert m['provider']=='Universal Production Music'
    assert m['pro']=='BMI' and len(m['parties'])==3
    assert m['raw']==raw


def test_credits_do_not_infer_composer_or_shares():
    m=normalize({'IART':'APM Music. Craig McConnell','INAM':'Real Homies Instrumental'},'CEZ_MAG_6110_01201_Real_Homies.wav')
    assert m['provider_track_id']=='CEZ_MAG_6110_01201'
    assert m['version']=='Instrumental'
    assert m['composer']=='' and m['parties']==[]
    parties=parse_parties('Wentworth Morris (ASCAP) 50%/David Young (BMI) 50%','composer')
    assert [p['share_percent'] for p in parties]==[50,50]
    assert [p['pro'] for p in parties]==['ASCAP','BMI']
    assert parse_parties('Smith, John [PRS]','composer')[0]['name']=='Smith, John'
    assert parse_parties('Unknown Writer','composer')[0]['share_percent'] is None


@pytest.fixture
def library(tmp_path):
    p=Project(tmp_path/'demo.cueatlas',True,'Demo')
    f=tmp_path/'reference.wav';f.write_bytes(b'reference')
    raw={'IART':'APM Music','INAM':'Original title','IPRD':'Bombastic Beatz (RLZ-0029)'}
    tid=p.save_track(f,120,{'title':'Edited title','composer':'Writer (BMI)',
                         'raw':raw,'_content_sha256':'keep'},[(123,1)])
    p.set('program',{'path':str(f),'duration':120});p.save_cues([cue(tid,0,10,title='Edited title')])
    try:yield p,tid
    finally:p.close()


def test_recovery_preserves_edits_and_works_offline(library,tmp_path):
    p,tid=library
    from pathlib import Path
    Path(p.tracks()[0]['path']).unlink()
    original=p.tracks()[0]['metadata'];cues=p.cues()
    plan=recovery_plan(p)
    assert plan[0]['metadata']['title']=='Edited title'
    assert plan[0]['metadata']['pro']=='BMI'
    assert plan[0]['metadata']['catalog_code']=='RLZ-0029'
    assert plan[0]['metadata']['parties'][0]['name']=='Writer'
    assert apply_plan(p,plan)==1
    assert p.cues()==cues
    assert p.db.execute('SELECT COUNT(*) FROM hashes').fetchone()[0]==1
    assert p.tracks()[0]['metadata']['raw']==original['raw']
    assert p.tracks()[0]['metadata']['_content_sha256']=='keep'
    assert recovery_plan(p)==[]
    assert p.tracks()[0]['metadata']['provenance'][0]['fields']==plan[0]['fields']


def test_json_matching_conflicts_and_transaction(library,tmp_path):
    p,tid=library;path=tmp_path/'enrichment.json'
    def write(entries):path.write_text(json.dumps({'tracks':entries}))
    write([{'reference_id':tid,'metadata':{'title':'Wrong title','isrc':'FRZPA2571920'}}])
    plan,skipped=enrichment_plan(p,path)
    assert not plan and 'conflicts' in skipped[0]
    write([{'metadata':{'title':'Edited title','isrc':'FRZPA2571920'}}])
    assert not enrichment_plan(p,path)[0]  # Never match on title alone.
    write([{'reference_id':tid,'metadata':{'isrc':'FRZPA2571920','source_url':'https://www.apmmusic.com/search'}}])
    plan,skipped=enrichment_plan(p,path);assert len(plan)==1 and not skipped
    assert 'isrc' not in p.tracks()[0]['metadata']
    apply_plan(p,plan)
    assert p.tracks()[0]['metadata']['isrc']=='FRZPA2571920'
    with pytest.raises(ValueError,match='changed'):apply_plan(p,plan)
    entry={'reference_id':tid,'metadata':{'iswc':'T123'}}
    write([entry,entry])
    with pytest.raises(ValueError,match='multiple entries'):enrichment_plan(p,path)


@pytest.mark.parametrize('party',[{'ipi':123},{'ipi':'123A'},{'share_percent':float('nan')},{'share_percent':101},{'share_percent':True}])
def test_invalid_party_values(party):
    with pytest.raises(ValueError):validate_parties([{'role':'composer','name':'Writer',**party}])


def test_structured_party_edit_and_exports(library,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    def unexpected_warning(*args):raise AssertionError(str(args[1:]))
    monkeypatch.setattr(QMessageBox,'warning',unexpected_warning)
    p,tid=library;app=QApplication.instance() or QApplication([])
    d=MetadataDialog(p.tracks()[0],None)
    assert not d.inputs['composer'].isReadOnly()
    d.parties_editor.table.item(0,3).setText('00535661740')
    d.parties_editor.table.item(0,4).setText('100')
    d.parties_editor.add({'role':'publisher','name':'Publisher','pro':'BMI','ipi':'00487402830','share_percent':100})
    d.accept();assert d.result()==QDialog.Accepted
    p.update_metadata(tid,d.metadata)
    assert d.metadata['publisher']=='Publisher (BMI) 100%'
    assert d.metadata['parties'][0]['ipi']=='00535661740'
    assert d.metadata['provenance'][-1]['status']=='user_edited'
    target=tmp_path/'references.json';export_reference_library(p,target)
    assert json.loads(target.read_text())['tracks'][0]['metadata']['parties']==d.metadata['parties']
    csv=tmp_path/'cues.csv';export(p,csv)
    import csv as csv_module
    rows=list(csv_module.reader(csv.open(encoding='utf-8-sig')))
    assert len(rows[0])==len(rows[1])==len(COLUMNS)
    assert json.loads(rows[1][COLUMNS.index('Rights Parties')])[0]['ipi']=='00535661740'
    d.show();app.processEvents();d.grab().save(str(tmp_path/'metadata-dialog.png'));d.close()


def test_provider_matching_and_structured_import(tmp_path):
    p=Project(tmp_path/'provider.cueatlas',True,'Provider')
    try:
        f=tmp_path/'ref.wav';f.write_bytes(b'ref')
        tid=p.save_track(f,10,{'title':'Title','provider':'APM Music','provider_track_id':'CEZ_MAG_6110_01201'},[])
        path=tmp_path/'credits.json'
        entry={'metadata':{'provider':'APM Music','provider_track_id':'CEZ_MAG_6110_01201',
            'parties':[{'role':'composer','name':'Vincent Leibovitz','pro':'SACEM','ipi':'00535661740','share_percent':100},
                       {'role':'publisher','name':'Cezame Metro Park','pro':'BMI','ipi':'00487402830','share_percent':100}]}}
        path.write_text(json.dumps({'tracks':[entry]}))
        plan,skipped=enrichment_plan(p,path);assert len(plan)==1 and not skipped
        apply_plan(p,plan)
        m=p.tracks()[0]['metadata'];assert m['composer']=='Vincent Leibovitz (SACEM) 100%'
        assert m['pro']=='SACEM; BMI'
    finally:p.close()


def test_enrichment_fills_party_ipi_without_replacing_shares(library,tmp_path):
    p,tid=library;apply_plan(p,recovery_plan(p))
    path=tmp_path/'ipi.json'
    path.write_text(json.dumps({'tracks':[{'reference_id':tid,'metadata':{
        'parties':[{'role':'composer','name':'Writer','pro':'BMI','ipi':'00012345678','share_percent':100}]}}]}))
    plan,skipped=enrichment_plan(p,path)
    assert len(plan)==1 and not skipped
    apply_plan(p,plan)
    party=p.tracks()[0]['metadata']['parties'][0]
    assert party['ipi']=='00012345678' and party['share_percent']==100
    path.write_text(json.dumps({'tracks':[{'reference_id':tid,'metadata':{
        'parties':[{'role':'composer','name':'Writer','pro':'BMI','ipi':'00099999999','share_percent':50}]}}]}))
    plan,skipped=enrichment_plan(p,path)
    assert not plan and skipped
    assert p.tracks()[0]['metadata']['parties'][0]==party


def test_bulk_recovery_preview_cancel_and_apply(library,monkeypatch):
    from cueatlas.metadata_ui import MetadataPreview
    p,tid=library;app=QApplication.instance() or QApplication([])
    w=Window()
    def unexpected_error(message):raise AssertionError(message)
    monkeypatch.setattr(w,'error',unexpected_error)
    w.load(str(p.path));before=w.p.tracks()[0]['metadata']
    try:
        monkeypatch.setattr(MetadataPreview,'exec',lambda self:QDialog.Rejected)
        w.recovermetadata_action.trigger()
        assert w.p.tracks()[0]['metadata']==before
        monkeypatch.setattr(MetadataPreview,'exec',lambda self:QDialog.Accepted)
        w.recovermetadata_action.trigger()
        assert w.p.tracks()[0]['metadata']['pro']=='BMI'
        assert '1 references' in w.status.text()
    finally:w.close();app.processEvents()
