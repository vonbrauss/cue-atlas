"""Isolated inference process. Never opens a project database or source recording."""
import gc,json,os,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'vendor'))
import numpy as np
import soundfile as sf
import torch
from bandit_v2.bandit import Bandit


def main():
    request=json.loads(Path(sys.argv[1]).read_text());root=Path(__file__).parent
    torch.set_num_threads(min(4,os.cpu_count() or 1))
    model=Bandit(**json.loads((root/'config.json').read_text())).eval()
    checkpoint=torch.load(request['checkpoint'],map_location='cpu',weights_only=True)
    model.load_state_dict({k.removeprefix('model.'):v for k,v in checkpoint['state_dict'].items() if k.startswith('model.')},strict=True)
    del checkpoint;gc.collect()
    device='mps' if torch.backends.mps.is_available() else 'cpu';model.tf_model.to(device)
    print(json.dumps({'type':'ready','device':device}),flush=True)
    with torch.inference_mode():
        for job in request['jobs']:
            started=time.perf_counter()
            try:
                audio,rate=sf.read(job['input'],dtype='float32')
                if rate!=48000 or audio.ndim!=1 or not len(audio):raise ValueError('Invalid AI input audio')
                pad=rate*4;chunk=rate*8;hop=rate*4
                samples=np.pad(audio,(pad,pad+chunk),mode='reflect')
                result=np.zeros_like(samples);weight=np.zeros_like(samples);window=np.hanning(chunk).astype(np.float32)
                for start in range(0,len(audio)+pad,hop):
                    batch=torch.from_numpy(samples[start:start+chunk].copy()).reshape(1,1,-1)
                    spectrum=model.stft(batch);z=model.band_split(spectrum)
                    q=model.tf_model(z.to(device)).cpu();mask=model.mask_estim['music'](q)
                    music=model.istft(spectrum*mask.to(spectrum.dtype),batch.shape[-1]).reshape(-1).numpy()
                    result[start:start+chunk]+=music*window;weight[start:start+chunk]+=window
                    print(json.dumps({'type':'progress','id':job['id'],'fraction':min(1,(start+hop)/(len(audio)+pad))}),flush=True)
                music=result[pad:pad+len(audio)]/np.maximum(weight[pad:pad+len(audio)],1e-8)
                if not np.isfinite(music).all():raise ValueError('AI output contained invalid audio')
                target=Path(job['output']);temporary=target.with_suffix('.partial.wav')
                sf.write(temporary,music,rate,subtype='FLOAT');os.replace(temporary,target)
                print(json.dumps({'type':'done','id':job['id'],'seconds':time.perf_counter()-started,'device':device}),flush=True)
            except Exception as exc:
                print(json.dumps({'type':'error','id':job['id'],'message':str(exc)}),flush=True)


if __name__=='__main__':main()
