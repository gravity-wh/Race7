#!/bin/bash
# build_spmv_x201.sh — 在容器内编译 mp_spmv_bench_x201（cu-bridge 路径）
set -e
export HPCC_PATH=/opt/hpcc
export PATH=$HPCC_PATH/bin:$HPCC_PATH/htgpu_llvm/bin:$PATH
export LD_LIBRARY_PATH=$HPCC_PATH/lib:$LD_LIBRARY_PATH

cd /workspace/x201_paper
echo "=== 编译器 ==="
$HPCC_PATH/tools/cu-bridge/bin/cucc --version 2>&1 | head -3 || true

echo "=== 编译 ==="
$HPCC_PATH/tools/cu-bridge/bin/cucc -O3 -std=c++14 \
  -o mp_spmv_bench_x201 mp_spmv_bench_x201.cu 2>&1 | head -40
echo "EXIT=$?"
ls -la mp_spmv_bench_x201 2>/dev/null && md5sum mp_spmv_bench_x201
