set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
cd /workspace/mp_bench/out || exit 1
M=/workspace/race7_code/data/s0/pg2k
echo "=== 旧二进制 ==="
CUDA_VISIBLE_DEVICES=2 stdbuf -o0 -e0 timeout -s TERM 120 ./mp_lu_bench $M.mtx $M.rhs 0 - 0 1 > /tmp/o1.txt 2>&1
echo "rc=$?"; tail -4 /tmp/o1.txt
echo "=== 新二进制 ==="
CUDA_VISIBLE_DEVICES=2 stdbuf -o0 -e0 timeout -s TERM 120 ./mp_lu_bench_ir $M.mtx $M.rhs 0 - 0 1 > /tmp/o2.txt 2>&1
echo "rc=$?"; tail -8 /tmp/o2.txt
