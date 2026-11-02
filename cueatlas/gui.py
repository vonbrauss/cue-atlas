import json
import sys
import sqlite3
from pathlib import Path
from PySide6.QtCore import Qt,QThread,Signal,QSettings,QUrl,QTimer,QItemSelectionModel,QSize,QEvent
from PySide6.QtGui import QColor,QPainter,QPen,QFont,QAction,QKeySequence,QIcon,QPixmap,QDesktopServices
from PySide6.QtWidgets import (QAbstractButton,QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QFileDialog,QMessageBox,QInputDialog,QTableWidget,QTableWidgetItem,QHeaderView,QTabWidget,
    QLineEdit,QDialog,QDialogButtonBox,QFormLayout,QComboBox,QDoubleSpinBox,QSpinBox,QTextEdit,
    QProgressBar,QSplitter,QFrame,QAbstractItemView,QMenu,QCheckBox,QScrollBar,QScrollArea,QLayout,QWidgetAction,QSizePolicy,QStyle,QTextBrowser)
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
from .project import Project,cue
from .ui_tables import batch_table_update
from . import __version__
from .engine import import_files,analyze,repair_coverage,import_library,identify_cue
from .audio import SUPPORTED,Cancelled,content_hash
from .metadata import FIELDS,parse_parties
from .enrichment import recovery_plan,enrichment_plan,apply_plan,party_credits
from .metadata_ui import PartiesEditor,MetadataPreview,MetadataImportDialog
from .json_metadata import metadata_import_plan,_sync_credits
from .timecode import RATES,format_tc,parse,clock
from .export import export,export_reference_library
from .coverage import covered_seconds
from .timeline import Timeline
from .playback import ReversePlayback
from .comparison import Comparison
from .matching import PRESETS,MATCH_KEYS
from .shortcuts import COMMANDS,DEFAULTS as SHORTCUT_DEFAULTS,load_bindings,event_key,canonical,ShortcutDialog
from .workflow import review_queue,restore_snapshot,save_marker,create_handoff,duplicate_report
from . import separation as ai
from . import monitor_audio as monitor


STYLE='''
QWidget { background:#101719; color:#dbe5e5; font-family:"Inter","Helvetica Neue","Arial"; font-size:13px; }
QMainWindow { background:#101719; }
QLabel { background:transparent; }
QPushButton#primary:disabled { background:#263b36; color:#66877d; }
QLabel#brand { font-size:23px; font-weight:700; color:#f3fbf9; }
QLabel#heading { font-size:22px; font-weight:650; color:#f3fbf9; }
QLabel#muted { color:#8caaaa; font-size:12px; }
QLabel#eyebrow { color:#70d9bf; font-size:11px; font-weight:700; letter-spacing:2px; }
QFrame#card { background:#172225; border:1px solid #293a3d; border-radius:12px; }
QPushButton { background:#223034; border:1px solid #34484b; border-radius:7px; padding:9px 15px; }
QPushButton:hover { background:#304347; border-color:#648580; }
QPushButton:disabled { color:#536769; background:#1a2528; border-color:#263437; }
QPushButton#primary { background:#79e2c4; color:#09271f; font-weight:700; border:0; }
QPushButton#primary:hover { background:#a0f1d9; }
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit { background:#182427; border:1px solid #35494c; border-radius:6px; padding:7px; selection-background-color:#326c5d; }
QTableWidget { background:#121c1f; alternate-background-color:#172225; border:1px solid #2a3b3f; border-radius:8px; gridline-color:#213034; selection-background-color:#254e46; selection-color:#e4fff5; }
QTableWidget::item { padding:8px; border-bottom:1px solid #213034; }
QHeaderView::section { background:#1b2a2e; color:#9bb7b6; border:0; padding:11px 8px; font-size:11px; font-weight:700; }
QTabWidget::pane { border:0; }
QTabBar::tab { background:#101719; color:#91a9aa; padding:12px 20px; margin-right:8px; border-bottom:2px solid transparent; }
QTabBar::tab:selected { color:#8be6cd; border-bottom:2px solid #79e2c4; }
QProgressBar { background:#213034; border:0; border-radius:3px; max-height:5px; }
QProgressBar::chunk { background:#79e2c4; border-radius:3px; }
QMenu { background:#1b2a2e; border:1px solid #40595a; padding:5px; }
QMenu::item { padding:7px 24px; }
QMenu::item:selected { background:#31584e; }
QScrollBar:vertical { background:#172225; width:10px; }
QScrollBar::handle:vertical { background:#395052; border-radius:5px; min-height:30px; }
QSplitter::handle { background:#293a3d; }
'''

def label(text,name=None):
    w=QLabel(text)
    if name:w.setObjectName(name)
    return w

def button(text,callback,primary=False):
    b=QPushButton(text);b.clicked.connect(callback)
    if primary:b.setObjectName('primary')
    return b

class Worker(QThread):
    progress=Signal(float,str);success=Signal(object);failure=Signal(str);cancelled=Signal()
    def __init__(self,fn,path,files=None):
        super().__init__();self.fn=fn;self.path=path;self.files=files
    def run(self):
        try:
            args=[self.path]+([self.files] if self.files is not None else [])
            result=self.fn(*args,progress=self.progress.emit,cancel=self.isInterruptionRequested)
            self.success.emit(result)
        except Cancelled:self.cancelled.emit()
        except Exception as e:self.failure.emit(str(e))

class SettingsDialog(QDialog):
    def __init__(self,project,parent):
        super().__init__(parent);self.setWindowTitle('Project settings');self.resize(480,440)
        if project is None:
            self.settings=None;self.setWindowTitle('Settings');self.resize(480,160);layout=QVBoxLayout(self)
            from .ai_ui import AISetupDialog
            ai_button=QPushButton('AI music separation…');ai_button.clicked.connect(lambda:AISetupDialog(self).exec());layout.addWidget(ai_button)
            buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
            return
        self.settings=project.settings;layout=QVBoxLayout(self);form=QFormLayout()
        self.rate=QComboBox();self.rate.addItems(RATES);self.rate.setCurrentText(self.settings['rate'])
        self.origin=QLineEdit(self.settings['origin']);form.addRow('Frame rate',self.rate);form.addRow('Program start TC',self.origin)
        self.sensitivity=QComboBox();self.sensitivity.addItems([*PRESETS,'Custom']);self.sensitivity.setCurrentText(self.settings['sensitivity_preset']);form.addRow('Detection sensitivity',self.sensitivity)
        self.values={}
        for key,title,low,high in [('min_cue','Minimum matched cue (seconds)',.3,30),('min_votes','Minimum fingerprint votes',5,200),('gap','Bridge matching gaps (seconds)',.1,5),('min_support','Minimum supporting landmarks',4,100),('silence_db','Silence gate (dBFS)',-100,-20),('reference_gain_db','Reference playback level (dB)',-60,0)]:
            spin=QDoubleSpinBox();spin.setRange(low,high);spin.setDecimals(0 if key in ('min_votes','min_support') else 2);spin.setValue(self.settings[key]);self.values[key]=spin;form.addRow(title,spin)
        self.sensitivity.currentTextChanged.connect(self.apply_sensitivity)
        for key in MATCH_KEYS:self.values[key].valueChanged.connect(self.custom_sensitivity)
        layout.addLayout(form)
        from .ai_ui import AISetupDialog
        ai_button=QPushButton('AI music separation…');ai_button.clicked.connect(lambda:AISetupDialog(self).exec());layout.addWidget(ai_button)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def apply_sensitivity(self,name):
        if name not in PRESETS:return
        for key,value in PRESETS[name].items():
            self.values[key].blockSignals(True);self.values[key].setValue(value);self.values[key].blockSignals(False)
    def custom_sensitivity(self,*args):
        selected=next((name for name,preset in PRESETS.items() if all(self.values[key].value()==value for key,value in preset.items())),'Custom')
        self.sensitivity.blockSignals(True);self.sensitivity.setCurrentText(selected);self.sensitivity.blockSignals(False)
    def accept(self):
        if self.settings is None:super().accept();return
        try:parse(self.origin.text(),self.rate.currentText())
        except ValueError as e:QMessageBox.warning(self,'Invalid timecode',str(e));return
        self.settings.update(rate=self.rate.currentText(),origin=self.origin.text(),sensitivity_preset=self.sensitivity.currentText(),**{k:v.value() for k,v in self.values.items()});super().accept()

class MetadataDialog(QDialog):
    def __init__(self,track,parent):
        super().__init__(parent);self.setWindowTitle('Reference metadata');self.resize(800,720);self.metadata=dict(track['metadata']);layout=QVBoxLayout(self)
        path=label(track['path'],'muted');path.setWordWrap(True);layout.addWidget(path)
        tabs=QTabWidget();edit=QWidget();form=QFormLayout(edit);self.inputs={}
        for field in FIELDS:
            entry=QLineEdit(str(self.metadata.get(field,'')));self.inputs[field]=entry;form.addRow(field.upper() if field in {'pro','isrc','iswc'} else field.replace('_',' ').title().replace(' Id',' ID').replace(' Url',' URL'),entry)
        raw=QTextEdit();raw.setReadOnly(True);raw.setPlainText(json.dumps(self.metadata.get('raw',{}),indent=2,ensure_ascii=False))
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(edit)
        self.initial_parties=self.metadata.get('parties') or parse_parties(self.metadata.get('composer',''),'composer')+parse_parties(self.metadata.get('publisher',''),'publisher')
        self.parties_editor=PartiesEditor(self.initial_parties,credit_text=self.metadata)
        if self.initial_parties and not self.inputs['pro'].text():self.inputs['pro'].setText(party_credits(self.initial_parties)['pro'])
        self.credit_text={field:self.inputs[field].text() for field in ('composer','publisher')}
        for field in ('composer','publisher'):
            self.inputs[field].setToolTip('Edit or clear this credit list; matching Rights parties are updated when you leave the field or Save.')
            self.inputs[field].editingFinished.connect(self.sync_credit_fields)
        self.inputs['pro'].setReadOnly(True);self.inputs['pro'].setToolTip('Edit each affiliation in the Rights parties tab.')
        tabs.addTab(scroll,'Cue sheet fields');tabs.addTab(self.parties_editor,'Rights parties');tabs.addTab(raw,'Original embedded tags')
        history=QTextEdit();history.setReadOnly(True);history.setPlainText(json.dumps(self.metadata.get('provenance',[]),indent=2,ensure_ascii=False));tabs.addTab(history,'Metadata sources');layout.addWidget(tabs)
        lookup=QPushButton('Find on APM…');lookup.setVisible(self.metadata.get('provider')=='APM Music' or 'APM Music' in str(self.metadata.get('raw',{})))
        lookup.clicked.connect(self.find_on_apm);layout.addWidget(lookup)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def sync_credit_fields(self):
        changes={field:self.inputs[field].text() for field in self.credit_text if self.inputs[field].text()!=self.credit_text[field]}
        if not changes:return True
        try:
            parties=self.parties_editor.values()
            updated=_sync_credits({'parties':parties},changes)
        except ValueError as exc:
            QMessageBox.warning(self,'Invalid rights party',str(exc));return False
        self.parties_editor.table.setRowCount(0)
        for party in updated['parties']:self.parties_editor.add(party)
        self.inputs['pro'].setText(party_credits(updated['parties'])['pro'])
        self.credit_text.update(changes)
        return True
    def find_on_apm(self):
        from urllib.parse import urlencode
        query=self.inputs['provider_track_id'].text().strip() or self.inputs['title'].text().strip()
        QDesktopServices.openUrl(QUrl('https://www.apmmusic.com/search?'+urlencode({'tab':'tracks','tincl':'"'+query+'"'})))
    def accept(self):
        if not self.sync_credit_fields():return
        try:parties=self.parties_editor.values()
        except ValueError as e:QMessageBox.warning(self,'Invalid rights party',str(e));return
        before=dict(self.metadata)
        self.metadata.update({k:v.text() for k,v in self.inputs.items()})
        self.metadata['parties']=parties;self.metadata.update(party_credits(parties))
        changed=[key for key in [*FIELDS,'parties'] if before.get(key)!=self.metadata.get(key)]
        if changed:
            from datetime import datetime,timezone
            self.metadata['provenance']=[*self.metadata.get('provenance',[]),{'source':'manual edit','retrieved_at':datetime.now(timezone.utc).isoformat(),'status':'user_edited','fields':changed}]
        super().accept()

class CueDialog(QDialog):
    def __init__(self,c,tracks,duration,parent,version_candidates=None):
        super().__init__(parent);self.setWindowTitle('Review cue');self.resize(500,350);self.c=dict(c);self.duration=duration
        layout=QVBoxLayout(self);form=QFormLayout();self.track=QComboBox();self.track.addItem('Unknown / unassigned',None)
        for t in tracks:self.track.addItem(t['metadata']['title'],t['id'])
        self.track.setCurrentIndex(max(0,self.track.findData(c['track'])))
        self.title=QLineEdit(c['title']);self.start=QDoubleSpinBox();self.end=QDoubleSpinBox()
        for widget,value in [(self.start,c['start']),(self.end,c['end'])]:widget.setRange(0,duration);widget.setDecimals(3);widget.setValue(value);widget.setSuffix(' s')
        self.status=QComboBox();self.status.addItems(['Needs review','Reviewed','Unknown']);self.status.setCurrentText(c['status'])
        self.notes=QLineEdit(c['note'])
        for name,widget in [('Reference',self.track),('Cue title',self.title),('Elapsed in',self.start),('Elapsed out (exclusive)',self.end),('Review status',self.status),('Notes',self.notes)]:form.addRow(name,widget)
        layout.addLayout(form)
        self.comparison=None
        if getattr(parent,'p',None):
            self.comparison=Comparison(c,tracks,parent.p,self.start,self.end,self.track,self,version_candidates=version_candidates);layout.addWidget(self.comparison)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.finished.connect(lambda *_:self.comparison.shutdown() if self.comparison else None)
    def accept(self):
        if self.end.value()<=self.start.value():QMessageBox.warning(self,'Invalid interval','Out must be later than in.');return
        tid=self.track.currentData()
        if tid and self.status.currentText()=='Unknown':self.status.setCurrentText('Needs review')
        version_pending=self.title.text().endswith(' · Version needs review')
        if not tid:self.status.setCurrentText('Needs review' if version_pending else 'Unknown')
        if tid and version_pending:
            self.title.setText(self.track.currentText())
            self.notes.setText('\n'.join(line for line in self.notes.text().splitlines() if not line.startswith(('Version needs review:','Song identified; recording version needs listening confirmation.'))))
        self.c.update(track=tid,title=self.title.text(),start=self.start.value(),end=self.end.value(),status=self.status.currentText(),note=self.notes.text())
        super().accept()

class MergeDialog(QDialog):
    def __init__(self,selected,tracks,parent):
        super().__init__(parent);self.setWindowTitle('Merge adjoining cues');self.resize(540,330)
        self.track=None;self.title='';self.note='';self.reviewed=False
        layout=QVBoxLayout(self);start=min(c['start'] for c in selected);end=max(c['end'] for c in selected)
        layout.addWidget(label(f"Join {len(selected)} cues into one · {clock(start)} → {clock(end)}"))
        form=QFormLayout();self.reference=QComboBox();self.reference.addItem('Unknown / unassigned',None)
        for t in tracks:self.reference.addItem(t['metadata']['title'],t['id'])
        known={c['track'] for c in selected if c['track']}
        if len(known)==1:self.reference.setCurrentIndex(self.reference.findData(next(iter(known))))
        self.title_input=QLineEdit('Unknown (merged)');self.notes=QLineEdit()
        form.addRow('Reference for joined cue',self.reference);form.addRow('Unknown cue title',self.title_input);form.addRow('Notes',self.notes);layout.addLayout(form)
        self.confirm=QCheckBox('I confirm this reference applies to the entire joined cue.');layout.addWidget(self.confirm)
        self.buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);self.buttons.button(QDialogButtonBox.Save).setText('Merge cues')
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.reference.currentIndexChanged.connect(self.reference_changed);self.confirm.toggled.connect(self.update_enabled);self.reference_changed()
    def reference_changed(self):
        known=self.reference.currentData() is not None
        self.confirm.setVisible(known);self.confirm.setChecked(False);self.title_input.setEnabled(not known);self.update_enabled()
    def update_enabled(self):
        self.buttons.button(QDialogButtonBox.Save).setEnabled(self.reference.currentData() is None or self.confirm.isChecked())
    def accept(self):
        self.track=self.reference.currentData();self.reviewed=self.track is not None and self.confirm.isChecked()
        if self.track is not None and not self.reviewed:return
        self.title=self.title_input.text();self.note=self.notes.text();super().accept()

class CueTable(QTableWidget):
    previewRequested=Signal()
    editNavigationRequested=Signal(int)
    mergeRequested=Signal();shuttleRequested=Signal(int);removeRequested=Signal()

    def keyPressEvent(self,event):
        if event.modifiers() & ~Qt.KeypadModifier==Qt.NoModifier and event.key() in (Qt.Key_Up,Qt.Key_Down):
            self.editNavigationRequested.emit(1 if event.key()==Qt.Key_Down else -1)
            event.accept();return
        if event.modifiers()==Qt.NoModifier and event.key() in (Qt.Key_Delete,Qt.Key_Backspace):
            if not event.isAutoRepeat():self.removeRequested.emit()
            event.accept();return
        if event.modifiers()==Qt.NoModifier and event.key() in (Qt.Key_J,Qt.Key_K,Qt.Key_L):
            if not event.isAutoRepeat():self.shuttleRequested.emit({Qt.Key_J:-1,Qt.Key_K:0,Qt.Key_L:1}[event.key()])
            event.accept();return
        if event.modifiers()==Qt.NoModifier and event.key() in (Qt.Key_Space,Qt.Key_M):
            if not event.isAutoRepeat():
                if event.key()==Qt.Key_Space:self.previewRequested.emit()
                else:self.mergeRequested.emit()
            event.accept();return
        super().keyPressEvent(event)

class Window(QMainWindow):
    projectRelocated=Signal(str,str)
    def __init__(self):
        super().__init__();self.setWindowTitle('Cue Atlas');self.resize(1240,850);self.setMinimumSize(950,650)
        self.reference_cache=None;self.reference_sort=None;self.cue_sort=(0,Qt.AscendingOrder)
        self.p=None;self.open_project_path=None;self.worker=None;self.track_rows=[];self.cue_rows=[];self.stop_at=None
        self.loop_start=None;self.audition_context=None;self._loop_seeking=False;self.loop_paused=False
        self.monitor_mode=False;self.monitor_descriptor=None;self._monitor_pending=None;self._switching_monitor=False
        self.reverse=ReversePlayback(self);self.shuttle_direction=0;self.shuttle_speed=1
        self.prefs=QSettings('CueAtlas','CueAtlas');self.recent=self.prefs.value('recent',[],type=list)
        self.favorite_projects=self.prefs.value('favorite_projects',[],type=list)
        self.shortcut_bindings=load_bindings(self.prefs)
        self.player=QMediaPlayer(self);self.output=QAudioOutput(self);self.output.setVolume(.75);self.player.setAudioOutput(self.output)
        self.player.positionChanged.connect(self.position_changed);self.player.errorOccurred.connect(self.monitor_playback_error)
        self.build_ui();self.build_menus();self.refresh()
        self.player.playbackStateChanged.connect(lambda *_:self.update_playback_ui())
        self.player.mediaStatusChanged.connect(self.media_status_changed)
        self.player.tracksChanged.connect(lambda:self.player.setActiveAudioTrack(0) if self.player.audioTracks() else None)
        self.reverse.positionChanged.connect(lambda seconds:self.position_changed(round(seconds*1000),reverse=True))
        self.reverse.stateChanged.connect(self.update_playback_ui);self.reverse.failed.connect(self.error)
        self.project_location_timer=QTimer(self);self.project_location_timer.setInterval(1000);self.project_location_timer.timeout.connect(self.check_project_location);self.project_location_timer.start()
        QApplication.instance().installEventFilter(self)
    def build_ui(self):
        root=QWidget();self.setCentralWidget(root)
        layout=QVBoxLayout(root);self.workspace_layout=layout;layout.setContentsMargins(14,10,14,10);layout.setSpacing(8)
        top=QHBoxLayout();top.addWidget(label('◈  Cue Atlas','brand'))
        self.project_heading=QWidget();heading=QHBoxLayout(self.project_heading);heading.setContentsMargins(10,0,0,0)
        self.heading=label('','muted');self.heading.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);heading.addWidget(self.heading)
        top.addWidget(self.project_heading,1);top.addStretch(1)
        self.project_button=button('Project ▾',self.project_menu);top.addWidget(self.project_button)
        self.review_queue_button=button('Review queue',self.show_review_queue);top.addWidget(self.review_queue_button)
        self.export_button=button('Export cue sheet',self.export_cues);top.addWidget(self.export_button)
        self.help_button=button('?',self.show_help);self.help_button.setFixedSize(32,32)
        self.help_button.setStyleSheet('QPushButton { padding:0; border-radius:16px; font-size:17px; font-weight:600; }')
        self.help_button.setToolTip('Help');self.help_button.setAccessibleName('Help');top.addWidget(self.help_button);layout.addLayout(top)
        self.workspace_splitter=QSplitter(Qt.Vertical);self.workspace_splitter.setChildrenCollapsible(False);layout.addWidget(self.workspace_splitter,1)
        card=QFrame();self.program_card=card;card.setMinimumHeight(240);card.setObjectName('card');cl=QVBoxLayout(card);cl.setContentsMargins(12,8,12,8);cl.setSpacing(6)
        row=QHBoxLayout();row.addWidget(label('PROGRAM','eyebrow'));self.program_label=label('No media','muted');self.program_label.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);row.addWidget(self.program_label,1)
        self.choose_button=button('Choose media',self.choose_program);row.addWidget(self.choose_button)
        self.analyze_button=button('Analyze',self.run_analysis,True);row.addWidget(self.analyze_button)
        self.monitor_button=QPushButton('Program audio');self.monitor_button.setToolTip('Switch between original program audio and cached AI music at the same playhead position');self.monitor_button.setCheckable(True);self.monitor_button.clicked.connect(self.toggle_monitor);row.addWidget(self.monitor_button)
        self.separate_range_button=button('Separate range',self.separate_timeline_range);self.separate_range_button.setToolTip('Separate I/O marks, Option/Alt-drag a range, or select cues. Cues are unchanged.');row.addWidget(self.separate_range_button)
        self.program_settings=QMenu('Program',self)
        self.choose_action=self.program_settings.addAction('Choose / relink audio or video…',self.choose_program)
        self.analyze_action=self.program_settings.addAction('Analyze program…',self.run_analysis)
        self.program_settings_button=QPushButton('⚙');self.program_settings_button.setToolTip('Program settings');self.program_settings_button.setMenu(self.program_settings);row.addWidget(self.program_settings_button)
        self.waveform_focus_button=self.focus_icon('Expand waveform',self.toggle_waveform_focus);row.addWidget(self.waveform_focus_button)
        cl.addLayout(row)
        self.timeline=Timeline();self.timeline.setMinimumHeight(85);self.timeline.seek.connect(self.seek);cl.addWidget(self.timeline,1)
        self.timeline.installEventFilter(self)
        self.timeline.selectionChanged.connect(self.select_timeline_cues)
        self.timeline.boundaryChanged.connect(self.trim_timeline_cue)
        self.timeline.trimToPlayheadRequested.connect(self.trim_to_playhead)
        self.timeline.editPointChanged.connect(self.adjust_timeline_edit)
        self.timeline.dragStarted.connect(self.on_drag_started)
        self.timeline.cueDrawn.connect(self.add_drawn_cue)
        self.timeline.boundaryFocused.connect(self.boundary_focused)
        self.timeline.nudgeRequested.connect(self.nudge_boundary)
        self.timeline.auditionRequested.connect(lambda:self.audition_transition(self.selected_edge))
        self.timeline.previewRequested.connect(self.preview_cue)
        self.timeline.shuttleRequested.connect(self.shuttle)
        self.timeline.playCueRequested.connect(self.play_cue)
        self.timeline.mergeRequested.connect(self.merge_selected)
        self.timeline.reviewRequested.connect(self.edit_cue)
        self.timeline.excludeRequested.connect(self.toggle_cue_exclusion)
        self.timeline.addRequested.connect(self.add_cue)
        self.timeline.removeRequested.connect(self.delete_cue)
        self.timeline.splitRequested.connect(self.split_selected_cue)
        self.timeline.separationRequested.connect(self.retry_with_separation)
        self.timeline.rangeChanged.connect(self.refresh_monitor_controls);self.timeline.rangeSeparationRequested.connect(self.separate_timeline_range)
        self.timeline.identifyRequested.connect(self.retry_selected_cue)
        zoom=QHBoxLayout()
        for title,fn in [('−',lambda:self.timeline.zoom(1/2)),('+',lambda:self.timeline.zoom(2)),('Fit',self.fit_timeline)]:
            zoom.addWidget(button(title,fn))
        self.timeline_scroll=QScrollBar(Qt.Horizontal);self.timeline_scroll.setRange(0,10000)
        self.timeline_scroll.valueChanged.connect(self.pan_timeline);zoom.addWidget(self.timeline_scroll,1)
        self.timeline.viewChanged.connect(self.timeline_view_changed)
        self.waveform_tools=QHBoxLayout();self.waveform_tools.setContentsMargins(0,0,0,0)
        self.cue_actions_button=QPushButton('Cues');self.cue_actions_menu=QMenu(self)
        for title,fn in [('Review…',self.edit_cue),('Merge selected…',self.merge_selected),('Exclude / Restore',self.toggle_cue_exclusion),('Add cue…',self.add_cue),('Delete selected cues…',self.delete_cue)]:self.cue_actions_menu.addAction(title,fn)
        self.retry_action=self.cue_actions_menu.addAction('Identify selected cue…',self.retry_selected_cue)
        self.split_action=self.cue_actions_menu.addAction('Split cue at playhead',self.split_selected_cue)
        self.ai_selected_action=self.cue_actions_menu.addAction('Reduce dialogue and retry…',self.retry_with_separation)
        self.cue_actions_button.setMenu(self.cue_actions_menu);self.waveform_tools.addWidget(self.cue_actions_button)
        self.waveform_excluded=QCheckBox('Excluded cues');self.waveform_excluded.toggled.connect(lambda checked:self.filter.setCurrentText('Excluded' if checked else 'All cues'));self.waveform_tools.addWidget(self.waveform_excluded)
        self.waveform_tools_widget=QWidget();self.waveform_tools_widget.setLayout(self.waveform_tools);self.waveform_tools_widget.hide();zoom.addWidget(self.waveform_tools_widget)
        cl.addLayout(zoom)
        transport=QHBoxLayout();self.play_button=button('▶ Play',self.toggle_play);transport.addWidget(self.play_button)
        self.position_label=label('00:00:00;00','muted');transport.addWidget(self.position_label)
        self.playback_label=label('Free playback','muted');self.playback_label.setWordWrap(True);transport.addWidget(self.playback_label,1)
        self.selected_edge='start'
        self.audition_button=button('Audition In',lambda:self.audition_transition(self.selected_edge));transport.addWidget(self.audition_button)
        self.audition_button.setToolTip('Audition selected edge')
        self.loop_button=button('Loop',self.toggle_transition_loop);self.loop_button.setCheckable(True);transport.addWidget(self.loop_button)
        self.loop_button.setToolTip('Loop selected edge')
        self.audition_options_button=QPushButton('⋯');self.audition_options_button.setToolTip('Audition options and frame adjustments')
        options=QMenu(self);self.audition_options_button.setMenu(options);transport.addWidget(self.audition_options_button)
        options.addAction('Audition cue In',lambda:self.audition_transition('start'))
        options.addAction('Audition cue Out',lambda:self.audition_transition('end'))
        options.addSeparator()
        options.addAction('Move edge back one frame  (,)',lambda:self.nudge_boundary(-1))
        options.addAction('Move edge forward one frame  (.)',lambda:self.nudge_boundary(1))
        radius_row=QWidget();radius_layout=QHBoxLayout(radius_row);radius_layout.addWidget(label('Seconds each side','muted'))
        self.audition_radius=QDoubleSpinBox();self.audition_radius.setRange(.1,10);self.audition_radius.setValue(2);self.audition_radius.setSuffix(' s');radius_layout.addWidget(self.audition_radius)
        radius_action=QWidgetAction(options);radius_action.setDefaultWidget(radius_row);options.addAction(radius_action)
        self.audition_radius.valueChanged.connect(self.audition_options_changed)
        cl.addLayout(transport)
        self.workspace_splitter.addWidget(card)
        self.tabs=QTabWidget();self.tabs.setMinimumHeight(180);self.workspace_splitter.addWidget(self.tabs)
        self.workspace_splitter.setStretchFactor(0,1);self.workspace_splitter.setStretchFactor(1,1)
        cues=QWidget();ql=QVBoxLayout(cues);ql.setContentsMargins(0,4,0,0)
        toolbar=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('Search cues');self.search.textChanged.connect(self.populate_cues);toolbar.addWidget(self.search,1)
        self.filter=QComboBox();self.filter.addItems(['All cues','Unknown','Needs review','Reviewed','Excluded']);self.filter.currentTextChanged.connect(self.populate_cues);toolbar.addWidget(self.filter)
        self.edit_button=button('Review cue',self.edit_cue);toolbar.addWidget(self.edit_button)
        self.merge_button=button('Merge selected',self.merge_selected);toolbar.addWidget(self.merge_button)
        self.exclude_button=button('Exclude',self.toggle_cue_exclusion);toolbar.addWidget(self.exclude_button)
        self.more_cues_button=QPushButton('More');more_cues=QMenu(self);self.more_cues_button.setMenu(more_cues)
        self.retry_table_action=more_cues.addAction('Identify selected cue…',self.retry_selected_cue)
        self.addcue_button=more_cues.addAction('Add cue…',self.add_cue)
        self.deletecue_button=more_cues.addAction('Delete selected cues…',self.delete_cue);toolbar.addWidget(self.more_cues_button)
        more_cues.addAction(self.split_action);more_cues.addAction(self.ai_selected_action)
        self.focus_button=self.focus_icon('Expand cue sheet',self.toggle_cue_focus);toolbar.addWidget(self.focus_button);ql.addLayout(toolbar)
        self.cue_table=self.table(['#','Track / cue','Program in','Program out','Duration','Evidence','Status']);self.cue_table.setSelectionMode(QAbstractItemView.ExtendedSelection);self.cue_table.itemSelectionChanged.connect(self.update_merge_button);self.cue_table.cellDoubleClicked.connect(lambda *_:self.edit_cue());ql.addWidget(self.cue_table)
        self.cue_table.previewRequested.connect(self.preview_cue)
        self.cue_table.installEventFilter(self)
        self.cue_table.editNavigationRequested.connect(self.timeline.jump_edit)
        self.cue_table.removeRequested.connect(self.delete_cue)
        self.cue_table.shuttleRequested.connect(self.shuttle)
        self.cue_table.mergeRequested.connect(lambda:self.merge_selected() if self.merge_button.isEnabled() else None)
        self.summary=label('No cues','muted');self.summary.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);ql.addWidget(self.summary)
        self.tabs.addTab(cues,'Cue sheet')
        refs=QWidget();rl=QVBoxLayout(refs);rl.setContentsMargins(0,8,0,0);rt=QHBoxLayout()
        self.addfolder_button=button('+ Music folder',self.add_folder,True);rt.addWidget(self.addfolder_button)
        self.addfiles_button=button('Add files',self.add_files);rt.addWidget(self.addfiles_button)
        self.importlibrary_button=button('Import library…',self.import_reference_library);rt.addWidget(self.importlibrary_button)
        self.reference_search=QLineEdit();self.reference_search.setPlaceholderText('Search references');self.reference_search.setClearButtonEnabled(True);self.reference_search.setMinimumWidth(100);self.reference_search.setAccessibleName('Search reference library');self.reference_search.textChanged.connect(self.populate_references);rt.addWidget(self.reference_search,1)
        self.metadata_menu=QMenu('Metadata',self)
        self.editmetadata_action=self.metadata_menu.addAction('Edit selected reference…',self.edit_metadata)
        self.metadata_menu.addSeparator()
        self.exportlibrary_action=self.metadata_menu.addAction('Export metadata JSON…',self.export_library_metadata)
        self.enrichmetadata_action=self.metadata_menu.addAction('Import metadata JSON…',self.import_library_metadata)
        self.metadata_menu.addSeparator()
        self.recovermetadata_action=self.metadata_menu.addAction('Recover embedded metadata…',self.recover_library_metadata)
        self.metadata_button=QPushButton('Metadata');self.metadata_button.setMenu(self.metadata_menu)
        self.metadata_button.setToolTip('Edit, export, import, or recover reference metadata');rt.addWidget(self.metadata_button)
        self.relink_button=button('Relink',self.relink_track);rt.addWidget(self.relink_button)
        self.removeref_button=button('Remove reference',self.remove_reference);rt.addWidget(self.removeref_button)
        self.reference_focus_button=self.focus_icon('Expand reference library',lambda:self.set_reference_focus(self.reference_focus_button.isChecked()));rt.addWidget(self.reference_focus_button);rl.addLayout(rt)
        self.reference_table=self.table(['Track','Artist','Composer','Publisher','Duration','Media']);self.reference_table.cellDoubleClicked.connect(lambda *_:self.edit_metadata());rl.addWidget(self.reference_table)
        self.tabs.addTab(refs,'Reference library')
        self.reference_summary=label('No references','muted');rl.addWidget(self.reference_summary)
        self.reference_table.horizontalHeader().sectionClicked.connect(lambda column:self.sort_table('reference',column))
        self.cue_table.horizontalHeader().sectionClicked.connect(lambda column:self.sort_table('cue',column))
        self.cue_table.horizontalHeader().setSortIndicator(0,Qt.AscendingOrder);self.cue_table.horizontalHeader().setSortIndicatorShown(True)
        bottom=QHBoxLayout();self.status=label('Ready','muted');self.status.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);bottom.addWidget(self.status,1)
        self.cancel_button=button('Cancel',self.cancel);self.cancel_button.hide();bottom.addWidget(self.cancel_button);layout.addLayout(bottom)
        self.progress=QProgressBar();self.progress.setTextVisible(False);self.progress.hide();layout.addWidget(self.progress)
    def focus_icon(self,title,callback):
        widget=QPushButton();widget.setCheckable(True);widget.setFixedSize(32,30);widget.setStyleSheet('QPushButton { padding: 4px; }')
        widget.setIconSize(QSize(18,18));widget.clicked.connect(callback);self.update_focus_icon(widget,False,title.removeprefix('Expand '))
        return widget
    def update_focus_icon(self,widget,focused,title):
        pixmap=QPixmap(20,20);pixmap.fill(Qt.transparent);painter=QPainter(pixmap);painter.setPen(QPen(QColor('#c4e4dd'),1.8))
        if focused:
            painter.drawRect(7,3,10,10);painter.drawRect(3,7,10,10)
        else:
            for x,y,dx,dy in [(3,3,1,1),(17,3,-1,1),(3,17,1,-1),(17,17,-1,-1)]:
                painter.drawLine(x,y,x+dx*5,y);painter.drawLine(x,y,x,y+dy*5)
        painter.end();widget.setIcon(QIcon(pixmap))
        widget.setToolTip(('Restore ' if focused else 'Expand ')+title);widget.setAccessibleName(widget.toolTip())
    def eventFilter(self,watched,event):
        if isinstance(watched,QAbstractButton) and watched.window() is self and event.type() in (QEvent.KeyPress,QEvent.KeyRelease) and event.key()==Qt.Key_Space and event.modifiers()==Qt.NoModifier:
            if event.type()==QEvent.KeyPress and not event.isAutoRepeat() and canonical(self.shortcut_bindings.get('play',''))==canonical('Space'):
                self.preview_cue()
            event.accept();return True
        if event.type()==QEvent.KeyPress and watched in (getattr(self,'timeline',None),getattr(self,'cue_table',None)):
            key=event_key(event)
            for command,label,default,context,repeat in COMMANDS:
                binding=self.shortcut_bindings.get(command,'')
                if binding and key==canonical(binding):
                    if self.timeline.drag:
                        if command=='cancel':self.timeline.cancel_drag()
                    elif (context=='Both' or watched is self.timeline) and (repeat or not event.isAutoRepeat()):
                        self.execute_editor_command(command)
                    event.accept();return True
            # Disable the old hardcoded handler after a default key is rebound.
            if key in {canonical(v) for v in SHORTCUT_DEFAULTS.values() if v}:
                event.accept();return True
        return super().eventFilter(watched,event)
    def execute_editor_command(self,command):
        if not self.p:return
        if not self.timeline.editable and command in {'trim_start','trim_end','merge','split','delete','exclude','identify','review','add_marker','new_cue','mark_in','mark_out','nudge_back','nudge_forward'}:return
        legacy={'frame_back':(Qt.Key_Left,Qt.NoModifier),'frame_forward':(Qt.Key_Right,Qt.NoModifier),
                'second_back':(Qt.Key_Left,Qt.ShiftModifier),'second_forward':(Qt.Key_Right,Qt.ShiftModifier),
                'home':(Qt.Key_Home,Qt.NoModifier),'end':(Qt.Key_End,Qt.NoModifier),
                'mark_in':(Qt.Key_I,Qt.NoModifier),'mark_out':(Qt.Key_O,Qt.NoModifier),
                'new_cue':(Qt.Key_N,Qt.NoModifier),'cancel':(Qt.Key_Escape,Qt.NoModifier),
                'fit':(Qt.Key_Backslash,Qt.NoModifier)}
        if command in legacy:self.editor_shortcut(*legacy[command]);return
        if command in ('clear_marks','clear_in','clear_out'):
            if command in ('clear_marks','clear_in'):self.timeline.mark_in=None
            if command in ('clear_marks','clear_out'):self.timeline.mark_out=None
            self.timeline.update();self.refresh_monitor_controls();return
        if command=='next_edit':self.timeline.jump_edit(1)
        elif command=='previous_edit':self.timeline.jump_edit(-1)
        elif command=='trim_start':self.trim_to_playhead('start')
        elif command=='trim_end':self.trim_to_playhead('end')
        elif command=='reverse':self.shuttle(-1)
        elif command=='pause':self.shuttle(0)
        elif command=='forward':self.shuttle(1)
        elif command=='play':self.preview_cue()
        elif command=='identify':self.retry_selected_cue()
        elif command=='review':self.edit_cue()
        elif command=='exclude':self.toggle_cue_exclusion()
        elif command=='merge':self.merge_selected()
        elif command=='split':self.split_selected_cue()
        elif command=='delete':self.delete_cue()
        elif command=='audition':self.audition_transition(self.selected_edge)
        elif command=='nudge_back':self.nudge_boundary(-1)
        elif command=='nudge_forward':self.nudge_boundary(1)
        elif command=='add_marker':self.add_marker_comment()
        elif command=='next_review':self.next_review_cue()
    def editor_shortcut(self,key,modifiers):
        t=self.timeline
        if not self.p or not t.duration:return
        if key in (Qt.Key_Left,Qt.Key_Right,Qt.Key_Home,Qt.Key_End):
            direction=1 if key==Qt.Key_Right else -1
            fps=RATES[self.p.settings['rate']][0]
            if key==Qt.Key_Home:point=0
            elif key==Qt.Key_End:point=t.duration
            elif modifiers & Qt.ShiftModifier:point=t.position+direction
            else:point=(round(t.position*fps)+direction)/fps
            point=max(0,min(t.duration,point));self.stop_audition();self.seek(point)
            if not t.view_start<=point<=t.view_start+t.view_span:t.set_view(point-t.view_span/2,t.view_span)
        elif key in (Qt.Key_I,Qt.Key_O):
            if not t.editable:return
            if key==Qt.Key_I:t.mark_in=t.position
            else:t.mark_out=t.position
            t.update();self.refresh_monitor_controls();self.status.setText(f'Marked {"In" if key==Qt.Key_I else "Out"} at {t.position:.3f} s')
        elif key==Qt.Key_N:
            if not t.editable:return
            if t.mark_in is None or t.mark_out is None or t.mark_out-t.mark_in<1/RATES[t.rate][0]-1e-8:
                self.status.setText('Set I and O marks at least one frame apart, with Out after In.');return
            if self.add_drawn_cue(t.mark_in,t.mark_out):t.mark_in=None;t.mark_out=None;t.update()
        elif key==Qt.Key_F:self.retry_selected_cue()
        elif key in (Qt.Key_Return,Qt.Key_Enter):self.edit_cue()
        elif key==Qt.Key_X:self.toggle_cue_exclusion()
        elif key==Qt.Key_Backslash:t.set_view(0,t.duration)
        elif key==Qt.Key_Escape:
            self.stop_audition();t.mark_in=None;t.mark_out=None;t.active_edit=None;t.current_id=None
            t.selected=set();self.select_timeline_cues([]);t.boundaryFocused.emit(None);t.update()
            self.refresh_monitor_controls()
    def table(self,headers):
        w=(CueTable if headers[0]=='#' else QTableWidget)(0,len(headers));w.setHorizontalHeaderLabels(headers);w.setAlternatingRowColors(True);w.setShowGrid(False)
        w.setSelectionBehavior(QAbstractItemView.SelectRows);w.setSelectionMode(QAbstractItemView.SingleSelection);w.setEditTriggers(QAbstractItemView.NoEditTriggers)
        w.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter);w.horizontalHeader().setSectionsClickable(True)
        w.verticalHeader().hide();w.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);w.horizontalHeader().setStretchLastSection(True);w.verticalHeader().setDefaultSectionSize(43)
        return w
    def build_menus(self):
        editmenu=self.menuBar().addMenu('Edit')
        self.undo_action=editmenu.addAction('Undo',self.undo_cue_edit);self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.redo_action=editmenu.addAction('Redo',self.redo_cue_edit);self.redo_action.setShortcuts([QKeySequence('Ctrl+Shift+Z'),QKeySequence('Ctrl+Y')])
        editmenu.addSeparator();editmenu.addAction('Keyboard shortcuts…',self.keyboard_shortcuts)
        menu=self.menuBar().addMenu('Project');self.projects_menu=menu
        menu.addSection('SWITCH PROJECTS')
        for title,fn,shortcut in [('New project…',self.new_project,'Ctrl+N'),('Open project…',self.open_project,'Ctrl+O'),('Browse projects…',self.manage_projects,None)]:
            action=menu.addAction(title,fn)
            if shortcut:action.setShortcut(QKeySequence(shortcut))
        self.recent_projects_menu=menu.addMenu('Recent projects')
        self.current_project_section=menu.addSection('CURRENT PROJECT')
        self.current_project_actions=[]
        for title,fn,shortcut in [('Project settings…',self.settings,'Ctrl+,'),('Rename project…',self.rename_project,None),('Backup project…',self.backup,None),('Recovery snapshots…',self.show_snapshots,None),('Close project',self.close_project,None)]:
            action=menu.addAction(title,fn);action.setMenuRole(QAction.NoRole)
            if fn==self.settings:self.project_settings_action=action
            else:self.current_project_actions.append(action)
            if shortcut:action.setShortcut(QKeySequence(shortcut))
        menu.addSection('DELIVER')
        for title,fn,shortcut in [('Export cue sheet…',self.export_cues,'Ctrl+E'),('Create handoff package…',self.handoff_project,None)]:
            action=menu.addAction(title,fn);self.current_project_actions.append(action)
            if shortcut:action.setShortcut(QKeySequence(shortcut))
        menu.aboutToShow.connect(self.update_project_menu)
        self.menuBar().addMenu(self.program_settings)
        librarymenu=self.menuBar().addMenu('Library')
        self.importlibrary_action=librarymenu.addAction('Import reference library…',self.import_reference_library)
        librarymenu.addAction('Reconnect selected reference…',self.relink_track)
        librarymenu.addSeparator()
        librarymenu.addMenu(self.metadata_menu)
        self.reference_focus_action=librarymenu.addAction('Focus reference library');self.reference_focus_action.setCheckable(True);self.reference_focus_action.triggered.connect(self.set_reference_focus)
        librarymenu.addAction('Reference duplicates and alternate mixes…',self.show_duplicates)
        cuesmenu=self.menuBar().addMenu('Cue sheet')
        self.focus_action=cuesmenu.addAction('Focus cue sheet');self.focus_action.setCheckable(True);self.focus_action.setShortcut(QKeySequence('Ctrl+Shift+F'));self.focus_action.triggered.connect(self.set_cue_focus)
        self.undo_merge_action=cuesmenu.addAction('Undo last merge',self.undo_last_merge)
        self.undo_boundary_action=cuesmenu.addAction('Undo boundary edit',self.undo_boundary_edit)
        self.undo_merge_action.setVisible(False);self.undo_boundary_action.setVisible(False)
        viewmenu=self.menuBar().addMenu('View')
        self.zoom_in_action=viewmenu.addAction('Zoom in',lambda:self.timeline.zoom(2))
        self.zoom_in_action.setShortcuts([QKeySequence('Ctrl++'),QKeySequence('Ctrl+='),QKeySequence('Ctrl+Shift+=')])
        self.zoom_out_action=viewmenu.addAction('Zoom out',lambda:self.timeline.zoom(.5))
        self.zoom_out_action.setShortcut(QKeySequence('Ctrl+-'))
        viewmenu.addAction('Fit program',lambda:self.timeline.set_view(0,self.timeline.duration))
        viewmenu.addAction('Fit selected cues',self.timeline.fit_selection)
        self.follow_action=viewmenu.addAction('Follow playhead');self.follow_action.setCheckable(True)
        self.timeline.follow_enabled=self.prefs.value('follow_playhead',True,type=bool);self.follow_action.setChecked(self.timeline.follow_enabled)
        self.follow_action.toggled.connect(self.set_follow_playhead)
        self.program_settings.addSeparator()
        self.snap_action=self.program_settings.addAction('Snap edits to playhead');self.snap_action.setCheckable(True)
        self.timeline.snap_enabled=self.prefs.value('snap_to_playhead',True,type=bool);self.snap_action.setChecked(self.timeline.snap_enabled)
        self.snap_action.toggled.connect(self.set_edit_snapping)
        self.repair_action=cuesmenu.addAction('Repair full-source coverage…',self.repair_source_coverage)
        cuesmenu.addSeparator()
        cuesmenu.addAction('Review queue…',self.show_review_queue)
        cuesmenu.addAction(self.split_action)
        cuesmenu.addAction(self.ai_selected_action)
        self.ai_unknown_action=cuesmenu.addAction('Analyze all Unknown cues with separation…',lambda:self.retry_with_separation(True))
        self.ai_results_action=cuesmenu.addAction('Review last AI results…',self.show_ai_results)
        cuesmenu.addAction('Next cue needing review',self.next_review_cue)
        cuesmenu.addAction('Validate cue sheet…',self.validate_cue_sheet)
        cuesmenu.addAction('Add marker at playhead…',self.add_marker_comment)
        cuesmenu.addAction('Markers and comments…',self.show_markers)
        helpmenu=self.menuBar().addMenu('Help');helpmenu.addAction('User guide…',lambda:self.show_help());helpmenu.addAction('Shortcut reference…',lambda:self.show_help('Keyboard shortcuts'));helpmenu.addAction('What’s new…',lambda:self.show_help('What’s new'));helpmenu.addSeparator();helpmenu.addAction('About Cue Atlas',lambda:QMessageBox.information(self,f'Cue Atlas {__version__}','Local project-scoped music identification.\n\nAutomatic cues are draft estimates for review. Unknown intervals can include silence and multiple tracks. Imported licensing tags are not proof of clearance.\n\nOpen-source notices: see THIRD_PARTY_NOTICES.md in the project.'))
    def show_help(self,topic='Start here'):
        from .help_window import HelpDialog
        dialog=getattr(self,'help_dialog',None)
        if dialog is None:
            dialog=HelpDialog(self,topic);self.help_dialog=dialog
            dialog.destroyed.connect(lambda:setattr(self,'help_dialog',None))
        else:dialog.open_topic(topic)
        dialog.show();dialog.raise_();dialog.activateWindow()
    def keyboard_shortcuts(self):
        dialog=ShortcutDialog(self.shortcut_bindings,self)
        if dialog.exec():
            self.shortcut_bindings=dialog.bindings()
            self.prefs.setValue('keyboard_shortcuts',json.dumps(self.shortcut_bindings))
            self.status.setText('Keyboard shortcuts saved. Help shows your current bindings.')
    def show_review_queue(self):
        if not self.p or not self.guard():return
        from .workflow_ui import ReviewQueueDialog
        dialog=getattr(self,'review_queue_dialog',None)
        if dialog and dialog.isVisible():dialog.raise_();dialog.activateWindow();return
        self.review_queue_dialog=ReviewQueueDialog(self);self.review_queue_dialog.show()
    def focus_cue(self,cue_id):
        if not self.p or self.busy():return False
        cue=next((c for c in self.p.cues() if c['id']==cue_id),None)
        if not cue:return False
        self.search.clear();self.filter.setCurrentText('Excluded' if cue_id in self.p.excluded_cue_ids() else 'All cues')
        self.timeline.current_id=cue_id;self.select_timeline_cues([cue_id])
        for row,c in enumerate(self.cue_rows):
            if c['id']==cue_id:self.cue_table.scrollToItem(self.cue_table.item(row,0));break
        import math
        if isinstance(cue['start'],(float,int)) and math.isfinite(cue['start']):
            point=max(0,min(self.timeline.duration,cue['start']));self.stop_audition();self.seek(point)
            if not self.timeline.view_start<=point<=self.timeline.view_start+self.timeline.view_span:
                self.timeline.set_view(point-self.timeline.view_span/2,self.timeline.view_span)
        return True
    def next_review_cue(self):
        if not self.p or not self.guard():return
        rows=review_queue(self.p)
        if not rows:self.status.setText('Review queue complete.');return
        current=self.timeline.current_id;ids=[c['id'] for c in rows]
        target=rows[(ids.index(current)+1)%len(rows)] if current in ids else next((c for c in rows if c['start']>=self.timeline.position),rows[0])
        self.focus_cue(target['id']);self.status.setText(f'{len(rows)} cues remaining · '+', '.join(target['reasons']))
    def validate_cue_sheet(self):
        if not self.p or not self.guard():return
        from .workflow_ui import ValidationDialog
        ValidationDialog(self).exec()
    def show_snapshots(self):
        if not self.p or not self.guard():return
        from .workflow_ui import SnapshotsDialog
        SnapshotsDialog(self).exec()
    def restore_recovery(self,path):
        if not self.p or not self.guard():return
        self.stop_audition();self.player.stop();restore_snapshot(self.p,path)
        self.timeline.set_source(None,0);self.search.clear();self.filter.setCurrentText('All cues')
        self.bind_player();self.refresh();self.status.setText('Recovery point restored; previous state saved as a new snapshot.')
    def add_marker_comment(self):self.edit_marker_comment()
    def edit_marker_comment(self,record=None):
        if not self.p or not self.guard():return
        if not self.timeline.duration:self.status.setText('Analyze the program before adding markers.');return
        from .workflow_ui import MarkerEditDialog
        dialog=MarkerEditDialog(self.p,self.timeline.position,record,self)
        if dialog.exec():
            try:
                save_marker(self.p,dialog.position.value(),dialog.text.toPlainText(),record['id'] if record else None)
                self.refresh();self.status.setText('Marker comment saved.')
            except Exception as exc:self.error(str(exc))
    def show_markers(self):
        if not self.p or not self.guard():return
        from .workflow_ui import MarkersDialog
        MarkersDialog(self).exec()
    def show_duplicates(self):
        if not self.p or not self.guard():return
        from .workflow_ui import DuplicatesDialog
        DuplicatesDialog(self).exec()
    def handoff_project(self):
        if not self.p or not self.guard():return
        from .workflow_ui import ValidationDialog,HandoffDialog
        if ValidationDialog(self,for_export=True).exec()!=QDialog.Accepted:return
        dialog=HandoffDialog(self)
        if dialog.exec():self.stop_audition();self.start_worker(create_handoff,dialog.options())
    def set_follow_playhead(self,enabled):
        self.timeline.follow_suspended=False
        self.timeline.follow_enabled=enabled;self.prefs.setValue('follow_playhead',enabled)
    def set_edit_snapping(self,enabled):
        self.timeline.snap_enabled=enabled;self.prefs.setValue('snap_to_playhead',enabled)
        if self.timeline.drag:self.timeline.drag['snapped_to_playhead']=False
        self.timeline.update()
    def sort_table(self,kind,column):
        attr='reference_sort' if kind=='reference' else 'cue_sort'
        previous=getattr(self,attr)
        order=Qt.DescendingOrder if previous and previous==(column,Qt.AscendingOrder) else Qt.AscendingOrder
        setattr(self,attr,(column,order))
        table=self.reference_table if kind=='reference' else self.cue_table
        table.horizontalHeader().setSortIndicator(column,order);table.horizontalHeader().setSortIndicatorShown(True)
        (self.populate_references if kind=='reference' else self.populate_cues)()
    def set_reference_focus(self,focused):
        if focused:
            if self.focus_button.isChecked():self.set_cue_focus(False)
            if self.waveform_focus_button.isChecked():self.set_waveform_focus(False)
        self.reference_focus_button.setChecked(focused);self.reference_focus_action.setChecked(focused)
        self.update_focus_icon(self.reference_focus_button,focused,'reference library')
        self.project_heading.setVisible(not focused);self.program_card.setVisible(not focused);self.tabs.tabBar().setVisible(not focused)
        if focused:self.tabs.setCurrentIndex(1);self.reference_table.setFocus()
    def toggle_cue_focus(self):self.set_cue_focus(self.focus_button.isChecked())
    def set_cue_focus(self,focused):
        if focused and self.reference_focus_button.isChecked():self.set_reference_focus(False)
        if focused and self.waveform_focus_button.isChecked():self.waveform_focus_button.setChecked(False);self.set_waveform_focus(False)
        self.focus_button.setChecked(focused);self.focus_action.setChecked(focused)
        self.update_focus_icon(self.focus_button,focused,'cue sheet')
        self.project_heading.setVisible(not focused);self.program_card.setVisible(not focused)
        self.tabs.tabBar().setVisible(not focused)
        if focused:
            self.tabs.setCurrentIndex(0)
            self.cue_table.setFocus()
            if not self.selected_cues() and self.cue_table.rowCount():self.cue_table.selectRow(0)
    def toggle_waveform_focus(self):self.set_waveform_focus(self.waveform_focus_button.isChecked())
    def set_waveform_focus(self,focused):
        if focused and self.reference_focus_button.isChecked():self.set_reference_focus(False)
        if focused and self.focus_button.isChecked():self.set_cue_focus(False)
        self.waveform_focus_button.setChecked(focused)
        self.update_focus_icon(self.waveform_focus_button,focused,'waveform')
        self.project_heading.setVisible(not focused);self.tabs.setVisible(not focused)
        self.timeline.setMinimumHeight(85)
        self.program_card.setMinimumHeight(240)
        self.waveform_tools_widget.setVisible(focused)
        if focused:self.timeline.setFocus()
    def timeline_view_changed(self,start,span):
        duration=self.timeline.duration;remaining=max(0,duration-span)
        self.timeline_scroll.blockSignals(True)
        self.timeline_scroll.setPageStep(max(1,int(10000*span/max(duration,1e-9))))
        self.timeline_scroll.setValue(int(start/max(remaining,1e-9)*10000));self.timeline_scroll.setEnabled(remaining>1e-8)
        self.timeline_scroll.blockSignals(False)
    def pan_timeline(self,value):
        self.timeline.pan(value/10000*max(0,self.timeline.duration-self.timeline.view_span))
    def select_timeline_cues(self,ids):
        current=self.timeline.current_id
        self.search.clear()
        self.filter.setCurrentText('Excluded' if self.timeline.show_excluded else 'All cues')
        self.cue_table.blockSignals(True);self.cue_table.clearSelection()
        for row,c in enumerate(self.cue_rows):
            if c['id'] in ids:
                index=self.cue_table.model().index(row,0)
                self.cue_table.selectionModel().select(index,QItemSelectionModel.Select|QItemSelectionModel.Rows)
                if c['id']==current:self.cue_table.selectionModel().setCurrentIndex(index,QItemSelectionModel.NoUpdate)
        self.cue_table.blockSignals(False);self.update_merge_button()
    def trim_timeline_cue(self,cue_id,start,end):
        if not self.p or not self.guard():return
        self.stop_audition()
        try:
            self.p.trim_cue(cue_id,start,end);self.refresh(cues_only=True)
            self.status.setText('Cue boundary saved')
        except ValueError as e:self.refresh(cues_only=True);self.error(str(e))
    def trim_to_playhead(self,edge):
        if not self.p or not self.guard() or self.timeline.drag:return
        position=self.timeline.position
        visible=self.timeline.visible_cues()
        selected=[c for c in visible if c['id'] in self.timeline.selected]
        # An explicit selection also permits extending its edge beyond the cue.
        targets=selected if selected else [c for c in visible if c['start']<position<c['end']]
        if len(targets)!=1:
            self.status.setText('Select one cue to trim or extend to the cursor.');return
        c=targets[0]
        if not 0<=position<=self.timeline.duration or (edge=='start' and position>=c['end']) or (edge=='end' and position<=c['start']):
            self.status.setText('The cue must retain a positive duration.');return
        self.trim_timeline_cue(c['id'],position if edge=='start' else c['start'],
                               position if edge=='end' else c['end'])
    def fit_timeline(self):
        if self.timeline.selected:self.timeline.fit_selection()
        else:self.timeline.set_view(0,self.timeline.duration)
    def boundary_focused(self,edit):
        self.selected_edge=edit['edge'] if edit else 'start'
        self.update_playback_ui()
    def on_drag_started(self):
        self.stop_audition()
    def add_drawn_cue(self,start,end):
        if not self.p or not self.guard():return
        duration=self.p.get('program',{}).get('duration',0)
        if not 0<=start<end<=duration:return
        new=cue(None,start,end,title='Untitled cue',note='Manually drawn cue.')
        self.stop_audition();self.p.save_cues(self.p.cues()+[new],label='Add cue')
        self.search.clear();self.filter.setCurrentText('All cues');self.refresh(cues_only=True)
        self.timeline.active_edit=None;self.timeline.current_id=new['id']
        self.select_timeline_cues([new['id']]);self.timeline.setFocus()
        self.status.setText('Cue added')
        return new['id']
    def adjust_timeline_edit(self,left_id,right_id,position,side):
        if not self.p or not self.guard():return
        self.stop_audition()
        try:
            self.p.adjust_edit_point(left_id,right_id,position,side);self.refresh(cues_only=True)
            self.status.setText(('Shared boundary rolled' if side=='roll' else f'{side} side trimmed')+' and saved.')
        except ValueError as e:self.refresh(cues_only=True);self.error(str(e))
    def undo_boundary_edit(self):
        if not self.p or not self.guard():return
        try:self.p.undo_trim();self.refresh(cues_only=True);self.status.setText('Previous cue boundaries restored.')
        except ValueError as e:self.error(str(e))
    def update_history_controls(self):
        if not hasattr(self,'undo_action'):return
        history=self.p.history_summary() if self.p else {'undo':None,'redo':None}
        for direction,action in [('undo',self.undo_action),('redo',self.redo_action)]:
            stack=history[direction];text=direction.title()+(' '+stack if stack else '')
            action.setText(text);action.setEnabled(bool(stack) and not self.busy())
    def undo_cue_edit(self):self.history_step('undo')
    def redo_cue_edit(self):self.history_step('redo')
    def history_step(self,direction):
        focus=QApplication.focusWidget()
        if isinstance(focus,(QLineEdit,QTextEdit)):
            getattr(focus,direction)();return
        if not self.p or not self.guard():return
        if self.timeline.drag:
            self.timeline.cancel_drag();self.status.setText('Boundary drag cancelled.');return
        self.stop_audition()
        try:
            before={c['id']:c for c in self.p.cues()};old_excluded=self.p.excluded_cue_ids()
            name=self.p.undo_edit() if direction=='undo' else self.p.redo_edit()
            after={c['id']:c for c in self.p.cues()}
            changed={cid for cid in before.keys()|after.keys() if before.get(cid)!=after.get(cid)}|(old_excluded^self.p.excluded_cue_ids())
            visible=changed & after.keys();excluded=self.p.excluded_cue_ids()
            self.search.clear();self.filter.setCurrentText('Excluded' if visible and visible<=excluded else 'All cues');self.refresh(cues_only=True)
            self.cue_table.clearSelection()
            for row,c in enumerate(self.cue_rows):
                if c['id'] in visible:self.cue_table.selectionModel().select(self.cue_table.model().index(row,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
            if visible:
                start=min(after[cid]['start'] for cid in visible)
                if not self.timeline.view_start<=start<=self.timeline.view_start+self.timeline.view_span:self.timeline.set_view(start,self.timeline.view_span)
            self.update_merge_button();self.status.setText(('Undid ' if direction=='undo' else 'Redid ')+name.lower()+'.')
        except ValueError as e:self.error(str(e))
    def busy(self):return self.worker is not None and self.worker.isRunning()
    def guard(self):
        if self.busy():QMessageBox.information(self,'Operation in progress','Finish or cancel the current operation first.');return False
        return True
    def project_menu(self):
        # The header and macOS menu bar share the same actions and state.
        self.projects_menu.exec(self.project_button.mapToGlobal(self.project_button.rect().bottomLeft()))
    def update_project_menu(self):
        menu=self.recent_projects_menu;menu.clear()
        paths=self.recent[:6]
        names=[Path(path).stem for path in paths]
        for path in paths:
            title=Path(path).stem
            if names.count(title)>1:title+=' — '+str(Path(path).parent)
            action=menu.addAction(title.replace('&','&&'));action.setToolTip(path)
            action.setCheckable(True);action.setChecked(bool(self.p and self.p.path==Path(path)))
            action.setEnabled(not self.busy())
            action.triggered.connect(lambda checked=False,p=path:self.load(p))
        if not paths:menu.addAction('No recent projects').setEnabled(False)
        menu.addSeparator();menu.addAction('Browse all projects…',self.manage_projects)
        self.current_project_section.setText(('CURRENT · '+self.p.get('name') if self.p else 'NO PROJECT OPEN').replace('&','&&'))
        for action in self.current_project_actions:action.setEnabled(bool(self.p) and not self.busy())
        self.project_settings_action.setEnabled(not self.busy())
    def set_project_favorite(self,path,favorite):
        self.favorite_projects=[p for p in self.favorite_projects if p!=path]
        if favorite:self.favorite_projects.append(path)
        self.prefs.setValue('favorite_projects',self.favorite_projects)
    def remember_project(self,path):
        path=str(Path(path).expanduser().absolute())
        self.recent=[path]+[p for p in self.recent if p!=path];self.prefs.setValue('recent',self.recent)
    def forget_project(self,path):
        if path in self.favorite_projects:self.set_project_favorite(path,False)
        self.recent=[p for p in self.recent if p!=path];self.prefs.setValue('recent',self.recent)
    def replace_project_location(self,old,new):
        old=str(old);new=str(new)
        if old==new:return
        if old in self.recent:
            self.recent=list(dict.fromkeys(new if path==old else path for path in self.recent));self.prefs.setValue('recent',self.recent)
        if old in self.favorite_projects:
            self.favorite_projects=list(dict.fromkeys(new if path==old else path for path in self.favorite_projects));self.prefs.setValue('favorite_projects',self.favorite_projects)
        self.projectRelocated.emit(old,new)
    def check_project_location(self):
        if not self.p or self.busy() or self.timeline.drag:return
        try:
            old=self.open_project_path or self.p.path;self.p.sync_path()
            if Path(old)!=self.p.path:
                self.open_project_path=self.p.path;self.replace_project_location(old,self.p.path);self.refresh()
        except (OSError,sqlite3.Error) as exc:self.status.setText('Project location unavailable: '+str(exc))
    def rename_project_file(self,path,name):
        if self.busy():raise ValueError('Finish or cancel the current operation before renaming a project.')
        path=Path(path).resolve();current=self.p and self.p.path==path
        p=self.p if current else Project(path)
        try:
            target=p.rename(name)
            if current:
                old=self.open_project_path or path;self.open_project_path=target;self.replace_project_location(old,target)
            if not current or path!=Path(old):self.replace_project_location(path,target)
            if current:self.refresh()
            return target
        finally:
            if not current:p.close()
    def manage_projects(self):
        if not self.guard():return
        from .projects import ProjectManager
        self.stop_audition();ProjectManager(self).exec()
    def close_project(self):
        if not self.guard():return
        self._monitor_pending=None;self.monitor_mode=False;self.monitor_descriptor=None;self.timeline.ai_regions=[]
        self.stop_audition();self.player.stop();self.player.setSource(QUrl());self.timeline.shutdown()
        if self.p:self.p.close()
        self.p=None;self.reference_cache=None;self.open_project_path=None;self.track_rows=[];self.cue_rows=[]
        self.cue_table.setRowCount(0);self.reference_table.setRowCount(0)
        self.timeline.cues=[];self.timeline.values=[];self.timeline.position=0;self.timeline.set_source(None,0)
        self.timeline.markers=[]
        self.timeline.selected=set();self.timeline.current_id=None;self.timeline.show_excluded=False
        self.search.clear();self.filter.setCurrentText('All cues');self.waveform_excluded.setChecked(False)
        self.set_reference_focus(False);self.set_cue_focus(False);self.set_waveform_focus(False)
        self.reference_search.clear();self.reference_summary.setText('No references')
        self.heading.setText('No project');self.heading.setToolTip('');self.program_label.setText('No media');self.program_label.setToolTip('')
        self.position_label.setText('00:00:00;00');self.summary.setText('No cues');self.setWindowTitle('Cue Atlas')
        self.refresh();self.status.setText('Project closed')
    def new_project(self):
        if not self.guard():return
        name,ok=QInputDialog.getText(self,'New project','Project name')
        if not ok or not name.strip():return
        safe=''.join(c if c.isalnum() or c in ' -_' else '_' for c in name.strip())
        path,_=QFileDialog.getSaveFileName(self,'Save project',str(Path.home()/'Documents'/f'{safe}.cueatlas'),'Cue Atlas project (*.cueatlas)')
        if not path:return
        if not path.endswith('.cueatlas'):path+='.cueatlas'
        try:p=Project(path,create=True,name=name.strip());p.close();self.load(path)
        except Exception as e:self.error(str(e))
    def open_project(self):
        if not self.guard():return
        path,_=QFileDialog.getOpenFileName(self,'Open project','','Cue Atlas project (*.cueatlas)')
        if path:self.load(path)
    def load(self,path):
        if not self.guard():return False
        try:
            p=Project(path)
            if self.p:self.p.close()
            self.p=p;self.reference_cache=None;self.open_project_path=p.path;self.remember_project(str(p.path))
            self.stop_audition();self.player.stop();self.bind_player();self.search.clear();self.reference_search.clear();self.filter.setCurrentText('All cues');self.refresh();self.status.setText('Project loaded')
            return True
        except Exception as e:self.error(str(e));return False
    def monitor_path(self):
        if self.monitor_mode and self.monitor_descriptor and Path(self.monitor_descriptor['path']).is_file():return self.monitor_descriptor['path']
        return self.p.get('program',{}).get('path') if self.p else None
    def selected_audio_range(self):
        t=self.timeline
        if t.mark_in is not None and t.mark_out is not None and t.mark_out>t.mark_in:return [t.mark_in,t.mark_out]
        cues=self.selected_cues()
        return [min(c['start'] for c in cues),max(c['end'] for c in cues)] if cues else None
    def refresh_monitor_controls(self):
        active=bool(self.p and self.p.get('program',{}).get('duration') and not self.busy())
        self.monitor_button.setEnabled(active);self.separate_range_button.setEnabled(active and self.selected_audio_range() is not None)
        self.monitor_button.setChecked(self.monitor_mode);self.monitor_button.setText('AI music' if self.monitor_mode else 'Program audio')
    def separate_timeline_range(self):
        if not self.p or not self.guard():return
        interval=self.selected_audio_range()
        if interval is None:self.status.setText('Mark I/O or Option-drag a range to separate.');return
        if not ai.installed():
            from .ai_ui import AISetupDialog
            AISetupDialog(self).exec()
            if not ai.installed():return
        self.stop_audition();self.start_worker(monitor.timeline_audio,{'range':interval})
    def toggle_monitor(self,enabled):
        if not self.p or not self.guard():self.refresh_monitor_controls();return
        if enabled:
            self.monitor_descriptor=monitor.descriptor(self.p.get('program',{}))
            if not self.monitor_descriptor:
                self.refresh_monitor_controls();self.start_worker(monitor.timeline_audio,{});return
        self.set_monitor_mode(enabled)
    def set_monitor_mode(self,enabled):
        if enabled and not self.monitor_descriptor:return
        position=self.timeline.position;playing=self.player.playbackState()==QMediaPlayer.PlayingState
        reverse=self.reverse.active;rate=self.shuttle_speed if reverse else self.player.playbackRate()
        if self._monitor_pending:
            playing=self._monitor_pending['playing'];reverse=self._monitor_pending['reverse'];rate=self._monitor_pending['rate']
        self._switching_monitor=True;self.reverse.stop();self.player.pause();self.monitor_mode=enabled
        path=self.monitor_path();self._monitor_pending={'position':position,'playing':playing,'reverse':reverse,'rate':rate,'path':path}
        self.player.setSource(QUrl.fromLocalFile(path) if path else QUrl());self.player.setPosition(round(position*1000))
        self.timeline.position=position;self._switching_monitor=False
        self.refresh(cues_only=True)
        if self.player.mediaStatus() in (QMediaPlayer.LoadedMedia,QMediaPlayer.BufferedMedia):self.finish_monitor_switch()
        self.refresh_monitor_controls();self.update_playback_ui()
    def finish_monitor_switch(self):
        pending=self._monitor_pending
        if not pending or self._switching_monitor:return
        self._switching_monitor=True;self.player.setPosition(round(pending['position']*1000));self.player.setPlaybackRate(pending['rate'])
        self.timeline.position=pending['position'];self._monitor_pending=None;self._switching_monitor=False
        if pending['reverse']:self.reverse.start(pending['path'],pending['position'],pending['rate'])
        elif pending['playing']:self.player.play()
        self.update_playback_ui()
    def monitor_playback_error(self,*args):
        message=self.player.errorString();self._monitor_pending=None
        if self.monitor_mode:self.set_monitor_mode(False)
        self.status.setText('Playback: '+message)
    def bind_player(self):
        self.stop_audition()
        program=self.p.get('program',{}) if self.p else {}
        self._monitor_pending=None;self.monitor_mode=False;self.monitor_descriptor=monitor.descriptor(program) if program.get('path') else None
        self.player.setSource(QUrl.fromLocalFile(program['path']) if program.get('path') and Path(program['path']).is_file() else QUrl())
        self.timeline.position=0
    def rename_project(self):
        if not self.p or not self.guard():return
        name,ok=QInputDialog.getText(self,'Rename project','Project name',text=self.p.get('name'))
        if ok and name.strip():
            try:self.rename_project_file(self.p.path,name)
            except Exception as exc:self.error(str(exc))
    def backup(self):
        if not self.p or not self.guard():return
        path,_=QFileDialog.getSaveFileName(self,'Backup project',str(self.p.path.with_stem(self.p.path.stem+'-backup')),'Cue Atlas project (*.cueatlas)')
        if path:
            try:self.p.backup(path);self.status.setText('Project backup saved. Original media is referenced, not included.')
            except Exception as e:self.error(str(e))
    def settings(self):
        if not self.guard():return
        dialog=SettingsDialog(self.p,self)
        if dialog.exec() and self.p:
            old=self.p.settings;self.p.set('settings',dialog.settings)
            if any(old[k]!=dialog.settings[k] for k in [*MATCH_KEYS,'silence_db']) and self.p.cues():self.p.set('stale',True)
            self.refresh()
        self.refresh_controls()
    def choose_program(self):
        if not self.p or not self.guard():return
        path,_=QFileDialog.getOpenFileName(self,'Choose program audio or video','','Audio / video (*.wav *.wave *.mp3 *.aif *.aiff *.flac *.m4a *.mp4 *.mov *.mxf);;All files (*)')
        if not path:return
        old=self.p.get('program',{})
        if self.p.cues():
            answer=QMessageBox.question(self,'Replace or relink program?','Keep the existing cues and relink to this file?\nChoose No to clear cues for a different program.',QMessageBox.Yes|QMessageBox.No|QMessageBox.Cancel)
            if answer==QMessageBox.Cancel:return
            if answer==QMessageBox.No:
                self.p.snapshot('Before replacing program and clearing cues',force=True);self.p.save_cues([],maintain_coverage=False);old={}
        old['path']=path;self.p.set('program',old);self.p.set('stale',True);self.bind_player();self.refresh()
    def add_folder(self):
        if not self.p or not self.guard():return
        folder=QFileDialog.getExistingDirectory(self,'Reference music folder')
        if folder:
            files=sorted(str(p) for p in Path(folder).rglob('*') if p.is_file() and p.suffix.lower() in SUPPORTED)
            if files:self.start_worker(import_files,files)
            else:QMessageBox.information(self,'No music files','No supported audio files were found in this folder.')
    def add_files(self):
        if not self.p or not self.guard():return
        files,_=QFileDialog.getOpenFileNames(self,'Reference music','','Audio (*.wav *.wave *.mp3 *.aif *.aiff *.flac *.m4a);;All files (*)')
        if files:self.start_worker(import_files,files)
    def run_analysis(self):
        if not self.p or not self.guard():return
        from .ai_ui import AnalysisModeDialog,AISetupDialog
        dialog=AnalysisModeDialog(self)
        if not dialog.exec():return
        use_ai=dialog.mode in ('ai_separation','hybrid')
        if self.p.cues() and QMessageBox.question(self,'Replace analysis?','Analysis replaces the current cues, including manual edits and exclusions. Save a project backup first if you need to preserve them. Continue?')!=QMessageBox.Yes:return
        if use_ai and not ai.installed():
            AISetupDialog(self).exec()
            if not ai.installed():return
        self.stop_audition();self.start_worker(ai.hybrid_analysis if dialog.mode=='hybrid' else (ai.analyze_program if use_ai else analyze))
    def import_reference_library(self):
        if not self.p or not self.guard():return
        path,_=QFileDialog.getOpenFileName(self,'Import reference library from project','','Cue Atlas project (*.cueatlas)')
        if path:self.start_worker(import_library,path)
    def recover_library_metadata(self):
        if not self.p or not self.guard():return
        try:
            plan=recovery_plan(self.p)
            if MetadataPreview(plan,[],self).exec()==QDialog.Accepted:
                count=apply_plan(self.p,plan);self.refresh();self.status.setText(f'Recovered embedded metadata · {count} references updated')
        except Exception as e:self.error(str(e))
    def import_library_metadata(self):
        if not self.p or not self.guard():return
        path,_=QFileDialog.getOpenFileName(self,'Import reference metadata JSON','','JSON (*.json)')
        if not path:return
        try:
            options=MetadataImportDialog(path,self)
            if options.exec()!=QDialog.Accepted:return
            mode=options.mode.currentData()
            plan,skipped=metadata_import_plan(self.p,path,mode)
            if MetadataPreview(plan,skipped,self,mode=mode).exec()==QDialog.Accepted:
                count=apply_plan(self.p,plan);self.refresh();self.status.setText(f'Imported metadata · {count} references updated · {len(skipped)} entries skipped')
        except Exception as e:self.error(str(e))
    def export_library_metadata(self):
        if not self.p or not self.guard():return
        default=self.p.path.with_name(self.p.path.stem+'-reference-library.json')
        path,_=QFileDialog.getSaveFileName(self,'Export reference library metadata',str(default),'JSON (*.json)')
        if not path:return
        try:
            if Path(path).suffix.lower()!='.json':path+='.json'
            count=export_reference_library(self.p,path)
            self.status.setText(f'Reference library metadata exported · {count} references · {path}')
        except Exception as e:self.error(str(e))
    def start_worker(self,fn,files=None):
        self.worker=Worker(fn,str(self.p.path),files);self.worker.progress.connect(self.on_progress)
        self.worker.success.connect(self.on_success);self.worker.failure.connect(self.error);self.worker.cancelled.connect(lambda:self.status.setText('Audio separation cancelled; cues and original audio were preserved.' if fn is monitor.timeline_audio else 'Analysis cancelled; any completed standard pass and follow-up results were kept.' if fn is ai.hybrid_analysis else 'AI analysis cancelled; previous cues were preserved. Completed music remains cached.' if fn is ai.analyze_program else 'AI search cancelled; cues were preserved. Review last AI results for completed work.' if fn is ai.analyze_separated else ('Handoff cancelled; no package was created.' if fn is create_handoff else ('Cue search cancelled' if fn is identify_cue else ('Library import cancelled. No references were added.' if fn is import_library else 'Cancelled. Completed reference imports were kept; previous analysis was preserved.')))))
        self.worker.finished.connect(self.worker_finished);self.progress.show();self.cancel_button.show();self.worker.start();self.refresh_controls()
    def on_progress(self,value,message):self.progress.setValue(int(value*100));self.status.setText(message)
    def on_success(self,result):
        if result.get('timeline_audio'):
            self._monitor_ready=result['preview'];self.status.setText('AI timeline audio ready')
        elif result.get('ai_batch'):
            self.ai_result=result if result['items'] or result.get('failure') or result.get('cancelled') else None
            self.status.setText('Follow-up results ready for review' if self.ai_result else 'Standard pass saved · no Unknown cues need AI follow-up')
        elif result.get('handoff'):
            self.status.setText(f"Handoff created · {result['missing']} missing media · {result['path']}")
            QMessageBox.information(self,'Handoff ready',f"Saved to:\n{result['path']}\n\n{result['missing']} requested media files were missing. See manifest.json for details.")
        elif result.get('cue_retry'):
            self.retry_result=result;self.status.setText(f"Cue search complete · {len(result['candidates'])} candidates")
        elif result.get('repaired'):
            self.search.clear();self.filter.setCurrentText('All cues')
            self.status.setText(f"Full-source coverage repaired · {result['added']} unknown intervals added · reviewed cues preserved")
        elif result.get('library_import'):
            self.status.setText(f"Imported {result['added']} references from project · {result['skipped']} duplicates skipped · existing metadata and cues preserved")
        elif 'added' in result:
            self.status.setText(f"Indexed {result['added']} references · {result['skipped']} unchanged · {len(result['failures'])} failed")
            if result['failures']:QMessageBox.warning(self,'Some files could not be imported','\n'.join(result['failures'])[:8000])
            if result.get('duplicates'):QMessageBox.information(self,'Duplicate recordings skipped','\n'.join(result['duplicates'])[:8000])
        else:
            self.search.clear();self.filter.setCurrentText('All cues')
            self.status.setText(f"{'AI analysis' if result.get('ai_analysis') else 'Analysis'} complete · {result['cues']} cues")
    def worker_finished(self):
        old=self.worker;kind=old.fn;self.worker=None;old.deleteLater();self.progress.hide();self.cancel_button.hide();self.refresh(cues_only=kind in (identify_cue,ai.analyze_separated,monitor.timeline_audio))
        result=getattr(self,'retry_result',None);self.retry_result=None
        if result:self.review_retry_result(result)
        result=getattr(self,'ai_result',None);self.ai_result=None
        if result:self.show_ai_results(result)
        ready=getattr(self,'_monitor_ready',None);self._monitor_ready=None
        if ready:self.monitor_descriptor=ready;self.set_monitor_mode(True)
    def cancel(self):
        if self.worker:self.worker.requestInterruption();self.cancel_button.setEnabled(False);self.status.setText('Cancelling…')
    def refresh_controls(self):
        active=bool(self.p) and not self.busy()
        program=self.p.get('program',{}) if self.p else {}
        analyzed=bool(self.p and (self.p.get('analysis_settings') or program.get('decoded_duration') or self.p.cues()))
        self.choose_button.setVisible(not bool(program.get('path')))
        self.analyze_button.setVisible(bool(program.get('path')) and not analyzed)
        self.choose_action.setEnabled(active);self.analyze_action.setEnabled(active and bool(program.get('path')) and bool(self.p.db.execute('SELECT 1 FROM tracks LIMIT 1').fetchone()) if self.p else False)
        self.timeline.editable=active
        self.review_queue_button.setEnabled(active)
        self.review_queue_button.setText(f'Review queue · {len(review_queue(self.p))}' if self.p else 'Review queue')
        for index in range(self.waveform_tools.count()):
            widget=self.waveform_tools.itemAt(index).widget()
            if widget:widget.setEnabled(active)
        self.undo_boundary_action.setEnabled(active and bool(self.p.get('undo_trim')) if self.p else False)
        self.importlibrary_button.setEnabled(active);self.importlibrary_action.setEnabled(active)
        self.exportlibrary_action.setEnabled(active);self.editmetadata_action.setEnabled(active)
        self.recovermetadata_action.setEnabled(active);self.enrichmetadata_action.setEnabled(active)
        for w in [self.choose_button,self.analyze_button,self.addfolder_button,self.addfiles_button,self.metadata_button,self.removeref_button,self.relink_button,self.edit_button,self.addcue_button,self.deletecue_button,self.export_button]:w.setEnabled(active)
        self.cancel_button.setEnabled(True)
        self.repair_action.setEnabled(active and bool(self.p.get('program')) if self.p else False)
        self.undo_merge_action.setEnabled(active and bool(self.p.get('undo_merge')) if self.p else False)
        self.update_merge_button()
        self.refresh_monitor_controls()
        if active:
            self.analyze_button.setEnabled(bool(self.p.db.execute('SELECT 1 FROM tracks LIMIT 1').fetchone()) and bool(self.p.get('program')))
            self.export_button.setEnabled(bool(self.p.included_cues()))
        self.play_button.setEnabled(bool(self.p and self.p.get('program')))
        self.update_history_controls()
    def refresh(self,cues_only=False):
        if self.p:
            old=self.open_project_path or self.p.path;self.p.sync_path();self.open_project_path=self.p.path;self.replace_project_location(old,self.p.path)
        self.refresh_controls()
        if not self.p:return
        self.heading.setText(self.p.get('name'));self.setWindowTitle(self.p.get('name')+' · Cue Atlas');self.project_button.setText('Project  ▾')
        all_tracks=self.reference_cache[0] if cues_only and self.reference_cache is not None else self.p.tracks();cues=self.p.cues();program=self.p.get('program',{})
        self.heading.setToolTip(f"{len(all_tracks)} references  /  {len(cues)} cues  /  {self.p.settings['rate']}  /  Auto-saved"+('  /  Reanalysis recommended' if self.p.get('stale') else ''))
        name=Path(program['path']).name if program else 'No program selected'
        if program and not Path(program['path']).is_file():name+=' · Missing media'
        elif program and 'size' in program:
            st=Path(program['path']).stat()
            if st.st_size!=program['size'] or st.st_mtime_ns!=program['mtime']:name+=' · Media changed'
        self.program_label.setText(name);self.program_label.setToolTip(program.get('path',''))
        if self.monitor_mode and (not self.monitor_descriptor or not Path(self.monitor_descriptor['path']).is_file()):self.set_monitor_mode(False);return
        self.timeline.values=self.monitor_descriptor['waveform'] if self.monitor_mode else program.get('waveform',[])
        self.timeline.ai_regions=self.monitor_descriptor.get('regions',[]) if self.monitor_descriptor and Path(self.monitor_descriptor['path']).is_file() else []
        self.timeline.rate=self.p.settings['rate'];self.timeline.origin=self.p.settings['origin']
        identity=(program.get('path'),program.get('duration',0),program.get('size'),program.get('mtime'))
        self.timeline.set_source(self.monitor_path(),program.get('duration',0),(self.monitor_path(),program.get('size'),program.get('mtime')),identity=identity)
        titles={t['id']:t['metadata'].get('title','') for t in all_tracks}
        excluded=self.p.excluded_cue_ids()
        self.timeline.cues=[c|{'excluded':c['id'] in excluded,'display_title':titles.get(c['track'],c['title'])} for c in cues];self.timeline.update()
        self.timeline.markers=self.p.get('markers',[])
        if not cues_only or self.reference_cache is None:
            self.cache_references(all_tracks);self.populate_references()
        settings=self.p.settings
        self.position_label.setText(format_tc(parse(settings['origin'],settings['rate'])+self.timeline.position,settings['rate']))
        self.populate_cues()
    def cache_references(self,all_tracks):
        flags={}
        for pair in duplicate_report(all_tracks):
            for tid in (pair['left'],pair['right']):flags.setdefault(tid,set()).add(pair['kind'])
        states={}
        for t in all_tracks:
            try:
                stat=Path(t['path']).stat();state='Available'
                if stat.st_size!=t['size'] or stat.st_mtime_ns!=t['mtime']:state='Changed · reimport'
            except OSError:state='Missing'
            if t['id'] in flags:state+=' · '+', '.join(sorted(flags[t['id']]))
            states[t['id']]=state
        texts={t['id']:(' '.join(str(t['metadata'].get(field,'')) for field in FIELDS)+' '+t['path']+' '+states[t['id']]).casefold() for t in all_tracks}
        self.reference_cache=(all_tracks,states,texts)
    def populate_references(self):
        if not self.p:return
        selected=self.selected_track();selected_id=selected['id'] if selected else None
        if self.reference_cache is None:self.cache_references(self.p.tracks())
        all_tracks,states,texts=self.reference_cache
        query=self.reference_search.text().strip().casefold()
        self.track_rows=[t for t in all_tracks if not query or query in texts[t['id']]]
        if self.reference_sort:
            column,order=self.reference_sort
            def key(t):
                m=t['metadata']
                return [str(m.get('title','')).casefold(),str(m.get('artist','')).casefold(),str(m.get('composer','')).casefold(),str(m.get('publisher','')).casefold(),t['duration'],states[t['id']].casefold()][column]
            self.track_rows.sort(key=key,reverse=order==Qt.DescendingOrder)
        with batch_table_update(self.reference_table):
            self.reference_table.setRowCount(len(self.track_rows));self.reference_table.clearSelection();self.reference_table.setCurrentCell(-1,-1)
            for row,t in enumerate(self.track_rows):
                m=t['metadata'];values=[m.get('title',''),m.get('artist',''),m.get('composer',''),m.get('publisher',''),clock(t['duration']),states[t['id']]]
                for col,value in enumerate(values):
                    item=QTableWidgetItem(str(value));item.setToolTip(t['path']);self.reference_table.setItem(row,col,item)
                if t['id']==selected_id:self.reference_table.selectRow(row)
        self.reference_summary.setText(f'{len(self.track_rows)} / {len(all_tracks)} references'+(' · filtered' if query else ''))
    def populate_cues(self):
        if not self.p:return
        selected_ids={c['id'] for c in self.selected_cues()}
        current=self.selected_cue();current_id=current['id'] if current else None
        with batch_table_update(self.cue_table):
            tracks={t['id']:t for t in (self.reference_cache[0] if self.reference_cache is not None else self.p.tracks())};settings=self.p.settings;rate=settings['rate'];origin=parse(settings['origin'],rate)
            search=self.search.text().lower();status=self.filter.currentText()
            excluded=self.p.excluded_cue_ids()
            self.exclude_button.setText('Restore' if status=='Excluded' else 'Exclude')
            self.cue_rows=[]
            for c in self.p.cues():
                if (c['id'] in excluded)!=(status=='Excluded'):continue
                title=tracks.get(c['track'],{}).get('metadata',{}).get('title',c['title'])
                if status not in ('All cues','Excluded') and c['status']!=status:continue
                if search and search not in ' '.join([title,c['status'],c['note']]).lower():continue
                self.cue_rows.append(c)
            ordinals={c['id']:i+1 for i,c in enumerate(self.p.cues())}
            if self.cue_sort:
                column,order=self.cue_sort
                def key(c):
                    title=tracks.get(c['track'],{}).get('metadata',{}).get('title',c['title'])
                    return [ordinals[c['id']],title.casefold(),c['start'],c['end'],c['end']-c['start'],c['confidence'] if c['track'] else -1,('Excluded' if c['id'] in excluded else c['status']).casefold()][column]
                self.cue_rows.sort(key=key,reverse=order==Qt.DescendingOrder)
            self.cue_table.setRowCount(len(self.cue_rows))
            self.cue_table.clearSelection();self.cue_table.setCurrentCell(-1,-1)
            for row,c in enumerate(self.cue_rows):
                title=tracks.get(c['track'],{}).get('metadata',{}).get('title',c['title'])
                values=[ordinals[c['id']],title,format_tc(origin+c['start'],rate),format_tc(origin+c['end'],rate),clock(c['end']-c['start']),f"{c['confidence']:.0f}/100" if c['track'] else '—','Excluded' if c['id'] in excluded else c['status']]
                for col,value in enumerate(values):
                    item=QTableWidgetItem(str(value));item.setToolTip(c['note'])
                    if col in (1,6):item.setForeground(QColor('#e7bb76' if not c['track'] else '#92ddc4'))
                    self.cue_table.setItem(row,col,item)
                if c['id'] in selected_ids:
                    self.cue_table.selectionModel().select(self.cue_table.model().index(row,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
                    if c['id']==current_id:self.cue_table.selectionModel().setCurrentIndex(self.cue_table.model().index(row,0),QItemSelectionModel.NoUpdate)
        self.timeline.show_excluded=status=='Excluded'
        self.waveform_excluded.blockSignals(True);self.waveform_excluded.setChecked(status=='Excluded');self.waveform_excluded.blockSignals(False)
        allc=self.p.cues();included=self.p.included_cues();unknown=sum(not c['track'] and c['status']=='Unknown' for c in included);reviewed=sum(c['status']=='Reviewed' for c in included)
        version_ids=set(self.p.get('version_reviews',{}));pending_versions=sum(not c['track'] and c['id'] in version_ids for c in included)
        duration=self.p.get('program',{}).get('duration',0)
        coverage=''
        if duration:
            represented=covered_seconds(allc,duration);identified=covered_seconds([c for c in included if c['track']],duration)
            program=self.p.get('program',{})
            length_label='Source' if program.get('reported_duration') is not None else ('Decoded length' if 'decoded_duration' in program else 'Stored length')
            coverage=f'Coverage {represented/duration:.2%} · Identified {identified/duration:.1%} · {length_label} {clock(duration)} · '
        filtered=bool(search or status!='All cues')
        self.summary.setText(coverage+f'{unknown} unknown · {reviewed} reviewed'+(f' · {pending_versions} versions need review' if pending_versions else '')+f' · {len(excluded)} excluded · {len(self.cue_rows)}/{len(allc)} visible'+(' (filtered)' if filtered else ''))
        self.update_merge_button()
    def selected_cues(self):
        rows=sorted(index.row() for index in self.cue_table.selectionModel().selectedRows())
        return [self.cue_rows[row] for row in rows if 0<=row<len(self.cue_rows)]
    def update_merge_button(self):
        if not hasattr(self,'merge_button') or not hasattr(self,'cue_table'):return
        selected=self.selected_cues();enabled=bool(self.p) and not self.busy() and len(selected)>=2
        self.timeline.selected={c['id'] for c in selected}
        current=self.selected_cue()
        self.timeline.current_id=current['id'] if current and current['id'] in self.timeline.selected else (selected[0]['id'] if selected else None)
        self.timeline.update()
        previous=getattr(self,'_playback_selection',set());current_ids={c['id'] for c in selected};self._playback_selection=current_ids
        if previous!=current_ids and (self.reverse.active or self.player.playbackState()==QMediaPlayer.PlayingState):self.stop_audition()
        self.exclude_button.setEnabled(bool(self.p) and not self.busy() and bool(selected))
        if enabled:
            try:self.p.merge_selection([c['id'] for c in selected])
            except ValueError:enabled=False
        self.merge_button.setEnabled(enabled)
        active=bool(self.p) and not self.busy()
        self.edit_button.setEnabled(active and len(selected)==1)
        retry=active and len(selected)==1 and selected[0]['id'] not in self.p.excluded_cue_ids() if self.p else False
        self.retry_action.setEnabled(retry);self.retry_table_action.setEnabled(retry)
        self.deletecue_button.setEnabled(active and bool(selected))
        self.split_action.setEnabled(active and len(selected)==1)
        self.ai_selected_action.setEnabled(active and bool(selected))
        self.ai_unknown_action.setEnabled(active and any(not c['track'] and c['status']=='Unknown' for c in self.p.included_cues()) if self.p else False)
        self.ai_results_action.setEnabled(active and ai.result_path(self.p.path).is_file() if self.p else False)
        for action,allowed in zip(self.cue_actions_menu.actions(),[active and len(selected)==1,enabled,active and bool(selected),active,active and bool(selected)]):action.setEnabled(allowed)
        self.cue_actions_menu.actions()[2].setText('Restore' if self.filter.currentText()=='Excluded' else 'Exclude')
        self.update_playback_ui()
        self.refresh_monitor_controls()
    def merge_selected(self):
        if not self.p or not self.guard():return
        try:selected=self.p.merge_selection([c['id'] for c in self.selected_cues()])
        except ValueError as e:self.error(str(e));return
        dialog=MergeDialog(selected,self.reference_cache[0] if self.reference_cache is not None else self.p.tracks(),self)
        if dialog.exec():
            try:
                merged=self.p.merge_cues([c['id'] for c in selected],dialog.track,dialog.title,dialog.reviewed,dialog.note)
                self.refresh(cues_only=True)
                for row,c in enumerate(self.cue_rows):
                    if c['id']==merged['id']:self.cue_table.selectRow(row);break
                self.stop_audition();self.update_history_controls();self.status.setText('Cues merged')
            except ValueError as e:self.error(str(e))
    def toggle_cue_exclusion(self):
        if not self.p or not self.guard():return
        selected=self.selected_cues()
        if not selected:return
        excluding=self.filter.currentText()!='Excluded'
        self.stop_audition();self.p.set_cues_excluded([c['id'] for c in selected],excluding)
        self.refresh(cues_only=True)
        self.status.setText(f"{len(selected)} cue(s) "+('excluded' if excluding else 'restored'))
    def undo_last_merge(self):
        if not self.p or not self.guard():return
        try:self.p.undo_merge();self.refresh(cues_only=True);self.status.setText('Original cue entries restored.')
        except ValueError as e:self.error(str(e))
    def repair_source_coverage(self):
        if not self.p or not self.guard():return
        self.stop_audition();self.start_worker(repair_coverage)
    def selected_track(self):
        row=self.reference_table.currentRow();return self.track_rows[row] if 0<=row<len(self.track_rows) else None
    def selected_cue(self):
        row=self.cue_table.currentRow();return self.cue_rows[row] if 0<=row<len(self.cue_rows) and self.cue_table.selectionModel().isRowSelected(row,self.cue_table.rootIndex()) else None
    def edit_metadata(self):
        if not self.p or not self.guard():return
        t=self.selected_track()
        if not t:return
        d=MetadataDialog(t,self)
        if d.exec():self.p.update_metadata(t['id'],d.metadata);self.refresh()
    def relink_track(self):
        if not self.p or not self.guard():return
        t=self.selected_track()
        if not t:
            c=self.playback_cue();t=next((t for t in self.p.tracks() if c and t['id']==c['track']),None)
        if not t:self.status.setText('No reference selected');return
        path,_=QFileDialog.getOpenFileName(self,'Reconnect original reference recording')
        if not path:return
        try:self.p.relink_reference(t['id'],path);self.refresh();self.status.setText('Reference reconnected')
        except Exception as exc:self.error(str(exc))
    def retry_selected_cue(self):
        if not self.p or not self.guard():return
        selected=self.selected_cues()
        if len(selected)!=1:return
        self.stop_audition();self.start_worker(identify_cue,selected[0]['id'])
    def split_selected_cue(self):
        if not self.p or not self.guard() or self.timeline.drag:return
        selected=self.selected_cues()
        if len(selected)!=1:return
        try:
            self.stop_audition();right=self.p.split_cue(selected[0]['id'],self.timeline.position)
            self.refresh(cues_only=True);self.timeline.current_id=right['id'];self.select_timeline_cues([right['id']])
            self.status.setText('Cue split at playhead · saved')
        except ValueError as exc:self.status.setText(str(exc))
    def retry_with_separation(self,all_unknown=False):
        if not self.p or not self.guard():return
        selected=self.selected_cues()
        if not all_unknown and not selected:return
        if not ai.installed():
            from .ai_ui import AISetupDialog
            AISetupDialog(self).exec()
            if not ai.installed():return
        self.stop_audition();self.start_worker(ai.analyze_separated,{'ids':None if all_unknown else [c['id'] for c in selected]})
    def show_ai_results(self,result=None):
        if not self.p or not self.guard():return
        from .ai_ui import AIResultsDialog
        try:
            if not isinstance(result,dict):result=json.loads(ai.result_path(self.p.path).read_text())
            if not result.get('strict_neighbor_merge'):
                from .versions import annotate_results
                annotate_results(result,self.p)
            AIResultsDialog(self,result).exec()
        except (OSError,ValueError) as exc:self.error(str(exc))
    def review_retry_result(self,result):
        original=next((c for c in self.p.cues() if c['id']==result['cue']['id']),None)
        if original!=result['cue']:
            self.status.setText('Cue changed; run Identify again');return
        candidates=result['candidates']
        if not candidates:
            QMessageBox.information(self,'Identify selected cue','No supported match found in this interval. The cue was left unchanged.');return
        dialog=QDialog(self);dialog.setWindowTitle('Reference candidates');dialog.resize(680,390);layout=QVBoxLayout(dialog)
        table=QTableWidget(len(candidates),3);table.setHorizontalHeaderLabels(['Reference','Landmark support','Reference in']);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.SingleSelection);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        for row,candidate in enumerate(candidates):
            for column,value in enumerate([candidate['title'],str(candidate['support']),f"{candidate['reference_start']:.3f} s"]):table.setItem(row,column,QTableWidgetItem(value))
        layout.addWidget(table);table.selectRow(0)
        controls=QDialogButtonBox(QDialogButtonBox.Open|QDialogButtonBox.Cancel);controls.button(QDialogButtonBox.Open).setText('Review candidate');controls.accepted.connect(dialog.accept);controls.rejected.connect(dialog.reject);layout.addWidget(controls)
        if dialog.exec():
            candidate=candidates[table.currentRow()]
            proposal=original|{'track':candidate['track'],'title':candidate['title'],
                               'status':'Needs review','confidence':0}
            self.edit_cue_dialog(proposal,proposal=candidate)
    def remove_reference(self):
        if not self.p or not self.guard():return
        t=self.selected_track()
        if t and QMessageBox.question(self,'Remove reference?','Remove this reference and its fingerprints from this project? Associated cues become unknown. Original media is kept.')==QMessageBox.Yes:
            self.p.remove_track(t['id']);self.p.set('stale',True);self.refresh()
    def edit_cue(self):
        if not self.p or not self.guard():return
        selected=self.selected_cues()
        if len(selected)!=1:
            self.status.setText('Select one cue to review, or use Merge selected for multiple cues.');return
        self.edit_cue_dialog(selected[0])
    def edit_cue_dialog(self,c,new=False,proposal=None):
        self.stop_audition()
        version_candidates=proposal.get('version_candidates',[]) if proposal else self.p.get('version_reviews',{}).get(c['id'],[])
        versions=proposal.get('version_tracks',[]) if proposal else [v['track'] for v in version_candidates]
        tracks=sorted(self.p.tracks(),key=lambda t:t['id'] not in versions)
        d=CueDialog(c,tracks,self.p.get('program',{}).get('duration',86400),self,version_candidates=version_candidates)
        if proposal and d.comparison:d.comparison.offset.setValue(max(0,proposal['reference_start']+c['start']-proposal['program_start']))
        original=c['track']
        if d.exec():
            if d.c['track']!=original:d.c['confidence']=0
            cues=self.p.cues();cues=[d.c if x['id']==c['id'] else x for x in cues]
            if new:cues.append(d.c)
            try:
                version_reviews=None
                if (proposal and proposal.get('version_unresolved')) or c['id'] in self.p.get('version_reviews',{}):
                    version_reviews=self.p.get('version_reviews',{})
                    if d.c['track'] is not None:version_reviews.pop(c['id'],None)
                    elif proposal and proposal.get('version_unresolved'):version_reviews[c['id']]=proposal['version_candidates']
                self.stop_audition();self.p.save_cues(cues,label='Add cue' if new else ('Identify cue' if proposal else 'Review cue'),version_reviews=version_reviews)
                if d.comparison:d.comparison.save()
                self.refresh()
            except ValueError as e:self.error(str(e))
    def add_cue(self):
        if not self.p or not self.guard():return
        duration=self.p.get('program',{}).get('duration',0)
        if not duration:self.error('Analyze the program before adding manual cues.');return
        start=min(self.timeline.position,max(0,duration-.1));self.edit_cue_dialog(cue(None,start,min(duration,start+5),title='Unknown (manual)'),True)
    def delete_cue(self):
        if self.timeline.drag:return
        if not self.p or not self.guard():return
        selected=self.selected_cues()
        if not selected:return
        count=len(selected);ids={c['id'] for c in selected}
        question=f'Delete “{self.cue_title(selected[0])}”?' if count==1 else f'Delete these {count} selected cues?'
        question+='\n\nTheir space will remain empty. You can undo this change.'
        if QMessageBox.question(self,'Delete cue?' if count==1 else 'Delete cues?',question,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        self.stop_audition()
        self.p.save_cues([c for c in self.p.cues() if c['id'] not in ids],label='Delete cue' if count==1 else 'Delete cues')
        self.refresh(cues_only=True);self.status.setText('Cue deleted' if count==1 else f'{count} cues deleted')
    def export_cues(self):
        if not self.p or not self.guard():return
        from .workflow import validate_cues
        from .workflow_ui import ValidationDialog,CueExportDialog
        issues=validate_cues(self.p)
        if any(i['severity']=='error' for i in issues):
            ValidationDialog(self,for_export=True).exec();return
        dialog=CueExportDialog(self,issues)
        if dialog.exec()==QDialog.Accepted:
            path=dialog.selectedFiles()[0];selected=dialog.selectedNameFilter()
            try:
                if Path(path).suffix.lower() not in {'.csv','.xlsx'}:path+='.xlsx' if 'Excel' in selected else '.csv'
                export(self.p,path);self.status.setText('Cue sheet exported with licensing fields, review status and original metadata.')
            except Exception as e:self.error(str(e))
    def playback_cue(self):
        selected=self.selected_cues()
        return self.selected_cue() or (selected[0] if selected else None)
    def cue_title(self,c):
        if not self.p:return c['title']
        track=next((t for t in (self.reference_cache[0] if self.reference_cache is not None else self.p.tracks()) if t['id']==c['track']),None)
        return track['metadata'].get('title',c['title']) if track else c['title']
    def stop_audition(self,pause=True):
        self.reverse.stop();self.shuttle_direction=0;self.shuttle_speed=1;self.player.setPlaybackRate(1)
        self.stop_at=None;self.loop_start=None;self.audition_context=None;self.loop_paused=False
        if hasattr(self,'loop_button'):
            self.loop_button.blockSignals(True);self.loop_button.setChecked(False);self.loop_button.blockSignals(False)
        if pause:self.player.pause()
        self.update_playback_ui()
    def update_playback_ui(self):
        if not hasattr(self,'playback_label') or not hasattr(self,'cue_table'):return
        if self.p:
            settings=self.p.settings
            self.position_label.setText(format_tc(parse(settings['origin'],settings['rate'])+self.timeline.position,settings['rate']))
        c=self.playback_cue();context=self.audition_context
        if context and (not c or context.get('cue_id')!=c['id']):
            self.stop_at=None;self.loop_start=None;self.audition_context=None;context=None
            self.loop_button.setChecked(False)
        playing=self.reverse.active or self.player.playbackState()==QMediaPlayer.PlayingState
        if self._monitor_pending:playing=self._monitor_pending['playing'] or self._monitor_pending['reverse']
        if self.reverse.active:description=('Loading reverse' if self.reverse.loading else 'Reverse')+f' · {self.shuttle_speed}×'
        elif self.shuttle_direction==1:description=f'Forward · {self.shuttle_speed}×'
        elif context:
            title=context['title'];mode=context['mode']
            description={'cue':'Preview','start':'Audition In','end':'Audition Out','loop-start':'Loop In','loop-end':'Loop Out'}[mode]+': '+title
        else:description='Preview: '+self.cue_title(c) if c else 'Free playback'
        if self.monitor_mode:
            covered=any(a<=self.timeline.position<b for a,b in self.monitor_descriptor.get('regions',[]))
            description=('AI music · ' if covered else 'Program audio · outside AI sections · ')+description
        self.playback_label.setText(('Preparing · ' if self.reverse.loading or self._monitor_pending else ('Playing · ' if playing else 'Paused · '))+description)
        self.play_button.setText('Ⅱ Pause' if playing else ('▶ Audition' if context and context['mode']!='cue' else ('▶ Preview cue' if c else '▶ Play from cursor')))
        active=bool(c and self.p and not self.busy() and self.p.get('program',{}).get('duration'))
        edit=self.timeline.active_edit
        if edit and (edit['id'] not in self.timeline.selected):
            self.timeline.active_edit=None;edit=None;self.selected_edge='start'
        self.audition_button.setText('Audition edit' if edit and edit['side']=='roll' and edit['edge']==self.selected_edge else ('Audition In' if self.selected_edge=='start' else 'Audition Out'))
        for widget in [self.audition_button,self.loop_button,self.audition_options_button,self.audition_radius]:widget.setEnabled(active)
    def toggle_play(self):self.preview_cue()
    def seek(self,seconds):
        self.timeline.follow_suspended=False
        if self._monitor_pending:self._monitor_pending['position']=seconds
        self.stop_audition(pause=False);self.timeline.position=seconds;self.timeline.update();self.player.setPosition(int(seconds*1000));self.update_playback_ui()
    def _play_interval(self,c,start,end,mode):
        self.reverse.stop();self.shuttle_direction=0;self.shuttle_speed=1;self.player.setPlaybackRate(1)
        self.audition_context={'cue_id':c['id'],'title':self.cue_title(c),'mode':mode,'start':start,'end':end}
        self.loop_start=start if mode.startswith('loop-') else None;self.stop_at=end;self.loop_paused=False
        self.timeline.position=start;self.timeline.update()
        if self._monitor_pending:self._monitor_pending.update(position=start,playing=True,reverse=False,rate=1)
        else:self.player.setPosition(int(start*1000));self.player.play()
        self.update_playback_ui()
    def play_cue(self):
        c=self.playback_cue()
        if c:
            self.loop_button.setChecked(False);self._play_interval(c,c['start'],c['end'],'cue')
    def preview_cue(self):
        if not self.p:return
        if self._monitor_pending:
            pending=self._monitor_pending
            if pending['playing'] or pending['reverse']:pending.update(playing=False,reverse=False)
            elif self.playback_cue():self.play_cue()
            else:pending['playing']=True
            self.update_playback_ui();return
        if self.reverse.active:self.shuttle(0);return
        if self.player.playbackState()==QMediaPlayer.PlayingState:
            self.loop_paused=True;self.player.pause();self.update_playback_ui();return
        c=self.playback_cue();context=self.audition_context
        if c and context and context['cue_id']==c['id'] and context['mode']!='cue':
            self._play_interval(c,context['start'],context['end'],context['mode'])
        elif c:self.play_cue()
        else:
            self.stop_at=None;self.loop_start=None;self.audition_context=None;self.player.play();self.update_playback_ui()
    def audition_transition(self,edge,loop=None):
        c=self.playback_cue()
        if not c or not self.p or not self.guard():return
        radius=self.audition_radius.value();duration=self.p.get('program',{}).get('duration',0)
        start=max(0,c[edge]-radius);end=min(duration,c[edge]+radius)
        if end<=start:return
        self.selected_edge=edge
        looping=self.loop_button.isChecked() if loop is None else loop
        self.loop_button.setChecked(looping)
        self._play_interval(c,start,end,('loop-' if looping else '')+edge)
        self.timeline.set_view(start,max(.25,end-start))
    def toggle_transition_loop(self):
        if self.loop_button.isChecked():self.audition_transition(self.selected_edge,loop=True)
        else:self.stop_audition()
    def audition_options_changed(self):
        if self.audition_context and self.audition_context['mode']!='cue':
            self.audition_transition(self.selected_edge)
    def nudge_boundary(self,direction):
        if not self.p or not self.guard():return
        c=self.playback_cue()
        if not c:return
        edge=self.selected_edge;fps=RATES[self.p.settings['rate']][0]
        point=c[edge]+direction/fps
        cues=self.p.cues();i=next(i for i,item in enumerate(cues) if item['id']==c['id'])
        neighbor=cues[i-1] if edge=='start' and i else (cues[i+1] if edge=='end' and i+1<len(cues) else None)
        edit=self.timeline.active_edit
        if edit and edit['id']==c['id'] and edit['edge']==edge and edit['side']=='roll' and neighbor and abs((neighbor['end'] if edge=='start' else neighbor['start'])-c[edge])<1e-8:
            a,b=(neighbor,c) if edge=='start' else (c,neighbor)
            self.adjust_timeline_edit(a['id'],b['id'],point,'roll')
        elif c['start']<point<c['end'] or (edge=='start' and 0<=point<c['end']) or (edge=='end' and c['start']<point<=self.timeline.duration):
            self.trim_timeline_cue(c['id'],point if edge=='start' else c['start'],point if edge=='end' else c['end'])
    def shuttle(self,direction):
        if not self.p or self.busy() or self.timeline.drag:return
        program=self.p.get('program',{})
        if not program.get('path'):return
        position=self.timeline.position
        if self._monitor_pending:
            pending=self._monitor_pending;running=pending['playing'] or pending['reverse']
            speed=min(8,self.shuttle_speed*2) if direction and self.shuttle_direction==direction and running else 1
            self.shuttle_direction=direction;self.shuttle_speed=speed
            pending.update(position=position,playing=direction>0,reverse=direction<0,rate=speed)
            self.update_playback_ui();return
        if direction==0:
            self.reverse.stop();self.player.pause();self.player.setPosition(round(position*1000))
            self.loop_paused=True;self.shuttle_direction=0;self.shuttle_speed=1;self.player.setPlaybackRate(1)
        else:
            running=self.reverse.active if direction<0 else self.player.playbackState()==QMediaPlayer.PlayingState
            speed=min(8,self.shuttle_speed*2) if self.shuttle_direction==direction and running else 1
            self.stop_audition();self.shuttle_direction=direction;self.shuttle_speed=speed
            if direction<0:self.reverse.start(self.monitor_path(),position,speed)
            else:
                self.player.setPlaybackRate(speed);self.player.setPosition(round(position*1000));self.player.play()
        self.update_playback_ui()
    def _restart_loop(self):
        if self.loop_start is None or self._loop_seeking or self.loop_paused:return
        self._loop_seeking=True
        try:
            self.timeline.position=self.loop_start;self.timeline.update();self.player.setPosition(int(self.loop_start*1000));self.player.play()
        finally:self._loop_seeking=False
    def media_status_changed(self,status):
        if self._monitor_pending and status in (QMediaPlayer.LoadedMedia,QMediaPlayer.BufferedMedia):self.finish_monitor_switch()
        if status==QMediaPlayer.EndOfMedia:self._restart_loop()
    def position_changed(self,ms,reverse=False):
        if self._switching_monitor or self._monitor_pending:return
        if self.reverse.active and not reverse:return
        self.timeline.position=ms/1000;self.timeline.update()
        if self.p:
            s=self.p.settings;self.position_label.setText(format_tc(parse(s['origin'],s['rate'])+ms/1000,s['rate']))
        if self.stop_at is not None and ms/1000>=self.stop_at:
            if self.loop_start is not None:self._restart_loop()
            else:self.stop_at=None;self.player.pause()
        if self.reverse.active or self.player.playbackState()==QMediaPlayer.PlayingState:
            self.timeline.follow_playhead(-1 if self.reverse.active else 1)
        self.update_playback_ui()
    def error(self,message):self.status.setText('Operation failed.');QMessageBox.warning(self,'Cue Atlas',message)
    def closeEvent(self,event):
        if self.busy():
            self.worker.requestInterruption();self.status.setText('Cancelling… Close again after the operation stops.');event.ignore();return
        self.project_location_timer.stop();self.reverse.shutdown();self.timeline.shutdown();self.player.stop()
        if self.p:self.p.close()
        event.accept()

def main():
    app=QApplication(sys.argv);app.setApplicationName('Cue Atlas');app.setApplicationVersion(__version__);app.setOrganizationName('CueAtlas');app.setStyle('Fusion');app.setStyleSheet(STYLE)
    from .diagnostics import start as start_diagnostics
    start_diagnostics(app)
    w=Window();w.show()
    if len(sys.argv)>1 and Path(sys.argv[1]).suffix=='.cueatlas':w.load(sys.argv[1])
    sys.exit(app.exec())
