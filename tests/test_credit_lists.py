from cueatlas.metadata import parse_parties
from cueatlas.enrichment import party_credits
from cueatlas.metadata_ui import CreditTextDialog
from cueatlas.gui import MetadataDialog
from test_timeline import open_window

COMPOSERS='Tamia Carter, Johnny Goldstein, Henry Smithson, Derrick Carrington Gray, Theron Makiel Thomas'
PUBLISHERS='Flo Milli Music (BMI), Concord Copyrights (BMI), 94 Sounds Worldwide (BMI), These are Pulse Songs (BMI), Johnny Goldstein Publishing Designee (BMI), Sony/ATV Songs LLC (BMI), Artist 101 Publishing Group (BMI), Derrick Carrington Gray Publishing Designee (BMI), Songs of Kobalt Music Publishing (BMI), Headbangers Publishing (SACEM/BIEM), Because Editions (SACEM), Concord Sounds, Thomasstarting5 (ASCAP)'


def test_exact_reported_lists_preserve_names_and_affiliations():
    writers=parse_parties(COMPOSERS,'composer');publishers=parse_parties(PUBLISHERS,'publisher')
    assert len(writers)==5 and len(publishers)==13
    assert writers[0]['name']=='Tamia Carter' and writers[-1]['name']=='Theron Makiel Thomas'
    assert publishers[5]['name']=='Sony/ATV Songs LLC' and publishers[5]['pro']=='BMI'
    assert publishers[9]['name']=='Headbangers Publishing' and publishers[9]['pro']=='SACEM/BIEM'
    assert publishers[11]['name']=='Concord Sounds' and publishers[11]['pro']==''
    assert all(p['share_percent'] is None for p in writers+publishers)
    credits=party_credits(writers+publishers)
    assert parse_parties(credits['composer'],'composer')==writers
    assert parse_parties(credits['publisher'],'publisher')==publishers


def test_boundaries_brackets_quotes_and_legacy_shares():
    parties=parse_parties('"Smith, John" (PRS); Sony/ATV (BMI)\nHeadbangers (SACEM/BIEM)','publisher')
    assert [p['name'] for p in parties]==['Smith, John','Sony/ATV','Headbangers']
    assert [p['share_percent'] for p in parse_parties('Writer One (BMI) 50%/Writer Two (ASCAP) 50%','composer')]==[50,50]
    assert parse_parties('Smith, John [PRS]','composer')[0]['name']=='Smith, John'


def test_credit_preview_cancel_and_metadata_save(tmp_path,monkeypatch):
    app,w,_=open_window(tmp_path)
    try:
        track=w.p.tracks()[0];original=track['metadata']
        d=MetadataDialog(track,w)
        def apply_preview(dialog):
            dialog.composers.setPlainText(COMPOSERS);dialog.publishers.setPlainText(PUBLISHERS);dialog.preview()
            assert len(dialog.parties)==18 and dialog.use.isEnabled()
            dialog.composers.setPlainText(COMPOSERS+' ');assert not dialog.use.isEnabled()
            dialog.preview();return 1
        monkeypatch.setattr(CreditTextDialog,'exec',apply_preview)
        d.parties_editor.paste_credits();assert len(d.parties_editor.values())==18
        assert w.p.tracks()[0]['metadata']==original
        d.accept();assert len(d.metadata['parties'])==18
        assert 'Sony/ATV Songs LLC (BMI)' in d.metadata['publisher']
        w.p.update_metadata(track['id'],d.metadata)
        reopened=MetadataDialog(w.p.tracks()[0],w)
        assert len(reopened.parties_editor.values())==18
        monkeypatch.setattr(CreditTextDialog,'exec',lambda dialog:0)
        reopened.parties_editor.paste_credits();assert len(reopened.parties_editor.values())==18
        reopened.close();d.close()
    finally:w.close();app.processEvents()
