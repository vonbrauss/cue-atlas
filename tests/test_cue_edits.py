import csv
import numpy as np
import pytest
from scipy.io.wavfile import write
from cueatlas.project import Project,cue
from cueatlas.coverage import ensure_coverage,covered_seconds
from cueatlas.audio import SR,decode_program,source_duration
from cueatlas.engine import analyze,repair_coverage,import_files
from cueatlas.export import export
from test_core import music


def test_every_gap_and_tail_is_represented():
    found=[cue('a',.1,6),cue('b',6.05,9.9)]
    full=ensure_coverage(found,10)
    assert [(c['start'],c['end']) for c in full if c['track'] is None]==[(0,.1),(6,6.05),(9.9,10)]
    assert covered_seconds(full,10)==pytest.approx(10)
    assert full[-1]['end']==10
    assert ensure_coverage([],10)[0]['end']==10
    assert ensure_coverage(full,10)==full


def test_overlaps_do_not_inflate_coverage_or_create_false_gaps():
    full=ensure_coverage([cue('a',0,7),cue('b',5,9)],10)
    assert covered_seconds(full,10)==10
    assert covered_seconds([c for c in full if c['track']],10)==9
    assert [(c['start'],c['end']) for c in full if not c['track']]==[(9,10)]


def make_project(tmp_path):
    p=Project(tmp_path/'edit.cueatlas',True,'Editing')
    f=tmp_path/'reference.wav';write(f,SR,music(6,6))
    tid=p.save_track(f,6,{'title':'Reference A','publisher':'Publisher A','license':'License 42','raw':{}},[])
    p.set('program',{'path':str(f),'duration':6})
    return p,tid


def test_known_unknown_merge_confirm_metadata_persistence_undo(tmp_path):
    p,tid=make_project(tmp_path)
    a=cue(tid,0,3,87,'Reference A',note='Original note');b=cue(None,3,6,title='Unknown 001')
    p.save_cues([a,b])
    with pytest.raises(ValueError,match='Confirm'):p.merge_cues([a['id'],b['id']],tid)
    assert len(p.cues())==2
    merged=p.merge_cues([a['id'],b['id']],tid,reviewed=True,note='Checked by ear')
    assert len(p.cues())==1 and merged['start']==0 and merged['end']==6
    assert merged['status']=='Reviewed' and merged['confidence']==0
    assert 'Original note' in merged['note'] and 'Checked by ear' in merged['note']
    out=tmp_path/'merged.csv';export(p,out)
    with out.open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    assert rows[0]['License']=='License 42' and rows[0]['Publisher']=='Publisher A'
    assert float(rows[0]['Duration Seconds'])==6
    path=p.path;p.close();p=Project(path)
    assert p.cues()[0]['id']==merged['id'];p.undo_merge();assert p.cues()==[a,b]
    p.close()


def test_nonadjoining_merge_is_rejected_even_when_filtered(tmp_path):
    p,tid=make_project(tmp_path)
    a,b,c=cue(tid,0,2),cue(None,2,4),cue(tid,4,6)
    p.save_cues([a,b,c])
    with pytest.raises(ValueError,match='adjoining'):p.merge_cues([a['id'],c['id']],tid,reviewed=True)
    assert len(p.cues())==3;p.close()


def test_unknown_merge_and_later_edit_clear_undo(tmp_path):
    p,_=make_project(tmp_path);a,b=cue(None,0,3),cue(None,3,6);p.save_cues([a,b])
    p.merge_cues([a['id'],b['id']],title='Unidentified bed')
    assert p.cues()[0]['title']=='Unidentified bed' and p.cues()[0]['status']=='Unknown'
    p.save_cues(p.cues());assert p.get('undo_merge') is None;p.close()


def test_manual_boundary_edit_and_deletion_leave_empty_space(tmp_path):
    p,tid=make_project(tmp_path);p.save_cues([cue(tid,0,6)])
    edited=p.cues()[0];edited.update(start=1,end=5);p.save_cues([edited])
    assert p.cues()==[edited] and covered_seconds(p.cues(),6)==4
    p.save_cues([]);assert not p.cues()
    p.undo_edit();assert p.cues()==[edited]
    p.redo_edit();assert not p.cues()
    p.close()


def test_analysis_matches_first_sixty_percent_but_covers_entire_source(tmp_path):
    p=Project(tmp_path/'sixty.cueatlas',True,'Sixty percent')
    reference=tmp_path/'known.wav';write(reference,SR,music(222,8));import_files(p.path,[str(reference)])
    program=tmp_path/'program.wav';write(program,SR,np.concatenate([music(222,8)[:6*SR],music(777,4)]))
    p.set('program',{'path':str(program)})
    # Legacy setting must not hide even small uncovered intervals.
    p.set('settings',p.settings|{'unknown_min':1000})
    analyze(p.path);cues=p.cues()
    assert covered_seconds(cues,10)==pytest.approx(10)
    assert cues[0]['start']==0 and max(c['end'] for c in cues)==10
    assert any(not c['track'] and c['start']<6.5 and c['end']==10 for c in cues)
    p.close()


def test_repair_extends_legacy_project_without_losing_reviewed_rows(tmp_path):
    p,tid=make_project(tmp_path)
    # Emulate an old project whose stored duration and final cue stop at 60%.
    program=p.get('program');program['duration']=3.6;p.set('program',program)
    existing=cue(tid,0,3.6,title='Reference A',status='Reviewed',note='Keep my review')
    p.save_cues([existing]);result=repair_coverage(p.path)
    assert result['repaired'] and result['added']==1
    assert p.cues()[0]==existing
    assert p.cues()[-1]['end']==6 and covered_seconds(p.cues(),6)==6
    assert p.get('program')['duration']==6;p.close()


def test_truncated_wav_is_not_silently_accepted(tmp_path):
    p,tid=make_project(tmp_path)
    truncated=tmp_path/'truncated.wav';write(truncated,SR,np.zeros(10*SR,dtype=np.int16))
    with truncated.open('r+b') as f:f.truncate(44+6*SR*2)
    assert source_duration(truncated)==10
    p.set('program',{'path':str(truncated),'duration':10})
    before=cue(tid,0,10,title='Preserve existing cues');p.save_cues([before])
    with pytest.raises(ValueError,match='Incomplete audio decode'):analyze(p.path)
    assert p.cues()==[before];p.close()
