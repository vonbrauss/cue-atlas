import time,threading
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from cueatlas.gui import CueDialog
from cueatlas.audio import Cancelled,decode
from cueatlas import comparison_audio
from test_timeline import open_window


def wait_until(predicate):
    deadline=time.monotonic()+5
    while not predicate() and time.monotonic()<deadline:QTest.qWait(10)
    assert predicate()


def test_opening_review_does_not_load_original_media_and_preparation_is_background(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);d=CueDialog(rows[1],w.p.tracks(),12,w);c=d.comparison
    assert c.program_player.source().isEmpty() and c.reference_player.source().isEmpty()
    calls=[];main=threading.get_ident();ticks=[]
    def slow_decode(*args,**kwargs):
        calls.append((threading.get_ident(),kwargs['start'],kwargs['duration']))
        for i in range(15):
            if kwargs['cancel']():raise Cancelled()
            time.sleep(.01)
        return decode(*args,**kwargs)
    monkeypatch.setattr(comparison_audio,'decode',slow_decode)
    timer=QTimer();timer.timeout.connect(lambda:ticks.append(1));timer.start(10)
    c.play_program();assert c.loading=='program'
    wait_until(lambda:c.loading is None)
    assert len(ticks)>=5 and calls==[(calls[0][0],2,4)] and calls[0][0]!=main
    assert c.program_player.source().toLocalFile()!=w.p.get('program')['path']
    from scipy.io.wavfile import read
    sr,audio=read(c.program_player.source().toLocalFile());assert sr==48000 and len(audio)==4*48000
    c.stop();c.play_program();assert len(calls)==1  # Cached local interval, no second decode.
    c.stop();timer.stop();d.reject();w.close();app.processEvents()


def test_close_during_preparation_never_waits_or_starts_late_audio(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);d=CueDialog(rows[1],w.p.tracks(),12,w);c=d.comparison
    started=threading.Event()
    def slow(*args,**kwargs):
        started.set()
        while not kwargs['cancel']():time.sleep(.01)
        raise Cancelled()
    monkeypatch.setattr(comparison_audio,'decode',slow)
    c.play_reference();wait_until(started.is_set)
    began=time.monotonic();d.reject();assert time.monotonic()-began<.2
    wait_until(lambda:not c.audio.jobs)
    assert c.reference_player.source().isEmpty() and not Path(c.audio.directory.name).exists()
    w.close();app.processEvents()


def test_failed_audio_keeps_dialog_and_save_available(tmp_path,monkeypatch):
    app,w,rows=open_window(tmp_path);d=CueDialog(rows[1],w.p.tracks(),12,w);c=d.comparison
    monkeypatch.setattr(comparison_audio,'decode',lambda *a,**k:(_ for _ in ()).throw(ValueError('Drive unavailable')))
    c.play_reference();wait_until(lambda:c.loading is None)
    assert 'Drive unavailable' in c.media_state.text()
    d.accept();assert d.result() and d.c==rows[1]
    wait_until(lambda:not c.audio.jobs);w.close();app.processEvents()


def test_preparation_timeout_reports_failure(tmp_path,monkeypatch):
    from types import SimpleNamespace
    source=tmp_path/'source.wav';source.write_bytes(b'test');clock=iter([0,31])
    monkeypatch.setattr(comparison_audio,'time',SimpleNamespace(monotonic=lambda:next(clock)))
    def timeout(*args,**kwargs):
        assert kwargs['cancel']();raise Cancelled()
    monkeypatch.setattr(comparison_audio,'decode',timeout)
    job=comparison_audio.PrepareAudio(str(source),0,1,str(tmp_path),2,'program');errors=[]
    job.failed.connect(lambda generation,message:errors.append(message));job.run()
    assert len(errors)==1 and 'timed out' in errors[0]
