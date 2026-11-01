# -*- coding: utf-8 -*-
import json, glob, os, math, sys
def t95(n):
    # 双侧 95% 的 t 值（小样本）
    T = {2:12.706,3:4.303,4:3.182,5:2.776,6:2.571,7:2.447,8:2.365,9:2.306,10:2.262,
         11:2.228,12:2.201,15:2.145,20:2.093,30:2.045}
    return T.get(n, 1.96)
def stats(v):
    n=len(v); m=sum(v)/n
    sd=math.sqrt(sum((x-m)**2 for x in v)/(n-1)) if n>1 else 0.0
    se=sd/math.sqrt(n) if n else 0
    return n, m, sd, se, t95(n)*se
def show(tag, v, unit='ms'):
    n,m,sd,se,ci = stats(v)
    cv = 100*sd/m if m else 0
    print('  %-22s n=%2d  %9.2f ± %-7.2f (95%%CI ±%.2f)  sd=%.2f  CV=%.1f%%' % (tag,n,m,ci,ci,sd,cv))
for f in sorted(glob.glob('work/a123/b2/*.jsonl')):
    name=os.path.basename(f)[:-6]
    rows=[json.loads(l[5:]) for l in open(f,encoding='utf-8') if l.startswith('JSON:')]
    if not rows: continue
    print('==', name, 'runs=', len(rows))
    for key in ('t_factor_st64_ms','t_factor_st32_ms','t_factor_par64_ms','t_trisolve_par64_ms','ir32_ms','ir64_ms'):
        v=[r[key] for r in rows if r.get(key, -1) and r[key] > 0]
        if len(v) >= 2: show(key, v)
    r32=[r['t_factor_st64_ms']/r['t_factor_st32_ms'] for r in rows if r.get('t_factor_st32_ms',0)>0]
    if len(r32)>=2: show('ratio ST64/ST32', r32, 'x')
