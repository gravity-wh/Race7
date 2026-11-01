#!/bin/bash
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
export PATH=/opt/hpcc/bin:/opt/htdriver/bin:$PATH
cd /workspace/mp_bench/out || exit 1
M=/workspace/race7_code/data/s0/pg2k
for bin in mp_lu_bench mp_lu_bench_ir; do
  echo "########## $bin （仅 PAR 段，max_n_st=0, reps=1）× 5"
  for i in 1 2 3 4 5; do
    out=$(CUDA_VISIBLE_DEVICES=2 timeout -s TERM 120 ./$bin $M.mtx $M.rhs 0 - 0 1 2>&1)
    rc=$?
    line=$(printf '%s' "$out" | grep -E "^fp64 PAR" | head -1)
    err=$(printf '%s' "$out" | grep -E "singular|overflow|FAIL" | head -1)
    printf '  run%d rc=%d  %s %s\n' "$i" "$rc" "${line:-<no line>}" "${err:+| $err}"
  done
done
