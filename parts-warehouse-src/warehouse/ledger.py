# -*- coding: utf-8 -*-
"""结构化出入库账本。

旧 activity_log.jsonl 保留用于兼容首页摘要；ledger.jsonl 一行一笔完整业务操作，
明细保留在同一记录内，便于按时间、单次操作查看和审计。
"""
import json
import os
import uuid
from datetime import datetime

LEDGER_NAME = "ledger.jsonl"


def ledger_path(data_dir: str) -> str:
    return os.path.join(data_dir, LEDGER_NAME)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_qty(v) -> int:
    try:
        return int(float(str(v).strip()))
    except (ValueError, TypeError):
        return 0


def append(data_dir: str, action: str, details: list, *, operator: str = "", reason: str = "", source: str = "", undo_id: str = "", origin: str = "local", event_id: str = "") -> dict:
    """追加一笔账本记录。details 是同一次操作的物料明细列表。

    origin: local=本机操作 (可提交线上) | remote=线上同步事件 (只读展示, 不参与提交)。
    sync_status: local 记录为 pending, 提交后变为 submitted; remote 记录固定为 remote。
    """
    entry = {
        "record_id": "ledger-" + uuid.uuid4().hex[:12],
        "time": _now(),
        "action": action,
        "operator": operator,
        "reason": reason,
        "source": source,
        "undo_id": undo_id,
        "event_id": str(event_id or ""),
        "origin": "local" if origin == "local" else "remote",
        "sync_status": "pending" if origin == "local" else "remote",
        "total_delta": sum(int(d.get("delta", 0) or 0) for d in details),
        "details": details,
    }
    os.makedirs(data_dir, exist_ok=True)
    with open(ledger_path(data_dir), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def mark_submitted(data_dir: str, record_id: str, event_ids: list) -> bool:
    """把本机账本记录标记为已提交线上，记录事件编号。"""
    p = ledger_path(data_dir)
    if not os.path.exists(p):
        return False
    rows = []
    changed = False
    with open(p, encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("record_id") == record_id:
                item["sync_status"] = "submitted"
                item["submitted_at"] = _now()
                old_ids = item.get("event_ids", []) or []
                item["event_ids"] = list(dict.fromkeys([str(x) for x in old_ids] + [str(x) for x in (event_ids or [])]))
                changed = True
            rows.append(item)
    if changed:
        with open(p, "w", encoding="utf-8") as f:
            for item in rows:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return changed


def has_event_id(data_dir: str, event_id: str) -> bool:
    """检查远端事件是否已经写入本机账本。"""
    wanted = str(event_id or "").strip()
    if not wanted:
        return False
    return any(str(item.get("event_id", "")).strip() == wanted for item in load(data_dir, limit=100000))


def pending_local(data_dir: str) -> list:
    """本机未提交账本记录 (origin=local 且 sync_status != submitted)，按时间正序。"""
    rows = load(data_dir)
    pending = [r for r in rows if r.get("origin", "local") == "local" and r.get("sync_status", "pending") != "submitted"]
    return list(reversed(pending))


def mark_status(data_dir: str, record_id: str, status: str) -> bool:
    p = ledger_path(data_dir)
    if not os.path.exists(p):
        return False
    rows = []
    changed = False
    with open(p, encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("record_id") == record_id:
                item["status"] = status
                changed = True
            rows.append(item)
    if changed:
        with open(p, "w", encoding="utf-8") as f:
            for item in rows:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return changed


def update_details(data_dir: str, record_id: str, updates: dict) -> bool:
    """更新一笔原始操作的明细状态。updates key 为 ``subcat:row``。"""
    p = ledger_path(data_dir)
    if not os.path.exists(p):
        return False
    rows = []
    changed = False
    with open(p, encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("record_id") == record_id:
                for detail_index, detail in enumerate(item.get("details") or []):
                    key = f"index:{detail_index}"
                    if key not in updates:
                        key = f"{detail.get('subcat', '')}:{detail.get('row', '')}"
                    if key in updates:
                        detail.update(updates[key])
                        changed = True
                states = [d.get("status", "正常") for d in item.get("details") or []]
                if states and all(s == "已撤回" for s in states):
                    item["status"] = "已撤回"
                elif any(s == "已撤回" for s in states):
                    item["status"] = "部分撤回"
                else:
                    item["status"] = "正常"
            rows.append(item)
    if changed:
        with open(p, "w", encoding="utf-8") as f:
            for item in rows:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return changed


def load(data_dir: str, start: str = "", end: str = "", action: str = "", limit: int = 500) -> list:
    """按时间范围/动作读取账本，新记录在前。日期筛选使用 YYYY-MM-DD 前缀。"""
    p = ledger_path(data_dir)
    if not os.path.exists(p):
        return []
    rows = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            day = str(item.get("time", ""))[:10]
            if start and day < start:
                continue
            if end and day > end:
                continue
            if action and item.get("action") != action:
                continue
            rows.append(item)
    return rows[-limit:][::-1]
