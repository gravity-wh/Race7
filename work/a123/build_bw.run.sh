#!/bin/bash
set -u
HPCC_PATH=/opt/hpcc
CUCC=$HPCC_PATH/tools/cu-bridge/bin/cucc
LIBS="-L$HPCC_PATH/lib -Wl,-rpath,$HPCC_PATH/lib -lhcruntime -lhccompiler -lsymbol_cu -lm"
cd /workspace/mp_bench/out || exit 1
rm -f ./bw_probe
$CUCC -O3 -offload-arch native -w -I$HPCC_PATH/tools/cu-bridge/include \
  -o bw_probe /workspace/bw_probe.cu $LIBS 2>&1 | tail -10
[ -x ./bw_probe ] && echo "BUILD_OK $(stat -c%s ./bw_probe)" || { echo BUILD_FAILED; exit 3; }
