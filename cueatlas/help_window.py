"""Searchable, topic-based local help using the same guide as the documentation."""
from html import escape
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont,QTextCursor,QTextBlockFormat,QTextCharFormat,QColor
from PySide6.QtWidgets import (QDialog,QHBoxLayout,QVBoxLayout,QLabel,QLineEdit,
                              QListWidget,QListWidgetItem,QTextBrowser,QPushButton,QFrame)
from . import __version__
from .help import GUIDE


WELCOME = '''## Make every cue count

A quick route from program audio to a reviewed cue sheet.

### 01 · Set up your project
Create a project, add your reference library, choose program media, and analyze.

### 02 · Find the right moment
Use **Down / Up** for next / previous edit. Step one frame with **Left / Right**, or one second with **Shift+Left / Right**.

### 03 · Build and identify a cue
Press **I** at the start and **O** at the end, then **N** to create the cue. Press **F** to identify it. Choose **Review candidate** to fill the reference and title, then compare and Save.

### 04 · Refine and deliver
Trim to the playhead with **Q / W**, review with **Enter**, and export your cue sheet. **Command/Ctrl-Z** undoes cue edits.

### Your workspace, your pace
Two-finger scrolling pans without pulling you back to the playhead. **Backslash** fits the full program. Search this guide or choose a topic on the left for details.
'''

UPDATES = '''## What’s new

### Responsive reference comparison · 0.9.2

Cue review prepares only the requested audio interval in a cancellable background task. Playback uses disposable local WAVs, with a 30-second preparation timeout and reuse within the review window. Opening review no longer opens the full program in another player. Local GUI-stall reports are retained in ~/Library/Logs/CueAtlas for troubleshooting.

### Playback keys and cue colors · 0.9.1

Space controls playback instead of activating focused toolbar buttons. Q/W trim or extend a selected cue’s start/end to the cursor. Option/Alt-I clears In, Option/Alt-O clears Out, and Option/Alt-X clears both. Unknown cues are yellow; repeated references share a color and different references receive distinct colors.

### Timeline AI listening · 0.9.0

Option/Alt-drag on the timeline to mark an audio range, or use I/O marks or selected cues. Click **Separate range** to reduce dialogue for that section without changing cues. Switch **Program audio / AI music** above the waveform to compare at the same playhead position. The waveform follows the selected audio; blue strips show separated sections. Outside those sections, original program audio plays and the playback label says so. Existing cached AI results are reusable.

### Standard + AI follow-up and version review · 0.8.0

Standard + AI follow-up searches the original program first, then separates only remaining Unknowns. Results retain original and AI evidence and show agreement with neighboring reference positions. Applying proposals can join supported continuous uses of the same recording in one undoable edit.

Vocal and instrumental recordings keep separate licensing. Uncertain versions are labeled Version needs review and remain unassigned until a recording is chosen. Review prioritizes the proposed versions and retains their individual comparison positions.

### Full-program AI analysis · 0.7.3

Analyze now offers Standard analysis or AI music separation for the initial full-program search. AI sections use overlapping context and caching while the editor continues to display and play the original source. Cancellation or separation errors preserve previous cues.

### AI matching and splitting · 0.7.0

Optional local music separation is installed from Project settings. Retry selected cues or all Unknown cues, compare original and separated results, and apply chosen matches with adjoining same-reference cues joined in one undoable edit.

Press **S** to split one selected cue at the playhead. Both pieces preserve reference, review state, and exclusion. Undo/Redo is supported.

### Lasso timeline selection · 0.6.10
Click and drag from empty timeline space to select cues touched by a selection box. You can start below the cues on the waveform and drag upward. Command/Ctrl-drag adds to the selection; Escape restores the previous selection. A simple waveform click still places the free-play cursor, and Shift-drag still creates a cue.

### Less work between edits · 0.6.9
Review, validation, marker, recovery, duplicate, and project-browser tables now defer column measurements until updates finish. The review queue avoids rereading cues while idle and still refreshes after edits from other project connections. Audio matching checks nearby fingerprint support with a moving window, preserving the same evidence rules and results.

### Simpler menus and export · 0.6.8
Project settings live only in Project. The program gear holds source selection, analysis, and snapping; shortcut editing lives in Edit, reference tools in Library, and review tools in Cue sheet. Export opens the save dialog directly, with an optional **Show warnings** button. Invalid cue timings still need correction before exporting.

### Faster table refreshes · 0.6.7
Cue and reference tables now suspend automatic column measurement while updating cells, then size the completed table once. This removes repeated text layout that could freeze the visible interface after deleting or merging cues.

### Responsive cue edits · 0.6.6
Deleting, merging, trimming, and excluding cues no longer copy the full reference fingerprint database. Edits write only changed cue rows and save their Undo/Redo state in the same transaction. Full recovery snapshots remain available for major project changes and manual checkpoints.

### Faster search and editable credits · 0.6.5
Reference search uses cached metadata, avoiding repeated database reads, file checks, and duplicate detection as you type. Composer and publisher fields now accept editing and clearing, with Rights parties synchronized on leaving the field or saving.

### Accurate credit lists · 0.6.4
Comma-separated composer and publisher lists now produce separate Rights parties rows. Sony/ATV-style names and combined affiliations such as SACEM/BIEM stay intact. Use **Rights parties → Paste credit lists** to preview and replace lists affected by earlier parsing, then Save metadata.

### Find and organize references · 0.6.3
Search the Reference library between Import library and Metadata. Expand it with its focus icon or Library → Focus reference library. Both tables now have left-aligned headers and support ascending/descending sorting by clicking column titles. Numeric columns sort by value, and row actions continue to target the selected entry.

### A compact reference library · 0.6.2
The Reference library now uses one toolbar row. Open **Metadata** for Edit selected reference, Export metadata JSON, Import metadata JSON, and Recover embedded metadata. Double-click a track to edit its metadata directly. The same menu is available from **Library → Metadata**.

### A clearer project workspace · 0.6.1
Import and Export metadata JSON now sit together in the Reference library. Library commands also have their own menu. The Project dropdown and menu bar share one organized menu, with a compact Recent projects submenu. **Browse projects** opens a searchable browser with Favorites, Unavailable, and name or recency sorting. Older projects stay in your saved list.

### Licensing JSON round-trip · 0.6.0
Export reference metadata, edit licensing details externally, then use **Reference library → Metadata → Import metadata JSON** to preview and apply corrections. Choose replacement edits or fill-only mode. Original-values baselines help detect stale edits. The **JSON licensing round-trip** topic includes the format, copyable examples, field rules, and matching behavior.

### Review, protect, and deliver · 0.5.0
- **Review queue** shows Unknown, weak, and unreviewed assignments with a live remaining count. Press **R** for the next outstanding cue.
- **Recovery snapshots** preserve dated project states before major changes, with a restore screen and the newest 20 recovery points retained.
- **Cue-sheet validation** flags metadata gaps, invalid timing, overlaps, and unreviewed assignments before export.
- **Edit → Keyboard shortcuts** lets you reassign editor keys and resolve conflicts. The shortcut reference shows your current bindings.
- **B** adds a saved marker comment at an exact program time. Manage comments from Cue sheet → Markers and comments.
- Reference import skips exact duplicate files; the duplicate report also flags possible alternate mixes by title for listening review.
- **Project → Create handoff package** collects a project, reports, comments, and optional linked recordings into a portable folder.

### Faster editing · 0.4.0
- **Left / Right**: step one frame. **Shift+Left / Right**: step one second.
- **Home / End**: program start / end (Fn+Left / Right on compact Mac keyboards).
- **I / O**, then **N**: mark and create a new cue. Marks appear as dashed lines.
- **F**: identify. **Enter**: review. **X**: exclude or restore.
- **Escape**: cancel a drag; otherwise stop playback and clear marks and selection.
- **Backslash**: fit the full program.

### Recent improvements · 0.3
- **Down** goes to the next edit; **Up** goes to the previous edit.
- **Q / W** trim the cue start / end to the playhead without shifting other cues.
- Two-finger panning stays independent of playback follow, including after you release the trackpad.
- Choosing an identification candidate fills its reference title into the cue title for review.

### A clearer guide
Browse by topic, search the full guide, or jump directly to Keyboard shortcuts from the Help menu. All help is available offline.
'''


class HelpDialog(QDialog):
    def __init__(self,parent=None,topic='Start here'):
        super().__init__(parent)
        self.setWindowTitle('Cue Atlas · Help');self.resize(1000,740);self.setMinimumSize(760,520)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setObjectName('helpWindow')
        self.setStyleSheet('''
            QDialog#helpWindow { background:#10191d; }
            QLabel#helpTitle { font-size:28px; font-weight:700; color:#f0f8f6; }
            QLabel#helpSubtitle { color:#9bb2b6; font-size:13px; }
            QLabel#helpBadge { color:#80e5c7; background:#1c3631; border-radius:9px; padding:6px 12px; }
            QFrame#helpPanel { background:#152227; border:1px solid #293c43; border-radius:12px; }
            QLineEdit { padding:11px; border:1px solid #385259; border-radius:8px; background:#18282d; }
            QListWidget { background:transparent; border:0; outline:0; font-size:13px; }
            QListWidget::item { padding:12px 10px; margin:2px 0; border-radius:7px; color:#a9bfc2; }
            QListWidget::item:selected { background:#244b43; color:#9cf0d6; }
            QListWidget::item:hover { background:#20343a; }
            QTextBrowser { background:#152227; border:0; color:#e0eaeb; font-size:16px; selection-background-color:#326c5d; }
        ''')
        self.topics=[('Start here',WELCOME),('What’s new',UPDATES)]
        for section in GUIDE.split('\n## ')[1:]:
            title,_,body=section.partition('\n')
            self.topics.append(('Keyboard shortcuts' if title.startswith('Keyboard shortcuts') else title,
                                '## '+title+'\n'+body))
        layout=QVBoxLayout(self);layout.setContentsMargins(28,24,28,20);layout.setSpacing(20)
        header=QHBoxLayout();titles=QVBoxLayout();titles.setSpacing(5)
        title=QLabel('The Cue Atlas guide');title.setObjectName('helpTitle');titles.addWidget(title)
        subtitle=QLabel('Find your flow. Shape your cues.');subtitle.setObjectName('helpSubtitle');titles.addWidget(subtitle)
        header.addLayout(titles);header.addStretch()
        badge=QLabel('v'+__version__+'  ·  OFFLINE GUIDE');badge.setObjectName('helpBadge');header.addWidget(badge)
        layout.addLayout(header)
        content=QHBoxLayout();content.setSpacing(20)
        sidebar=QVBoxLayout();sidebar.setSpacing(12)
        self.search=QLineEdit();self.search.setPlaceholderText('Search the guide…');self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName('Search help topics');sidebar.addWidget(self.search)
        self.navigation=QListWidget();self.navigation.setAccessibleName('Help topics');sidebar.addWidget(self.navigation,1)
        self.navigation.setWordWrap(True);self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left=QFrame();left.setLayout(sidebar);left.setFixedWidth(245);content.addWidget(left)
        panel=QFrame();panel.setObjectName('helpPanel');panel_layout=QVBoxLayout(panel);panel_layout.setContentsMargins(24,16,24,16)
        self.browser=QTextBrowser();self.browser.setAccessibleName('Help article')
        article_font=QFont('Helvetica Neue');article_font.setPixelSize(16)
        self.browser.setFont(article_font)
        self.browser.document().setDefaultStyleSheet('''
            h2 { color:#f0f8f6; font-size:24px; margin-bottom:20px; }
            h3 { color:#8ce4c9; font-size:16px; margin-top:24px; }
            p, li { line-height:150%; } strong { color:#a4eed9; }
            table { border-collapse:collapse; width:100%; }
            th { background:#244139; color:#a4eed9; padding:12px; }
            td { padding:10px; border-bottom:1px solid #30474e; }
        ''')
        panel_layout.addWidget(self.browser);content.addWidget(panel,1);layout.addLayout(content,1)
        footer=QHBoxLayout();hint=QLabel('HELP  /  Browse topics or search by action and key')
        hint.setObjectName('helpSubtitle');footer.addWidget(hint);footer.addStretch()
        close=QPushButton('Done');close.clicked.connect(self.close);close.setAutoDefault(False);footer.addWidget(close);layout.addLayout(footer)
        self.navigation.currentItemChanged.connect(self.display_topic)
        self.search.textChanged.connect(self.filter_topics)
        self.filter_topics('');self.open_topic(topic)

    def open_topic(self,title):
        self.search.clear()
        for row in range(self.navigation.count()):
            if self.navigation.item(row).text()==title:self.navigation.setCurrentRow(row);return

    def filter_topics(self,query):
        current=self.navigation.currentItem()
        selected=current.text() if current else None
        self.navigation.clear()
        for title,body in self.topics:
            if all(word in (title+' '+body).casefold() for word in query.casefold().split()):
                item=QListWidgetItem(title);item.setData(Qt.UserRole,body);self.navigation.addItem(item)
        if self.navigation.count():
            row=next((i for i in range(self.navigation.count()) if self.navigation.item(i).text()==selected),0)
            self.navigation.setCurrentRow(row)
        else:
            self.browser.setMarkdown('## No matching topics\nTry an action such as **trim**, **identify**, or **scroll**.')
            self.format_article()

    def format_article(self):
        # Markdown import does not reliably apply paragraph CSS. Set native Qt
        # block formats so spacing survives topic changes and search results.
        block=self.browser.document().begin()
        while block.isValid():
            cursor=QTextCursor(block);fmt=block.blockFormat();heading=fmt.headingLevel()
            in_table=cursor.currentTable() is not None
            code=fmt.hasProperty(QTextBlockFormat.BlockCodeLanguage) or fmt.hasProperty(QTextBlockFormat.BlockCodeFence)
            fmt.setLineHeight(145,QTextBlockFormat.ProportionalHeight.value)
            fmt.setTopMargin(24 if heading and block.blockNumber() else 0)
            fmt.setBottomMargin(12 if heading else (0 if code else (6 if in_table else 18)))
            cursor.setBlockFormat(fmt)
            if heading:
                cursor.select(QTextCursor.BlockUnderCursor)
                char=QTextCharFormat();char.setFontPointSize(20 if heading<=2 else 14)
                char.setForeground(QColor('#f0f8f6' if heading<=2 else '#9ce8d1'))
                cursor.mergeCharFormat(char)
            block=block.next()

    def display_topic(self,item,previous=None):
        if item:
            body=item.data(Qt.UserRole)
            if item.text()=='Keyboard shortcuts':
                rows=[]
                parent=self.parent()
                if parent and hasattr(parent,'shortcut_bindings'):
                    from .shortcuts import COMMANDS
                    bindings=parent.shortcut_bindings
                    entries=[(bindings.get(command,'') or 'Unassigned',label,
                              'Waveform or cue sheet' if context=='Both' else context)
                             for command,label,default,context,repeat in COMMANDS]
                    entries.extend([('Shift+Up / Down','Extend row selection','Cue sheet'),
                                    ('Command/Ctrl-Z','Undo; cancel an unfinished drag','Editing workspace'),
                                    ('Command/Ctrl-Shift-Z','Redo','Editing workspace'),
                                    ('Command/Ctrl + / −','Zoom around playhead','Main window')])
                else:
                    entries=[]
                    for line in body.splitlines():
                        if not line.startswith('|') or line.startswith('| Key') or line.startswith('| ---'):continue
                        entries.append(tuple(part.strip() for part in line.strip('|').split('|')))
                for key,action,scope in entries:
                    rows.append('<tr><td width="140" bgcolor="#203b35" style="color:#a4eed9;font-weight:600;">'
                                +escape(key)+'</td><td>'+escape(action)
                                +'<br><span style="color:#a5bdc2;font-size:13px;">'+escape(scope)+'</span></td></tr>')
                self.browser.setHtml('<h1 style="font-size:25px;color:#f0f8f6;">Keyboard shortcuts</h1>'
                                     '<p style="color:#a5babe;">Current editor bindings. Change them in Edit → Keyboard shortcuts. Click the waveform or cue sheet first; text fields retain normal typing.</p>'
                                     '<table width="100%" border="0" cellspacing="6" cellpadding="10">'
                                     +''.join(rows)+'</table>'
                                     '<p>Down: next edit. Up: previous edit. Navigation keeps cue selection unchanged. '
                                     'On compact Mac keyboards, use Fn+Left / Right for Home / End. '
                                     'See Cue editing for trim rules and mark behavior.</p>')
            else:self.browser.setMarkdown(body)
            self.format_article()
            self.browser.verticalScrollBar().setValue(0)
