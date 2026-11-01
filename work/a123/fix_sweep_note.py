# -*- coding: utf-8 -*-
import io, os, hashlib
p = os.path.expanduser('~/Huangcw/presubmission_eda260769/eda260769_性能报告.txt')
s = io.open(p, encoding='utf-8').read()
old = ('说明: datasweep 的各参数组相互独立，默认 64 并发（DS_MAXJOBS=64）。\n'
       '串行基线 9.35 s，默认并行 0.24 s，约 39 倍加速；输出表数均为 300。\n'
       '（2026-10-30 18:24 复测，同机同时刻测得，机器 load≈74）')
new = ('说明: datasweep 的各参数组相互独立，默认 64 并发（DS_MAXJOBS=64）。\n'
       '串行基线 9.35 s；本表 64 并发实测 0.24 s（38.6×，2026-10-30 18:24 复测，机器 load≈74）。\n'
       '摘要采用更保守的 0.44 s：同一脚本在不同负载下实测 0.24–0.49 s，报告口径取保守值。\n'
       '输出表数均为 300。')
assert s.count(old) == 1, s.count(old)
io.open(p, 'w', encoding='utf-8', newline='\n').write(s.replace(old, new))
print('note reconciled')
