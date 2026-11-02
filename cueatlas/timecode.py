"""SMPTE display. Internal timings remain elapsed seconds; out is exclusive."""
import math
RATES = {'23.976': (24000/1001,24,0), '24': (24,24,0), '25': (25,25,0),
         '29.97 NDF': (30000/1001,30,0), '29.97 DF': (30000/1001,30,2),
         '30': (30,30,0), '50': (50,50,0), '59.94 NDF': (60000/1001,60,0),
         '59.94 DF': (60000/1001,60,4), '60': (60,60,0)}
def parse(value, rate):
    fps, nominal, drop = RATES[rate]
    parts=value.replace(';',':').split(':')
    if len(parts)!=4: raise ValueError('Use HH:MM:SS:FF (or HH:MM:SS;FF).')
    h,m,s,f=map(int,parts)
    if h<0 or not 0<=m<60 or not 0<=s<60 or not 0<=f<nominal:
        raise ValueError('Timecode contains an out-of-range field.')
    if drop and m%10 and s==0 and f<drop:
        raise ValueError('That frame number is skipped by drop-frame timecode.')
    minutes=h*60+m
    return ((h*3600+m*60+s)*nominal+f-drop*(minutes-minutes//10))/fps

def format_tc(seconds,rate='29.97 DF'):
    fps,n,drop=RATES[rate]
    frames=max(0,int(math.floor(seconds*fps+0.5)))
    if drop:
        ten=n*600-drop*9
        d,r=divmod(frames,ten)
        frames+=drop*9*d+drop*max(0,(r-drop)//(n*60-drop))
    h,frames=divmod(frames,n*3600);m,frames=divmod(frames,n*60);s,f=divmod(frames,n)
    return f'{h:02}:{m:02}:{s:02}{";" if drop else ":"}{f:02}'

def clock(seconds):
    ms=round(max(0,seconds)*1000);s,ms=divmod(ms,1000);m,s=divmod(s,60);h,m=divmod(m,60)
    return f'{h:02}:{m:02}:{s:02}.{ms:03}'
