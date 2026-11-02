"""Cue coverage and audio-activity gates, independent of reference matching."""
import math
import numpy as np
from .audio import SR
from .project import cue
EPSILON = 1e-8

def coverage_spans(cues, duration):
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Program duration must be a positive finite number.')
    spans=[]
    for item in sorted(cues,key=lambda c:c['start']):
        start,end=float(item['start']),float(item['end'])
        if not math.isfinite(start) or not math.isfinite(end) or start<0 or end>duration+EPSILON or end<=start:
            raise ValueError('A cue lies outside the program or has invalid timing. Review its in/out before saving.')
        end=min(duration,end)
        if spans and start<=spans[-1][1]+EPSILON:spans[-1][1]=max(spans[-1][1],end)
        else:spans.append([start,end])
    return spans

def covered_seconds(cues,duration):
    return sum(end-start for start,end in coverage_spans(cues,duration))

def audible_spans(audio,duration,silence_db=-65,min_silence=.35):
    """Locate audible activity in 50-ms windows with bounded scratch memory.

    Short pauses stay inside a region. Long silence is empty; 50 ms of padding
    protects fades and transients. A peak guard retains brief quiet attacks.
    """
    step=max(1,round(SR*.05));rms_limit=10**(silence_db/20);peak_limit=rms_limit*2
    active=[]
    for first in range(0,len(audio),step*2048):
        block=np.asarray(audio[first:first+step*2048]);indices=np.arange(0,len(block),step)
        counts=np.minimum(step,len(block)-indices)
        rms=np.sqrt(np.add.reduceat(np.square(block,dtype=np.float64),indices)/counts)
        peaks=np.maximum.reduceat(np.abs(block),indices)
        active.extend(((rms>rms_limit)|(peaks>peak_limit)).tolist())
    indices=np.flatnonzero(active)
    if not len(indices):return []
    spans=[]
    for group in np.split(indices,np.where(np.diff(indices)*step/SR>min_silence)[0]+1):
        start=max(0,group[0]*step/SR-.05);end=min(duration,(group[-1]+1)*step/SR+.05)
        if end<=start:continue
        if spans and start<=spans[-1][1]:spans[-1][1]=max(spans[-1][1],end)
        else:spans.append([start,end])
    return spans


def trim_automatic_cues(cues,activity,min_duration):
    """Only analysis-generated rows are trimmed; reviewed rows are never passed."""
    import uuid
    result=[]
    for c in cues:
        first=True
        for start,end in activity:
            if end<=c['start']:continue
            if start>=c['end']:break
            a=max(start,c['start']);b=min(end,c['end'])
            if b-a<min_duration:continue
            result.append(c|{'id':c['id'] if first else uuid.uuid4().hex,'start':a,'end':b});first=False
    return result


def ensure_coverage(cues,duration,audio=None,silence_db=-65,activity=None):
    """Preserve existing cues and fill audible unmatched time, skipping silence.

    Without audio (legacy/manual coverage tools), the whole interval is eligible.
    """
    result=[dict(c) for c in cues];spans=coverage_spans(result,duration)
    if activity is None:activity=audible_spans(audio,duration,silence_db) if audio is not None else [(0,duration)]
    existing_titles={c['title'] for c in result};number=0;cursor=0;index=0
    for start,end in spans+[[duration,duration]]:
        if start-cursor>EPSILON:
            while index<len(activity) and activity[index][1]<=cursor:index+=1
            for active_index in range(index,len(activity)):
                a,b=activity[active_index]
                if a>=start:break
                a=max(a,cursor);b=min(b,start)
                if b-a<=EPSILON or (audio is not None and b-a<.25):continue
                while True:
                    number+=1;title=f'Unknown {number:03}'
                    if title not in existing_titles:break
                result.append(cue(None,a,b,title=title,note='Audible unmatched interval; review music assignment.'))
        cursor=max(cursor,end)
    return sorted(result,key=lambda c:(c['start'],c['end']))
