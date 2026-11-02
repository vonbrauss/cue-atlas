import pytest
from cueatlas.project import Project,cue
from cueatlas.engine import import_library,analyze,import_files
from cueatlas.audio import Cancelled,SR
from scipy.io.wavfile import write
from test_core import music


def test_library_import_preserves_metadata_fingerprints_and_projects(tmp_path):
    source=Project(tmp_path/'source.cueatlas',True,'Source')
    target=Project(tmp_path/'target.cueatlas',True,'Target')
    media=tmp_path/'ref.wav';media.write_bytes(b'fixture')
    meta={'title':'Licensed','license':'License 42','publisher':'Publisher','raw':{'custom':'value'}}
    original=source.save_track(media,8,meta,[(42,3),(43,4)])
    source.save_cues([cue(original,0,8)]);source.set('program',{'path':'source.wav'})
    before_source=source.path.read_bytes()
    program={'path':'target.wav','duration':10};target.set('program',program)
    rows=[cue(None,0,5),cue(None,5,10)];target.save_cues(rows)
    target.merge_cues([c['id'] for c in rows]);before_cues=target.cues();undo=target.get('undo_merge')
    settings=target.settings
    media.unlink()  # Imported fingerprints must work even with offline reference media.
    result=import_library(target.path,source.path)
    assert result['added']==1
    imported=target.tracks()[0];assert imported['id']!=original and imported['metadata']==meta
    assert [tuple(r) for r in target.db.execute('SELECT hash,frame FROM hashes ORDER BY hash')]==[(42,3),(43,4)]
    assert target.get('program')==program and target.cues()==before_cues
    assert target.get('undo_merge')==undo and target.settings==settings and target.get('name')=='target'
    assert source.path.read_bytes()==before_source
    target.update_metadata(imported['id'],meta|{'license':'Edited locally'})
    assert import_library(target.path,source.path)['skipped']==1
    assert target.tracks()[0]['metadata']['license']=='Edited locally'
    source.close();target.close()


def test_library_import_deduplicates_content_and_rolls_back_on_cancel(tmp_path):
    source=Project(tmp_path/'source.cueatlas',True,'Source');target=Project(tmp_path/'target.cueatlas',True,'Target')
    for i in range(2):
        f=tmp_path/f'{i}.wav';f.write_bytes(b'fixture')
        source.save_track(f,8,{'title':str(i),'_content_sha256':str(i)},[(42,i)])
    calls=[]
    def progress(*args):calls.append(args)
    with pytest.raises(Cancelled):
        import_library(target.path,source.path,progress=progress,cancel=lambda:len(calls)>1)
    assert not target.tracks() and not target.db.execute('SELECT * FROM hashes').fetchall()
    other=tmp_path/'same-content.wav';other.write_bytes(b'fixture')
    target.save_track(other,8,{'title':'Keep','_content_sha256':'0'},[(99,9)])
    result=import_library(target.path,source.path)
    assert result['added']==1 and result['skipped']==1
    assert len(target.tracks())==2
    with pytest.raises(ValueError,match='different project'):import_library(target.path,target.path)
    with pytest.raises(Exception):import_library(target.path,tmp_path/'absent.cueatlas')
    assert not (tmp_path/'absent.cueatlas').exists()
    source.close();target.close()


def test_imported_library_identifies_program_without_reindexing(tmp_path):
    source=Project(tmp_path/'source.cueatlas',True,'Source');target=Project(tmp_path/'target.cueatlas',True,'Target')
    reference=tmp_path/'ref.wav';write(reference,SR,music(441,8))
    import_files(source.path,[str(reference)])
    target.set('program',{'path':str(reference)})
    import_library(target.path,source.path);analyze(target.path)
    assert any(c['track']==target.tracks()[0]['id'] for c in target.cues())
    source.close();target.close()
