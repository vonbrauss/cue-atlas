"""Optional AI setup and review of cancellable selected/batch searches."""
import json
from pathlib import Path
from PySide6.QtCore import Qt,QUrl
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QProgressBar,QMessageBox,
    QTableWidgetItem,QComboBox,QCheckBox,QHeaderView)
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
from . import separation as ai
from .workflow_ui import table
from .ui_tables import batch_table_update
from .timecode import format_tc,parse


class AnalysisModeDialog(QDialog):
    def __init__(self,parent):
        super().__init__(parent);self.setWindowTitle('Analyze program');self.mode=None
        layout=QVBoxLayout(self);row=QHBoxLayout()
        for title,mode in [('Standard analysis','standard'),('Standard + AI follow-up','hybrid'),('Full-program AI separation','ai_separation')]:
            button=QPushButton(title);button.setAutoDefault(False)
            if mode=='hybrid':button.setObjectName('primary')
            button.clicked.connect(lambda checked=False,value=mode:self.choose(value));row.addWidget(button)
        layout.addLayout(row);cancel=QPushButton('Cancel');cancel.clicked.connect(self.reject);layout.addWidget(cancel)
    def choose(self,mode):self.mode=mode;self.accept()


class AISetupDialog(QDialog):
    def __init__(self,parent):
        super().__init__(parent);self.worker=None;self.setWindowTitle('AI music separation');self.resize(520,240)
        layout=QVBoxLayout(self)
        text=QLabel('Optional · local processing · Apple Silicon Macs\n447 MB model plus runtime libraries · about 1.6 GB installed')
        text.setWordWrap(True);layout.addWidget(text)
        self.state=QLabel();self.state.setWordWrap(True);layout.addWidget(self.state)
        self.progress=QProgressBar();self.progress.setStyleSheet('min-height:10px;max-height:10px;');self.progress.setTextVisible(False);self.progress.hide();layout.addWidget(self.progress)
        row=QHBoxLayout()
        self.install=QPushButton('Install');self.install.clicked.connect(self.start);row.addWidget(self.install)
        self.clear=QPushButton('Clear cached audio');self.clear.clicked.connect(self.clear_audio);row.addWidget(self.clear)
        self.remove=QPushButton('Uninstall');self.remove.clicked.connect(self.uninstall);row.addWidget(self.remove)
        self.close_button=QPushButton('Done');self.close_button.clicked.connect(self.done_or_cancel);row.addWidget(self.close_button)
        layout.addLayout(row);self.refresh()
    def refresh(self):
        busy=self.worker is not None;installed=ai.installed()
        if not busy:self.state.setText('Installed · ready for selected cues or all Unknown cues' if installed else 'Not installed')
        self.install.setEnabled(not busy and not installed);self.remove.setEnabled(not busy and (ai.home()/'engine').exists())
        self.clear.setEnabled(not busy and (ai.home()/'cache').exists());self.close_button.setText('Cancel' if busy else 'Done')
    def start(self):
        if self.worker is not None:return
        from .gui import Worker
        self.worker=Worker(ai.install_engine,None);self.worker.progress.connect(self.update_progress)
        self.worker.failure.connect(lambda message:QMessageBox.warning(self,'AI installation',message))
        self.worker.cancelled.connect(lambda:self.state.setText('Installation cancelled'))
        self.worker.finished.connect(self.installation_finished)
        self.state.setText('Starting installation…');self.progress.setRange(0,0);self.progress.show();self.refresh();self.worker.start()
    def update_progress(self,value,message):
        self.progress.setRange(0,0 if value<0 else 100)
        if value>=0:self.progress.setValue(round(value*100))
        self.state.setText(message)
    def installation_finished(self):
        worker=self.worker;self.worker=None;worker.deleteLater();self.progress.hide();self.refresh()
    def done_or_cancel(self):
        if self.worker:self.worker.requestInterruption();self.state.setText('Cancelling installation…')
        else:self.accept()
    def clear_audio(self):
        try:ai.clear_cache();self.refresh()
        except OSError as exc:QMessageBox.warning(self,'Cached audio',str(exc))
    def uninstall(self):
        if QMessageBox.question(self,'Uninstall AI separation?','Remove the optional AI model and runtime? Cue sheets and source recordings are preserved.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        try:ai.uninstall_engine();self.refresh()
        except OSError as exc:QMessageBox.warning(self,'AI separation',str(exc))
    def closeEvent(self,event):
        if self.worker:self.worker.requestInterruption();event.ignore();self.state.setText('Cancelling installation…')
        else:super().closeEvent(event)
    def reject(self):
        if self.worker:self.done_or_cancel()
        else:super().reject()


class AIResultsDialog(QDialog):
    def __init__(self,owner,result):
        super().__init__(owner);self.owner=owner;self.result=result;self.setWindowTitle('AI cue matches');self.resize(1050,550)
        self.player=QMediaPlayer(self);self.output=QAudioOutput(self);self.output.setVolume(.75);self.player.setAudioOutput(self.output);self.stop_at=None;self.playing=None
        self.player.positionChanged.connect(self.position_changed)
        layout=QVBoxLayout(self)
        prefix='Cancelled · completed results retained' if result.get('cancelled') else 'AI search complete'
        if result.get('hybrid'):prefix='Standard pass saved · '+prefix+f" · {result['unknown_searched']} Unknowns searched"
        self.summary=QLabel(prefix+f" · {len(result['items'])} results · merge requires adjoining reference positions to agree")
        self.summary.setWordWrap(True);layout.addWidget(self.summary)
        if result.get('failure'):
            error=QLabel(result['failure']);error.setWordWrap(True);layout.addWidget(error)
        self.table=table(['Apply','Cue / program in','Original match','AI match','Review','Use reference / version'])
        self.table.setStyleSheet('QTableView::indicator {width:15px;height:15px;border:1px solid #648580;border-radius:3px;background:#182427;} QTableView::indicator:checked {background:#79e2c4;border-color:#79e2c4;}')
        self.table.verticalHeader().setMinimumSectionSize(48);self.table.verticalHeader().setDefaultSectionSize(48)
        for column,width in [(1,175),(2,160),(3,160),(4,170)]:
            self.table.horizontalHeader().setSectionResizeMode(column,QHeaderView.Fixed);self.table.setColumnWidth(column,width)
        self.table.horizontalHeader().setSectionResizeMode(5,QHeaderView.Stretch)
        self.selectors=[];settings=owner.p.settings;origin=parse(settings['origin'],settings['rate'])
        with batch_table_update(self.table):
            self.table.setRowCount(len(result['items']))
            for row,entry in enumerate(result['items']):
                use=QTableWidgetItem();use.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable|Qt.ItemIsUserCheckable);use.setCheckState(Qt.Unchecked)
                self.table.setItem(row,0,use)
                self.table.setItem(row,1,QTableWidgetItem(entry['cue']['title']+' · '+format_tc(origin+entry['cue']['start'],settings['rate'])))
                for col,key in [(2,'original'),(3,'separated')]:
                    candidates=entry[key]
                    value=(candidates[0]['title']+f" · {candidates[0]['support']} points") if candidates else (entry.get('error') or ('Not processed' if entry.get('pending') and key=='separated' else 'No candidate'))
                    if key=='separated' and entry.get('not_separated'):value='Not run · version review'
                    cell=QTableWidgetItem(value);cell.setToolTip(value);self.table.setItem(row,col,cell)
                reason=entry.get('recommendation',{}).get('reason','Reference proposal');cell=QTableWidgetItem(reason);cell.setToolTip(reason);self.table.setItem(row,4,cell)
                from .versions import review_choices
                selector=QComboBox();choices=review_choices(entry)
                for candidate in choices:
                    if candidate.get('version_unresolved'):text=candidate['title']
                    elif candidate.get('comparison_only'):text=candidate['title']+' · Compare version'
                    else:
                        label='Original' if candidate in entry['original'] else 'AI'
                        text=f"{candidate['title']} · {label} · {candidate['support']}"
                        if any(n['track']==candidate['track'] for n in entry.get('neighbors',[])):text+=' · neighbor agrees'
                    selector.addItem(text,candidate)
                selector.setMinimumContentsLength(16);selector.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
                selector.setToolTip(selector.currentText());selector.currentTextChanged.connect(selector.setToolTip)
                selector.activated.connect(lambda index,r=row:self.table.selectRow(r))
                if not choices:use.setFlags(Qt.NoItemFlags)
                self.table.setCellWidget(row,5,selector);self.selectors.append(selector)
        layout.addWidget(self.table)
        all_matches=QCheckBox('Select all proposed matches');all_matches.toggled.connect(self.select_all);layout.addWidget(all_matches)
        all_matches.setStyleSheet('QCheckBox::indicator {width:15px;height:15px;border:1px solid #648580;border-radius:3px;background:#182427;} QCheckBox::indicator:checked {background:#79e2c4;border-color:#79e2c4;}')
        row=QHBoxLayout()
        for name,callback in [('Play original',lambda:self.play(False)),('Play music',lambda:self.play(True)),('Review candidate…',self.review),('Apply matches && merge',self.apply),('Close',self.reject)]:
            button=QPushButton(name);button.clicked.connect(callback);button.setAutoDefault(False);row.addWidget(button)
            if name=='Play original':self.original_button=button
            elif name=='Play music':self.music_button=button
            elif name=='Review candidate…':self.review_button=button
            elif name=='Apply matches && merge':self.apply_button=button
        layout.addLayout(row)
        self.table.currentCellChanged.connect(lambda r,c,oldr,oldc:self.selection_changed(r,oldr))
        self.table.itemChanged.connect(self.update_controls)
        self.player.playbackStateChanged.connect(self.update_controls)
        if result['items']:self.table.selectRow(0)
        self.update_controls()
    def select_all(self,value):
        with batch_table_update(self.table):
            for row,selector in enumerate(self.selectors):
                if selector.count() and selector.isEnabled():self.table.item(row,0).setCheckState(Qt.Checked if value else Qt.Unchecked)
        self.update_controls()
    def selection_changed(self,row,previous):
        if row!=previous:self.player.stop();self.playing=None
        self.update_controls()
    def update_controls(self,*args):
        row,entry=self.current();valid=entry is not None
        self.original_button.setEnabled(valid and Path(self.result['program'].get('path','')).is_file())
        self.music_button.setEnabled(valid and Path(entry.get('audio','')).is_file())
        self.review_button.setEnabled(valid and self.selectors[row].count()>0 and self.selectors[row].isEnabled())
        self.apply_button.setEnabled(any(self.table.item(r,0).checkState()==Qt.Checked and s.count()>0 and s.isEnabled() for r,s in enumerate(self.selectors)))
        playing=self.player.playbackState()==QMediaPlayer.PlayingState
        self.original_button.setText('Pause original' if playing and valid and self.playing==(entry['cue']['id'],False) else 'Play original')
        self.music_button.setText('Pause music' if playing and valid and self.playing==(entry['cue']['id'],True) else 'Play music')
    def current(self):
        row=self.table.currentRow()
        return (row,self.result['items'][row]) if 0<=row<len(self.result['items']) else (None,None)
    def play(self,music):
        _,entry=self.current()
        if not entry:return
        key=(entry['cue']['id'],music)
        if self.playing==key and self.player.playbackState()==QMediaPlayer.PlayingState:self.player.pause();return
        path=Path(entry.get('audio','')) if music else Path(self.result['program'].get('path',''))
        if not path.is_file():return
        start=0 if music else entry['cue']['start'];self.stop_at=(entry['cue']['end']-entry['cue']['start']) if music else entry['cue']['end']
        self.playing=key;self.player.setSource(QUrl.fromLocalFile(str(path)));self.player.setPosition(round(start*1000));self.player.play()
    def position_changed(self,millis):
        if self.stop_at is not None and millis/1000>=self.stop_at:self.player.pause()
    def review(self):
        row,entry=self.current()
        if entry is None or not self.selectors[row].count():return
        candidate=self.selectors[row].currentData();self.player.stop()
        current=next((c for c in self.owner.p.cues() if c['id']==entry['cue']['id']),None)
        if current!=entry['cue']:
            QMessageBox.information(self,'Cue changed','This cue changed after the search. Run AI analysis again.');return
        from .versions import review_choices
        proposal=candidate|{'version_candidates':[c for c in review_choices(entry) if c['track']],
                            'version_tracks':entry.get('recommendation',{}).get('version_tracks',[])}
        self.owner.edit_cue_dialog(current|{'track':candidate['track'],'title':candidate['title'],'status':'Needs review','confidence':0},proposal=proposal)
        current=next((c for c in self.owner.p.cues() if c['id']==entry['cue']['id']),None)
        if current!=entry['cue']:
            self.table.item(row,0).setCheckState(Qt.Unchecked);self.table.item(row,0).setFlags(Qt.NoItemFlags);self.selectors[row].setEnabled(False)
        self.update_controls()
    def apply(self):
        choices={entry['cue']['id']:self.selectors[row].currentData() for row,entry in enumerate(self.result['items'])
                 if self.table.item(row,0).checkState()==Qt.Checked and self.selectors[row].count() and self.selectors[row].isEnabled()}
        if not choices:return
        try:
            self.player.stop();joined=ai.apply_matches(self.owner.p,self.result,choices)
            self.owner.refresh(cues_only=True);self.owner.status.setText(f'{len(choices)} proposals applied · {joined} adjoining boundaries joined · Needs review')
            self.accept()
        except (ValueError,OSError) as exc:QMessageBox.warning(self,'AI matches',str(exc))
    def done(self,code):
        self.player.stop();self.player.setSource(QUrl());super().done(code)
