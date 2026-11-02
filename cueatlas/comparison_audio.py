"""Prepare bounded local review audio without opening source media on the UI thread."""
import tempfile,time,uuid
from pathlib import Path
from scipy.io.wavfile import write
from PySide6.QtCore import QObject,QThread,Signal
from .audio import decode,Cancelled

# Keep cancelled jobs alive if their dialog closes before FFmpeg has stopped.
_JOBS=set()

class PrepareAudio(QThread):
    ready=Signal(object);failed=Signal(int,str)
    def __init__(self,path,start,duration,directory,generation,kind,expected=None):
        super().__init__();self.path=path;self.start_time=start;self.duration=duration
        self.directory=directory;self.generation=generation;self.kind=kind;self.expected=expected
    def run(self):
        target=Path(self.directory)/(uuid.uuid4().hex+'.wav');began=time.monotonic()
        def cancelled():return self.isInterruptionRequested() or time.monotonic()-began>30
        try:
            # Even external-drive existence checks belong in this worker.
            if not Path(self.path).is_file():raise ValueError('Source recording is unavailable. Reconnect it or make it available offline.')
            if self.expected and 'size' in self.expected:
                stat=Path(self.path).stat()
                if (stat.st_size,stat.st_mtime_ns)!=(self.expected['size'],self.expected.get('mtime')):raise ValueError('Source recording changed. Reconnect or reimport the correct recording before comparing.')
            samples=decode(self.path,start=self.start_time,duration=self.duration,cancel=cancelled,sample_rate=48000)
            if cancelled():raise Cancelled()
            if not len(samples):raise ValueError('No audio could be read at this position.')
            write(target,48000,samples)
            if cancelled():target.unlink(missing_ok=True);raise Cancelled()
            self.ready.emit({'generation':self.generation,'kind':self.kind,'path':str(target),'duration':len(samples)/48000})
        except Cancelled:
            target.unlink(missing_ok=True)
            if not self.isInterruptionRequested():self.failed.emit(self.generation,'Audio preparation timed out. Check that the external drive is connected and the recording is available offline.')
        except Exception as exc:
            target.unlink(missing_ok=True);self.failed.emit(self.generation,str(exc))

class ReviewAudio(QObject):
    ready=Signal(object);failed=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.directory=tempfile.TemporaryDirectory(prefix='cueatlas-review-')
        self.generation=0;self.jobs=[];self.closed=False;self.cache={}
    def cancel(self):
        self.generation+=1
        for job in self.jobs:job.requestInterruption()
    def prepare(self,kind,path,start,duration,expected=None):
        self.cancel();key=(kind,path,start,duration)
        if key in self.cache and Path(self.cache[key]['path']).is_file():
            self.ready.emit(self.cache[key]|{'generation':self.generation});return
        job=PrepareAudio(path,start,duration,self.directory.name,self.generation,kind,expected)
        self.jobs.append(job);_JOBS.add(job)
        job.ready.connect(lambda result:self._ready(key,result));job.failed.connect(self._failed)
        directory=self.directory;jobs=self.jobs
        def finished():
            jobs.remove(job);_JOBS.discard(job);job.deleteLater()
            if self.closed and not jobs:directory.cleanup()
        job.finished.connect(finished);job.start()
    def _ready(self,key,result):
        if self.closed or result['generation']!=self.generation:Path(result['path']).unlink(missing_ok=True);return
        self.cache[key]=result;self.ready.emit(result)
    def _failed(self,generation,message):
        if not self.closed and generation==self.generation:self.failed.emit(message)
    def shutdown(self):
        self.closed=True;self.cancel()
        if not self.jobs:self.directory.cleanup()
