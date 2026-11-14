#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preview.py — 从生成的 Chrome Trace Event JSON 反绘一张调度泳道预览图
=====================================================================

用途：不开 ui.perfetto.dev 也能快速确认「生成的 perfetto 文件里到底有什么」。
只画 CPU 运行泳道 / IRQ-softirq 泳道 / 选中的线程状态轨，以及唤醒 flow 箭头。

    python3 preview.py out/iperf-zoom.json -o out/overview.png
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

# 中文字体
for fp in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
           "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"):
    if os.path.exists(fp):
        from matplotlib import font_manager
        font_manager.fontManager.addfont(fp)
        plt.rcParams["font.family"] = "Noto Sans CJK JP"
        break
plt.rcParams["axes.unicode_minus"] = False

C_CPU = {"iperf3": "#2563eb", "swapper": "#cbd5e1", "rcu": "#a855f7",
         "ksoftirqd": "#0891b2", "other": "#94a3b8"}
C_IRQ = {"NET_RX": "#0d9488", "NET_TX": "#ea580c", "TIMER": "#7c3aed",
         "SCHED": "#db2777", "RCU": "#94a3b8"}
C_STATE = {"RUN": "#16a34a", "R": "#f59e0b", "S": "#64748b",
           "D": "#dc2626", "other": "#cbd5e1"}


def color_cpu(name):
    for k, v in C_CPU.items():
        if k != "other" and name.startswith(k):
            return v
    return C_CPU["other"]


def color_irq(name):
    for k, v in C_IRQ.items():
        if k in name:
            return v
    return "#94a3b8"


def color_state(name):
    for k, v in C_STATE.items():
        if k != "other" and name.startswith(k):
            return v
    return C_STATE["other"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json", help="Chrome Trace Event JSON（推荐 iperf-zoom.json）")
    ap.add_argument("-o", "--output", default="out/overview.png")
    ap.add_argument("--start", type=float, help="只画这个绝对秒之后的片段")
    ap.add_argument("--end", type=float, help="只画这个绝对秒之前的片段")
    opts = ap.parse_args()

    with open(opts.json, encoding="utf-8") as f:
        data = json.load(f)

    metas = {}
    slices, flows, instants = [], [], []
    for e in data:
        if not isinstance(e, dict):
            continue
        ph = e.get("ph")
        if ph == "M" and e.get("name") == "thread_name":
            metas[(e.get("pid"), e.get("tid"))] = e.get("args", {}).get("name", "")
        elif ph == "X":
            slices.append(e)
        elif ph in ("s", "f"):
            flows.append(e)
        elif ph == "i":
            instants.append(e)

    t0 = min([s["ts"] for s in slices] + [f["ts"] for f in flows])
    t1 = max([s["ts"] + s.get("dur", 0) for s in slices] + [f["ts"] for f in flows])
    if opts.start:
        t0 = max(t0, opts.start * 1e6)
    if opts.end:
        t1 = min(t1, opts.end * 1e6)
    span = max(1.0, t1 - t0)

    groups = defaultdict(list)
    for s in slices:
        if s["ts"] + s.get("dur", 0) < t0 or s["ts"] > t1:
            continue
        groups[(s.get("pid"), s.get("tid"))].append(s)

    # 选择要显示的泳道：CPU(1) → IRQ(3) → 状态轨(2) 里 slice 最多的 3 条
    cpu = sorted([k for k in groups if k[0] == 1])
    irq = sorted([k for k in groups if k[0] == 3])
    state = sorted([k for k in groups if k[0] == 2],
                   key=lambda k: -len(groups[k]))[:3]
    lanes = cpu + irq + state
    ypos = {k: len(lanes) - 1 - i for i, k in enumerate(lanes)}

    H = max(6.0, len(lanes) * 0.62 + 2.2)
    fig, ax = plt.subplots(figsize=(17, H), dpi=150)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    def X(ts):
        return (ts - t0) / 1000.0        # 相对起点，单位 ms

    # 泳道背景
    for k in lanes:
        y = ypos[k]
        c = "#f8fafc" if k[0] != 3 else "#f0fdfa"
        ax.add_patch(Rectangle((0, y - 0.5), X(t1), 1.0, facecolor=c,
                               edgecolor="none", zorder=0))
        ax.axhline(y - 0.5, color="#e2e8f0", lw=0.6, zorder=1)

    # slice
    for k in lanes:
        y = ypos[k]
        for s in sorted(groups[k], key=lambda x: x["ts"]):
            a, b = max(s["ts"], t0), min(s["ts"] + s.get("dur", 0), t1)
            if b <= a:
                continue
            nm = s.get("name", "")
            boot = nm.startswith("(trace start)")
            col = ("#dbe3ec" if boot else
                   color_cpu(nm) if k[0] == 1 else
                   color_irq(nm) if k[0] == 3 else color_state(nm))
            ax.add_patch(Rectangle((X(a), y - 0.30), max(X(b) - X(a), 0.004), 0.60,
                                   facecolor=col,
                                   edgecolor="none" if boot else "white", lw=0.7,
                                   alpha=0.40 if boot else 0.92, zorder=2 if boot else 3))
            w = X(b) - X(a)
            if boot:
                continue          # 技术性引导 slice：淡背景，不标文字
            if k[0] == 1:                       # CPU：进程名:pid
                label = nm if len(nm) <= 18 else nm[:17] + "…"
                thr, fs = 0.16, 7.2
            elif k[0] == 3:                     # IRQ：只显示 [ACTION]
                m = re.search(r"\[([A-Z_]+)\]", nm)
                label = m.group(1) if m else (nm[:16] + "…" if len(nm) > 16 else nm)
                thr, fs = 0.12, 7.6
            else:                               # 状态：短码 R / S / RUN
                head = nm.split()[0] if nm.split() else nm
                label = "RUN" if head.startswith("RUNNING") else head[:2]
                thr, fs = 0.09, 8.5
            if w > thr:
                ax.text(X(a) + w / 2, y, label, ha="center", va="center",
                        fontsize=fs, color="white", fontweight="bold", zorder=4)

    # 唤醒 flow 箭头：按 id 配对 s → f
    byid = defaultdict(list)
    for f in flows:
        byid[f.get("id")].append(f)
    drawn = 0
    for fid, evs in byid.items():
        evs.sort(key=lambda e: e["ts"])
        starts = [e for e in evs if e["ph"] == "s"]
        if not starts:
            continue
        s = starts[0]
        for e in evs[1:]:
            k_src = (s.get("pid"), s.get("tid"))
            k_dst = (e.get("pid"), e.get("tid"))
            y1, y2 = ypos.get(k_src), ypos.get(k_dst)
            if y1 is None or y2 is None or y1 == y2:
                continue
            ax.add_patch(FancyArrowPatch(
                (X(s["ts"]), y1), (X(e["ts"]), y2),
                connectionstyle="arc3,rad=0.18", arrowstyle="-|>",
                mutation_scale=12, lw=1.9, color="#dc2626", alpha=0.9, zorder=6))
            drawn += 1
            break

    # 左侧标签
    for k in lanes:
        y = ypos[k]
        label = metas.get(k, "%s/%s" % k)
        ax.text(-X(t1) * 0.012, y, label, ha="right", va="center",
                fontsize=9, color="#0f172a", fontweight="bold")

    # 分组标题
    for k in lanes:
        y = ypos[k]
        g = {1: "CPU", 2: "状态", 3: "IRQ"}.get(k[0], "")
        ax.text(-X(t1) * 0.075, y, g, ha="center", va="center", fontsize=7.5,
                color="#64748b")

    ax.set_xlim(-X(t1) * 0.14, X(t1) * 1.01)
    ax.set_ylim(-1.0, len(lanes) + 0.2)
    ax.set_yticks([])
    ax.set_xlabel("相对时间（ms） · 数据源：%s" % os.path.basename(opts.json),
                  fontsize=10, color="#475569", labelpad=8)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(axis="x", colors="#475569", labelsize=9)
    ax.grid(axis="x", color="#e2e8f0", lw=0.6, zorder=1)
    ax.set_title("生成的 Perfetto trace · 调度泳道预览（红箭头 = 唤醒/中断因果 flow）",
                 fontsize=14, color="#0f172a", fontweight="bold", pad=14)

    # 底部图例
    legend = [("CPU: iperf3", C_CPU["iperf3"]), ("CPU: idle", C_CPU["swapper"]),
              ("IRQ: NET_RX", C_IRQ["NET_RX"]), ("IRQ: TIMER/SCHED", C_IRQ["TIMER"]),
              ("状态: RUN", C_STATE["RUN"]), ("状态: R", C_STATE["R"]),
              ("状态: S", C_STATE["S"]), ("因果/唤醒 flow", "#dc2626")]
    for i, (name, col) in enumerate(legend):
        x = 0.01 + i * 0.123
        fig.patches.append(Rectangle((x, 0.020), 0.014, 0.014,
                                     transform=fig.transFigure, facecolor=col,
                                     edgecolor="none", clip_on=False))
        fig.text(x + 0.018, 0.022, name, fontsize=8.5, color="#475569",
                 va="bottom")

    plt.tight_layout(rect=(0.09, 0.062, 1, 1))
    os.makedirs(os.path.dirname(os.path.abspath(opts.output)), exist_ok=True)
    plt.savefig(opts.output, dpi=150, facecolor="white")
    print("预览图: %s  (%d 条泳道, %d 条 flow 箭头, 窗口 %.3f ms)" % (
        opts.output, len(lanes), drawn, span / 1000.0))


if __name__ == "__main__":
    main()
