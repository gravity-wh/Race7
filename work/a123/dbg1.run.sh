set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
cd /workspace/mp_bench/out || exit 1
ls -l mp_lu_bench_ir mp_lu_bench
echo "=== 直接运行 ==="
CUDA_VISIBLE_DEVICES=2 ./mp_lu_bench_ir /workspace/race7_code/data/s0/pg2k.mtx /workspace/race7_code/data/s0/pg2k.rhs 0 - 0 1 2>&1 | head -20
echo "PIPESTATUS=${PIPESTATUS[0]}"
