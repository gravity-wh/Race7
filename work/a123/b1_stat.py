# -*- coding: utf-8 -*-
import json, glob, os, math, re, sys
def t95(n):
    T={10:2.262,15:2.131,20:2.093,30:2.045,40:2.021}
    return T.get(n,2.0)
def st(v):
    n=len(v); m=sum(v)/n
    sd=math.sqrt(sum((x-m)**2 for x in v)/(n-1)) if n>1 else 0
    return n,m,sd,t95(n)*sd/math.sqrt(n) if n>1 else 0
d='work/a123/b1'
per={}
for f in glob.glob(os.path.join(d,'job_*.log')):
    mat=re.sub(r'^job_\d+_','',os.path.basename(f))[:-4]
    txt=open(f,encoding='utf-8',errors='replace').read()
    for l in txt.split('\n'):
        if l.startswith('JSON:'):
            per.setdefault(mat,[]).append(json.loads(l[5:]))
for mat in ('sky130_bandgap','sky130_flash','pg2k','pg5k','pg10k'):
    rs=per.get(mat,[])
    if not rs: continue
    print('== %-14s runs=%d'%(mat,len(rs)))
    for k in ('t_factor_st64_ms','t_factor_st32_ms','t_factor_par64_ms','t_trisolve_par64_ms','t_trisolve_par32_ms','ir32_ms','ir64_ms'):
        v=[r[k] for r in rs if r.get(k,-1) and r[k]>0]
        if len(v)>=3:
            n,m,sd,ci=st(v)
            print('   %-20s %12.2f ± %-9.2f  CV %4.1f%%'%(k,m,ci,100*sd/m))
    def ratio(fn):
        v=[fn(r) for r in rs]
        return [x for x in v if x]
    a=ratio(lambda r: r['t_factor_st64_ms']/r['t_factor_st32_ms'] if r.get('t_factor_st32_ms',0)>0 else None)
    if len(a)>=3:
        n,m,sd,ci=st(a); print('   %-20s %12.3f ± %-9.3f  (上界 %.3f)'%('ST64/ST32',m,ci,m+ci))
    b=ratio(lambda r: r['t_factor_st64_ms']/r['t_factor_par64_ms'] if r.get('t_factor_par64_ms',0)>0 else None)
    if len(b)>=3:
        n,m,sd,ci=st(b); print('   %-20s %12.3f ± %-9.3f'%('ST/PAR',m,ci))
    c=ratio(lambda r: r['ir32_ms']/r['t_trisolve_par64_ms'] if r.get('t_trisolve_par64_ms',0)>0 else None)
    if len(c)>=3:
        n,m,sd,ci=st(c); print('   %-20s %12.3f ± %-9.3f'%('IR32/fp64tri',m,ci))
    print()
