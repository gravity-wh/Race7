#!/bin/bash
# 修复后重测 A1/A2/A3 中依赖并行因子的项
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
OUT=/workspace/a123_out/postfix
mkdir -p $OUT
cd /workspace/mp_bench/out || exit 1
S=/workspace/x201_paper/s0; D=/workspace/race7_code/data/s0
run() {  # tag mtx rhs
  local tag=$1 m=$2 r=$3 i
  for i in 1 2 3; do
    CUDA_VISIBLE_DEVICES=${CV:-3} DSH_IR=1 DSH_ST_REPS=1 \
      timeout -s TERM 900 ./mp_lu_bench_ir "$m" "$r" 0 - 15000 2 > $OUT/$tag.a$i.log 2>&1
    grep -q "JSON:" $OUT/$tag.a$i.log && { echo "$tag OK (attempt $i)"; return 0; }
    echo "$tag attempt$i 失败，重试"
  done
  echo "$tag FAILED"
}
echo "=== postfix start $(date +%H:%M:%S) ==="
run sky130_bandgap $S/sky130-bandgap-reference-pvt.mtx $S/sky130-bandgap-reference-pvt.rhs
run sky130_flash   $S/sky130-flash-adc-3bit-pvt.mtx     $S/sky130-flash-adc-3bit-pvt.rhs
run pg2k           $D/pg2k.mtx                          $D/pg2k.rhs
run pg5k           $D/pg5k.mtx                          $D/pg5k.rhs
echo "=== postfix done $(date +%H:%M:%S) ==="
