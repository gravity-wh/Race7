#!/bin/bash
# 等 GPU 空闲窗口再跑可靠性测试（别的队在抢卡时会 SIGBUS）
set -u
export PATH=/opt/hpcc/bin:/opt/htdriver/bin:$PATH
LOG=/workspace/a123_out/watch.log
: > $LOG
for i in $(seq 1 240); do
  busy=$(ht-smi --show-all-process 2>/dev/null | grep -cE "ngspice|t2_batch|python3")
  echo "$(date +%H:%M:%S) poll#$i busy=$busy" >> $LOG
  if [ "$busy" -eq 0 ]; then
    echo "$(date +%H:%M:%S) GPU idle -> start" >> $LOG
    bash /workspace/_reliab_v2.sh
    echo "$(date +%H:%M:%S) reliab2 done" >> $LOG
    exit 0
  fi
  sleep 60
done
echo "$(date +%H:%M:%S) TIMEOUT waiting" >> $LOG
