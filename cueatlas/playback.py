"""Audible reverse transport using bounded, disposable PCM chunks.

QMediaPlayer only plays forward. Reversing a short decoded window keeps memory
bounded and gives its position clock an exact mapping back to source time.
"""
import tempfile
import uuid
from pathlib import Path
import numpy as np
from scipy.io.wavfile import write
from PySide6.QtCore import QObject,QThread,Signal,QUrl
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
from .audio import decode,Cancelled
PREVIEW_SR=44100


class ReverseWorker(QThread):
    ready=Signal(object);failed=Signal(int,str)
    def __init__(self,source,end,directory,generation,parent=None):
        super().__init__(parent);self.source=source;self.end=end;self.start_time=max(0,end-30)
        self.directory=directory;self.generation=generation
    def run(self):
        path=Path(self.directory)/(uuid.uuid4().hex+'.wav')
        try:
            samples=decode(self.source,start=self.start_time,duration=self.end-self.start_time,cancel=self.isInterruptionRequested,sample_rate=PREVIEW_SR)
            if self.isInterruptionRequested():return
            write(path,PREVIEW_SR,(np.clip(samples[::-1],-1,1)*32767).astype('<i2'))
            if self.isInterruptionRequested():path.unlink(missing_ok=True);return
            # The actual decoded length defines the source-time mapping.
            self.ready.emit({'generation':self.generation,'path':path,'start':self.start_time,'end':self.start_time+len(samples)/PREVIEW_SR})
        except Cancelled:path.unlink(missing_ok=True)
        except Exception as exc:
            path.unlink(missing_ok=True);self.failed.emit(self.generation,str(exc))


class ReversePlayback(QObject):
    positionChanged=Signal(float);stateChanged=Signal();failed=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.player=QMediaPlayer(self);self.output=QAudioOutput(self)
        self.output.setVolume(.75);self.player.setAudioOutput(self.output)
        self.player.positionChanged.connect(self._position);self.player.mediaStatusChanged.connect(self._status)
        self.player.errorOccurred.connect(self._error)
        self.directory=tempfile.TemporaryDirectory(prefix='cueatlas-reverse-')
        self.workers=[];self.generation=0;self.active=False;self.loading=False;self.chunk=None;self.path=None;self.rate=1;self.position=0
    def start(self,path,position,rate=1):
        self.stop();self.path=path;self.position=max(0,position);self.rate=rate
        if self.position<=0:return
        self.active=True;self._load(self.position);self.stateChanged.emit()
    def _load(self,end):
        self.loading=True;worker=ReverseWorker(self.path,end,self.directory.name,self.generation,self)
        self.workers.append(worker);worker.ready.connect(self._ready);worker.failed.connect(self._failed)
        worker.finished.connect(lambda:self._finished(worker));worker.start()
    def _finished(self,worker):
        self.workers.remove(worker);worker.deleteLater()
    def _ready(self,chunk):
        if not self.active or chunk['generation']!=self.generation:
            chunk['path'].unlink(missing_ok=True);return
        old=self.chunk;self.chunk=None
        self.player.stop();self.player.setSource(QUrl.fromLocalFile(str(chunk['path'])))
        if old:old['path'].unlink(missing_ok=True)
        self.chunk=chunk;self.loading=False;self.player.setPlaybackRate(self.rate);self.player.play();self.stateChanged.emit()
    def _position(self,ms):
        if self.active and self.chunk and not self.loading:
            self.position=max(self.chunk['start'],self.chunk['end']-ms/1000)
            self.positionChanged.emit(self.position)
    def _status(self,status):
        if status==QMediaPlayer.EndOfMedia and self.active and self.chunk and not self.loading:
            start=self.chunk['start'];self.position=start;self.positionChanged.emit(start)
            if start<=0:self.stop()
            else:self._load(start)
    def _error(self,*args):
        if self.active:self._failed(self.generation,self.player.errorString())
    def _failed(self,generation,message):
        if self.active and generation==self.generation:self.stop();self.failed.emit(message)
    def stop(self):
        self.generation+=1;self.active=False;self.loading=False
        for worker in self.workers:worker.requestInterruption()
        self.player.stop();self.player.setSource(QUrl())
        if self.chunk:self.chunk['path'].unlink(missing_ok=True);self.chunk=None
        self.stateChanged.emit()
    def shutdown(self):
        self.stop()
        for worker in list(self.workers):worker.wait()
        self.directory.cleanup()
