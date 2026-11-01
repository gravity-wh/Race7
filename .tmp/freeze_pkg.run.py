#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交付包冻结工具（赛题七 eda260769）。

用法:
    python3 freeze_pkg.py <包根目录>

产出:
    MANIFEST.txt      关键文件的 sha256 清单（供评测方/自检核对）
    RELEASE_CHECK.txt 发布自检结果
    标准输出最后一行  包指纹

包指纹口径（2026-10-30 定义，可复现）:
    fp = md5( 排序后的 "sha256<两个空格>相对路径" 行, 以 \n 连接并补尾随 \n )
    统计范围为包内全部普通文件，排除 MANIFEST.txt、RELEASE_CHECK.txt、*.bak.*
"""
import hashlib
import io
import os
import sys
import time

KEY_FILES = [
    'eda260769_性能报告.txt',
    'README.md',
    'S4_GPU_平台限制说明.md',
    'task1/run.sh',
    'task1/README.md',
    'task1/regularize_singular.py',
    'task1/build_lu.sh',
    'task1/bin/test_lu_gpu',
    'task1/GLU_public/src/test_lu_gpu',
    'task1/GLU_public/src/lu_cmd',
    'task2/run.sh',
    'task2/README.md',
    'task2/run_datasweep.sh',
    'task2/tools/cmp_tables.py',
    'task2/CUSPICE_public/local/ngspice',
    'task2/CUSPICE_public/local/ngspice.bin',
]
EXCLUDE_NAMES = {'MANIFEST.txt', 'RELEASE_CHECK.txt'}


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def walk_files(root):
    out = []
    for dp, dns, fns in os.walk(root):
        dns.sort()
        for fn in sorted(fns):
            if fn in EXCLUDE_NAMES or '.bak.' in fn:
                continue
            fp = os.path.join(dp, fn)
            if os.path.islink(fp) or not os.path.isfile(fp):
                continue
            out.append(os.path.relpath(fp, root).replace(os.sep, '/'))
    return sorted(out)


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else '.')
    files = walk_files(root)
    print('files scanned:', len(files))

    # 与 du -sh 口径一致：按磁盘分配块计（10k 个小文件时 apparent size 会低估约 15%）
    total = sum(os.stat(os.path.join(root, f)).st_blocks * 512 for f in files)
    print('total size(du-style): %.1f MB' % (total / 1048576.0))

    # 指纹
    digest = []
    for rel in files:
        digest.append('%s  %s' % (sha256(os.path.join(root, rel)), rel))
    fp = hashlib.md5(('\n'.join(digest) + '\n').encode('utf-8')).hexdigest()

    # MANIFEST
    mlines = ['# 预提交包清单（自动生成 %s）' % time.strftime('%Y-%m-%d %H:%M:%S'),
              '# 文件总数: %d' % len(files),
              '# 包大小: %dM' % int(round(total / 1048576.0)),
              '# 包指纹: %s' % fp,
              '#   口径: md5(排序后的 "sha256  相对路径" 行)，排除 MANIFEST.txt/RELEASE_CHECK.txt/*.bak.*', '']
    for rel in KEY_FILES:
        p = os.path.join(root, rel)
        if os.path.isfile(p):
            mlines.append('%s  %s' % (sha256(p), rel))
    io.open(os.path.join(root, 'MANIFEST.txt'), 'w', encoding='utf-8', newline='\n').write('\n'.join(mlines) + '\n')
    print('MANIFEST.txt written (%d key files)' % (len(mlines) - 6))

    # 自检
    checks = []
    def add(ok, label):
        checks.append(('PASS' if ok else 'FAIL') + '  ' + label)

    def ex(rel):
        p = os.path.join(root, rel)
        return os.path.isfile(p) and os.access(p, os.X_OK)

    def isf(rel):
        return os.path.isfile(os.path.join(root, rel))

    add(ex('task1/run.sh'), 'task1/run.sh 存在且可执行')
    add(ex('task1/GLU_public/src/lu_cmd'), 'A146: task1/GLU_public/src/lu_cmd 可执行')
    add(ex('task1/GLU_public/src/test_lu_gpu'), 'A146: task1/GLU_public/src/test_lu_gpu 可执行')
    add(isf('task1/README.md'), 'task1/README.md 存在')
    add(isf('task1/regularize_singular.py'), 'task1/regularize_singular.py 存在')
    add(ex('task2/run.sh'), 'task2/run.sh 存在且可执行')
    add(ex('task2/CUSPICE_public/local/ngspice'), 'A146: task2/CUSPICE_public/local/ngspice 可执行')
    add(isf('task2/CUSPICE_public/local/ngspice.bin'), 'GPU 二进制 ngspice.bin 存在')
    add(ex('task2/CUSPICE_public/cuspice_cpu/src/ngspice'), 'CPU 兜底二进制可执行')
    add(isf('task2/README.md'), 'task2/README.md 存在')

    rep = io.open(os.path.join(root, 'eda260769_性能报告.txt'), encoding='utf-8').read()
    add('GPU 利用率' in rep and 'ht-smi' in rep, '报告含 GPU 利用率实测段')
    add('13/13' in rep, '报告标注任务一 13/13')
    add(isf('S4_GPU_平台限制说明.md'), 'S4 平台限制说明存在')
    add('/home/eda260769' not in rep, '报告无硬编码家目录路径')

    # MANIFEST 自校验
    bad = 0
    for ln in io.open(os.path.join(root, 'MANIFEST.txt'), encoding='utf-8'):
        ln = ln.rstrip('\n')
        if not ln or ln.startswith('#'):
            continue
        h, _, p = ln.partition('  ')
        fp2 = os.path.join(root, p)
        if not os.path.isfile(fp2) or sha256(fp2) != h:
            bad += 1
    add(bad == 0, 'MANIFEST 全部哈希校验通过')

    fails = sum(1 for c in checks if c.startswith('FAIL'))
    out = ['预提交包发布自检  %s' % time.strftime('%Y-%m-%d %H:%M:%S'), '-' * 46]
    out += checks
    out += ['-' * 46,
            '文件数: %d   大小: %dM' % (len(files), int(round(total / 1048576.0))),
            '包指纹: %s' % fp,
            'FAIL 数: %d' % fails]
    io.open(os.path.join(root, 'RELEASE_CHECK.txt'), 'w', encoding='utf-8', newline='\n').write('\n'.join(out) + '\n')
    print('\n'.join(out))
    print('\nFINGERPRINT %s' % fp)
    return 0 if fails == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
