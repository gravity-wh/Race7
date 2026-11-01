#!/bin/bash
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
export PATH=/opt/hpcc/bin:/opt/htdriver/bin:$PATH
cd /workspace/mp_bench/out || exit 1
echo "=== GPU 状态 ==="; ht-smi 2>/dev/null | grep -E "Mars X201|Available" | head -8
D=/workspace/x201_paper/s0
for m in sky130-bandgap-reference-pvt sky130-flash-adc-3bit-pvt; do
  echo "===== $m ====="
  CUDA_VISIBLE_DEVICES=2 DSH_IR=1 DSH_IR_TOL=1e-10 timeout 300 ./mp_lu_bench_ir $D/$m.mtx $D/$m.rhs 0 - 15000 3 2>&1 | grep -E "^(n=|CPU ref|fp64|fp32|JSON)|IR"
done
