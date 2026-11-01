#!/bin/bash
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
cd /workspace/mp_bench/out || exit 1
D=/workspace/race7_code/data/s0
OUT=/workspace/a4_out
# 先跑一次热身，再在高频采样下跑 reps=20
CUDA_VISIBLE_DEVICES=3 ./mp_lu_bench_ir $D/pg2k.mtx $D/pg2k.rhs 0 - 0 1 > /dev/null 2>&1
python3 /workspace/x201_paper/lib_bw_sample.py 30 3 0.02 > $OUT/bw_lib_pg2k.txt 2>&1 &
SP=$!
sleep 2
CUDA_VISIBLE_DEVICES=3 timeout -s TERM 300 ./mp_lu_bench_ir $D/pg2k.mtx $D/pg2k.rhs 0 - 0 20 2>&1 | grep -E "^fp64 PAR"
wait $SP 2>/dev/null
echo "--- 采样（MB/s，sum 列=该卡所有 die 求和）---"
awk 'NF==6{if($6+0>0){s+=$6;n++; if($6>mx)mx=$6}} END{if(n)printf "  n=%d mean=%.1f max=%.1f MB/s\n",n,s/n,mx; else print "  no data"}' $OUT/bw_lib_pg2k.txt
