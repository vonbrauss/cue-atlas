import time
import numpy as np
import pytest
from scipy.io.wavfile import write
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialog
from cueatlas.gui import Window,MergeDialog,STYLE
from cueatlas.project import Project,cue
from cueatlas.audio import SR
from cueatlas.coverage import covered_seconds


def fixture_project(tmp_path):
    p=Project(tmp_path/'edit.cueatlas',True,'Waveform editing')
    f=tmp_path/'program.wav'
    samples=np.sin(np.arange(SR*12)*.09).astype(np.float32)*.5
    write(f,SR,samples)
    tid=p.save_track(f,12,{'title':'Neon evenings','license':'Keep license','raw':{}},[])
    p.set('program',{'path':str(f),'duration':12,'waveform':[.5]*1100})
    rows=[cue(None,0,2,title='Intro'),cue(tid,2,6,title='Song',status='Reviewed'),cue(None,6,12,title='Tail')]
    p.save_cues(rows)
    return p,rows


def test_trim_preserves_neighbors_identity_metadata_and_undo(tmp_path):
    p,rows=fixture_project(tmp_path)
    p.trim_cue(rows[1]['id'],1,8)
    assert [(c['start'],c['end']) for c in p.cues()]==[(0,2),(1,8),(6,12)]
    assert p.cues()[1]['id']==rows[1]['id'] and p.cues()[1]['status']=='Reviewed'
    assert p.tracks()[0]['metadata']['license']=='Keep license'
    assert covered_seconds(p.cues(),12)==12
    path=p.path;p.close();p=Project(path);p.undo_trim();assert p.cues()==rows
    with pytest.raises(ValueError):p.trim_cue(rows[1]['id'],8,1)
    assert p.cues()==rows
    p.trim_cue(rows[1]['id'],3,5)
    assert covered_seconds(p.cues(),12)==10
    assert len(p.cues())==3
    p.set_cues_excluded([rows[0]['id']]);assert p.get('undo_trim') is None
    p.close()


def test_trim_preserves_other_identified_and_excluded_regions(tmp_path):
    p,rows=fixture_project(tmp_path)
    p.set_cues_excluded([rows[2]['id']]);p.trim_cue(rows[1]['id'],2,10)
    assert next(c for c in p.cues() if c['id']==rows[2]['id'])==rows[2]
    p.undo_trim();assert p.excluded_cue_ids()=={rows[2]['id']}
    p.set_cues_excluded([rows[2]['id']],False)
    other=rows[2]|{'track':rows[1]['track'],'status':'Reviewed'}
    p.save_cues([rows[0],rows[1],other]);p.trim_cue(rows[1]['id'],2,8)
    assert next(c for c in p.cues() if c['id']==other['id'])==other
    p.close()


def open_window(tmp_path):
    app=QApplication.instance() or QApplication([]);app.setStyleSheet(STYLE)
    p,rows=fixture_project(tmp_path);path=p.path;p.close()
    w=Window();w.load(str(path));w.show();w.waveform_focus_button.click();app.processEvents()
    return app,w,rows


def center(timeline,cue_id):
    return next(rect.center().toPoint() for c,rect in timeline.regions() if c['id']==cue_id)


def test_waveform_mouse_selection_merge_exclusion_and_preview(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);t=w.timeline
    assert w.tabs.isHidden() and t.height()>=300
    assert next(c for c in t.cues if c['id']==rows[1]['id'])['display_title']=='Neon evenings'
    QTest.mouseClick(t,Qt.LeftButton,Qt.NoModifier,center(t,rows[1]['id']))
    assert [c['id'] for c in w.selected_cues()]==[rows[1]['id']]
    calls=[];monkeypatch.setattr(w.player,'setPosition',lambda ms:calls.append(ms));monkeypatch.setattr(w.player,'play',lambda:None)
    QTest.keyClick(t,Qt.Key_Space);assert calls[-1]==2000 and w.stop_at==6
    QTest.mouseClick(t,Qt.LeftButton,Qt.ShiftModifier,center(t,rows[2]['id']))
    assert len(w.selected_cues())==2
    def accept_merge(self):
        self.confirm.setChecked(True);self.accept();return QDialog.Accepted
    monkeypatch.setattr(MergeDialog,'exec',accept_merge)
    QTest.keyClick(t,Qt.Key_M)
    assert len(w.p.cues())==2 and w.p.cues()[1]['end']==12
    assert len(t.selected)==1
    w.toggle_cue_exclusion();assert len(t.visible_cues())==1
    w.waveform_excluded.setChecked(True);assert len(t.visible_cues())==1
    QTest.mouseClick(t,Qt.LeftButton,Qt.NoModifier,center(t,w.p.cues()[1]['id']))
    w.toggle_cue_exclusion();assert not w.p.excluded_cue_ids()
    w.waveform_focus_button.click();assert not w.tabs.isHidden()
    w.close();app.processEvents()


def test_drag_handles_save_and_escape_cancel(tmp_path):
    app,w,rows=open_window(tmp_path);t=w.timeline
    QTest.mouseClick(t,Qt.LeftButton,Qt.NoModifier,center(t,rows[1]['id']))
    rect=next(rect for c,rect in t.regions() if c['id']==rows[1]['id'])
    edge=QPoint(round(rect.left()),round(rect.center().y()))
    destination=QPoint(round(t.x_at(1)),edge.y())
    QTest.mousePress(t,Qt.LeftButton,Qt.NoModifier,edge)
    QTest.mouseMove(t,destination)
    assert t.drag is not None
    QTest.mouseRelease(t,Qt.LeftButton,Qt.NoModifier,destination)
    edited=next(c for c in w.p.cues() if c['id']==rows[1]['id'])
    assert edited['start']==pytest.approx(1,abs=.04)
    assert w.undo_action.isEnabled()
    w.undo_boundary_edit();assert w.p.cues()==rows
    rect=next(rect for c,rect in t.regions() if c['id']==rows[1]['id'])
    edge=QPoint(round(rect.right()),round(rect.center().y()))
    QTest.mousePress(t,Qt.LeftButton,Qt.NoModifier,edge);QTest.mouseMove(t,QPoint(round(t.x_at(9)),edge.y()))
    QTest.keyClick(t,Qt.Key_Escape);QTest.mouseRelease(t,Qt.LeftButton,Qt.NoModifier,edge)
    assert w.p.cues()==rows
    t.editable=False
    QTest.mousePress(t,Qt.LeftButton,Qt.NoModifier,edge);assert t.drag is None
    QTest.mouseRelease(t,Qt.LeftButton,Qt.NoModifier,edge)
    w.close();app.processEvents()


def test_zoom_pan_and_load_actual_waveform_detail(tmp_path):
    app,w,rows=open_window(tmp_path);t=w.timeline
    t.zoom(12,anchor=6);assert t.view_span==1
    before=t.view_start;t.zoom(2,anchor=6);assert t.view_span==.5
    assert t.view_start>before
    t.set_view(4,.5)
    deadline=time.monotonic()+5
    while t.detail_key!=(4,.5,t.path,t.revision) and time.monotonic()<deadline:
        app.processEvents();time.sleep(.01)
    assert t.detail_key==(4,.5,t.path,t.revision) and len(t.detail)>100
    assert max(t.detail)==pytest.approx(.5,abs=.01)
    w.pan_timeline(10000);assert t.view_start==11.5
    w.cue_table.selectRow(1);t.fit_selection();assert t.view_start<2 and t.view_start+t.view_span>6
    w.grab().save('/private/tmp/cueatlas-waveform-editor.png')
    t.set_view(0,12);assert t.view_span==12 and not w.timeline_scroll.isEnabled()
    w.waveform_focus_button.click();app.processEvents()
    assert t.geometry().bottom()<w.timeline_scroll.parentWidget().height()
    # Timeline and transport controls must occupy distinct vertical space.
    assert t.geometry().bottom()<w.play_button.geometry().top()
    w.grab().save('/private/tmp/cueatlas-waveform-normal.png')
    w.close();app.processEvents()


def test_free_waveform_click_deselects_and_plays_before_cue(tmp_path,monkeypatch):
    from PySide6.QtMultimedia import QMediaPlayer
    app,w,rows=open_window(tmp_path);t=w.timeline
    calls=[]
    monkeypatch.setattr(w.player,'setPosition',lambda ms:calls.append(('seek',ms)))
    monkeypatch.setattr(w.player,'play',lambda:calls.append(('play',)))
    monkeypatch.setattr(w.player,'pause',lambda:calls.append(('pause',)))
    monkeypatch.setattr(w.player,'playbackState',lambda:QMediaPlayer.StoppedState)
    QTest.mouseClick(t,Qt.LeftButton,Qt.NoModifier,center(t,rows[1]['id']))
    QTest.keyClick(t,Qt.Key_Space)
    assert calls[-2:]==[('seek',2000),('play',)] and w.stop_at==6
    point=QPoint(round(t.x_at(1.5)),t.height()-20)
    QTest.mouseClick(t,Qt.LeftButton,Qt.NoModifier,point)
    assert not t.selected and not w.selected_cues() and w.selected_cue() is None
    assert w.stop_at is None and t.position==pytest.approx(1.5,abs=.02)
    seek_call=calls[-1];assert seek_call[0]=='seek' and abs(seek_call[1]-1500)<20
    QTest.keyClick(t,Qt.Key_Space)
    assert calls[-2:]==[seek_call,('play',)] and w.stop_at is None
    w.position_changed(6500);assert calls[-1]==('play',)  # Free playback crosses cue ends.
    monkeypatch.setattr(w.player,'playbackState',lambda:QMediaPlayer.PlayingState)
    QTest.keyClick(t,Qt.Key_Space);assert calls[-1]==('pause',)
    QTest.mouseClick(t,Qt.LeftButton,Qt.NoModifier,center(t,rows[1]['id']))
    monkeypatch.setattr(w.player,'playbackState',lambda:QMediaPlayer.StoppedState)
    QTest.keyClick(t,Qt.Key_Space);assert calls[-2:]==[('seek',2000),('play',)]
    assert w.p.cues()==rows
    w.close();app.processEvents()


def test_horizontal_trackpad_and_command_zoom(tmp_path):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QWheelEvent
    app,w,rows=open_window(tmp_path);t=w.timeline
    w.activateWindow();t.setFocus();app.processEvents()
    t.set_view(3,4)
    def scroll(pixels,angles=QPoint()):
        pos=QPointF(t.width()/2,t.height()-20)
        event=QWheelEvent(pos,QPointF(t.mapToGlobal(pos.toPoint())),pixels,angles,Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False)
        QApplication.sendEvent(t,event)
    scroll(QPoint(-100,0));assert t.view_start>3 and t.view_span==4
    before=t.view_start;scroll(QPoint(50,0));assert t.view_start<before and t.view_span==4
    scroll(QPoint(),QPoint(-120,0));assert t.view_span==4
    QTest.keyClick(t,Qt.Key_Equal,Qt.ControlModifier);assert t.view_span==2
    QTest.keyClick(t,Qt.Key_Minus,Qt.ControlModifier);assert t.view_span==4
    QTest.keyClick(t,Qt.Key_Plus,Qt.ControlModifier);assert t.view_span==2
    w.close();app.processEvents()
