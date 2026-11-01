# -*- coding: utf-8 -*-
import os, shutil, glob

base = os.path.expanduser('~/Huangcw/presubmission_eda260769')

# 1) 我自己的备份移出包外
bakdir = os.path.expanduser('~/Huangcw/backup/rc_docs_20261030')
os.makedirs(bakdir, exist_ok=True)
moved = []
for p in glob.glob(os.path.join(base, '**', '*.bak.*'), recursive=True):
    t = os.path.join(bakdir, os.path.basename(p))
    shutil.move(p, t)
    moved.append(p)
print('moved out %d bak files -> %s' % (len(moved), bakdir))

# 2) 测试产物（可一键再生成）
for d in ('task2/out', 'task2/golden_out_cpu', 'task2/golden_out_gpu'):
    p = os.path.join(base, d)
    if os.path.isdir(p):
        n = sum(len(f) for _, _, f in os.walk(p))
        shutil.rmtree(p)
        print('removed %s (%d files)' % (d, n))

# 3) 运行时缓存
for p in glob.glob(os.path.join(base, 'task2/CUSPICE_public/local/.gpu_probe_fail')):
    os.remove(p); print('removed gpu probe cache')

# 4) 其余可疑残留
for pat in ('**/*.pyc', '**/__pycache__', '**/.dsrow*', '**/*.dsrow*.sp'):
    for p in glob.glob(os.path.join(base, pat), recursive=True):
        if os.path.isdir(p):
            shutil.rmtree(p)
        else:
            os.remove(p)
        print('removed', os.path.relpath(p, base))

n = sum(len(f) for _, _, f in os.walk(base))
print('files now:', n)
