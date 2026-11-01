#!/bin/bash
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
export PATH=/opt/hpcc/bin:/opt/htdriver/bin:$PATH
cd /workspace/mp_bench/out || exit 1
D=/workspace/x201_paper/s0
for m in sky130-bandgap-reference-pvt sky130-flash-adc-3bit-pvt; do
  echo "===== $m ====="
  CUDA_VISIBLE_DEVICES=2 DSH_IR=1 timeout -s TERM 240 ./mp_lu_bench_ir $D/$m.mtx $D/$m.rhs 0 - 15000 2 2>&1 | grep -E "^(fp32 IR|fp64 IR|fp64 PAR|fp32 PAR|fp64 ST|fp32 ST)"
  echo "rc=${PIPESTATUS[0]}"
done
echo "===== pg2k ====="
M=/workspace/race7_code/data/s0/pg2k
CUDA_VISIBLE_DEVICES=2 DSH_IR=1 timeout -s TERM 600 ./mp_lu_bench_ir $M.mtx $M.rhs 0 - 15000 2 2>&1 | grep -E "^(fp32 IR|fp64 IR|fp64 PAR|fp32 PAR|CPU ref)"
echo "rc=${PIPESTATUS[0]}"
