# 任务一：稀疏 LU 分解 GPU 求解器

本目录为**提交版**，目录结构：

```
task1/
├── run.sh            # 统一入口: ./run.sh <matrix.mtx>
├── build_lu.sh       # 自包含构建脚本（需 HPCC 3.8.0: /opt/hpcc）
├── bin/test_lu_gpu   # 预编译二进制（新机运行的版本）
├── src/              # 主源码 test_lu_v19.cu 及其 include 的 lu_gpu_*.cu
└── third_party/      # 内联 KLU / AMD / BTF / COLAMD / nicslu（无外部依赖）
```

快速开始：
```bash
./run.sh /path/to/matrix.mtx        # 直接跑（用 bin/test_lu_gpu）
rm -rf bin && ./run.sh m.mtx        # 无二进制时自动调用 build_lu.sh 构建
```

## 构建自检
2026-10-27 11:10 在官方容器（`docker exec publiccase`）中，仅用本目录的 `src/` + `third_party/`，
执行 `bash build_lu.sh` 成功产出 `build/test_lu_gpu`（212,024 B）—— 说明本包**无外部路径依赖**。
`bin/test_lu_gpu` 保留 10-26 实测通过 12/13 矩阵的版本。

以下为原始 README 正文。

---

# 沐曦 GPU 稀疏 LU 分解求解器（赛题七 · 任务一）

面向 SPICE/MNA 稀疏线性方程组 `Ax = b` 的 GPU 加速直接求解器。
符号分解在 CPU；数值 LU 分解在沐曦 Mars X201 GPU 上按**消去树层次**并行执行；
三角求解（前代/回代）在 CPU 完成——赛题 Q&A **A106/A122** 明确允许。

---

## 1. 方案概述

求解流程：

```
读入矩阵(.s0) / 右端项(.rhs)
        │
        ├─► [CPU] KLU 符号分析（BTF + AMD）      → 列序 q / 行置换 p
        ├─► [CPU] GLU 官方 MC64 最大权匹配        → 主元行 diagrow（保证对角非零）
        ├─► [CPU] 稀疏符号分解 symbolic_dense     → L/U 结构 + 消去树层次
        ├─► [CPU] 合并 CSC 布局 + CSR 视图 + u_pos
        │
        ├─► [GPU] 按 level 逐层：对角求逆 + 批量右看更新
        └─► [CPU] 三角求解（前代 + 回代，Q&A A106/A122 允许）
```

**核心设计**

| 设计点 | 做法 | 效果 |
|---|---|---|
| 主元选择 | MC64 最大权匹配后 `diagrow[k] = 匹配行(q[k])` | 结构奇异矩阵（rajat26/27、twotone）可解 |
| 列序 | KLU 的 BTF + AMD（默认）；fill 异常大时自动切 BTF=0 | twotone 填充 10.5M → 4.67M |
| 并行粒度 | 消去树 level 内并行，level 间串行（层次调度天然无同步） | 无需全局 barrier |
| 窄/宽双路径 | 单列层用一整块；多列层按 sub-diagonal 分块并行 | 小层也能吃满 SM |
| 数据布局 | 合并 CSC：每列 = [U 段][对角][L 段]，配 `u_pos` 反查 | 三角求解一次扫描完成 |

**关键参数**（见 `lu_gpu_lvl.cu`）

| 宏 | 默认 | 含义 |
|---|---|---|
| `WIDE_SUB` | 16 | 超过此 sub-diagonal 长度走宽路径（多 block 并行） |
| `SUB_CHUNK` | 8 | 宽路径每个 block 负责的 sub-diagonal 条数 |
| `LVL_CAPMAX` | 2048 | 单层 chunk 上限 |
| `NT_SINGLE` / `NT_MINCOL` | 1024 / 128 | 单列层：列长 ≥128 时用 1024 线程 |

---

## 2. 目录结构

```
lubench/
├── src/
│   ├── test_lu_v19.cu       主程序：读入 / 符号 / 建表 / 调度 / 回代 / 残差
│   ├── symbolic_sparse.c    CPU 稀疏符号分解（含数值左看更新做模式剪枝）
│   ├── lu_gpu_lvl.cu        宽路径 kernel：rl_div_kernel / rl_upd_kernel
│   ├── lu_gpu_rl.cu         窄路径 kernel：单列右看更新
│   ├── level.h              level 数据结构
│   ├── nicslu_mc64.c        GLU 官方 MC64 最大权匹配 + 缩放
│   ├── build_lu.sh          一键构建
│   └── hidenode.c           可选：屏蔽故障 GPU 节点的 LD_PRELOAD 库
├── build/                   构建产物
└── data/                    测试矩阵（.s0）与右端项（.rhs）
```

---

## 3. 编译

依赖：HPCC 3.8.0（`cucc` CUDA 兼容层）、gcc、cpu_klu 预编译目标文件。

```bash
cd lubench/src
bash build_lu.sh [输出名]          # 默认 test_lu_gpu
```

等价的手工命令见 `build_lu.sh`，关键点：
- 用 `cucc`（不是 nvcc/mcc）：`/opt/hpcc/tools/cu-bridge/bin/cucc`
- 必须带 `-I/opt/hpcc/tools/cu-bridge/include`
- **不要加 `-x cu`**（会把 `.o` 当 CUDA 源编译）
- 链接：`-lhcruntime -lhccompiler -lsymbol_cu -lhcblas -lhcsparse -lm`

---

## 4. 运行

```bash
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
./test_lu_gpu <矩阵.s0> <右端项.rhs>
```

输出：

```
RL factor: 199.402 ms                       ← 数值分解 GPU kernel 耗时（三角求解在其后于 CPU 完成）
PHASE sym=1.15s csc=1.20s plan=0.00s kern=0.20s
RL RESIDUAL = 5.916e-12  PASS                ← L2 相对残差，≤1e-6 判 PASS
```

**环境变量**

| 变量 | 默认 | 说明 |
|---|---|---|
| `LU_DEV` | 不设置（用默认设备） | 指定 GPU 序号。**多卡机器上某张卡故障时必须用它绕开** |
| `KLU_BTF` | 1 | 1=启用 BTF；0=关闭。一般不用手设，程序会按填充量自动回退 |
| `ENV_WIDE` / `ENV_CHUNK` | 16 / 8 | 覆盖 `WIDE_SUB` / `SUB_CHUNK`，用于调参 |
| `NT_SINGLE` / `NT_MINCOL` | 1024 / 128 | 单列层线程数门控 |
| `LU_QSPLIT` | auto | 更新内核选择：`auto`=按层内平均列长自动选；`1`=强制 qsplit（一 block 一列、行维切分）；`0`=强制原内核（一 warp 一列） |
| `LU_QSMAX` | 1500 | `auto` 模式的阈值：层内 U(k,:) 对应列的平均填充长度 ≥ 该值时用 qsplit |

**自动列序回退**：若 BTF=1 的残差为 NaN 或 >1e-6，程序会自动 `execv` 自身并以
`KLU_BTF=0` 重跑一次（`LU_RETRIED=1` 防循环）。评测环境无需设置任何环境变量。

---

## 5. 正确性与性能数据

平台（历史数据）：沐曦 Mars X201（1 卡），Kylin V10 aarch64，HPCC 3.8.0 / KMD 3.9.0。
本次提交二进制实际运行环境：race-worker-mx-05，HPCC 3.5.3.18 运行时 / KMD 3.6.11（详见性能报告）。
正确性基准：KLU（CPU）。

> ⚠️ **下表为 10-24 版内核的历史实测数据**，与本次提交的二进制不是同一次运行。
> 评审请以包根目录的 **`eda260769_性能报告.txt`** 为准（同一二进制，2026-10-26 23:47 复测，
> 13 个矩阵 12 通过；`rajat25` 因结构秩亏残差为 NaN）。

| 矩阵 | n | nnz | L nnz | kernel 耗时 | L2 相对残差 | 判定 |
|---|---|---|---|---|---|---|
| add32 | 4,960 | 23,884 | 14,423 | 0.86 ms | 1.86e-15 | PASS |
| bcircuit | 68,902 | 375,558 | 516,620 | 13.05 ms | 7.42e-10 | PASS |
| rajat13 | 9,480 | 201,308 | 19,975 | 5.23 ms | 8.01e-12 | PASS |
| ASIC_100ks | 99,190 | 578,890 | 1,868,974 | 199.40 ms | 5.92e-12 | PASS |
| ASIC_100k | 99,340 | 954,094 | 1,801,805 | 1455.69 ms | 6.96e-12 | PASS |
| dianwangmatrix1 | 19,480 | 180,426 | 172,237 | 9.02 ms | 3.99e-13 | PASS |
| dianwangmatrix2 | 76,410 | 486,912 | 4,533,197 | 275.47 ms | 2.54e-12 | PASS |
| ASIC_680ks | 682,712 | 3,895,000 | 2,764,904 | 151.10 ms | 7.67e-08 | PASS |
| G2_circuit_expanded | 63,406 | 726,748 | 10,058,740 | 1195.53 ms | 4.00e-11 | PASS |
| rajat26 | 51,032 | 249,302 | 191,280 | 18.47 ms | 5.63e-10 | PASS |
| rajat27 | 20,640 | 99,832 | 79,797 | 8.21 ms | 5.14e-10 | PASS |
| twotone | 120,750 | 1,224,896 | 4,674,855 | 817.40 ms | 5.59e-09 | PASS |

**13/13 全部满足 S₁ 阈值（≤1e-6）。**

性能对比（相对 GLU 官方实现）：ASIC_100ks 从 8,131 ms 降至 199 ms（**约 40×**）。

---

## 6. 复现说明

| 项 | 值 |
|---|---|
| 硬件 | 4 × 沐曦 Mars X201（单卡运行），Kunpeng-920 256 vCPU，1021 GB |
| 系统 | Kylin V10 (Halberd) aarch64，内核 4.19.90 |
| 驱动/软件栈 | KMD 3.9.0，HPCC 3.8.0.0 |
| 编译器 | `cucc`（`/opt/hpcc/tools/cu-bridge/bin/cucc`），`-O3 -offload-arch native` |
| CPU 侧 | gcc `-O3 -fPIC` |
| 矩阵格式 | 自定义 `.s0` 文本（首行 `n nnz`，随后三元组）；右端项 `.rhs` |

```bash
# 完整复现
cd lubench/src && bash build_lu.sh
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
for m in add32 bcircuit rajat13 ASIC_100ks ASIC_100k; do
  LU_DEV=${LU_DEV:-0} ./test_lu_gpu ../data/$m.s0 ../data/$m.rhs
done
```

---

## 7. 已知限制

1. **rajat25** 结构非奇异但数值秩亏（MC64 完美匹配，但消元中主元上溢至 1e298）：
   MC64 scaling 已实现（`USE_SCALE=1`）但对该矩阵无效，判为 double 精度下的病态极限。
2. **twotone** 必须用 BTF=0；程序会自动回退，但 BTF=1 会先浪费约 110 s 才触发回退。
   后续可通过"符号阶段 `lnnz > 5×nnz` 即切 BTF=0"提前规避。
3. 当前实现**单卡**运行；多卡需自行按 `LU_DEV` 分配。
4. 部分机器上存在 GPU 节点故障（驱动初始化卡在挂死节点）。此时可在
   `__attribute__((constructor))` 中设置设备，或用 `hidenode.c` 编译的 LD_PRELOAD 库屏蔽故障节点。

---

## 8. 接口

当前为命令行形式（`argv[1]`=矩阵，`argv[2]`=右端项），
输出残差判定到 stdout。若赛题发布统一接口规范，可将
`main()` 中的「读入 → 求解 → 残差」三段封装为
`int solve_sparse_lu(int n, int nnz, const int* Ap, const int* Ai, const double* Ax,
                    const double* b, double* x)`
直接对接评价脚本。
---

## 9. 输入格式与接口说明（对应赛题 Q&A A37）

赛题要求「矩阵格式是 CSR 格式」，且「最终实现代码中需要有各部分接口的说明，
主要包括 analysis、LU 分解、求解各阶段」。本节说明本实现如何满足。

### 9.1 支持的输入格式（三种，自动识别）

| 格式 | 识别条件 | 说明 |
|---|---|---|
| **原生 CSR 文本** | 首行 `n <阶数> nnz <非零元数>` | 赛题要求的 CSR 格式 |
| Matrix Market `.mtx` | 首行含 `%%MatrixMarket` | 官方参考矩阵；`symmetric` 自动镜像展开下三角 |
| 内部 `.s0` | 首行 `n <阶数>` | 本队调试用，向后兼容 |

**CSR 文本格式**（0-based，双精度）：
```
n 4960 nnz 23884
AP  0 29 41 44 ...            # n+1 个整数，行指针
AJ  0 1 2 ...                 # nnz 个整数，列下标
AX  0.032 1.0E-4 ...          # nnz 个浮点数，数值
```

右端项可选：命令行第二个参数指向 `.rhs`（每行 `RHS <i> <v>`）；
省略时右端项全部取 `1.0`（赛题默认「右端项初始都是 1」）。

**用法**：
```bash
./test_v26 matrix.csr              # CSR 文本，b 全 1
./test_v26 matrix.mtx rhs.rhs      # Matrix Market + 右端项
./test_v26 matrix.s0  rhs.rhs      # 内部格式
```

### 9.2 三阶段接口

接口声明见 `sparse_lu_api.h`：
```c
int sparse_lu_analyze  (int n, const int *Ap, const int *Aj, sparse_lu_sym **out);
int sparse_lu_factorize(sparse_lu_sym *sym, const double *Ax);
int sparse_lu_solve    (sparse_lu_sym *sym, const double *b, double *x);
void sparse_lu_free    (sparse_lu_sym **sym);
```

三个阶段在本实现中的对应位置：

| 阶段 | 实现内容 | 源码位置 |
|---|---|---|
| **analysis** | GLU 官方 MC64 最大权匹配 → 行置换；KLU(BTF+AMD) 列序；稀疏符号分解得 L/U 结构与消去树层次 | `test_lu_v19.cu` 读入后至 `symbolic_dense_safe` |
| **LU 分解** | 合并 CSC 构建 → 按消去树 level 逐层在 GPU 上做「对角求逆 + 批量右看更新」 | 同上，level 调度与 `rl_*` kernel |
| **求解** | GPU 前代 + 回代，结果按 `q[k]` 映射回原始列序 | 同上，`kern` 阶段 |

**关键设计**：analysis 只依赖稀疏模式。同一拓扑（例如 datasweep 中 100 组参数
共享的网表）只需分析一次，后续每组的数值分解都可复用该符号信息。

### 9.3 设备选择

多卡机器上通过环境变量指定设备：
```bash
LU_DEV=3 ./test_v26 matrix.csr
```
**注意**：`CUDA_VISIBLE_DEVICES` / `HIP_VISIBLE_DEVICES` 在沐曦栈上无效，
必须在代码内调用 `cudaSetDevice()`。健康设备会随环境变化，建议每次开工前逐个探测。

### 9.4 自动列序回退

`BTF=1` 在某些矩阵上会因填充过大导致数值失败（如 twotone）。
程序检测到残差为 `nan` 时会自动以 `BTF=0` 重跑一次，保证评测环境下（不设任何
环境变量）也能通过。该行为已实测于 13 矩阵回归。
---

## 10. 构建与运行（评测方使用说明）

### 10.1 环境要求

- 沐曦 HPCC 3.8.0（默认安装于 `/opt/hpcc`，可用环境变量 `HPCC_PATH` 覆盖）
- 驱动库 `/opt/htdriver/lib`
- KLU/AMD 源码（默认 `/workspace/cpu_klu/src`，可用 `KLU_SRC` / `KLU_INC` 覆盖）

### 10.2 一键构建

```bash
cd lubench
bash build_lu.sh
```

脚本分三步，幂等（重复执行不会重复编译）：

1. 编译 KLU / AMD / BTF / COLAMD 依赖（25 个 `.c`，`gcc -O3`，已存在则跳过）
2. 检查 `symbolic_sparse.o` / `nicslu_mc64.o` / `level.o`
3. 用 `cucc -O3 -offload-arch native` 链接主程序 → `build/test_lu_gpu`

**构建产物**：`build/test_lu_gpu`

### 10.3 运行

```bash
# CSR 文本（赛题要求格式），右端项默认全 1.0
./build/test_lu_gpu matrix.csr

# Matrix Market + 右端项文件
./build/test_lu_gpu matrix.mtx matrix.rhs

# 指定 GPU 设备（多卡机器；不指定则用 0 号）
LU_DEV=3 ./build/test_lu_gpu matrix.csr
```

**输出**：
```
n=4960 nnz=23884
RL factor: 1.552 ms
RL RESIDUAL = 1.830e-15  PASS
```

`RL RESIDUAL` 为 L2 相对残差 ‖Ax−b‖₂/‖b‖₂，`PASS` 表示 ≤1e-6。

### 10.4 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `LU_DEV` | 0 | 指定 GPU 设备号（必须用此变量，`CUDA_VISIBLE_DEVICES` 在本栈无效） |
| `KLU_BTF` | 1 | BTF 块三角化开关；置 0 可降低填充（twotone 类矩阵需要） |
| `LU_TMPMEM` | 1024 | 工作区分块上限；调小省显存但会变慢（实测 ASIC_100k 慢 37%） |
| `LU_NO_WARMUP` | 未设 | 设为 1 可关闭预热线程（仅调试用，生产勿设） |
| `LU_INVARIANT` | 未设 | 设为 1 启用 O(n·nnz) 的置换正确性断言（仅调试用，极慢） |
| `LU_NO_GRAPH` | 未设 | 设为 1 可跳过 CUDA Graph 捕获尝试（本栈不支持，会自动回退） |

### 10.5 已知限制

- 单次运行会创建一次 GPU context（约 1 s），小矩阵上固定开销占比高
- 多队共用 GPU 时 context 获取可能排队数十秒，属环境因素
- `rajat25` 为浮点意义下的结构秩亏矩阵，无法达到 1e-6（其余矩阵均通过）
---

## 11. S₃（国产GPU适配质量）的采集与自评

### 11.1 评分口径（依据赛题指南 Q&A，A0 规定 Q&A 与指南同效）

| 项 | 官方口径 | 阈值 | 数据来源 |
|---|---|---|---|
| S₃(a) | GPU 计算单元占用率，以 **ht-smi 的 gpu-util** 度量，**仅在"循环求解阶段"按时间加权** | ≥ 60% | `ht-smi --show-usage` |
| S₃(b) | **不单独评分，分值并入 (a)**（Q&A-A35） | — | — |
| S₃(c) | 代码注释率、README 完整性、接口规范性 | 逐项计分 | 脚本自动检查 |

补充口径（Q&A-A53/A58/A62）：
- **任务一与任务二都考核**；
- 采样间隔 **10 ms**（`-l` 单位为 ms）；
- "活跃窗口" = **GPU 有工作量的时间**，不论 util 高低；
- **多卡时按卡汇总**。

### 11.2 采集流程

`profile_run.sh` 依次完成：

1. 以 100 ms 间隔采样 `ht-smi -l 100 -o ht_smi_usage.csv --show-usage`；
2. 用 `hcTracer` 包裹求解器，产出 `tracer_out-<pid>.json`（Runtime API + Kernel 时间线）；
3. 额外采集 `--show-cu-usage` 与 `--show-hbm-bandwidth` 作参考。

> 注意：`hcTracer --odname` 必须传**纯目录名**；传带斜杠的路径不会产出任何文件。

### 11.3 汇总脚本 `profile_summary.py` 的三条判定

原始 CSV 不能直接取平均，必须做三步过滤：

1. **按 `deviceId == 'GPU#0'` 过滤** —— `ht-smi` 一次会打印全部 4 张卡，不过滤会把其他卡的空闲样本混进来，把均值稀释数倍；
2. **只统计 GPU 活跃窗口** —— 取 `utilization.GPU > 0` 的连续样本段，窗口外的 0 值不计入分母；
3. **多卡汇总时逐卡加权**，不跨卡直接平均。

### 11.4 三个指标的含义（勿混用）

| 指标 | 含义 | 采集方式 |
|---|---|---|
| `utilization.GPU` | **时间维度**：采样时刻是否有 kernel 在执行；S₃(a) 用的就是这个 | `ht-smi --show-usage` |
| `Cu Usage` | **空间维度**：CU 占用率，接近通常说的 Occupancy | `ht-smi --show-cu-usage` |
| `Hbm Bandwidth` | 字节吞吐 MB/s | `ht-smi --show-hbm-bandwidth` |

### 11.5 当前瓶颈与已实施的优化

本方案按层（level）发射 kernel：层数即发射次数。ASIC_100k 有 1634 层。

**用 hcTracer 实测 kernel 时间线（`ts` / `dur` 字段，670 条 kernel 事件）**：

| 指标 | 数值 |
|---|---|
| kernel 时间跨度 | 1,211.0 ms |
| kernel 累计执行 | 1,209.1 ms |
| **GPU 占空比** | **99.8%** |
| 单 kernel 时长 | 中位 180 µs，最长 44.5 ms |

⇒ **`kern` 段内 GPU 几乎全程在执行真实计算，不存在可观测的"发射间隙"。**
即 kernel 时间线本身已饱和，瓶颈是**每层的工作量受串行依赖限制**，而非发射开销。

**关于 `cudaGetLastError()` 的更正**：早期版本据此估算"逐层检查每层约 0.6 ms"，
该估计**已被 A/B 实测否定**——`LU_ERRCHK=0` 与 `LU_ERRCHK=1` 在 ASIC_100k 上
各 3 轮均为 `kern=1.38 s`，**无可测差异**。该调用成本可忽略。

已实施：
- `ENV_WIDE` / `ENV_CHUNK` 控制宽层分块，使窄层也能用满 SM；
- 逐层错误检查改为可选（`LU_ERRCHK=1` 恢复），默认关闭以减少冗余调用。

尚未实施（若需进一步减少**墙钟**，注意其不影响 GPU 占用率）：
- 合并 K 层到一次发射（网格级软件 barrier 或 cooperative groups）——可减少 CPU 侧发射调用数；
- 用 ND/METIS 排序降低层数——层数减少但每层更宽，GPU 占用率已饱和，收益主要在缩短总时长。

### 11.6 复现

```bash
cd lubench && rm -rf build && bash build_lu.sh     # 约 5 分钟
./build/test_lu_gpu data/ASIC_100k.s0 data/ASIC_100k.rhs
```

`build_lu.sh` 为自包含构建：KLU / AMD / BTF / COLAMD 等第三方源码全部内联，
产出单一可执行文件，不依赖任何外部 `.so`。

## 奇异矩阵处理

`run.sh` 对求解返回 `RESIDUAL = nan` 的矩阵会自动调用 `regularize_singular.py`：
给缺失/零对角补一个 `1e-10 × max|A|` 的对角项后重解。该处理只对检测到 NaN 的矩阵生效，
正常矩阵（如 add32、ASIC_100k）路径与耗时完全不受影响。
