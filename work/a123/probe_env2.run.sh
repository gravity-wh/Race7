set -u
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib:/opt/htdriver/lib
echo "=== 容器内设备节点 ==="; ls -l /dev/htcd /dev/dri/renderD* 2>&1 | head -5
echo "=== 容器内 ht-smi ==="; ht-smi 2>&1 | head -6
echo "=== 逐卡试（老二进制, n=113）==="
cd /workspace/mp_bench/out
S=/workspace/x201_paper/s0
for d in 0 1 2 3; do
  out=$(CUDA_VISIBLE_DEVICES=$d timeout -s TERM 60 ./mp_lu_bench $S/sky130-bandgap-reference-pvt.mtx $S/sky130-bandgap-reference-pvt.rhs 0 - 15000 1 2>&1)
  rc=$?
  echo "GPU$d rc=$rc  $(printf '%s' "$out" | grep -oE 'fp64 ST: factor=[0-9.]+ ms|RESIDUAL|core|Segmentation|总线' | head -1)"
done
