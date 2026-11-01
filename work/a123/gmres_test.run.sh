#!/bin/bash
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
cd /workspace/mp_bench/out || exit 1
S=/workspace/x201_paper/s0; D=/workspace/race7_code/data/s0
echo "===== sky130_flash ====="
CUDA_VISIBLE_DEVICES=3 DSH_IR=1 DSH_GMRES=1 timeout -s TERM 600 ./mp_lu_bench_ir $S/sky130-flash-adc-3bit-pvt.mtx $S/sky130-flash-adc-3bit-pvt.rhs 0 - 15000 2 2>&1 | grep -E "^(fp32 IR|fp64 IR|gmres|fp32 PAR|fp64 PAR)"
echo "===== sky130_bandgap ====="
CUDA_VISIBLE_DEVICES=3 DSH_IR=1 DSH_GMRES=1 timeout -s TERM 600 ./mp_lu_bench_ir $S/sky130-bandgap-reference-pvt.mtx $S/sky130-bandgap-reference-pvt.rhs 0 - 15000 2 2>&1 | grep -E "^(fp32 IR|fp64 IR|gmres)"
echo "===== pg2k ====="
CUDA_VISIBLE_DEVICES=3 DSH_IR=1 DSH_GMRES=1 timeout -s TERM 900 ./mp_lu_bench_ir $D/pg2k.mtx $D/pg2k.rhs 0 - 15000 2 2>&1 | grep -E "^(fp32 IR|fp64 IR|gmres)"
