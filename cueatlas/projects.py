"""Project-file management. Listing projects never opens a writable database."""
import json
import sqlite3
from pathlib import Path
from PySide6.QtCore import Qt,QFile,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLineEdit,QPushButton,
    QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QFileDialog,QInputDialog,QMessageBox,
    QLabel,QFrame,QListWidget,QComboBox,QMenu)
from .project import Project
from .ui_tables import batch_table_update


def project_info(path):
    path=Path(path).expanduser().absolute()
    info={'path':str(path),'name':path.stem,'state':'Missing','valid':False}
    if not path.is_file():return info
    info['state']='Not a Cue Atlas project'
    if path.suffix.lower()!='.cueatlas':return info
    try:
        db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=1)
        try:
            if db.execute('PRAGMA user_version').fetchone()[0]!=1:return info
            row=db.execute("SELECT value FROM info WHERE key='name'").fetchone()
            if not row or not isinstance(json.loads(row[0]),str) or not json.loads(row[0]).strip():return info
            for table in ('tracks','hashes','cues'):db.execute(f'SELECT 1 FROM {table} LIMIT 1')
            info.update(state='Available',valid=True)
        finally:db.close()
    except (sqlite3.Error,ValueError,OSError):pass
    return info


class ProjectManager(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.setWindowTitle('Cue Atlas · Projects');self.resize(1080,680);self.setMinimumSize(850,540)
        self.setObjectName('projectBrowser')
        self.setStyleSheet("""
            QDialog#projectBrowser { background:#10191d; }
            QLabel#projectTitle { font-size:28px; font-weight:700; color:#f0f8f6; }
            QLabel#projectSubtitle { color:#9bb2b6; }
            QFrame#projectPanel { background:#152227; border:1px solid #293c43; border-radius:12px; }
            QListWidget { background:transparent; border:0; outline:0; }
            QListWidget::item { padding:14px 10px; margin:2px 0; border-radius:7px; color:#a9bfc2; }
            QListWidget::item:selected { background:#244b43; color:#9cf0d6; }
        """)
        layout=QVBoxLayout(self);layout.setContentsMargins(28,24,28,20);layout.setSpacing(20)
        header=QHBoxLayout();titles=QVBoxLayout()
        title=QLabel('Your projects');title.setObjectName('projectTitle');titles.addWidget(title)
        subtitle=QLabel('Find a project. Pick up where you left off.');subtitle.setObjectName('projectSubtitle');titles.addWidget(subtitle)
        header.addLayout(titles);header.addStretch()
        new=QPushButton('New project…');new.setAutoDefault(False);new.clicked.connect(self.new_project);header.addWidget(new)
        add=QPushButton('Add existing…');add.setAutoDefault(False);add.clicked.connect(self.add_project);header.addWidget(add);layout.addLayout(header)
        content=QHBoxLayout();content.setSpacing(20)
        self.navigation=QListWidget();self.navigation.addItems(['All projects','Favorites','Unavailable']);self.navigation.setFixedWidth(165)
        self.navigation.setAccessibleName('Project collections');self.navigation.setCurrentRow(0);content.addWidget(self.navigation)
        panel=QFrame();panel.setObjectName('projectPanel');body=QVBoxLayout(panel);body.setContentsMargins(16,16,16,16);body.setSpacing(12)
        top=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('Search by name or folder…');self.search.setClearButtonEnabled(True);self.search.setAccessibleName('Search projects');top.addWidget(self.search,1)
        self.sort=QComboBox();self.sort.addItems(['Recently opened','Name A–Z','Name Z–A']);self.sort.setAccessibleName('Sort projects');top.addWidget(self.sort);body.addLayout(top)
        self.count=QLabel();self.count.setObjectName('projectSubtitle');body.addWidget(self.count)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['Project','Location','Status'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows);self.table.setSelectionMode(QAbstractItemView.SingleSelection);self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False);self.table.setAlternatingRowColors(True);self.table.verticalHeader().hide();self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Interactive);self.table.setColumnWidth(0,210)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch);self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeToContents)
        body.addWidget(self.table,1)
        self.empty=QLabel();self.empty.setWordWrap(True);self.empty.setObjectName('projectSubtitle');body.addWidget(self.empty)
        actions=QHBoxLayout();self.buttons={}
        for name,callback in [('Open',self.open_selected),('Favorite',self.toggle_favorite),('Open folder',self.show_folder)]:
            button=QPushButton(name);button.setAutoDefault(False);button.clicked.connect(callback);actions.addWidget(button);self.buttons[name]=button
        self.buttons['Open'].setObjectName('primary')
        more=QPushButton('More ▾');self.more_menu=QMenu(self);more.setMenu(self.more_menu);actions.addWidget(more)
        for name,callback in [('Rename…',self.rename_selected),('Backup…',self.backup_selected),('Remove from Recents',self.forget_selected),('Move to Trash…',self.trash_selected)]:
            if name=='Remove from Recents':self.more_menu.addSeparator()
            self.buttons[name]=self.more_menu.addAction(name,callback)
        actions.addStretch();body.addLayout(actions);content.addWidget(panel,1);layout.addLayout(content,1)
        footer=QHBoxLayout();hint=QLabel('Projects save automatically. Double-click a row to open.');hint.setObjectName('projectSubtitle');footer.addWidget(hint);footer.addStretch()
        close=QPushButton('Done');close.setAutoDefault(False);close.clicked.connect(self.accept);footer.addWidget(close);layout.addLayout(footer)
        self.search.textChanged.connect(self.filter_rows);self.navigation.currentRowChanged.connect(self.filter_rows)
        self.sort.currentIndexChanged.connect(lambda *_:self.refresh());self.table.itemSelectionChanged.connect(self.update_actions)
        self.table.cellDoubleClicked.connect(lambda *_:self.open_selected());window.projectRelocated.connect(self.project_relocated);self.refresh()
    def new_project(self):
        previous=self.window.p
        self.window.new_project()
        if self.window.p is not previous:self.accept()
    def toggle_favorite(self):
        info=self.selected()
        if info:
            path=info['path']
            if path not in self.window.recent:self.window.remember_project(path)
            self.window.set_project_favorite(path,path not in self.window.favorite_projects);self.refresh(path)
    def project_relocated(self,old,new):
        if self.isVisible():
            selected=self.selected();self.refresh(new if selected and selected['path']==old else None)
    def selected(self):
        row=self.table.currentRow()
        return self.rows[row] if 0<=row<len(self.rows) and not self.table.isRowHidden(row) else None
    def refresh(self,select=None):
        previous=select or (self.selected()['path'] if hasattr(self,'rows') and self.selected() else None)
        paths=list(self.window.recent)
        if self.window.p and str(self.window.p.path) not in paths:paths.insert(0,str(self.window.p.path))
        self.rows=[project_info(path) for path in dict.fromkeys(paths)]
        if self.sort.currentIndex():self.rows.sort(key=lambda info:(info['name'].casefold(),info['path'].casefold()),reverse=self.sort.currentIndex()==2)
        with batch_table_update(self.table):
            self.table.clearSelection();self.table.setRowCount(len(self.rows))
            for row,info in enumerate(self.rows):
                current=self.window.p and Path(info['path']).resolve()==self.window.p.path
                state=('Open' if info['path'] in self.window.recent else 'Open · not in Recents') if current else info['state']
                for column,value in enumerate([('★  ' if info['path'] in self.window.favorite_projects else '')+info['name'],info['path'],state]):
                    item=QTableWidgetItem(value);item.setToolTip(info['path']);self.table.setItem(row,column,item)
            self.table.setCurrentCell(-1,-1)
        self.filter_rows()
        index=next((i for i,info in enumerate(self.rows) if info['path']==previous),None)
        if index is None:index=next((i for i in range(len(self.rows)) if not self.table.isRowHidden(i)),None)
        if index is not None and not self.table.isRowHidden(index):self.table.selectRow(index)
        self.update_actions()
    def filter_rows(self,*args):
        query=self.search.text().strip().casefold();collection=self.navigation.currentRow()
        visible=[]
        for row,info in enumerate(self.rows):
            matches=query in (info['name']+' '+info['path']).casefold()
            matches=matches and (collection!=1 or info['path'] in self.window.favorite_projects) and (collection!=2 or not info['valid'])
            self.table.setRowHidden(row,not matches)
            if matches:visible.append(row)
        if visible and not self.selected():self.table.selectRow(visible[0])
        if not visible:self.table.clearSelection();self.table.setCurrentCell(-1,-1)
        self.count.setText(f'{len(visible)} of {len(self.rows)} projects')
        self.empty.setVisible(not visible)
        self.empty.setText('No matching projects. Try another search or collection.' if self.rows else 'No projects yet. Create a project or add an existing .cueatlas file.')
        self.update_actions()
    def update_actions(self):
        info=self.selected();valid=bool(info and info['valid'])
        for name in ('Open','Rename…','Backup…','Move to Trash…'):self.buttons[name].setEnabled(valid)
        self.buttons['Remove from Recents'].setEnabled(bool(info and info['path'] in self.window.recent))
        self.buttons['Favorite'].setEnabled(bool(info))
        self.buttons['Favorite'].setText('Unfavorite' if info and info['path'] in self.window.favorite_projects else 'Favorite')
        self.buttons['Open folder'].setEnabled(bool(info and Path(info['path']).parent.is_dir()))
    def add_project(self):
        path,_=QFileDialog.getOpenFileName(self,'Add existing project','','Cue Atlas project (*.cueatlas)')
        if not path:return
        info=project_info(path)
        if not info['valid']:QMessageBox.warning(self,'Add project','Choose a valid Cue Atlas project file.');return
        self.window.remember_project(info['path']);self.refresh(info['path'])
    def open_selected(self):
        info=self.selected()
        if info and info['valid'] and self.window.load(info['path']):self.accept()
    def rename_selected(self):
        info=self.selected()
        if not info or not info['valid']:return
        name,ok=QInputDialog.getText(self,'Rename project','Project name',text=info['name'])
        if not ok or not name.strip():return
        try:
            target=self.window.rename_project_file(info['path'],name)
            self.refresh(str(target))
        except Exception as exc:QMessageBox.warning(self,'Rename project',str(exc))
    def backup_selected(self):
        info=self.selected()
        if not info or not info['valid']:return
        source=Path(info['path']);path,_=QFileDialog.getSaveFileName(self,'Backup project',str(source.with_stem(source.stem+'-backup')),'Cue Atlas project (*.cueatlas)')
        if not path:return
        target=Path(path if path.lower().endswith('.cueatlas') else path+'.cueatlas')
        try:
            if target.resolve()==source.resolve() or (target.exists() and target.samefile(source)):raise ValueError('Choose a different backup file.')
            db=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
            try:
                backup=sqlite3.connect(target)
                try:db.backup(backup)
                finally:backup.close()
            finally:db.close()
            self.window.remember_project(str(target.resolve()));self.refresh(str(target.resolve()))
        except Exception as exc:QMessageBox.warning(self,'Backup project',str(exc))
    def show_folder(self):
        info=self.selected()
        if info and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(info['path']).parent))):QMessageBox.warning(self,'Open folder','The project folder could not be opened.')
    def forget_selected(self):
        info=self.selected()
        if info:self.window.forget_project(info['path']);self.refresh()
    def trash_selected(self):
        info=self.selected()
        if not info or not project_info(info['path'])['valid']:return
        question=f'Move “{info["name"]}” to Trash?\n\nThis removes the project file, including its cues and reference fingerprints. Original audio and video files are kept.\n\nRestore the file from Trash in Finder if needed; cue Undo cannot restore a project.'
        if QMessageBox.question(self,'Move project to Trash?',question,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        active_path=self.window.p.path if self.window.p and self.window.p.path==Path(info['path']).resolve() else None
        if active_path:self.window.close_project()
        try:
            result=QFile.moveToTrash(info['path']);success=result[0] if isinstance(result,tuple) else result
            if not success:raise OSError('The project could not be moved to Trash. The file was kept in its original location.')
        except Exception as exc:
            if active_path:self.window.load(str(active_path))
            QMessageBox.warning(self,'Move project to Trash',str(exc));return
        self.window.forget_project(info['path']);self.window.status.setText('Project moved to Trash');self.refresh()
