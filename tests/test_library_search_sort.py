from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from test_timeline import open_window


def click_column(table,column):
    header=table.horizontalHeader()
    QTest.mouseClick(header.viewport(),Qt.LeftButton,pos=QPoint(header.sectionViewportPosition(column)+10,header.height()//2))


def test_reference_search_sort_selection_and_focus(tmp_path):
    app,w,rows=open_window(tmp_path)
    try:
        path=tmp_path/'alternate.wav';path.write_bytes(b'audio')
        tid=w.p.save_track(path,100,{'title':'A different track','composer':'JANE SMITH','publisher':'Publisher'},[])
        w.refresh();w.set_waveform_focus(False);w.resize(950,650);w.tabs.setCurrentIndex(1);app.processEvents()
        assert w.width()==950
        for widget in [w.reference_search,w.metadata_button,w.reference_focus_button]:
            point=widget.mapTo(w.centralWidget(),QPoint(0,0))
            assert widget.isVisible() and point.x()+widget.width()<=w.centralWidget().width()
        w.reference_search.setText('jane');assert [t['id'] for t in w.track_rows]==[tid]
        w.reference_table.selectRow(0);w.reference_search.clear();assert w.selected_track()['id']==tid
        click_column(w.reference_table,4)
        assert [t['duration'] for t in w.track_rows]==[12,100] and w.selected_track()['id']==tid
        click_column(w.reference_table,4)
        assert [t['duration'] for t in w.track_rows]==[100,12]
        w.refresh();assert w.selected_track()['id']==tid
        w.reference_search.setText('no match');assert not w.track_rows and w.selected_track() is None
        w.reference_search.clear();w.reference_focus_button.click();app.processEvents()
        assert w.program_card.isHidden() and w.tabs.tabBar().isHidden() and w.reference_focus_action.isChecked()
        w.set_cue_focus(True);assert not w.reference_focus_button.isChecked() and w.tabs.currentIndex()==0
        w.set_reference_focus(True);w.set_waveform_focus(True);assert not w.reference_focus_button.isChecked() and w.tabs.isHidden()
        w.set_waveform_focus(False);assert not w.program_card.isHidden() and not w.tabs.tabBar().isHidden()
        w.tabs.setCurrentIndex(1);app.processEvents();w.grab().save('/private/tmp/cueatlas-library-063.png')
    finally:w.close();app.processEvents()


def test_cue_sort_keeps_identity_selection_and_numbers(tmp_path):
    app,w,rows=open_window(tmp_path)
    try:
        w.set_waveform_focus(False);app.processEvents();w.cue_table.selectRow(0)
        original=w.p.cues()
        click_column(w.cue_table,4);click_column(w.cue_table,4)
        assert [c['end']-c['start'] for c in w.cue_rows]==[6,4,2]
        assert w.selected_cue()['id']==rows[0]['id']
        w.refresh();assert w.selected_cue()['id']==rows[0]['id']
        w.timeline.current_id=rows[2]['id'];w.select_timeline_cues([rows[2]['id']]);assert w.selected_cue()['id']==rows[2]['id']
        assert w.cue_table.item(0,0).text()=='3'
        w.p.set_cues_excluded([w.selected_cue()['id']]);w.refresh()
        assert rows[2]['id'] not in [c['id'] for c in w.cue_rows]
        w.filter.setCurrentText('Excluded');assert w.cue_rows[0]['id']==rows[2]['id']
        assert w.p.cues()==original
        for table in [w.cue_table,w.reference_table]:
            assert table.horizontalHeader().defaultAlignment() & Qt.AlignLeft
    finally:w.close();app.processEvents()
