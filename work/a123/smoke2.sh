#!/bin/bash
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
export PATH=/opt/hpcc/bin:/opt/htdriver/bin:$PATH
echo "=== 我的进程 ==="; ps -u $(id -u) -o pid,etime,args | grep -E "mp_lu_bench|ngspice" | grep -v grep | head
echo "=== GPU 进程 ==="; ht-smi --show-all-process 2>/dev/null | head -12
cd /workspace/mp_bench/out || exit 1
D=/workspace/x201_paper/s0
m=sky130-flash-adc-3bit-pvt
echo "===== $m (IR only, max_n_st=15000, reps=1) ====="
time CUDA_VISIBLE_DEVICES=2 DSH_IR=1 DSH_IR_TOL=1e-10 DSH_IR_MAXIT=20 \
  timeout -s TERM 180 ./mp_lu_bench_ir $D/$m.mtx $D/$m.rhs 0 - 15000 1 2>&1 | grep -E "^(n=|CPU ref|fp64|fp32|JSON)|IR"
echo "rc=$?"
