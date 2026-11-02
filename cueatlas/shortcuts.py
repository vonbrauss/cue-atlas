"""Editable, single-stroke editor shortcuts. Menu shortcuts remain reserved."""
import json
from PySide6.QtCore import Qt,QKeyCombination
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,
                              QHeaderView,QKeySequenceEdit,QDialogButtonBox)

# id, label, default, context, allows held-key repeats
COMMANDS=[
    ('next_edit','Next edit','Down','Both',True),('previous_edit','Previous edit','Up','Both',True),
    ('frame_back','Step back one frame','Left','Both',True),('frame_forward','Step forward one frame','Right','Both',True),
    ('second_back','Step back one second','Shift+Left','Both',True),('second_forward','Step forward one second','Shift+Right','Both',True),
    ('home','Program start','Home','Both',False),('end','Program end','End','Both',False),
    ('mark_in','Mark In','I','Both',False),('mark_out','Mark Out','O','Both',False),
    ('clear_marks','Clear In and Out','Alt+X','Both',False),
    ('clear_in','Clear In','Alt+I','Both',False),('clear_out','Clear Out','Alt+O','Both',False),
    ('new_cue','Create marked cue','N','Both',False),('identify','Identify cue','F','Both',False),
    ('review','Review cue','Return','Both',False),('exclude','Exclude / restore','X','Both',False),
    ('cancel','Cancel / clear selection','Esc','Both',False),('fit','Fit program','\\','Both',False),
    ('trim_start','Trim / extend start to playhead','Q','Waveform',False),('trim_end','Trim / extend end to playhead','W','Waveform',False),
    ('reverse','Shuttle backward','J','Both',False),('pause','Pause','K','Both',False),('forward','Shuttle forward','L','Both',False),
    ('play','Play / pause','Space','Both',False),('merge','Merge cues','M','Both',False),
    ('split','Split cue at playhead','S','Both',False),
    ('delete','Delete cues','Delete','Both',False),('audition','Audition boundary','A','Waveform',False),
    ('nudge_back','Nudge boundary backward',',','Waveform',True),('nudge_forward','Nudge boundary forward','.','Waveform',True),
    ('add_marker','Add marker comment','B','Both',False),('next_review','Next cue needing review','R','Both',False),
]
DEFAULTS={c[0]:c[2] for c in COMMANDS}
RESERVED=['Ctrl+N','Ctrl+O','Ctrl+,','Ctrl+E','Ctrl+Z','Ctrl+Shift+Z','Ctrl+Y',
          'Ctrl+Shift+F','Ctrl++','Ctrl+=','Ctrl+Shift+=','Ctrl+-','Shift+Up','Shift+Down']


def canonical(text):
    sequence=QKeySequence(text)
    if sequence.count()==1:
        combination=sequence[0];key=combination.key()
        if key in (Qt.Key_Enter,Qt.Key_Backspace):
            key=Qt.Key_Return if key==Qt.Key_Enter else Qt.Key_Delete
            sequence=QKeySequence(QKeyCombination(combination.keyboardModifiers(),key))
    return sequence.toString(QKeySequence.PortableText)


def conflicts(bindings):
    problems=[];seen={}
    reserved={canonical(k) for k in RESERVED}
    for command,label,default,context,repeat in COMMANDS:
        text=bindings.get(command,'');sequence=QKeySequence(text)
        if not text:continue
        key=canonical(text)
        if sequence.isEmpty() or sequence.count()!=1 or sequence[0].key()==Qt.Key_unknown:
            problems.append(f'{label}: choose one valid key combination.');continue
        if key in reserved:problems.append(f'{label}: {key} is reserved by a menu or row selection.')
        if key in seen:problems.append(f'{label} conflicts with {seen[key]} ({key}).')
        seen[key]=label
    return problems


def load_bindings(prefs):
    try:
        stored=json.loads(prefs.value('keyboard_shortcuts','{}'))
        if not isinstance(stored,dict):return dict(DEFAULTS)
        bindings=DEFAULTS|{k:v for k,v in stored.items() if k in DEFAULTS and isinstance(v,str)}
        # A newly added default must not reset existing custom bindings.
        assigned={canonical(v) for k,v in stored.items() if k in DEFAULTS and isinstance(v,str) and v}
        for k in DEFAULTS:
            if k not in stored and canonical(bindings[k]) in assigned:bindings[k]=''
        return dict(DEFAULTS) if conflicts(bindings) else bindings
    except (TypeError,ValueError):return dict(DEFAULTS)


def event_key(event):
    key=event.key()
    if key==Qt.Key_Enter:key=Qt.Key_Return
    # Both delete keys share the default delete command, but remain assignable.
    if key==Qt.Key_Backspace:key=Qt.Key_Delete
    return QKeySequence(QKeyCombination(event.modifiers() & ~Qt.KeypadModifier,Qt.Key(key))).toString(QKeySequence.PortableText)


class ShortcutDialog(QDialog):
    def __init__(self,bindings,parent=None):
        super().__init__(parent);self.setWindowTitle('Keyboard shortcuts');self.resize(760,650)
        layout=QVBoxLayout(self);hint=QLabel('Click a shortcut and press a new key combination. Clear it to disable.\nApplies in the waveform and cue sheet; text fields keep their normal keys.')
        hint.setWordWrap(True);layout.addWidget(hint)
        layout.addWidget(QLabel('Return / Enter share a binding, as do Delete / Backspace.'))
        self.table=QTableWidget(len(COMMANDS),3);self.table.setHorizontalHeaderLabels(['Action','Shortcut','Where'])
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch);layout.addWidget(self.table)
        self.table.setColumnWidth(1,180);self.table.setColumnWidth(2,100)
        self.table.verticalHeader().setDefaultSectionSize(48);self.table.verticalHeader().hide()
        self.editors={}
        for row,(command,label,default,context,repeat) in enumerate(COMMANDS):
            for col,text in ((0,label),(2,context)):
                item=QTableWidgetItem(text);item.setFlags(item.flags() & ~Qt.ItemIsEditable);self.table.setItem(row,col,item)
            editor=QKeySequenceEdit(QKeySequence(bindings.get(command,'')));editor.setMaximumSequenceLength(1)
            editor.setClearButtonEnabled(True);self.table.setCellWidget(row,1,editor);self.editors[command]=editor
            editor.keySequenceChanged.connect(self.check)
        self.message=QLabel();self.message.setWordWrap(True);layout.addWidget(self.message)
        self.buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel|QDialogButtonBox.RestoreDefaults)
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self.reset)
        layout.addWidget(self.buttons);self.check()
    def bindings(self):return {k:editor.keySequence().toString(QKeySequence.PortableText) for k,editor in self.editors.items()}
    def check(self,*args):
        problems=conflicts(self.bindings());self.message.setText('\n'.join(problems) if problems else 'No conflicts. Changes apply after Save.')
        self.message.setStyleSheet('color:'+('#efb17d' if problems else '#8ce4c9'))
        self.buttons.button(QDialogButtonBox.Save).setEnabled(not problems)
    def reset(self):
        for k,editor in self.editors.items():editor.setKeySequence(QKeySequence(DEFAULTS[k]))
    def accept(self):
        if not conflicts(self.bindings()):super().accept()
