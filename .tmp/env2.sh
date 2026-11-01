set -u
P=$HOME/Huangcw/presubmission_eda260769
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib
echo "### load"; uptime; echo "nproc=$(nproc)"
echo "### 当前其它用户进程数"; ps -eo user= | sort | uniq -c | sort -rn | head -5
echo "### 串行基线 DS_JOBS=1"
cd /tmp; rm -rf /tmp/ds_serial
NET=$P/task2/CUSPICE_public/netlist/datasweep_tran_100row.sp
s=$(date +%s%N)
DS_JOBS=1 S4_FORCE=cpu bash "$P/task2/run.sh" "" /tmp/ds_serial >/dev/null 2>&1
e=$(date +%s%N)
echo "serial: $(( (e-s)/1000000 )) ms  tables=$(grep -c '^Index' /tmp/ds_serial/final.txt)"
