#!/bin/bash
# 交付包全套自检（只读检查 + 输出定向到 /tmp，不污染包）
set -u
P=$HOME/Huangcw/presubmission_eda260769
export LD_LIBRARY_PATH=/opt/hpcc/lib:/opt/hpcc/htgpu_llvm/lib
cd /tmp || exit 1

echo "### GPU 占用进程数"
ht-smi --show-all-process 2>/dev/null | grep -cE '^\| *[0-9]' || echo 0

echo "### A. verify_golden.sh cpu"
bash "$P/task2/verify_golden.sh" cpu 2>&1 | tail -3

echo "### B. task2/run.sh  (S4_FORCE=cpu, 输出到 /tmp/ds_out)"
rm -rf /tmp/ds_out
S4_FORCE=cpu bash "$P/task2/run.sh" "" /tmp/ds_out 2>&1 | tail -6
echo "final.txt 表数: $(grep -c '^Index' /tmp/ds_out/final.txt 2>/dev/null)"
echo "final.txt 行数: $(wc -l < /tmp/ds_out/final.txt 2>/dev/null)"

echo "### C. task1 13 矩阵回归（每矩阵 90s 超时）"
MD=$HOME/PublicCase/GLU_public/src/matrix
pass=0; fail=0; to=0
for m in "$MD"/*.mtx; do
  n=$(basename "$m")
  o=$(timeout -s TERM 90 bash "$P/task1/run.sh" "$m" 2>&1)
  rc=$?
  r=$(printf '%s' "$o" | grep -oE 'RESIDUAL = [0-9.eE+-]+|RESIDUAL = nan' | head -1)
  t=$(printf '%s' "$o" | grep -oE 'RL factor[^)]*\)|Total[^|]*ms' | head -1)
  if [ $rc -eq 124 ]; then to=$((to+1)); st=TIMEOUT
  elif printf '%s' "$r" | grep -qi nan; then fail=$((fail+1)); st=NaN
  elif [ -z "$r" ]; then fail=$((fail+1)); st=NORESID
  else pass=$((pass+1)); st=OK
  fi
  printf '%-24s %-8s %-28s %s\n' "$n" "$st" "${r:-none}" "${t:-}"
done
echo "task1 汇总: PASS=$pass FAIL=$fail TIMEOUT=$to"

echo "### D. 入口哈希一致性"
sha256sum "$P/task1/bin/test_lu_gpu" "$P/task1/GLU_public/src/test_lu_gpu" \
          "$P/task1/GLU_public/src/lu_cmd" 2>&1
