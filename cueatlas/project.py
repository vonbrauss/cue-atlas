import json
import os
import sqlite3
import uuid
from pathlib import Path
from contextlib import contextmanager
from .matching import PRESETS,resolved_settings
DEFAULTS={'rate':'29.97 DF','origin':'01:00:00;00','silence_db':-65,'reference_gain_db':-12,'sensitivity_preset':'Conservative'}|PRESETS['Conservative']
def trim_rows(before,cue_id,start,end,excluded=(),adjust_unknown=False):
    """Pure trim preview shared by the timeline and saved edit."""
    item=next(c for c in before if c['id']==cue_id)
    after=[]
    for c in before:
        c=dict(c)
        if c['id']==cue_id:c.update(start=start,end=end)
        elif adjust_unknown and not c['track'] and c['id'] not in excluded:
            # Adjust unreviewed gap placeholders touched by this edit;
            # retain reviewed/identified neighbors and intentional overlaps.
            if c['status']!='Reviewed' and c['start']>=item['end']-1e-8 and c['start']<end:c['start']=end
            if c['status']!='Reviewed' and c['end']<=item['start']+1e-8 and c['end']>start:c['end']=start
        if c['end']>c['start']:after.append(c)
    return after

class Project:
    def __init__(self,path,create=False,name=None):
        self.path=Path(path).resolve()
        if not create and not self.path.is_file(): raise ValueError('Project file does not exist.')
        if create and self.path.exists(): raise ValueError('Choose a new filename; that project already exists.')
        self._connect(create=create)
        if create:
            self.db.executescript('''
                PRAGMA user_version=1;
                CREATE TABLE info(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE tracks(id TEXT PRIMARY KEY,path TEXT UNIQUE NOT NULL,size INTEGER,mtime INTEGER,duration REAL,metadata TEXT);
                CREATE TABLE hashes(hash INTEGER,track TEXT REFERENCES tracks(id) ON DELETE CASCADE,frame INTEGER);
                CREATE INDEX byhash ON hashes(hash);
                CREATE INDEX bytrack ON hashes(track);
                CREATE TABLE cues(id TEXT PRIMARY KEY,track TEXT REFERENCES tracks(id) ON DELETE SET NULL,start REAL,end REAL,confidence REAL,status TEXT,note TEXT,title TEXT);
            ''')
            self._store_name();self.set('settings',DEFAULTS)
        try:
            if self.db.execute('PRAGMA user_version').fetchone()[0]!=1: raise ValueError('Unsupported project version.')
            row=self.db.execute("SELECT value FROM info WHERE key='name'").fetchone()
            saved=json.loads(row[0]) if row else None
            if not isinstance(saved,str) or not saved.strip():raise ValueError('Invalid Cue Atlas project.')
            if saved!=self.path.stem:self._store_name()
        except Exception:
            self.db.close();raise
    def _connect(self,create=False):
        self.db=sqlite3.connect(self.path) if create else sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True)
        self.db.row_factory=sqlite3.Row;self.db.execute('PRAGMA foreign_keys=ON')
        stat=self.path.stat();self._identity=(stat.st_dev,stat.st_ino);self._history_summary_cache=None
    def _store_name(self):
        with self.db:self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('name',json.dumps(self.path.stem)))
    def sync_path(self):
        """Find a same-folder Finder rename by file identity, never by title."""
        def identity(path):
            try:
                stat=path.stat();return stat.st_dev,stat.st_ino
            except OSError:return None
        if identity(self.path)==self._identity:return False
        try:matches=[p for p in self.path.parent.iterdir() if p.suffix.lower()=='.cueatlas' and identity(p)==self._identity]
        except OSError:return False
        if not matches:return False
        target=sorted(matches)[0].resolve()
        self.db.close();self.path=target;self._connect();self._store_name();return True
    @staticmethod
    def _move_without_replace(source,target):
        # QFile refuses to replace an existing destination and also supports
        # project volumes that cannot create hard links (for example exFAT).
        from PySide6.QtCore import QFile
        file=QFile(str(source))
        if not file.rename(str(target)):raise OSError(file.errorString())
    def _move_project_file(self,source,target,case_only=False):
        if not case_only:self._move_without_replace(source,target);return
        temporary=source.with_name('.cueatlas-rename-'+uuid.uuid4().hex)
        self._move_without_replace(source,temporary)
        try:self._move_without_replace(temporary,target)
        except Exception:self._move_without_replace(temporary,source);raise
    def rename(self,name):
        self.sync_path();name=name.strip()
        if name.lower().endswith('.cueatlas'):name=name[:-9].strip()
        if not name or name in ('.','..') or any(ch in '<>:"/\\|?*' or ord(ch)<32 for ch in name):
            raise ValueError('Use a project name without path separators or filename control characters.')
        target=self.path.with_name(name+'.cueatlas');source=self.path
        if target==source:return self.path
        case_only=(target.name.casefold()==source.name.casefold() and os.path.lexists(target)
                   and target.samefile(source) and target.name not in {p.name for p in source.parent.iterdir()})
        if os.path.lexists(target) and not case_only:raise ValueError('A project with that filename already exists. Choose another name.')
        if self.db.in_transaction:raise ValueError('Finish the current project edit before renaming.')
        if self.db.execute('PRAGMA journal_mode').fetchone()[0]=='wal':
            if self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0]:raise ValueError('Close other connections to this project before renaming.')
            self.db.execute('PRAGMA journal_mode=DELETE')
        self.db.close()
        try:self._move_project_file(source,target,case_only)
        except Exception:self.path=source;self._connect();raise
        self.path=target
        try:self._connect();self._store_name()
        except Exception:
            self.db.close();self._move_project_file(target,source,case_only);self.path=source;self._connect();raise
        return self.path
    def close(self): self.db.close()
    def get(self,key,default=None):
        if key=='name':self.sync_path()
        row=self.db.execute('SELECT value FROM info WHERE key=?',(key,)).fetchone()
        if key=='name' and row:return self.path.stem
        value=json.loads(row[0]) if row else default
        if key=='program' and isinstance(value,dict) and value.get('path') and self.get('portable_paths',False):
            value=value|{'path':str((self.path.parent/value['path']).resolve())}
        return value
    def set(self,key,value):
        if key=='name':self.rename(value);return
        if key=='program' and self.get('program') and self.get('program')!=value:
            self.snapshot('Before changing program media',force=True)
        with self.db:
            if key=='program' and self.get(key)!=value:
                self.db.execute("DELETE FROM info WHERE key IN ('edit_history','undo_trim','undo_merge','cue_matches')")
            self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',(key,json.dumps(value)))
    @property
    def settings(self):return resolved_settings(DEFAULTS,self.get('settings',{}))
    def tracks(self):
        rows=[dict(r)|{'metadata':json.loads(r['metadata'])} for r in self.db.execute('SELECT * FROM tracks ORDER BY path')]
        if self.get('portable_paths',False):
            for row in rows:row['path']=str((self.path.parent/row['path']).resolve())
        return rows
    def track(self,tid):
        row=self.db.execute('SELECT * FROM tracks WHERE id=?',(tid,)).fetchone()
        if row is None:return None
        result=dict(row);result['metadata']=json.loads(result['metadata'])
        if self.get('portable_paths',False):result['path']=str((self.path.parent/result['path']).resolve())
        return result
    def snapshot(self,reason,force=False):
        from .workflow import create_snapshot
        try:return create_snapshot(self,reason,force)
        except (OSError,sqlite3.Error) as exc:
            raise ValueError('Recovery snapshot could not be saved; the edit was not applied. '+str(exc)) from exc
    def cues(self):return [dict(r) for r in self.db.execute('SELECT * FROM cues ORDER BY start,end')]
    def excluded_cue_ids(self):return set(self.get('excluded_cues',[]))
    def _edit_state(self):return {'cues':self.cues(),'excluded':sorted(self.excluded_cue_ids())}
    def edit_history(self):
        history=self.get('edit_history',{'undo':[],'redo':[]})
        expected=history['undo'][-1]['after'] if history['undo'] else (history['redo'][-1]['before'] if history['redo'] else None)
        if expected is not None and expected!=self._edit_state():return {'undo':[],'redo':[]}
        return history
    def _history_key(self):return self.db.total_changes,self.db.execute('PRAGMA data_version').fetchone()[0]
    def _cache_history_summary(self,history):
        summary={side:(history[side][-1]['label'] if history[side] else None) for side in ('undo','redo')}
        expected=history['undo'][-1]['after'] if history['undo'] else (history['redo'][-1]['before'] if history['redo'] else None)
        self._history_summary_cache=(self._history_key(),summary,expected)
        return summary
    def history_summary(self):
        cached=self._history_summary_cache
        if cached and cached[0]==self._history_key() and (cached[2] is None or cached[2]==self._edit_state()):return dict(cached[1])
        return dict(self._cache_history_summary(self.edit_history()))
    def _record_edit(self,label,before,matches_before=None,versions_before=None):
        """Called inside the same transaction as the edit; navigation isn't history."""
        after=self._edit_state()
        if before==after and (matches_before is None or matches_before==self.get('cue_matches',{})) and (versions_before is None or versions_before==self.get('version_reviews',{})):return
        history=self.get('edit_history',{'undo':[],'redo':[]})
        expected=history['undo'][-1]['after'] if history['undo'] else (history['redo'][-1]['before'] if history['redo'] else None)
        if expected is not None and expected!=before:history={'undo':[],'redo':[]}
        entry={'label':label,'before':before,'after':after}
        if matches_before is not None:entry.update(matches_before=matches_before,matches_after=self.get('cue_matches',{}))
        if versions_before is not None:entry.update(versions_before=versions_before,versions_after=self.get('version_reviews',{}))
        history={'undo':(history['undo']+[entry])[-50:],'redo':[]}
        self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('edit_history',json.dumps(history,separators=(',',':'))))
        self._cache_history_summary(history)
    def _restore_edit(self,state):
        self._write_cues(state['cues'])
        self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('excluded_cues',json.dumps(state['excluded'])))
        self.db.execute("DELETE FROM info WHERE key IN ('undo_trim','undo_merge')")
    def undo_edit(self):
        history=self.edit_history()
        if not history['undo']:raise ValueError('There is no cue edit to undo.')
        entry=history['undo'].pop()
        with self.db:
            self._restore_edit(entry['before']);history['redo'].append(entry)
            if 'matches_before' in entry:self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('cue_matches',json.dumps(entry['matches_before'])))
            if 'versions_before' in entry:self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('version_reviews',json.dumps(entry['versions_before'])))
            self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('edit_history',json.dumps(history,separators=(',',':'))))
        self._cache_history_summary(history)
        return entry['label']
    def redo_edit(self):
        history=self.edit_history()
        if not history['redo']:raise ValueError('There is no cue edit to redo.')
        entry=history['redo'].pop()
        with self.db:
            self._restore_edit(entry['after']);history['undo'].append(entry)
            if 'matches_after' in entry:self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('cue_matches',json.dumps(entry['matches_after'])))
            if 'versions_after' in entry:self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('version_reviews',json.dumps(entry['versions_after'])))
            self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('edit_history',json.dumps(history,separators=(',',':'))))
        self._cache_history_summary(history)
        return entry['label']
    def trim_cue(self,cue_id,start,end,adjust_unknown=False):
        import math
        state=self._edit_state();before=state['cues'];item=next((c for c in before if c['id']==cue_id),None)
        duration=self.get('program',{}).get('duration',0)
        if item is None:raise ValueError('The cue no longer exists.')
        if not all(math.isfinite(v) for v in (start,end)) or not 0<=start<end<=duration:
            raise ValueError('Cue boundaries must stay inside the program with a positive duration.')
        excluded=self.excluded_cue_ids()
        after=trim_rows(before,cue_id,start,end,excluded,adjust_unknown)
        with self.db:
            self._write_cues(after)
            self.db.execute("DELETE FROM info WHERE key='undo_merge'")
            snapshot={'before':before,'after':self.cues(),'excluded':sorted(excluded)}
            self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('undo_trim',json.dumps(snapshot)))
            self._record_edit('Trim cue',state)
    def adjust_edit_point(self,left_id,right_id,position,side='roll'):
        """Adjust a touching pair, preserving both references and outer edges."""
        import math
        state=self._edit_state();before=state['cues'];ids=[c['id'] for c in before]
        if side not in ('A','B','roll'):raise ValueError('Choose A, B, or Roll for the edit point.')
        if left_id not in ids or right_id not in ids or ids.index(right_id)!=ids.index(left_id)+1:
            raise ValueError('Choose two adjoining cues to adjust their edit point.')
        left=before[ids.index(left_id)];right=before[ids.index(right_id)]
        if abs(left['end']-right['start'])>1e-8:
            raise ValueError('A shared edit requires cues whose boundaries touch.')
        if {left_id,right_id} & self.excluded_cue_ids():raise ValueError('Restore excluded cues before adjusting a shared edit.')
        if not math.isfinite(position) or not left['start']<position<right['end']:
            raise ValueError('The edit point must stay inside the two cues.')
        if side=='A':self.trim_cue(left_id,left['start'],position,adjust_unknown=False);return
        if side=='B':self.trim_cue(right_id,position,right['end'],adjust_unknown=False);return
        after=[dict(c) for c in before]
        after[ids.index(left_id)]['end']=position;after[ids.index(right_id)]['start']=position
        with self.db:
            self._write_cues(after)
            self.db.execute("DELETE FROM info WHERE key='undo_merge'")
            snapshot={'before':before,'after':self.cues(),'excluded':sorted(self.excluded_cue_ids())}
            self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('undo_trim',json.dumps(snapshot)))
            self._record_edit('Roll edit',state)
    def undo_trim(self):
        snapshot=self.get('undo_trim')
        if not snapshot:raise ValueError('There is no boundary edit to undo.')
        if self.cues()!=snapshot['after'] or sorted(self.excluded_cue_ids())!=snapshot['excluded']:
            raise ValueError('Cues changed since the boundary edit; it can no longer be undone.')
        if self.edit_history()['undo']:return self.undo_edit()
        with self.db:
            self._write_cues(snapshot['before'])
            self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('excluded_cues',json.dumps(snapshot['excluded'])))
            self.db.execute("DELETE FROM info WHERE key IN ('undo_trim','undo_merge')")
    def included_cues(self):
        excluded=self.excluded_cue_ids()
        return [c for c in self.cues() if c['id'] not in excluded]
    def split_cue(self,cue_id,position):
        import math
        rows=self.cues();item=next((c for c in rows if c['id']==cue_id),None)
        if item is None:raise ValueError('The cue no longer exists.')
        if not math.isfinite(position) or not item['start']<position<item['end']:
            raise ValueError('Place the playhead inside the selected cue to split it.')
        right=item|{'id':uuid.uuid4().hex,'start':position}
        after=[c if c['id']!=cue_id else c|{'end':position} for c in rows]+[right]
        hidden=self.excluded_cue_ids();matches=self.get('cue_matches',{});matches_before=dict(matches)
        versions=self.get('version_reviews',{});versions_before=dict(versions)
        with self.db:
            before=self._edit_state();self._write_cues(after)
            if cue_id in hidden:hidden.add(right['id'])
            self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('excluded_cues',json.dumps(sorted(hidden))))
            if cue_id in matches:
                matches[right['id']]=dict(matches[cue_id])
                self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('cue_matches',json.dumps(matches)))
            if cue_id in versions:
                versions[right['id']]=versions[cue_id]
                self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('version_reviews',json.dumps(versions)))
            self.db.execute("DELETE FROM info WHERE key IN ('undo_trim','undo_merge')")
            self._record_edit('Split cue',before,matches_before,versions_before)
        return right
    def set_cues_excluded(self,ids,excluded=True):
        before=self._edit_state()
        ids=set(ids);existing={c['id'] for c in self.cues()}
        if not ids or not ids<=existing:raise ValueError('Select existing cues to exclude or restore.')
        hidden=self.excluded_cue_ids()
        hidden=hidden|ids if excluded else hidden-ids
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('excluded_cues',json.dumps(sorted(hidden))))
            self.db.execute("DELETE FROM info WHERE key='undo_trim'")
            self.db.execute("DELETE FROM info WHERE key='undo_merge'")
            self._record_edit('Exclude cues' if excluded else 'Restore cues',before)
    def _write_cues(self,cues):
        cues=list(cues)
        if len({c['id'] for c in cues})!=len(cues):raise ValueError('Cue IDs must be unique.')
        previous={c['id']:c for c in self.cues()}
        ids={c['id'] for c in cues}
        self.db.executemany('DELETE FROM cues WHERE id=?',((cid,) for cid in previous.keys()-ids))
        self.db.executemany('''INSERT INTO cues VALUES(:id,:track,:start,:end,:confidence,:status,:note,:title)
            ON CONFLICT(id) DO UPDATE SET track=excluded.track,start=excluded.start,end=excluded.end,
            confidence=excluded.confidence,status=excluded.status,note=excluded.note,title=excluded.title''',
            (c for c in cues if previous.get(c['id'])!=c))
    def save_cues(self,cues,maintain_coverage=False,label='Edit cues',version_reviews=None):
        from .coverage import ensure_coverage
        before=self._edit_state();cues=list(cues)
        versions_before=self.get('version_reviews',{}) if version_reviews is not None else None
        duration=self.get('program',{}).get('duration')
        if duration and maintain_coverage:cues=ensure_coverage(cues,duration)
        # Cue changes and their undo states commit together. Copying the full
        # fingerprint database here blocks even tiny edits in large projects.
        with self.db:
            self._write_cues(cues)
            self.db.execute("DELETE FROM info WHERE key='undo_trim'")
            hidden=self.excluded_cue_ids() & {c['id'] for c in cues}
            self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('excluded_cues',json.dumps(sorted(hidden))))
            self.db.execute("DELETE FROM info WHERE key='undo_merge'")
            if version_reviews is not None:self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('version_reviews',json.dumps(version_reviews)))
            self._record_edit(label,before,versions_before=versions_before)
    def merge_selection(self,selected_ids):
        before=self.cues();selected_ids=set(selected_ids)
        indices=[i for i,c in enumerate(before) if c['id'] in selected_ids]
        if len(selected_ids)<2 or len(indices)!=len(selected_ids):
            raise ValueError('Select at least two existing cues to merge.')
        if selected_ids & self.excluded_cue_ids():raise ValueError('Restore excluded cues before merging them.')
        if indices!=list(range(indices[0],indices[-1]+1)):
            raise ValueError('Select adjoining cues in the full cue sheet. Clear filters to include any hidden cues between them.')
        return [before[i] for i in indices]
    def merge_cues(self,selected_ids,track=None,title='',reviewed=False,note=''):
        state=self._edit_state()
        selected=self.merge_selection(selected_ids)
        if track and not reviewed:raise ValueError('Confirm the chosen reference before merging identified cues.')
        reference=self.track(track) if track is not None else None
        if track is not None and reference is None:raise ValueError('The chosen reference is no longer in this project.')
        start=min(c['start'] for c in selected);end=max(c['end'] for c in selected)
        title=reference['metadata']['title'] if reference else (title.strip() or 'Unknown (merged)')
        source_notes=list(dict.fromkeys(c['note'] for c in selected if c['note']))
        detail='Manually merged '+str(len(selected))+' adjoining cues. Evidence score reset; assignment confirmed by user.' if track else 'Manually merged unknown interval.'
        notes='\n'.join(filter(None,[detail,*source_notes,note]))
        merged=cue(track,start,end,0,title,'Reviewed' if track else 'Unknown',notes)
        ids={c['id'] for c in selected};before=self.cues()
        after=[c for c in before if c['id'] not in ids]+[merged]
        after=sorted(after,key=lambda c:(c['start'],c['end']))
        with self.db:
            self._write_cues(after)
            self.db.execute("DELETE FROM info WHERE key='undo_trim'")
            self.db.execute('INSERT OR REPLACE INTO info VALUES(?,?)',('undo_merge',json.dumps({'before':before,'after':after})))
            self._record_edit('Merge cues',state)
        return merged
    def undo_merge(self):
        snapshot=self.get('undo_merge')
        if not snapshot:raise ValueError('There is no merge to undo.')
        if self.cues()!=snapshot['after']:raise ValueError('Cues changed since the merge; restore a backup instead.')
        if self.edit_history()['undo']:return self.undo_edit()
        with self.db:
            self._write_cues(snapshot['before'])
            self.db.execute("DELETE FROM info WHERE key='undo_merge'")

    def save_track(self,path,duration,metadata,hashes):
        path=Path(path).resolve();stat=path.stat()
        old=self.db.execute('SELECT id FROM tracks WHERE path=?',(str(path),)).fetchone()
        if old is None and self.get('portable_paths',False):
            match=next((t for t in self.tracks() if Path(t['path'])==path),None)
            if match:old=(match['id'],)
        if old:self.snapshot('Before reindexing a reference',force=True)
        elif self.db.execute('SELECT 1 FROM tracks LIMIT 1').fetchone():self.snapshot('Before importing references')
        tid=old[0] if old else uuid.uuid4().hex
        with self.db:
            self.db.execute('DELETE FROM hashes WHERE track=?',(tid,))
            self.db.execute('INSERT INTO tracks VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET size=excluded.size,mtime=excluded.mtime,duration=excluded.duration,metadata=excluded.metadata',
                (tid,str(path),stat.st_size,stat.st_mtime_ns,duration,json.dumps(metadata)))
            self.db.executemany('INSERT INTO hashes VALUES(?,?,?)',((int(h),tid,int(t)) for h,t in hashes))
        return tid
    def update_metadata(self,tid,metadata):
        self.snapshot('Before changing reference metadata')
        with self.db:self.db.execute('UPDATE tracks SET metadata=? WHERE id=?',(json.dumps(metadata),tid))
    def remove_track(self,tid):
        self.snapshot('Before removing a reference',force=True)
        with self.db:
            self.db.execute("DELETE FROM info WHERE key IN ('edit_history','undo_trim','undo_merge')")
            self.db.execute("UPDATE cues SET status='Unknown',title='Unknown (reference removed)',confidence=0 WHERE track=?",(tid,))
            self.db.execute('DELETE FROM tracks WHERE id=?',(tid,))
    def relink_reference(self,tid,path):
        from .audio import content_hash
        track=next((t for t in self.tracks() if t['id']==tid),None)
        if track is None:raise ValueError('The reference no longer exists.')
        path=Path(path).resolve();stat=path.stat();checksum=track['metadata'].get('_content_sha256')
        if stat.st_size!=track['size'] or (checksum and content_hash(path)!=checksum):
            raise ValueError('This file differs from the original reference. Import it as a new reference to build correct fingerprints.')
        if not checksum:
            # Legacy projects have only file size, so verify their stored landmarks too.
            from .engine import fingerprints
            from .audio import decode
            stored=set(tuple(row) for row in self.db.execute('SELECT hash,frame FROM hashes WHERE track=?',(tid,)))
            if not stored or stored!=set(fingerprints(decode(path))):
                raise ValueError('The original reference cannot be verified. Import this file as a new reference instead.')
        with self.db:self.db.execute('UPDATE tracks SET path=?,mtime=? WHERE id=?',(str(path),stat.st_mtime_ns,tid))
    def backup(self,path):
        if Path(path).resolve()==self.path:raise ValueError('Choose a different backup path.')
        target=sqlite3.connect(path)
        try:self.db.backup(target)
        finally:target.close()

def cue(track,start,end,confidence=0,title='',status=None,note=''):
    return dict(id=uuid.uuid4().hex,track=track,start=float(start),end=float(end),confidence=float(confidence),
                title=title,status=status or ('Needs review' if track else 'Unknown'),note=note)
