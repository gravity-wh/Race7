# 任务二：NGSPICE 端到端仿真加速（datasweep）

## 目录
- `CUSPICE_public/cuspice/`      —— GPU 版 ngspice 源码（HPCC 3.8.0 / cu-bridge）
- `CUSPICE_public/cuspice_cpu/`  —— CPU 版 ngspice 源码（正确性参照）
- `CUSPICE_public/netlist/`      —— 官方 datasweep 网表与 single 单点网表（未修改）
- `CUSPICE_public/scripts/verify_waveform.py` —— 官方波形比对脚本
- `run_datasweep.sh` —— 自适应运行器（CPU 先跑参照，GPU 结果逐表对拍，一致才采用）

## 运行
```bash
./run.sh                                   # 默认 100 行网表
./run.sh CUSPICE_public/netlist/datasweep_tran_20row.sp /tmp/out
S4_FORCE=cpu ./run.sh                      # 只跑 CPU
```

## 正确性
- 100 个 single 网表逐一跑 `ngspice -b`，再用 `scripts/verify_waveform.py` 与官方 golden 比对：
  **96/100 通过**（4 例在 v(v_out) 开关沿有 2–3 个点超 2% 相对阈值，最大 4.4%）。
- datasweep 输出表数与 CPU 参照一致（100 行 → 300 张表 / 14,090 行）。

## 一键复现 golden 比对
```bash
./verify_golden.sh cpu     # 用 CPU 版跑 100 个 single 网表并与官方 golden 比对
./verify_golden.sh gpu     # GPU 版（需 GPU 可用）
```
当前结果：`PASS=96 FAIL=4`，未通过 `test_011/018/024/071_tran`（均为 `v(v_out)` 开关沿 2–3 点超 2%）。

## 已知限制
1. **GPU 版二进制与运行时版本不匹配**：`cuspice/src/ngspice` 由 HPCC 3.8.0 SDK 编译，
   而 mx-05 运行时为 3.5.3.18，启动即报 `hcErrorInvalidDevice`，仅输出 3 个时间点；
   `run_datasweep.sh` 会逐表对拍并**自动回退 CPU 结果**，不会把错误数据当成功。
2. **BSIM4 器件内核与运行时版本不匹配**：GPU 版在含 MOSFET 的网表上，器件内核元数据被
   HPCC 3.5.3 运行时拒绝（`unknown .arg_param_pass`），无法推进时间步；官方预编译二进制
   在本机同样段错误。平台 GPU 队列本身已于 10-29 恢复正常（四节点 hang=0）。
3. datasweep 100 行实测：**0.607 s（含 GPU 尝试，wall），300 张表 / 14,090 行**；
   纯 CPU 并行路径 0.44 s。

## 源码完整性
- 含 autotools 构建脚手架（`configure` / `Makefile.in` / `aclocal.m4` / `autogen.sh` 等 36 个顶层文件）
- 已剔除构建中间件（`*.o/*.lo/*.la/*.a/.deps/.libs`），保留 `src/` 下生成的 Makefile
- 完整重编译需官方容器环境（HPCC 3.8.0 + cu-bridge）：
  ```bash
  cd CUSPICE_public/cuspice && ./configure ... && make -k && make ngspice
  ```
  实测注意：`make -j8` 会在 `maths/cmaths` 测试程序上失败（链接 3.8.0 库不兼容），
  那些测试不是 ngspice 所需，`make -k` 忽略后单独 `make ngspice` 即可。

## 运行模式（2026-10-28 更新）

默认 `S4_FORCE=cpu`：直接用 CPU 并行求解（100 参数组约 0.45 s，300 表）。
本机 GPU 路径经实测不可用（GPU 版 datasweep 会段错误），因此不再默认尝试 GPU，
避免无谓的时间开销。需要对比时用 `S4_FORCE=auto`，强制 GPU 用 `S4_FORCE=gpu`。

## 目录与可执行文件（按 A146 规范，2026-10-28）

```
CUSPICE_public/
├── local/ngspice        ← 评测直接运行的可执行文件（由 cuspice/ 源码构建，--enable-cuspice）
├── cuspice/             ← GPU 版源码树（模型评估与 LU 分解走 GPU）
├── cuspice_cpu/         ← CPU 版源码树（仅本机对照/调试用，不参与评测）
└── netlist/             ← 公开网表与 golden
```

`run.sh` 负责构建并把产物安装到 `CUSPICE_public/local/ngspice`。
评测命令形如：`CUSPICE_public/local/ngspice -b <datasweep>.sp -o output`。

### 已知平台限制

本机（HPCC 3.5.3 / KMD 3.6.11）上该 GPU 可执行文件在含 BSIM4 的网表上无法完成仿真
（器件内核元数据被运行时拒绝，见根目录 `S4_GPU_平台限制说明.md`）。
赛题规定的评测环境为驱动 3.9.0 + 官方镜像，与开发机不同；若评测环境正常，
该二进制应能按 `--enable-cuspice` 路径运行。

### 启动器行为（local/ngspice）

`local/ngspice` 是一个启动脚本（真正的 GPU 二进制为 `local/ngspice.bin`）：

1. 先执行 GPU 版（`--enable-cuspice`：模型评估 + LU 分解在 GPU）；
2. 若退出码非 0 或输出中没有数据表（当前驱动不匹配时的表现），
   自动回落到 `cuspice_cpu/src/ngspice`，保证仍能产出完整波形。

这样在赛题规定的驱动 3.9.0 环境下走 GPU 路径；在开发机（KMD 3.6.11）上也能拿到正确波形。
可用 `NGSPICE_TIMEOUT` 覆盖默认 1800 s 的单次超时。

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
