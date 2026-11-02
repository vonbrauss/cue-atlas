import sqlite3
import numpy as np
import pytest
from scipy.io.wavfile import write
from PySide6.QtWidgets import QDialog,QMessageBox,QStyledItemDelegate,QHeaderView
from PySide6.QtCore import QItemSelectionModel
from cueatlas.audio import SR
from cueatlas.coverage import audible_spans,ensure_coverage,trim_automatic_cues
from cueatlas.engine import analyze,identify_cue,import_files,repair_coverage,NFFT,STEP
from cueatlas.project import Project,cue
from cueatlas.gui import SettingsDialog,MergeDialog
from cueatlas.matching import PRESETS
from cueatlas.workflow import list_snapshots
from test_timeline import fixture_project,open_window
from test_core import music


def test_routine_deletes_and_merges_never_copy_library_keep_persistent_undo(tmp_path,monkeypatch):
    p,rows=fixture_project(tmp_path)
    def fail(*args,**kwargs):raise AssertionError('Routine cue edit copied the library')
    monkeypatch.setattr(p,'snapshot',fail)
    p.save_cues(rows[1:],label='Delete cue');deleted=p.cues()
    p.merge_cues([c['id'] for c in deleted],track=rows[1]['track'],reviewed=True)
    merged=p.cues();assert not list_snapshots(p)
    path=p.path;p.close();p=Project(path)
    p.undo_edit();assert p.cues()==deleted
    p.undo_edit();assert p.cues()==rows
    p.redo_edit();p.redo_edit();assert p.cues()==merged
    p.close()


def test_delete_eight_cues_writes_only_selected_rows(tmp_path,monkeypatch):
    p,_=fixture_project(tmp_path)
    rows=[cue(None,i/20,(i+1)/20,title=f'Cue {i}') for i in range(200)]
    p.save_cues(rows)
    with p.db:
        p.db.executescript('''CREATE TEMP TABLE touched(id TEXT);
            CREATE TEMP TRIGGER cue_deleted AFTER DELETE ON cues BEGIN INSERT INTO touched VALUES(old.id); END;
            CREATE TEMP TRIGGER cue_updated AFTER UPDATE ON cues BEGIN INSERT INTO touched VALUES(new.id); END;
            CREATE TEMP TRIGGER cue_inserted AFTER INSERT ON cues BEGIN INSERT INTO touched VALUES(new.id); END;''')
    def fail(*args,**kwargs):raise AssertionError('Cue editing requested a full backup')
    monkeypatch.setattr(p,'snapshot',fail)
    p.save_cues(rows[8:],label='Delete cues')
    assert {r[0] for r in p.db.execute('SELECT id FROM touched')}=={c['id'] for c in rows[:8]}
    assert p.cues()==rows[8:]
    p.undo_edit();assert p.cues()==rows
    p.close()


def test_failed_partial_cue_write_rolls_back_deletion_and_history(tmp_path):
    p,rows=fixture_project(tmp_path);history=p.edit_history()
    changed=dict(rows[1],track='missing-reference')
    with pytest.raises(sqlite3.IntegrityError):p.save_cues([changed,rows[2]],label='Invalid edit')
    assert p.cues()==rows and p.edit_history()==history
    p.close()


def test_visible_delete_batches_column_measurements(tmp_path,monkeypatch):
    app,w,_=open_window(tmp_path)
    rows=[cue(None,i/30,(i+1)/30,title=f'Unknown cue with a longer title {i}') for i in range(300)]
    w.p.save_cues(rows);w.refresh(cues_only=True);w.show();app.processEvents()
    class CountingDelegate(QStyledItemDelegate):
        calls=0
        def sizeHint(self,option,index):
            self.calls+=1
            return super().sizeHint(option,index)
    delegate=CountingDelegate(w.cue_table);w.cue_table.setItemDelegate(delegate)
    # A visible native view requests cell geometry on dataChanged. Force that
    # path in headless tests too; otherwise pending layouts hide the regression.
    w.cue_table.model().dataChanged.connect(lambda first,*_:w.cue_table.visualRect(first))
    flags=QItemSelectionModel.Select|QItemSelectionModel.Rows
    for row in range(8):w.cue_table.selectionModel().select(w.cue_table.model().index(row,0),flags)
    monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.Yes)
    delegate.calls=0;w.delete_cue();app.processEvents()
    assert len(w.p.cues())==292
    assert delegate.calls<300*7*4
    assert w.cue_table.horizontalHeader().sectionResizeMode(0)==QHeaderView.ResizeToContents
    assert not w.cue_table.signalsBlocked() and w.cue_table.updatesEnabled()
    w.undo_cue_edit();assert len(w.p.cues())==300
    w.close();app.processEvents()


def test_history_summary_cache_observes_external_edits_and_rollback(tmp_path):
    p,rows=fixture_project(tmp_path);p.trim_cue(rows[1]['id'],3,5)
    assert p.history_summary()['undo']=='Trim cue'
    other=Project(p.path);changed=other.cues();changed[0]['note']='External review';other.save_cues(changed,label='Review cue');other.close()
    assert p.history_summary()['undo']=='Review cue'
    before=p._edit_state()
    with pytest.raises(RuntimeError):
        with p.db:
            p.db.execute("UPDATE cues SET note='Rolled back' WHERE id=?",(rows[0]['id'],))
            p._record_edit('Never committed',before)
            raise RuntimeError()
    assert p.history_summary()['undo']=='Review cue' and p._edit_state()==before
    p.close()


def test_delete_and_merge_do_not_rebuild_reference_table(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);cache=w.reference_cache
    def fail(*args,**kwargs):raise AssertionError('Cue editing rebuilt the reference library')
    monkeypatch.setattr(w,'cache_references',fail);monkeypatch.setattr(w,'populate_references',fail)
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Yes)
    w.cue_table.selectRow(0);w.delete_cue();assert w.reference_cache is cache
    w.undo_cue_edit()
    flags=QItemSelectionModel.Select|QItemSelectionModel.Rows
    w.cue_table.clearSelection()
    for row in (0,1):w.cue_table.selectionModel().select(w.cue_table.model().index(row,0),flags)
    def merge(dialog):dialog.confirm.setChecked(True);dialog.accept();return QDialog.Accepted
    monkeypatch.setattr(MergeDialog,'exec',merge);w.merge_selected()
    assert len(w.p.cues())==2 and w.reference_cache is cache
    w.close();app.processEvents()


def test_silence_gaps_quiet_music_and_existing_reviewed_cues():
    # True silence must not generate Unknown cues or hide quiet audible music.
    audio=np.concatenate([np.zeros(SR),music(912,2)*.02,np.zeros(2*SR)])
    rows=ensure_coverage([],5,audio,silence_db=-65)
    assert rows and all(.85<=c['start']<c['end']<=3.15 for c in rows)
    assert not ensure_coverage([],5,np.zeros(5*SR))
    quiet=np.sin(np.arange(SR)*.1).astype(np.float32)*.001
    assert audible_spans(quiet,1,-65)  # Roughly -63 dBFS RMS, still audible.
    existing=cue(None,0,5,title='Reviewed silence decision',status='Reviewed')
    assert ensure_coverage([existing],5,np.zeros(5*SR))==[existing]
    # No 50-ms/100-ms Unknown slivers around detected boundaries.
    sound=np.ones(SR,dtype=np.float32)*.1
    known=cue('a',.1,.9)
    assert ensure_coverage([known],1,sound)==[known]


def test_analysis_generated_cue_splits_at_long_silence():
    audio=np.concatenate([np.ones(SR*2)*.1,np.zeros(SR*2),np.ones(SR*2)*.1])
    activity=audible_spans(audio,6);original=cue('reference',0,6,title='Original')
    rows=trim_automatic_cues([original],activity,.75)
    assert len(rows)==2 and rows[0]['end']<2.2 and rows[1]['start']>3.8
    assert rows[0]['id']!=rows[1]['id'] and all(c['track']=='reference' for c in rows)


def test_silent_program_has_no_cues_repair_preserves_manual_review(tmp_path):
    p,rows=fixture_project(tmp_path)
    silent=tmp_path/'silence.wav';write(silent,SR,np.zeros(SR*6,dtype=np.float32))
    p.set('program',{'path':str(silent)});analyze(p.path)
    assert not p.cues() and p.get('program')['duration']==6
    manual=cue(rows[1]['track'],1,2,title='Preserve reviewed entry',status='Reviewed');p.save_cues([manual])
    repair_coverage(p.path);assert p.cues()==[manual]
    p.close()


def test_presets_ui_and_legacy_custom_thresholds(tmp_path):
    p,rows=fixture_project(tmp_path);assert p.settings['sensitivity_preset']=='Conservative'
    p.set('settings',{'min_votes':12,'min_cue':2,'gap':1})
    assert p.settings['sensitivity_preset']=='Conservative' and p.settings['min_votes']==24
    p.set('settings',{'min_votes':37,'min_cue':1.4,'gap':.3})
    assert p.settings['sensitivity_preset']=='Custom' and p.settings['min_votes']==37
    p.close()
    # QApplication is provided explicitly because this case otherwise uses only the model.
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    p=Project(tmp_path/'controls.cueatlas',True)
    dialog=SettingsDialog(p,None);dialog.sensitivity.setCurrentText('Sensitive')
    assert all(dialog.values[key].value()==value for key,value in PRESETS['Sensitive'].items())
    dialog.values['min_votes'].setValue(39);assert dialog.sensitivity.currentText()=='Custom'
    dialog.sensitivity.setCurrentText('Balanced');dialog.accept()
    p.set('settings',dialog.settings);assert p.settings['sensitivity_preset']=='Balanced'
    assert all(p.settings[key]==value for key,value in PRESETS['Balanced'].items());p.close()


def test_same_sensitivity_gates_apply_to_analysis_and_retry(tmp_path,monkeypatch):
    p,rows=fixture_project(tmp_path);track=rows[1]['track']
    # Ten densely aligned support frames over ~2.9 seconds: legacy/Balanced evidence.
    # Conservative must reject it, and Sensitive/Balanced may propose it.
    times=np.linspace(0,2.8,10)
    monkeypatch.setattr('cueatlas.engine.match_chunk',lambda *args:[(track,0,times,30)])
    monkeypatch.setattr('cueatlas.engine.refine_region',lambda program,reference,start,end,offset:(start,end))
    conservative=identify_cue(p.path,rows[1]['id']);assert not conservative['candidates']
    analyze(p.path);assert not any(c['track'] for c in p.cues())
    p.save_cues(rows);p.set('settings',p.settings|PRESETS['Balanced']|{'sensitivity_preset':'Balanced'})
    assert identify_cue(p.path,rows[1]['id'])['candidates'][0]['track']==track
    analyze(p.path);assert any(c['track']==track for c in p.cues())
    p.close()
