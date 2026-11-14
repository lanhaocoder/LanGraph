#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify.py — 用官方 Perfetto trace_processor_shell 校验生成的 trace 文件
=====================================================================

用法:
    python3 verify.py out/iperf-lifecycle.pftrace
    python3 verify.py out/*.json --json-out verify.json

校验项:
  1. 文件能否被官方工具加载
  2. Trace health issues（导入错误 / 数据丢失）
  3. slice / flow / track / args 数量
  4. 六类生命周期 instant 事件计数（应与原始 ftrace 一致）
  5. wake2run_us 是否落入 args
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

TPS_CANDIDATES = [
    "trace_processor_shell",
    "/tmp/tps_dl/linux-amd64/trace_processor_shell",
    "/usr/local/bin/trace_processor_shell",
    "./trace_processor_shell",
]

COUNT_SQL = """
SELECT 'slice' k, count(*) n FROM slice
UNION ALL SELECT 'flow', count(*) FROM flow
UNION ALL SELECT 'track', count(*) FROM track
UNION ALL SELECT 'args', count(*) FROM args;
"""

LIFE_SQL = """
SELECT name, count(*) n FROM slice
WHERE dur = 0 AND name LIKE 'sched_process%'
GROUP BY name ORDER BY n DESC;
"""

WAKE_SQL = """
SELECT count(*) n, round(avg(real_value), 1) mean_us,
       min(real_value) min_us, max(real_value) max_us
FROM args WHERE key LIKE '%wake2run_us';
"""


def find_tps():
    for c in TPS_CANDIDATES:
        if os.path.isabs(c):
            if os.path.isfile(c) and os.access(c, os.X_OK):
                return c
        else:
            p = shutil.which(c)
            if p:
                return p
    return None


def run(tps, path, sql, timeout=300):
    try:
        r = subprocess.run([tps, "query", path, sql], capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    out = r.stdout + "\n" + r.stderr
    if r.returncode != 0 and "Trace loaded" not in out:
        return None, out.strip()[:400]
    return out, None


def parse_rows(out):
    """解析 trace_processor_shell 的 CSV-ish 输出。"""
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith('"') and not re.match(r"^\d", line):
            continue
        parts = [p.strip('"') for p in line.split(",")]
        rows.append(parts)
    return rows


def health(out):
    if "Trace health issues" not in out:
        return []
    seg = out.split("Trace health issues", 1)[1].split("Query executed")[0]
    issues = [ln.strip() for ln in seg.splitlines()
              if re.match(r"^[A-Za-z_][A-Za-z0-9_]*:\s*\d+", ln.strip())]
    return issues[:8]


def verify_one(tps, path):
    res = {"file": os.path.abspath(path), "size": os.path.getsize(path)}
    out, err = run(tps, path, COUNT_SQL)
    if err:
        res["ok"] = False
        res["error"] = err
        return res
    res["ok"] = True
    res["health"] = health(out)
    res["counts"] = {}
    for row in parse_rows(out):
        if len(row) >= 2 and row[0] in ("slice", "flow", "track", "args"):
            try:
                res["counts"][row[0]] = int(row[1])
            except ValueError:
                pass
    out2, _ = run(tps, path, LIFE_SQL)
    res["lifecycle"] = {}
    if out2:
        for row in parse_rows(out2):
            if len(row) >= 2 and row[0].startswith("sched_process"):
                try:
                    res["lifecycle"][row[0]] = int(row[1])
                except ValueError:
                    pass
    out3, _ = run(tps, path, WAKE_SQL)
    if out3:
        rows = [r for r in parse_rows(out3) if len(r) >= 2 and r[0].isdigit()]
        if rows:
            try:
                res["wake2run_us"] = {
                    "args_entries": int(rows[0][0]),
                    "mean": float(rows[0][1]) if rows[0][1] != "[NULL]" else None,
                }
            except (ValueError, IndexError):
                pass
    return res


def main():
    ap = argparse.ArgumentParser(description="校验 ftrace2perfetto.py 产出的文件")
    ap.add_argument("files", nargs="+", help="trace 文件（支持通配）")
    ap.add_argument("--tps", help="trace_processor_shell 路径")
    ap.add_argument("--json-out", help="把结果写成 JSON")
    opts = ap.parse_args()

    tps = opts.tps or find_tps()
    if not tps:
        print("找不到 trace_processor_shell；请用 --tps 指定路径。", file=sys.stderr)
        print("下载：https://github.com/google/perfetto/releases 或 apt install perfetto", file=sys.stderr)
        return 2

    files = []
    for pat in opts.files:
        files.extend(sorted(glob.glob(pat)))
    # 统计报告 / 校验结果本身不是 trace，跳过
    files = [f for f in files
             if not f.endswith(".stats.json") and not f.endswith("verify.json")]
    if not files:
        print("没有匹配的文件", file=sys.stderr)
        return 2

    print("验证工具: %s\n" % tps)
    results = []
    for f in files:
        r = verify_one(tps, f)
        results.append(r)
        tag = "OK  " if r["ok"] and not r.get("health") else "WARN" if r["ok"] else "FAIL"
        print("[%s] %s (%.2f MB)" % (tag, os.path.basename(f), r["size"] / 1024 / 1024))
        if not r["ok"]:
            print("      错误: %s" % r.get("error"))
            continue
        print("      slice=%s flow=%s track=%s args=%s" % (
            r["counts"].get("slice"), r["counts"].get("flow"),
            r["counts"].get("track"), r["counts"].get("args")))
        if r["lifecycle"]:
            print("      生命周期: %s" % ", ".join("%s=%s" % kv for kv in r["lifecycle"].items()))
        if r.get("wake2run_us"):
            print("      wake2run args: %s 条, 均值 %s µs" % (
                r["wake2run_us"]["args_entries"], r["wake2run_us"]["mean"]))
        if r["health"]:
            print("      health: %s" % r["health"][:2])
        print()

    if opts.json_out:
        with open(opts.json_out, "w", encoding="utf-8") as fp:
            json.dump(results, fp, ensure_ascii=False, indent=2)
        print("结果写入: %s" % opts.json_out)
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
