"""BandIt v2 pilot inference. Run with the isolated AI Python, not the app venv."""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--device',choices=['auto','cpu'],default='auto')
    args=parser.parse_args()
    sys.path.insert(0,str(args.source.resolve()))
    import numpy as np
    import soundfile as sf
    import torch
    import yaml
    from models.bandit_v2.bandit import Bandit
    torch.set_num_threads(min(4,os.cpu_count() or 1))
    with args.checkpoint.open('rb') as f:digest=hashlib.file_digest(f,'md5').hexdigest()
    if digest!='fea2868787551b0cff36cfcf7c3622a3':raise ValueError('Checkpoint checksum does not match official multilingual release.')
    config=yaml.load(args.config.read_text(),Loader=yaml.FullLoader)
    rate=48000
    model=Bandit(**(config['kwargs']|{'fs':rate})).eval()
    checkpoint=torch.load(args.checkpoint,map_location='cpu',weights_only=True)
    weights={k.removeprefix('model.'):v for k,v in checkpoint['state_dict'].items() if k.startswith('model.')}
    model.load_state_dict(weights,strict=True)
    del checkpoint,weights;gc.collect()
    device='mps' if args.device=='auto' and torch.backends.mps.is_available() else 'cpu'
    # Keep complex spectral operations on CPU. Only the recurrent backbone
    # moves to Apple GPU; no unsupported-complex fallback changes the model.
    def music_tensor(audio):
        spectrum=model.stft(audio)
        z=model.band_split(spectrum)
        q=model.tf_model(z.to(device)).cpu()
        mask=model.mask_estim['music'](q)
        return model.istft(spectrum*mask.to(spectrum.dtype),audio.shape[-1])
    manifest=json.loads((args.output/'manifest.json').read_text())
    first=np.array(sf.read(args.output/'original'/f"{manifest['samples'][0]['id']}.wav",dtype='float32')[0][:rate//2],copy=True)
    with torch.inference_mode():
        sample=torch.from_numpy(first).reshape(1,1,-1)
        if device=='mps':
            # Validate the hybrid execution against CPU before measuring clips.
            device='cpu';reference=music_tensor(sample);device='mps'
            model.tf_model.to(device)
            actual=music_tensor(sample)
            error=float((actual-reference).abs().max())
            tolerance=max(1e-5,float(reference.abs().max())*.005)
            if error>tolerance:raise ValueError(f'GPU parity check failed: {error} > {tolerance}')
            print(json.dumps({'device':device,'gpu_parity_max_error':error}),flush=True)
        else:print(json.dumps({'device':device}),flush=True)
        logs=[]
        for sample in manifest['samples']:
            target=args.output/'music'/f"{sample['id']}.wav"
            if target.exists():continue
            waveform,sr=sf.read(args.output/'original'/f"{sample['id']}.wav",dtype='float32')
            if sr!=rate or waveform.ndim!=1:raise ValueError('Expected mono 48 kHz pilot excerpt.')
            started=time.perf_counter();pad=rate*4;chunk=rate*8;hop=rate*4
            audio=np.pad(waveform,(pad,pad+chunk),mode='reflect')
            result=np.zeros_like(audio);count=np.zeros_like(audio)
            window=np.hanning(chunk).astype(np.float32)
            for start in range(0,len(waveform)+pad,hop):
                batch=torch.from_numpy(audio[start:start+chunk].copy()).reshape(1,1,-1)
                separated=music_tensor(batch).reshape(-1).numpy()
                result[start:start+chunk]+=separated*window
                count[start:start+chunk]+=window
            music=result[pad:pad+len(waveform)]/np.maximum(count[pad:pad+len(waveform)],1e-8)
            if not np.isfinite(music).all():raise ValueError('Separation produced invalid samples.')
            sf.write(target,music,rate,subtype='FLOAT')
            log={'id':sample['id'],'seconds':time.perf_counter()-started,'duration':len(waveform)/rate,'device':device,
                 'peak_process_memory_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
            logs.append(log);print(json.dumps(log),flush=True)
            (args.output/'separation_metrics.json').write_text(json.dumps(logs,indent=2))


if __name__=='__main__':main()
