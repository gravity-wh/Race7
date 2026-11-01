#!/bin/bash
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
export PATH=/opt/hpcc/bin:/opt/htdriver/bin:$PATH
cd /workspace/mp_bench/out || exit 1
D=/workspace/x201_paper/s0
m=sky130-flash-adc-3bit-pvt
echo "===== $m 全量输出 ====="
CUDA_VISIBLE_DEVICES=2 DSH_IR=1 timeout -s TERM 180 ./mp_lu_bench_ir $D/$m.mtx $D/$m.rhs 0 - 15000 1 2>&1 | tail -15
echo "PROG_RC=${PIPESTATUS[0]}"
echo "===== 老二进制对照（同一矩阵）====="
CUDA_VISIBLE_DEVICES=2 timeout -s TERM 180 ./mp_lu_bench $D/$m.mtx $D/$m.rhs 0 - 15000 1 2>&1 | tail -8
echo "PROG_RC=${PIPESTATUS[0]}"
