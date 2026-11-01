set -u
P=$HOME/Huangcw/presubmission_eda260769
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib
cd /tmp
rm -rf /tmp/final_smoke
s=$(date +%s%N)
S4_FORCE=cpu bash "$P/task2/run.sh" "" /tmp/final_smoke 2>&1 | tail -2
e=$(date +%s%N)
echo "wall: $(( (e-s)/1000000 )) ms"
echo "tables=$(grep -c '^Index' /tmp/final_smoke/final.txt)  data_rows=$(grep -cE '^ *[-0-9]+ ' /tmp/final_smoke/final.txt)"
echo "package clean? extra files under task2/:"
ls "$P/task2"
