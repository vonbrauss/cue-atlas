import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from test_timeline import fixture_project,open_window


@pytest.mark.parametrize('excluded',[False,True])
def test_split_preserves_reference_review_exclusion_alignment_and_history(tmp_path,excluded):
    p,rows=fixture_project(tmp_path);original=rows[1]
    p.set('cue_matches',{original['id']:{'track':original['track'],'program_start':2,'reference_start':9}})
    if excluded:p.set_cues_excluded([original['id']])
    before=p._edit_state();right=p.split_cue(original['id'],4.125)
    left=p.cues()[1]
    assert left==original|{'end':4.125}
    assert right==original|{'id':right['id'],'start':4.125}
    assert right['id']!=original['id']
    assert p.get('cue_matches')[right['id']]==p.get('cue_matches')[original['id']]
    assert (right['id'] in p.excluded_cue_ids())==excluded
    assert p.track(original['track'])['metadata']['license']=='Keep license'
    after=p._edit_state();path=p.path;p.close()
    from cueatlas.project import Project
    p=Project(path);assert p.undo_edit()=='Split cue';assert p._edit_state()==before
    p.redo_edit();assert p._edit_state()==after;p.close()


@pytest.mark.parametrize('point',[2,6,1,7,float('nan'),float('inf')])
def test_split_rejects_outside_or_boundary_without_changes(tmp_path,point):
    p,rows=fixture_project(tmp_path);before=p._edit_state();history=p.edit_history()
    with pytest.raises(ValueError):p.split_cue(rows[1]['id'],point)
    assert p._edit_state()==before and p.edit_history()==history;p.close()


@pytest.mark.parametrize('target',['timeline','cue_table'])
def test_s_splits_selected_cue_at_playhead_and_does_not_intercept_typing(tmp_path,target):
    app,w,rows=open_window(tmp_path);w.cue_table.selectRow(1);w.seek(4)
    QTest.keyClick(getattr(w,target),Qt.Key_S)
    assert [(c['start'],c['end']) for c in w.p.cues()]==[(0,2),(2,4),(4,6),(6,12)]
    assert w.selected_cues()[0]['start']==4
    w.undo_cue_edit();assert w.p.cues()==rows
    w.search.setFocus();QTest.keyClicks(w.search,'s');assert w.search.text()=='s' and w.p.cues()==rows
    w.close();app.processEvents()


def test_new_split_default_preserves_existing_custom_s_binding(tmp_path):
    import json
    from PySide6.QtCore import QSettings
    from cueatlas.shortcuts import load_bindings,DEFAULTS
    prefs=QSettings(str(tmp_path/'keys.ini'),QSettings.IniFormat)
    previous={k:v for k,v in DEFAULTS.items() if k!='split'};previous['identify']='S'
    prefs.setValue('keyboard_shortcuts',json.dumps(previous))
    loaded=load_bindings(prefs)
    assert loaded['identify']=='S' and loaded['split']==''
    assert {k:v for k,v in loaded.items() if k!='split'}==previous
