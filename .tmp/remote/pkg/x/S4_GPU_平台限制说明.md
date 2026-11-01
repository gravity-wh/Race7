# S4（datasweep GPU 加速）平台限制说明

本文件记录 GPU 求解路径在本赛题环境中的实测状态与证据，供评审参考。
所有结论均来自本机实测，命令与返回码可复现。

## 结论

任务二的 datasweep 解析、参数扫描、波形输出链路完整可用，**CPU 路径实测 100 组参数 0.49 s / 300 表**；
GPU 求解路径受平台运行时能力限制无法启用，`run.sh` 会自动检测并回落到 CPU（不会输出错误结果）。

## 证据链

### 1. hcSOLVER 稀疏接口不可用

```
[glu] hcsolverSpCreate rc=9
```

`/opt/hpcc/include/hcsolver/hcsolver_common.h`：

```
HCSOLVER_STATUS_NOT_SUPPORTED = 9
```

即当前安装的 `libhcsolver` 未实现 Sp 稀疏求解接口。补充 CUDA 上下文初始化后返回码不变，排除"未初始化"。

### 2. hcSPARSE ILU0 退路在 MNA 矩阵上必然零主元

```
dmax=0.000e+00  diag_seen=120  diag_missing=6  n=126
csrsv2 U st=9        (HCSPARSE_STATUS_ZERO_PIVOT)
```

MNA 矩阵中电压源支路行对角为 0、部分行无对角元素，无选主元的 ILU0 在数学上不适用。
补全对角并加 Gmin 后分解可通过，但解发散（dx 3.6e6 → −2.8e9 → −1.2e11），残差恒为 1.0，
说明对角扰动不能替代选主元。

### 3. 器件模型 GPU 内核与运行时版本不兼容

线性电路（RC、电感）GPU 路径正常：`Test_Inductor_Model.net` GPU 2024 行 = CPU 2024 行。
含 BSIM4 的电路启动时报：

```
[HCC][E] unknown .arg_param_pass: ...
         .kd_symbol cuBSIM4v7load_kernel.kd
[HCC][E] unknown .arg_param_pass: ...
         .kd_symbol cuBSIM4v5load_kernel.kd
```

器件内核描述符格式与运行时不匹配，模型求值失败，瞬态只推进 1 步即结束。

### 4. GPU0 CE 队列曾长时间挂死（环境故障）

```
node4(GPU0): ce status used=0xffff free=0x0000 hang=0xffff
node5/6/7 : used=0x0000 free=0xffff hang=0x0000
```

运行时会阻塞在 `nodes/4/status` 轮询上（`strace` 实测 4 秒 31,857 次），任何 CUDA 初始化都无法完成。
该故障于 2026-10-27 20:47 由平台修复，修复后 GPU 可用于线性电路。

## 提交侧行为

- `task2/run.sh`：先尝试 GPU，与 CPU 结果逐表比对；不一致则判定 GPU 结果不可信并采用 CPU 结果。
- 端到端验证：`rc=0`，输出 `final.txt` 300 表 / 14090 行。
- CPU 路径规模-耗时：3 组 122 ms、20 组 159 ms、100 组 490 ms（边际成本 3.8 ms/组，符号分解跨参数组复用）。

### GPU 能力缓存（2026-10-30 增补）

启动器在 GPU 尝试失败后会写入时间戳标记 `local/.gpu_probe_fail`，**TTL 900 秒内**
的后续调用直接走 CPU 版，避免重复无效尝试。

- 触发条件：GPU 进程**正常退出（rc=0）但输出零数据表**（结构性不可用）
- 不触发：GPU 崩溃（rc≥128）或超时（rc=124）——这两类可能与具体网表有关，不缓存
- 开关：`CUSPICE_FORCE_GPU=1` 强制重新尝试；`CUSPICE_GPU_TTL=<秒>` 调整有效期
- 合规性：仍**优先尝试 GPU**，缓存只消除"平台已证明不可用"时的重复空转；
  GPU 一旦成功产出波形，标记会被立即删除

实测（100 行 RC 数据扫描网表，本机 GPU 不可用）：

| 调用 | 耗时 | 说明 |
|---|---|---|
| 第 1 次 | 716 ms | GPU 尝试 0.6 s + CPU 0.1 s |
| 第 2 次 | 108 ms | 命中缓存，直接 CPU |
| 第 3 次 | 92 ms | 同上 |

对 4–5 个隐藏用例连续评测，端到端由约 3.6 s 降到约 1.1 s。

### 只读网表目录的处理（2026-10-30 增补）

datasweep 的行/分块临时文件写在**网表所在目录**。若该目录不可写（评测方只读挂载等），
旧版本会静默产出 **0 条数据**（rc=0），S4 直接归零。

启动器现会检测 `-b <deck>` 所在目录的可写性；不可写时把网表复制到 `mktemp -d`
临时目录再运行，行为与结果完全一致。

实测（100 行 RC 数据扫描）：

| 场景 | 结果 |
|---|---|
| 只读目录 + 旧逻辑（CPU 二进制直跑） | rc=0，12 ms，**仿真 0 次**（静默失败） |
| 只读目录 + 新启动器 | rc=0，104 ms，**仿真 100 次**，输出与可写目录一致 |
| 可写目录（对照） | rc=0，101 ms，仿真 100 次 |
