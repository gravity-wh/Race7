#!/bin/bash
# A1/A2/A3 扫描：每个矩阵最多 3 次尝试，成功即停（PAR 因子存在非确定性失败）
set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
export PATH=/opt/hpcc/bin:/opt/htdriver/bin:$PATH
OUT=/workspace/a123_out
mkdir -p $OUT
cd /workspace/mp_bench/out || exit 1
LOG=$OUT/run.log
: > $LOG

run_one() {  # $1=tag  $2=mtx  $3=rhs  $4=attempt
  local tag=$1 m=$2 r=$3 a=$4
  local o=$OUT/${tag}.a${a}.log
  CUDA_VISIBLE_DEVICES=${CV:-2} DSH_IR=1 DSH_ST_REPS=1 \
    timeout -s TERM 900 ./mp_lu_bench_ir "$m" "$r" 0 - 15000 2 > "$o" 2>&1
  local rc=$?
  # 成功判据：rc=0 且 fp64 PAR 残差 < 1e-5（若该段存在）
  local res64
  res64=$(grep -oE "L2\(vs CPU\)=[0-9.eE+-]+ res=[0-9.eE+-]+" "$o" | head -1)
  echo "  attempt$a rc=$rc $res64" >> $LOG
  if [ $rc -eq 0 ]; then
    local pr
    pr=$(grep -E "^fp64 PAR" "$o" | grep -oE "res=[0-9.eE+-]+" | cut -d= -f2)
    if [ -n "$pr" ]; then
      awk -v v="$pr" 'BEGIN{exit !(v+0 < 1e-5 && v+0 == v+0)}' && return 0
    else
      return 0
    fi
  fi
  return 1
}

mat() {  # $1=tag $2=dir $3=name
  local tag=$1 d=$2 n=$3
  echo "=== $tag  $(date +%H:%M:%S)" >> $LOG
  for a in 1 2 3; do
    if run_one "$tag" "$d/$n.mtx" "$d/$n.rhs" "$a"; then
      echo "  => $tag OK (attempt $a)" >> $LOG
      return 0
    fi
    sleep 3
  done
  echo "  => $tag FAILED 3 attempts" >> $LOG
}

S=/workspace/x201_paper/s0
D=/workspace/race7_code/data/s0
mat sky130_bandgap $S sky130-bandgap-reference-pvt
mat sky130_flash   $S sky130-flash-adc-3bit-pvt
for p in pg2k pg5k pg10k pg25k pg50k; do mat $p $D $p; done
echo "=== ALL DONE $(date +%H:%M:%S)" >> $LOG
