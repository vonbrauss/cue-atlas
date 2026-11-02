import csv
import pytest
from openpyxl import load_workbook
from cueatlas.project import Project,cue
from cueatlas.coverage import covered_seconds
from cueatlas.export import export
from cueatlas.engine import repair_coverage
from cueatlas.audio import SR
from scipy.io.wavfile import write
import numpy as np


def test_exclusion_persists_restores_and_filters_both_exports(tmp_path):
    p=Project(tmp_path/'exclude.cueatlas',True,'Exclusion')
    p.set('program',{'duration':9})
    cues=[cue(None,0,3,title='Keep'),cue(None,3,6,title='Not music'),cue(None,6,9,title='Keep too')]
    p.save_cues(cues);p.set_cues_excluded([cues[1]['id']])
    assert p.cues()==cues and covered_seconds(p.cues(),9)==9
    assert p.included_cues()==[cues[0],cues[2]]
    with pytest.raises(ValueError,match='Restore'):p.merge_selection([cues[0]['id'],cues[1]['id']])
    for suffix in ['csv','xlsx']:
        path=tmp_path/f'export.{suffix}';export(p,path)
        if suffix=='csv':
            with path.open(encoding='utf-8-sig') as f:rows=list(csv.reader(f))
        else:rows=list(load_workbook(path).active.values)
        assert [r[1] for r in rows[1:]]==['Keep','Keep too']
        assert [int(r[0]) for r in rows[1:]]==[1,2]
    path=p.path;p.close();p=Project(path)
    assert p.excluded_cue_ids()=={cues[1]['id']}
    p.set_cues_excluded([cues[1]['id']],False)
    assert p.included_cues()==cues
    p.set_cues_excluded([cues[0]['id'],cues[1]['id']])
    p.save_cues([]);assert not p.excluded_cue_ids()
    p.close()


def test_repair_keeps_excluded_placeholder(tmp_path):
    p=Project(tmp_path/'repair.cueatlas',True,'Repair')
    audio=tmp_path/'program.wav';write(audio,SR,np.zeros(SR*6,dtype=np.float32))
    p.set('program',{'path':str(audio),'duration':6})
    rows=[cue(None,0,3),cue(None,3,6)];p.save_cues(rows)
    p.set_cues_excluded([rows[0]['id']]);repair_coverage(p.path)
    assert p.cues()==rows and p.included_cues()==[rows[1]]
    p.close()
