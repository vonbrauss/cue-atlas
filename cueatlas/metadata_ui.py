"""Editors and previews for structured reference metadata."""
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QTableWidget,QTableWidgetItem,QHeaderView,QComboBox,QDialog,QDialogButtonBox,QTextEdit)
from PySide6.QtCore import Qt
from .enrichment import PARTY_ROLES,validate_parties
from .metadata import parse_parties


class PartiesEditor(QWidget):
    def __init__(self,parties,parent=None,credit_text=None):
        super().__init__(parent);self.credit_text=credit_text or {};layout=QVBoxLayout(self)
        hint=QLabel('One row per writer or publisher. Keep PRO, IPI and share with that party. Blank shares remain unknown; writer and publisher shares are separate.')
        hint.setWordWrap(True);layout.addWidget(hint)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(['Role','Name','PRO','IPI','Share %'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(44)
        for col,width in enumerate([160,210,80,140]):self.table.setColumnWidth(col,width)
        layout.addWidget(self.table)
        for p in parties:self.add(p)
        row=QHBoxLayout();add=QPushButton('Add party');add.clicked.connect(lambda:self.add({}))
        remove=QPushButton('Remove selected parties');remove.clicked.connect(self.remove)
        paste=QPushButton('Paste credit lists…');paste.clicked.connect(self.paste_credits)
        row.addWidget(add);row.addWidget(remove);row.addWidget(paste);row.addStretch();layout.addLayout(row)
    def paste_credits(self):
        dialog=CreditTextDialog(self.credit_text,self)
        if dialog.exec():
            self.table.setRowCount(0)
            for party in dialog.parties:self.add(party)
            self.credit_text={'composer':dialog.composers.toPlainText(),'publisher':dialog.publishers.toPlainText()}
    def add(self,party):
        row=self.table.rowCount();self.table.insertRow(row)
        role=QComboBox()
        for value in sorted(PARTY_ROLES):role.addItem(value.replace('_',' / ').title(),value)
        role.setCurrentIndex(role.findData(party.get('role','composer')));self.table.setCellWidget(row,0,role)
        for col,key in enumerate(['name','pro','ipi','share_percent'],1):
            value=party.get(key,'');self.table.setItem(row,col,QTableWidgetItem('' if value is None else str(value)))
    def remove(self):
        for row in sorted({i.row() for i in self.table.selectedIndexes()},reverse=True):self.table.removeRow(row)
    def values(self):
        values=[]
        for row in range(self.table.rowCount()):
            def text(col):return self.table.item(row,col).text().strip()
            try:share=float(text(4)) if text(4) else None
            except ValueError:raise ValueError('Party shares must be numbers, or blank.')
            values.append({'role':self.table.cellWidget(row,0).currentData(),'name':text(1),
                           'pro':text(2),'ipi':text(3),'share_percent':share})
        return validate_parties(values)


class CreditTextDialog(QDialog):
    def __init__(self,credits=None,parent=None):
        super().__init__(parent);self.setWindowTitle('Paste credit lists');self.resize(760,650);self.parties=[]
        credits=credits or {};layout=QVBoxLayout(self)
        hint=QLabel('Paste names separated by commas, semicolons, or new lines. Slashes inside names and affiliations stay intact. Quote names that contain commas. Preview before replacing the Rights parties rows. Existing IPI numbers and shares are replaced by the pasted values; the reference changes only when you Save metadata.')
        hint.setWordWrap(True);layout.addWidget(hint)
        layout.addWidget(QLabel('Composers / writers'));self.composers=QTextEdit();self.composers.setAcceptRichText(False);self.composers.setMaximumHeight(100);self.composers.setPlainText(credits.get('composer',''));layout.addWidget(self.composers)
        layout.addWidget(QLabel('Publishers'));self.publishers=QTextEdit();self.publishers.setAcceptRichText(False);self.publishers.setMaximumHeight(140);self.publishers.setPlainText(credits.get('publisher',''));layout.addWidget(self.publishers)
        preview=QPushButton('Preview parties');preview.clicked.connect(self.preview);layout.addWidget(preview)
        self.preview_text=QTextEdit();self.preview_text.setReadOnly(True);layout.addWidget(self.preview_text,1)
        buttons=QDialogButtonBox(QDialogButtonBox.Cancel);self.use=buttons.addButton('Use these parties',QDialogButtonBox.AcceptRole);self.use.setEnabled(False)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.composers.textChanged.connect(lambda:self.use.setEnabled(False));self.publishers.textChanged.connect(lambda:self.use.setEnabled(False))
    def preview(self):
        self.parties=parse_parties(self.composers.toPlainText(),'composer')+parse_parties(self.publishers.toPlainText(),'publisher')
        self.preview_text.setPlainText('\n\n'.join(f"{p['role'].title()} · {p['name']}\nPRO: {p['pro'] or 'Not provided'} · Share: {str(p['share_percent'])+'%' if p['share_percent'] is not None else 'Unknown'}" for p in self.parties) or 'No parties found.')
        self.use.setEnabled(bool(self.parties))


class MetadataPreview(QDialog):
    def __init__(self,plan,skipped,parent=None,mode='fill'):
        super().__init__(parent);self.setWindowTitle('Review metadata changes');self.resize(760,600)
        layout=QVBoxLayout(self)
        description='Provided edits replace existing values; blank text clears a field.' if mode=='update' else 'Existing values are preserved; only missing information is filled.'
        hint=QLabel(f'{len(plan)} references to update. {description}\nA recovery snapshot is saved before applying. Review imported credits and licensing information before delivery.')
        hint.setWordWrap(True);layout.addWidget(hint)
        import json
        details=[]
        for item in plan:
            details.append(item['title'])
            for field in item['fields']:
                details.append(f"  {field}\n    Before: {json.dumps(item['before'].get(field,''),ensure_ascii=False)}\n    After:  {json.dumps(item['metadata'][field],ensure_ascii=False)}")
        if skipped:details.extend(['','Skipped entries:',*skipped])
        viewer=QTextEdit();viewer.setReadOnly(True);viewer.setPlainText('\n\n'.join(details) or 'No metadata changes found.');layout.addWidget(viewer)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('Apply changes');buttons.button(QDialogButtonBox.Save).setEnabled(bool(plan))
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)


class MetadataImportDialog(QDialog):
    def __init__(self,path,parent=None):
        super().__init__(parent);self.setWindowTitle('Import reference metadata JSON');self.resize(620,290)
        layout=QVBoxLayout(self);title=QLabel('Update your reference licensing information');title.setStyleSheet('font-size:20px;font-weight:600;color:#a4eed9;');layout.addWidget(title)
        file=QLabel(str(path));file.setWordWrap(True);file.setTextFormat(Qt.PlainText);layout.addWidget(file)
        self.mode=QComboBox();self.mode.addItem('Apply edits to existing references','update');self.mode.addItem('Fill blank fields only','fill');layout.addWidget(self.mode)
        hint=QLabel('Apply edits supports corrections and clearing text with an empty string.\nUnchanged fields in a new export are left alone. You will preview old and new values before anything is saved.')
        hint.setWordWrap(True);layout.addWidget(hint)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.Ok).setText('Preview changes')
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
