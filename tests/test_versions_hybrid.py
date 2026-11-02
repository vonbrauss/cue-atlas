import csv,json
from pathlib import Path
import numpy as np
import pytest
from scipy.io.wavfile import write
from cueatlas.project import cue
from cueatlas import separation as ai
from cueatlas import versions as v
from cueatlas.audio import SR,Cancelled,decode
from cueatlas.engine import analyze
from test_timeline import fixture_project,open_window


@pytest.fixture(autouse=True)
def isolated_ai(tmp_path,monkeypatch):
    monkeypatch.setenv('CUEATLAS_AI_HOME',str(tmp_path/'ai'));monkeypatch.setattr(ai,'installed',lambda:True)


def track(tid,title,**metadata):return {'id':tid,'metadata':{'title':title}|metadata,'path':title+'.wav'}


def candidate(tid,row,support=30,shift=0):
    return {'track':tid,'title':'Reference '+tid,'support':support,'votes':support*3,
            'program_start':max(row['start'],-shift),'reference_start':max(0,row['start']+shift)}


def version_project(tmp_path):
    p,rows=fixture_project(tmp_path);path=tmp_path/'instrumental.wav';path.write_bytes(b'instrumental')
    alt=p.save_track(path,12,{'title':'Neon evenings (Instrumental)','license':'Instrumental license'},[])
    return p,rows,alt


def results(p,row,original=(),separated=()):
    result={'ai_batch':True,'project':str(p.path),'settings':p.settings,'program':p.get('program'),'library':ai.library_signature(p),
            'items':[{'cue':row,'original':list(original),'separated':list(separated),'error':None,'pending':False}]}
    return v.annotate_results(result,p)


@pytest.mark.parametrize('name',['Neon evenings Instrumental','Neon evenings (Instrumental)','Neon evenings - Full Instrumental','Neon evenings [Vocal Version]','Neon evenings Original Version'])
def test_family_hints_group_versions(name):
    assert v.related(track('a','Neon evenings'),track('b',name))


def test_grouping_preserves_meaningful_titles_and_conflicting_provenance():
    assert not v.related(track('a','Original Sin'),track('b','Sin'))
    assert not v.related(track('a','Neon (Live)'),track('b','Neon Instrumental'))
    assert not v.related(track('a','Neon',library='A'),track('b','Neon Instrumental',library='B'))
    assert not v.related(track('a','Neon',artist='A'),track('b','Neon Instrumental',artist='B'))
    assert v.related(track('a','Été'),track('b','Été (Instrumental)'))


def test_original_vocal_evidence_is_not_overridden_by_stronger_ai_instrumental(tmp_path):
    p,rows,alt=version_project(tmp_path);row=rows[2];vocal=rows[1]['track']
    original=candidate(vocal,row,30);music=candidate(alt,row,150)
    result=results(p,row,[original],[music]);entry=result['items'][0]
    assert entry['recommendation']['preferred']==vocal and not entry['recommendation']['version_unresolved']
    assert v.review_choices(entry)[0]==original
    ai.apply_matches(p,result,{row['id']:original})
    assert p.cues()[-1]['track']==vocal and p.track(vocal)['metadata']['license']=='Keep license'
    assert p.track(alt)['metadata']['license']=='Instrumental license';p.close()


def test_conflicting_original_versions_remain_unresolved_even_with_unequal_support(tmp_path):
    p,rows,alt=version_project(tmp_path);row=rows[2];vocal=rows[1]['track']
    result=results(p,row,[candidate(vocal,row,30),candidate(alt,row,200)],[candidate(alt,row,300)])
    assert result['items'][0]['recommendation']['version_unresolved'];p.close()


def test_ai_only_song_can_be_applied_without_guessing_version_or_license_and_undone(tmp_path):
    from cueatlas.export import export
    p,rows,alt=version_project(tmp_path);row=rows[2];before=p._edit_state();old_versions=p.get('version_reviews',{})
    result=results(p,row,separated=[candidate(alt,row,150)])
    choices=v.review_choices(result['items'][0]);pending=choices[0]
    assert pending['version_unresolved'] and pending['track'] is None
    assert any(c.get('comparison_only') and c['track']==rows[1]['track'] for c in choices)
    assert ai.apply_matches(p,result,{row['id']:pending})==0
    saved=p.cues()[-1];assert saved['track'] is None and saved['status']=='Needs review' and 'Version needs review' in saved['title']
    assert len(p.get('version_reviews')[row['id']])==2
    out=tmp_path/'export.csv';export(p,out)
    with out.open(encoding='utf-8-sig') as file:
        exported=list(csv.DictReader(file));assert exported[-1]['License']==''
    after=p._edit_state();new_versions=p.get('version_reviews');p.undo_edit()
    assert p._edit_state()==before and p.get('version_reviews',{})==old_versions
    p.redo_edit();assert p._edit_state()==after and p.get('version_reviews')==new_versions;p.close()


@pytest.mark.parametrize('delta,joined',[(0,1),(.08,1),(.2,0),(40,0)])
def test_adjoining_merge_requires_same_recording_and_continuous_reference_position(tmp_path,delta,joined):
    p,rows=fixture_project(tmp_path);row=rows[2];tid=rows[1]['track']
    p.set('cue_matches',{rows[1]['id']:{'track':tid,'program_start':2,'reference_start':40}})
    c=candidate(tid,row,30,38+delta);result=results(p,row,separated=[c]);before=p._edit_state()
    assert bool(result['items'][0]['neighbors'])==(joined==1)
    assert ai.apply_matches(p,result,{row['id']:c})==joined
    assert len(p.cues())==3-joined;p.undo_edit();assert p._edit_state()==before;p.close()


def test_versions_do_not_merge_even_if_song_title_and_positions_agree(tmp_path):
    p,rows,alt=version_project(tmp_path);row=rows[2];tid=rows[1]['track']
    p.set('cue_matches',{rows[1]['id']:{'track':tid,'program_start':2,'reference_start':2}})
    c=candidate(alt,row,30);result=results(p,row,[c],[c])
    assert ai.apply_matches(p,result,{row['id']:c})==0 and len(p.cues())==3;p.close()


def test_neighbors_only_help_candidates_with_real_audio_evidence(tmp_path):
    p,rows=fixture_project(tmp_path);row=rows[2];tid=rows[1]['track']
    path=tmp_path/'other.wav';path.write_bytes(b'other');other=p.save_track(path,12,{'title':'Different song'},[])
    p.set('cue_matches',{rows[1]['id']:{'track':tid,'program_start':2,'reference_start':2}})
    result=results(p,row,separated=[candidate(tid,row,90),candidate(other,row,100)])
    assert result['items'][0]['recommendation']['preferred']==tid
    empty=results(p,row);assert 'recommendation' not in empty['items'][0]
    p.close()


def test_first_pass_collapses_ambiguous_version_observations_without_assigning_a_license():
    tracks=[track('v','Song'),track('i','Song Instrumental')]
    rows=[cue('v',0,10,title='Song')|{'_support':30,'_reference_offset':4},cue('i',0,10,title='Song Instrumental')|{'_support':90,'_reference_offset':4}]
    output,reviews=v.collapse_versions(rows,tracks,8)
    assert len(output)==1 and output[0]['track'] is None and output[0]['status']=='Needs review'
    assert {c['track'] for c in reviews[output[0]['id']]}=={'v','i'}


def test_hybrid_only_sends_unknowns_to_ai_and_retains_standard_results(tmp_path,monkeypatch):
    import cueatlas.engine as engine
    p,rows=fixture_project(tmp_path);calls=[]
    def standard(path,**kwargs):
        assert kwargs['version_aware'] and kwargs['unknown_max_seconds']==120
        return {'cues':3}
    def follow(path,request,**kwargs):
        calls.extend(request['ids']);assert p.cues()==rows
        return {'ai_batch':True,'project':str(p.path),'settings':p.settings,'program':p.get('program'),'library':ai.library_signature(p),'items':[], 'cancelled':False}
    monkeypatch.setattr(engine,'analyze',standard);monkeypatch.setattr(ai,'analyze_separated',follow)
    result=ai.hybrid_analysis(p.path)
    assert calls==[rows[0]['id'],rows[2]['id']] and result['hybrid'] and result['unknown_searched']==2
    assert p.cues()==rows and p.get('analysis_mode')=='standard_ai_followup';p.close()


def test_hybrid_does_not_separate_already_identified_but_ambiguous_versions(tmp_path,monkeypatch):
    import cueatlas.engine as engine
    p,rows,alt=version_project(tmp_path);row=rows[2]|{'status':'Needs review','title':'Neon evenings · Version needs review'}
    p.save_cues([rows[1],row]);p.set('version_reviews',{row['id']:[candidate(rows[1]['track'],row),candidate(alt,row)]})
    monkeypatch.setattr(engine,'analyze',lambda *a,**k:{'cues':2})
    monkeypatch.setattr(ai,'analyze_separated',lambda *a,**k:pytest.fail('No unresolved music search is needed'))
    result=ai.hybrid_analysis(p.path)
    assert result['unknown_searched']==0 and result['items'][0]['recommendation']['version_unresolved'];p.close()


def test_cancelled_follow_up_keeps_standard_cues_and_provides_review_results(tmp_path,monkeypatch):
    import cueatlas.engine as engine
    p,rows=fixture_project(tmp_path);before=p._edit_state()
    monkeypatch.setattr(engine,'analyze',lambda *a,**k:{'cues':3})
    def cancel(*a,**k):raise Cancelled()
    monkeypatch.setattr(ai,'analyze_separated',cancel)
    result=ai.hybrid_analysis(p.path)
    assert result['cancelled'] and result['hybrid'] and p._edit_state()==before;p.close()


def test_hybrid_initial_unknowns_are_bounded_for_follow_up(tmp_path,monkeypatch):
    p,rows=fixture_project(tmp_path);source=Path(p.get('program')['path']);write(source,SR,np.full(SR*301,.1,dtype=np.float32))
    monkeypatch.setattr('cueatlas.engine.match_chunk',lambda *a:[])
    analyze(p.path,version_aware=True,unknown_max_seconds=120)
    assert [round(c['end']-c['start']) for c in p.cues()]==[120,120,61];p.close()


def test_unresolved_version_choice_is_visible_and_never_defaults_to_a_recording(tmp_path):
    from cueatlas.ai_ui import AIResultsDialog
    app,w,rows=open_window(tmp_path);path=tmp_path/'instrumental.wav';path.write_bytes(b'alt')
    alt=w.p.save_track(path,12,{'title':'Neon evenings Instrumental','license':'Alt'},[])
    result=results(w.p,rows[2],separated=[candidate(alt,rows[2])]);dialog=AIResultsDialog(w,result)
    assert dialog.selectors[0].currentData()['version_unresolved']
    assert 'Version needs review' in dialog.table.item(0,4).text()
    dialog.select_all(True);dialog.apply();assert w.p.cues()[-1]['track'] is None
    w.close();app.processEvents()


def test_hybrid_mode_is_offered_and_dispatches_follow_up(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QPushButton,QMessageBox,QDialog
    from cueatlas.ai_ui import AnalysisModeDialog
    app,w,rows=open_window(tmp_path);calls=[]
    def choose(dialog):
        button=next(b for b in dialog.findChildren(QPushButton) if b.text()=='Standard + AI follow-up')
        button.click();return QDialog.Accepted
    monkeypatch.setattr(AnalysisModeDialog,'exec',choose);monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.Yes)
    monkeypatch.setattr(w,'start_worker',lambda fn,*a:calls.append(fn))
    w.run_analysis();assert calls==[ai.hybrid_analysis] and w.p.cues()==rows;w.close();app.processEvents()


def test_unknown_ai_uses_surrounding_context_but_returns_exact_cue_audio(tmp_path,monkeypatch):
    from test_ai_separation import proposal
    p,rows=fixture_project(tmp_path);row=rows[1];observed=[]
    monkeypatch.setattr(ai,'identify_cue',lambda path,cid,**kwargs:{'candidates':[proposal(p,row)] if 'audio_override' in kwargs else []})
    def events(request,cancel):
        job=json.loads(Path(request).read_text())['jobs'][0];audio=decode(job['input'],sample_rate=48000)
        observed.append(len(audio)/48000);write(job['output'],48000,audio)
        yield {'type':'done','id':job['id'],'seconds':.01}
    monkeypatch.setattr(ai,'_events',events)
    result=ai.analyze_separated(p.path,{'ids':[row['id']]});entry=result['items'][0]
    assert observed==[10]  # Cue 2–6, with source context 0–10.
    assert len(decode(entry['audio']))==4*SR and entry['cue']==row and p.cues()==rows
    assert not entry['error'] and not result.get('failure');p.close()


def test_main_review_can_confirm_version_and_undo_restores_unassigned_family(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QDialog
    from cueatlas.gui import CueDialog
    app,w,rows=open_window(tmp_path);path=tmp_path/'instrumental.wav';path.write_bytes(b'alt')
    alt=w.p.save_track(path,12,{'title':'Neon evenings Instrumental','license':'Instrumental license'},[])
    result=results(w.p,rows[2],separated=[candidate(alt,rows[2])]);entry=result['items'][0]
    ai.apply_matches(w.p,result,{rows[2]['id']:v.review_choices(entry)[0]});pending=w.p.cues()[-1]
    before=w.p._edit_state();versions=w.p.get('version_reviews')
    def confirm(dialog):
        assert isinstance(dialog,CueDialog)
        assert {dialog.track.itemData(i) for i in (1,2)}=={rows[1]['track'],alt}
        dialog.track.setCurrentIndex(dialog.track.findData(rows[1]['track']));dialog.status.setCurrentText('Reviewed');dialog.accept();return QDialog.Accepted
    monkeypatch.setattr(QDialog,'exec',confirm);w.edit_cue_dialog(pending)
    saved=w.p.cues()[-1];assert saved['track']==rows[1]['track'] and saved['status']=='Reviewed'
    assert 'Version needs review' not in saved['title'] and rows[2]['id'] not in w.p.get('version_reviews')
    w.p.undo_edit();assert w.p._edit_state()==before and w.p.get('version_reviews')==versions
    w.close();app.processEvents()


def test_split_unresolved_version_preserves_choices_and_history(tmp_path):
    p,rows,alt=version_project(tmp_path);row=rows[2]
    result=results(p,row,separated=[candidate(alt,row)]);ai.apply_matches(p,result,{row['id']:v.review_choices(result['items'][0])[0]})
    before=p._edit_state();versions=p.get('version_reviews');right=p.split_cue(row['id'],9)
    assert p.get('version_reviews')[right['id']]==versions[row['id']]
    p.undo_edit();assert p._edit_state()==before and p.get('version_reviews')==versions;p.close()


def test_engine_persists_ambiguous_original_versions_for_review(tmp_path):
    import shutil
    from test_retry_comparison import retry_project
    from cueatlas.workflow import review_queue
    p,original,rows=retry_project(tmp_path);path=tmp_path/'alternate.wav';shutil.copyfile(original['path'],path)
    hashes=[tuple(r) for r in p.db.execute('SELECT hash,frame FROM hashes WHERE track=?',(original['id'],))]
    alt=p.save_track(path,original['duration'],original['metadata']|{'title':original['metadata']['title']+' Instrumental','license':'Alt only'},hashes)
    analyze(p.path,version_aware=True)
    pending=[c for c in p.cues() if c['id'] in p.get('version_reviews',{})]
    assert pending and all(c['track'] is None and c['status']=='Needs review' for c in pending)
    assert {v['track'] for v in p.get('version_reviews')[pending[0]['id']]}=={original['id'],alt}
    assert any('Version needs review' in c['reasons'] for c in review_queue(p))
    p.close()


def test_comparing_versions_uses_each_recordings_own_reference_position(tmp_path):
    from cueatlas.gui import CueDialog
    app,w,rows=open_window(tmp_path);path=tmp_path/'instrumental.wav';path.write_bytes(b'alt')
    alt=w.p.save_track(path,100,{'title':'Neon evenings Instrumental'},[]);vocal=rows[1]['track']
    options=[candidate(vocal,rows[2],30,2),candidate(alt,rows[2],40,20)]
    d=CueDialog(rows[2],w.p.tracks(),12,w,version_candidates=options)
    d.track.setCurrentIndex(d.track.findData(vocal));assert d.comparison.offset.value()==8
    d.track.setCurrentIndex(d.track.findData(alt));assert d.comparison.offset.value()==26
    d.reject();w.close();app.processEvents()



def test_partial_interval_evidence_does_not_auto_merge_unknown_into_neighbor(tmp_path):
    p,rows=fixture_project(tmp_path);row=rows[2];tid=rows[1]['track']
    p.set('cue_matches',{rows[1]['id']:{'track':tid,'program_start':2,'reference_start':2}})
    partial=candidate(tid,row,30)|{'evidence_start':8,'evidence_end':10,'max_evidence_gap':.1}
    result=results(p,row,separated=[partial]);assert 'review cue boundaries' in result['items'][0]['recommendation']['reason']
    assert ai.apply_matches(p,result,{row['id']:partial})==0 and len(p.cues())==3;p.close()


def test_review_controls_show_available_audio_and_explicit_playback_state(tmp_path,monkeypatch):
    from PySide6.QtMultimedia import QMediaPlayer
    from cueatlas.ai_ui import AIResultsDialog
    app,w,rows=open_window(tmp_path);c=candidate(rows[1]['track'],rows[2])
    result=results(w.p,rows[2],original=[c]);dialog=AIResultsDialog(w,result)
    assert dialog.original_button.isEnabled() and not dialog.music_button.isEnabled() and not dialog.apply_button.isEnabled()
    audio=tmp_path/'music.wav';write(audio,SR,np.zeros(SR*6,dtype=np.float32));result['items'][0]['audio']=str(audio);dialog.update_controls()
    assert dialog.music_button.isEnabled();state=[QMediaPlayer.StoppedState];positions=[]
    monkeypatch.setattr(dialog.player,'playbackState',lambda:state[0])
    def play():state[0]=QMediaPlayer.PlayingState;dialog.update_controls()
    def pause():state[0]=QMediaPlayer.PausedState;dialog.update_controls()
    monkeypatch.setattr(dialog.player,'play',play);monkeypatch.setattr(dialog.player,'pause',pause)
    monkeypatch.setattr(dialog.player,'setSource',lambda *a:None);monkeypatch.setattr(dialog.player,'setPosition',positions.append)
    dialog.play(True);assert positions[-1]==0 and dialog.music_button.text()=='Pause music'
    dialog.play(False);assert positions[-1]==6000 and dialog.original_button.text()=='Pause original' and dialog.music_button.text()=='Play music'
    dialog.play(False);assert state[0]==QMediaPlayer.PausedState and dialog.original_button.text()=='Play original'
    dialog.select_all(True);assert dialog.apply_button.isEnabled()
    dialog.reject();w.close();app.processEvents()
