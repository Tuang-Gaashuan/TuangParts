# -*- coding: utf-8 -*-
"""元器件仓库 — Web 服务 (三级结构: 一级分类 -> 子分类 -> 元器件表格).

结构:
  总览页    : 一级分类卡片 (只显示有记录的分类)
  子分类页  : 一级分类下的子分类列表 (只显示有数据的子分类)
  表格页    : 子分类的元器件 Excel (可编辑 / AI 填入 / 保存)

数据文件: data/<一级分类>/<子分类>.xlsx, 有数据才建文件。
重名子分类物理文件唯一, 多个一级分类入口指向同一文件。

设置: data/settings.json (数据路径 / AI 接口 / 界面主题), 用户可改。

启动:  python app.py   (浏览器 http://127.0.0.1:5000)
桌面版: python desktop.py (pywebview 原生窗口)
"""

import os
import uuid
import zipfile
from urllib.parse import urlparse
import threading
import webbrowser
import faulthandler
from datetime import datetime

# 原生层崩溃 (OpenCV/摄像头驱动) 无 Python traceback, faulthandler 能打印线程栈定位
faulthandler.enable()

from flask import Flask, jsonify, render_template, request, send_from_directory, send_file

from warehouse.config import CATEGORIES, fields_for, subcats, subcat_owners, primary_owner, safe_filename
from warehouse.excel_store import ExcelStore
from warehouse.ai_fill import AIFiller, get_api_key
from warehouse.settings import load_settings, save_settings, public_view, resolve_data_dir, chat_completions_url
from warehouse.activity import record as record_activity
from warehouse.activity import load as load_activity
from warehouse import ledger
from warehouse.batch_import import BatchParser
from warehouse import git_sync

# 数据/设置根目录:
#   打包版 (desktop.py) 通过环境变量 PARTS_APP_DIR 指向 exe 旁目录;
#   开发版用源码目录。
BASE_DIR = os.environ.get("PARTS_APP_DIR") or os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = os.path.join(BASE_DIR, "data")

# 模板/静态资源目录: 打包版在 _MEIPASS (通过 PARTS_RES_DIR), 开发版用源码目录
RES_DIR = os.environ.get("PARTS_RES_DIR") or BASE_DIR

app = Flask(
    __name__,
    template_folder=os.path.join(RES_DIR, "templates"),
    static_folder=os.path.join(RES_DIR, "static"),
)


def get_data_dir() -> str:
    """当前实际数据目录 (跟随用户设置, 支持运行时切换)。"""
    return resolve_data_dir(BASE_DIR)


def activity_path(path: str):
    """数据目录可能与源码不在同一盘，跨盘时保留绝对路径。"""
    try:
        return os.path.relpath(path, BASE_DIR)
    except ValueError:
        return os.path.abspath(path)


def get_store() -> ExcelStore:
    return app.config.get("STORE") or ExcelStore(get_data_dir())


def get_ai_cfg() -> dict | None:
    """当前 AI 配置, 未配置返回 None。

    online: 需要 api_key; ollama: 本地离线模型, 无需 key,
    默认 base_url http://localhost:11434/v1 (OpenAI 兼容), key 用占位符。
    """
    s = load_settings(BASE_DIR)
    ai = s["ai"]
    provider = ai.get("provider", "online")
    if provider == "ollama":
        cfg = dict(ai)
        cfg["base_url"] = (ai.get("base_url") or "http://localhost:11434/v1").strip()
        cfg["api_key"] = "ollama"   # 本地服务不校验, 占位即可
        if not cfg.get("model"):
            cfg["model"] = "qwen2.5:7b"
        return cfg
    if not ai.get("api_key"):
        return None
    return ai


# ── 页面 ───────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


def active_sync_cfg() -> dict:
    """返回当前线上同步平台的配置 (sync_provider: git | gitee)。"""
    s = load_settings(BASE_DIR)
    prov = str(s.get("sync_provider", "gitee"))
    if prov not in ("git", "gitee"):
        prov = "gitee"
    return dict(s.get(f"{prov}_sync") or {})


def sync_config_error(cfg: dict) -> str:
    """拒绝平台配置与远端主机错配，避免显示平台和实际连接目标不一致。"""
    provider = str(load_settings(BASE_DIR).get("sync_provider", "gitee"))
    host = urlparse(str(cfg.get("remote_url", "")).strip()).netloc.lower().split(":", 1)[0]
    if not host:
        return "当前平台尚未填写远端仓库地址"
    if provider == "gitee" and ("github.com" in host or "githubusercontent.com" in host):
        return "当前选择 Gitee，但远端地址是 GitHub，请填写 gitee.com 仓库地址"
    if provider == "git" and "gitee.com" in host:
        return "当前选择 GitHub，但远端地址是 Gitee，请填写 github.com 仓库地址"
    return ""


@app.route("/api/git-sync/inspect", methods=["POST"])
def git_sync_inspect():
    cfg = active_sync_cfg()
    mismatch = sync_config_error(cfg)
    if mismatch:
        return jsonify({"ok": False, "message": mismatch})
    return jsonify(git_sync.inspect_config(cfg))


@app.route("/api/git-sync/check", methods=["POST"])
def git_sync_check():
    cfg = active_sync_cfg()
    mismatch = sync_config_error(cfg)
    if mismatch:
        return jsonify({"ok": False, "message": mismatch})
    if not cfg.get("enabled"):
        return jsonify({"ok": False, "message": "线上同步尚未启用", "disabled": True})
    result = git_sync.init_or_update(cfg)
    if not result.get("ok"):
        return jsonify(result)
    events = git_sync.read_unread_event_files(cfg, mark_read=False)
    if not events.get("ok"):
        result["events_error"] = events.get("message", "事件读取失败")
        result["event_count"] = 0
    else:
        result["event_count"] = events.get("count", 0)
    return jsonify(result)


@app.route("/api/git-sync/events", methods=["POST"])
def git_sync_events():
    cfg = active_sync_cfg()
    mismatch = sync_config_error(cfg)
    if mismatch:
        return jsonify({"ok": False, "message": mismatch})
    if not cfg.get("enabled"):
        return jsonify({"ok": False, "message": "线上同步尚未启用", "disabled": True})
    data = request.get_json(silent=True) or {}
    result = git_sync.read_unread_event_files(cfg, str(data.get("since_commit", "")), mark_read=bool(data.get("mark_read", True)))
    # 读取并标记后，把线上事件写入账本 (origin=remote)，与本地操作区分开
    if result.get("ok") and result.get("events") and data.get("mark_read", True):
        _apply_remote_events_to_ledger(cfg, result.get("events", []))
        result["ledger_applied"] = len(result.get("events", []))
    return jsonify(result)


@app.route("/api/git-sync/upload", methods=["POST"])
def git_sync_upload():
    cfg = active_sync_cfg()
    mismatch = sync_config_error(cfg)
    if mismatch:
        return jsonify({"ok": False, "message": mismatch})
    if not cfg.get("enabled"):
        return jsonify({"ok": False, "message": "请先在设置中启用线上同步", "disabled": True})
    data = request.get_json(silent=True) or {}
    data.setdefault("username", cfg.get("username", ""))
    data.setdefault("event_version", 1)
    data.setdefault("created_at", datetime.utcnow().isoformat() + "Z")
    return jsonify(git_sync.upload_event(cfg, data))


# ── 账本一键提交线上 ──────────────────────────────────────
_OP_TO_ACTION = {"restock": "录入", "withdraw": "取出", "adjust": "调整"}


def _apply_remote_events_to_ledger(cfg: dict, events: list) -> None:
    """线上事件进入账本 (origin=remote)，与本地操作区分；只读展示，不修改库存。

    兼容两种事件格式：新版 event_version=2 带 items 明细数组；旧版单条 part_id/delta。
    """
    for ev in events:
        event_id = str(ev.get("event_id", "")).strip()
        if ledger.has_event_id(get_data_dir(), event_id):
            continue
        items = ev.get("items")
        if items:
            details = [{
                "subcat": str(it.get("subcat", "") or it.get("part_id", "")),
                "name": str(it.get("name", "") or it.get("part_id", "")),
                "delta": it.get("delta", 0),
                "quantity_before": it.get("quantity_before"),
                "quantity_after": it.get("quantity_after"),
            } for it in items]
        else:
            details = [{
                "subcat": str(ev.get("part_id", "")),
                "name": str(ev.get("part_id", "")),
                "delta": ev.get("delta", 0),
                "quantity_before": ev.get("quantity_before"),
                "quantity_after": ev.get("quantity_after"),
            }]
        ledger.append(
            get_data_dir(),
            _OP_TO_ACTION.get(str(ev.get("operation", "")), "调整"),
            details,
            operator=str(ev.get("username", "") or "线上"),
            reason=str(ev.get("reason", "") or "线上同步事件"),
            source="sync",
            origin="remote",
            event_id=event_id,
        )


@app.route("/api/sync/pending", methods=["GET"])
def sync_pending():
    """返回全部本机账本记录，供首次提交和重复提交使用。"""
    cfg = active_sync_cfg()
    all_records = ledger.load(get_data_dir(), limit=5000)
    records = [r for r in all_records if r.get("origin", "local") == "local"]
    return jsonify({
        "ok": True,
        "count": len(records),
        "detail_count": sum(len(r.get("details", [])) for r in records),
        "records": records,
        "enabled": bool(cfg.get("enabled")),
        "provider": str(load_settings(BASE_DIR).get("sync_provider", "gitee")),
        "remote_url": str(cfg.get("remote_url", "")),
        "config_error": sync_config_error(cfg),
    })


@app.route("/api/sync/submit", methods=["POST"])
def sync_submit():
    """把本机账本记录（可指定 record_ids，缺省全部）拆成事件提交到线上。"""
    cfg = active_sync_cfg()
    mismatch = sync_config_error(cfg)
    if mismatch:
        return jsonify({"ok": False, "message": mismatch})
    if not cfg.get("enabled"):
        return jsonify({"ok": False, "message": "请先在设置中启用线上同步", "disabled": True})
    data = request.get_json(silent=True) or {}
    wanted = [str(x).strip() for x in data.get("record_ids", []) if str(x).strip()]
    all_records = ledger.load(get_data_dir(), limit=5000)
    records = [r for r in all_records if r.get("origin", "local") == "local"]
    if wanted:
        records = [r for r in records if r["record_id"] in wanted]
    if not records:
        return jsonify({"ok": False, "message": "没有待提交的本机账本记录", "count": 0})
    username = str(cfg.get("username", "") or "parts-warehouse")
    events = []
    record_event_ids: dict[str, list] = {}
    for rec in records:
        rec_hex = str(rec["record_id"]).replace("ledger-", "")
        details = rec.get("details", []) or []
        op = {"录入": "restock", "取出": "withdraw", "调整": "adjust", "撤回": "adjust"}.get(str(rec.get("action", "")), "adjust")
        # 每次提交都生成新的事件 ID；重复提交不能覆盖原事件文件。
        ev_id = f"evt-{rec_hex}-{uuid.uuid4().hex[:8]}"
        items = []
        for d in details:
            part = str(d.get("subcat", "")).strip()
            nm = str(d.get("name", "")).strip()
            part_id = f"{part}|{nm}" if part and nm else (part or nm or f"row{d.get('row', '')}")
            items.append({
                "part_id": part_id,
                "subcat": part,
                "name": nm,
                "delta": int(d.get("delta", 0) or 0),
                "quantity_before": d.get("quantity_before"),
                "quantity_after": d.get("quantity_after"),
            })
        events.append({
            "event_id": ev_id,
            "event_version": 2,
            "operation": op,
            "username": username,
            "created_at": str(rec.get("time", "")),
            "reason": str(rec.get("reason", "") or rec.get("action", "")),
            "items": items,
        })
        record_event_ids[rec["record_id"]] = [ev_id]
    result = git_sync.upload_events(cfg, events)
    if not result.get("ok"):
        return jsonify(result)
    marked = 0
    for rec_id, ids in record_event_ids.items():
        if ledger.mark_submitted(get_data_dir(), rec_id, ids):
            marked += 1
    # 推进同步游标，防止刚提交的事件被自己读回重复记入账本
    try:
        git_sync.read_unread_event_files(cfg, mark_read=True)
    except Exception:
        pass
    return jsonify({
        "ok": True,
        "message": result.get("message", "已提交"),
        "submitted": marked,
        "events": len(events),
        "paths": result.get("paths", []),
    })


@app.route("/api/settings", methods=["GET"])
def settings_get():
    s = load_settings(BASE_DIR)
    view = public_view(s)
    view["resolved_data_dir"] = get_data_dir()
    return jsonify(view)


@app.route("/api/settings", methods=["POST"])
def settings_post():
    data = request.get_json(force=True) or {}
    patch = {}
    if "data_dir" in data:
        patch["data_dir"] = (data.get("data_dir") or "").strip()
    if "theme" in data:
        patch["theme"] = data.get("theme", "light-blue")
    if "background" in data:
        patch["background"] = (data.get("background") or "").strip()
    if "bg_fill" in data:
        v = (data.get("bg_fill") or "cover").strip()
        if v in ("cover", "contain", "stretch", "repeat", "original"):
            patch["bg_fill"] = v
    for k in ("bg_brightness", "bg_opacity", "card_opacity", "decor1", "decor2"):
        if k in data:
            if k.startswith("decor"):
                patch[k] = (data.get(k) or "").strip()
            else:
                try:
                    patch[k] = max(0, min(200, int(data[k])))
                except (TypeError, ValueError):
                    pass
    if "ai" in data:
        new_ai = {
            "provider": (data["ai"].get("provider") or "online").strip(),
            "base_url": (data["ai"].get("base_url") or "").strip(),
            "api_key": (data["ai"].get("api_key") or "").strip(),
            "model": (data["ai"].get("model") or "").strip(),
        }
        # 留空 Key = 保持原有 Key (避免打开设置面板再点保存时误清空)
        cur_ai = load_settings(BASE_DIR)["ai"]
        if not new_ai["api_key"] and cur_ai.get("api_key") and new_ai["provider"] != "ollama":
            new_ai["api_key"] = cur_ai["api_key"]
        patch["ai"] = new_ai
    if "sync_provider" in data:
        v = str(data.get("sync_provider") or "gitee").strip().lower()
        patch["sync_provider"] = v if v in ("git", "gitee") else "gitee"
    for sync_key in ("git_sync", "gitee_sync"):
        if sync_key in data and isinstance(data[sync_key], dict):
            g = data[sync_key]
            patch[sync_key] = {
                "enabled": bool(g.get("enabled", False)),
                "remote_url": (g.get("remote_url") or "").strip(),
                "local_dir": (g.get("local_dir") or "").strip(),
                "branch": (g.get("branch") or "main").strip() or "main",
                "events_dir": (g.get("events_dir") or "events").strip() or "events",
                "username": (g.get("username") or "").strip(),
            }
    candidate_provider = str(patch.get("sync_provider", load_settings(BASE_DIR).get("sync_provider", "gitee")))
    candidate_cfg = patch.get(f"{candidate_provider}_sync")
    if candidate_cfg:
        host = urlparse(candidate_cfg["remote_url"]).netloc.lower().split(":", 1)[0]
        if candidate_provider == "gitee" and ("github.com" in host or "githubusercontent.com" in host):
            return jsonify({"ok": False, "message": "Gitee 配置不能填写 GitHub 仓库地址，请检查远端地址"}), 400
        if candidate_provider == "git" and "gitee.com" in host:
            return jsonify({"ok": False, "message": "GitHub 配置不能填写 Gitee 仓库地址，请检查远端地址"}), 400
    s = save_settings(BASE_DIR, patch)
    view = public_view(s)
    view["resolved_data_dir"] = get_data_dir()
    return jsonify(view)


@app.route("/api/settings/background", methods=["POST"])
def settings_background():
    """上传背景图, 只存文件不写设置 (预览用), 保存由前端统一点"保存背景设置"。"""
    if "file" not in request.files:
        return jsonify({"error": "未收到文件"}), 400
    f = request.files["file"]
    fname = f.filename or ""
    if not fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
        return jsonify({"error": "仅支持 png/jpg/webp/bmp 图片"}), 400
    try:
        data_dir = get_data_dir()
        bg_dir = os.path.join(data_dir, "backgrounds")
        os.makedirs(bg_dir, exist_ok=True)
        ext = os.path.splitext(fname)[1].lower()
        out_name = "bg_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ext
        out_path = os.path.join(bg_dir, out_name)
        f.save(out_path)
        rel = os.path.join("backgrounds", out_name).replace("\\", "/")
        return jsonify({"ok": True, "background": rel})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@app.route("/api/settings/decor", methods=["POST"])
def settings_decor():
    """上传首页装饰图 (index=1|2), 存 data/decor/, 立即写设置。"""
    f = request.files.get("file")
    index = request.form.get("index", "1")
    if not f or not (f.filename or "").lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
        return jsonify({"ok": False, "error": "请选择图片文件 (png/jpg/webp/bmp)"})
    try:
        data_dir = get_data_dir()
        decor_dir = os.path.join(data_dir, "decor")
        os.makedirs(decor_dir, exist_ok=True)
        ext = os.path.splitext(f.filename)[1].lower()
        out_name = f"decor_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{index}{ext}"
        f.save(os.path.join(decor_dir, out_name))
        rel = f"decor/{out_name}"
        key = f"decor{index}"
        save_settings(BASE_DIR, {key: rel})
        return jsonify({"ok": True, "decor": rel})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:200]})


# ── API: data 目录静态服务 (背景图等) ──────────────────
@app.route("/data/<path:filename>")
def data_file(filename):
    return send_from_directory(get_data_dir(), filename)


# ── API: 总览 (一级分类, 只含有记录的) ─────────────────
@app.route("/api/overview")
def overview():
    store = get_store()
    overview = store.all_overview()
    cards = []
    for key, total in overview.items():
        if total > 0:
            name = "未分类" if key == "unclassified" else CATEGORIES[key][0]
            cards.append({"key": key, "name": name, "count": total})
    return jsonify({"cards": cards, "total": sum(overview.values())})


# ── API: 未分类元件 (手动归类界面) ─────────────────────
@app.route("/api/unclassified")
def unclassified_list():
    from warehouse import unclassified as uncat
    data_dir = get_data_dir()
    headers, rows = uncat.load(data_dir)
    fkeys = [fk for fk, _ in fields_for("")]
    items = []
    for i, row in enumerate(rows):
        d = {}
        for j, fk in enumerate(fkeys):
            v = row[j] if j < len(row) else ""
            d[fk] = v if v is not None else ""
        d["raw"] = row[len(fkeys)] if len(row) > len(fkeys) else ""
        d["index"] = i
        items.append(d)
    tree = {key: {"name": CATEGORIES[key][0], "subs": CATEGORIES[key][1]} for key in CATEGORIES}
    return jsonify({"items": items, "count": len(items), "cat_tree": tree})


@app.route("/api/unclassified/assign", methods=["POST"])
def unclassified_assign():
    data = request.get_json(force=True) or {}
    indices = data.get("indices") or []
    cat_key = (data.get("cat_key") or "").strip()
    subcat = (data.get("subcat") or "").strip()
    if not indices or cat_key not in CATEGORIES:
        return jsonify({"error": "请选择一级分类与条目"}), 400
    subs = CATEGORIES[cat_key][1]
    if subcat not in subs:
        return jsonify({"error": f"子分类不存在: {subcat}"}), 400
    from warehouse import unclassified as uncat
    data_dir = get_data_dir()
    try:
        # 记录撤销快照 (目标子分类 + 未分类)
        headers_u, old_uncat_rows = uncat.load(data_dir)
        h_old, old_target_rows = get_store().load(subcat)
        moved = uncat.assign(data_dir, indices, cat_key, subcat)
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500
    from warehouse import undo as undo_mod
    undo_mod.push(data_dir, [
        {"subcat": subcat, "old_rows": old_target_rows},
        {"subcat": undo_mod.UNCAT_KEY, "old_rows": old_uncat_rows},
    ], "未分类归类")
    return jsonify({"ok": True, "moved": moved})


# ── API: 一级分类下的子分类 (只含有数据的) ──────────────
@app.route("/api/category/<key>")
def category(key):
    if key not in CATEGORIES:
        return jsonify({"error": "未知分类"}), 404
    store = get_store()
    subs = store.subcats_with_data(key)
    return jsonify({
        "key": key,
        "name": CATEGORIES[key][0],
        "subcats": [{"name": name, "count": n, "owner": primary_owner(name)} for name, n in subs],
    })


# ── API: 子分类表格数据 ────────────────────────────────
@app.route("/api/subcat")
def subcat():
    name = (request.args.get("name") or "").strip()
    if not name or primary_owner(name) is None:
        return jsonify({"error": "未知子分类"}), 404
    store = get_store()
    headers, rows = store.load(name)
    fields = fields_for(name)
    items = []
    for row in rows:
        item = {}
        for (fkey, label), val in zip(fields, row):
            item[fkey] = val if val is not None else ""
        items.append(item)
    return jsonify({
        "name": name,
        "owners": subcat_owners(name),
        "fields": [{"key": fk, "label": lb} for fk, lb in fields],
        "items": items,
    })


# ── API: 保存子分类 ────────────────────────────────────
@app.route("/api/save", methods=["POST"])
def save():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name or primary_owner(name) is None:
        return jsonify({"error": "未知子分类"}), 404
    store = get_store()
    data_dir = get_data_dir()
    fields = fields_for(name)
    fkeys = [fk for fk, _ in fields]
    items = data.get("items", [])
    rows = []
    for item in items:
        row = [item.get(fk, "") for fk in fkeys]
        rows.append(row)
    old_headers, old_rows = store.load(name)
    path = store.save(name, [lb for _, lb in fields], rows)
    record_activity(data_dir, name, old_rows, rows, path=os.path.relpath(path, BASE_DIR))
    changed = []
    for i, row in enumerate(rows):
        old = old_rows[i] if i < len(old_rows) else []
        oldq = ledger.parse_qty(old[3]) if len(old) > 3 else 0
        newq = ledger.parse_qty(row[3]) if len(row) > 3 else 0
        if oldq != newq:
            changed.append({"subcat": name, "row": i, "name": row[0] if row else "", "delta": newq - oldq, "quantity_before": oldq, "quantity_after": newq})
    if changed:
        ledger.append(data_dir, "调整", changed, reason="编辑库存表", source="table")

    from warehouse import undo as undo_mod
    undo_mod.push(data_dir, [{"subcat": name, "old_rows": old_rows}], "保存修改")
    return jsonify({"ok": True, "saved": len(rows), "path": os.path.relpath(path, BASE_DIR)})


# ── API: 一级分类下的全量子分类 (含空的, 录入界面用) ──
@app.route("/api/subcats_all")
def subcats_all():
    key = request.args.get("key", "")
    if key not in CATEGORIES:
        return jsonify({"error": "未知分类"}), 404
    return jsonify({"key": key, "subcats": subcats(key)})


# ── API: 取出元器件 (出库) ─────────────────────────────
@app.route("/api/withdraw", methods=["POST"])
def withdraw():
    """从子分类扣减库存。items: [{row: 行号, qty: 取出数量}]。
    校验数量充足后扣减, 记录操作日志 (qty_delta<0 → 使用/取出)。"""
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    items = data.get("items") or []
    if not name or primary_owner(name) is None:
        return jsonify({"error": "未知子分类"}), 404
    if not items:
        return jsonify({"error": "未选择要取出的元件"}), 400

    store = get_store()
    data_dir = get_data_dir()
    headers, old_rows = store.load(name)

    # 校验并计算新行
    new_rows = [list(r) for r in old_rows]
    taken_total = 0
    detail = []
    for it in items:
        try:
            row_index = int(it.get("row", -1))
            take = int(float(str(it.get("qty", 0)).strip()))
        except (TypeError, ValueError):
            continue
        if row_index < 0 or row_index >= len(new_rows):
            continue
        if take <= 0:
            continue
        row = new_rows[row_index]
        try:
            cur = int(float(str(row[3]).strip())) if len(row) > 3 else 0
        except (TypeError, ValueError):
            cur = 0
        if take > cur:
            label = str(row[0]) if row and row[0] else f"第{row_index + 1}行"
            return jsonify({"error": f"「{label}」库存不足: 当前 {cur} 件, 要取出 {take} 件"}), 400
        row[3] = str(cur - take)
        taken_total += take
        detail.append({"row": row_index, "name": row[0] if row else "", "taken": take})

    if taken_total == 0:
        return jsonify({"error": "取出数量必须大于 0"}), 400

    path = store.save(name, [label for _, label in fields_for(name)], new_rows)
    record_activity(data_dir, name, old_rows, new_rows, path=activity_path(path))
    from warehouse import undo as undo_mod
    undo_entry = undo_mod.push(data_dir, [{"subcat": name, "old_rows": old_rows}], "取出")
    ledger.append(data_dir, "取出", [{**d, "delta": -int(d["taken"]), "quantity_before": ledger.parse_qty(old_rows[d["row"]][3]), "quantity_after": ledger.parse_qty(new_rows[d["row"]][3]), "subcat": name} for d in detail], reason="库存取出", source="withdraw", undo_id=undo_entry.get("undo_id"))
    return jsonify({"ok": True, "subcat": name, "taken": taken_total, "items": detail})


@app.route("/api/withdraw/batch", methods=["POST"])
def withdraw_batch():
    """跨多个子分类一次取出，只生成一笔账本和一个撤回快照。"""
    data = request.get_json(force=True) or {}
    groups = data.get("groups") or {}
    if not isinstance(groups, dict) or not groups:
        return jsonify({"error": "未选择要取出的元件"}), 400
    store = get_store()
    data_dir = get_data_dir()
    snapshots, updates, details = [], [], []
    taken_total = 0
    for raw_name, items in groups.items():
        name = str(raw_name or "").strip()
        if not name or primary_owner(name) is None:
            return jsonify({"error": f"未知子分类: {name}"}), 404
        if not isinstance(items, list) or not items:
            return jsonify({"error": f"「{name}」没有有效取出明细"}), 400
        headers, old_rows = store.load(name)
        new_rows = [list(row) for row in old_rows]
        group_details = []
        for item in items:
            try:
                row_index = int(item.get("row", -1))
                take = int(float(str(item.get("qty", 0)).strip()))
            except (TypeError, ValueError):
                return jsonify({"error": f"「{name}」的取出数量无效"}), 400
            if row_index < 0 or row_index >= len(new_rows) or take <= 0:
                return jsonify({"error": f"「{name}」存在无效取出明细"}), 400
            row = new_rows[row_index]
            current = ledger.parse_qty(row[3] if len(row) > 3 else 0)
            if take > current:
                label = str(row[0] or f"第{row_index + 1}行") if row else f"第{row_index + 1}行"
                return jsonify({"error": f"「{label}」库存不足: 当前 {current} 件, 要取出 {take} 件"}), 400
            row[3] = str(current - take)
            group_details.append({"row": row_index, "name": row[0] if row else "", "taken": take,
                                  "delta": -take, "quantity_before": current,
                                  "quantity_after": current - take, "subcat": name})
        snapshots.append({"subcat": name, "old_rows": old_rows})
        updates.append((name, old_rows, new_rows))
        details.extend(group_details)
        taken_total += sum(d["taken"] for d in group_details)
    for name, old_rows, new_rows in updates:
        path = store.save(name, [label for _, label in fields_for(name)], new_rows)
        record_activity(data_dir, name, old_rows, new_rows, path=activity_path(path))
    from warehouse import undo as undo_mod
    undo_entry = undo_mod.push(data_dir, snapshots, "取出")
    ledger_entry = ledger.append(data_dir, "取出", details, reason="BOM 清单取出",
                                 source="withdraw-batch", undo_id=undo_entry.get("undo_id"))
    return jsonify({"ok": True, "taken": taken_total, "lines": len(details),
                    "subcats": len(updates), "undo_id": undo_entry.get("undo_id"),
                    "record_id": ledger_entry.get("record_id")})


# ── BOM 取出匹配 (替换料机制) ─────────────────────
@app.route("/api/withdraw/match", methods=["POST"])
def withdraw_match():
    """对 BOM 解析结果匹配现有库存。
    items: 批量导入解析后的条目 [{name,brand,package,qty,spec,cat_key,subcat}]。
    返回 [{item, candidates: [{subcat,row,name,brand,package,qty,spec}]}]。
    """
    data = request.get_json(force=True) or {}
    items = data.get("items") or []
    if not items:
        return jsonify({"error": "无数据"}), 400
    from warehouse.withdraw_match import match_items
    results = match_items(items, get_data_dir())
    matched = sum(1 for r in results if r["candidates"])
    return jsonify({"ok": True, "results": results, "matched": matched, "total": len(results)})


# -- API: BOM 清单 (匹配结果持久化, 不直接改库存) --
@app.route("/api/bom-lists", methods=["GET"])
def bom_lists_get():
    from warehouse.bom_lists import list_lists
    return jsonify({"ok": True, "items": list_lists(get_data_dir())})


@app.route("/api/bom-lists/<list_id>/prepare", methods=["POST"])
def bom_list_prepare(list_id):
    """读取已保存 BOM，按份数生成绑定库存行的实时取出结果。"""
    from warehouse.bom_lists import get_list
    from warehouse.withdraw_match import match_items
    item = get_list(get_data_dir(), list_id)
    if not item:
        return jsonify({"error": "BOM 清单不存在"}), 404
    try:
        copies = int((request.get_json(force=True) or {}).get("copies", 1))
    except (TypeError, ValueError):
        copies = 0
    if copies < 1:
        return jsonify({"error": "份数必须是大于等于 1 的整数"}), 400

    store = get_store()
    results = []
    def _same_cell(actual, expected):
        return str(actual or "").strip() == str(expected or "").strip()

    for saved in item.get("items", []):
        req = dict(saved.get("item") or {})
        try:
            req["qty"] = str(int(float(str(req.get("qty", 0)))) * copies)
        except (TypeError, ValueError):
            req["qty"] = "0"
        selected = saved.get("selected") or {}
        subcat = str(selected.get("subcat") or "").strip()
        try:
            row_index = int(selected.get("row", -1))
        except (TypeError, ValueError):
            row_index = -1
        candidates = []
        if subcat and primary_owner(subcat) is not None:
            _, rows = store.load(subcat)
            snapshot = selected.get("snapshot") or {}
            if not (0 <= row_index < len(rows)) or (
                snapshot and any(
                    not _same_cell(rows[row_index][idx] if len(rows[row_index]) > idx else "", snapshot.get(key, ""))
                    for idx, key in ((0, "name"), (1, "brand"), (2, "package"), (6, "spec"))
                )
            ):
                row_index = next((i for i, row in enumerate(rows) if all(
                    _same_cell(row[idx] if len(row) > idx else "", snapshot.get(key, ""))
                    for idx, key in ((0, "name"), (1, "brand"), (2, "package"), (6, "spec"))
                )), -1)
            if 0 <= row_index < len(rows):
                row = rows[row_index]
                candidates = [{
                    "subcat": subcat, "row": row_index,
                    "name": str(row[0] or "") if len(row) > 0 else "",
                    "brand": str(row[1] or "") if len(row) > 1 else "",
                    "package": str(row[2] or "") if len(row) > 2 else "",
                    "qty": str(row[3] or "") if len(row) > 3 else "",
                    "spec": str(row[6] or "") if len(row) > 6 else "",
                    "match_type": "exact", "pkg_note": "",
                }]
        results.append({"item": req, "candidates": candidates, "saved_selected": selected})
    return jsonify({"ok": True, "results": results, "copies": copies, "name": item.get("name", "")})


@app.route("/api/bom-lists/<list_id>", methods=["GET"])
def bom_list_get(list_id):
    from warehouse.bom_lists import get_list
    item = get_list(get_data_dir(), list_id)
    if not item:
        return jsonify({"error": "BOM 清单不存在"}), 404
    return jsonify({"ok": True, "item": item})


@app.route("/api/bom-lists", methods=["POST"])
def bom_list_save():
    from warehouse.bom_lists import save_list
    payload = request.get_json(force=True) or {}
    rows = payload.get("items") or []
    if not rows:
        return jsonify({"error": "BOM 清单至少需要一条物料"}), 400
    store = get_store()
    normalized = []
    for entry in rows:
        entry = dict(entry or {})
        selected = dict(entry.get("selected") or {})
        subcat = str(selected.get("subcat") or "").strip()
        try:
            row_index = int(selected.get("row", -1))
        except (TypeError, ValueError):
            row_index = -1
        # 缺料行允许保存：保留完整 EDA BOM，selected 为空表示待补料。
        if not subcat:
            entry["selected"] = {}
            normalized.append(entry)
            continue
        if primary_owner(subcat) is None:
            return jsonify({"error": f"未知仓库子分类: {subcat}"}), 400
        _, inventory = store.load(subcat)
        if row_index < 0 or row_index >= len(inventory):
            return jsonify({"error": f"仓库物料行无效: {subcat} 第 {row_index + 1} 行"}), 400
        row = inventory[row_index]
        selected["row"] = row_index
        selected["snapshot"] = {
            "name": str(row[0] or "") if len(row) > 0 else "",
            "brand": str(row[1] or "") if len(row) > 1 else "",
            "package": str(row[2] or "") if len(row) > 2 else "",
            "qty": str(row[3] or "") if len(row) > 3 else "",
            "spec": str(row[6] or "") if len(row) > 6 else "",
        }
        entry["selected"] = selected
        normalized.append(entry)
    payload["items"] = normalized
    try:
        item = save_list(get_data_dir(), payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "item": item})


@app.route("/api/bom-lists/<list_id>", methods=["DELETE"])
def bom_list_delete(list_id):
    from warehouse.bom_lists import delete_list
    if not delete_list(get_data_dir(), list_id):
        return jsonify({"error": "BOM 清单不存在"}), 404
    return jsonify({"ok": True})


@app.route("/api/addstock", methods=["POST"])
def addstock():
    """给子分类元件增加库存。items: [{row: 行号, qty: 增加数量}]。
    数量累加到库存, 记录操作日志 (qty_delta>0 → 存入)。"""
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    items = data.get("items") or []
    if not name or primary_owner(name) is None:
        return jsonify({"error": "未知子分类"}), 404
    if not items:
        return jsonify({"error": "未选择要增加的元件"}), 400

    store = get_store()
    data_dir = get_data_dir()
    headers, old_rows = store.load(name)
    new_rows = [list(r) for r in old_rows]
    added_total = 0
    detail = []
    for it in items:
        try:
            row_index = int(it.get("row", -1))
            add = int(float(str(it.get("qty", 0)).strip()))
        except (TypeError, ValueError):
            continue
        if row_index < 0 or row_index >= len(new_rows) or add <= 0:
            continue
        row = new_rows[row_index]
        try:
            cur = int(float(str(row[3]).strip())) if len(row) > 3 else 0
        except (TypeError, ValueError):
            cur = 0
        row[3] = str(cur + add)
        added_total += add
        detail.append({"row": row_index, "name": row[0] if row else "", "added": add})

    if added_total == 0:
        return jsonify({"error": "增加数量必须大于 0"}), 400

    path = store.save(name, [label for _, label in fields_for(name)], new_rows)
    record_activity(data_dir, name, old_rows, new_rows, path=activity_path(path))
    from warehouse import undo as undo_mod
    undo_entry = undo_mod.push(data_dir, [{"subcat": name, "old_rows": old_rows}], "增加库存")
    ledger.append(data_dir, "录入", [{**d, "delta": int(d["added"]), "quantity_before": ledger.parse_qty(old_rows[d["row"]][3]), "quantity_after": ledger.parse_qty(new_rows[d["row"]][3]), "subcat": name} for d in detail], reason="库存录入", source="addstock", undo_id=undo_entry.get("undo_id"))
    return jsonify({"ok": True, "subcat": name, "added": added_total, "items": detail})


# ── API: 合并重复元件 (名称/品牌/封装/规格 相同 → 数量累加) ──
@app.route("/api/subcat/merge", methods=["POST"])
def subcat_merge():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name or primary_owner(name) is None:
        return jsonify({"error": "未知子分类"}), 404
    store = get_store()
    data_dir = get_data_dir()
    headers, old_rows = store.load(name)
    from warehouse.batch_import import _merge_rows
    new_rows = _merge_rows(old_rows, [], name)
    removed = len(old_rows) - len(new_rows)
    if removed <= 0:
        return jsonify({"ok": True, "removed": 0, "before": len(old_rows), "after": len(new_rows)})
    path = store.save(name, [label for _, label in fields_for(name)], new_rows)
    record_activity(data_dir, name, old_rows, new_rows, path=activity_path(path))
    from warehouse import undo as undo_mod
    undo_mod.push(data_dir, [{"subcat": name, "old_rows": old_rows}], "合并重复")
    return jsonify({"ok": True, "removed": removed, "before": len(old_rows), "after": len(new_rows)})


# ── API: 快速删除数据 (设置 → 数据管理) ────────────────
def _clear_all_data(data_dir: str) -> dict:
    """清空全部元器件数据: 分类文件夹 + 未分类 + 活动日志。
    保留: settings.json / backgrounds / decor (配置与图片资源)。"""
    import shutil
    cleared = {"categories": [], "activity": False}
    for name in os.listdir(data_dir):
        p = os.path.join(data_dir, name)
        if name in ("settings.json", "backgrounds", "decor"):
            continue
        if os.path.isdir(p):
            shutil.rmtree(p)
            cleared["categories"].append(name)
        elif name in ("activity_log.jsonl", "ledger.jsonl"):
            os.remove(p)
            cleared["activity"] = True
        else:
            os.remove(p)
    return cleared


@app.route("/api/data/clear", methods=["POST"])
def data_clear():
    data = request.get_json(force=True) or {}
    scope = data.get("scope", "")
    data_dir = get_data_dir()
    if scope == "all":
        cleared = _clear_all_data(data_dir)
        return jsonify({"ok": True, "scope": "all", "cleared": cleared})
    if scope == "unclassified":
        from warehouse import unclassified
        n = unclassified.count(data_dir)
        if n:
            unclassified.remove(data_dir, list(range(n)))
        return jsonify({"ok": True, "scope": "unclassified", "cleared": n})
    if scope == "activity":
        p = os.path.join(data_dir, "activity_log.jsonl")
        removed = []
        if os.path.exists(p):
            os.remove(p)
            removed.append("activity_log.jsonl")
        return jsonify({"ok": True, "scope": "activity", "removed": removed,
                        "message": "主页操作摘要已清除，出入账本未改动"})
    return jsonify({"error": "未知操作"}), 400


# ── API: 删除指定子分类 (设置 → 数据管理) ──────────────
@app.route("/api/subcat/delete", methods=["POST"])
def subcat_delete():
    data = request.get_json(force=True) or {}
    names = data.get("names") or []
    if not names:
        return jsonify({"error": "未选择子分类"}), 400
    store = get_store()
    data_dir = get_data_dir()
    deleted = []
    snapshots = []
    for name in names:
        if primary_owner(name) is None:
            continue
        headers, old_rows = store.load(name)
        if not old_rows:
            continue
        path = store.save(name, [label for _, label in fields_for(name)], [])
        record_activity(data_dir, name, old_rows, [], path=os.path.relpath(path, BASE_DIR))
        deleted.append(name)
        snapshots.append({"subcat": name, "old_rows": old_rows})
    if snapshots:
        from warehouse import undo as undo_mod
        undo_mod.push(data_dir, snapshots, "删除子分类")
    return jsonify({"ok": True, "deleted": deleted})


# ── API: 撤回系统 ─────────────────────────────────────
@app.route("/api/undo", methods=["GET"])
def undo_list():
    from warehouse import undo as undo_mod
    return jsonify({"ok": True, "items": undo_mod.list_recent(get_data_dir())})


@app.route("/api/undo", methods=["POST"])
def undo_apply():
    data = request.get_json(force=True) or {}
    time = (data.get("time") or "").strip()
    if not time:
        return jsonify({"error": "缺少操作时间"}), 400
    from warehouse import undo as undo_mod
    entry = undo_mod.undo(get_data_dir(), time)
    if not entry:
        return jsonify({"error": "该操作不存在或已撤回"}), 404
    return jsonify({"ok": True, "action": entry.get("action", ""),
                    "restored": entry.get("restored", [])})


@app.route("/api/ledger")
def ledger_api():
    records = ledger.load(get_data_dir(), request.args.get("start", ""), request.args.get("end", ""), request.args.get("action", ""))
    # 撤回记录是审计事件，不单独占一行；原始业务操作行显示当前状态。
    records = [r for r in records if r.get("action") != "撤回"]
    return jsonify({"records": records})


@app.route("/api/ledger/undo", methods=["POST"])
def ledger_undo():
    data = request.get_json(force=True) or {}
    undo_id = (data.get("undo_id") or "").strip()
    if not undo_id:
        return jsonify({"error": "缺少账本记录编号"}), 400
    data_dir = get_data_dir()
    source_record = next((x for x in ledger.load(data_dir)
                          if x.get("undo_id") == undo_id and x.get("action") in ("录入", "取出", "调整")), None)
    if not source_record or source_record.get("origin") == "remote":
        return jsonify({"error": "该账本记录不存在或不可撤回"}), 404
    requested = data.get("items") or []
    requested_indexes = {int(x.get("detail_index")) for x in requested
                         if isinstance(x, dict) and str(x.get("detail_index", "")).lstrip("-").isdigit()}
    requested_keys = {(str(x.get("subcat", "")), int(x.get("row", -1)))
                      for x in requested if isinstance(x, dict)}
    selected = []
    for detail_index, detail in enumerate(source_record.get("details") or []):
        key = (str(detail.get("subcat", "")), int(detail.get("row", -1)))
        if detail.get("status", "正常") != "正常":
            continue
        if requested_indexes:
            if detail_index not in requested_indexes:
                continue
        elif requested_keys and key not in requested_keys:
            continue
        detail = dict(detail)
        detail["detail_index"] = detail_index
        selected.append(detail)
    if not selected:
        return jsonify({"error": "所选明细已撤回或不存在"}), 400
    from warehouse import undo as undo_mod
    try:
        result = undo_mod.apply_operation(data_dir, undo_id, selected, "undo")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if not result or not result.get("items"):
        return jsonify({"error": "撤回失败，未找到有效明细"}), 400
    updates = {}
    for item in result["items"]:
        updates[f"index:{item['detail_index']}"] = {"status": "已撤回", "note": "已撤回"}
    ledger.update_details(data_dir, source_record.get("record_id", ""), updates)
    ledger.append(data_dir, "已撤回", result["items"], reason=f"撤回 {undo_id}", source="ledger-undo", undo_id=undo_id)
    current = next((x for x in ledger.load(data_dir) if x.get("record_id") == source_record.get("record_id")), source_record)
    return jsonify({"ok": True, "status": current.get("status", "部分撤回"),
                    "restored": result["items"], "record_id": source_record.get("record_id")})


@app.route("/api/ledger/restore", methods=["POST"])
def ledger_restore():
    data = request.get_json(force=True) or {}
    undo_id = (data.get("undo_id") or "").strip()
    if not undo_id:
        return jsonify({"error": "缺少账本记录编号"}), 400
    data_dir = get_data_dir()
    source_record = next((x for x in ledger.load(data_dir)
                          if x.get("undo_id") == undo_id and x.get("action") in ("录入", "取出", "调整")), None)
    if not source_record or source_record.get("origin") == "remote":
        return jsonify({"error": "该账本记录不存在或不可恢复"}), 404
    requested = data.get("items") or []
    requested_indexes = {int(x.get("detail_index")) for x in requested
                         if isinstance(x, dict) and str(x.get("detail_index", "")).lstrip("-").isdigit()}
    requested_keys = {(str(x.get("subcat", "")), int(x.get("row", -1)))
                      for x in requested if isinstance(x, dict)}
    selected = []
    for detail_index, detail in enumerate(source_record.get("details") or []):
        key = (str(detail.get("subcat", "")), int(detail.get("row", -1)))
        if detail.get("status", "正常") != "已撤回":
            continue
        if requested_indexes:
            if detail_index not in requested_indexes:
                continue
        elif requested_keys and key not in requested_keys:
            continue
        detail = dict(detail)
        detail["detail_index"] = detail_index
        selected.append(detail)
    if not selected:
        return jsonify({"error": "所选明细未处于已撤回状态"}), 400
    from warehouse import undo as undo_mod
    try:
        result = undo_mod.apply_operation(data_dir, undo_id, selected, "restore")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if not result or not result.get("items"):
        return jsonify({"error": "取消撤回失败，未找到有效明细"}), 400
    updates = {}
    for item in result["items"]:
        updates[f"index:{item['detail_index']}"] = {"status": "正常", "note": ""}
    ledger.update_details(data_dir, source_record.get("record_id", ""), updates)
    ledger.append(data_dir, "取消撤回", result["items"], reason=f"取消撤回 {undo_id}", source="ledger-restore", undo_id=undo_id)
    current = next((x for x in ledger.load(data_dir) if x.get("record_id") == source_record.get("record_id")), source_record)
    return jsonify({"ok": True, "status": current.get("status", "正常"),
                    "restored": result["items"], "record_id": source_record.get("record_id")})


@app.route("/api/ledger/clear", methods=["POST"])
def ledger_clear():
    data_dir = get_data_dir()
    p = os.path.join(data_dir, "ledger.jsonl")
    removed = []
    if os.path.exists(p):
        os.remove(p)
        removed.append("ledger.jsonl")
    return jsonify({"ok": True, "removed": removed, "message": "出入账本已清除，主页摘要未改动"})


# ── API: 浏览页 (统计 + 日志 + 低库存) ─────────────────
@app.route("/api/dashboard")
def dashboard():
    store = get_store()
    stats = store.global_stats()
    logs = load_activity(get_data_dir(), limit=50)
    return jsonify({"stats": stats, "logs": logs})


@app.route("/api/lowstock")
def lowstock():
    store = get_store()
    threshold = request.args.get("threshold", default=10, type=int)
    items = store.low_stock(threshold)
    return jsonify({"threshold": threshold, "items": items})


# ── API: 品牌库 (采购参考: 品牌 / 采购量 / 经营的元器件类别) ──
@app.route("/api/brands")
def brands():
    """品牌聚合: 品牌名称 + 条目数 + 总数量 + 覆盖的一级分类/子分类 + 型号示例。"""
    from warehouse.brands import aggregate
    data = aggregate(get_data_dir())
    return jsonify(data)


@app.route("/api/brands/detail")
def brands_detail():
    """某品牌(含所有别名写法)下的全部元器件行 (只读明细表)。"""
    brand = (request.args.get("brand") or "").strip()
    if not brand:
        return jsonify({"error": "缺少品牌名"}), 400
    from warehouse.brands import detail as brands_detail_rows
    res = brands_detail_rows(get_data_dir(), brand)
    return jsonify({"brand": brand, "items": res["items"], "count": len(res["items"]),
                    "aliases": res["aliases"]})


@app.route("/api/brands/export")
def brands_export():
    """品牌汇总导出为 xlsx (直接下载)。"""
    from io import BytesIO
    from warehouse.brands import export_xlsx
    try:
        data = export_xlsx(get_data_dir())
    except Exception as e:
        return jsonify({"error": f"导出失败: {str(e)[:200]}"}), 500
    fname = f"parts-warehouse_品牌汇总_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        BytesIO(data), as_attachment=True, download_name=fname,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/api/brands/catalog", methods=["POST"])
def brands_catalog():
    """重建品牌库档案 data/品牌库.xlsx (品牌/业务/已购种类/总件数)。"""
    from warehouse.brands import build_catalog
    try:
        p = build_catalog(get_data_dir())
        # 绝对路径返回 (数据目录可能在别的盘, relpath 会跨盘崩溃)
        return jsonify({"ok": True, "path": p})
    except Exception as e:
        return jsonify({"error": f"生成失败: {str(e)[:200]}"}), 500


# ── API: AI 连通性测试 ─────────────────────────────────
@app.route("/api/ollama/models", methods=["GET"])
def ollama_models():
    """探测本地 Ollama: 是否运行 + 已装模型列表。

    返回 {running, base_url, models: [{name, size_gb}], error?}
    """
    import httpx
    url = "http://localhost:11434/api/tags"
    try:
        resp = httpx.get(url, timeout=5)
        if resp.status_code != 200:
            return jsonify({"running": False, "models": [],
                            "error": f"Ollama 服务响应异常 HTTP {resp.status_code}"})
        data = resp.json()
        models = [{
            "name": m.get("name", ""),
            "size_gb": round((m.get("size") or 0) / 1024 ** 3, 2),
        } for m in data.get("models", [])]
        return jsonify({"running": True, "models": models, "base_url": "http://localhost:11434/v1"})
    except Exception as e:
        return jsonify({"running": False, "models": [],
                        "error": "未检测到 Ollama 服务：请先安装并启动 Ollama（ollama.com），"
                                 "再用 `ollama pull qwen2.5:7b` 拉取模型"}), 200


@app.route("/api/ai_test", methods=["POST"])
def ai_test():
    cfg = get_ai_cfg()
    if not cfg:
        return jsonify({"ok": False, "error": "未配置 AI 接口，请先填写 API Key"}), 200
    try:
        import httpx
        url = chat_completions_url(cfg['base_url'])
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"},
            json={
                "model": cfg["model"],
                "messages": [{"role": "user", "content": "回复OK两个字"}],
                "max_tokens": 10,
                "temperature": 0,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            return jsonify({"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}), 200
        reply = resp.json()["choices"][0]["message"]["content"].strip()
        return jsonify({"ok": True, "reply": reply})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300]}), 200


# ── API: 图片文字识别 (OCR) ────────────────────────────
@app.route("/api/ocr", methods=["POST"])
def ocr_recognize():
    """上传图片, 识别其中的文字 (料袋/照片/截图), 返回文本行。"""
    if "file" not in request.files:
        return jsonify({"error": "未收到图片"}), 400
    f = request.files["file"]
    fname = f.filename or ""
    if not fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
        return jsonify({"error": "仅支持 png/jpg/webp/bmp 图片"}), 400
    try:
        from warehouse.ocr import recognize
        lines = recognize(f.read())
        return jsonify({"ok": True, "text": "\n".join(lines), "lines": lines})
    except Exception as e:
        return jsonify({"error": f"OCR 识别失败: {str(e)[:200]}"}), 500


@app.route("/api/ocr/batch", methods=["POST"])
def ocr_recognize_batch():
    """一次上传多张图片并并发 OCR; workers=0 按本机 CPU 自动选择。"""
    from concurrent.futures import ThreadPoolExecutor

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "未收到图片"}), 400
    allowed = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
    invalid = [f.filename or "" for f in files
               if not (f.filename or "").lower().endswith(allowed)]
    if invalid:
        return jsonify({"error": "仅支持 png/jpg/webp/bmp 图片"}), 400

    data = request.form
    try:
        requested = int(data.get("workers", "0") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "线程数必须是 0~8 的整数"}), 400
    if requested < 0 or requested > 8:
        return jsonify({"error": "线程数必须是 0~8 的整数"}), 400

    import os
    cpu_count = os.cpu_count() or 2
    auto_workers = min(8, max(1, cpu_count // 2))
    workers = auto_workers if requested == 0 else requested
    workers = min(workers, len(files))

    try:
        from warehouse.ocr import recognize
        image_bytes = [f.read() for f in files]
        if workers == 1:
            groups = [recognize(raw) for raw in image_bytes]
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                groups = list(executor.map(recognize, image_bytes))
        return jsonify({
            "ok": True,
            "groups": groups,
            "lines": [line for group in groups for line in group],
            "workers": workers,
            "workers_requested": requested,
            "workers_auto": auto_workers,
        })
    except Exception as e:
        return jsonify({"error": f"OCR 识别失败: {str(e)[:200]}"}), 500


def _format_by_rules(text: str):
    """对格式清楚的 OCR 文本做本地整理, 返回文本或 None。"""
    from warehouse.rules import RuleParser

    groups = []
    current = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if line.startswith("【图"):
            if current:
                groups.append(current)
                current = []
            continue
        if line:
            current.append(line)
    if current:
        groups.append(current)
    if not groups:
        groups = [[line.strip()] for line in (text or "").splitlines() if line.strip()]

    items = []
    for group in groups:
        parser = RuleParser()
        item = parser.parse_line(" ".join(group))
        if not item or not item.get("name") or not item.get("cat_key"):
            return None
        items.append(item)
    if not items:
        return None

    def line_for(item):
        values = [item.get("qty", ""), item.get("name", ""),
                  item.get("brand", ""), item.get("package", ""),
                  item.get("spec", ""), item.get("subcat", "")]
        return " ".join(str(value).strip() for value in values if str(value).strip())

    return "\n".join(line_for(item) for item in items)


@app.route("/api/ocr/format", methods=["POST"])
def ocr_format():
    """把 OCR 识别文本按料袋模板整理, 优先本地规则, 复杂文本再调用 AI。"""
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "没有可整理的文本"}), 400

    try:
        local_text = _format_by_rules(text)
    except Exception:
        local_text = None
    if local_text:
        return jsonify({"ok": True, "text": local_text, "source": "rules"})

    cfg = get_ai_cfg()
    if not cfg:
        return jsonify({"error": "未配置 AI 接口，无法自动整理"}), 400
    try:
        from warehouse.ocr import format_text
        out = format_text(text, cfg)
        return jsonify({"ok": True, "text": out, "source": "ai"})
    except Exception as e:
        return jsonify({"error": f"整理失败: {str(e)[:200]}"}), 500


@app.route("/api/ocr/parse_text", methods=["POST"])
def ocr_parse_text():
    """把 OCR 文本直接解析成核对表条目。

    图片/摄像头流程只需要一次结构化 AI 调用；旧的 /api/ocr/format
    保留给手动整理和兼容旧客户端。
    """
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "没有可解析的 OCR 文本"}), 400
    cfg = get_ai_cfg()
    if not cfg:
        return jsonify({"error": "未配置 AI 接口，请到「设置 → AI」填写 API Key"}), 400
    try:
        parser = BatchParser(cfg["api_key"], cfg["base_url"], cfg["model"])
        items = parser.parse_ocr_groups(text)
        return jsonify({"ok": True, "items": items, "dropped_nc": parser.dropped_nc,
                        "usage": parser.usage})
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500
def _camera_names() -> list:
    """用 Windows PnP 枚举摄像头设备友好名, 顺序与 DirectShow 索引一致。

    仅用于给用户看"哪个摄像头是哪个", 失败返回 [] (名称缺失不影响功能)。
    """
    import subprocess
    ps = (
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
        "Get-PnpDevice -PresentOnly | Where-Object { $_.Class -eq 'Camera' -or "
        "($_.Class -eq 'Image' -and $_.FriendlyName -match 'cam') } | "
        "Sort-Object InstanceId | ForEach-Object { $_.FriendlyName }"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, timeout=15, text=True,
            encoding="utf-8", errors="replace",
        )
        return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    except Exception:
        return []


_WIN_TITLE = "PartsWarehouse-Camera (SPACE=CAP BS=UNDO ENTER=DONE)"


def _sanitize_ascii(s) -> str:
    """OpenCV putText 只能画 ASCII, 中文设备名过滤成 '?'。"""
    return "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in (s or ""))


def _pick_resolution(cap) -> tuple:
    """探测摄像头实际能出的最高分辨率, 返回 (w, h)。"""
    import time
    import cv2
    for w, h in [(1920, 1080), (1280, 1024), (1280, 720), (960, 540)]:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        time.sleep(0.08)
        ret, frame = cap.read()
        if ret and frame is not None:
            return frame.shape[1], frame.shape[0]
    return 1280, 720


LUM_DARK = 60        # 低于此值视为太暗 (实测用户环境约 57, OCR 甜区约 80~180)
LUM_BRIGHT = 200     # 高于此值视为太亮


def _lum_of(frame) -> int:
    """感知亮度 0~255 (OpenCV GRAY = 0.299R+0.587G+0.114B)。"""
    import cv2
    return int(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean())


def _draw_hud(frame, n_photos: int, device: int, device_name: str, res_text: str,
              lum: int = 128, warn_text: str = "", flash: bool = False):
    """给预览帧画半透明 HUD: 顶部信息条 / 拍摄数徽标 / 实时亮度 / 三分线 / 底部按键条。

    putText 只能画 ASCII → 设备名先过 _sanitize_ascii, 中文提示留在网页上。
    """
    import cv2
    import numpy as np
    _FONT = cv2.FONT_HERSHEY_SIMPLEX
    h, w = frame.shape[:2]
    out = frame.copy()

    # 取景三分线 (半透明细线, 最底层)
    overlay = out.copy()
    thin = max(1, w // 900)
    for i in (1, 2):
        cv2.line(overlay, (w * i // 3, 0), (w * i // 3, h), (255, 255, 255), thin)
        cv2.line(overlay, (0, h * i // 3), (w, h * i // 3), (255, 255, 255), thin)
    out = cv2.addWeighted(overlay, 0.16, out, 0.84, 0)

    # 顶部信息条 (深色半透明, 两行: 标题+徽标 / 设备+分辨率+亮度)
    bar_h = max(54, h // 12)
    overlay = out.copy()
    cv2.rectangle(overlay, (0, 0), (w, bar_h), (10, 16, 28), -1)
    out = cv2.addWeighted(overlay, 0.66, out, 0.34, 0)
    cv2.putText(out, "PARTS WAREHOUSE", (14, 23), _FONT, 0.62,
                (255, 180, 60), 2, cv2.LINE_AA)
    name = _sanitize_ascii(device_name) or f"Cam {device}"
    cv2.putText(out, f"{name}  |  {res_text}", (14, bar_h - 10), _FONT, 0.5,
                (190, 205, 225), 1, cv2.LINE_AA)

    # 右上角拍摄数徽标 (第一行, 绿点 + 数字)
    label = f"{n_photos} SHOT"
    (tw, _), _ = cv2.getTextSize(label, _FONT, 0.6, 2)
    bx = w - tw - 26
    cv2.circle(out, (bx - 9, 22), 6, (50, 210, 100), -1)
    cv2.putText(out, label, (bx, 30), _FONT, 0.6, (255, 255, 255), 2, cv2.LINE_AA)

    # 亮度 (第二行右侧, 按三档着色: 正常绿 / 太暗橙 / 太亮黄)
    if lum < LUM_DARK:
        lum_label, lum_color = f"LUM {lum} DARK - LIGHT?", (0, 165, 255)
    elif lum > LUM_BRIGHT:
        lum_label, lum_color = f"LUM {lum} BRIGHT - SHADE?", (0, 255, 255)
    else:
        lum_label, lum_color = f"LUM {lum} NORMAL", (140, 255, 140)
    (lw, _), _ = cv2.getTextSize(lum_label, _FONT, 0.55, 2)
    cv2.putText(out, lum_label, (w - lw - 16, bar_h - 10), _FONT, 0.55,
                lum_color, 2, cv2.LINE_AA)

    # 拍照亮度异常警告浮层 (画面中上方, 大橙字, 约 1.3s 自动消失)
    if warn_text:
        (ww, wh), _ = cv2.getTextSize(warn_text, _FONT, 1.0, 3)
        wx, wy = (w - ww) // 2, max(bar_h + 46, int(h * 0.2))
        overlay = out.copy()
        cv2.rectangle(overlay, (wx - 16, wy - wh - 10), (wx + ww + 16, wy + 8),
                      (10, 16, 28), -1)
        out = cv2.addWeighted(overlay, 0.7, out, 0.3, 0)
        cv2.putText(out, warn_text, (wx, wy), _FONT, 1.0, (0, 165, 255), 3, cv2.LINE_AA)

    # 底部按键条 (深色半透明)
    bar_h2 = max(52, h // 11)
    overlay = out.copy()
    cv2.rectangle(overlay, (0, h - bar_h2), (w, h), (10, 16, 28), -1)
    out = cv2.addWeighted(overlay, 0.66, out, 0.34, 0)
    cv2.putText(out, "[SPACE] CAPTURE   [BS] UNDO   [ENTER] DONE   [ESC] EXIT",
                (14, h - bar_h2 // 2 + 6), _FONT, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

    # 拍照闪光反馈
    if flash:
        out = cv2.addWeighted(out, 0.76, np.full_like(out, 255), 0.24, 0)
    return out


def _camera_capture_session(data_dir: str, device: int = 1, max_photos: int = 30,
                            timeout_s: int = 180, device_name: str = "") -> list:
    """打开指定摄像头弹窗: 空格=拍照, 回车=结束。

    自动取该摄像头最高分辨率, 拍照存原帧 (OCR 识别更清晰), 预览带 HUD。
    照片存 data/cache/ 后返回 bytes 列表 (调用方识别后删除)。
    返回 [] 表示摄像头不可用或未拍到。
    """
    import time
    import cv2
    import numpy as np

    # 压掉探测不存在索引时的 DSHOW/MSMF WARN 刷屏
    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    except Exception:
        pass

    # DSHOW 失败换 MSMF 后端, 应对驱动不稳定
    cap = None
    for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF):
        cap = cv2.VideoCapture(device, backend)
        if cap.isOpened():
            break
        cap.release()
        cap = None
    if cap is None:
        return []

    # 外置 USB 摄像头默认 YUYV 高分辨率, USB 带宽大 → read 容易失败/黑屏。
    # 尽量切 MJPG 编码 + 小缓冲, 设置失败不影响使用。
    try:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    except Exception:
        pass
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    res_w, res_h = _pick_resolution(cap)      # 自动取最高实际分辨率
    res_text = f"{res_w}x{res_h}"

    cache_dir = os.path.join(data_dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    photos = []           # [(path, bytes, lum)]
    start = time.time()
    no_frame = 0          # 连续丢帧计数
    flash_pending = False # 拍照后下一帧闪白反馈
    warn_pending = ""     # 拍照亮度异常警告文本
    warn_frames = 0       # 警告剩余帧数 (~1.3s 自动消失)
    cv2.namedWindow(_WIN_TITLE, cv2.WINDOW_NORMAL)   # 可拖动缩放窗口
    cv2.resizeWindow(_WIN_TITLE, 960, int(960 * res_h / res_w))
    try:
        while time.time() - start < timeout_s:
            ret, frame = cap.read()
            if not ret:
                # 丢帧重试: 外置 USB 摄像头驱动起步慢/偶发丢帧,
                # 立即退出会表现为"摄像头一闪就关"。
                no_frame += 1
                if no_frame == 1:
                    blank = np.zeros((540, 960, 3), np.uint8)
                    cv2.putText(blank, "Waiting for camera frame...", (12, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
                    cv2.imshow(_WIN_TITLE, blank)
                if no_frame >= 60:   # 连续约 2s 无帧才放弃
                    break
                cv2.waitKey(30)
                continue
            no_frame = 0
            # 实时亮度 (感知灰度均值), 供 HUD 显示 + 拍照异常提醒
            lum = _lum_of(frame)
            fh, fw = frame.shape[:2]
            scale = 960.0 / fw
            disp = cv2.resize(frame, (960, int(fh * scale)))
            warn_text = warn_pending if warn_frames > 0 else ""
            disp = _draw_hud(disp, len(photos), device, device_name, res_text,
                             lum=lum, warn_text=warn_text, flash=flash_pending)
            flash_pending = False
            if warn_frames > 0:
                warn_frames -= 1
            cv2.imshow(_WIN_TITLE, disp)
            k = cv2.waitKey(30) & 0xFF
            # 窗口被用户手动关闭 (点 X) → 视为取消, 干净退出 (防止 imshow 已销毁窗口后崩溃)
            if cv2.getWindowProperty(_WIN_TITLE, cv2.WND_PROP_VISIBLE) < 1:
                photos.clear()
                break
            if k in (13, 10):          # 回车: 结束
                break
            elif k == 32:              # 空格: 拍照 (存原帧, 分辨率不缩)
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                if ok:
                    fname = f"cam_{int(time.time()*1000)}_{len(photos)}.jpg"
                    path = os.path.join(cache_dir, fname)
                    with open(path, "wb") as f:
                        f.write(buf.tobytes())
                    photos.append((path, buf.tobytes(), lum))
                    flash_pending = True
                    # 亮度异常: 浮层警告约 1.3s, 提醒重拍
                    if lum < LUM_DARK:
                        warn_pending, warn_frames = "!! LOW LIGHT !!", 40
                    elif lum > LUM_BRIGHT:
                        warn_pending, warn_frames = "!! TOO BRIGHT !!", 40
                if len(photos) >= max_photos:
                    break
            elif k == 8:               # Backspace: 撤回最近一张
                if photos:
                    path, _, _ = photos.pop()
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            elif k == 27:              # ESC: 取消
                photos.clear()
                break
    finally:
        # 稍等驱动收尾再释放, 降低反复开关 USB 摄像头时驱动状态错乱概率
        time.sleep(0.3)
        try:
            cap.release()
        except Exception:
            pass
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
    return photos


# 探测结果缓存: 全量扫描要 5~10 秒, 30 秒内复用, 点"重新检测"强制重扫
_camera_cache = {"ts": 0.0, "devices": None}
_CAMERA_CACHE_TTL = 30.0


def _probe_index(idx: int) -> bool:
    """单个索引探测 (独立线程执行以便超时保护, 防 DSHOW 偶发卡死)。"""
    import time
    import cv2
    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    except Exception:
        pass
    for attempt in range(2):
        for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF):
            cap = cv2.VideoCapture(idx, backend)
            if not cap.isOpened():
                cap.release()
                continue
            # read 等待首帧, 重试 3 次
            for _ in range(3):
                ret, frame = cap.read()
                if ret and frame is not None:
                    cap.release()
                    return True
            cap.release()
        time.sleep(0.3)   # 驱动未就绪, 稍等重试
    return False


@app.route("/api/camera/list", methods=["GET"])
def camera_list():
    """扫描可用摄像头, 返回 [{index, ok, name}, ...] (探测 0~8)。

    每个设备: DSHOW 失败换 MSMF, 打开后 read 重试, 失败稍等再试一次,
    应对驱动初始化慢 / 摄像头刚插上的情况; 单个索引超时 4s 判失败,
    避免 DSHOW 偶发卡死拖死整个探测。
    name 来自 Windows PnP 设备名, 按探测到的顺序对应 (拿不到名称为空串)。
    ?force=1 强制重新扫描 (前端"🔄 重新检测")。
    """
    import time
    from concurrent.futures import ThreadPoolExecutor

    global _camera_cache
    if _camera_cache["devices"] is not None and \
            time.time() - _camera_cache["ts"] < _CAMERA_CACHE_TTL and \
            request.args.get("force") != "1":
        return jsonify({"ok": True, "devices": _camera_cache["devices"]})

    names = _camera_names()
    ok_flags = {}
    with ThreadPoolExecutor(max_workers=9) as ex:
        futs = {ex.submit(_probe_index, i): i for i in range(9)}
        for fut, idx in futs.items():
            try:
                ok_flags[idx] = fut.result(timeout=4)
            except Exception:
                ok_flags[idx] = False
    devices = []
    ok_order = 0
    for idx in range(9):
        ok = bool(ok_flags.get(idx))
        name = names[ok_order] if ok and ok_order < len(names) else ""
        if ok:
            ok_order += 1
        devices.append({"index": idx, "ok": ok, "name": name})
    _camera_cache = {"ts": time.time(), "devices": devices}
    return jsonify({"ok": True, "devices": devices})


@app.route("/api/camera/capture", methods=["POST"])
def camera_capture():
    """打开指定摄像头拍照 (空格拍照/回车结束), 逐张 OCR, 照片识别后删除。

    body: {device: 摄像头编号}  (默认 1)
    返回 {ok, n, groups: [[行,...], ...]} (每张图一组文本行)。
    """
    body = request.get_json(force=True, silent=True) or {}
    device = int(body.get("device", 1))
    data_dir = get_data_dir()
    # 从探测缓存里带出设备名 (HUD 顶部显示用, 查不到就用 Cam N)
    dev_name = ""
    if _camera_cache["devices"]:
        for d in _camera_cache["devices"]:
            if d.get("index") == device:
                dev_name = d.get("name") or ""
                break
    photos = _camera_capture_session(data_dir, device=device, device_name=dev_name)
    if not photos:
        return jsonify({"error": f"摄像头 {device} 不可用或未拍到照片"}), 400
    try:
        from warehouse.ocr import recognize
        groups = []
        n_dark = 0
        n_bright = 0
        for path, buf, lum in photos:
            if lum < LUM_DARK:
                n_dark += 1
            elif lum > LUM_BRIGHT:
                n_bright += 1
            try:
                groups.append(recognize(buf))
            except Exception as e:
                groups.append([])
            finally:
                # 照片用完即删 (缓存不残留)
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
        # 亮度异常提醒 (OCR 过暗/过亮会识别不准)
        warn_light = ""
        if n_dark and n_bright:
            warn_light = f"有 {n_dark} 张过暗、{n_bright} 张过亮，识别可能不准，建议补拍"
        elif n_dark:
            warn_light = f"有 {n_dark} 张照片环境过暗，识别可能不准，建议开灯补拍"
        elif n_bright:
            warn_light = f"有 {n_bright} 张照片过亮/反光，识别可能不准，建议避开强光补拍"
        return jsonify({"ok": True, "n": len(photos), "groups": groups,
                        "warn_light": warn_light})
    except Exception as e:
        return jsonify({"error": f"识别失败: {str(e)[:200]}"}), 500


# ── API: 数据包 导出/导入 (ZIP) ────────────────────────
@app.route("/api/data/export", methods=["POST"])
def data_export():
    """一键导出全部元器件数据为 ZIP。

    body: {out_dir: 导出目录, 缺省存 data/exports/}
    """
    from warehouse.packfile import export_package
    body = request.get_json(force=True, silent=True) or {}
    try:
        r = export_package(get_data_dir(), out_dir=body.get("out_dir") or "")
        return jsonify(r)
    except Exception as e:
        return jsonify({"error": f"导出失败: {str(e)[:200]}"}), 500


@app.route("/api/data/import", methods=["POST"])
def data_import():
    """一键导入 ZIP 数据包 (合并模式, 导入前自动备份)。"""
    from warehouse.packfile import import_package
    if "file" not in request.files:
        return jsonify({"error": "未收到数据包文件"}), 400
    f = request.files["file"]
    if not (f.filename or "").lower().endswith(".zip"):
        return jsonify({"error": "仅支持 .zip 数据包"}), 400
    try:
        r = import_package(get_data_dir(), f.read(), project_root=BASE_DIR)
        return jsonify(r)
    except zipfile.BadZipFile:
        return jsonify({"error": "导入失败：文件不是有效的 ZIP 数据包，可能已损坏或扩展名不正确。请重新导出数据包后再导入。"}), 400
    except ValueError as e:
        return jsonify({"error": f"导入失败：{str(e)[:300]}"}), 400
    except Exception as e:
        return jsonify({"error": f"导入失败：{str(e)[:200]}"}), 500


# ── API: 批量导入 ──────────────────────────────────────
@app.route("/api/import_parse_text", methods=["POST"])
def import_parse_text():
    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "内容为空"}), 400
    cfg = get_ai_cfg()
    if not cfg:
        return jsonify({"error": "未配置 AI 接口，请到「设置 → AI」填写 API Key"}), 400
    try:
        parser = BatchParser(cfg["api_key"], cfg["base_url"], cfg["model"])
        items = parser.parse_text(text)
        return jsonify({"ok": True, "items": items, "dropped_nc": parser.dropped_nc,
                        "usage": parser.usage})
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500


@app.route("/api/import_parse_excel", methods=["POST"])
def import_parse_excel():
    cfg = get_ai_cfg()
    if not cfg:
        return jsonify({"error": "未配置 AI 接口，请到「设置 → AI」填写 API Key"}), 400
    if "file" not in request.files:
        return jsonify({"error": "未收到文件"}), 400
    f = request.files["file"]
    fname = f.filename or ""
    if not fname.lower().endswith((".xlsx", ".xls")):
        return jsonify({"error": "仅支持 .xlsx / .xls 文件"}), 400
    raw_file = f.read()
    if not raw_file:
        return jsonify({"error": "导入文件为空"}), 400
    try:
        parser = BatchParser(cfg["api_key"], cfg["base_url"], cfg["model"])
        items, preview = parser.parse_excel(raw_file, fname)
        return jsonify({"ok": True, "items": items, "preview": preview,
                        "filename": fname, "dropped_nc": parser.dropped_nc,
                        "usage": parser.usage})
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500


@app.route("/api/import_parse_rules", methods=["POST"])
def import_parse_rules():
    """脚本解析 (纯规则, 无 AI): 支持粘贴文本 {text} 或上传文件 (excel/txt)。

    返回 {ok, items, dropped_nc, mode: "rules"}。
    """
    from warehouse.rules import RuleParser
    text = ""
    if "file" in request.files:
        f = request.files["file"]
        fname = (f.filename or "").lower()
        data = f.read()
        if fname.endswith((".xlsx", ".xls")):
            cfg = get_ai_cfg() or {"api_key": "", "base_url": "", "model": ""}
            parser = BatchParser(cfg["api_key"], cfg["base_url"], cfg["model"])
            items, _preview = parser.parse_excel(data, f.filename or fname)
            return jsonify({"ok": True, "items": items, "dropped_nc": parser.dropped_nc,
                            "mode": "rules"})
        else:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = data.decode("gbk", errors="ignore")
        if not text.strip():
            return jsonify({"error": "文件内容为空"}), 400
    else:
        body = request.get_json(force=True, silent=True) or {}
        text = (body.get("text") or "").strip()
        if not text:
            return jsonify({"error": "内容为空"}), 400
    try:
        parser = RuleParser()
        items = parser.parse_text(text)
        return jsonify({"ok": True, "items": items, "dropped_nc": parser.dropped_nc,
                        "mode": "rules"})
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500


@app.route("/api/import_commit", methods=["POST"])
def import_commit():
    data = request.get_json(force=True)
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "没有可写入的数据"}), 400
    cfg = get_ai_cfg()
    if not cfg:
        return jsonify({"error": "未配置 AI 接口"}), 400
    try:
        parser = BatchParser(cfg["api_key"], cfg["base_url"], cfg["model"])
        result = parser.commit(items, get_data_dir())
        return jsonify({"ok": True, "result": result, "total": len(items)})
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500


# ── API: AI 快速填入 ───────────────────────────────────
@app.route("/api/ai_fill", methods=["POST"])
def ai_fill():
    data = request.get_json(force=True)
    name = (data.get("subcat") or "").strip()
    desc = (data.get("desc") or "").strip()
    if not name or primary_owner(name) is None:
        return jsonify({"error": "未知子分类"}), 404
    if not desc:
        return jsonify({"error": "描述为空"}), 400
    cfg = get_ai_cfg()
    if not cfg:
        return jsonify({"error": "未配置 AI 接口，请到「设置 → AI」填写 API Key"}), 500
    try:
        fields = fields_for(name)
        parsed = AIFiller(
            api_key=cfg["api_key"], base_url=cfg["base_url"], model=cfg["model"]
        ).parse(name, desc, fields, subcat_list=None)
        return jsonify({"ok": True, "item": parsed})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def main():
    threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    # threaded=True: 摄像头拍照/探测等阻塞端点不能卡死整个服务
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)


if __name__ == "__main__":
    main()
