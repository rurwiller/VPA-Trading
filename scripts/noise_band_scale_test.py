"""Trend-day (noise band) breakout: scale-out in thirds and a breakeven stop, per ticker.

Variants: the original (hold to the rule), thirds at 1% / 2% with the last third riding the rule, and the same plus a stop
at the entry price once the first third has taken profit. Costs = ticker spread + 1 bp per round trip. Before / after
2024-11-01. Run from the repo root:   python scripts/noise_band_scale_test.py TSLA AMD GLD SLV
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
import intraday_momentum_test as T
from midcap_test import cost_bps
SPLIT=pd.Timestamp("2024-11-01")
def run(sym, levels, fracs, be=False):
    m1=T.load_bars_file(f'data/alpaca/{sym}-1m-ext.csv.gz')
    C,O,VW=T.matrices(sym)
    day=m1.index.normalize(); mi=((m1.index-day)/pd.Timedelta(minutes=1)).astype(int)-570
    m1=m1.assign(day=day,mi=mi); m1=m1[(m1.mi>=0)&(m1.mi<390)]
    full=m1.groupby('day').mi.max()>=389; m1=m1[m1.day.isin(full.index[full])]
    Hh=m1.pivot(index='day',columns='mi',values='high').reindex(columns=range(390)).ffill(axis=1).reindex(C.index).to_numpy()
    Ll=m1.pivot(index='day',columns='mi',values='low').reindex(columns=range(390)).ffill(axis=1).reindex(C.index).to_numpy()
    c=C.to_numpy(); o=O.to_numpy(); vw=VW.to_numpy(); prev=np.r_[np.nan,c[:-1,389]]
    sigma=pd.DataFrame(np.abs(c/o[:,None]-1)).rolling(14).mean().shift(1).to_numpy()
    cost=cost_bps(sym)/1e4; checks=list(range(29,360,30)); ub0,lb0=np.fmax(o,prev),np.fmin(o,prev)
    out=np.full(len(c),np.nan)
    for k in range(len(c)):
        if np.isnan(sigma[k,checks[0]]) or np.isnan(prev[k]): continue
        pos=0; entry=0.0; rem=0.0; ret=0.0; targets=[]; tfr=[]; be_on=False
        def close(px,frac):
            nonlocal ret
            ret+=frac*(pos*(px/entry-1)-cost)
        for ci,t in enumerate(checks):
            # scan bars from the previous check (or entry) to this check for profit targets
            px=c[k,t]; ub=ub0[k]*(1+sigma[k,t]); lb=lb0[k]*(1-sigma[k,t])
            want=pos
            if pos==1 and px<max(ub,vw[k,t]): want=0
            elif pos==-1 and px>min(lb,vw[k,t]): want=0
            if want==0: want=1 if px>ub else (-1 if px<lb else 0)
            if want!=pos:
                if pos!=0 and rem>0: close(px,rem); rem=0
                if want!=0:
                    entry=px; rem=1.0; targets=[entry*(1+want*l) for l in levels]; tfr=list(fracs); be_on=False
                pos=want
            # targets between this check and the next (bars t+1 .. next check or close)
            if pos!=0 and tfr:
                end=checks[ci+1] if ci+1<len(checks) else 389
                for b in range(t+1,end+1):
                    if be and be_on and rem>1e-9 and ((pos>0 and Ll[k,b]<=entry) or (pos<0 and Hh[k,b]>=entry)):
                        close(entry,rem); rem=0.0; pos=0; break
                    if not tfr: continue
                    hit=(Hh[k,b]>=targets[0]) if pos>0 else (Ll[k,b]<=targets[0])
                    while tfr and ((Hh[k,b]>=targets[0]) if pos>0 else (Ll[k,b]<=targets[0])):
                        close(targets[0],tfr[0]); rem-=tfr[0]; targets.pop(0); tfr.pop(0); be_on=True
        if pos!=0 and rem>1e-9: close(c[k,389],rem)
        out[k]=ret
    return pd.Series(out,index=C.index)
if __name__=="__main__":
    third=1/3
    for sym in (sys.argv[1:] or ['TSLA','AMD','QQQ']):
        rows=[]
        for name,(lv,fr,be) in {'no scale-out (original)':([],[],False),'thirds 1%/2%, last third rides':([0.01,0.02],[third,third],False),
                                'thirds 1%/2% + breakeven stop after the first take':([0.01,0.02],[third,third],True)}.items():
            r=run(sym,lv,fr,be); d=r.index<SPLIT
            rows.append(dict(variant=name,bps_before=r[d].mean()*1e4,bps_after=r[~d].mean()*1e4,sharpe_before=r[d].mean()/r[d].std()*np.sqrt(252),
                             sharpe_after=r[~d].mean()/r[~d].std()*np.sqrt(252),worst_day_bps=r.min()*1e4,pct_green=(r[r!=0]>0).mean()*100))
        print(sym); print(pd.DataFrame(rows).round(2).to_string(index=False))
