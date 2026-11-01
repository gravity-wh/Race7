set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
cd /workspace/mp_bench/out
S=/workspace/x201_paper/s0
echo "=== 1) 老二进制 + 极小矩阵（ST 路径，无并行因子）==="
CUDA_VISIBLE_DEVICES=2 timeout -s TERM 60 ./mp_lu_bench $S/sky130-bandgap-reference-pvt.mtx $S/sky130-bandgap-reference-pvt.rhs 0 - 15000 1 2>&1 | tail -6
echo "rc=${PIPESTATUS[0]}"
echo "=== 2) 设备查询 ==="
CUDA_VISIBLE_DEVICES=2 timeout -s TERM 30 ./mp_lu_bench 2>&1 | head -3
echo "rc=${PIPESTATUS[0]}"
echo "=== 3) dmesg 末尾（权限内）==="
dmesg 2>/dev/null | tail -5 || echo "no dmesg"
