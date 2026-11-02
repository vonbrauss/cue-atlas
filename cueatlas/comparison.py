"""Optional reference audition. Fingerprints remain usable without source media."""
from pathlib import Path
from .comparison_audio import ReviewAudio
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QDoubleSpinBox,QCheckBox,QFileDialog,QMessageBox
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput


class Comparison(QWidget):
    def __init__(self,c,tracks,project,start,end,track_selector,parent,version_candidates=None):
        super().__init__(parent);self.c=c;self.tracks={t['id']:dict(t) for t in tracks};self.project=project
        self.start=start;self.end=end;self.selector=track_selector;self.gains=dict(project.get('reference_gains',{}))
        self.version_candidates={c['track']:c for c in (version_candidates or []) if not c.get('comparison_only')}
        self.audio=ReviewAudio(self);self.loading=None;self.clips={}
        self.audio.ready.connect(self.audio_ready);self.audio.failed.connect(self.audio_failed)
        self.default_gain=project.settings['reference_gain_db'];self.current=None
        self.program_player=QMediaPlayer(self);self.reference_player=QMediaPlayer(self)
        self.program_output=QAudioOutput(self);self.program_output.setVolume(.75);self.program_player.setAudioOutput(self.program_output)
        self.reference_output=QAudioOutput(self);self.reference_player.setAudioOutput(self.reference_output)
        source=project.get('program',{}).get('path','')
        self.program_source=source;self.program_info=project.get('program',{})
        box=QVBoxLayout(self);box.setContentsMargins(0,0,0,0)
        row=QHBoxLayout();self.program_button=QPushButton('▶ Program cue');self.program_button.setEnabled(Path(source).is_file());row.addWidget(self.program_button)
        self.reference_button=QPushButton('▶ Reference');row.addWidget(self.reference_button)
        self.relink_button=QPushButton('Reconnect…');row.addWidget(self.relink_button);box.addLayout(row)
        controls=QHBoxLayout();controls.addWidget(QLabel('Reference in'))
        self.offset=QDoubleSpinBox();self.offset.setDecimals(3);self.offset.setSuffix(' s');controls.addWidget(self.offset)
        controls.addWidget(QLabel('Reference level'));self.gain=QDoubleSpinBox();self.gain.setRange(-60,0);self.gain.setSuffix(' dB');controls.addWidget(self.gain)
        self.use_default=QCheckBox('Project default');controls.addWidget(self.use_default);box.addLayout(controls)
        self.media_state=QLabel();box.addWidget(self.media_state)
        self.program_button.clicked.connect(self.play_program);self.reference_button.clicked.connect(self.play_reference);self.relink_button.clicked.connect(self.relink)
        self.gain.valueChanged.connect(self.level_changed);self.use_default.toggled.connect(self.default_changed)
        self.selector.currentIndexChanged.connect(self.track_changed)
        self.start.valueChanged.connect(self.stop);self.end.valueChanged.connect(self.stop);self.offset.valueChanged.connect(self.stop)
        self.program_player.positionChanged.connect(self.program_position);self.reference_player.positionChanged.connect(self.reference_position)
        for player in (self.program_player,self.reference_player):
            player.playbackStateChanged.connect(self.update_buttons);player.errorOccurred.connect(lambda *args,p=player:self.media_state.setText(p.errorString()))
        self.track_changed()
    def available(self,t):
        if not t:return False
        path=Path(t['path'])
        if not path.is_file():return False
        stat=path.stat()
        return stat.st_size==t['size'] and stat.st_mtime_ns==t['mtime']
    def remember_gain(self):
        if self.current:
            if self.use_default.isChecked():self.gains.pop(self.current,None)
            else:self.gains[self.current]=self.gain.value()
    def track_changed(self,*args):
        self.remember_gain();self.stop();self.current=self.selector.currentData();t=self.tracks.get(self.current)
        valid=self.available(t);self.reference_button.setEnabled(valid);self.relink_button.setEnabled(bool(t))
        self.relink_button.setVisible(bool(t) and not valid)
        self.reference_player.setSource(QUrl());self.clips.pop('reference',None)
        self.offset.setRange(0,max(0,t['duration']-.001) if t else 0)
        saved=self.project.get('cue_matches',{}).get(self.c['id'],{})
        if saved.get('track')!=self.current:saved=self.version_candidates.get(self.current,{})
        aligned=saved.get('track')==self.current
        self.offset.setValue(max(0,saved.get('reference_start',0)+self.start.value()-saved.get('program_start',self.start.value())) if aligned else 0)
        self.use_default.blockSignals(True);self.use_default.setChecked(self.current not in self.gains);self.use_default.blockSignals(False)
        self.gain.blockSignals(True);self.gain.setValue(self.gains.get(self.current,self.default_gain));self.gain.blockSignals(False)
        self.gain.setEnabled(bool(t));self.use_default.setEnabled(bool(t));self.offset.setEnabled(bool(t));self.apply_gain()
        self.media_state.setText('Reference available' if valid else ('Reference missing or changed' if t else 'No reference selected'))
    def apply_gain(self):self.reference_output.setVolume(.75*10**(self.gain.value()/20))
    def level_changed(self,*args):
        self.use_default.blockSignals(True);self.use_default.setChecked(False);self.use_default.blockSignals(False);self.apply_gain()
    def default_changed(self,checked):
        if checked:
            self.gain.blockSignals(True);self.gain.setValue(self.default_gain);self.gain.blockSignals(False);self.apply_gain()
    def stop(self,*args):
        self.audio.cancel();self.loading=None
        self.program_player.pause();self.reference_player.pause();self.update_buttons()
    def update_buttons(self,*args):
        self.program_button.setText('Cancel preparation' if self.loading=='program' else ('Ⅱ Pause program' if self.program_player.playbackState()==QMediaPlayer.PlayingState else '▶ Program cue'))
        self.reference_button.setText('Cancel preparation' if self.loading=='reference' else ('Ⅱ Pause reference' if self.reference_player.playbackState()==QMediaPlayer.PlayingState else '▶ Reference'))
    def prepare_audio(self,kind,path,start,duration):
        if duration<=0:return
        self.stop();self.loading=kind;self.media_state.setText('Preparing '+kind+' audio…');self.update_buttons()
        self.audio.prepare(kind,path,start,duration,self.program_info if kind=='program' else self.tracks.get(self.current))
    def audio_ready(self,result):
        kind=result['kind'];self.loading=None;self.clips[kind]=result
        player=self.program_player if kind=='program' else self.reference_player
        player.setSource(QUrl.fromLocalFile(result['path']));player.setPosition(0);player.play()
        self.media_state.setText('Comparing '+kind);self.update_buttons()
    def audio_failed(self,message):
        self.loading=None;self.media_state.setText(message);self.update_buttons()
    def play_program(self):
        if self.loading=='program' or self.program_player.playbackState()==QMediaPlayer.PlayingState:self.stop();return
        self.prepare_audio('program',self.program_source,self.start.value(),self.end.value()-self.start.value())
    def play_reference(self):
        if self.loading=='reference' or self.reference_player.playbackState()==QMediaPlayer.PlayingState:self.stop();return
        t=self.tracks.get(self.current)
        if t:self.prepare_audio('reference',t['path'],self.offset.value(),min(t['duration']-self.offset.value(),self.end.value()-self.start.value()))
    def program_position(self,ms):
        if 'program' in self.clips and ms>=self.clips['program']['duration']*1000:self.program_player.pause()
    def reference_position(self,ms):
        if 'reference' in self.clips and ms>=self.clips['reference']['duration']*1000:self.reference_player.pause()
    def relink(self):
        if not self.current:return
        path,_=QFileDialog.getOpenFileName(self,'Reconnect original reference recording')
        if not path:return
        try:
            self.project.relink_reference(self.current,path)
            self.tracks={t['id']:t for t in self.project.tracks()};self.track_changed()
        except Exception as exc:QMessageBox.warning(self,'Reconnect reference',str(exc))
    def save(self):
        self.remember_gain();self.project.set('reference_gains',self.gains)
        if self.current:
            matches=self.project.get('cue_matches',{});matches[self.c['id']]={'track':self.current,'reference_start':self.offset.value(),'program_start':self.start.value()}
            self.project.set('cue_matches',matches)
    def shutdown(self):
        self.loading=None
        self.program_player.stop();self.reference_player.stop();self.program_player.setSource(QUrl());self.reference_player.setSource(QUrl())
        self.audio.shutdown()
