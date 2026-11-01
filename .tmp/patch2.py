# -*- coding: utf-8 -*-
import io, os, time, shutil
base = os.path.expanduser('~/Huangcw/presubmission_eda260769')
p = os.path.join(base, 'eda260769_性能报告.txt')
src = io.open(p, encoding='utf-8').read()
pairs = [
 ('          GPU 利用率 2026-10-28 13:15-13:20（ht-smi -l 10，13 矩阵）',
  '          GPU 利用率 2026-10-29 12:42（ht-smi -l 10，13 矩阵）'),
 ('（add32/bcircuit/rajat13 采样点不足）',
  '（add32/rajat13 采样点不足，bcircuit 循环仅 72 ms 读数波动大）'),
 ('  GPU 版: 故障期间不可用；10-26 历史实测因 SDK 版本不匹配报 hcErrorInvalidDevice，\n'
  '          仅输出 3 个时间点，已被自适应运行器判为不一致并回退 CPU。\n\n'
  '说明: 本报告在平台 GPU 故障窗口内产出；任务二数据来自 CPU 参照路径，GPU 数据待恢复后补测。',
  '  GPU 版: 受运行时版本不匹配限制（3.8.0 编译 / 3.5.3 运行时）报 hcErrorInvalidDevice，\n'
  '          仅输出 3 个时间点，已被自适应运行器判为不一致并回退 CPU；\n'
  '          完整证据链见包根 `S4_GPU_平台限制说明.md`。\n\n'
  '说明: 任务二数据来自 CPU 并行 datasweep 路径；GPU 求解路径在本开发机受平台运行时限制，\n'
  '      在赛题规定的驱动 3.9.0 + 官方镜像环境下应可沿 --enable-cuspice 路径运行。'),
]
for o, n in pairs:
    assert src.count(o) == 1, (src.count(o), o[:50])
    src = src.replace(o, n)
shutil.copy2(p, os.path.join(os.path.expanduser('~/Huangcw/backup/rc_docs_20261030'),
                             'eda260769_性能报告.txt.bak2'))
io.open(p, 'w', encoding='utf-8', newline='\n').write(src)
print('patched report (round 2)')
