import json
import numpy as np
from PySide6.QtWidgets import QApplication,QStyledItemDelegate
from cueatlas import engine
from cueatlas.project import Project
from cueatlas.workflow_ui import ReviewQueueDialog,table,fill
from test_timeline import open_window


def legacy_support(frames):
    return [t for t in frames if sum(abs(t-j)<=22 for j in frames)>=3]


def test_matching_support_is_identical_at_boundaries_and_with_sparse_noise(monkeypatch):
    cases=[[],[0],[0,22,44],[0,23,46],[-22,0,22],[0,1,2,100,101,102]]
    rng=np.random.default_rng(72)
    cases.extend(sorted(set(rng.integers(-100,1000,size=n).tolist())) for n in (3,20,300,1000))
    for frames in cases:assert engine.supported_frames(frames)==legacy_support(frames)
    import sqlite3
    db=sqlite3.connect(':memory:');db.execute('CREATE TABLE hashes(hash INTEGER,track TEXT,frame INTEGER)')
    fp=[];stored=[]
    for h in range(180):
        t=int(rng.integers(0,900));fp.append((h,t))
        for tid,offset in [('a',8),('b',-18)]:stored.append((h,tid,t+offset+int(rng.integers(-1,2))))
    stored.extend((int(rng.integers(0,180)),'noise',int(rng.integers(0,900))) for _ in range(300))
    db.executemany('INSERT INTO hashes VALUES(?,?,?)',stored)
    actual=engine.match_chunk(db,fp,12)
    monkeypatch.setattr(engine,'supported_frames',legacy_support);expected=engine.match_chunk(db,fp,12)
    assert len(actual)==len(expected)>0
    for a,b in zip(actual,expected):
        assert a[:2]==b[:2] and a[3]==b[3];np.testing.assert_array_equal(a[2],b[2])
    db.close()


def test_review_queue_idle_polling_skips_cues_and_observes_external_updates(tmp_path):
    app,w,rows=open_window(tmp_path);rows[1]['status']='Needs review';w.p.save_cues(rows)
    q=ReviewQueueDialog(w);queries=[];w.p.db.set_trace_callback(queries.append)
    for _ in range(20):q.refresh()
    assert not any('SELECT' in sql.upper() for sql in queries)
    w.p.db.set_trace_callback(None)
    other=Project(w.p.path)
    with other.db:
        metadata=other.track(rows[1]['track'])['metadata'];metadata['title']='Updated reference title'
        other.db.execute('UPDATE tracks SET metadata=? WHERE id=?',(json.dumps(metadata),rows[1]['track']))
    q.refresh();assert q.table.item(1,0).text()=='Updated reference title'
    other.set('settings',other.settings|{'origin':'02:00:00;00'})
    q.refresh();assert q.table.item(0,1).text().startswith('02:')
    changed=other.cues();changed[1]['status']='Reviewed';other.save_cues(changed)
    q.refresh();assert rows[1]['id'] not in {r['id'] for r in q.rows}
    other.close();q.close();w.close();app.processEvents()


def test_review_queue_never_displays_uncommitted_edits(tmp_path):
    app,w,rows=open_window(tmp_path);q=ReviewQueueDialog(w)
    w.p.db.execute('DELETE FROM cues WHERE id=?',(rows[0]['id'],));q.refresh()
    assert rows[0]['id'] in {r['id'] for r in q.rows}
    w.p.db.rollback();q.refresh();assert rows[0]['id'] in {r['id'] for r in q.rows}
    q.close();w.close();app.processEvents()


def test_secondary_dialog_tables_defer_content_measurements():
    app=QApplication.instance() or QApplication([]);widget=table(['Cue','In','Out','Reason'])
    rows=[[str(i),'01:00:00;00','01:00:02;00','Needs review'] for i in range(100)]
    fill(widget,rows);widget.show();app.processEvents()
    class Counter(QStyledItemDelegate):
        calls=0
        def sizeHint(self,option,index):
            self.calls+=1;return super().sizeHint(option,index)
    delegate=Counter(widget);widget.setItemDelegate(delegate)
    widget.model().dataChanged.connect(lambda first,*_:widget.visualRect(first))
    fill(widget,rows);app.processEvents()
    assert delegate.calls<100*4*4
    assert widget.item(99,0).text()=='99'
    widget.close();app.processEvents()
