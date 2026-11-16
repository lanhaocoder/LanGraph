# ftrace → Perfetto 转换工具

把 `get_ftrace.sh` 产出的 **ftrace 文本日志**转成 `ui.perfetto.dev` 能直接打开的调度 trace。
工具零第三方依赖（纯 Python 标准库），单遍流式解析，可同时输出两种格式。

> 数据源：`langraph-qemu-perf-lab / iperf-lifecycle / langraph / ftrace.log`
> （QEMU Guest 内重抓的完整 20 线程双向 TCP iperf 生命周期，26.007 s，4 CPU）

---

## 1. 两种「perfetto 文件」

| 格式 | 扩展名 | 说明 | 推荐度 |
|---|---|---|---|
| **Perfetto 原生 protobuf** | `.pftrace` | 官方二进制格式，直接编码 `TrackPacket / TrackEvent`。加载最快、track 名完整、SQL 表干净、**零导入告警** | ★ 推荐 |
| **Chrome Trace Event JSON** | `.json` | 老牌通用格式，`ui.perfetto.dev` 同样直接打开，便于用文本工具检查 / 二次处理 | 兼容备选 |

两者共用同一套事件模型，看到的调度语义完全一致；区别只在编码。
本次两种都生成了，文件名相同、扩展名不同。

**打开方式**：浏览器打开 <https://ui.perfetto.dev> → `Open trace file` → 选 `.pftrace` 或 `.json`。
不需要后端、不需要联网上传（纯前端 WASM，文件留在本机）。

---

## 2. 本次生成的三份文件

| 文件 | 窗口 | 大小 | 用途 |
|---|---|---|---|
| `out/iperf-lifecycle.pftrace` / `.json` | 全量 `11.068 ~ 37.075 s` | 19.3 MB / 27.4 MB | **主交付**：完整 26 s 采集窗口，含 ftrace 先行段、全部 iperf 生死、尾部余量 |
| `out/iperf-focus.pftrace` / `.json` | `13.0 ~ 29.0 s` + `--focus iperf3` | 19.1 MB / 27.1 MB | 只显示 iperf3 的 42 个 tid 的 CPU slice / 状态轨 / 生命周期，其余进程留白 |
| `out/iperf-zoom.pftrace` / `.json` | `16.9045 ~ 16.9080 s`（3.5 ms） | 19 KB / 34 KB | **秒开**：一条完整「中断 → 软中断 → 唤醒 → 切换」因果链，适合看箭头和字段 |

`out/overview.png` 是从 `iperf-zoom.json` **反绘**的泳道预览，不开 UI 也能快速确认文件内容。

配套：`*.stats.json`（每份文件的生成统计）、`out/verify.json`（官方工具校验结果）。

---

## 2.1 本轮三项修正（相对首版）

针对评审反馈，本轮在生成器里修了三处，现均已通过官方校验：

1. **idle 线程按 CPU 区分（swapper/N:0）**
   ftrace 里每个 CPU 的 idle 线程都是 `swapper/N` + `pid=0`，如果不区分，
   所有 CPU 的 idle 会共用 `tid 0` 的状态轨而错乱。现在 idle 线程按
   `swapper/2:0` 这种「comm:pid」形式独立建轨，状态/生命周期互不串。

2. **线程名可见**
   线程状态轨、生命周期轨、CPU 运行 slice 的标签都带上 comm（如 `iperf3 状态`、
   `swapper/2:0 状态`、`iperf3:379`），Perfetto 里一眼能认出是哪个进程/线程。

3. **硬中断 → 软中断 → 用户态唤醒 因果链连上**
   把整条链做成**一条跨轨 flow**：`硬中断(IRQ 轨) → 软中断 raise(IRQ 轨) →
   唤醒(IRQ 轨) → 入队(CPU 轨) → 上CPU运行(CPU 轨)`，箭头从 IRQ 泳道直接指向
   被唤醒任务上 CPU 的切片；非中断触发的自发唤醒仍走独立的 `wakeup → run` 流。
   （IRQ 泳道补了一条全程引导 slice，避免 JSON 导入报 `flow_no_enclosing_slice`。）

---

## 3. 工具用法

```bash
# 全量，两种格式都出
python3 ftrace2perfetto.py langraph/ftrace.log -o out/trace.json --format both

# 只要原生 protobuf
python3 ftrace2perfetto.py langraph/ftrace.log -o out/trace.pftrace --format proto

# 时间窗口 + 聚焦某进程 + 只要 0/1 号 CPU
python3 ftrace2perfetto.py langraph/ftrace.log.gz -o out/zoom.json \
    --start 16.9045 --end 16.9080 --focus iperf3 --cpus 0,1 --gzip

# 校验产出
python3 verify.py "out/*.pftrace" "out/*.json" --json-out out/verify.json

# 反绘预览图
python3 preview.py out/iperf-zoom.json -o out/overview.png
```

| 参数 | 说明 |
|---|---|
| `-o, --output` | 输出路径；`both` 时自动派生同名 `.json` 与 `.pftrace` |
| `--format` | `json` / `proto` / `both`（默认 `both`） |
| `--start` / `--end` | 按 ftrace **绝对秒**裁剪 |
| `--cpus` | 只保留指定 CPU，如 `0,1` |
| `--focus` | comm 正则，只保留匹配 tid 的 CPU slice / 状态 / 生命周期 / flow（中断轨保留，因果链需要它） |
| `--no-irq` / `--no-flow` / `--no-thread-state` / `--no-lifecycle` | 按需关掉某类轨 |
| `--gzip` | JSON 输出压缩为 `.json.gz` |
| `--max-tracks` | 状态 / 生命周期轨上限（默认 1200，防止 UI 卡顿） |
| `--stats` | 统计报告路径（默认 `<output>.stats.json`） |

输入支持 `.gz`；栈回溯行（` => ...` / `<stack trace>`）自动跳过，210 MB 日志两遍扫描约 16 s。

---

## 4. 转换模型：4 组 track

| 组 | Chrome `pid` | 内容 | 事件类型 |
|---|---|---|---|
| **CPU 运行泳道** | 1 | 每 CPU 一条，`sched_switch` 换入→换出 | `X` / `SLICE_BEGIN+END` |
| **线程状态轨** | 2 | 每 **tid** 一条：`RUNNING / R / S / D / X / Z` | `X` |
| **IRQ / softirq 轨** | 3 | 每 CPU 一条：硬中断、softirq、tasklet 的 slice；`softirq_raise` 的 instant | `X` + `i` |
| **进程生命周期** | 4 | 每 tid 一条：fork / exec / wakeup_new / migrate / exit / free / wait | `i` |

CPU slice 的 `args`：`pid`、`tgid`、`comm`、`cpu`、`prev_state`、`flags`（行首标志位如 `d.h..`）、
`runtime_ns`（最近一次 `sched_stat_runtime`）、`wake2run_us`（本次唤醒到上 CPU 的延迟）。

**唤醒 flow** 用规范 `s` / `f` 事件串成 `sched_waking → sched_wakeup → sched_switch`，整数 `id`、不带 `bp:"e"`。

---

## 5. 关联规则（把前面讨论的判读逻辑编码进工具）

1. **按 tid 独立调度。** 一个 `iperf3` 进程 `tgid=371`，收/发线程是独立的 `task_struct`（`379` / `380` …）。
   行前缀 `iperf3-379 (371) [002]`：短横后 tid、括号 tgid、方括号 CPU。所以状态轨、生命周期轨都按 tid 分。
2. **唤醒三兄弟别混。**
   `sched_waking` = 决定唤醒（常在中断上下文 `d.s5.`）；`sched_wakeup` = 入就绪队列并置 `TIF_NEED_RESCHED`（`dNs6.`）；
   `sched_switch` = 真正拿到 CPU。**唤醒延迟从 `sched_wakeup` 起算**，写进换入 slice 的 `wake2run_us`。
3. **匹配键**：`waking/wakeup` 的 `pid` + `target_cpu` ↔ `sched_switch` 的 `next_pid` + `[CPU]`。
   工具用「最近一次唤醒 + 1 s 超时」消费 pending，避免长期未上 CPU 的 task 把旧 wake 误配（否则会出现 10 s 级假延迟）。
4. **中断 → 调度（收包方向）**：
   `irq_handler_entry → softirq_raise(vec=3 NET_RX) → softirq_entry → 协议栈 → sched_waking → sched_wakeup → sched_switch`。
   硬中断里**只 raise 不执行**，所以 `softirq_raise` 画成 instant，真正的处理在 `softirq_entry/exit` 的 slice 里。
   发包方向反过来：`调度(T_tx 运行) → softirq_raise(vec=2 NET_TX) → 网卡`。
5. **`prev_state` 决定为什么让出 CPU**：`S/D` 主动睡眠或等 I/O；`R/R+` 仍可运行但**被抢占**；`X/Z` 退出路径。
6. **`sched_process_free` 的坑**：被释放的 task 只在 **args** 的 `comm=... pid=...` 里，
   行前缀通常是 `<idle>` / `ksoftirqd`。工具按 args 取 pid，不按行前缀。
   `sched_process_fork` 相反：父 pid 在行前缀，`child_pid` 在 args。

---

## 6. SQL 查询模板

在 `ui.perfetto.dev` 左侧 **Query (Trace Processor)** 面板，或命令行：

```bash
TPS=/path/to/trace_processor_shell
$TPS query out/iperf-lifecycle.pftrace "SELECT ...;"
```

```sql
-- 各进程占用 CPU 时长 TOP 10
SELECT s.name, count(*) AS slices, round(sum(s.dur)/1e6, 2) AS ms
FROM slice s JOIN track t ON s.track_id = t.id
WHERE t.name LIKE 'CPU%' AND s.dur > 0
GROUP BY s.name ORDER BY ms DESC LIMIT 10;

-- 唤醒延迟分布（key 前缀：proto 是 debug.，JSON 是 args.）
SELECT count(*) n, round(avg(real_value), 1) mean_us,
       min(real_value) min_us, max(real_value) max_us
FROM args WHERE key LIKE '%wake2run_us';

-- 六类生命周期事件计数（应与原始 ftrace 一致）
SELECT name, count(*) FROM slice
WHERE dur = 0 AND name LIKE 'sched_process%' GROUP BY name;

-- 被抢占（R/R+）vs 主动睡眠（S）的次数
SELECT json_extract_string(a.string_value) ... -- 或直接看 args.prev_state
SELECT string_value AS prev_state, count(*) n
FROM args WHERE key LIKE '%prev_state' GROUP BY string_value ORDER BY n DESC;

-- 某次唤醒链的三个点（用放大版最直观）
SELECT ts, dur, name FROM slice
WHERE name LIKE '%wakeup%' OR name LIKE 'sched_waking%' ORDER BY ts LIMIT 20;
```

> 差异提示：原生 `.pftrace` 里 track 名在 `track.name`（如 `CPU0 运行`），
> 参数 key 前缀是 `debug.`；Chrome JSON 里 track 名可能为空（需用 `thread_track / thread` join），
> 参数 key 前缀是 `args.`。上面用 `LIKE '%xxx'` 兼容两者。

---

## 7. 校验结果（官方 `trace_processor_shell v59.1`）

| 文件 | slice | flow | track | health |
|---|---:|---:|---:|---|
| `iperf-lifecycle.pftrace` | 203,682 | 43,954 | 107 | **无告警** |
| `iperf-lifecycle.json` | 132,943 | 43,951 | 162 | **无告警** |
| `iperf-focus.pftrace` | 201,305 | 43,421 | 84 | 无告警 |
| `iperf-focus.json` | 131,379 | 43,417 | 122 | 无告警 |
| `iperf-zoom.pftrace` | 134 | 18 | 27 | 无告警 |
| `iperf-zoom.json` | 104 | 11 | 33 | 无告警 |

> 两种格式各自独立生成、各自用官方工具校验，均无 `flow_no_enclosing_slice`
> 等 health 告警。`.pftrace` 的 `flow` 略多于 `.json`，是因为 JSON 导入器对
> 极个别未配对的跨轨 flow 步进做了折叠，不影响主因果链呈现。

**输入 → 输出一致性**：原始 180,083 条 tracepoint 中，六类生命周期事件
`fork 59 / free 60 / exit 59 / wait 38 / exec 7` 在两种格式里**逐类完全相等**，无丢失。
全量 15,012 次 `sched_waking` 中 13,123 次（87.4%）匹配到后续 `sched_switch` 并算出唤醒延迟；
唤醒延迟 p50 **46 µs**、p95 **405 µs**、p99 **2.44 ms**（TCG 模拟环境下的长尾属正常）。
59 个 tid 的 `fork → free` 闭合（包含 iperf3 的 42 个）。

---

## 8. 踩过的坑（已修，留档）

| 现象 | 根因 | 处理 |
|---|---|---|
| proto slice 时长比 JSON 小 1000 倍 | `TracePacket.timestamp` 单位是**纳秒**，Chrome JSON 是**微秒** | proto 编码层统一做 `µs × 1000` |
| flow 全部丢失 | `ph:"f"` 带 `bp:"e"` 时 Perfetto 报 `flow_no_enclosing_slice` | 去掉 `bp`，`id` 用整数 |
| 3 条 flow 告警 | ftrace 开录到该 CPU 首次 `sched_switch` 之间泳道空白，flow 无 enclosing slice | 每条 CPU 泳道补一个 `(trace start)` 引导 slice（淡背景，预览图不显示） |
| 唤醒延迟出现 10 s 级假值 | 旧 pending 没清，被很久以后的 switch 误匹配 | 倒序取最近唤醒 + 1 s 超时 + 消费后清空该 pid 的 pending |
| annotation 值读不出来 | `DebugAnnotation` 字段号记错 | 按官方 proto 修正：`name=10, int=4, double=5, string=6` |

---

## 9. 复现

```bash
cd /workspace/ftrace2perfetto
SRC=/workspace/iperf-lifecycle-out/langraph/ftrace.log

python3 ftrace2perfetto.py "$SRC" -o out/iperf-lifecycle.json --format both
python3 ftrace2perfetto.py "$SRC" -o out/iperf-focus.json --format both \
    --start 13.0 --end 29.0 --focus iperf3
python3 ftrace2perfetto.py "$SRC" -o out/iperf-zoom.json --format both \
    --start 16.9045 --end 16.9080
python3 preview.py out/iperf-zoom.json -o out/overview.png
python3 verify.py "out/iperf-*.pftrace" "out/iperf-*.json" --json-out out/verify.json
```

---

## 10. 已知限制：在 Perfetto UI 里查看因果链

官方文档原话：*"The link is displayed as an arrow in the UI, when one of the events is selected."*
即 flow 箭头**不会默认全画**，必须点选某个端点事件才显示。全量 26 s 视图下看不到箭头属正常。

当前 `.pftrace` 的 flow 端点全部是 `dur=0` 的 instant（`flow_ids=47` / `terminating_flow_ids=48`），
UI 里渲染成 1px 紫色三角 ▲，不容易点中；`.json` 版因 Chrome JSON 导入器会把 `ph:s/f` 贴到
enclosing slice 上，端点是有宽度的 slice，更好点选。这是已知的**两种格式不对称**，待修项：
把 pftrace 端点改为有宽度的 slice。

查看步骤：

1. 用窄窗口文件（`iperf-chain.pftrace` / `.json`，2.4 ms），别用 26 s 全量；
2. 展开「CPU 运行泳道」「IRQ/softirq 轨」；
3. 滚轮放大到 0.5~2 ms 视野；
4. 点选紫色三角 ▲ 或 slice → 箭头出现，详情面板出现 Flow 字段。

数据本身完整：全量 pftrace 有 43,954 条 flow、4,641 条跨轨、零 health 告警。

**更正一处之前的错误判断**：当时写「硬中断少是抓包没 enable `irq/irq_handler_entry`、
需重抓补齐」是错的——tracepoint 一直开着（`irq_handler_entry/exit` 74/74 成对）。
真正原因是 **e1000 驱动的 NAPI 中断屏蔽**：`e1000_intr()` 写 IMC 关中断 →
`__napi_schedule()` → NET_RX softirq 里 `e1000_clean()` 批量收包；持续大流量下
RX 队列不排空，就一直停在 polling，不 `napi_complete()` 重开中断，
所以稳定打流 10 s 内 eth0 硬中断为 0，因果链只能从 NET_RX 软中断起点。

**本轮已低速重抓验证**：流量改成 `-P 2 -b 1M -l 256`（2.0 Mbps），包间隔拉到
ms 级，每轮 poll 都能排空队列、重开中断。实测 `irq_handler_entry: irq=11 eth0`
从 66 → **18,522**，与 NET_RX raise 15,184 约 1.2 : 1，
`/proc/interrupts` IRQ11 增量 +18,698，并抓到 4,886 条「硬中断 → 上CPU」完整链。

工具本轮两处改动：
① 支持 `napi_poll` 事件（自由文本解析 `device/work/budget`，在 IRQ 轨发 instant 并续接 flow）；
② `softirq_exit` 不再立即 end 因果流，改为挂起、2 ms 内的 `sched_waking` 复活它，
   让硬中断链能闭合到「上CPU运行」（闭合数 3,044 → 4,886）。

归档见 `langraph-qemu-perf-lab/iperf-hardirq/`（采集脚本、原始日志、统计结果）与
`langraph-qemu-perf-lab/iperf-hardirq/perfetto/`（trace、结果页、校验报告）。

**本轮工具代码同步更新**：`ftrace2perfetto.py` 新增 `napi_poll` 解析与
`softirq_exit` 挂起/复活逻辑，已随本轮一并归档到 `LanGraph`。

### 已知限制（待修）

`.pftrace` 的 flow 端点目前全部是 `dur=0` 的 instant，Perfetto UI 对 instant 端点的
箭头渲染不如落在有宽度 slice 上稳妥；`.json` 版本端点多数落在 slice 内。
需要肉眼确认箭头时优先用 `.json`，或看 `hardirq-result.html`。
把 pftrace 端点改成带 `dur` 的 slice 是后续待修项，不影响数据完整性。

---

## 12. 带调用栈标注（实验 6）

新增 `tracepoint_stacks.py`：解析每个 tracepoint 后面的 `<stack trace>` / `<user stack trace>`，
输出逐条索引（`start/end/start_sym/end_sym/depth`）。`ftrace2perfetto.py` 新增
`--stacks <jsonl.gz>`，把三个字段挂到 tracepoint 产生的 slice / instant / flow 上；新增
`--show-sleep-state` 开关，**默认隐藏 S 可中断睡眠段**（D 等其它状态保留）。

「起始/末尾堆栈」定义：ftrace 跟的是**一个完整内核栈**（栈顶→栈底），
`stack_start` = 栈顶第一帧（直接触发点），`stack_end` = 栈底最后一帧（调用链入口）。
例：`irq_handler_entry` 起始帧 100% 是 `__handle_irq_event_percpu`，
`sched_waking` 100% 是 `try_to_wake_up`。归属按 `<stack trace>` 标记行自带的 CPU，
否则 4 CPU buffer 合并时会串轨。

产物归档在 `langraph-qemu-perf-lab/iperf-hardirq/perfetto/stacks/`：
单链原件 + 全量 gzip（97 MB→3.6 MB）+ 逐条索引 + 校验报告，四份零 health 告警。
该目录只含 Perfetto 文件与数据索引，无 HTML/PNG 展示物。

---

## 11. 状态

工具本体已归档到 `LanGraph/script/ftrace2perfetto/`，
trace 产物已归档到 `langraph-qemu-perf-lab/iperf-lifecycle/perfetto/`（实验 4）、
`langraph-qemu-perf-lab/iperf-hardirq/perfetto/`（实验 5，完整硬中断链）与
`iperf-hardirq/perfetto/stacks/`（实验 6，带堆栈）。
全部通过官方 `trace_processor_shell v59.1` 校验（零 health 告警）。

实验 5 新增产物：`iperf-hardirq-chain.*`（3 ms 单条完整链）、
`iperf-hardirq-full.*`（26 s 全量）、`hardirq-chain-preview.png`、
`hardirq-result.html`、`verify-hardirq.json`；原始采集在 `langraph-qemu-perf-lab/iperf-hardirq/`。
两个仓库的旧错误说明（「需 enable `irq_handler_entry` 后重抓」）已一并更正。
