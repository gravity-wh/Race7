# 预提交包 —— 赛题七（eda260769）

| 路径 | 内容 |
|---|---|
| `task1/` | 任务一：稀疏 LU 求解器 GPU 加速（源码 + `run.sh` + `README.md`） |
| `task2/` | 任务二：NGSPICE datasweep 加速（源码 + `run.sh` + `README.md`） |
| `eda260769_性能报告.txt` | 正确性验证与性能指标（纯文本） |

## 环境
- 平台: race-worker-mx-05，4 × 沐曦 Mars X201 (SM=104)
- 运行时: HPCC 3.5.3.18 / 驱动 3.6.11；编译: cu-bridge（HPCC 3.8.0 SDK）
- 运行前需 `export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib`

## 已知限制（如实说明）
1. **GPU 利用率**：仅 ASIC_100k 实测（29%，ht-smi 时间加权）。其余 12 个矩阵在采集窗口内
   平台 GPU3 CE 引擎队列故障（2026-10-27 08:51 起，CUDA 初始化卡在 nodes/7 轮询，
   实测 add32 由 1.4 ms 变为 >90 s 超时），无法采样。平台恢复后可用
   `tools/collect_gpu_util.sh <matrix_dir> [device]` 一次补齐，本报告随之更新。
2. **加权耗时**：按赛题评分口径（各评测矩阵得分取算术平均）以等权计算。
3. **任务二数据来自 CPU 参照路径**：GPU 版因 SDK 版本不匹配（3.8.0 编译 / 3.5.3 运行时）
   报 hcErrorInvalidDevice，已由自适应运行器判为不一致并回退 CPU。
