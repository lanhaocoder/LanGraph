# QEMU 下的 LanGraph 采集验证（配套实验归档）

本目录是独立实验工程 https://github.com/lanhaocoder/langraph-qemu-perf-lab 的产物镜像。
主工程 `LanGraph` 的源码与构建方式不受影响；完整脚本、报告、两轮压测日志都在独立工程里。

## 背景

云沙箱宿主机上 `perf_event_open` 返回 `EPERM`、无法挂载 tracefs/debugfs，
因此用 **QEMU 8.2.2 TCG**（无 KVM，纯软件模拟）启动一个最小 Guest
（Ubuntu `6.8.0-31-generic` 内核 + busybox initramfs + `e1000` 网卡），
借 Guest 自带内核的 tracefs 跑通 `get_ftrace.sh`。

## 这轮做了什么

```bash
# Guest 内，脚本未做任何修改
sh /get_ftrace.sh -t 20 -p 1 -z 0 -o langraph
```

- `-p 1`：**perf 与 ftrace 同时采集**
- `-o langraph`：脚本默认输出目录名，产物为 `langraph/`
- QEMU `-append` 加 `nokaslr`，内核基址固定
- 负载：宿主机 `iperf3 -P 20 --bidir -t 15`（40 条流，双向）

`capture.log` 里 `start perf capture` 与 `start ftrace capture` 都在。

## 归档内容

`langraph.tar.gz` **9.23 MB**（原始 204 MB，压缩率 4.5%，`gzip -t` 通过），
`tar xzf langraph.tar.gz` 解压得到 `langraph/`：

| 文件 | 规模 | 说明 |
|---|---|---|
| `perf.data` | 12.23 MB | 原始采样，63,828 个 `cpu-clock` 采样 |
| `perf.log` | 60.29 MB / 1,141,976 行 | `perf script` 符号化文本 |
| `ftrace.log` | 122.69 MB / 2,227,814 行 | 91,772 条 sched/irq 事件 |
| `ftrace_format.log` | 503 行 | 事件 format 定义 |
| `ftrace_symbol.log` | 454 行 | 用户栈 `addr2line` 结果 |
| `kallsyms.txt` | 203,527 行 | 运行时符号表，含 688 个 e1000 模块符号 |
| `modules.txt` / `version.txt` / `capture.log` | — | 模块基址 / 构建信息 / 脚本输出 |

完整清单与 sha256 见 `MANIFEST.txt`。内核栈热点以收包路径为主：
`__napi_poll` 12,264、`e1000_clean` 12,221、`e1000_clean_rx_irq` 12,013、
`netif_receive_skb_list_internal` 10,660、`tcp_rcv_established` 7,644。

## 用法

```bash
tar xzf langraph.tar.gz && cd langraph
perf script --kallsyms kallsyms.txt -i perf.data > perf.relog   # 地址严格对应
grep -oE ' (tcp_|e1000_|netif_|__napi_)[a-z_]*\+0x' perf.log | sort | uniq -c | sort -rn | head -20
```

`run-langraph.sh`（宿主机编排）与 `guest-init.sh`（Guest `/init`）可复现这一轮；
`guest-serial.log` 是完整串口输出，`host_to_guest.json` 是 iperf 双向结果。
搭建 QEMU 环境所需的内核、initramfs、构建脚本见独立工程的 `qemu-guest/`。

## 限制

- `ftrace_symbol.log` 多为 `?? ??:0`：Guest 内 busybox/iperf3 无 debug info，`addr2line` 给不出行号。
- TCG 下时序、带宽、调度延迟**无真实性能意义**，不能用于真实延迟/锁竞争分析；
  本轮 iperf 40 流发送 270 Mbps、接收 2.39 Mbps，接收侧偏低是软件模拟下 Guest 发包受限。
- 硬件 PMU 不可用，`cycles` / `instructions` 为 `ENOENT`，perf 使用 `cpu-clock` 软件事件。
- 脚本 `save_perf` 早于 `perf record`（`sleep t+5`）结束，Guest 内等写完后重跑了一次
  `perf script` 覆盖 `perf.log`，因此归档里的 `perf.data` 与 `perf.log` 都是完整的。
