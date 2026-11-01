set -u
P=$HOME/Huangcw/presubmission_eda260769
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib
cd /tmp
echo "### A. run.sh (S4_FORCE=cpu) 端到端 wall x3"
for i in 1 2 3; do
  rm -rf /tmp/ds_t$i
  s=$(date +%s%N)
  S4_FORCE=cpu bash "$P/task2/run.sh" "" /tmp/ds_t$i >/dev/null 2>&1
  e=$(date +%s%N)
  echo "  run$i: $(( (e-s)/1000000 )) ms"
done
echo "### B. 纯 CPU 二进制直跑（无启动器开销）x3"
NET=$P/task2/CUSPICE_public/netlist/datasweep_tran_100row.sp
for i in 1 2 3; do
  rm -rf /tmp/cpu_t$i && mkdir -p /tmp/cpu_t$i
  sed "s|/workspace/|$HOME/PublicCase/|g" "$NET" > /tmp/cpu_t$i/net.sp
  s=$(date +%s%N)
  ( cd /tmp/cpu_t$i && "$P/task2/CUSPICE_public/cuspice_cpu/src/ngspice" -b net.sp -o out.txt >/dev/null 2>&1 )
  e=$(date +%s%N)
  echo "  cpu$i: $(( (e-s)/1000000 )) ms"
done
echo "### C. 表数/行数"
grep -c '^Index' /tmp/ds_t1/final.txt; wc -l < /tmp/ds_t1/final.txt
