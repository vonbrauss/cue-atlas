import time
import subprocess
import numpy as np
import pytest
from scipy.io.wavfile import write,read
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialog,QTextBrowser
from PySide6.QtMultimedia import QMediaPlayer
from cueatlas.audio import SR,ffmpeg,decode,decode_program,source_duration
from cueatlas.playback import ReverseWorker,ReversePlayback,PREVIEW_SR
from test_timeline import open_window
from test_editor_controls import fake_player


def wait_for(app,predicate):
    deadline=time.monotonic()+8
    while not predicate() and time.monotonic()<deadline:
        app.processEvents();time.sleep(.01)
    assert predicate()


def test_zoom_centers_playhead_for_buttons_and_keyboard(tmp_path):
    app,w,rows=open_window(tmp_path);t=w.timeline
    w.activateWindow();t.setFocus();app.processEvents()
    t.set_view(0,12);t.position=7
    QTest.mouseMove(t,QPoint(round(t.x_at(2)),t.height()-30))
    w.zoom_in_action.trigger();assert t.view_span==6 and t.view_start==pytest.approx(4)
    QTest.keyClick(t,Qt.Key_Equal,Qt.ControlModifier)
    assert t.view_span==3 and t.view_start==pytest.approx(5.5)
    # Panning away does not change which cursor the next zoom uses.
    t.set_view(0,2);t.zoom(2)
    assert t.view_start==pytest.approx(6.5) and t.view_span==1
    w.close();app.processEvents()


def test_jkl_transport_position_speed_and_text_entry(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);t=w.timeline;state,calls=fake_player(w,monkeypatch)
    reverse_calls=[]
    def reverse_start(path,pos,rate):
        w.reverse.active=True;reverse_calls.append((path,pos,rate))
    monkeypatch.setattr(w.reverse,'start',reverse_start)
    w.seek(5);w.cue_table.selectRow(1);t.setFocus()
    QTest.keyClick(t,Qt.Key_L);assert ('seek',5000) in calls and w.stop_at is None
    assert w.shuttle_direction==1 and w.shuttle_speed==1
    QTest.keyClick(t,Qt.Key_L);assert w.shuttle_speed==2 and w.player.playbackRate()==2
    w.position_changed(7000)
    QTest.keyClick(t,Qt.Key_K);assert state['value']==QMediaPlayer.PausedState and t.position==7
    QTest.keyClick(t,Qt.Key_J);assert reverse_calls[-1][1:]==(7,1)
    w.reverse.positionChanged.emit(6.5);assert t.position==6.5
    w.position_changed(7000);assert t.position==6.5  # Ignore stale forward ticks.
    QTest.keyClick(t,Qt.Key_J);assert reverse_calls[-1][1:]==(6.5,2)
    QTest.keyClick(t,Qt.Key_L);assert not w.reverse.active and calls[-2:]==[('seek',6500),('play',)]
    assert w.shuttle_speed==1
    QTest.keyClick(w.cue_table,Qt.Key_K);assert state['value']==QMediaPlayer.PausedState
    before=list(calls);w.search.setFocus();QTest.keyClicks(w.search,'jkl')
    assert w.search.text()=='jkl' and calls==before
    w.close();app.processEvents()


def test_fixed_layout_header_controls_and_help(tmp_path):
    app,w,rows=open_window(tmp_path)
    w.waveform_focus_button.click();w.resize(950,650);app.processEvents()
    assert w.centralWidget().metaObject().className()=='QWidget'
    assert w.width()==950 and w.height()==650
    for widget in [w.program_card,w.tabs,w.status,w.export_button]:
        point=widget.mapTo(w.centralWidget(),QPoint(0,0))
        assert point.x()>=0 and point.y()>=0
        assert point.x()+widget.width()<=w.centralWidget().width()
        assert point.y()+widget.height()<=w.centralWidget().height()
    assert w.choose_button.isHidden() and w.analyze_button.isHidden()
    assert w.choose_action.isEnabled() and w.analyze_action.isEnabled()
    assert w.export_button.parentWidget()==w.project_button.parentWidget()
    assert not w.focus_button.text() and not w.waveform_focus_button.text()
    w.grab().save('/private/tmp/cueatlas-compact-normal.png')
    w.focus_button.click();app.processEvents()
    assert w.program_card.isHidden() and w.export_button.isVisible() and w.focus_button.isVisible()
    w.focus_button.click();w.waveform_focus_button.click();app.processEvents()
    assert w.tabs.isHidden() and w.export_button.isVisible()
    w.grab().save('/private/tmp/cueatlas-compact-waveform.png')
    w.help_button.click();app.processEvents()
    from cueatlas.help_window import HelpDialog
    help_dialog=w.findChild(HelpDialog)
    assert help_dialog is not None
    for topic,expected in [('Keyboard shortcuts','J'),('Project setup','MP4'),('Cue editing','Shift-drag')]:
        help_dialog.open_topic(topic)
        assert expected in help_dialog.browser.toPlainText()
    help_dialog.close();w.close();app.processEvents()


def test_reverse_worker_outputs_reversed_audio_and_stale_chunks_are_ignored(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    path=tmp_path/'audio.wav';samples=np.linspace(-.75,.75,PREVIEW_SR*2,dtype=np.float32);write(path,PREVIEW_SR,samples)
    worker=ReverseWorker(str(path),2,str(tmp_path),5);results=[];worker.ready.connect(results.append)
    worker.start();wait_for(app,lambda:bool(results));worker.wait()
    chunk=results[0];rate,data=read(chunk['path'])
    assert rate==PREVIEW_SR and chunk['start']==0 and chunk['end']==2
    assert data/32767==pytest.approx(samples[::-1],abs=1/32767)
    reverse=ReversePlayback();monkeypatch.setattr(reverse.player,'play',lambda:None)
    reverse.generation=5;reverse.active=True;reverse.loading=True;reverse._ready(chunk)
    positions=[];reverse.positionChanged.connect(positions.append)
    reverse._position(500);assert positions[-1]==1.5
    reverse.stop();reverse._position(1000);assert positions[-1]==1.5
    stale=tmp_path/'stale.wav';stale.write_bytes(b'stale')
    reverse._ready({'generation':5,'path':stale,'start':0,'end':2})
    assert not stale.exists() and not reverse.active
    reverse.shutdown()


def make_video(tmp_path,suffix,offset=0,silent=False):
    from test_core import music
    audio=tmp_path/'sound.wav';write(audio,SR,music(222,4))
    output=tmp_path/('source'+suffix)
    args=[ffmpeg(),'-v','error','-f','lavfi','-i','color=c=black:s=64x64:r=10:d=6']
    if not silent:args+=['-itsoffset',str(offset),'-i',str(audio),'-map','0:v:0','-map','1:a:0','-c:a','aac']
    args+=['-c:v','mpeg4',str(output)]
    subprocess.run(args,check=True,capture_output=True)
    return output


@pytest.mark.parametrize('suffix',['.mp4','.mov'])
def test_video_audio_analysis_uses_audio_duration_not_longer_video(tmp_path,suffix):
    video=make_video(tmp_path,suffix)
    samples,duration,reported=decode_program(video)
    assert duration==pytest.approx(4,abs=.1) and reported==pytest.approx(4,abs=.1)
    assert np.max(np.abs(samples))>.3
    from cueatlas.project import Project
    from cueatlas.engine import analyze,import_files
    p=Project(tmp_path/'video.cueatlas',True,'Video');p.set('program',{'path':str(video)})
    import_files(p.path,[str(tmp_path/'sound.wav')]);analyze(p.path)
    assert p.get('program')['duration']==duration and p.cues()
    assert any(c['track'] for c in p.cues())
    p.close()


def test_video_leading_audio_offset_and_no_audio_error(tmp_path):
    video=make_video(tmp_path,'.mov',offset=1)
    samples,duration,reported=decode_program(video)
    assert duration==pytest.approx(5,abs=.15)
    assert np.max(np.abs(samples[:int(SR*.8)]))<.001
    # Zoom/reverse decoding must share the full-source time origin.
    detail=decode(video,start=0,duration=.5)
    assert np.max(np.abs(detail))<.001
    detail=decode(video,start=1.5,duration=.5)
    expected=samples[round(1.5*SR):round(2*SR)]
    assert len(detail)==pytest.approx(.5*SR,abs=1)
    assert np.corrcoef(detail[:len(expected)],expected[:len(detail)])[0,1]>.95
    silent=make_video(tmp_path,'.mp4',silent=True)
    with pytest.raises(ValueError,match='No audio track'):decode_program(silent)


def test_setup_actions_move_to_settings_after_completion(tmp_path):
    app,w,rows=open_window(tmp_path)
    w.waveform_focus_button.click()
    program=w.p.get('program');w.p.save_cues([]);w.p.set('program',{})
    w.refresh();app.processEvents()
    assert w.choose_button.isVisible() and w.analyze_button.isHidden()
    w.p.set('program',{'path':program['path']});w.refresh();app.processEvents()
    assert w.choose_button.isHidden() and w.analyze_button.isVisible() and w.analyze_button.isEnabled()
    w.p.set('program',program|{'decoded_duration':12});w.p.set('analysis_settings',w.p.settings)
    w.refresh();app.processEvents()
    assert w.analyze_button.isHidden() and w.analyze_action.isEnabled()
    assert w.choose_action.isEnabled()  # Still available after setup, even with an empty cue sheet.
    w.close();app.processEvents()
