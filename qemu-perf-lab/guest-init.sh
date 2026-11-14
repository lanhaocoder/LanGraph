#!/bin/busybox sh
# 按 get_ftrace.sh 原生语义生成 langraph/ 输出目录：
#   -o langraph（脚本默认输出名）、-p 1（perf 与 ftrace 同时采）
# 产出 ftrace.log / ftrace_format.log / ftrace_symbol.log / perf.log / perf.data，
# 并入运行时 kallsyms，整体回传宿主机压缩归档。
/bin/busybox --install -s /bin 2>/dev/null
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mount -t tracefs tracefs /sys/kernel/tracing 2>/dev/null
mkdir -p /sys/kernel/debug
mount -t debugfs nodev /sys/kernel/debug 2>/dev/null
[ -d /sys/kernel/debug/tracing ] || { mkdir -p /sys/kernel/debug/tracing; mount -t tracefs tracefs /sys/kernel/debug/tracing 2>/dev/null; }
export LD_LIBRARY_PATH=/lib:/lib64:/opt/lib
export PATH=/bin:/usr/bin:/sbin:/usr/sbin

echo "########## GUEST BOOTED: $(uname -r) ##########"
echo "[cmd] addr2line: $(which addr2line 2>/dev/null || echo 缺失)  perf: $(which perf 2>/dev/null || echo 缺失)"

echo "[net] insmod e1000"
insmod /modules/e1000.ko
sleep 2
ifconfig eth0 10.0.2.15 netmask 255.255.255.0 up
route add default gw 10.0.2.2 2>/dev/null

# 符号表放独立目录：get_ftrace.sh 会把 output 目录挂成 tmpfs，
# 提前放进去的文件会被隐藏，因此放在 /ks，脚本结束后再并入 langraph/
echo "[ks] 导出运行时符号表（nokaslr，地址固定）"
echo 0 > /proc/sys/kernel/kptr_restrict 2>/dev/null
mkdir -p /ks
cp /proc/kallsyms /ks/kallsyms.txt
cp /proc/modules  /ks/modules.txt
cp /proc/version  /ks/version.txt
echo "[ks] kallsyms=$(wc -l < /ks/kallsyms.txt) 行, modules=$(wc -l < /ks/modules.txt) 个"

# Guest 侧 iperf3 server，供宿主机经 hostfwd 发起 20 流双向流量
iperf3 -s -p 5201 -D 2>/dev/null || iperf3 -s -p 5201 >/dev/null 2>&1 &
sleep 2

mkdir -p /work
cd /work
echo "[capture] get_ftrace.sh -t 20 -p 1 -z 0 -o langraph   (perf + ftrace 同时)"
sh /get_ftrace.sh -t 20 -p 1 -z 0 -o langraph > /capture.log 2>&1 &
CPID=$!

wait $CPID
echo "[capture] 脚本结束，rc=$?"
sleep 12   # perf record 是 sleep(t+5)，等 perf.data 写完

cd /work/langraph
echo "[fix] 脚本 save_perf 早于 perf record 结束，重新生成完整 perf.log"
perf script -F comm,pid,tid,cpu,flags,time,event,ip,sym,dso,trace,symoff,dso,ipc > perf.log.new 2>/dev/null
if [ -s perf.log.new ]; then mv perf.log.new perf.log; else rm -f perf.log.new; fi
wc -l perf.log
cd /work

echo "[pack] 并入符号表 / 采集日志"
cp /ks/kallsyms.txt /ks/modules.txt /ks/version.txt langraph/
cp /capture.log langraph/capture.log
echo "[pack] langraph/ 内容:"
ls -lh langraph/ | sed 's/^/    /'

echo "[export] 回传 langraph/ (tar 未压缩，压缩在宿主机侧做，TCG 下更快)"
tar cf /tmp/result.tar -C /work langraph
echo "[export] tar=$(wc -c < /tmp/result.tar) bytes"
cat /tmp/result.tar | nc 10.0.2.2 9999 && echo "[export] push OK" || echo "[export] push FAILED"

# 兜底：起 httpd 供宿主机经 hostfwd 拉取
cd /work
cp /tmp/result.tar /work/result.tar
httpd -p 8080 -h /work 2>/dev/null &
sleep 5
echo "########## GUEST DONE ##########"
poweroff -f
