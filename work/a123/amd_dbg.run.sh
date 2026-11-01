set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
cd /workspace/mp_bench/out || exit 1
D=/workspace/race7_code/data/s0
CUDA_VISIBLE_DEVICES=3 DSH_ORDER=amd_ata timeout -s TERM 300 ./mp_lu_bench_ir $D/pg2k.mtx $D/pg2k.rhs 0 - 0 1 2>&1 | head -12
echo "rc=${PIPESTATUS[0]}"
