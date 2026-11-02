"""Desktop screens for review, recovery, markers, and delivery."""
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QTableWidget,QTableWidgetItem,QAbstractItemView,QHeaderView,QSpinBox,QDoubleSpinBox,
    QFormLayout,QDialogButtonBox,QMessageBox,QTextEdit,QComboBox,QLineEdit,QFileDialog)
from .workflow import review_queue,validate_cues,list_snapshots,create_snapshot,save_marker,duplicate_report
from .timecode import format_tc,parse
from .ui_tables import batch_table_update


def table(headers):
    widget=QTableWidget(0,len(headers));widget.setHorizontalHeaderLabels(headers)
    widget.setSelectionBehavior(QAbstractItemView.SelectRows);widget.setSelectionMode(QAbstractItemView.SingleSelection)
    widget.setEditTriggers(QAbstractItemView.NoEditTriggers);widget.verticalHeader().hide()
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    widget.horizontalHeader().setStretchLastSection(True)
    return widget


def fill(widget,rows):
    with batch_table_update(widget):
        widget.setRowCount(len(rows))
        for row,values in enumerate(rows):
            for column,value in enumerate(values):
                item=QTableWidgetItem(str(value));item.setToolTip(str(value));widget.setItem(row,column,item)


def tc(project,seconds):
    rate=project.settings['rate'];return format_tc(parse(project.settings['origin'],rate)+seconds,rate)


class ReviewQueueDialog(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.project=owner.p;self.setWindowTitle('Review queue');self.resize(850,530)
        layout=QVBoxLayout(self);self.count=QLabel();layout.addWidget(self.count)
        controls=QHBoxLayout();controls.addWidget(QLabel('Weak match: evidence score below'))
        self.threshold=QSpinBox();self.threshold.setRange(0,100);self.threshold.setValue(self.project.settings.get('review_threshold',60))
        controls.addWidget(self.threshold);controls.addStretch();layout.addLayout(controls)
        self.table=table(['Cue','Program In','Program Out','Reason']);layout.addWidget(self.table)
        actions=QHBoxLayout()
        for name,fn in [('Previous',lambda:self.move(-1)),('Next',lambda:self.move(1)),
                        ('Go to cue',self.jump),('Review…',lambda:self.act('review')),('Identify…',lambda:self.act('identify'))]:
            button=QPushButton(name);button.clicked.connect(fn);actions.addWidget(button)
        layout.addLayout(actions)
        hint=QLabel('Unknown and unreviewed assignments remain here. Reviewed assignments are confirmed, regardless of their original score. Excluded cues are omitted.')
        hint.setWordWrap(True);layout.addWidget(hint)
        self.table.cellDoubleClicked.connect(lambda *args:self.act('review'))
        self.threshold.valueChanged.connect(self.change_threshold)
        self.timer=QTimer(self);self.timer.setInterval(500);self.timer.timeout.connect(self.refresh);self.timer.start()
        self.rows=[];self.signature=None;self.refresh()
    def change_threshold(self,value):
        if self.owner.p is self.project and not self.owner.busy():
            self.project.set('settings',self.project.settings|{'review_threshold':value});self.refresh()
    def refresh(self):
        if self.owner.p is not self.project:self.close();return
        self.threshold.setEnabled(not self.owner.busy())
        if self.owner.busy() or self.project.db.in_transaction:return
        # Include other SQLite connections (analysis workers), not just UI edits.
        signature=(self.project.db.total_changes,self.project.db.execute('PRAGMA data_version').fetchone()[0],self.threshold.value())
        if signature==self.signature:return
        rows=review_queue(self.project,self.threshold.value())
        current=self.rows[self.table.currentRow()]['id'] if 0<=self.table.currentRow()<len(self.rows) else None
        self.rows=rows
        titles={t['id']:t['metadata'].get('title') for t in self.project.tracks()}
        settings=self.project.settings;rate=settings['rate'];origin=parse(settings['origin'],rate)
        fill(self.table,[[titles.get(c['track']) or c['title'],format_tc(origin+c['start'],rate),format_tc(origin+c['end'],rate),', '.join(c['reasons'])] for c in rows])
        self.count.setText(f'{len(rows)} cues remaining to review')
        if rows:self.table.selectRow(next((i for i,c in enumerate(rows) if c['id']==current),0))
        self.signature=signature
    def jump(self):
        row=self.table.currentRow()
        if self.owner.p is self.project and 0<=row<len(self.rows):return self.owner.focus_cue(self.rows[row]['id'])
    def move(self,direction):
        if self.rows:self.table.selectRow(max(0,min(len(self.rows)-1,self.table.currentRow()+direction)));self.jump()
    def act(self,action):
        if self.jump():
            if action=='review':self.owner.edit_cue()
            else:self.owner.retry_selected_cue()
            self.refresh()
    def closeEvent(self,event):self.timer.stop();super().closeEvent(event)


class CueExportDialog(QFileDialog):
    """Choose the output file, with optional access to nonblocking warnings."""
    def __init__(self,owner,issues):
        super().__init__(owner,'Export cue sheet',str(owner.p.path.with_suffix('.csv')),'CSV (*.csv);;Excel (*.xlsx)')
        self.setOption(QFileDialog.DontUseNativeDialog,True)
        self.setAcceptMode(QFileDialog.AcceptSave);self.setFileMode(QFileDialog.AnyFile)
        self.setDefaultSuffix('csv');self.setLabelText(QFileDialog.Accept,'Export')
        self.filterSelected.connect(self.change_format)
        self.warnings_button=QPushButton('Show warnings…',self)
        self.warnings_button.setAutoDefault(False);self.warnings_button.setEnabled(bool(issues))
        self.warnings_button.clicked.connect(lambda:ValidationDialog(owner).exec())
        layout=self.layout();layout.addWidget(self.warnings_button,layout.rowCount(),0,1,1)
    def change_format(self,name):
        suffix='xlsx' if 'Excel' in name else 'csv'
        files=self.selectedFiles()
        if files and Path(files[0]).suffix.lower() in ('.csv','.xlsx'):
            self.selectFile(str(Path(files[0]).with_suffix('.'+suffix)))
        self.setDefaultSuffix(suffix)


class ValidationDialog(QDialog):
    def __init__(self,owner,for_export=False):
        super().__init__(owner);self.owner=owner;self.setWindowTitle('Cue-sheet validation');self.resize(900,550)
        self.issues=validate_cues(owner.p);layout=QVBoxLayout(self)
        errors=sum(i['severity']=='error' for i in self.issues)
        layout.addWidget(QLabel(f'{errors} timing errors · {len(self.issues)-errors} warnings'))
        hint=QLabel('Warnings are optional to review and do not prevent export. Invalid cue timings must be corrected.')
        hint.setWordWrap(True);layout.addWidget(hint)
        self.table=table(['Severity','Cue','Issue']);fill(self.table,[[i['severity'].title(),i['title'],i['message']] for i in self.issues]);layout.addWidget(self.table)
        row=QHBoxLayout();go=QPushButton('Go to selected cue');go.clicked.connect(self.jump);row.addWidget(go);row.addStretch()
        if for_export:
            proceed=QPushButton('Export with warnings' if self.issues else 'Continue to export');proceed.setEnabled(errors==0)
            proceed.clicked.connect(self.accept);row.addWidget(proceed)
        close=QPushButton('Cancel' if for_export else 'Done');close.clicked.connect(self.reject);row.addWidget(close);layout.addLayout(row)
        if self.issues:self.table.selectRow(0)
    def jump(self):
        row=self.table.currentRow()
        if 0<=row<len(self.issues):self.owner.focus_cue(self.issues[row]['cue_id']);self.reject()


class SnapshotsDialog(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.setWindowTitle('Recovery snapshots');self.resize(850,500)
        layout=QVBoxLayout(self);hint=QLabel('Recovery points include the entire project database. Media stays linked. The newest 20 are kept beside the project. Restore first saves the current state.')
        hint.setWordWrap(True);layout.addWidget(hint)
        self.table=table(['Created','Before / reason','Size']);layout.addWidget(self.table)
        row=QHBoxLayout()
        for name,fn in [('Snapshot now',self.create),('Restore selected…',self.restore),('Done',self.accept)]:
            button=QPushButton(name);button.clicked.connect(fn);row.addWidget(button)
        layout.addLayout(row);self.refresh()
    def refresh(self):
        self.rows=list_snapshots(self.owner.p)
        fill(self.table,[[datetime.fromisoformat(s['created_utc']).astimezone().strftime('%Y-%m-%d %H:%M:%S'),s.get('reason','Recovery point'),f'{s["size"]/1024/1024:.1f} MB'] for s in self.rows])
        if self.rows:self.table.selectRow(0)
    def create(self):
        try:create_snapshot(self.owner.p,'Manual recovery point',force=True);self.refresh()
        except Exception as exc:self.owner.error(str(exc))
    def restore(self):
        row=self.table.currentRow()
        if not 0<=row<len(self.rows):return
        if QMessageBox.question(self,'Restore recovery point?','Replace the current project state with this snapshot? A new recovery point will preserve the current state.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        try:self.owner.restore_recovery(self.rows[row]['path']);self.refresh()
        except Exception as exc:self.owner.error(str(exc))


class MarkerEditDialog(QDialog):
    def __init__(self,project,position,record=None,parent=None):
        super().__init__(parent);self.setWindowTitle('Marker comment');self.resize(480,320)
        layout=QVBoxLayout(self);form=QFormLayout();self.position=QDoubleSpinBox();self.position.setDecimals(3)
        self.position.setRange(0,project.get('program',{}).get('duration',0));self.position.setValue(record['position'] if record else position);self.position.setSuffix(' s')
        form.addRow('Program position',self.position);layout.addLayout(form)
        self.text=QTextEdit();self.text.setPlaceholderText('What needs attention at this moment?');self.text.setPlainText(record['text'] if record else '')
        layout.addWidget(self.text);buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def accept(self):
        if not self.text.toPlainText().strip():QMessageBox.information(self,'Marker comment','Enter a comment for this marker.');return
        super().accept()


class MarkersDialog(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.setWindowTitle('Markers and comments');self.resize(780,470)
        layout=QVBoxLayout(self);self.table=table(['Program time','Comment']);layout.addWidget(self.table)
        row=QHBoxLayout()
        for name,fn in [('Add at playhead…',self.add),('Go to marker',self.jump),('Edit…',self.edit),('Delete',self.delete),('Done',self.accept)]:
            button=QPushButton(name);button.clicked.connect(fn);row.addWidget(button)
        layout.addLayout(row);self.table.cellDoubleClicked.connect(lambda *args:self.jump());self.refresh()
    def refresh(self):
        self.rows=self.owner.p.get('markers',[])
        fill(self.table,[[tc(self.owner.p,m['position']),m['text']] for m in self.rows])
        if self.rows:self.table.selectRow(0)
    def add(self):self.owner.add_marker_comment();self.refresh()
    def jump(self):
        row=self.table.currentRow()
        if 0<=row<len(self.rows):
            t=self.owner.timeline;self.owner.stop_audition();self.owner.seek(self.rows[row]['position'])
            t.set_view(t.position-t.view_span/2,t.view_span)
    def edit(self):
        row=self.table.currentRow()
        if 0<=row<len(self.rows):self.owner.edit_marker_comment(self.rows[row]);self.refresh()
    def delete(self):
        row=self.table.currentRow()
        if not 0<=row<len(self.rows):return
        try:
            self.owner.p.snapshot('Before deleting a marker',force=True)
            self.owner.p.set('markers',[m for m in self.rows if m['id']!=self.rows[row]['id']]);self.owner.refresh();self.refresh()
        except Exception as exc:self.owner.error(str(exc))


class DuplicatesDialog(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.setWindowTitle('Reference duplicates and alternate mixes');self.resize(920,520)
        layout=QVBoxLayout(self);tracks={t['id']:t for t in owner.p.tracks()};rows=duplicate_report(list(tracks.values()))
        hint=QLabel(f'{len(rows)} pairs flagged. Exact duplicates share a file checksum. Possible alternate mixes share a base title and need listening; nothing is removed automatically.')
        hint.setWordWrap(True);layout.addWidget(hint);self.table=table(['Type','Reference A','Reference B','Reason'])
        fill(self.table,[[r['kind'],tracks[r['left']]['path'],tracks[r['right']]['path'],r['reason']] for r in rows]);layout.addWidget(self.table)
        close=QPushButton('Done');close.clicked.connect(self.accept);layout.addWidget(close)


class HandoffDialog(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.setWindowTitle('Create project handoff');self.resize(680,300)
        layout=QVBoxLayout(self);hint=QLabel('Collect a project copy, CSV cue sheet, validation report, marker comments, and optional media into a new portable folder. Existing folders are preserved.')
        hint.setWordWrap(True);layout.addWidget(hint);form=QFormLayout();self.path=QLineEdit(str(owner.p.path.with_name(owner.p.path.stem+'-handoff-'+datetime.now().strftime('%Y%m%d-%H%M%S'))))
        form.addRow('New folder',self.path);browse=QPushButton('Choose location…');browse.clicked.connect(self.browse);form.addRow('',browse)
        self.media=QComboBox();self.media.addItem('Project and reports only','none');self.media.addItem('Include program media','program');self.media.addItem('Include program and all references','all')
        form.addRow('Media',self.media);layout.addLayout(form)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.Save).setText('Create handoff')
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def browse(self):
        path,_=QFileDialog.getSaveFileName(self,'Name a new handoff folder',self.path.text())
        if path:self.path.setText(path)
    def accept(self):
        if not self.path.text().strip() or Path(self.path.text()).expanduser().exists():
            QMessageBox.information(self,'New handoff folder','Choose a new folder name that does not already exist.');return
        super().accept()
    def options(self):return {'destination':str(Path(self.path.text()).expanduser()),'media':self.media.currentData()}
