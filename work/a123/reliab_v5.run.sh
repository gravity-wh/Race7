#!/bin/bash
# 修复后的 PAR 因子可靠性（v5：参数签名已修正）
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
OUT=/workspace/a123_out
cd /workspace/mp_bench/out || exit 1
TSV=$OUT/reliab5.tsv
LOG=$OUT/reliab5.log
: > $TSV; : > $LOG
printf "mat\ttrial\trc\tres\terr\tok\n" >> $TSV
say() { echo "$(date +%H:%M:%S) $*" >> $LOG; }

one() {  # $1=tag $2=mtx $3=rhs $4=trial
  local tag=$1 mtx=$2 rhs=$3 t=$4 err res rc ok=0 out attempt
  for attempt in 1 2; do
    out=$(CUDA_VISIBLE_DEVICES=${CV:-3} timeout -s TERM 300 ./mp_lu_bench_ir "$mtx" "$rhs" 0 - 0 1 2>&1)
    rc=$?
    printf '%s' "$out" | grep -q "colamd ok" && break
    say "$tag#$t attempt$attempt ENVFAIL rc=$rc"; sleep 5
  done
  res=$(printf '%s' "$out" | grep -E "^fp64 PAR:" | grep -oE "res=[0-9.eE+-]+" | cut -d= -f2)
  err=$(printf '%s' "$out" | grep -oE "singular at column [0-9]+|illegal memory access|struct[^ ]* overflow|capacity overflow" | head -1)
  [ -z "$res" ] && res=NA
  [ -z "$err" ] && err=-
  if [ "$rc" = "0" ] && [ "$res" != "NA" ]; then
    awk -v v="$res" 'BEGIN{exit !(v+0 < 1e-5)}' && ok=1
  fi
  printf "%s\t%s\t%s\t%s\t%s\t%s\n" "$tag" "$t" "$rc" "$res" "$err" "$ok" >> $TSV
  say "$tag#$t rc=$rc res=$res ok=$ok"
}

say "=== reliab5 (race-fixed) start ==="
S=/workspace/x201_paper/s0; D=/workspace/race7_code/data/s0
for t in $(seq 1 20); do one pg2k  $D/pg2k.mtx  $D/pg2k.rhs  $t; done; say "pg2k done"
for t in $(seq 1 10); do one pg5k  $D/pg5k.mtx  $D/pg5k.rhs  $t; done; say "pg5k done"
for t in $(seq 1 10); do one flash $S/sky130-flash-adc-3bit-pvt.mtx $S/sky130-flash-adc-3bit-pvt.rhs $t; done
say "=== reliab5 done ==="
