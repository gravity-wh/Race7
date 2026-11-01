# -*- coding: utf-8 -*-
"""订正交付包性能报告中的两处过期数字（A.53 固化后未同步）。"""
import io, os, sys, time, shutil, hashlib

base = os.path.expanduser('~/Huangcw/presubmission_eda260769')
rep = os.path.join(base, 'eda260769_性能报告.txt')
man = os.path.join(base, 'MANIFEST.txt')

stamp = time.strftime('%Y%m%d-%H%M%S')
bak = rep + '.bak.' + stamp
shutil.copy2(rep, bak)
print('backup:', bak)

src = io.open(rep, encoding='utf-8').read()

old_time = u'采集时间: 任务一 2026-10-29 12:34（全量重测，GPU 四节点均健康）'
new_time = (u'采集时间: 任务一 2026-10-30 17:45（迭代耗时，默认参数固化后全量重测，GPU 四节点健康；'
            u'一次性耗时取自 10-27）；GPU 利用率 2026-10-29 12:42')
old_w = u'加权耗时: 375.5 ms（13 矩阵平均；剔除 rajat25 后 373.6 ms）'
new_w = u'加权耗时: 282.7 ms（13 矩阵平均；剔除 rajat25 后 282.6 ms）'

for o in (old_time, old_w):
    assert src.count(o) == 1, ('NOT FOUND / NOT UNIQUE: %r count=%d' % (o, src.count(o)))

src = src.replace(old_time, new_time).replace(old_w, new_w)
io.open(rep, 'w', encoding='utf-8', newline='\n').write(src)
print('report patched')

# MANIFEST: 更新头部时间戳 + 报告哈希
h = hashlib.sha256(io.open(rep, 'rb').read()).hexdigest()
mlines = io.open(man, encoding='utf-8').read().split('\n')
hit = 0
for i, ln in enumerate(mlines):
    if ln.endswith('  eda260769_性能报告.txt'):
        mlines[i] = h + '  eda260769_性能报告.txt'
        hit += 1
    elif ln.startswith('# 预提交包清单（自动生成'):
        mlines[i] = u'# 预提交包清单（自动生成 %s）' % time.strftime('%Y-%m-%d %H:%M:%S')
assert hit == 1, 'manifest hash line not found'
io.open(man, 'w', encoding='utf-8', newline='\n').write('\n'.join(mlines))
print('manifest patched, report sha256 =', h)
