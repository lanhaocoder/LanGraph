#!/bin/bash
# 按 get_ftrace.sh 原生语义生成 langraph/ 产物，并压缩归档
# Guest: -o langraph -p 1 (perf + ftrace 同时) -z 0
# Host : 20 并行流双向 iperf 负载 + 接收回传 + pigz 压缩
set -u
OUT=/workspace/langraph-native-out
mkdir -p "$OUT"
rm -f "$OUT/result.tar" "$OUT/result.tar.wget" "$OUT/langraph.tar.gz"

pkill -f 'nc -l 9999' 2>/dev/null || true
sleep 1

echo "[host] 启动 nc 接收端 :9999"
timeout 1500 nc -l 9999 > "$OUT/result.tar" 2>/dev/null &
NPID=$!
sleep 1

echo "[host] 构建 initramfs"
cp "$OUT/guest-init.sh" /tmp/guest/init
chmod +x /tmp/guest/init
( cd /tmp/guest && find . | cpio -o -H newc -R root:root 2>/dev/null | gzip -9 > /tmp/initramfs_langraph.cpio.gz )
echo "       initramfs: $(ls -lh /tmp/initramfs_langraph.cpio.gz | awk '{print $5}')"

echo "[qemu] 启动 Guest (TCG, 4 vCPU / 2G, nokaslr)"
timeout 1500 qemu-system-x86_64 \
    -m 2048 -smp 4 \
    -kernel /tmp/vmlinuz \
    -initrd /tmp/initramfs_langraph.cpio.gz \
    -append "console=ttyS0 rdinit=/init panic=-1 nokaslr" \
    -netdev user,id=net0,hostfwd=tcp:127.0.0.1:15201-:5201,hostfwd=tcp:127.0.0.1:18080-:8080 \
    -device e1000,netdev=net0 \
    -nographic -accel tcg -no-reboot -monitor none \
    > "$OUT/qemu.log" 2>&1 &
QPID=$!

echo "[host] 等 Guest 侧 iperf3 server (127.0.0.1:15201)"
OK=0
for i in $(seq 1 240); do
    if nc -z 127.0.0.1 15201 2>/dev/null; then OK=1; break; fi
    kill -0 "$QPID" 2>/dev/null || break
    sleep 1
done
echo "[host] Guest server 可达: $OK"

if [ "$OK" = 1 ]; then
    echo "[host] 20 并行流双向 iperf: iperf3 -P 20 --bidir -t 15"
    iperf3 -c 127.0.0.1 -p 15201 -P 20 --bidir -t 15 -J > "$OUT/host_to_guest.json" 2>&1
    echo "[host] 压测结束 (rc=$?)"
fi

echo "[host] 等待 langraph/ 回传"
for i in $(seq 1 400); do
    [ -s "$OUT/result.tar" ] && break
    wget -q -O "$OUT/result.tar.wget" "http://127.0.0.1:18080/result.tar" 2>/dev/null
    if [ -s "$OUT/result.tar.wget" ]; then mv "$OUT/result.tar.wget" "$OUT/result.tar"; echo "[host] 经 httpd 取回"; break; fi
    kill -0 "$QPID" 2>/dev/null || { sleep 3; break; }
    sleep 2
done

wait "$QPID" 2>/dev/null
echo "[qemu] 已退出"
kill "$NPID" 2>/dev/null || true

if [ ! -s "$OUT/result.tar" ]; then
    echo "[ERROR] 未收到回传文件"
    exit 1
fi

echo "[host] 解包 langraph/"
rm -rf "$OUT/langraph"
tar xf "$OUT/result.tar" -C "$OUT"
echo "[host] langraph/ 内容:"
ls -lh "$OUT/langraph" | sed 's/^/    /'

echo "[host] 压缩归档 (pigz -9, 多线程)"
cd "$OUT"
tar cf - langraph | pigz -9 > langraph.tar.gz
echo "[host] langraph.tar.gz: $(ls -lh langraph.tar.gz | awk '{print $5}')"
echo "[host] 归档内容:"
tar tzf langraph.tar.gz | sed 's/^/    /'
