from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog
from cueatlas.workflow_ui import ReviewQueueDialog,ValidationDialog,MarkerEditDialog
from test_timeline import open_window


def test_review_queue_jumps_and_refreshes_after_confirming(tmp_path):
    app,w,rows=open_window(tmp_path);queue=ReviewQueueDialog(w)
    assert len(queue.rows)==2 and '2 cues' in queue.count.text()
    queue.move(1)
    assert w.timeline.position==6 and w.selected_cues()[0]['id']==rows[2]['id']
    changed=w.p.cues();changed[-1].update(track=rows[1]['track'],status='Reviewed')
    w.p.save_cues(changed,label='Review cue');w.refresh();queue.refresh()
    assert len(queue.rows)==1 and '1 cues' in queue.count.text()
    queue.close();w.close();app.processEvents()


def test_validation_go_to_cue_and_marker_shortcut(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);dialog=ValidationDialog(w,True)
    assert any(i['code']=='composer' for i in dialog.issues)
    row=next(i for i,issue in enumerate(dialog.issues) if issue['code']=='composer')
    dialog.table.selectRow(row);dialog.jump();assert w.selected_cues()[0]['id']==rows[1]['id']
    def accept_marker(dialog):
        dialog.text.setPlainText('Confirm ending');dialog.accept();return QDialog.Accepted
    monkeypatch.setattr(MarkerEditDialog,'exec',accept_marker)
    w.seek(4);QTest.keyClick(w.timeline,Qt.Key_B)
    assert w.p.get('markers')[0]['text']=='Confirm ending'
    assert w.timeline.markers[0]['position']==4
    QTest.keyClick(w.timeline,Qt.Key_R)
    assert w.selected_cues()[0]['id']==rows[2]['id']
    w.close();app.processEvents()
