#!/bin/bash
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
export PATH=/opt/hpcc/bin:/opt/htdriver/bin:$PATH
OUT=/workspace/a123_out
cd /workspace/mp_bench/out || exit 1
TSV=$OUT/reliab2.tsv
: > $TSV
printf "mat\ttrial\trc\tres\terr\tok\n" >> $TSV
say() { echo "$@" >> $OUT/reliab2.log; }
say "=== reliab2 (race-fixed) start $(date +%H:%M:%S) ==="
one() {
  local tag=$1 f=$2 t=$3 err res rc ok=0
  out=$(CUDA_VISIBLE_DEVICES=2 timeout -s TERM 300 ./mp_lu_bench_ir "$f.mtx" "$f.rhs" 0 - 0 1 2>&1)
  rc=$?
  res=$(printf '%s' "$out" | grep -E "^fp64 PAR:" | grep -oE "res=[0-9.eE+-]+" | cut -d= -f2)
  err=$(printf '%s' "$out" | grep -oE "singular at column [0-9]+|illegal memory access|struct[^ ]* overflow|capacity overflow" | head -1)
  [ -z "$res" ] && res=NA
  [ -z "$err" ] && err=-
  if [ "$rc" = "0" ] && [ "$res" != "NA" ]; then
    awk -v v="$res" 'BEGIN{exit !(v+0 < 1e-5)}' && ok=1
  fi
  printf "%s\t%s\t%s\t%s\t%s\t%s\n" "$tag" "$t" "$rc" "$res" "$err" "$ok" >> $TSV
}
for t in $(seq 1 20); do one pg2k /workspace/race7_code/data/s0/pg2k $t; done
say "pg2k done $(date +%H:%M:%S)"
for t in $(seq 1 10); do one pg5k /workspace/race7_code/data/s0/pg5k $t; done
say "pg5k done $(date +%H:%M:%S)"
for t in $(seq 1 10); do one flash /workspace/x201_paper/s0/sky130-flash-adc-3bit-pvt $t; done
say "=== reliab2 done $(date +%H:%M:%S) ==="
