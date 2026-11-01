#!/bin/bash
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
export PATH=/opt/hpcc/bin:/opt/htdriver/bin:$PATH
OUT=/workspace/a123_out
cd /workspace/mp_bench/out || exit 1
D=/workspace/race7_code/data/s0
for a in 1 2; do
  echo "=== pg10k attempt$a $(date +%H:%M:%S)" >> $OUT/run.log
  CUDA_VISIBLE_DEVICES=2 DSH_IR=1 DSH_SKIP_PAR=1 DSH_ST_REPS=1 \
    timeout -s TERM 1800 ./mp_lu_bench_ir $D/pg10k.mtx $D/pg10k.rhs 0 - 15000 2 \
    > $OUT/pg10k.a$a.log 2>&1
  rc=$?
  echo "  rc=$rc $(grep -oE 'L2\(vs CPU\)=[0-9.eE+-]+' $OUT/pg10k.a$a.log | head -1)" >> $OUT/run.log
  [ $rc -eq 0 ] && break
  sleep 5
done
echo "=== pg10k DONE $(date +%H:%M:%S)" >> $OUT/run.log
