#!/bin/bash
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
cd /workspace/mp_bench/out || exit 1
D=/workspace/race7_code/data/s0
for m in pg2k pg5k pg10k; do
  for o in colamd klu_amd; do
    echo "== $m  order=$o =="
    CUDA_VISIBLE_DEVICES=3 DSH_ORDER=$o timeout -s TERM 600 ./mp_lu_bench_ir $D/$m.mtx $D/$m.rhs 0 - 0 2 2>&1 \
      | grep -E "^(colamd|klu_amd) ok|^CPU ref|^fp64 PAR"
  done
done
