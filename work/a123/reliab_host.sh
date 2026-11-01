#!/bin/bash
# 宿主机侧门禁：ht-smi 能看到所有队的进程；空闲才进容器跑一次
set -u
OUT=$HOME/PublicCase/a123_out
TSV=$OUT/reliab3.tsv
LOG=$OUT/reliab3.log
: > $TSV; : > $LOG
printf "mat\ttrial\trc\tres\terr\tok\n" >> $TSV
say() { echo "$(date +%H:%M:%S) $*" >> $LOG; }
busy() { ht-smi --show-all-process 2>/dev/null | grep -cE "ngspice|t2_batch|python3|mp_lu"; }

wait_idle() {
  local i
  for i in $(seq 1 90); do
    if [ "$(busy)" -eq 0 ]; then sleep 5; [ "$(busy)" -eq 0 ] && return 0; fi
    sleep 20
  done
  return 1
}

one() {
  local tag=$1 mtx=$2 rhs=$3 t=$4 attempt out rc res err ok=0
  for attempt in 1 2 3; do
    wait_idle || { say "$tag#$t 无空闲窗口，跳过"; return 1; }
    out=$(docker exec publiccase bash -lc "cd /workspace/mp_bench/out && CUDA_VISIBLE_DEVICES=2 timeout -s TERM 300 ./mp_lu_bench_ir $mtx $rhs 0 - 0 1" 2>&1)
    rc=$?
    printf '%s' "$out" | grep -q "colamd ok" && break
    say "$tag#$t attempt$attempt ENVFAIL rc=$rc，重试"; sleep 15
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

say "=== reliab3(host-gated) start busy=$(busy) ==="
S=/workspace/x201_paper/s0
D=/workspace/race7_code/data/s0
for t in $(seq 1 20); do one pg2k $D/pg2k.mtx $D/pg2k.rhs $t; done
say "pg2k done"
for t in $(seq 1 10); do one pg5k $D/pg5k.mtx $D/pg5k.rhs $t; done
say "pg5k done"
for t in $(seq 1 10); do one flash $S/sky130-flash-adc-3bit-pvt.mtx $S/sky130-flash-adc-3bit-pvt.rhs $t; done
say "=== reliab3 done ==="
