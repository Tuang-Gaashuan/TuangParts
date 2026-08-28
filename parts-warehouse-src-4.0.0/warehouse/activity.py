# -*- coding: utf-8 -*-
"""元器件仓库 — 操作日志 (存入/使用情况)。

每次保存子分类时记录一条日志: 新增/删除/修改了多少行, 数量净变化。
日志存 data/activity_log.jsonl (追加式, 每行一条 JSON)。

界面左侧"滚轮"读取最近的日志展示。
"""

import json
import os
from datetime import datetime

LOG_NAME = "activity_log.jsonl"


def log_path(data_dir: str) -> str:
    return os.path.join(data_dir, LOG_NAME)


def _parse_qty(v) -> int:
    """把数量字段解析为 int, 解析失败返回 0。"""
    try:
        return int(float(str(v).strip()))
    except (ValueError, TypeError):
        return 0


def compute_qty_delta(old_rows: list, new_rows: list, qty_col: int = 3) -> int:
    """比较保存前后的数量变化: 正值=净存入, 负值=净使用。"""
    def total(rows):
        return sum(_parse_qty(r[qty_col]) if len(r) > qty_col else 0 for r in rows)
    return total(new_rows) - total(old_rows)


def record(data_dir: str, subcat: str, old_rows: list, new_rows: list,
           path: str = "") -> dict:
    """写入一条操作日志。返回日志 dict。"""
    old_n, new_n = len(old_rows), len(new_rows)
    delta = compute_qty_delta(old_rows, new_rows)

    if old_n == 0 and new_n > 0:
        action = "存入"
    elif old_n > 0 and new_n == 0:
        action = "清空"
    elif new_n > old_n:
        action = "新增"
    elif new_n < old_n:
        action = "删除"
    else:
        action = "修改"

    entry = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "subcat": subcat,
        "action": action,
        "old": old_n,
        "new": new_n,
        "qty_delta": delta,      # >0 净存入, <0 净使用
        "path": path,
    }
    p = log_path(data_dir)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load(data_dir: str, limit: int = 50) -> list:
    """读取最近 limit 条日志 (新->旧)。"""
    p = log_path(data_dir)
    if not os.path.exists(p):
        return []
    entries = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries[-limit:][::-1]
