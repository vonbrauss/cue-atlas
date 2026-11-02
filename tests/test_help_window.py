from PySide6.QtWidgets import QApplication
from cueatlas.help_window import HelpDialog


def test_help_search_topics_and_shortcut_reference():
    app=QApplication.instance() or QApplication([])
    dialog=HelpDialog(topic='Keyboard shortcuts')
    text=dialog.browser.toPlainText()
    for key in ('Down','Up','Shift+Left / Right','I / O','Backslash','Enter'):
        assert key in text
    dialog.search.setText('snap')
    assert dialog.navigation.count()>0
    assert all('snap' in dialog.navigation.item(i).data(256).lower()
               for i in range(dialog.navigation.count()))
    dialog.search.setText('no-such-topic-000');assert dialog.navigation.count()==0
    assert 'No matching topics' in dialog.browser.toPlainText()
    dialog.open_topic('What’s new');assert 'Faster editing' in dialog.browser.toPlainText()
    dialog.open_topic('Start here');assert 'Make every cue count' in dialog.browser.toPlainText()
    dialog.close();app.processEvents()
