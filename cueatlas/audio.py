import os
import subprocess
import re
import tempfile
from pathlib import Path
import numpy as np
import imageio_ffmpeg
SR=11025
VIDEO={'.mp4','.mov','.mxf'}
SUPPORTED={'.wav','.wave','.mp3','.aif','.aiff','.flac','.m4a','.mp4','.mov','.mxf'}
class Cancelled(Exception): pass

def ffmpeg():
    return imageio_ffmpeg.get_ffmpeg_exe()

def decode(path, start=None, duration=None, cancel=lambda:False, sample_rate=SR):
    args=[ffmpeg(),'-v','error','-nostdin']
    if start is not None: args+=['-ss',str(max(0,start))]
    video=Path(path).suffix.lower() in VIDEO
    if video:args+=['-copyts','-start_at_zero']
    args+=['-i',str(path)]
    if duration is not None: args+=['-t',str(duration)]
    args+=['-map','0:a:0','-vn']
    if video:args+=['-af',f'asetpts=PTS-{max(0,start or 0)}/TB,aresample={sample_rate}:async=1:first_pts=0']
    args+=['-ac','1','-ar',str(sample_rate),'-f','f32le','pipe:1']
    # Temporary file avoids pipe deadlock and lets cancellation terminate decoding.
    import tempfile
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        p=subprocess.Popen(args,stdout=out,stderr=err,creationflags=0x08000000 if os.name=='nt' else 0)
        try:
            while p.poll() is None:
                if cancel(): raise Cancelled()
                try: p.wait(timeout=.15)
                except subprocess.TimeoutExpired: pass
            if p.returncode:
                err.seek(0);message=err.read().decode(errors='replace')
                if 'matches no streams' in message:raise ValueError(f'No audio track found in {Path(path).name}. Choose a file with audio.')
                raise ValueError(message[-1800:] or 'Audio decoding failed.')
            out.seek(0); data=np.frombuffer(out.read(),dtype='<f4').copy()
        finally:
            if p.poll() is None: p.terminate();p.wait()
    if not len(data): raise ValueError(f'No audio found in {Path(path).name}.')
    return data

def waveform(audio,bins=1100):
    step=max(1,int(np.ceil(len(audio)/bins)))
    return [float(np.max(np.abs(audio[i:i+step]))) for i in range(0,len(audio),step)]


def content_hash(path,cancel=lambda:False):
    import hashlib
    digest=hashlib.sha256()
    with open(path,'rb') as file:
        while block:=file.read(1024*1024):
            if cancel():raise Cancelled()
            digest.update(block)
    return digest.hexdigest()


def video_audio_duration(path,cancel=lambda:False):
    """Measure the selected audio packet timeline, not the longer video track.

    Stream-copying packet timestamps requires no decoding or temporary media file.
    The same timestamp origin as decode() includes any leading audio offset.
    """
    with tempfile.TemporaryFile() as output,tempfile.TemporaryFile() as errors:
        process=subprocess.Popen([ffmpeg(),'-v','error','-nostdin','-copyts','-start_at_zero','-i',str(path),
            '-map','0:a:0','-vn','-c:a','copy','-f','framecrc','pipe:1'],
            stdout=output,stderr=errors,creationflags=0x08000000 if os.name=='nt' else 0)
        try:
            while process.poll() is None:
                if cancel():raise Cancelled()
                try:process.wait(timeout=.15)
                except subprocess.TimeoutExpired:pass
        finally:
            if process.poll() is None:process.kill();process.wait()
        if process.returncode:
            errors.seek(0);message=errors.read().decode(errors='replace')
            if 'matches no streams' in message:raise ValueError(f'No audio track found in {Path(path).name}. Choose a file with audio.')
            raise ValueError(message[-1800:] or 'Unable to read the video audio track.')
        output.seek(0);time_base=None;end=None
        for line in output:
            if cancel():raise Cancelled()
            if line.startswith(b'#tb'):
                match=re.search(rb'(\d+)/(\d+)',line)
                if match:time_base=int(match[1])/int(match[2])
            elif not line.startswith(b'#'):
                fields=line.split(b',')
                if len(fields)>=4:
                    value=int(fields[2])+int(fields[3]);end=value if end is None else max(end,value)
        return max(0,end*time_base) if end is not None and time_base else None


def source_duration(path,cancel=lambda:False):
    """Probe the source/container duration independently of decoded PCM length.

    FFmpeg's probe exits nonzero because no output is requested; its header is
    still useful. WAV data sizes provide an additional sample-accurate check.
    """
    if cancel():raise Cancelled()
    if Path(path).suffix.lower() in VIDEO:return video_audio_duration(path,cancel)
    process=subprocess.Popen([ffmpeg(),'-hide_banner','-nostdin','-i',str(path)],
        stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
        creationflags=0x08000000 if os.name=='nt' else 0)
    try:
        while True:
            if cancel():raise Cancelled()
            try:
                _,stderr=process.communicate(timeout=.15);break
            except subprocess.TimeoutExpired:pass
    finally:
        if process.poll() is None:process.kill();process.communicate()
    match=re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)',stderr.decode(errors='replace'))
    reported=sum(float(v)*scale for v,scale in zip(match.groups(),(3600,60,1))) if match else None
    if Path(path).suffix.lower() in {'.wav','.wave'}:
        import struct
        try:
            with open(path,'rb') as file:
                header=file.read(12);rate=None;align=None;data_size=None;rf64_size=None
                if header[:4] in {b'RIFF',b'RF64'} and header[8:]==b'WAVE':
                    while True:
                        block=file.read(8)
                        if len(block)!=8:break
                        key,size=struct.unpack('<4sI',block)
                        if key==b'ds64':
                            data=file.read(min(size,28))
                            if len(data)>=16:rf64_size=struct.unpack_from('<Q',data,8)[0]
                            file.seek(size-len(data)+(size%2),1)
                        elif key==b'fmt ':
                            data=file.read(min(size,40))
                            if len(data)>=16:
                                rate=struct.unpack_from('<I',data,4)[0];align=struct.unpack_from('<H',data,12)[0]
                                encoding=struct.unpack_from('<H',data,0)[0]
                                if encoding==65534 and len(data)>=26:encoding=struct.unpack_from('<H',data,24)[0]
                            else:encoding=0
                            file.seek(size-len(data)+(size%2),1)
                        elif key==b'data':
                            data_size=rf64_size if size==0xffffffff and rf64_size is not None else size
                            break
                        else:file.seek(size+(size%2),1)
                    if rate and align and data_size and encoding in {1,3}:
                        return data_size/(rate*align)
        except (OSError,ValueError,struct.error):pass
    return reported


def decode_program(path,cancel=lambda:False):
    """Reject suspiciously short decodes rather than saving incomplete results."""
    expected=source_duration(path,cancel)
    samples=decode(path,cancel=cancel)
    actual=len(samples)/SR
    if cancel():raise Cancelled()
    # Container/MP3 headers can round or include encoder padding. A quarter
    # second accommodates this, but never silently accepts a truncated source.
    if expected is not None and expected-actual>.25:
        raise ValueError(
            f'Incomplete audio decode: source reports {expected:.3f} seconds, '
            f'but only {actual:.3f} seconds decoded. Previous cues were preserved. '
            'Re-export the entire source as PCM WAV and try again.')
    return samples,actual,expected
