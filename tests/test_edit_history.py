import pytest
from cueatlas.project import Project,cue
from cueatlas.engine import repair_coverage,analyze
from test_timeline import fixture_project


def test_mixed_history_survives_reopen_and_redo_preserves_exact_rows(tmp_path):
    p,rows=fixture_project(tmp_path);snapshots=[p._edit_state()]
    p.trim_cue(rows[1]['id'],1,7);snapshots.append(p._edit_state())
    p.set_cues_excluded([rows[2]['id']]);snapshots.append(p._edit_state())
    p.set_cues_excluded([rows[2]['id']],False);snapshots.append(p._edit_state())
    p.merge_cues([rows[0]['id'],rows[1]['id']],rows[1]['track'],reviewed=True);snapshots.append(p._edit_state())
    edited=p.cues();edited[0]['note']='Reviewed by ear';p.save_cues(edited,label='Review cue');snapshots.append(p._edit_state())
    path=p.path;p.close();p=Project(path)
    for state in reversed(snapshots[:-1]):
        p.undo_edit();assert p._edit_state()==state
    for state in snapshots[1:]:
        p.redo_edit();assert p._edit_state()==state
    assert p.tracks()[0]['metadata']['license']=='Keep license'
    p.close()


def test_new_edit_discards_redo_navigation_does_not(tmp_path):
    p,rows=fixture_project(tmp_path)
    p.trim_cue(rows[1]['id'],1,6);p.undo_edit()
    assert p.edit_history()['redo']
    p.save_cues(p.cues())  # Saving the same rows is not a new history entry.
    assert p.edit_history()['redo']
    p.set_cues_excluded([rows[0]['id']])
    assert not p.edit_history()['redo']
    with pytest.raises(ValueError):p.redo_edit()
    p.close()


def test_remove_and_add_undo_including_exclusions(tmp_path):
    p,rows=fixture_project(tmp_path);p.set_cues_excluded([rows[1]['id']])
    before=p._edit_state();p.save_cues([rows[0],rows[2]],label='Remove cue')
    assert rows[1]['id'] not in p.excluded_cue_ids()
    after=p._edit_state();p.undo_edit();assert p._edit_state()==before
    p.redo_edit();assert p._edit_state()==after
    new=cue(None,3,4,title='Manual');p.save_cues(p.cues()+[new],label='Add cue')
    p.undo_edit();assert p._edit_state()==after
    p.close()


def test_invalid_edit_does_not_change_history_and_repair_resets_it(tmp_path):
    p,rows=fixture_project(tmp_path);p.trim_cue(rows[1]['id'],1,6)
    before=p._edit_state();history=p.edit_history()
    with pytest.raises(ValueError):p.trim_cue(rows[1]['id'],-1,4)
    assert p._edit_state()==before and p.edit_history()==history
    repair_coverage(p.path)
    assert not p.edit_history()['undo'] and not p.edit_history()['redo']
    p.close()


def test_source_change_and_reference_removal_invalidate_history(tmp_path):
    p,rows=fixture_project(tmp_path);p.trim_cue(rows[1]['id'],1,6)
    p.set('program',p.get('program')|{'path':'new-source.wav'})
    assert not p.edit_history()['undo']
    p.save_cues(p.cues()+[cue(None,3,4)])
    p.remove_track(rows[1]['track']);assert not p.edit_history()['undo']
    p.close()
