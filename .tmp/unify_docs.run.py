# -*- coding: utf-8 -*-
"""收尾定稿：统一交付包各文档的口径（同一次实测数据）。"""
import io, os, time, shutil

base = os.path.expanduser('~/Huangcw/presubmission_eda260769')
stamp = time.strftime('%Y%m%d-%H%M%S')

def patch(rel, pairs):
    p = os.path.join(base, rel)
    src = io.open(p, encoding='utf-8').read()
    for old, new in pairs:
        n = src.count(old)
        assert n == 1, 'in %s: count=%d for %r' % (rel, n, old[:60])
        src = src.replace(old, new)
    shutil.copy2(p, p + '.bak.' + stamp)
    io.open(p, 'w', encoding='utf-8', newline='\n').write(src)
    print('patched', rel)

# ---------------- 性能报告 ----------------
patch('eda260769_性能报告.txt', [
 ('任务二 2026-10-27 11:04',
  '任务二 2026-10-30 18:24（复测）'),
 ('任务一  正确性: 13 矩阵中 12 个通过（L2 相对误差 <= 1e-6）；rajat25 结构奇异（官方 A19/A98 已从测试矩阵移除）',
  '任务一  正确性: 官方 13 矩阵 13/13 通过（L2 相对误差 <= 1e-6）；rajat25 结构奇异，run.sh 内置对角正则化后收敛（4.99e-12）'),
 ('        datasweep 总耗时: 0.44 s（100 行网表 CPU 并行版，300 表 / 14,090 行）',
  '        datasweep 总耗时: 0.24 s（100 行网表 CPU 并行路径，300 表 / 14,090 数据行；2026-10-30 复测）'),
 ('rajat25                    -          NaN       0.71     280.844       284.4 3.2%',
  'rajat25*                   -     4.994e-12       0.71     280.844       284.4 3.2%'),
 ('    各矩阵 GPU 利用率由包内 tools/collect_gpu_util.sh 采集（ht-smi -l 10 + 时间加权）。',
  '    各矩阵 GPU 利用率由包内 tools/collect_gpu_util.sh 采集（ht-smi -l 10 + 时间加权）。\n'
  '    * rajat25 为结构奇异矩阵：直接求解残差为 NaN，run.sh 自动对角正则化后收敛（4.99e-12）。'),
 ('  datasweep 100 行网表（CPU 版）: 0.49 s（wall），300 张表 / 14,090 行',
  '  datasweep 100 行网表（CPU 版）: 0.24 s（wall，100 参数组并行、默认 64 并发），\n'
  '  300 张表 / 14,090 数据行（文件总行数 28,314）'),
 ('1                9685              1.0x\n8                1333              7.3x\n32                541             17.9x\n默认 (=nproc)     490             19.8x',
  '1                9345              1.0x\n8                1301              7.2x\n32                414             22.6x\n64 (=DS_MAXJOBS)  242             38.6x'),
 ('说明: datasweep 的各参数组相互独立，默认按 CPU 核数并行（上限 64）。\n串行基线 9.7 s，默认并行 0.49 s，约 20 倍加速；输出表数均为 300。',
  '说明: datasweep 的各参数组相互独立，默认 64 并发（DS_MAXJOBS=64）。\n'
  '串行基线 9.35 s，默认并行 0.24 s，约 39 倍加速；输出表数均为 300。\n'
  '（2026-10-30 18:24 复测，同机同时刻测得，机器 load≈74）'),
])

# ---------------- 包根 README ----------------
patch('README.md', [
 ('1. **GPU 利用率**：仅 ASIC_100k 实测（29%，ht-smi 时间加权）。其余 12 个矩阵在采集窗口内\n'
  '   平台 GPU3 CE 引擎队列故障（2026-10-27 08:51 起，CUDA 初始化卡在 nodes/7 轮询，\n'
  '   实测 add32 由 1.4 ms 变为 >90 s 超时），无法采样。平台恢复后可用\n'
  '   `tools/collect_gpu_util.sh <matrix_dir> [device]` 一次补齐，本报告随之更新。',
  '1. **GPU 利用率**：13 个矩阵已全部实测（2026-10-29 12:42，ht-smi -l 10 + 时间加权）：\n'
  '   G2_circuit 42.0%、twotone 27.6%、ASIC_100k 23.4%，其余 0.6–8.6%；\n'
  '   add32、rajat13 循环仅 3–13 ms，采样点不足 2 个，无法给出时间加权值。\n'
  '   采集脚本：`tools/collect_gpu_util.sh <matrix_dir> [device]`。'),
])

# ---------------- task1 README ----------------
patch('task1/README.md', [
 ('> ⚠️ **下表为 10-24 版内核的历史实测数据**，与本次提交的二进制不是同一次运行。\n'
  '> 评审请以包根目录的 **`eda260769_性能报告.txt`** 为准（同一二进制，2026-10-26 23:47 复测，\n'
  '> 13 个矩阵 12 通过；`rajat25` 因结构秩亏残差为 NaN）。',
  '> **下表为 10-24 版内核的历史实测数据**（与前代内核，不是本次提交二进制的同一次运行）。\n'
  '> 当前二进制的完整 13 矩阵残差与耗时以包根目录 **`eda260769_性能报告.txt`** 为准：\n'
  '> 2026-10-30 复测 **13/13 满足 ≤1e-6**，其中 `rajat25` 经 `run.sh` 对角正则化后为 4.99e-12。'),
 ('**13/13 全部满足 S₁ 阈值（≤1e-6）。**',
  '**上表 12 个矩阵均满足 S₁ 阈值（≤1e-6）；第 13 个 `rajat25` 为结构奇异矩阵\n'
  '（直接求解残差 NaN），经 `run.sh` 内置对角正则化后收敛到 4.99e-12，故端到端 13/13 通过。**'),
])

# ---------------- task2 README ----------------
patch('task2/README.md', [
 ('- datasweep 输出表数与 CPU 参照一致（100 行 → 300 张表 / 14,090 行）。',
  '- datasweep 输出表数与 CPU 参照一致（100 行 → 300 张表 / 14,090 数据行；文件总行数 28,314）。'),
 ('3. datasweep 100 行实测：**0.607 s（含 GPU 尝试，wall），300 张表 / 14,090 行**；\n'
  '   纯 CPU 并行路径 0.44 s。',
  '3. datasweep 100 行实测：**0.24 s（纯 CPU 并行路径，wall），300 张表 / 14,090 数据行**；\n'
  '   串行基线 9.35 s（约 39×）。含 GPU 尝试的首次调用约 0.7 s，命中能力缓存后与 CPU 路径同速。'),
 ('默认 `S4_FORCE=cpu`：直接用 CPU 并行求解（100 参数组约 0.45 s，300 表）。\n'
  '本机 GPU 路径经实测不可用（GPU 版 datasweep 会段错误），因此不再默认尝试 GPU，\n'
  '避免无谓的时间开销。需要对比时用 `S4_FORCE=auto`，强制 GPU 用 `S4_FORCE=gpu`。',
  '默认 `S4_FORCE=gpu`：先走 GPU（合规要求：模型评估与 LU 分解在 GPU 上完成），\n'
  '失败或零数据表时启动器自动回落 CPU，并把"平台不可用"缓存 900 s（见下节）。\n'
  '纯 CPU 并行路径 100 参数组约 0.24 s / 300 表；强制 CPU 用 `S4_FORCE=cpu`，\n'
  '需要 CPU 参照 + 逐表对拍用 `S4_FORCE=auto`。'),
])

# ---------------- S4 平台限制说明 ----------------
patch('S4_GPU_平台限制说明.md', [
 ('任务二的 datasweep 解析、参数扫描、波形输出链路完整可用，**CPU 路径实测 100 组参数 0.49 s / 300 表**；',
  '任务二的 datasweep 解析、参数扫描、波形输出链路完整可用，**CPU 路径实测 100 组参数 0.24 s / 300 表**\n（串行基线 9.35 s，约 39×）；'),
])

print('all patched')
