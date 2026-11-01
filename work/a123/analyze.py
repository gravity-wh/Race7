#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 a123_out/*.log 里的 JSON 汇总成 A1/A2/A3 三张表（markdown）。"""
import glob
import json
import os
import sys

outdir = sys.argv[1] if len(sys.argv) > 1 else 'a123_out'
rows = {}
for p in sorted(glob.glob(os.path.join(outdir, '*.a*.log'))):
    tag = os.path.basename(p).split('.a')[0]
    for line in open(p, encoding='utf-8', errors='replace'):
        if line.startswith('JSON:'):
            d = json.loads(line[5:])
            d['_tag'] = tag
            d['_att'] = os.path.basename(p)
            rows.setdefault(tag, {}).update(d)   # 合并（JSON 覆盖同名键）
        elif line.startswith('fp64 ST:'):
            rows.setdefault(tag, {})['res64_st'] = float(line.rsplit('res=', 1)[1])
        elif line.startswith('fp32 ST:'):
            rows.setdefault(tag, {})['res32_st'] = float(line.rsplit('res=', 1)[1])
        elif line.startswith('fp64 PAR:') and 'res=' in line:
            rows.setdefault(tag, {})['res64_par'] = float(line.rsplit('res=', 1)[1])
        elif line.startswith('fp32 PAR trisolve:') and 'res=' in line:
            rows.setdefault(tag, {})['res32_par'] = float(line.rsplit('res=', 1)[1])
order = ['sky130_bandgap', 'sky130_flash', 'pg2k', 'pg5k', 'pg10k', 'pg25k', 'pg50k']
items = [rows[t] for t in order if t in rows]

def f(x, spec='%.2f'):
    if x is None:
        return '—'
    if isinstance(x, float) and (x != x):
        return 'NaN'
    return spec % x

print('## A1  GMRES-IR（fp32 因子 / fp64 因子 两套预条件）\n')
print('| 矩阵 | n | fp32 直解残差 | fp32+IR 轮数 | fp32+IR 时间(ms) | fp32+IR 残差 | fp64+IR 轮数 | fp64+IR 时间(ms) | fp64+IR 残差 |')
print('|---|---|---|---|---|---|---|---|---|')
for d in items:
    print('| %s | %d | %s | %s | %s | %s | %s | %s | %s |' % (
        d['_tag'], d['n'], f(d.get('res32_par'), '%.2e'),
        d.get('ir32_iters', '—'), f(d.get('ir32_ms')), f(d.get('ir32_res'), '%.2e'),
        d.get('ir64_iters', '—'), f(d.get('ir64_ms')), f(d.get('ir64_res'), '%.2e')))

print('\n## A2  fp32 因子 vs fp64 因子（存储 / 分解时间 / 残差）\n')
print('| 矩阵 | L+U nnz (fp64) | L+U nnz (fp32) | 存储 fp64 (MB) | 存储 fp32 (MB) | 存储比 | 分解 ST fp64 (ms) | 分解 ST fp32 (ms) | 速度比 | 残差 fp64 | 残差 fp32 |')
print('|---|---|---|---|---|---|---|---|---|---|---|')
for d in items:
    lu64 = d['lnnz64'] + d['unnz64']
    lu32 = d['lnnz32'] + d['unnz32']
    mr = d['mem_fp64_mb'] / d['mem_fp32_mb'] if d.get('mem_fp32_mb') else float('nan')
    print('| %s | %d | %d | %.3f | %.3f | %.2f× | %s | %s | %s | %s | %s |' % (
        d['_tag'], lu64, lu32, d['mem_fp64_mb'], d['mem_fp32_mb'], mr,
        f(d['t_factor_st64_ms']), f(d['t_factor_st32_ms']), f(d.get('speedup_factor_st')),
        f(d.get('res64_st'), '%.2e'), f(d.get('res32_st'), '%.2e')))

print('\n## A3  规模曲线（因子 / 三角求解 / IR）\n')
print('| 矩阵 | n | nnz | L+U nnz | 因子 ST fp64 (ms) | 因子 ST fp32 (ms) | 因子 PAR fp64 (ms) | 三角 ST fp64 (ms) | 三角 PAR fp64 (ms) | 三角 PAR fp32 (ms) | IR32 总 (ms) | IR64 总 (ms) |')
print('|---|---|---|---|---|---|---|---|---|---|---|---|')
for d in items:
    print('| %s | %d | %d | %d | %s | %s | %s | %s | %s | %s | %s | %s |' % (
        d['_tag'], d['n'], d['nnz'], d['lnnz_cpu'] + d['unnz_cpu'],
        f(d['t_factor_st64_ms']), f(d['t_factor_st32_ms']), f(d['t_factor_par64_ms']),
        f(d['t_trisolve_st64_ms']), f(d['t_trisolve_par64_ms']), f(d['t_trisolve_par32_ms']),
        f(d.get('ir32_ms')), f(d.get('ir64_ms'))))
