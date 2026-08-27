# -*- coding: utf-8 -*-
"""Git 增量库存同步实验模块。

当前阶段只负责本地同步副本、远端提交检测和事件文件读取；不自动修改正式库存。
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Any


def _run(args: list[str], cwd: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)


def _git(cwd: str, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return _run(["git", "-C", cwd, *args], cwd=cwd, timeout=timeout)


def config_view(cfg: dict) -> dict:
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "remote_url": str(cfg.get("remote_url", "")),
        "branch": str(cfg.get("branch", "main") or "main"),
        "local_dir": str(cfg.get("local_dir", "")),
        "events_dir": str(cfg.get("events_dir", "events") or "events"),
        "username": str(cfg.get("username", "")),
        "configured": bool(cfg.get("remote_url") and cfg.get("local_dir")),
    }


def _status(repo: str, cfg: dict, message: str = "") -> dict:
    p = _git(repo, "rev-parse", "--is-inside-work-tree")
    return {
        "ok": p.returncode == 0,
        "message": message or (p.stderr.strip() if p.returncode else "Git 仓库已初始化"),
        "local_dir": repo,
        "branch": cfg.get("branch", "main"),
        "remote_url": cfg.get("remote_url", ""),
    }


def inspect_config(cfg: dict) -> dict:
    """检查配置，不联网、不创建文件。"""
    remote = str(cfg.get("remote_url", "")).strip()
    local = os.path.abspath(os.path.expandvars(os.path.expanduser(str(cfg.get("local_dir", "")).strip()))) if cfg.get("local_dir") else ""
    if not remote or not local:
        return {"ok": False, "message": "请填写 Git 仓库地址和本地同步目录", "configured": False}
    return {"ok": True, "message": "Git 配置格式已填写", "configured": True, "remote_url": remote, "local_dir": local, "branch": cfg.get("branch", "main") or "main"}


def init_or_update(cfg: dict) -> dict:
    """首次 clone，已有副本则 fetch；只返回提交检测信息。"""
    check = inspect_config(cfg)
    if not check["ok"]:
        return check
    remote, local, branch = check["remote_url"], check["local_dir"], check["branch"]
    os.makedirs(os.path.dirname(local), exist_ok=True)
    if not os.path.exists(os.path.join(local, ".git")):
        if os.path.exists(local) and os.listdir(local):
            return {"ok": False, "message": "本地同步目录非空且不是 Git 仓库，请更换目录或清空后重试"}
        p = subprocess.run(["git", "clone", "--branch", branch, remote, local], capture_output=True, text=True, timeout=120, check=False)
        if p.returncode:
            return {"ok": False, "message": (p.stderr or p.stdout).strip()[-500:]}
        return {"ok": True, "changed": True, "message": "已首次克隆 Git 仓库", "local_dir": local, "branch": branch, "remote_url": remote}
    before = _git(local, "rev-parse", "HEAD").stdout.strip()
    p = _git(local, "fetch", "origin", branch, timeout=120)
    if p.returncode:
        return {"ok": False, "message": (p.stderr or p.stdout).strip()[-500:], "local_dir": local}
    remote_head = _git(local, "rev-parse", f"origin/{branch}").stdout.strip()
    return {
        "ok": True,
        "changed": bool(before and remote_head and before != remote_head),
        "message": "检测到新的 Git 提交" if before != remote_head else "Git 没有新提交",
        "local_commit": before,
        "remote_commit": remote_head,
        "local_dir": local,
        "branch": branch,
        "remote_url": remote,
    }


def read_event_files(cfg: dict, since_commit: str = "") -> dict:
    """读取远端分支中新增的 events JSON；当前只解析，不应用到库存。"""
    check = inspect_config(cfg)
    if not check["ok"]:
        return check
    remote, local, branch = check["remote_url"], check["local_dir"], check["branch"]
    if not os.path.isdir(os.path.join(local, ".git")):
        return {"ok": False, "message": "本地 Git 副本尚未初始化"}
    head = _git(local, "rev-parse", f"origin/{branch}").stdout.strip()
    if since_commit:
        args = ["diff", "--name-only", f"{since_commit}..origin/{branch}", "--", str(cfg.get("events_dir", "events"))]
    else:
        args = ["ls-tree", "-r", "--name-only", f"origin/{branch}", "--", str(cfg.get("events_dir", "events"))]
    p = _git(local, *args)
    if p.returncode:
        return {"ok": False, "message": (p.stderr or p.stdout).strip()[-500:]}
    events: list[dict[str, Any]] = []
    for rel in p.stdout.splitlines():
        if not rel.lower().endswith(".json"):
            continue
        path = os.path.join(local, rel.replace("/", os.sep))
        try:
            with open(path, encoding="utf-8") as f:
                item = json.load(f)
            item["_path"] = rel.replace("\\", "/")
            events.append(item)
        except (OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "message": f"事件文件读取失败: {rel}: {exc}"}
    return {"ok": True, "remote_commit": head, "events": events, "count": len(events), "message": f"读取到 {len(events)} 条未应用事件"}


STATE_FILENAME = "sync_state.json"


def state_path(cfg: dict) -> str:
    check = inspect_config(cfg)
    return os.path.join(check["local_dir"], STATE_FILENAME) if check["ok"] else ""


def load_sync_state(cfg: dict) -> dict:
    default = {"schema_version": 1, "last_remote_commit": "", "read_event_ids": []}
    path = state_path(cfg)
    if not path or not os.path.isfile(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        ids = data.get("read_event_ids", [])
        return {"schema_version": 1, "last_remote_commit": str(data.get("last_remote_commit", "")),
                "read_event_ids": list(dict.fromkeys(str(x) for x in ids if str(x).strip()))}
    except (OSError, json.JSONDecodeError, TypeError):
        return default


def save_sync_state(cfg: dict, state: dict) -> dict:
    path = state_path(cfg)
    if not path:
        return {"ok": False, "message": "Git 配置不完整，无法保存同步状态"}
    clean = {"schema_version": 1, "last_remote_commit": str(state.get("last_remote_commit", "")),
             "read_event_ids": list(dict.fromkeys(str(x) for x in state.get("read_event_ids", []) if str(x).strip()))}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    try:
        with open(temp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(temp, path)
        return {"ok": True, "path": path, "state": clean}
    except OSError as exc:
        try:
            os.remove(temp)
        except OSError:
            pass
        return {"ok": False, "message": f"同步状态保存失败: {exc}"}


def read_unread_event_files(cfg: dict, since_commit: str = "", mark_read: bool = True) -> dict:
    """按本机 sync_state.json 过滤 event_id，避免重复读取。"""
    state = load_sync_state(cfg)
    base = read_event_files(cfg, since_commit=since_commit or state.get("last_remote_commit", ""))
    if not base.get("ok"):
        return base
    known = set(state.get("read_event_ids", []))
    unread = []
    for event in base.get("events", []):
        event_id = str(event.get("event_id", "")).strip()
        if not event_id:
            return {"ok": False, "message": f"事件缺少 event_id: {event.get('_path', '')}"}
        if event_id not in known:
            unread.append(event)
    if mark_read:
        state["read_event_ids"] = state.get("read_event_ids", []) + [str(e["event_id"]) for e in unread]
        state["last_remote_commit"] = base.get("remote_commit", state.get("last_remote_commit", ""))
        saved = save_sync_state(cfg, state)
        if not saved.get("ok"):
            return saved
    return {"ok": True, "remote_commit": base.get("remote_commit", ""), "events": unread,
            "count": len(unread), "read_event_ids": [str(e["event_id"]) for e in unread],
            "known_ids": state.get("read_event_ids", [])[-20:],
            "message": f"读取到 {len(unread)} 条未读事件" if unread else "没有新的未读事件"}


def upload_event(cfg: dict, event: dict) -> dict:
    """写入一条精简事件并提交推送，不上传库存目录或本地同步状态。"""
    check = inspect_config(cfg)
    if not check["ok"]:
        return check
    remote, local, branch = check["remote_url"], check["local_dir"], check["branch"]
    if not os.path.isdir(os.path.join(local, ".git")):
        return {"ok": False, "message": "本地 Git 副本尚未初始化，请先执行同步"}
    required = ("event_id", "part_id", "operation", "delta", "username")
    missing = [key for key in required if not str(event.get(key, "")).strip()]
    if missing:
        return {"ok": False, "message": "上传事件缺少字段: " + ", ".join(missing)}
    event_id = str(event["event_id"]).strip()
    safe_name = "".join(ch for ch in event_id if ch.isalnum() or ch in "-_")
    if safe_name != event_id or not safe_name:
        return {"ok": False, "message": "event_id 只能包含字母、数字、短横线和下划线"}
    events_dir = str(cfg.get("events_dir", "events") or "events").strip("/\\")
    day = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    rel = f"{events_dir}/{day}/{safe_name}.json"
    path = os.path.join(local, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    clean = {k: event[k] for k in ("event_id", "event_version", "part_id", "operation", "delta", "quantity_before", "quantity_after", "username", "created_at", "reason") if k in event}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
        f.write("\n")
    add = _git(local, "add", "--", rel)
    if add.returncode:
        return {"ok": False, "message": (add.stderr or add.stdout).strip()[-500:]}
    commit = _git(local, "-c", "commit.gpgsign=false", "-c", "user.name=" + str(cfg.get("username") or "parts-warehouse"), "-c", "user.email=parts-warehouse@localhost", "commit", "-m", "sync: " + safe_name)
    if commit.returncode:
        return {"ok": False, "message": (commit.stderr or commit.stdout).strip()[-500:]}
    push = _git(local, "push", remote, branch, timeout=180)
    if push.returncode:
        return {"ok": False, "message": (push.stderr or push.stdout).strip()[-500:], "path": rel}
    return {"ok": True, "message": "事件已上传", "path": rel, "event_id": event_id}


def upload_events(cfg: dict, events: list[dict]) -> dict:
    """批量写入多条事件并一次 commit + push（幂等：已存在的文件跳过写入）。

    每项事件字段要求与 upload_event 相同。返回每个事件的文件相对路径。
    """
    check = inspect_config(cfg)
    if not check["ok"]:
        return check
    remote, local, branch = check["remote_url"], check["local_dir"], check["branch"]
    if not os.path.isdir(os.path.join(local, ".git")):
        return {"ok": False, "message": "本地 Git 副本尚未初始化，请先执行同步"}
    events_dir = str(cfg.get("events_dir", "events") or "events").strip("/\\")
    day = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    rels = []
    for event in events:
        items = event.get("items")
        if items:
            # 批量事件格式 (event_version=2)：一条事件 = 一次业务操作的全部明细
            required = ("event_id", "operation", "username")
            missing = [key for key in required if not str(event.get(key, "")).strip()]
            if missing:
                return {"ok": False, "message": "上传事件缺少字段: " + ", ".join(missing)}
            for it in items:
                im = [key for key in ("part_id", "delta") if str(it.get(key, "")).strip() == "" or it.get(key) is None]
                if im:
                    return {"ok": False, "message": "事件明细缺少字段: " + ", ".join(im)}
        else:
            required = ("event_id", "part_id", "operation", "delta", "username")
            missing = [key for key in required if not str(event.get(key, "")).strip()]
            if missing:
                return {"ok": False, "message": "上传事件缺少字段: " + ", ".join(missing)}
        event_id = str(event["event_id"]).strip()
        safe_name = "".join(ch for ch in event_id if ch.isalnum() or ch in "-_")
        if safe_name != event_id or not safe_name:
            return {"ok": False, "message": f"event_id 只能包含字母、数字、短横线和下划线: {event_id}"}
        rel = f"{events_dir}/{day}/{safe_name}.json"
        path = os.path.join(local, rel.replace("/", os.sep))
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if items:
                clean = {k: event[k] for k in ("event_id", "event_version", "operation", "username", "created_at", "reason") if k in event}
                clean["items"] = items
            else:
                clean = {k: event[k] for k in ("event_id", "event_version", "part_id", "operation", "delta", "quantity_before", "quantity_after", "username", "created_at", "reason") if k in event}
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(clean, f, ensure_ascii=False, indent=2)
                f.write("\n")
        rels.append(rel)
    if not rels:
        return {"ok": False, "message": "没有可提交的事件"}
    add = _git(local, "add", "--", events_dir)
    if add.returncode:
        return {"ok": False, "message": (add.stderr or add.stdout).strip()[-500:]}
    commit = _git(local, "-c", "commit.gpgsign=false", "-c", "user.name=" + str(cfg.get("username") or "parts-warehouse"), "-c", "user.email=parts-warehouse@localhost",
                  "commit", "-m", "sync: batch " + str(len(rels)))
    if commit.returncode:
        # 全部文件此前已提交过（幂等重试），没有新变更也可以继续 push
        if "nothing to commit" not in (commit.stderr or "") and "nothing to commit" not in (commit.stdout or ""):
            return {"ok": False, "message": (commit.stderr or commit.stdout).strip()[-500:]}
    push = _git(local, "push", remote, branch, timeout=180)
    if push.returncode:
        return {"ok": False, "message": (push.stderr or push.stdout).strip()[-500:], "paths": rels}
    return {"ok": True, "message": f"已上传 {len(rels)} 条事件", "paths": rels}
