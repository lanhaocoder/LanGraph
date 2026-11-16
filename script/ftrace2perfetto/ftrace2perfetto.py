#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ftrace2perfetto.py — 把 ftrace 文本日志转换成 Perfetto 可打开的调度 trace
========================================================================

输入：`get_ftrace.sh` 产出的 `ftrace.log`（纯文本，可能带内核栈回溯、可 gzip）
输出：两种格式，可任选或同时生成

  * Chrome Trace Event JSON (.json) —— ui.perfetto.dev 直接 File > Open 即可
  * Perfetto 原生 protobuf trace (.pftrace) —— 官方二进制格式，加载更快、SQL 更全

两种格式共用同一套「事件模型」，保证看到的调度语义完全一致。

设计要点（对应 ftrace → 调度的关联规则）
----------------------------------------
1. `sched_switch` 是 CPU 泳道的唯一依据：换入 → 开 slice，换出 → 关 slice。
   slice 的 args 带 pid / tgid / prev_state / flags / runtime_ns / wake2run_us。
2. 唤醒链 `sched_waking → sched_wakeup → sched_switch` 用规范 flow 箭头连接。
   **flow 的 `f` 事件绝不能带 `bp:"e"`**，否则 Perfetto 报
   `flow_no_enclosing_slice` 而整条 flow 丢失；`id` 用整数。
3. `sched_waking` 只是「决定唤醒」，`sched_wakeup` 才入队并置 NEED_RESCHED，
   `sched_switch` 才真正上 CPU。唤醒延迟 = switch(ts) − wakeup(ts)，
   写进换入 slice 的 `wake2run_us`。
4. 线程按 **tid** 独立调度：每个 tid 一条状态轨（R/S/D/RUNNING/X/Z），
   一条生命周期轨（fork/exec/wakeup_new/migrate/exit/free/wait instant）。
5. `sched_process_free` 的被释放 task 在 **args** 里（comm=... pid=...），
   行前缀通常是 `<idle>` / ksoftirqd —— 按行前缀匹配会漏掉它。
   `sched_process_fork` 的父 pid 在行前缀，child_pid 在 args。
6. 中断侧：`irq_handler_entry/exit`、`softirq_entry/exit`、`tasklet_*` 画成
   IRQ 泳道 slice，`softirq_raise` 画成 instant（硬中断里只 raise，不执行）。
7. 时间戳：ftrace 是秒（6 位小数），Chrome/Perfetto 用微秒，×1e6 不丢精度。
8. `--stacks` 载入逐条堆栈索引后，每个 tracepoint 产生的 slice / instant / flow
   的 args 会带上 `stack_start`（栈顶起始帧）、`stack_end`（栈底末尾帧）、
   `stack_depth`。索引由 `tracepoint_stacks.py --events-out` 生成。
9. **S 可中断睡眠默认不显示**：状态轨上 S 段留白（只闭合上一段、不再新开），
   `--show-sleep-state` 可恢复。CPU 运行轨与 IRQ 轨不受影响。

用法
----
    python3 ftrace2perfetto.py ftrace.log -o out/trace.json
    python3 ftrace2perfetto.py ftrace.log -o out/trace.pftrace --format both
    python3 ftrace2perfetto.py ftrace.log.gz -o out/zoom.json \
        --start 16.0 --end 17.0 --focus iperf3 --gzip
    python3 ftrace2perfetto.py ftrace.log -o out/trace.json --no-irq --no-flow

依赖：仅 Python 标准库（3.8+）。
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import struct
import sys
import time
from collections import Counter, defaultdict

VERSION = "1.0"

# ---------------------------------------------------------------------------
# ftrace 行格式
#   ksoftirqd/0-16  (  16) [000] d.s..  7.046084: sched_switch: prev_comm=... ...
#   <idle>-0        (-----) [001] d..2. 7.048484: sched_wakeup: comm=... ...
#   iperf3-379      (  371) [002] d..2. 16.905375: sched_switch: ... ==> next_pid=382
# ---------------------------------------------------------------------------
LINE_RE = re.compile(
    r"^\s*(?P<comm>.+?)-(?P<pid>\d+)\s+\((?P<tgid>[^)]*)\)\s+"
    r"\[(?P<cpu>\d+)\]\s+(?P<flags>\S+)\s+"
    r"(?P<ts>\d+\.\d+):\s+(?P<event>[A-Za-z_][A-Za-z0-9_]*):\s*(?P<rest>.*)$"
)
KV_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=([^\s\]]+)")

# 只处理这些 tracepoint，其余（尤其 200 万行栈帧）直接跳过
WANTED = {
    "sched_switch", "sched_waking", "sched_wakeup", "sched_wakeup_new",
    "sched_wake_idle_without_ipi", "sched_migrate_task", "sched_stat_runtime",
    "sched_process_fork", "sched_process_exec", "sched_process_exit",
    "sched_process_free", "sched_process_wait",
    "irq_handler_entry", "irq_handler_exit",
    "softirq_raise", "softirq_entry", "softirq_exit",
    "napi_poll",
    "tasklet_entry", "tasklet_exit",
}

# Track 分组（Chrome JSON 的 pid；原生 proto 里是 parent track）
G_CPU, G_STATE, G_IRQ, G_LIFE = 1, 2, 3, 4
GROUP_NAMES = {
    G_CPU: "CPU 运行泳道",
    G_STATE: "线程状态轨（按 tid）",
    G_IRQ: "IRQ / softirq 轨",
    G_LIFE: "进程生命周期事件",
}

STATE_NAME = {
    "R": "R 可运行 / 被抢占", "S": "S 可中断睡眠", "D": "D 不可中断睡眠",
    "I": "I idle 内核线程", "T": "T 已停止", "X": "X 退出中",
    "Z": "Z 僵尸", "K": "K 内核唤醒", "W": "W 唤醒中", "P": "P 暂停",
    "N": "N 待运行", "RUN": "RUNNING 正在 CPU 上运行",
}


def state_label(prev_state: str) -> str:
    p = (prev_state or "").rstrip("+")
    key = p[:1].upper() if p else "?"
    return STATE_NAME.get(key, "其他(%s)" % (prev_state or "?"))


# ---------------------------------------------------------------------------
# 纯标准库 protobuf 编码器（Perfetto Trace / TracePacket / TrackEvent）
# 字段号取自官方 protos/perfetto/trace/*.proto
#   Trace.packet = 1
#   TracePacket: timestamp=8, trusted_packet_sequence_id=10, sequence_flags=13,
#                track_event=11, track_descriptor=60
#   TrackEvent: type=9, track_uuid=11, name=23, categories=22,
#               debug_annotations=4, flow_ids=47(fixed64), terminating_flow_ids=48
#   TrackDescriptor: uuid=1, name=2, parent_uuid=5
#   DebugAnnotation: name=10, bool=2, uint=3, int=4, double=5, string=6
# ---------------------------------------------------------------------------
def _vi(n: int) -> bytes:
    out = bytearray()
    n = int(n)
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _tag(field: int, wire: int) -> bytes:
    return _vi((field << 3) | wire)


def _v(field: int, n: int) -> bytes:
    return _tag(field, 0) + _vi(n)


def _s(field: int, x) -> bytes:
    b = x.encode("utf-8") if isinstance(x, str) else bytes(x)
    return _tag(field, 2) + _vi(len(b)) + b


def _m(field: int, b: bytes) -> bytes:
    return _tag(field, 2) + _vi(len(b)) + b


def _f64(field: int, n: int) -> bytes:
    return _tag(field, 1) + struct.pack("<Q", int(n))


def _dbl(field: int, x: float) -> bytes:
    return _tag(field, 1) + struct.pack("<d", float(x))


def _annotation(name: str, value) -> bytes:
    d = _s(10, name)
    if isinstance(value, bool):
        d += _v(2, 1 if value else 0)
    elif isinstance(value, int):
        d += _v(4, value)
    elif isinstance(value, float):
        d += _dbl(5, value)
    else:
        d += _s(6, str(value))
    return _m(4, d)


class ProtoWriter:
    """流式写 Perfetto 原生 protobuf trace。"""

    SLICE_BEGIN, SLICE_END, INSTANT = 1, 2, 3

    def __init__(self, path):
        self.f = open(path, "wb")
        self.first = True
        self.count = 0

    def _packet(self, ts_us: int, body: bytes, clear=False):
        # Perfetto trace 内部时间戳一律为纳秒；本工具内部统一用微秒，
        # 在这里做唯一一次 µs → ns 换算（descriptor 传 0）。
        b = _v(8, max(0, int(ts_us * 1000)))
        if clear:
            b += _v(13, 1)          # SEQ_INCREMENTAL_STATE_CLEARED
        b += body
        b += _v(10, 1)             # trusted_packet_sequence_id
        self.f.write(_m(1, b))
        self.count += 1
        self.first = False

    def descriptor(self, uuid, name, parent=None):
        d = _v(1, uuid) + _s(2, name)
        if parent is not None:
            d += _v(5, parent)
        self._packet(0, _m(60, d), clear=self.first)

    def _event(self, ts_us, uuid, typ, name=None, cat=None,
               flow=None, term_flow=None, args=None):
        e = _v(9, typ) + _v(11, uuid)
        if name:
            e += _s(23, name)
        if cat:
            e += _s(22, cat)
        if flow is not None:
            e += _f64(47, flow)
        if term_flow is not None:
            e += _f64(48, term_flow)
        for k, val in (args or {}).items():
            if val is not None:
                e += _annotation(k, val)
        self._packet(ts_us, _m(11, e))

    def slice_begin(self, ts, uuid, name, cat, args=None, flow=None):
        self._event(ts, uuid, self.SLICE_BEGIN, name, cat, flow=flow, args=args)

    def slice_end(self, ts, uuid, term_flow=None):
        self._event(ts, uuid, self.SLICE_END, term_flow=term_flow)

    def instant(self, ts, uuid, name, cat, args=None, flow=None, term_flow=None):
        self._event(ts, uuid, self.INSTANT, name, cat,
                    flow=flow, term_flow=term_flow, args=args)

    def close(self):
        self.f.close()


class JsonWriter:
    """流式写 Chrome Trace Event JSON。"""

    def __init__(self, path, gzip_output=False):
        self.path = path
        self.gzip_output = gzip_output
        self.f = gzip.open(path, "wt", encoding="utf-8") if gzip_output else open(path, "w", encoding="utf-8")
        self.n = 0
        self.count = 0
        self.f.write("[\n")

    def emit(self, obj):
        if self.n:
            self.f.write(",\n")
        self.f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
        self.n += 1
        self.count += 1

    def meta(self, pid, tid, name, value):
        self.emit({"ph": "M", "pid": pid, "tid": tid,
                   "name": name, "args": {"name": value}})

    def slice(self, pid, tid, ts, dur, name, cat, args=None):
        o = {"ph": "X", "pid": pid, "tid": tid, "ts": ts,
             "dur": max(0.0, dur), "name": name, "cat": cat}
        if args:
            o["args"] = args
        self.emit(o)

    def instant(self, pid, tid, ts, name, cat, args=None, scope="t"):
        o = {"ph": "i", "pid": pid, "tid": tid, "ts": ts,
             "name": name, "cat": cat, "s": scope}
        if args:
            o["args"] = args
        self.emit(o)

    def flow_start(self, pid, tid, ts, fid, name, args=None):
        # 注意：不带 bp:"e"，id 必须是整数
        o = {"ph": "s", "id": fid, "pid": pid, "tid": tid, "ts": ts,
             "cat": "wakeup", "name": name}
        if args:
            o["args"] = args
        self.emit(o)

    def flow_step(self, pid, tid, ts, fid, name, args=None):
        o = {"ph": "f", "id": fid, "pid": pid, "tid": tid, "ts": ts,
             "cat": "wakeup", "name": name}
        if args:
            o["args"] = args
        self.emit(o)

    def close(self):
        self.f.write("\n]\n")
        self.f.close()


# ---------------------------------------------------------------------------
# 转换器
# ---------------------------------------------------------------------------
class Converter:
    def __init__(self, opts):
        self.opts = opts
        self.jw = None
        self.pw = None
        # 每个 tracepoint 的「起始 / 末尾堆栈」，来自 tracepoint_stacks.py 的逐条索引
        self.stack_map = {}
        self.cur_stack_args = {}
        if getattr(opts, "stacks", None):
            self._load_stacks(opts.stacks)
        self.tracks = {}            # key -> (group, tid, uuid, name)
        self.group_uuid = {}        # group -> parent uuid
        self.next_uuid = 10000
        self.next_tid = 100

        # 统计
        self.st = {
            "in_events": Counter(), "out": Counter(),
            "lines": 0, "stack_lines": 0, "skipped_lines": 0,
            "tmin": None, "tmax": None,
            "wake2run_us": [], "flow_matched": 0, "flow_total": 0,
            "focus_tids": set(), "life": defaultdict(set),
            "pids_seen": set(), "cpus_seen": set(),
        }
        # pass2 运行状态
        self.cpu_running = {}       # cpu -> dict
        self.state_open = {}        # pid -> dict(state, ts, comm)
        self.irq_open = defaultdict(list)   # cpu -> [dict]
        self.pending_wake = defaultdict(list)  # pid -> [dict]
        self.last_runtime = {}      # pid -> ns
        self.flow_seq = 0
        self.task_names = {}        # pid -> comm
        self.comm_by_pid = {}       # pid -> comm（扫描期收集，用于线程轨命名）
        # 单条跨轨因果链：硬中断 → 软中断 → 唤醒 → 入队 → 上CPU运行
        # 起点挂在 G_IRQ 轨，终点落在被唤醒任务上 CPU 的 G_CPU 轨。
        self.causal_fid = {}          # cpu -> fid（当前打开的因果流，None 表示无）
        self.causal_softirq_seen = {} # cpu -> bool（本次中断是否已产生 softirq）
        # softirq_exit 时因果流先「挂起」而不是立刻 end：真实内核里
        # sched_waking 常发生在软中断退出之后几十~几百 µs（尤其 TCG 下），
        # 立即 end 会把「硬中断→上CPU」链拦腰截断。挂起窗口内若有唤醒则复活该流。
        self.pending_close = {}       # cpu -> (fid, ts_us, vec)

    def _load_stacks(self, path):
        """加载逐条堆栈索引（tracepoint_stacks.py --events-out 产出的 JSONL）。

        key = (ts 原始字符串, cpu:int, event, pid:int) -> [条目, ...]
        用 list 而非 pop，保证 Pass1 / Pass2 各自维护独立游标、互不干扰。
        """
        op = gzip.open if path.endswith(".gz") else open
        n = 0
        with op(path, "rt", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                key = (str(r["ts"]), int(r["cpu"]), r["event"], int(r["pid"]))
                self.stack_map.setdefault(key, []).append(r)
                n += 1
        sys.stderr.write("[stacks] 载入 %d 条逐条堆栈索引（%d 个 key）\n"
                         % (n, len(self.stack_map)))

    def _stack_args(self, d):
        """把当前事件的「起始 / 末尾堆栈」转成 Perfetto args。"""
        s = d.get("stack")
        if not s:
            return {}
        return {
            "stack_start": s.get("start", ""),
            "stack_end": s.get("end", ""),
            "stack_depth": s.get("depth", 0),
        }

    # ---------------- 文件 IO ----------------
    def _open_input(self):
        p = self.opts.input
        if p.endswith(".gz"):
            return gzip.open(p, "rt", encoding="utf-8", errors="replace")
        return open(p, "r", encoding="utf-8", errors="replace")

    def _iter(self):
        """逐行解析，产出 dict；跳过栈帧与注释。

        若给了 --stacks，按 (ts 字符串, cpu, event, pid) 查逐条堆栈索引，
        把「起始 / 末尾堆栈」挂到 d["stack"] 上。Pass1 / Pass2 各自维护
        独立的 used 游标，互不干扰。
        """
        cpus = None
        if self.opts.cpus:
            cpus = set(int(x) for x in self.opts.cpus.split(",") if x.strip())
        used = defaultdict(int)
        with self._open_input() as f:
            for line in f:
                self.st["lines"] += 1
                if line.startswith(" =>") or "<stack trace>" in line:
                    self.st["stack_lines"] += 1
                    continue
                if not line or line[0] == "#":
                    self.st["skipped_lines"] += 1
                    continue
                m = LINE_RE.match(line.rstrip("\n"))
                if not m:
                    self.st["skipped_lines"] += 1
                    continue
                ev = m.group("event")
                if ev not in WANTED:
                    self.st["skipped_lines"] += 1
                    continue
                d = m.groupdict()
                ts_raw = d["ts"]
                d["ts"] = float(ts_raw)
                d["cpu"] = int(d["cpu"])
                d["pid"] = int(d["pid"])
                if cpus is not None and d["cpu"] not in cpus:
                    continue
                try:
                    d["tgid"] = int(d["tgid"].strip())
                except ValueError:
                    d["tgid"] = None
                d["kv"] = {k: v for k, v in KV_RE.findall(d["rest"])}
                # 每个 tracepoint 的起始 / 末尾堆栈
                if self.stack_map:
                    key = (ts_raw, d["cpu"], ev, d["pid"])
                    i = used[key]
                    used[key] += 1
                    lst = self.stack_map.get(key)
                    d["stack"] = lst[i] if lst and i < len(lst) else None
                else:
                    d["stack"] = None
                yield d

    # ---------------- track 注册 ----------------
    def _track_key(self, group, key, name):
        k = (group, key)
        if k not in self.tracks:
            tid = self.next_tid
            uuid = self.next_uuid
            self.next_tid += 1
            self.next_uuid += 1
            self.tracks[k] = (group, tid, uuid, name)
        return self.tracks[k]

    def _thread_key(self, pid, comm, cpu):
        """线程轨唯一 key。idle 线程(pid=0 / swapper / <idle>) 按 CPU 区分：
        用 swapper/N:0，否则同 tid=0 在不同 CPU 上会错乱。"""
        comm = comm or ""
        if (pid == 0) or comm.startswith("swapper") or comm == "<idle>":
            label = comm if (comm and comm != "<idle>") else ("swapper/%d" % cpu)
            return ("idle", label)          # 已含 CPU 号，全局唯一
        return ("task", pid)

    def _thread_label(self, comm, cpu, pid=None):
        """线程显示名：idle 用 swapper/N:0，普通线程用 comm（缺省回退 tid）。"""
        comm = comm or ""
        if (pid == 0) or comm.startswith("swapper") or comm == "<idle>":
            label = comm if (comm and comm != "<idle>") else ("swapper/%d" % cpu)
            return "%s:0" % label
        return comm or ("tid %d" % (pid if pid is not None else 0))

    def _register_thread_tracks(self, key, comm, cpu, pid=None):
        label = self._thread_label(comm, cpu, pid)
        if not self.opts.no_thread_state:
            self._track_key(G_STATE, key, label + " 状态")
        if not self.opts.no_lifecycle:
            self._track_key(G_LIFE, key, label + " 生命周期")

    def _emit_descriptors(self):
        # 先建 4 个 parent track（原生 proto 的层级）
        for g in (G_CPU, G_STATE, G_IRQ, G_LIFE):
            u = self.next_uuid
            self.next_uuid += 1
            self.group_uuid[g] = u
            if self.jw:
                self.jw.meta(g, 0, "process_name", GROUP_NAMES[g])
            if self.pw:
                self.pw.descriptor(u, GROUP_NAMES[g])
        # 子 track
        for (g, key), (grp, tid, uuid, name) in sorted(self.tracks.items(),
                                                       key=lambda x: (x[1][0], str(x[1][1]))):
            if self.jw:
                self.jw.meta(grp, tid, "thread_name", name)
            if self.pw:
                self.pw.descriptor(uuid, name, parent=self.group_uuid[grp])

    # ---------------- 统一 emit ----------------
    def emit_slice(self, group, key, name, ts, dur, cat, args, track_name=None,
                   flow=None, term_flow=None):
        if self.cur_stack_args:
            args = {**self.cur_stack_args, **(args or {})}
        if track_name is None:
            track_name = name
        _, tid, uuid, _ = self._track_key(group, key, track_name)
        if self.jw:
            self.jw.slice(group, tid, ts, dur, name, cat, args)
        if self.pw:
            self.pw.slice_begin(ts, uuid, name, cat, args, flow=flow)
            self.pw.slice_end(ts + max(0.0, dur), uuid, term_flow=term_flow)
        self.st["out"]["slice"] += 1

    def emit_instant(self, group, key, name, ts, cat, args, track_name=None,
                     flow=None, term_flow=None):
        if self.cur_stack_args:
            args = {**self.cur_stack_args, **(args or {})}
        if track_name is None:
            track_name = "事件"
        _, tid, uuid, _ = self._track_key(group, key, track_name)
        if self.jw:
            self.jw.instant(group, tid, ts, name, cat, args)
        if self.pw:
            self.pw.instant(ts, uuid, name, cat, args, flow=flow, term_flow=term_flow)
        self.st["out"]["instant"] += 1

    def emit_flow(self, cpu, ts, fid, name, kind, args, group=None):
        """kind: 'start' | 'step' | 'end'；group 默认 G_CPU，
        中断→软中断→唤醒 这条因果链挂在 G_IRQ 轨上。"""
        if self.cur_stack_args:
            args = {**self.cur_stack_args, **(args or {})}
        if group is None:
            group = G_CPU
        if group == G_IRQ:
            key = ("irq", cpu); lane = "CPU%d IRQ / softirq" % cpu
        else:
            key = ("cpu", cpu); lane = "CPU%d 运行" % cpu
        _, tid, uuid, _ = self._track_key(group, key, lane)
        if self.jw:
            if kind == "start":
                self.jw.flow_start(group, tid, ts, fid, name, args)
            else:
                self.jw.flow_step(group, tid, ts, fid, name, args)
        if self.pw:
            if kind == "end":
                self.pw.instant(ts, uuid, name, "wakeup", args, term_flow=fid)
            else:
                self.pw.instant(ts, uuid, name, "wakeup", args, flow=fid)
        self.st["out"]["flow"] += 1

    def _close_intr(self, cpu, us, reason, args=None):
        """收尾当前 CPU 上未闭合的因果流（防止 dangling flow 告警）。"""
        if self.causal_fid.get(cpu) is not None:
            self.emit_flow(cpu, us, self.causal_fid[cpu], reason, "end",
                           args or {"note": reason}, group=G_IRQ)
            self.causal_fid[cpu] = None
            self.causal_softirq_seen[cpu] = False

    def _flush_pending_close(self, cpu):
        """把 softirq_exit 挂起、但窗口内始终没等到唤醒的因果流收尾。

        end 时间点用挂起时刻（软中断退出），这样箭头不会拖到下一个硬中断。
        """
        pc = self.pending_close.pop(cpu, None)
        if pc:
            fid, t0, vec = pc
            self.emit_flow(cpu, t0, fid, "软中断结束(未唤醒任务)", "end",
                           {"vec": vec, "note": "窗口内无唤醒，链在软中断出口收尾"},
                           group=G_IRQ)

    # ---------------- Pass 1：扫描统计 + 收集 track ----------------
    def scan(self):
        focus = self.opts.focus
        focus_re = re.compile(focus) if focus else None
        for d in self._iter():
            ev, ts, cpu, pid = d["event"], d["ts"], d["cpu"], d["pid"]
            self.st["in_events"][ev] += 1
            if self.st["tmin"] is None or ts < self.st["tmin"]:
                self.st["tmin"] = ts
            if self.st["tmax"] is None or ts > self.st["tmax"]:
                self.st["tmax"] = ts
            self.st["cpus_seen"].add(cpu)
            self.st["pids_seen"].add(pid)

            kv = d["kv"]
            comm = d["comm"]
            # 收集 comm，供线程状态/生命周期轨命名（让 Perfetto 显示线程名）
            self.comm_by_pid.setdefault(pid, comm)
            if ev == "sched_switch":
                pc, ppid = kv.get("prev_comm"), kv.get("prev_pid")
                nc, npid = kv.get("next_comm"), kv.get("next_pid")
                if ppid and ppid.isdigit():
                    self.comm_by_pid.setdefault(int(ppid), pc)
                if npid and npid.isdigit():
                    self.comm_by_pid.setdefault(int(npid), nc)
            hit = False
            if focus_re:
                if focus_re.search(comm) or any(focus_re.search(v) for v in kv.values()):
                    hit = True
            # 收集 focus tid：行前缀 pid + args 里的各类 pid
            if hit:
                self.st["focus_tids"].add(pid)
                for k in ("pid", "child_pid", "next_pid", "prev_pid", "old_pid"):
                    if k in kv and kv[k].isdigit():
                        self.st["focus_tids"].add(int(kv[k]))

            # 收集需要建 track 的 pid（全量模式下只给真实出现过的 task 建）
            self.st["pids_seen"].add(pid)
            for k in ("pid", "child_pid", "next_pid"):
                if k in kv and kv[k].isdigit():
                    self.st["pids_seen"].add(int(kv[k]))

        # 注册 track
        for c in sorted(self.st["cpus_seen"]):
            self._track_key(G_CPU, ("cpu", c), "CPU%d 运行" % c)
            if not self.opts.no_irq:
                self._track_key(G_IRQ, ("irq", c), "CPU%d IRQ / softirq" % c)
        pids = self.st["focus_tids"] if focus else self.st["pids_seen"]
        # 上限保护：track 过多会让 UI 卡顿
        if len(pids) > self.opts.max_tracks:
            pids = set(sorted(pids)[:self.opts.max_tracks])
        for p in sorted(pids):
            if p == 0:
                # idle 线程按 CPU 拆成 swapper/N:0，否则同 tid=0 会错乱
                for c in sorted(self.st["cpus_seen"]):
                    self._register_thread_tracks(("idle", "swapper/%d" % c),
                                                 "swapper/%d" % c, c, 0)
            else:
                comm = self.comm_by_pid.get(p, "")
                self._register_thread_tracks(("task", p), comm, None, p)
        if not self.opts.no_flow:
            # flow 挂在 CPU / IRQ track 上，已注册
            pass

    # ---------------- Pass 2：状态机 ----------------
    def _window_ok(self, ts):
        if self.opts.start is not None and ts < self.opts.start:
            return False
        if self.opts.end is not None and ts > self.opts.end:
            return False
        return True

    def _visible(self, pid):
        if not self.opts.focus:
            return True
        return pid in self.st["focus_tids"]

    def _set_state(self, pid, state, ts, comm=None, cpu=None, raw=None):
        if self.opts.no_thread_state or not self._visible(pid):
            return
        if comm:
            self.comm_by_pid.setdefault(pid, comm)
        tk = self._thread_key(pid, comm, cpu)
        label = self._thread_label(comm, cpu, pid)
        cur = self.state_open.get(tk)
        if cur:
            self.emit_slice(G_STATE, tk, cur["state"],
                            cur["ts"], ts - cur["ts"], "state",
                            {"tid": pid, "comm": comm or self.comm_by_pid.get(pid, "")},
                            track_name=label + " 状态")
        # S 可中断睡眠默认不显示：上一段已闭合，这里不再新开，状态轨上留白
        if not getattr(self.opts, "show_sleep_state", False) and \
                (raw or "").rstrip("+").upper().startswith("S"):
            self.state_open.pop(tk, None)
            return
        self.state_open[tk] = {"state": state, "ts": ts, "label": label,
                               "comm": comm or self.comm_by_pid.get(pid, "")}

    def _close_cpu(self, cpu, ts, prev_state):
        r = self.cpu_running.get(cpu)
        if not r:
            return
        if self._visible(r["pid"]) or r.get("bootstrap"):
            boot = bool(r.get("bootstrap"))
            args = {
                "pid": r["pid"], "tgid": r["tgid"], "comm": r["comm"],
                "cpu": cpu,
                "prev_state": "(trace start)" if boot else prev_state,
                "flags": r["flags"],
            }
            if boot:
                args["note"] = "开录到该 CPU 首次 sched_switch 的空白段，用于闭合泳道"
            if r["pid"] in self.last_runtime:
                args["runtime_ns"] = self.last_runtime[r["pid"]]
            if r["wake2run_us"] is not None:
                args["wake2run_us"] = round(r["wake2run_us"], 3)
            name = "%s:%d" % (r["comm"], r["pid"])
            if boot:
                name = "(trace start) " + name
            self.emit_slice(G_CPU, ("cpu", cpu), name,
                            r["ts"], ts - r["ts"], "sched", args,
                            track_name="CPU%d 运行" % cpu)
        del self.cpu_running[cpu]

    def _open_cpu(self, cpu, ts, pid, comm, tgid, flags, prev_state):
        # 消费 pending wake → 计算唤醒延迟并收尾 flow
        w2r, fid = None, None
        pending = self.pending_wake.get(pid)
        if pending and not self.opts.no_flow:
            cand = None
            # 倒序取「最近一次」唤醒；超过 1 s 的旧 pending 视为过期。
            # 否则长期未上 CPU 的 task 会把很久以前的 wake 误配到本次
            # switch，污染 wake2run（TCG 下会出现 10 s 级假延迟）。
            for i in range(len(pending) - 1, -1, -1):
                w = pending[i]
                if w["cpu"] != cpu and w["cpu"] is not None:
                    continue
                if ts - w["ts_waking"] > 1_000_000:   # 1 s（µs）
                    continue
                cand = i
                break
            if cand is not None:
                w = pending[cand]
                # ts / base 都已经是微秒（us = ts_sec * 1e6），差值直接就是 µs
                base = w["ts_wakeup"] if w["ts_wakeup"] is not None else w["ts_waking"]
                w2r = ts - base
                cfid = w.get("causal_fid")
                self.pending_wake[pid].clear()   # 一次上 CPU 消费掉该 pid 的全部 pending
                self.st["wake2run_us"].append(w2r)
                self.st["flow_matched"] += 1
                if cfid is not None:
                    # 跨轨因果链收尾：硬中断→软中断→唤醒→入队→上CPU运行
                    self.emit_flow(cpu, ts, cfid, "上CPU运行（中断→唤醒→运行）", "end",
                                   {"pid": pid, "wake2run_us": round(w2r, 3),
                                    "target_cpu": w["cpu"]}, group=G_CPU)
                else:
                    self.emit_flow(cpu, ts, w["fid"], "wakeup -> run", "end",
                                   {"pid": pid, "wake2run_us": round(w2r, 3),
                                    "target_cpu": w["cpu"]})
        self.cpu_running[cpu] = {
            "pid": pid, "comm": comm, "tgid": tgid, "ts": ts,
            "flags": flags, "wake2run_us": w2r,
        }

    def _irq_push(self, cpu, ts, name, cat, args):
        if self.opts.no_irq:
            return
        self.irq_open[cpu].append({"name": name, "ts": ts, "cat": cat, "args": args})

    def _irq_pop(self, cpu, ts, match=None):
        if self.opts.no_irq:
            return
        stack = self.irq_open[cpu]
        if not stack:
            return
        idx = len(stack) - 1
        if match:
            for i in range(len(stack) - 1, -1, -1):
                if match in stack[i]["name"]:
                    idx = i
                    break
        it = stack.pop(idx)
        self.emit_slice(G_IRQ, ("irq", cpu), it["name"], it["ts"],
                        ts - it["ts"], it["cat"], it["args"],
                        track_name="CPU%d IRQ / softirq" % cpu)

    def _life(self, pid, ts, name, args, cpu=None, comm=None, track_name=None):
        if self.opts.no_lifecycle or not self._visible(pid):
            return
        tk = self._thread_key(pid, comm, cpu)
        label = self._thread_label(comm, cpu, pid)
        self.st["life"][pid].add(name.split(":")[0])
        self.emit_instant(G_LIFE, tk, name, ts, "lifecycle", args,
                          track_name=track_name or (label + " 生命周期"))

    def _on_event(self, d):
        ev, ts, cpu, pid, kv = d["event"], d["ts"], d["cpu"], d["pid"], d["kv"]
        if not self._window_ok(ts):
            return
        us = ts * 1e6
        comm, flags, tgid = d["comm"], d["flags"], d["tgid"]

        # ---------- 调度切换 ----------
        if ev == "sched_switch":
            prev_pid = int(kv.get("prev_pid", pid))
            next_pid = int(kv.get("next_pid", 0))
            prev_state = kv.get("prev_state", "?")
            next_comm = kv.get("next_comm", "?")
            self.comm_by_pid.setdefault(next_pid, next_comm)
            self._close_cpu(cpu, us, prev_state)
            self._set_state(prev_pid, state_label(prev_state), us,
                            kv.get("prev_comm"), cpu, raw=prev_state)
            self._open_cpu(cpu, us, next_pid, next_comm, tgid, flags, prev_state)
            self._set_state(next_pid, "RUNNING 正在 CPU 上运行", us, next_comm, cpu)
            return

        # ---------- 唤醒三兄弟 ----------
        if ev in ("sched_waking", "sched_wakeup", "sched_wakeup_new"):
            wpid = int(kv.get("pid", pid))
            tcpu = int(kv["target_cpu"]) if kv.get("target_cpu", "").isdigit() else None
            self.comm_by_pid.setdefault(wpid, kv.get("comm", ""))
            if self.opts.no_flow or not self._visible(wpid):
                return
            if ev == "sched_waking":
                entry = {"fid": None, "ts_waking": us, "ts_wakeup": None,
                         "cpu": tcpu, "causal_fid": None}
                # 优先用仍打开的因果流；若已在 softirq_exit 挂起，且距挂起
                # 不超过 2ms（本轮实测 99.1% 的硬中断后唤醒落在 2ms 内），
                # 则复活它——真实内核里 sched_waking 常在软中断退出之后到达，
                # 旧实现在 softirq_exit 立即 end，会把完整链拦腰截断。
                cfid = self.causal_fid.get(cpu)
                from_open = cfid is not None
                if cfid is None:
                    pc = self.pending_close.get(cpu)
                    if pc and us - pc[1] <= 2000:
                        cfid = pc[0]
                        self.pending_close.pop(cpu, None)
                    else:
                        self._flush_pending_close(cpu)   # 超时：收尾旧挂起流
                if cfid is not None:
                    # 本次唤醒由本 CPU 上的硬中断/软中断引发：把因果流从
                    # IRQ 轨续接到唤醒点，并随 pending 带到 switch 处收尾
                    # （终点落在被唤醒任务上 CPU 的 G_CPU 轨，形成跨轨箭头）。
                    if from_open:
                        self.causal_fid[cpu] = None
                        self.causal_softirq_seen[cpu] = False
                    entry["causal_fid"] = cfid
                    self.st["flow_total"] += 1
                    self.emit_flow(cpu, us, cfid,
                                   "中断/软中断 → 唤醒 %s" % kv.get("comm", ""), "step",
                                   {"woken_pid": wpid, "comm": kv.get("comm", ""),
                                    "target_cpu": tcpu,
                                    "chain": "软中断内" if from_open else "软中断退出后续接"},
                                   group=G_IRQ)
                else:
                    # 非中断引发（任务自发唤醒）：普通 wake2run 流，起点在 CPU 轨
                    self.flow_seq += 1
                    fid = self.flow_seq
                    entry["fid"] = fid
                    self.st["flow_total"] += 1
                    self.emit_flow(tcpu if tcpu is not None else cpu, us, fid,
                                   "sched_waking", "start",
                                   {"pid": wpid, "comm": kv.get("comm", ""),
                                    "target_cpu": tcpu, "flags": flags})
                self.pending_wake[wpid].append(entry)
                self._set_state(wpid, "R 可运行 / 被抢占", us, kv.get("comm"), tcpu)
            else:
                pend = self.pending_wake.get(wpid)
                if pend:
                    w = pend[-1]
                    if w["ts_wakeup"] is None:
                        w["ts_wakeup"] = us
                    cfid = w.get("causal_fid")
                    if cfid is not None:
                        # 因果流：唤醒 → 入队（落到 G_CPU 轨，跨向被唤醒任务）
                        self.emit_flow(tcpu if tcpu is not None else cpu, us, cfid,
                                       "sched_wakeup", "step",
                                       {"pid": wpid, "comm": kv.get("comm", ""),
                                        "target_cpu": tcpu, "flags": flags}, group=G_CPU)
                    else:
                        self.emit_flow(tcpu if tcpu is not None else cpu, us, w["fid"],
                                       ev, "step",
                                       {"pid": wpid, "comm": kv.get("comm", ""),
                                        "target_cpu": tcpu, "flags": flags})
            return

        # ---------- 时间片 / 迁移 / idle 唤醒 ----------
        if ev == "sched_stat_runtime":
            rpid = int(kv.get("pid", pid))
            try:
                self.last_runtime[rpid] = int(kv.get("runtime", "0"))
            except ValueError:
                pass
            return
        if ev == "sched_migrate_task":
            mpid = int(kv.get("pid", pid))
            self._life(mpid, us, "sched_migrate_task", {
                "pid": mpid, "comm": kv.get("comm", ""),
                "orig_cpu": kv.get("orig_cpu"), "dest_cpu": kv.get("dest_cpu"),
                "prio": kv.get("prio"),
            }, cpu=cpu, comm=kv.get("comm", ""))
            return
        if ev == "sched_wake_idle_without_ipi":
            return

        # ---------- 进程生命周期 ----------
        if ev == "sched_process_fork":
            cpid = int(kv.get("child_pid", 0))
            self._life(cpid, us, "sched_process_fork", {
                "parent_pid": pid, "parent_comm": comm,
                "child_pid": cpid, "child_comm": kv.get("child_comm", ""),
            }, cpu=cpu, comm=kv.get("child_comm", ""))
            self._set_state(cpid, "R 可运行 / 被抢占", us, kv.get("child_comm"), cpu)
            return
        if ev == "sched_process_exec":
            epid = int(kv.get("pid", pid))
            self._life(epid, us, "sched_process_exec", {
                "pid": epid, "old_pid": kv.get("old_pid"),
                "filename": kv.get("filename", ""),
            }, cpu=cpu, comm=kv.get("comm", comm))
            return
        if ev in ("sched_process_exit", "sched_process_free", "sched_process_wait"):
            # 关键：被释放的 task 在 args 里，行前缀通常是 <idle> / ksoftirqd
            xpid = int(kv.get("pid", pid))
            self._life(xpid, us, ev, {
                "pid": xpid, "comm": kv.get("comm", ""),
                "prio": kv.get("prio"), "prefix_comm": comm, "prefix_pid": pid,
                "note": "free 的 comm 在 args 里，行前缀不是被释放的 task",
            }, cpu=cpu, comm=kv.get("comm", ""))
            if ev == "sched_process_exit":
                self._set_state(xpid, "X 退出中", us, kv.get("comm"), cpu)
            elif ev == "sched_process_free":
                self._set_state(xpid, "Z 僵尸", us, kv.get("comm"), cpu)
            return

        # ---------- 中断 / 软中断 ----------
        if ev == "irq_handler_entry":
            # 新硬中断到来：先收尾上一条挂起流，再收尾残留（被嵌套）的因果流
            self._flush_pending_close(cpu)
            if self.causal_fid.get(cpu) is not None:
                self._close_intr(cpu, us, "硬中断被嵌套/打断（前一条未收尾）")
            self.flow_seq += 1
            fid = self.flow_seq
            self.causal_fid[cpu] = fid
            self.causal_softirq_seen[cpu] = False
            self.emit_flow(cpu, us, fid,
                           "硬中断 IRQ %s (%s)" % (kv.get("irq", "?"), kv.get("name", "")),
                           "start", {"irq": kv.get("irq"), "name": kv.get("name")},
                           group=G_IRQ)
            self._irq_push(cpu, us, "IRQ %s (%s)" % (kv.get("irq", "?"), kv.get("name", "")),
                           "irq", {"irq": kv.get("irq"), "name": kv.get("name"), "flags": flags})
            return
        if ev == "irq_handler_exit":
            # 本硬中断没产生软中断也没唤醒任务 → 在此闭合因果流
            if self.causal_fid.get(cpu) is not None and not self.causal_softirq_seen.get(cpu):
                self._close_intr(cpu, us, "硬中断结束(未产生软中断唤醒)",
                                {"name": kv.get("name")})
            self._irq_pop(cpu, us, match="IRQ")
            return
        if ev == "softirq_raise":
            vec = kv.get("vec", "?")
            act = kv.get("action", "")
            if not self.opts.no_irq:
                # 中断/软中断因果流：已有打开的流则续接（IRQ→softirq），
                # 否则（softirq 在硬中断上下文外触发）新开一条。
                if self.causal_fid.get(cpu) is not None:
                    self.emit_flow(cpu, us, self.causal_fid[cpu],
                                   "软中断 raise vec=%s [%s]" % (vec, act), "step",
                                   {"vec": vec, "action": act}, group=G_IRQ)
                else:
                    self.flow_seq += 1
                    fid = self.flow_seq
                    self.causal_fid[cpu] = fid
                    self.emit_flow(cpu, us, fid,
                                   "软中断 raise vec=%s [%s]" % (vec, act), "start",
                                   {"vec": vec, "action": act}, group=G_IRQ)
                self.causal_softirq_seen[cpu] = True
                self.emit_instant(G_IRQ, ("irq", cpu),
                                  "softirq_raise vec=%s [%s]" % (vec, act), us, "softirq",
                                  {"vec": vec, "action": act, "flags": flags,
                                   "note": "硬中断里只置位，执行在 softirq_entry"},
                                  track_name="CPU%d IRQ / softirq" % cpu)
            return
        if ev == "napi_poll":
            # 格式是自由文本（非 key=value）：
            #   "napi poll on napi struct <addr> for device eth0 work 0 budget 64"
            # work < budget 表示本轮 RX 队列已排空 → napi_complete() 写 IMS 重开中断。
            rest = d["rest"]
            mdev = re.search(r"for device\s+(\S+)", rest)
            mwork = re.search(r"\bwork\s+(\d+)", rest)
            mbud = re.search(r"\bbudget\s+(\d+)", rest)
            dev = mdev.group(1) if mdev else "?"
            work = mwork.group(1) if mwork else "?"
            bud = mbud.group(1) if mbud else "?"
            if not self.opts.no_irq:
                # 因果流仍打开（napi_poll 恰好落在唤醒之前）→ 续接一个 step；
                # 若晚于唤醒则 causal_fid 已移交 pending，这里不追加，避免箭头倒序。
                if self.causal_fid.get(cpu) is not None:
                    self.emit_flow(cpu, us, self.causal_fid[cpu],
                                   "NAPI poll %s work=%s" % (dev, work), "step",
                                   {"device": dev, "work": work, "budget": bud},
                                   group=G_IRQ)
                self.emit_instant(G_IRQ, ("irq", cpu),
                                  "napi_poll %s work=%s budget=%s" % (dev, work, bud),
                                  us, "napi",
                                  {"device": dev, "work": work, "budget": bud,
                                   "note": "work<budget 表示 RX 队列排空，napi_complete 写 IMS 重开硬中断"},
                                  track_name="CPU%d IRQ / softirq" % cpu)
            return
        if ev == "softirq_entry":
            vec, act = kv.get("vec", "?"), kv.get("action", "")
            self._irq_push(cpu, us, "softirq vec=%s [%s]" % (vec, act), "softirq",
                           {"vec": vec, "action": act, "flags": flags})
            return
        if ev == "softirq_exit":
            # 软中断退出时先「挂起」因果流而不是立刻 end：
            # sched_waking 常在软中断退出之后到达，2ms 内若来唤醒就复活该流，
            # 否则由下一个硬中断 / trace 结束统一收尾（见 _flush_pending_close）。
            if self.causal_fid.get(cpu) is not None:
                self._flush_pending_close(cpu)     # 先清掉更早的挂起流
                fid = self.causal_fid[cpu]
                self.causal_fid[cpu] = None
                self.causal_softirq_seen[cpu] = False
                self.pending_close[cpu] = (fid, us, kv.get("vec", "?"))
            self._irq_pop(cpu, us, match="softirq")
            return
        if ev == "tasklet_entry":
            fn = kv.get("function", "?")
            self._irq_push(cpu, us, "tasklet %s" % fn, "tasklet",
                           {"function": fn, "flags": flags})
            return
        if ev == "tasklet_exit":
            self._irq_pop(cpu, us, match="tasklet")
            return

    def convert(self):
        # 输出文件
        fmt = self.opts.format
        stem = self.opts.output
        if stem.endswith(".json"):
            stem = stem[:-5]
        elif stem.endswith(".pftrace"):
            stem = stem[:-8]
        jpath = stem + ".json" + (".gz" if self.opts.gzip else "")
        ppath = self.opts.pftrace or (stem + ".pftrace")
        if fmt in ("json", "both"):
            self.jw = JsonWriter(jpath, self.opts.gzip)
        if fmt in ("proto", "both"):
            self.pw = ProtoWriter(ppath)

        self.scan()
        self._emit_descriptors()
        self.st["out"]["metadata"] = len(self.tracks) + len(self.group_uuid)

        # 为每条 CPU 泳道补一个「trace 起始」引导 slice。
        # ftrace 开录后到该 CPU 第一次 sched_switch 之间没有任何运行记录，
        # 而 Perfetto 的 Chrome JSON 导入器会认为落在空白段里的 flow 事件
        # 缺少 enclosing slice，从而报 flow_no_enclosing_slice。
        # 补上这段（语义上是「开录瞬间的当前进程，未记录」）即可让泳道全程闭合。
        t_begin = ((self.opts.start if self.opts.start is not None else self.st["tmin"]) * 1e6)
        t_end = (self.opts.end * 1e6) if self.opts.end is not None else self.st["tmax"] * 1e6
        for cpu in sorted(self.st["cpus_seen"]):
            self.cpu_running[cpu] = {
                "pid": 0, "comm": "swapper/%d" % cpu, "tgid": None, "ts": t_begin,
                "flags": "", "wake2run_us": None, "bootstrap": True,
            }
        # IRQ / softirq 轨同样需要一个全程引导 slice，否则挂在该轨上的
        # 「中断 → 软中断 → 唤醒」flow 在 Chrome JSON 导入时会因缺少
        # enclosing slice 被丢弃（flow_no_enclosing_slice）。
        if not self.opts.no_irq:
            for cpu in sorted(self.st["cpus_seen"]):
                self.emit_slice(G_IRQ, ("irq", cpu), "(trace start) IRQ",
                                t_begin, t_end - t_begin, "sched",
                                {"note": "引导 slice，闭合 IRQ/softirq 轨上的 flow"},
                                track_name="CPU%d IRQ / softirq" % cpu)

        for d in self._iter():
            self.cur_stack_args = self._stack_args(d)
            self._on_event(d)
            self.cur_stack_args = {}

        # 收尾：把所有打开的 slice 关到 tmax
        t_end = (self.opts.end * 1e6) if self.opts.end is not None else self.st["tmax"] * 1e6
        for cpu in list(self.cpu_running):
            self._close_cpu(cpu, t_end, "end_of_trace")
        for tk in list(self.state_open):
            cur = self.state_open[tk]
            self.emit_slice(G_STATE, tk, cur["state"], cur["ts"],
                            t_end - cur["ts"], "state",
                            {"comm": cur.get("comm", ""), "note": "trace_end"},
                            track_name=cur.get("label", "") + " 状态")
            self.state_open.pop(tk, None)
        for cpu in list(self.irq_open):
            while self.irq_open[cpu]:
                self._irq_pop(cpu, t_end)
        # 收尾所有挂起/残留的因果流，避免生成 dangling flow
        for cpu in list(self.pending_close):
            self._flush_pending_close(cpu)
        for cpu in list(self.causal_fid):
            self._close_intr(cpu, t_end, "trace 结束(未唤醒)")

        paths = {}
        if self.jw:
            self.jw.close()
            paths["json"] = jpath
        if self.pw:
            self.pw.close()
            paths["pftrace"] = ppath
        return paths

    # ---------------- 统计报告 ----------------
    def report(self, paths, elapsed):
        w = self.st["wake2run_us"]
        w.sort()

        def pct(p):
            if not w:
                return None
            return round(w[min(len(w) - 1, int(len(w) * p))], 3)

        life = self.st["life"]
        closed = [p for p, evs in life.items()
                  if "sched_process_fork" in evs and "sched_process_free" in evs]
        return {
            "tool": "ftrace2perfetto.py", "version": VERSION,
            "input": os.path.abspath(self.opts.input),
            "outputs": {k: os.path.abspath(v) for k, v in paths.items()},
            "options": {
                "format": self.opts.format, "start": self.opts.start, "end": self.opts.end,
                "focus": self.opts.focus, "cpus": self.opts.cpus,
                "no_irq": self.opts.no_irq, "no_flow": self.opts.no_flow,
                "no_thread_state": self.opts.no_thread_state,
                "no_lifecycle": self.opts.no_lifecycle,
                "stacks": getattr(self.opts, "stacks", None),
                "hide_sleep_state": not getattr(self.opts, "show_sleep_state", False),
            },
            "elapsed_sec": round(elapsed, 2),
            "input_stats": {
                "total_lines": self.st["lines"],
                "stack_lines": self.st["stack_lines"],
                "stack_index_entries": sum(len(v) for v in self.stack_map.values()),
                "skipped_lines": self.st["skipped_lines"],
                "tracepoint_events": sum(self.st["in_events"].values()),
                "event_counts": dict(self.st["in_events"].most_common()),
                "time_window_sec": [self.st["tmin"], self.st["tmax"]],
                "cpus": sorted(self.st["cpus_seen"]),
                "distinct_pids": len(self.st["pids_seen"]),
            },
            "output_stats": {
                "events": dict(self.st["out"]),
                "tracks": len(self.tracks),
                "track_groups": len(self.group_uuid),
                "flow_total": self.st["flow_total"],
                "flow_matched_to_switch": self.st["flow_matched"],
                "flow_match_rate": (round(self.st["flow_matched"] / self.st["flow_total"], 4)
                                    if self.st["flow_total"] else None),
            },
            "wake2run_us": {
                "samples": len(w), "p50": pct(0.50), "p95": pct(0.95),
                "p99": pct(0.99), "max": round(w[-1], 3) if w else None,
                "mean": round(sum(w) / len(w), 3) if w else None,
            },
            "lifecycle": {
                "tids_with_events": len(life),
                "tids_fork_to_free_closed": len(closed),
                "sample_closed_tids": sorted(closed)[:10],
            },
        }


# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        description="把 ftrace 文本转换成 Perfetto 可打开的调度 trace",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("用法\n----")[-1] if "用法\n----" in __doc__ else None)
    p.add_argument("input", help="ftrace.log（支持 .gz）")
    p.add_argument("-o", "--output", required=True,
                   help="输出路径（.json / .pftrace / 无后缀均可；both 时自动生成两个）")
    p.add_argument("--format", choices=("json", "proto", "both"), default="both",
                   help="json=Chrome Trace Event；proto=原生 protobuf；both=两个都生成（默认）")
    p.add_argument("--pftrace", help="显式指定 .pftrace 路径（仅 proto/both 有效）")
    p.add_argument("--start", type=float, help="起始时间（ftrace 绝对秒）")
    p.add_argument("--end", type=float, help="结束时间（ftrace 绝对秒）")
    p.add_argument("--cpus", help="只保留这些 CPU，如 0,1（默认全部）")
    p.add_argument("--focus", help="聚焦某个 comm 的正则，只输出相关 tid 的调度与生命周期")
    p.add_argument("--no-irq", action="store_true", help="不生成 IRQ / softirq 轨")
    p.add_argument("--no-flow", action="store_true", help="不生成唤醒 flow 箭头")
    p.add_argument("--no-thread-state", action="store_true", help="不生成线程状态轨")
    p.add_argument("--no-lifecycle", action="store_true", help="不生成进程生命周期轨")
    p.add_argument("--stacks", help="逐条堆栈索引 JSONL（tracepoint_stacks.py --events-out 产出，支持 .gz）；"
                                    "给每个 tracepoint 加 stack_start / stack_end / stack_depth")
    p.add_argument("--show-sleep-state", action="store_true",
                   help="显示 S 可中断睡眠状态段（默认不显示，状态轨上留白）")
    p.add_argument("--max-tracks", type=int, default=1200, help="最多建多少条状态/生命周期轨")
    p.add_argument("--gzip", action="store_true", help="JSON 输出用 gzip 压缩")
    p.add_argument("--stats", help="统计报告 JSON 路径（默认 <output>.stats.json）")
    p.add_argument("--quiet", action="store_true", help="不打印摘要")
    return p


def main():
    opts = build_parser().parse_args()
    if not os.path.isfile(opts.input):
        sys.exit("输入文件不存在: %s" % opts.input)
    os.makedirs(os.path.dirname(os.path.abspath(opts.output)), exist_ok=True)
    t0 = time.time()
    c = Converter(opts)
    paths = c.convert()
    elapsed = time.time() - t0
    rep = c.report(paths, elapsed)
    sp = opts.stats or (os.path.splitext(opts.output)[0] + ".stats.json")
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)

    if not opts.quiet:
        i, o = rep["input_stats"], rep["output_stats"]
        print("输入 : %s" % rep["input"])
        print("       %s 行（其中栈帧 %s），%s 条 tracepoint，%.3f~%.3f s，CPU %s" % (
            f"{i['total_lines']:,}", f"{i['stack_lines']:,}",
            f"{i['tracepoint_events']:,}", i["time_window_sec"][0],
            i["time_window_sec"][1], i["cpus"]))
        print("输出 : %s" % ", ".join("%s=%s" % (k, os.path.basename(v)) for k, v in paths.items()))
        print("       %s 个事件 / %s 条 track，flow %s/%s 匹配到 switch" % (
            f"{sum(o['events'].values()):,}", o["tracks"],
            o["flow_matched_to_switch"], o["flow_total"]))
        w = rep["wake2run_us"]
        if w["samples"]:
            print("       唤醒延迟 wake2run_us: p50=%s p95=%s p99=%s max=%s" % (
                w["p50"], w["p95"], w["p99"], w["max"]))
        print("统计 : %s" % sp)
        print("耗时 : %.1f s" % elapsed)


if __name__ == "__main__":
    main()
