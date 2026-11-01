set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
cd /workspace/mp_bench/out || exit 1
D=/workspace/race7_code/data/s0
echo "=== 单进程 pg10k（DSH_SKIP_PAR=1）$(date +%H:%M:%S) ==="
CUDA_VISIBLE_DEVICES=0 DSH_IR=1 DSH_SKIP_PAR=1 DSH_ST_REPS=1 timeout -s TERM 900 ./mp_lu_bench_ir $D/pg10k.mtx $D/pg10k.rhs 0 - 15000 2 2>&1 | tail -5
echo "rc=${PIPESTATUS[0]}"
