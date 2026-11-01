#!/bin/bash
# 可靠性测试 v3：每次运行前确认 GPU 空闲；环境性 SIGBUS(rc>=128 且无 colamd) 自动重试
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
export PATH=/opt/hpcc/bin:/opt/htdriver/bin:$PATH
OUT=/workspace/a123_out
cd /workspace/mp_bench/out || exit 1
TSV=$OUT/reliab3.tsv
LOG=$OUT/reliab3.log
: > $TSV; : > $LOG
printf "mat\ttrial\trc\tres\terr\tok\n" >> $TSV
say() { echo "$(date +%H:%M:%S) $*" >> $LOG; }

busy() { ht-smi --show-all-process 2>/dev/null | grep -cE "ngspice|t2_batch|python3"; }

wait_idle() {
  local i
  for i in $(seq 1 60); do
    [ "$(busy)" -eq 0 ] && { sleep 3; [ "$(busy)" -eq 0 ] && return 0; }
    sleep 20
  done
  return 1
}

one() {
  local tag=$1 f=$2 t=$3 attempt err res rc ok=0 out
  for attempt in 1 2 3 4 5; do
    wait_idle || { say "$tag#$t no idle window"; return 1; }
    out=$(CUDA_VISIBLE_DEVICES=2 timeout -s TERM 300 ./mp_lu_bench_ir "$f.mtx" "$f.rhs" 0 - 0 1 2>&1)
    rc=$?
    if [ $rc -ge 128 ] && ! printf '%s' "$out" | grep -q "colamd ok"; then
      say "$tag#$t attempt$attempt ENVFAIL rc=$rc (抢卡)，重试"
      sleep 10; continue
    fi
    break
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

say "=== reliab3 (race-fixed) start ==="
for t in $(seq 1 20); do one pg2k /workspace/race7_code/data/s0/pg2k $t; done
say "pg2k done"
for t in $(seq 1 10); do one pg5k /workspace/race7_code/data/s0/pg5k $t; done
say "pg5k done"
for t in $(seq 1 10); do one flash /workspace/x201_paper/s0/sky130-flash-adc-3bit-pvt $t; done
say "=== reliab3 done ==="
