#!/bin/bash
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
export PATH=/opt/htdriver/bin:$PATH
cd /workspace/mp_bench/out || exit 1
D=/workspace/race7_code/data/s0
OUT=/workspace/a4_out
mkdir -p $OUT
for m in pg2k pg5k; do
  echo "=== $m: 采样期间放大 reps=20 ==="
  ( for i in $(seq 1 40); do ht-smi --show-hbm-bandwidth 2>/dev/null | awk -v m="$m" '/GPU#3/{f=1} f&&/throughput/{print m"\t"$3; f=0}'; sleep 0.5; done > $OUT/bw_${m}.tsv ) &
  SP=$!
  CUDA_VISIBLE_DEVICES=3 timeout -s TERM 300 ./mp_lu_bench_ir $D/$m.mtx $D/$m.rhs 0 - 0 20 2>&1 | grep -E "^fp64 PAR" 
  wait $SP
  echo "--- $m 采样统计（MB/s）---"
  awk '{s+=$2; n++; if($2>mx)mx=$2} END{if(n)printf "  n=%d mean=%.1f max=%.1f\n", n, s/n, mx}' $OUT/bw_${m}.tsv
done
