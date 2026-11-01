#!/bin/bash
# A1 并发扩展：同一矩阵，1/2/4 个实例分别在 1/2/4 张卡上同时跑
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
OUT=/workspace/a4_out
mkdir -p $OUT
cd /workspace/mp_bench/out || exit 1
D=/workspace/race7_code/data/s0

run_set() {  # $1=mat $2=ninst $3=round
  local m=$1 n=$2 r=$3 i gpu
  local t0 t1
  t0=$(date +%s%N)
  for i in $(seq 0 $((n-1))); do
    case $n in
      1) gpu=3 ;;
      2) gpu=$((2 + i)) ;;
      4) gpu=$i ;;
    esac
    ( CUDA_VISIBLE_DEVICES=$gpu timeout -s TERM 600 ./mp_lu_bench_ir $D/$m.mtx $D/$m.rhs 0 - 0 3 \
        > $OUT/${m}_n${n}_r${r}_i${i}.log 2>&1 ) &
  done
  wait
  t1=$(date +%s%N)
  echo "$m n=$n round=$r wall_ms=$(( (t1-t0)/1000000 ))" >> $OUT/wall.log
}

echo "=== A1 start $(date +%H:%M:%S) ===" > $OUT/wall.log
# 预热
CUDA_VISIBLE_DEVICES=3 ./mp_lu_bench_ir $D/pg2k.mtx $D/pg2k.rhs 0 - 0 1 > /dev/null 2>&1
for m in pg2k pg5k; do
  for n in 1 2 4; do
    for r in 1 2 3; do
      run_set $m $n $r
      echo "  done $m n=$n r=$r $(date +%H:%M:%S)" >> $OUT/wall.log
    done
  done
done
echo "=== A1 done $(date +%H:%M:%S) ===" >> $OUT/wall.log
