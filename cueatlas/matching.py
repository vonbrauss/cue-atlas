"""Named detection thresholds; evidence is not a calibrated probability."""
PRESETS={
    'Conservative':{'min_votes':24,'min_cue':3.0,'gap':.5,'min_support':14},
    'Balanced':{'min_votes':12,'min_cue':2.0,'gap':1.0,'min_support':8},
    'Sensitive':{'min_votes':8,'min_cue':.75,'gap':.65,'min_support':6},
}
MATCH_KEYS=tuple(PRESETS['Conservative'])


def resolved_settings(defaults,saved):
    result=defaults|saved
    if 'sensitivity_preset' not in saved:
        # Untouched legacy defaults adopt the new default. Preserve manual tuning.
        legacy=PRESETS['Balanced']
        if saved.get('silence_db')==-55:result['silence_db']=defaults['silence_db']
        if all(saved.get(key,legacy[key])==legacy[key] for key in ('min_votes','min_cue','gap')):
            result.update(PRESETS['Conservative'],sensitivity_preset='Conservative')
        else:result.update(sensitivity_preset='Custom',min_support=saved.get('min_support',8))
    name=result.get('sensitivity_preset')
    if name not in PRESETS and name!='Custom':result['sensitivity_preset']='Custom'
    if name in PRESETS and any(result[key]!=PRESETS[name][key] for key in MATCH_KEYS):result['sensitivity_preset']='Custom'
    return result
