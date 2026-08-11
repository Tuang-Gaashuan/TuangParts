# -*- coding: utf-8 -*-
"""元器件仓库 — 撤回系统 (undo)。

每次修改库存的操作 (取出/增加/保存/合并/批量导入/归类/删除) 自动把
操作前的数据快照记录到 data/undo_log.jsonl。界面「↩ 撤回」弹窗列出
最近操作, 点某条即恢复该操作前的数据 (一步一撤, 可连续撤回)。

快照结构: [{subcat, old_rows}, ...]  (一次操作可含多个子分类快照)
特殊 subcat "__unclassified__" 表示未分类文件 (data/未分类/未分类.xlsx)。
"""

import json
import os
from datetime import datetime

from warehouse.config import COMMON_FIELDS

UNDO_FILE = "undo_log.jsonl"
MAX_ENTRIES = 60   # 最多保留 60 条可撤回操作
UNCAT_KEY = "__unclassified__"


def _path(data_dir: str) -> str:
    return os.path.join(data_dir, UNDO_FILE)


def load_all(data_dir: str) -> list:
    p = _path(data_dir)
    if not os.path.exists(p):
        return []
    entries = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _write_all(data_dir: str, entries: list):
    p = _path(data_dir)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def push(data_dir: str, snapshots: list, action: str = ""):
    """记录一次可撤回操作。snapshots: [{subcat, old_rows}, ...]。"""
    if not snapshots:
        return
    entries = load_all(data_dir)
    entries.append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "snapshots": snapshots,
    })
    if len(entries) > MAX_ENTRIES:
        entries = entries[-MAX_ENTRIES:]
    _write_all(data_dir, entries)


def list_recent(data_dir: str, limit: int = 15) -> list:
    """最近可撤回操作 (新→旧): [{time, action, subcat, n}]。"""
    out = []
    for e in reversed(load_all(data_dir)):
        snaps = e.get("snapshots") or []
        if not snaps:
            continue
        subcats = [
            "未分类" if s.get("subcat") == UNCAT_KEY else s.get("subcat", "")
            for s in snaps
        ]
        out.append({
            "time": e.get("time", ""),
            "action": e.get("action", ""),
            "subcat": "、".join(dict.fromkeys(subcats)),   # 去重保序
            "n": len(snaps),
        })
        if len(out) >= limit:
            break
    return out


def undo(data_dir: str, time: str) -> dict | None:
    """撤回指定时间的操作: 恢复所有快照, 并从 undo 栈移除该条。"""
    entries = load_all(data_dir)
    idx = -1
    for i in range(len(entries) - 1, -1, -1):
        if entries[i].get("time") == time:
            idx = i
            break
    if idx < 0:
        return None
    entry = entries.pop(idx)
    _write_all(data_dir, entries)

    from warehouse.excel_store import ExcelStore
    store = ExcelStore(data_dir)
    headers = [label for _, label in COMMON_FIELDS]
    restored = []
    for snap in entry.get("snapshots") or []:
        subcat = snap.get("subcat", "")
        old_rows = snap.get("old_rows") or []
        if subcat == UNCAT_KEY:
            from warehouse import unclassified
            unclassified._save(data_dir, unclassified.HEADERS, old_rows)
        else:
            store.save(subcat, headers, old_rows)
        restored.append(subcat)
    entry["restored"] = restored
    return entry
