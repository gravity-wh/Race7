#!/bin/bash
# mp_stability_run.sh — 混精端到端加速比（1.08× 这类数）的重复性/稳定性实验
#
# 目的：给「fp32 因子端到端 1.083×」这类结论打误差棒，判定它是否可写进文章。
#
# 用法（容器内）:
#   bash /workspace/gpu_probe/mp_stability_run.sh [REPEATS] [mat...]
#   默认: REPEATS=10  mat=pg2k
# 环境变量:
#   CV            指定卡号（默认 2）
#   REBUILD=1     强制重编
#   OUTDIR        覆盖输出目录
#   PER_RUN_SEC   单轮墙钟上限（默认 600，卡死时不至于等 30 分钟）
#   MAX_ATTEMPT   总尝试次数上限（默认 REPEATS*2，失败重试不占有效轮次）
#
# 产物:
#   $OUTDIR/stab_<时间戳>.jsonl   每行 = 一次有效运行（原始 JSON + 挂钟 + 目标卡占用快照）
#   $OUTDIR/stab_<时间戳>.log     人读日志
#   $OUTDIR/fail_*.raw            失败轮次的完整输出（事后查因）
#
# 判读口径（写文章用）:
#   - CV ≤ 0.5% 且 95%CI 半宽 ≤ 0.5% → 可写单点数 "1.08×（±0.01）"
#   - CV 0.5%~3%                     → 只能写区间 "[1.05, 1.11]"
#   - CV > 3%                        → 抖动主导，单点数不可用，必须报区间 + 机理
#
# 注意（本机实测）: 这是共享机器，队友的 ngspice 会在任意时刻抢卡，
# 抢卡后 mp_lu_bench 直接 rc=1 或挂在首次 launch。所以每轮都记录目标卡的
# 占用与进程名，用于事后剔除被污染轮次。

set -u
export HPCC_PATH=/opt/hpcc
export PATH=$HPCC_PATH/bin:$HPCC_PATH/htgpu_llvm/bin:$HPCC_PATH/tools/cu-bridge/bin:/opt/htdriver/bin:$PATH
export LD_LIBRARY_PATH=$HPCC_PATH/lib:$HPCC_PATH/htgpu_llvm/lib:/opt/htdriver/lib:${LD_LIBRARY_PATH:-}
export CUCC_PATH=$HPCC_PATH/tools/cu-bridge
export CU_BRIDGE_PATH=$HPCC_PATH/tools/cu-bridge
export HTCC_PATH=$HPCC_PATH/htgpu_llvm/bin/htcc
export CUBRIDGE_HOME=$HOME
export CUDA_VISIBLE_DEVICES=${CV:-2}

CUCC=$HPCC_PATH/tools/cu-bridge/bin/cucc
ROOT=/workspace/race7_code
SOL=$ROOT/src/solver
MPB=$SOL/mp_bench
CUSI=/workspace/CUSPICE_public/cuspice/src/include
CUSRC=$(dirname "$CUSI")
S0=$ROOT/data/s0
EXTRA=/workspace/mp_data
OUTDIR=${OUTDIR:-/workspace/mp_bench/out}
INC="-I$SOL -I$CUSI -I$HPCC_PATH/tools/cu-bridge/include"
LIBS="-L$HPCC_PATH/lib -Wl,-rpath,$HPCC_PATH/lib -lhcruntime -lhccompiler -lsymbol_cu -lhcblas -lhcsparse -lm"

REPEATS=${1:-10}; shift || true
MATS="${*:-pg2k}"
PER_RUN_SEC=${PER_RUN_SEC:-600}
MAX_ATTEMPT=${MAX_ATTEMPT:-$((REPEATS*2))}

mkdir -p "$OUTDIR"; cd "$OUTDIR" || exit 1
TS=$(date +%Y%m%d_%H%M%S)
JSONL=$OUTDIR/stab_$TS.jsonl
LOG=$OUTDIR/stab_$TS.log
: > "$JSONL"; : > "$LOG"

say() { echo "$@" | tee -a "$LOG"; }

HTSMI=$(command -v ht-smi || echo /opt/htdriver/bin/ht-smi)

# 目标卡的 util 与进程名（用于剔除被队友污染轮次）
gpu_util() {
  [ -x "$HTSMI" ] || { echo "NA"; return; }
  "$HTSMI" 2>/dev/null | awk -F'|' -v c="$1" '$2 ~ ("^ *" c " +Mars") {gsub(/ /,"",$5); print $5}' | head -1
}
gpu_procs() {
  [ -x "$HTSMI" ] || { echo ""; return; }
  "$HTSMI" 2>/dev/null | awk -F'|' -v c="$1" '$2 ~ ("^ *" c " +[0-9]+ ") {gsub(/^ +| +$/,"",$2); n=split($2,a,/ +/); print a[3]}' \
    | sort | uniq -c | awk '{printf "%s×%s ", $1, $2}'
}

say "### mp_stability_run  TS=$TS  CV=$CUDA_VISIBLE_DEVICES  REPEATS=$REPEATS  MATS=$MATS  HOST=$(hostname)  PER_RUN_SEC=$PER_RUN_SEC"

# ---------- [0] 二进制 ----------
BIN=$OUTDIR/mp_lu_bench
if [ "${REBUILD:-0}" = "1" ] || [ ! -x "$BIN" ]; then
  say "### [0] 编译 mp_lu_bench"
  [ -f colamd.o ]        || gcc -O2 -w -c $CUSRC/maths/KLU/colamd.c        -o colamd.o        -I$CUSI 2>&1 | tail -3
  [ -f colamd_global.o ] || gcc -O2 -w -c $CUSRC/maths/KLU/colamd_global.c -o colamd_global.o -I$CUSI 2>&1 | tail -3
  [ -f cpu_ref_lu.o ]    || gcc -O2 -w -c $SOL/cpu_ref_lu.c                -o cpu_ref_lu.o    -I$SOL -I$CUSI 2>&1 | tail -3
  if [ -f "$MPB/mp_lu_bench.cu" ]; then
    $CUCC -O3 -offload-arch native -w $INC -o mp_lu_bench $MPB/mp_lu_bench.cu \
          colamd.o colamd_global.o cpu_ref_lu.o $LIBS 2>&1 | tail -8
  else
    say "!! 找不到 $MPB/mp_lu_bench.cu —— 源码已随容器回收丢失，需要先恢复"
    exit 3
  fi
  [ -x ./mp_lu_bench ] || { say "COMPILE_FAILED"; exit 3; }
fi
BINMD5=$(md5sum "$BIN" | cut -d' ' -f1)
say "### bin=$BIN  size=$(stat -c%s "$BIN")  md5=${BINMD5:0:12}"

# ---------- [1] 设备快照 ----------
say "### [1] 设备状态  target=GPU$CUDA_VISIBLE_DEVICES  util=$(gpu_util "$CUDA_VISIBLE_DEVICES")  procs=$(gpu_procs "$CUDA_VISIBLE_DEVICES")"

# ---------- [2] 重复运行 ----------
for m in $MATS; do
  MF=$S0/$m.mtx; RF=$S0/$m.rhs; FLT=""
  [ -f "$MF" ] || { MF=$EXTRA/$m.mtx; RF=$EXTRA/$m.rhs; }
  [ -f "$S0/$m.flt" ] && FLT=$S0/$m.flt
  if [ ! -f "$MF" ]; then say "SKIP $m (no data)"; continue; fi
  say "### [2] $m  mtx=$MF  rhs=$RF  flt=${FLT:-<none>}"

  valid=0; attempt=0; fail=0
  while [ "$valid" -lt "$REPEATS" ] && [ "$attempt" -lt "$MAX_ATTEMPT" ]; do
    attempt=$((attempt+1))
    U0=$(gpu_util "$CUDA_VISIBLE_DEVICES"); P0=$(gpu_procs "$CUDA_VISIBLE_DEVICES")
    t0=$(date +%s.%N)
    RAW=$(timeout "$PER_RUN_SEC" ./mp_lu_bench "$MF" "$RF" 0 $FLT 2>&1)
    rc=$?
    t1=$(date +%s.%N)
    wall=$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.3f", b-a}')
    U1=$(gpu_util "$CUDA_VISIBLE_DEVICES"); P1=$(gpu_procs "$CUDA_VISIBLE_DEVICES")
    JS=$(printf '%s\n' "$RAW" | grep -m1 '^JSON:')

    if [ -z "$JS" ] || [ "$rc" -ne 0 ]; then
      fail=$((fail+1))
      RAWOUT=$OUTDIR/fail_${TS}_a${attempt}.raw
      printf '%s\n' "$RAW" > "$RAWOUT"
      say "  attempt#$attempt  rc=$rc  wall=${wall}s  INVALID (util ${U0}->${U1}, procs ${P1:-none})  raw=$RAWOUT"
      continue
    fi

    valid=$((valid+1))
    printf '{"mat":"%s","run":%d,"attempt":%d,"rc":%d,"wall_s":%s,"bin_md5":"%s","cv":"%s","util_before":"%s","util_after":"%s","procs_before":"%s","procs_after":"%s","json":%s}\n' \
      "$m" "$valid" "$attempt" "$rc" "$wall" "$BINMD5" "$CUDA_VISIBLE_DEVICES" \
      "$U0" "$U1" "$P0" "$P1" "${JS#JSON:}" >> "$JSONL"
    say "  run#$valid (attempt $attempt)  rc=$rc  wall=${wall}s  util ${U0}->${U1}  ${JS#JSON: }"
  done
  say "### $m: 有效 $valid/$REPEATS，共尝试 $attempt 次，失败 $fail 次"
done

say "### JSONL=$JSONL"
say "### LOG=$LOG"
echo "PYJSON=$JSONL"
