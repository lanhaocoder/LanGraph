#!/usr/bin/env python3
"""把 ftrace.log 里每个 tracepoint 的调用栈抽出来，按「起始帧 / 末尾帧」汇总打印。

ftrace 中每个事件行后面紧跟两类堆栈块：

    <stack trace>          + 若干 " => sym+0x/0x <addr>"   （内核栈）
    <user stack trace>     + 若干 " => ..."                （用户栈，可选）

栈帧书写顺序是 **栈顶（最内层、事件触发的直接调用点） → 栈底（最外层、调用链入口）**。
因此本报告定义：

    起始堆栈 = 第一帧（栈顶，直接调用点）
    末尾堆栈 = 最后一帧（栈底，调用链入口，通常是中断/系统调用/调度器入口）

归属要点：`<stack trace>` / `<user stack trace>` 标记行**自带 CPU**，而栈帧行
(" => ...") 不带任何行头。trace 文件按时间戳合并 4 个 CPU 的 buffer，事件行之间会
插入其它 CPU 的事件行，所以必须**按标记行的 CPU 去找该 CPU 最近的事件**，
不能用「全局最近的事件行」，否则栈会错配到别的 CPU / 别的 tracepoint 上。

输出：
  -o/--out          人可读文本报告
  --json            结构化汇总（按 tracepoint 聚合）
  --events-out      逐条 JSONL（每条事件的起始帧/末尾帧，供转换工具消费）
  --html            自包含展示页
  --samples         逐条示例条数（默认 20）
"""
import argparse
import html
import json
import re
from collections import Counter

# 事件行 / 堆栈标记行的公共行头
HEAD_RE = re.compile(
    r"^\s*(?P<comm>.+?)-(?P<pid>\d+)\s+\((?P<tgid>[^)]*)\)\s+"
    r"\[(?P<cpu>\d+)\]\s+(?P<flags>\S+)\s+"
    r"(?P<ts>\d+\.\d+):\s+(?P<rest>.*)$"
)
FRAME_RE = re.compile(r"^\s*=>\s+(?P<sym>.*?)\s*<(?P<addr>[0-9A-Fa-fx]+)>\s*$")
EVENT_RE = re.compile(r"^(?P<event>[A-Za-z_][A-Za-z0-9_]*):\s*(?P<args>.*)$")

KSTACK_MARK = "<stack trace>"
USTACK_MARK = "<user stack trace>"


def norm(sym):
    """归一化符号名，便于按函数聚合。

    内核帧  __napi_poll+0x9b/0x200   -> __napi_poll
    用户帧  /bin/busybox[+0xb22e0]   -> /bin/busybox
    未符号化 <0x413f5a>              -> <0x413f5a>（原样保留，不再变成空串）
    """
    s = sym.strip()
    if s.startswith("<0x"):
        return s
    if s.endswith("]"):
        i = s.rfind("[+")
        if i > 0:
            return s[:i]
    i = s.find("+0x")
    if i > 0:
        s = s[:i]
    return s or "<unknown>"


class Agg:
    """单个 tracepoint 的聚合结果（常驻内存很小，只存计数 + 一份样例）。"""

    def __init__(self):
        self.count = 0
        self.kstack = 0
        self.ustack = 0
        self.kframes = 0
        self.uframes = 0
        self.kdepth_min = None
        self.kdepth_max = 0
        self.start_k = Counter()
        self.end_k = Counter()
        self.start_u = Counter()
        self.end_u = Counter()
        self.sample = None
        self.first_ts = None
        self.last_ts = None

    def add(self, ev):
        self.count += 1
        ts = float(ev["ts"])
        if self.first_ts is None:
            self.first_ts = ts
        self.last_ts = ts
        k, u = ev["kernel"], ev["user"]
        if k:
            self.kstack += 1
            self.kframes += len(k)
            d = len(k)
            self.kdepth_min = d if self.kdepth_min is None else min(self.kdepth_min, d)
            self.kdepth_max = max(self.kdepth_max, d)
            self.start_k[norm(k[0])] += 1
            self.end_k[norm(k[-1])] += 1
        if u:
            self.ustack += 1
            self.uframes += len(u)
            self.start_u[norm(u[0])] += 1
            self.end_u[norm(u[-1])] += 1
        if self.sample is None and k:
            self.sample = {
                "ts": ev["ts"], "cpu": ev["cpu"], "comm": ev["comm"],
                "pid": ev["pid"], "flags": ev["flags"],
                "event": ev["event"], "args": ev["args"],
                "kernel": k, "user": u,
            }

    def as_dict(self, topn=10):
        kd = (self.kframes / self.kstack) if self.kstack else 0
        return {
            "count": self.count,
            "with_kernel_stack": self.kstack,
            "with_user_stack": self.ustack,
            "kernel_frames": self.kframes,
            "kernel_depth": {
                "min": self.kdepth_min or 0, "max": self.kdepth_max,
                "mean": round(kd, 2),
            },
            "first_ts": self.first_ts, "last_ts": self.last_ts,
            "start_frames_top": self.start_k.most_common(topn),
            "end_frames_top": self.end_k.most_common(topn),
            "user_start_frames_top": self.start_u.most_common(topn),
            "user_end_frames_top": self.end_u.most_common(topn),
            "sample": self.sample,
        }


def parse(path, samples=20, topn=10, events_out=None):
    agg = {}
    per_event_examples = []
    # 每个 CPU 上「最近一个事件」，stack 标记行按自己的 CPU 来取，避免跨 CPU 错配
    cur_by_cpu = {}
    active = None       # {"cpu", "kind", "ev"}：当前正在收集的堆栈块
    totals = {
        "event_lines": 0, "kernel_stack_blocks": 0, "user_stack_blocks": 0,
        "kernel_frames": 0, "user_frames": 0, "other_lines": 0,
        "events_without_kstack": 0, "orphan_frames": 0,
        "unresolved_user_syms": 0,
    }
    ef = open(events_out, "w") if events_out else None

    def flush(ev):
        """事件的所有堆栈已收齐，提交聚合。"""
        if ev is None:
            return
        if not ev["kernel"]:
            totals["events_without_kstack"] += 1
        name = ev["event"]
        agg.setdefault(name, Agg()).add(ev)
        if len(per_event_examples) < samples:
            k, u = ev["kernel"], ev["user"]
            per_event_examples.append({
                "ts": ev["ts"], "cpu": ev["cpu"], "comm": ev["comm"],
                "pid": ev["pid"], "event": name, "args": ev["args"],
                "start": k[0] if k else "", "end": k[-1] if k else "",
                "kernel_depth": len(k),
                "user_start": u[0] if u else "", "user_end": u[-1] if u else "",
                "user_depth": len(u),
            })
        if ef:
            k, u = ev["kernel"], ev["user"]
            ef.write(json.dumps({
                "ts": ev["ts"], "cpu": ev["cpu"], "comm": ev["comm"],
                "pid": ev["pid"], "event": name,
                "start": k[0] if k else "", "end": k[-1] if k else "",
                "start_sym": norm(k[0]) if k else "", "end_sym": norm(k[-1]) if k else "",
                "depth": len(k),
                "user_start": u[0] if u else "", "user_end": u[-1] if u else "",
            }, ensure_ascii=False) + "\n")

    with open(path, "r", errors="replace", buffering=1 << 20) as f:
        for line in f:
            s = line.rstrip("\n")

            # ---- 栈帧行（无行头，归属由 active 决定）----
            if s.startswith(" =>") or s.lstrip().startswith("=>"):
                m = FRAME_RE.match(s)
                if m:
                    sym = m.group("sym").strip()
                    if not sym:
                        # 用户栈地址未能符号化：=>  <0000000000413f5a>
                        addr = m.group("addr").lstrip("0") or "0"
                        sym = "<0x%s>" % addr
                        totals["unresolved_user_syms"] += 1
                    if active is None or active["ev"] is None:
                        totals["orphan_frames"] += 1
                    else:
                        ev = active["ev"]
                        if active["kind"] == "kernel":
                            ev["kernel"].append(sym)
                            totals["kernel_frames"] += 1
                        else:
                            ev["user"].append(sym)
                            totals["user_frames"] += 1
                continue

            if not s or s.startswith("#"):
                continue
            m = HEAD_RE.match(s)
            if not m:
                totals["other_lines"] += 1
                continue

            cpu = m.group("cpu")
            rest = m.group("rest")

            # ---- 堆栈标记行：按自己的 CPU 找 owner ----
            if KSTACK_MARK in rest:
                totals["kernel_stack_blocks"] += 1
                active = {"cpu": cpu, "kind": "kernel", "ev": cur_by_cpu.get(cpu)}
                continue
            if USTACK_MARK in rest:
                totals["user_stack_blocks"] += 1
                active = {"cpu": cpu, "kind": "user", "ev": cur_by_cpu.get(cpu)}
                continue

            # ---- 事件行 ----
            em = EVENT_RE.match(rest)
            if not em:
                totals["other_lines"] += 1
                continue
            active = None
            # 同 CPU 的前一个事件已收齐所有堆栈，提交
            flush(cur_by_cpu.get(cpu))
            cur_by_cpu[cpu] = {
                "ts": m.group("ts"), "cpu": cpu,
                "comm": m.group("comm").strip(), "pid": m.group("pid"),
                "flags": m.group("flags"),
                "event": em.group("event"), "args": em.group("args").strip(),
                "kernel": [], "user": [],
            }
            totals["event_lines"] += 1

    for ev in cur_by_cpu.values():
        flush(ev)
    if ef:
        ef.close()

    result = {
        "source": path,
        "totals": totals,
        "tracepoints": {name: a.as_dict(topn) for name, a in
                        sorted(agg.items(), key=lambda kv: -kv[1].count)},
        "per_event_examples": per_event_examples,
    }
    return result


NOTES = """数据说明（读栈前必看）：
1. trace 文件按时间戳合并 4 个 CPU 的 per-CPU buffer，事件行之间会插入其它 CPU 的
   事件行。`<stack trace>` 标记行自带 CPU，本报告按该 CPU 归属，避免栈错配。
2. ftrace 的 stacktrace 抓的是「事件提交那一刻 CPU 上的完整内核栈」，因此栈里会
   包含 **ftrace 采集器自身的帧**（stack_trace_save_user / ftrace_trace_userstack /
   trace_event_buffer_commit / trace_event_raw_event_* 等），甚至嵌套上一次 tracepoint
   的采集路径。这不是脏数据，但读调用链时要把这些帧跳过。
3. 栈很深（均值 15~29 帧，最深 125 帧），因为 TCG 下中断/软中断经常嵌套，
   且栈底一直回溯到 CPU 启动路径。末尾帧常见 secondary_startup_64_no_verify
   （CPU 启动栈底）或 entry_SYSCALL_64_after_hwframe（系统调用入口）。
4. 用户栈多为未符号化地址（Guest 内 busybox/perf.bin 无符号表），显示成 <0x...>。
"""


def render_txt(r, topn=10):
    t = r["totals"]
    L = []
    L.append("=" * 78)
    L.append("ftrace tracepoint 调用栈报告")
    L.append("=" * 78)
    L.append(f"源: {r['source']}")
    L.append("")
    L.append(f"事件行            {t['event_lines']:>10,}")
    L.append(f"内核栈块          {t['kernel_stack_blocks']:>10,}  ({t['kernel_stack_blocks']/max(t['event_lines'],1)*100:.1f}%)")
    L.append(f"用户栈块          {t['user_stack_blocks']:>10,}  ({t['user_stack_blocks']/max(t['event_lines'],1)*100:.1f}%)")
    L.append(f"内核栈帧          {t['kernel_frames']:>10,}")
    L.append(f"用户栈帧          {t['user_frames']:>10,}")
    L.append(f"未符号化用户帧    {t['unresolved_user_syms']:>10,}")
    L.append(f"无内核栈事件      {t['events_without_kstack']:>10,}")
    L.append(f"孤立帧/未识别行   {t['orphan_frames']:>10,} / {t['other_lines']:,}")
    L.append("")
    L.append("栈帧顺序: 栈顶(最内层/触发点) → 栈底(最外层/入口)")
    L.append("起始堆栈 = 第一帧(栈顶)    末尾堆栈 = 最后一帧(栈底)")
    L.append("")
    L.append(NOTES)
    L.append("-" * 78)
    L.append("目录（按事件数降序）")
    L.append("-" * 78)
    for name, d in r["tracepoints"].items():
        L.append(f"  {name:<32} {d['count']:>8,}  栈深 {d['kernel_depth']['min']:>2}~{d['kernel_depth']['max']:>2} (均 {d['kernel_depth']['mean']})")
    L.append("")

    for name, d in r["tracepoints"].items():
        L.append("=" * 78)
        L.append(f"## {name}")
        L.append("=" * 78)
        L.append(f"次数          {d['count']:>10,}")
        L.append(f"带内核栈      {d['with_kernel_stack']:>10,}")
        L.append(f"带用户栈      {d['with_user_stack']:>10,}")
        kd = d["kernel_depth"]
        L.append(f"内核栈深      min {kd['min']} / mean {kd['mean']} / max {kd['max']}")
        L.append("")
        L.append("### 起始堆栈（栈顶 / 事件触发的直接调用点） Top %d" % topn)
        for sym, n in d["start_frames_top"]:
            L.append(f"  {n:>9,}  {sym}")
        L.append("")
        L.append("### 末尾堆栈（栈底 / 调用链入口） Top %d" % topn)
        for sym, n in d["end_frames_top"]:
            L.append(f"  {n:>9,}  {sym}")
        L.append("")
        if d["user_start_frames_top"]:
            L.append("### 用户栈 起始帧 Top 5")
            for sym, n in d["user_start_frames_top"][:5]:
                L.append(f"  {n:>9,}  {sym}")
            L.append("")
            L.append("### 用户栈 末尾帧 Top 5")
            for sym, n in d["user_end_frames_top"][:5]:
                L.append(f"  {n:>9,}  {sym}")
            L.append("")
        s = d["sample"]
        if s:
            L.append(f"### 完整样例  t={s['ts']}  cpu={s['cpu']}  {s['comm']}:{s['pid']}  flags={s['flags']}")
            L.append(f"    {s['event']}: {s['args']}")
            L.append(f"    -- 内核栈（{len(s['kernel'])} 帧，栈顶 → 栈底）--")
            for i, fr in enumerate(s["kernel"]):
                tag = "起始" if i == 0 else ("末尾" if i == len(s["kernel"]) - 1 else "    ")
                L.append(f"    [{tag}] {i:>2}  => {fr}")
            if s["user"]:
                L.append(f"    -- 用户栈（{len(s['user'])} 帧）--")
                for i, fr in enumerate(s["user"]):
                    tag = "起始" if i == 0 else ("末尾" if i == len(s["user"]) - 1 else "    ")
                    L.append(f"    [{tag}] {i:>2}  => {fr}")
            L.append("")

    L.append("=" * 78)
    L.append("逐条示例：每条 tracepoint 的「起始帧 / 末尾帧」")
    L.append("=" * 78)
    for e in r["per_event_examples"]:
        L.append(f"t={e['ts']}  cpu={e['cpu']}  {e['comm']}:{e['pid']}  {e['event']}")
        L.append(f"  参数      {e['args'][:110]}")
        L.append(f"  起始堆栈  => {e['start']}   (内核栈 {e['kernel_depth']} 帧)")
        L.append(f"  末尾堆栈  => {e['end']}")
        if e["user_start"]:
            L.append(f"  用户栈起  => {e['user_start']}")
            L.append(f"  用户栈末  => {e['user_end']}")
        L.append("")
    return "\n".join(L)


def render_html(r, topn=10):
    t = r["totals"]
    P = []
    P.append("<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>")
    P.append("<title>ftrace tracepoint 调用栈</title>")
    P.append("""<style>
body{font:14px/1.6 -apple-system,Segoe UI,Consolas,monospace;max-width:1100px;margin:32px auto;padding:0 20px;color:#1f2328}
h1{font-size:22px} h2{font-size:17px;margin-top:36px;border-bottom:2px solid #d0d7de;padding-bottom:6px}
table{border-collapse:collapse;width:100%;margin:10px 0} th,td{border:1px solid #d0d7de;padding:5px 9px;text-align:left;vertical-align:top}
th{background:#f6f8fa} td.n{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
code,pre{font-family:Consolas,Menlo,monospace} pre{background:#f6f8fa;padding:12px;border-radius:6px;overflow-x:auto;font-size:12.5px;line-height:1.45}
.tag{display:inline-block;padding:0 6px;border-radius:3px;font-size:12px;font-weight:600}
.st{background:#dafbe1;color:#116329} .en{background:#ddf4ff;color:#0969da}
.meta{color:#57606a} .summary{background:#fff8c5;border-left:4px solid #d4a72c;padding:10px 14px}
.notes{background:#f6f8fa;border-left:4px solid #6e7781;padding:10px 14px;white-space:pre-wrap;font-size:13px}
</style></head><body>""")
    P.append("<h1>ftrace tracepoint 调用栈报告</h1>")
    P.append(f"<p class='meta'>源：<code>{html.escape(r['source'])}</code></p>")
    P.append("<div class='summary'>每个事件行都带一个内核调用栈，栈帧顺序为 <b>栈顶（最内层 / 触发点）→ 栈底（最外层 / 入口）</b>。"
             "本报告把 <span class='tag st'>起始堆栈</span> 定义为第一帧、"
             "<span class='tag en'>末尾堆栈</span> 定义为最后一帧。</div>")
    P.append("<table><tr><th>项目</th><th>数量</th></tr>")
    for k, label in [("event_lines", "事件行"), ("kernel_stack_blocks", "内核栈块"),
                     ("user_stack_blocks", "用户栈块"), ("kernel_frames", "内核栈帧"),
                     ("user_frames", "用户栈帧"), ("unresolved_user_syms", "未符号化用户帧"),
                     ("events_without_kstack", "无内核栈事件"),
                     ("orphan_frames", "孤立帧"), ("other_lines", "其他/未识别行")]:
        P.append(f"<tr><td>{label}</td><td class='n'>{t[k]:,}</td></tr>")
    P.append("</table>")
    P.append(f"<div class='notes'>{html.escape(NOTES)}</div>")

    P.append("<h2>目录（按事件数降序）</h2><table><tr><th>tracepoint</th><th>次数</th><th>栈深 min/mean/max</th></tr>")
    for name, d in r["tracepoints"].items():
        kd = d["kernel_depth"]
        P.append(f"<tr><td><a href='#{html.escape(name)}'><code>{html.escape(name)}</code></a></td>"
                 f"<td class='n'>{d['count']:,}</td><td class='n'>{kd['min']} / {kd['mean']} / {kd['max']}</td></tr>")
    P.append("</table>")

    for name, d in r["tracepoints"].items():
        P.append(f"<h2 id='{html.escape(name)}'><code>{html.escape(name)}</code></h2>")
        P.append(f"<p class='meta'>次数 {d['count']:,} · 带内核栈 {d['with_kernel_stack']:,} · "
                 f"带用户栈 {d['with_user_stack']:,}</p>")
        for title, key, cls in [("起始堆栈（栈顶 / 直接调用点）", "start_frames_top", "st"),
                                ("末尾堆栈（栈底 / 调用链入口）", "end_frames_top", "en")]:
            P.append(f"<p><span class='tag {cls}'>{title}</span></p>")
            P.append("<table><tr><th>次数</th><th>函数</th></tr>")
            for sym, n in d[key]:
                P.append(f"<tr><td class='n'>{n:,}</td><td><code>{html.escape(sym)}</code></td></tr>")
            P.append("</table>")
        s = d["sample"]
        if s:
            P.append(f"<p class='meta'>完整样例 t={s['ts']} cpu={s['cpu']} "
                     f"{html.escape(s['comm'])}:{s['pid']} flags={s['flags']}</p>")
            P.append("<pre>")
            P.append(html.escape(f"{s['event']}: {s['args']}"))
            P.append("\n-- 内核栈（栈顶 → 栈底）--")
            for i, fr in enumerate(s["kernel"]):
                tag = "起始" if i == 0 else ("末尾" if i == len(s["kernel"]) - 1 else "    ")
                P.append(f"\n[{tag}] {i:>2}  => {html.escape(fr)}")
            if s["user"]:
                P.append("\n-- 用户栈 --")
                for i, fr in enumerate(s["user"]):
                    tag = "起始" if i == 0 else ("末尾" if i == len(s["user"]) - 1 else "    ")
                    P.append(f"\n[{tag}] {i:>2}  => {html.escape(fr)}")
            P.append("</pre>")
    P.append("</body></html>")
    return "\n".join(P)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("-o", "--out", help="文本报告路径")
    ap.add_argument("--json", help="结构化汇总路径")
    ap.add_argument("--events-out", help="逐条 JSONL（每条事件起始/末尾帧）")
    ap.add_argument("--html", help="自包含展示页路径")
    ap.add_argument("--samples", type=int, default=20)
    ap.add_argument("--topn", type=int, default=10)
    a = ap.parse_args()

    r = parse(a.log, samples=a.samples, topn=a.topn, events_out=a.events_out)
    txt = render_txt(r, topn=a.topn)
    if a.out:
        with open(a.out, "w") as f:
            f.write(txt + "\n")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
    if a.html:
        with open(a.html, "w") as f:
            f.write(render_html(r, topn=a.topn))

    t = r["totals"]
    print(f"解析完成: 事件 {t['event_lines']:,} / 内核栈块 {t['kernel_stack_blocks']:,} / "
          f"用户栈块 {t['user_stack_blocks']:,} / 内核栈帧 {t['kernel_frames']:,} / 用户栈帧 {t['user_frames']:,}")
    print(f"无内核栈事件 {t['events_without_kstack']:,} / 孤立帧 {t['orphan_frames']:,} / "
          f"未符号化用户帧 {t['unresolved_user_syms']:,}")
    print(f"tracepoint 种类: {len(r['tracepoints'])}")
    print()
    print(f"{'tracepoint':<32} {'次数':>9}  {'起始帧(栈顶)':<46} 末尾帧(栈底)")
    print("-" * 130)
    for name, d in r["tracepoints"].items():
        st = d["start_frames_top"][0][0] if d["start_frames_top"] else "-"
        en = d["end_frames_top"][0][0] if d["end_frames_top"] else "-"
        print(f"{name:<32} {d['count']:>9,}  {st[:45]:<46} {en}")
    for p in (a.out, a.json, a.events_out, a.html):
        if p:
            print(f"产物: {p}")


if __name__ == "__main__":
    main()
