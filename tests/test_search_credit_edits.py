from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from cueatlas.gui import MetadataDialog
from cueatlas.enrichment import party_credits
from test_timeline import open_window


def test_search_does_no_disk_or_database_work_and_refreshes_edits(tmp_path,monkeypatch):
    app,w,_=open_window(tmp_path)
    try:
        with monkeypatch.context() as patch:
            def unexpected(*args,**kwargs):raise AssertionError('Search performed expensive library work')
            patch.setattr(w.p,'tracks',unexpected)
            patch.setattr('cueatlas.gui.duplicate_report',unexpected)
            patch.setattr(Path,'stat',unexpected)
            w.reference_search.setText('neon');assert len(w.track_rows)==1
            w.reference_search.setText('absent');assert not w.track_rows
            w.reference_search.clear();assert len(w.track_rows)==1
            w.sort_table('reference',0)
        track=w.p.tracks()[0]
        w.p.update_metadata(track['id'],track['metadata']|{'publisher':'New Publishing'})
        w.refresh();w.reference_search.setText('new publishing');assert len(w.track_rows)==1
    finally:w.close();app.processEvents()


def test_delete_credit_text_updates_parties_and_saved_export(tmp_path):
    app,w,_=open_window(tmp_path)
    try:
        track=w.p.tracks()[0]
        parties=[{'role':'composer','name':'Writer One','pro':'ASCAP','ipi':'00123','share_percent':50},
                 {'role':'composer','name':'Writer Two','pro':'BMI','ipi':'00456','share_percent':50},
                 {'role':'publisher','name':'Sony/ATV','pro':'BMI','ipi':'00789','share_percent':100}]
        track['metadata'].update(party_credits(parties),parties=parties)
        d=MetadataDialog(track,w)
        d.inputs['composer'].selectAll();QTest.keyClick(d.inputs['composer'],Qt.Key_Backspace)
        assert d.inputs['composer'].text()==''
        assert d.sync_credit_fields()
        assert [p['name'] for p in d.parties_editor.values()]==['Sony/ATV']
        d.inputs['publisher'].selectAll();QTest.keyClick(d.inputs['publisher'],Qt.Key_Delete)
        d.accept();assert d.metadata['parties']==[] and d.metadata['composer']==d.metadata['publisher']==d.metadata['pro']==''
        w.p.update_metadata(track['id'],d.metadata)
        reopened=MetadataDialog(w.p.tracks()[0],w);assert reopened.parties_editor.values()==[]
        assert reopened.inputs['composer'].text()==reopened.inputs['publisher'].text()==''
        d.close();reopened.close()
        d=MetadataDialog(track,w);d.inputs['composer'].setText('Writer One');d.accept()
        saved=d.metadata['parties'];assert len(saved)==2
        writer=next(p for p in saved if p['role']=='composer');assert writer['ipi']=='00123' and writer['share_percent']==50
        assert next(p for p in saved if p['role']=='publisher')['ipi']=='00789'
        d.close()
    finally:w.close();app.processEvents()
