#!/bin/bash
# run_wave_e2e.sh -- 端到端波形对比：把 100 个官方 single 网表分别用
#                    CPU 参考路径与 GPU 加速路径各跑一遍，然后三方对拍。
#
# 用法（在 race-worker-mx-05 上跑）：
#   bash code/run_wave_e2e.sh            # 全量 100 个
#   NDEV=3 bash code/run_wave_e2e.sh     # 指定并行度（默认 3，避开 GPU0）
#
# 前置：
#   - CPU 参考二进制  $CPU_BIN   （KLU 版 ngspice）
#   - GPU 加速二进制  $GPU_BIN   （自建 dense-LU 路径）
#   - 官方网表        $SINGLE/*.sp、$SINGLE_GOLDEN/*.out
#
# 产出：
#   $W/{cpu,gpu}/<case>.out        两条路径的原始输出
#   $W/cmp_{golden_cpu,golden_gpu,cpu_gpu}.csv
#   $W/gpu_adoption.tsv            GPU 内解 / 回落 KLU 的逐用例统计
#
# 说明：GPU 路径需要写到网表同目录的临时文件，且网表里写死了
#       /workspace/CUSPICE_public/... 的库路径，所以统一经 run.sh 做
#       路径改写 + 临时目录拷贝（与提交包 local/ngspice 启动器同一逻辑）。

set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")

# ---- 可覆盖的路径 ----
PKG=${PKG:-$HOME/Huangcw/presubmission_eda260769/task2/CUSPICE_public}
SINGLE=${SINGLE:-$PKG/netlist/single}
SINGLE_GOLDEN=${SINGLE_GOLDEN:-$PKG/netlist/single_golden}
CPU_BIN=${CPU_BIN:-$HOME/PublicCase/CUSPICE_public/cuspice_cpu/src/ngspice}
GPU_BIN=${GPU_BIN:-$HOME/PublicCase/_task2_gpu_work/cuspice_gpu_build/src/ngspice}
W=${W:-$HOME/PublicCase/_wv}
NDEV=${NDEV:-3}
DEVBASE=${DEVBASE:-1}      # GPU0 常被他人占用，默认从 1 开始

mkdir -p "$W" "$W/cpu" "$W/gpu"

# ---- 单次运行封装 ----
cat > "$W/run.sh" <<'INNER'
#!/bin/bash
set -u
BIN="$1"; DECK="$2"; OUT="$3"; DEV="${4:-2}"
CP=${PKG:-$HOME/Huangcw/presubmission_eda260769/task2/CUSPICE_public}
TMP=$(mktemp -d)
sed "s#/workspace/CUSPICE_public#$CP#g" "$DECK" > "$TMP/deck.sp"
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export CUDA_VISIBLE_DEVICES="$DEV"
exec "$BIN" -b "$TMP/deck.sp" -o "$OUT"
INNER
chmod +x "$W/run.sh"
export PKG

# ---- 并发跑全部用例 ----
run_all() {   # run_all <bins> <outdir> <ndev> <devbase>
    local BIN="$1" OUT="$2" ND="$3" DB="$4"
    local d i=0
    for d in $(seq 0 $((ND - 1))); do
        (
            i=0
            for f in "$SINGLE"/*_tran.sp; do
                i=$((i + 1))
                [ $(( (i - 1) % ND )) -ne "$d" ] && continue
                base=$(basename "$f" .sp)
                [ -s "$OUT/$base.out" ] && continue
                t0=$(date +%s)
                CUSPICE_GPU_LU_DEBUG=1 timeout 300 \
                    "$W/run.sh" "$BIN" "$f" "$OUT/$base.out" $((DB + d)) >/dev/null 2>&1
                rc=$?
                t1=$(date +%s)
                printf "%s\t%s\t%s\n" "$base" "$rc" "$((t1 - t0))" >> "$OUT/_timing.$d.tsv"
            done
        ) &
    done
    wait
}

echo "== CPU 参考路径（$CPU_BIN）"
run_all "$CPU_BIN" "$W/cpu" 1 9
echo "== GPU 加速路径（$GPU_BIN），${NDEV} 路并行，设备 $DEVBASE..$((DEVBASE + NDEV - 1))"
run_all "$GPU_BIN" "$W/gpu" "$NDEV" "$DEVBASE"

# ---- 三方对比 ----
cp "$SINGLE_GOLDEN"/*.out "$W/golden/" 2>/dev/null || { mkdir -p "$W/golden"; cp "$SINGLE_GOLDEN"/*.out "$W/golden/"; }
cd "$W"
echo; echo "===== golden vs CPU（基线）"
python3 "$HERE/wave_compare.py" golden cpu --csv cmp_golden_cpu.csv | tail -5
echo; echo "===== golden vs GPU（基线 + 求解器）"
python3 "$HERE/wave_compare.py" golden gpu --csv cmp_golden_gpu.csv | tail -5
echo; echo "===== CPU vs GPU（仅求解器）"
python3 "$HERE/wave_compare.py" cpu gpu --csv cmp_cpu_gpu.csv | tail -5

# ---- 采用率 ----
python3 - "$W" <<'PY' | tee gpu_adoption.tsv
import glob, os, sys
W = sys.argv[1]
print("case\tok\tunavail\trefine_div\tklu_fb\tsolves\tadopt_pct")
ok_t = s_t = 0
for f in sorted(glob.glob(W + "/gpu/*.out")):
    c = os.path.basename(f)[:-4]
    t = open(f, errors="replace").read()
    ok = t.count("GPU LU 求解成功"); un = t.count("GPU LU 不可用")
    rd = t.count("dense refine 发散"); fb = t.count("回落 KLU")
    s = ok + un; ok_t += ok; s_t += s
    print("%s\t%d\t%d\t%d\t%d\t%d\t%s" % (c, ok, un, rd, fb, s,
          ("%.2f" % (100.0 * ok / s)) if s else "NA"))
print("# overall solves=%d gpu_ok=%d adopt=%.2f%%" % (s_t, ok_t, 100.0 * ok_t / max(s_t, 1)))
PY

echo; echo "完成。CSV 在 $W/cmp_*.csv；出图：python3 code/fig_wave_e2e.py"
