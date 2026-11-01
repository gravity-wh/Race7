#!/bin/bash
# 在容器内编译 A1 版基准
set -u
HPCC_PATH=/opt/hpcc
CUSI=/workspace/CUSPICE_public/cuspice/src/include
CUSRC=/workspace/CUSPICE_public/cuspice/src
SOL=/workspace/race7_code/src/solver
MPB=$SOL/mp_bench
OUT=/workspace/mp_bench/out
CUCC=$HPCC_PATH/tools/cu-bridge/bin/cucc
KLU_LIB=/workspace/CUSPICE_public/cuspice_cpu/src/maths/KLU/.libs/libKLU.a
KLU_INC=/workspace/CUSPICE_public/cuspice_cpu/src/include
INC="-I$SOL -I$CUSI -I$KLU_INC -I$HPCC_PATH/tools/cu-bridge/include"
LIBS="-L$HPCC_PATH/lib -Wl,-rpath,$HPCC_PATH/lib -lhcruntime -lhccompiler -lsymbol_cu -lhcblas -lhcsparse -lm"
cd "$OUT" || exit 1
[ -f colamd.o ]        || gcc -O2 -w -c "$CUSRC/maths/KLU/colamd.c" -o colamd.o -I"$CUSI"
[ -f colamd_global.o ] || gcc -O2 -w -c "$CUSRC/maths/KLU/colamd_global.c" -o colamd_global.o -I"$CUSI"
[ -f cpu_ref_lu.o ]    || gcc -O2 -w -c "$SOL/cpu_ref_lu.c" -o cpu_ref_lu.o -I"$SOL" -I"$CUSI"
echo "=== compile ==="
rm -f ./mp_lu_bench_ir
$CUCC -O3 -offload-arch native -w $INC -o mp_lu_bench_ir "$MPB/mp_lu_bench_ir.cu" \
      colamd.o colamd_global.o cpu_ref_lu.o $KLU_LIB $LIBS 2>&1 | tail -25
if [ -x ./mp_lu_bench_ir ]; then
  echo "BUILD_OK $(stat -c%s ./mp_lu_bench_ir) bytes  md5=$(md5sum ./mp_lu_bench_ir | cut -c1-12)"
else
  echo "BUILD_FAILED"
  exit 3
fi
