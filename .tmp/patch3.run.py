# -*- coding: utf-8 -*-
import io, os, shutil
base = os.path.expanduser('~/Huangcw/presubmission_eda260769')
p = os.path.join(base, 'eda260769_性能报告.txt')
src = io.open(p, encoding='utf-8').read()

old_note = '  注: GPU context 创建/首次调用无法在故障窗口内单独计量，该项亦按 0.005 计，影响可忽略。'
new_note = '  注: GPU context 创建/首次调用无法与迭代阶段精确分离计量，该项亦按 0.005 计，影响可忽略。'

old_mech = ('  实测: ASIC_100k 约 29%（ht-smi 时间加权采样）\n'
 '  机理: 每层 2 次 kernel 发射（div + upd），单次发射约 420 us（正常约 5 us）；\n'
 '        ASIC_100k 共 1634 层 -> 约 3268 次发射，CPU 侧发射时间约 1373 ms，\n'
 '        与数值分解总耗时 1377 ms 吻合 => CPU 发射瓶颈主导，GPU 空闲等待。\n'
 '        各矩阵层数已实测（12 - 3729 层），层数越多发射开销越大。')
new_mech = ('  实测: ASIC_100k 23.4%（ht-smi 时间加权，2026-10-29 12:42 复测）\n'
 '  机理（2026-10-29 实测定位）：\n'
 '        ASIC_100k 共 1634 层、合计 3.96M nnz、迭代 1362 ms -> 每层约 833 us；\n'
 '        每层约 6 万次「右看」散射更新 -> 每次约 13 ns，即随机访存延迟量级\n'
 '        （有效带宽仅约 1 GB/s 级），故 GPU 大部分时间在等内存，而非空转等发射。\n'
 '        排除「发射瓶颈」解释的两条对照实验（同一健康窗口）：\n'
 '          1) LU_ERRCHK=1（每次发射后 cudaGetLastError）vs 默认：1362 vs 1362 ms，无差异；\n'
 '          2) KLU_BTF=0 使层数 1634 -> 1492，但迭代 1374.9 -> 1394.7 ms（反而更慢）。\n'
 '        针对性改进：U(k,:) 对应列的平均填充长度 >= 250 时改用「一 block 一列」\n'
 '        更新内核（LU_QSPLIT=auto，阈值 LU_QSMAX），ASIC_100k 1374.6 -> 641.2 ms（2.09x）。\n'
 '        各矩阵层数已实测（12 - 3729 层）；层数本身不直接决定耗时，每层更新量的访存\n'
 '        局部性才是主因。')

for o, n in ((old_note, new_note), (old_mech, new_mech)):
    assert src.count(o) == 1, (src.count(o), o[:40])
    src = src.replace(o, n)
shutil.copy2(p, os.path.join(os.path.expanduser('~/Huangcw/backup/rc_docs_20261030'),
                             'eda260769_性能报告.txt.bak3'))
io.open(p, 'w', encoding='utf-8', newline='\n').write(src)
print('patched report (round 3: S3 mechanism)')
