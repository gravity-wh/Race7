#!/bin/bash
# B2 误差棒：每个矩阵重复 N 次，逐次保存原始 JSON
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
OUT=/workspace/b2_out
mkdir -p $OUT
cd /workspace/mp_bench/out || exit 1
S=/workspace/x201_paper/s0; D=/workspace/race7_code/data/s0
N=${N:-10}
run_n() {  # tag mtx rhs
  local tag=$1 m=$2 r=$3 i
  : > $OUT/$tag.jsonl
  for i in $(seq 1 $N); do
    CUDA_VISIBLE_DEVICES=${CV:-3} DSH_IR=1 DSH_ST_REPS=1 \
      timeout -s TERM 900 ./mp_lu_bench_ir "$m" "$r" 0 - 15000 2 \
      | grep -E "^JSON:" >> $OUT/$tag.jsonl
    echo "$tag $i/$(($(grep -c "" $OUT/$tag.jsonl))) $(date +%H:%M:%S)" >> $OUT/progress.log
  done
}
echo "=== b2 start $(date +%H:%M:%S) N=$N ===" > $OUT/progress.log
run_n sky130_flash $S/sky130-flash-adc-3bit-pvt.mtx $S/sky130-flash-adc-3bit-pvt.rhs
run_n pg2k $D/pg2k.mtx $D/pg2k.rhs
run_n pg5k $D/pg5k.mtx $D/pg5k.rhs
echo "=== b2 done $(date +%H:%M:%S) ===" >> $OUT/progress.log
