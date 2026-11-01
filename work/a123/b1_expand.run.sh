#!/bin/bash
# B1：扩到 5 矩阵 × 20 次（pg10k ×10），4 路并发，每路固定一张卡
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
OUT=/workspace/b1_out
mkdir -p $OUT
cd /workspace/mp_bench/out || exit 1
S=/workspace/x201_paper/s0; D=/workspace/race7_code/data/s0

# 任务表：id mat mtx rhs extra
J=$OUT/jobs.txt
: > $J
n=0
for r in $(seq 1 20); do
  echo "$n sky130_bandgap $S/sky130-bandgap-reference-pvt.mtx $S/sky130-bandgap-reference-pvt.rhs" >> $J; n=$((n+1))
  echo "$n sky130_flash $S/sky130-flash-adc-3bit-pvt.mtx $S/sky130-flash-adc-3bit-pvt.rhs" >> $J; n=$((n+1))
  echo "$n pg2k $D/pg2k.mtx $D/pg2k.rhs" >> $J; n=$((n+1))
  echo "$n pg5k $D/pg5k.mtx $D/pg5k.rhs" >> $J; n=$((n+1))
done
for r in $(seq 1 10); do
  echo "$n pg10k $D/pg10k.mtx $D/pg10k.rhs skip" >> $J; n=$((n+1))
done
echo "jobs=$n" > $OUT/progress.log

next_id() {  # 原子取下一个任务
  exec 9>>$OUT/lock
  flock 9
  local last=0
  [ -f $OUT/cursor ] && last=$(cat $OUT/cursor)
  local nid=$last
  echo $((last+1)) > $OUT/cursor
  exec 9>&-
  echo $nid
}

worker() {  # $1=gpu
  local gpu=$1 id line mat mtx rhs extra
  while :; do
    id=$(next_id)
    [ "$id" -ge "$n" ] && break
    line=$(sed -n "$((id+1))p" $J)
    set -- $line
    mat=$2; mtx=$3; rhs=$4; extra=${5:-}
    local env=""
    [ "$extra" = "skip" ] && env="DSH_SKIP_PAR=1"
    env $env CUDA_VISIBLE_DEVICES=$gpu DSH_IR=1 DSH_ST_REPS=1 \
      timeout -s TERM 900 ./mp_lu_bench_ir "$mtx" "$rhs" 0 - 15000 2 > $OUT/job_${id}_${mat}.log 2>&1
    echo "$(date +%H:%M:%S) id=$id $mat gpu=$gpu rc=$?" >> $OUT/progress.log
  done
}
for g in 0 1 2 3; do worker $g & done
wait
echo "=== B1 done $(date +%H:%M:%S) ===" >> $OUT/progress.log
