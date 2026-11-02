import csv
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import pytest
from cueatlas.project import Project,cue
from cueatlas.workflow import (review_queue,validate_cues,create_snapshot,list_snapshots,
    restore_snapshot,save_marker,duplicate_report,create_handoff)
from cueatlas.audio import Cancelled
from test_timeline import fixture_project


def test_review_queue_confirmation_threshold_and_exclusions(tmp_path):
    p,rows=fixture_project(tmp_path);track=rows[1]['track']
    weak=cue(track,1,2,30,'Weak');strong=cue(track,3,4,90,'Unreviewed')
    p.save_cues([*rows,weak,strong]);p.set_cues_excluded([rows[2]['id']])
    queue=review_queue(p)
    assert {c['id'] for c in queue}=={rows[0]['id'],weak['id'],strong['id']}
    assert 'Weak match' in next(c for c in queue if c['id']==weak['id'])['reasons']
    assert 'Weak match' not in next(c for c in review_queue(p,20) if c['id']==weak['id'])['reasons']
    weak['status']='Reviewed';p.save_cues([rows[0],rows[1],rows[2],weak,strong])
    assert weak['id'] not in {c['id'] for c in review_queue(p)}
    p.close()


def test_validation_nested_overlaps_metadata_timing_and_excluded(tmp_path):
    p,rows=fixture_project(tmp_path);track=rows[1]['track']
    a=cue(track,0,10,90,'Long');b=cue(track,2,3,90,'Short',status='Reviewed')
    c=cue(track,4,5,90,'Also inside',status='Reviewed');bad=cue(None,-1,1,title='Invalid')
    p.save_cues([a,b,c,bad]);issues=validate_cues(p)
    assert len([i for i in issues if i['code']=='overlap'])==2
    assert {i['code'] for i in issues}>={'composer','publisher','unreviewed','timing'}
    assert next(i for i in issues if i['code']=='timing')['severity']=='error'
    p.set_cues_excluded([bad['id'],a['id']]);assert not any(i['code'] in ('timing','overlap') for i in validate_cues(p))
    p.close()


def test_automatic_snapshots_restore_and_preserve_current_state(tmp_path):
    p,rows=fixture_project(tmp_path);p.snapshot('Before replacing analysis',force=True);p.trim_cue(rows[1]['id'],3,5)
    snapshots=list_snapshots(p);assert snapshots and snapshots[0]['reason']=='Before replacing analysis'
    saved=p.cues();restore_snapshot(p,snapshots[0]['path']);assert p.cues()==rows
    newest=list_snapshots(p)[0];assert newest['reason']=='Before restoring a recovery point'
    with sqlite3.connect(newest['path']) as db:
        assert [(r[0],r[1]) for r in db.execute('SELECT start,end FROM cues ORDER BY start')]==[(c['start'],c['end']) for c in saved]
    with pytest.raises(ValueError):restore_snapshot(p,tmp_path/'somewhere-else.cueatlas')
    for i in range(21):create_snapshot(p,f'Manual {i}',force=True)
    assert len(list_snapshots(p))==20
    path=p.path;p.close();p=Project(path);assert len(list_snapshots(p))==20;p.close()


def test_snapshot_failure_prevents_destructive_edit(tmp_path,monkeypatch):
    p,rows=fixture_project(tmp_path)
    def fail(path):raise OSError('Disk full')
    monkeypatch.setattr(p,'backup',fail)
    with pytest.raises(ValueError,match='Disk full'):p.snapshot('Before replacing analysis',force=True)
    assert p.cues()==rows;p.close()


def test_markers_persist_and_validate_position(tmp_path):
    p,rows=fixture_project(tmp_path);m=save_marker(p,3.25,'Check alternate mix')
    save_marker(p,4,'Music under dialogue',m['id']);assert len(p.get('markers'))==1
    with pytest.raises(ValueError):save_marker(p,13,'Outside')
    with pytest.raises(ValueError):save_marker(p,4,'  ')
    path=p.path;p.close();p=Project(path);assert p.get('markers')[0]['position']==4;p.close()


def test_duplicate_report_distinguishes_checksum_and_possible_titles():
    def track(id,title,checksum):return {'id':id,'path':id+'.wav','metadata':{'title':title,'_content_sha256':checksum}}
    rows=[track('a','Our song (Main)','abc'),track('b','Our song (Instrumental)','def'),track('c','Copy','abc')]
    report=duplicate_report(rows)
    assert len(report)==2
    assert {r['kind'] for r in report}=={'Exact duplicate','Possible alternate mix'}


def test_import_skips_identical_files_before_indexing_again(tmp_path):
    from cueatlas.engine import import_files
    p,rows=fixture_project(tmp_path);source=tmp_path/'program.wav';copy=tmp_path/'copy.wav';shutil.copy2(source,copy)
    result=import_files(p.path,[str(source),str(copy)])
    assert result['added']==0 and result['skipped']==2 and len(result['duplicates'])==1
    p.close()


def test_handoff_moves_with_media_and_leaves_source_untouched(tmp_path):
    p,rows=fixture_project(tmp_path);save_marker(p,3,'Confirm ending')
    before=hashlib.sha256(p.path.read_bytes()).hexdigest();dest=tmp_path/'handoff'
    result=create_handoff(p.path,{'destination':str(dest),'media':'all'})
    assert result['missing']==0 and hashlib.sha256(p.path.read_bytes()).hexdigest()==before
    moved=tmp_path/'moved';dest.rename(moved)
    packaged=Project(moved/p.path.name)
    assert Path(packaged.get('program')['path']).is_file()
    assert all(Path(t['path']).is_file() and Path(t['path']).is_relative_to(moved) for t in packaged.tracks())
    assert packaged.cues()==rows and packaged.get('markers')==p.get('markers')
    assert not packaged.get('recovery_id')
    with (moved/'cue-sheet.csv').open(encoding='utf-8-sig') as file:
        report=list(csv.DictReader(file))
    assert any(r['Reference File'].startswith('media/') for r in report)
    # Packaging a portable project must resolve paths from its original folder.
    again=tmp_path/'again';create_handoff(packaged.path,{'destination':str(again),'media':'all'})
    second=Project(again/packaged.path.name);assert Path(second.tracks()[0]['path']).is_file()
    from cueatlas.engine import import_library
    imported=Project(tmp_path/'imported.cueatlas',True)
    assert import_library(imported.path,packaged.path)['added']==1
    assert Path(imported.tracks()[0]['path']).is_file()
    imported.close()
    second.close();packaged.close();p.close()


def test_handoff_cancel_missing_media_and_existing_destination(tmp_path):
    p,rows=fixture_project(tmp_path);dest=tmp_path/'cancelled'
    with pytest.raises(Cancelled):create_handoff(p.path,{'destination':str(dest),'media':'all'},cancel=lambda:True)
    assert not dest.exists() and not list(tmp_path.glob('.cueatlas-handoff-*'))
    dest.mkdir()
    with pytest.raises(ValueError,match='existing folders'):create_handoff(p.path,{'destination':str(dest)})
    (tmp_path/'program.wav').unlink();dest=tmp_path/'offline'
    assert create_handoff(p.path,{'destination':str(dest),'media':'program'})['missing']==1
    assert json.loads((dest/'manifest.json').read_text())['files'][0]['status']=='missing'
    p.close()
