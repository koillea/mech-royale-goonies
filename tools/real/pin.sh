#!/bin/bash
# keep Chrome's GPU process on CPU 3 at nice 19; node + H3 on CPUs 0-2
while true; do
  for P in $(pgrep -f "type=gpu-process"); do taskset -a -p 0x8 $P >/dev/null 2>&1; renice -n 19 -p $(ls /proc/$P/task 2>/dev/null) >/dev/null 2>&1; done
  for P in $(pgrep -f "realplay2.js") $(pgrep -f "h3/bot/main.py"); do taskset -a -p 0x7 $P >/dev/null 2>&1; done
  sleep 3
done
