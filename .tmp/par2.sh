set -u
P=$HOME/Huangcw/presubmission_eda260769
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib
cd /tmp
for j in 1 8 32 64; do
  rm -rf /tmp/par_$j
  s=$(date +%s%N)
  DS_JOBS=$j S4_FORCE=cpu bash "$P/task2/run.sh" "" /tmp/par_$j >/dev/null 2>&1
  e=$(date +%s%N)
  echo "DS_JOBS=$j  $(( (e-s)/1000000 )) ms  tables=$(grep -c '^Index' /tmp/par_$j/final.txt 2>/dev/null)"
done
echo "---DOCS---"
cd "$P" && tar czf - README.md task1/README.md task2/README.md S4_GPU_平台限制说明.md eda260769_性能报告.txt
