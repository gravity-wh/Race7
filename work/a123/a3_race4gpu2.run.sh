#!/bin/bash
# A3：修复前二进制在 4 卡并发下的错误率（对比单卡基线 50%/70%）
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
OUT=/workspace/a4_out
mkdir -p $OUT
cd /workspace/mp_bench/out || exit 1
BIN=${BIN:-./mp_lu_bench}
D=/workspace/race7_code/data/s0
TSV=$OUT/race4_${TAG}.tsv
: > $TSV
printf "mat\tround\tgpu\trc\tres\terr\n" >> $TSV

one() {  # mat round gpu
  local m=$1 r=$2 g=$3 log=$OUT/race_${TAG}_${m}_r${r}_g${g}.log rc res err
  CUDA_VISIBLE_DEVICES=$g timeout -s TERM 120 $BIN $D/$m.mtx $D/$m.rhs 0 - 0 1 > $log 2>&1
  rc=$?
  res=$(grep -E "^fp64 PAR:" $log | grep -oE "res=[0-9.eE+-]+" | cut -d= -f2)
  err=$(grep -oE "singular at column [0-9]+|illegal memory access" $log | head -1)
  [ -z "$res" ] && res=NA; [ -z "$err" ] && err=-
  printf "%s\t%s\t%s\t%s\t%s\t%s\n" "$m" "$r" "$g" "$rc" "$res" "$err" >> $TSV
}

echo "=== A3 start $(date +%H:%M:%S)  bin=$(md5sum $BIN | cut -c1-12) tag=${TAG} ===" > $OUT/race4_${TAG}.log
for m in pg2k pg5k; do
  for r in $(seq 1 10); do
    for g in 0 1 2 3; do one $m $r $g & done
    wait
    echo "  $m round $r done $(date +%H:%M:%S)" >> $OUT/race4_${TAG}.log
  done
done
echo "=== A3 done $(date +%H:%M:%S) ===" >> $OUT/race4_${TAG}.log
