#!/bin/bash
# 受控对照：同一容器、同一张卡、无外部负载，旧/新二进制**交替**跑（消除时间漂移）
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
OUT=/workspace/ctrl_out
mkdir -p $OUT
cd /workspace/mp_bench/out || exit 1
D=/workspace/race7_code/data/s0
TSV=$OUT/ctrl.tsv
: > $TSV
printf "i\tbin\trc\tres\terr\n" >> $TSV
N=${N:-200}

one() {  # bin tag i
  local bin=$1
  local tag=$2
  local i=$3
  local log="$OUT/${tag}_${i}.log"
  local rc res err
  CUDA_VISIBLE_DEVICES=3 timeout -s TERM 120 $bin $D/pg5k.mtx $D/pg5k.rhs 0 - 0 1 > $log 2>&1
  rc=$?
  res=$(grep -E "^fp64 PAR:" $log | grep -oE "res=[0-9.eE+-]+" | cut -d= -f2)
  err=$(grep -oE "singular at column [0-9]+|illegal memory access" $log | head -1)
  [ -z "$res" ] && res=NA; [ -z "$err" ] && err=-
  printf "%s\t%s\t%s\t%s\t%s\n" "$i" "$tag" "$rc" "$res" "$err" >> $TSV
  rm -f $log
}

echo "=== ctrl start $(date +%H:%M:%S) N=$N ===" > $OUT/ctrl.log
for i in $(seq 1 $N); do
  one ./mp_lu_bench    old $i
  one ./mp_lu_bench_ir new $i
  [ $((i % 20)) -eq 0 ] && echo "  $i/$(($N)) $(date +%H:%M:%S)" >> $OUT/ctrl.log
done
echo "=== ctrl done $(date +%H:%M:%S) ===" >> $OUT/ctrl.log
