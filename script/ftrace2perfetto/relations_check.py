#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关系字段可查询性验证（蓝方 c 方案落地验证）。

对转换器写入 args 的关系字段做实证校验：这些字段必须能被 SQL join 出来，
才说明「任意事件关系可分析」成立，而非只是画了几条启发式箭头。

字段（args 表，key 带 debug. 前缀）：
  debug.causal_id            因果链 ID：同一条链上的所有事件共享
  debug.parent_ts_ns         直接前驱事件时间戳（ns，与 slice.ts 同单位）
  debug.parent_event         直接前驱事件名
  debug.waker_tid/debug.wakee_tid   唤醒者 / 被唤醒者（sched_waking 行前缀 + kv.pid）
  debug.irq_depth/debug.parent_irq_ts_ns  中断嵌套深度 / 父中断时间戳
  debug.lock_holder_tid/debug.lock_holder_inferred  推断持锁者（demo 启发式）

用法:
  python3 relations_check.py trace.pftrace [trace2.pftrace ...]
"""

import argparse
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
]

# 每条查询返回一个标量，key -> SQL
QUERIES = {
    # 1) 前驱边：a.parent_ts_ns 精确等于某个 b.ts → join 命中数
    "predecessor_edges": """
        SELECT count(*) FROM slice a
        JOIN args aa ON a.arg_set_id=aa.arg_set_id AND aa.key='debug.parent_ts_ns'
        JOIN slice b ON CAST(aa.int_value AS INT)=b.ts
    """,
    # 2) 写了 parent_ts_ns 的事件数（分母）
    "events_with_parent": """
        SELECT count(*) FROM args WHERE key='debug.parent_ts_ns'
    """,
    # 3) causal_id 链：不同链数量
    "causal_chains": """
        SELECT count(DISTINCT int_value) FROM args WHERE key='debug.causal_id'
    """,
    # 4) causal_id 链：最大链的事件数（一条链能 join 出多少事件）
    "causal_chain_max_size": """
        SELECT max(n) FROM (
          SELECT int_value, count(*) n FROM args
          WHERE key='debug.causal_id' GROUP BY int_value)
    """,
    # 5) causal_id 覆盖的事件数
    "events_with_causal": """
        SELECT count(*) FROM args WHERE key='debug.causal_id'
    """,
    # 6) 唤醒边 waker->wakee
    "waker_wakee_edges": """
        SELECT count(*) FROM args WHERE key='debug.waker_tid'
    """,
    # 7) 锁持锁者推断覆盖
    "lock_holder_annotations": """
        SELECT count(*) FROM args WHERE key='debug.lock_holder_tid'
    """,
    # 8) 中断嵌套深度 >1 的事件数
    "irq_nested_events": """
        SELECT count(*) FROM args WHERE key='debug.irq_depth' AND int_value>1
    """,
    # 9) slice / args 总数（规模背景）
    "slice_total": "SELECT count(*) FROM slice",
    "args_total": "SELECT count(*) FROM args",
}

# 抽样：一条最大因果链上的事件（名字 + 时间），证明可展开
CHAIN_SAMPLE_SQL = """
SELECT s.name AS event, s.ts AS ts,
       (SELECT int_value FROM args WHERE arg_set_id=s.arg_set_id AND key='debug.causal_id') AS cid,
       (SELECT string_value FROM args WHERE arg_set_id=s.arg_set_id AND key='debug.parent_event') AS parent
FROM slice s
WHERE s.arg_set_id IN (
  SELECT arg_set_id FROM args WHERE key='debug.causal_id'
    AND int_value=(SELECT int_value FROM args WHERE key='debug.causal_id'
                   GROUP BY int_value ORDER BY count(*) DESC LIMIT 1))
ORDER BY s.ts LIMIT 25
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


def run(tps, path, sql, timeout=600):
    r = subprocess.run([tps, "query", path, " ".join(sql.split())],
                       capture_output=True, text=True, timeout=timeout)
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    if r.returncode != 0 and "Trace loaded" not in out:
        return None, out.strip()[:300]
    return out, None


def scalar(out):
    """从 tps 的 CSV-ish 输出里取第一个非表头数字。"""
    for line in (out or "").splitlines():
        line = line.strip()
        if not line or line.startswith('"'):
            continue
        parts = line.split(",")
        if parts:
            v = parts[0].strip().strip('"')
            try:
                return int(v)
            except ValueError:
                try:
                    return float(v)
                except ValueError:
                    return v
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("-o", "--output", help="JSON 报告路径")
    opts = ap.parse_args()
    tps = find_tps()
    if not tps:
        print("找不到 trace_processor_shell", file=sys.stderr)
        sys.exit(2)

    report = []
    for path in opts.files:
        print("==> %s" % path)
        item = {"file": os.path.abspath(path), "size": os.path.getsize(path), "queries": {}}
        for key, sql in QUERIES.items():
            out, err = run(tps, path, sql)
            if err:
                item["queries"][key] = "ERR: " + err
                print("   %-24s %s" % (key, item["queries"][key]))
            else:
                v = scalar(out)
                item["queries"][key] = v
                print("   %-24s %s" % (key, v))
        out, err = run(tps, path, CHAIN_SAMPLE_SQL)
        item["chain_sample"] = out.strip() if not err else ("ERR: " + err)
        # 断言式结论
        q = item["queries"]
        pe = q.get("predecessor_edges")
        wp = q.get("events_with_parent")
        item["verdict"] = {
            "parent_join_ok": isinstance(pe, int) and pe > 0,
            # 命中边数 / 写了 parent 的事件数；可 >1（同一前驱被多个子事件引用）
            "parent_join_ratio": (round(pe / wp, 4) if isinstance(pe, int)
                                  and isinstance(wp, int) and wp else None),
            "causal_id_ok": isinstance(q.get("causal_chains"), int)
                            and q["causal_chains"] > 0,
        }
        report.append(item)

    if opts.output:
        with open(opts.output, "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print("报告写入", opts.output)


if __name__ == "__main__":
    main()
