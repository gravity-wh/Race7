# -*- coding: utf-8 -*-
import os, shutil, glob
base = os.path.expanduser('~/Huangcw/presubmission_eda260769')
dst = os.path.expanduser('~/Huangcw/backup/pkg_src_baks_20261030')
os.makedirs(dst, exist_ok=True)
n = 0
for p in glob.glob(os.path.join(base, '**', '*.bak_*'), recursive=True):
    rel = os.path.relpath(p, base).replace(os.sep, '__')
    shutil.move(p, os.path.join(dst, rel))
    n += 1
print('moved %d source-bak files -> %s' % (n, dst))
print('remaining in pkg:', sum(len(f) for _, _, f in os.walk(base)))
