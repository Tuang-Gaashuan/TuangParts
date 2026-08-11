# -*- coding: utf-8 -*-
"""元器件仓库 — 统一设置 (数据路径 / AI 接口 / 界面主题)。

存于 data/settings.json (exe 旁的可写文件), 不打包进程序。
兼容旧版 data/ai_config.json (迁移后优先 settings.json)。

主题色系: theme 为 CSS 主题名 (light-blue / dark / green / orange / purple)。
背景图: 上传后存 data/backgrounds/<文件>, 路径记录在 settings。
"""

import json
import os
import shutil

DEFAULT_SETTINGS = {
    "data_dir": "",            # 空 = 使用程序默认 data/ 目录
    "theme": "light-blue",     # 界面色系
    "background": "",          # 背景图相对 data 的路径 (如 backgrounds/xxx.png)
    "bg_brightness": 100,      # 背景图亮度 % (30-200)
    "bg_opacity": 100,         # 背景图透明度 % (0-100)
    "card_opacity": 100,       # 卡片透明度 % (0-100)
    "bg_fill": "cover",        # 背景图填充方式: cover铺满裁剪 / contain完整留边 / stretch拉伸 / repeat平铺 / original原始尺寸
    "decor1": "static/deco_parts.png",    # 首页装饰图1 (空 = 隐藏)
    "decor2": "static/deco_circuit.png",  # 首页装饰图2 (空 = 隐藏)
    "ai": {
        "provider": "online",   # online=在线API | ollama=本地离线模型
        "base_url": "https://api.deepseek.com",
        "api_key": "",
        "model": "deepseek-chat",
    },
}


def settings_path(app_dir: str) -> str:
    return os.path.join(app_dir, "data", "settings.json")


def _migrate_legacy(app_dir: str, s: dict) -> dict:
    """旧版 ai_config.json 迁移到 settings.json 的 ai 段。"""
    legacy = os.path.join(app_dir, "data", "ai_config.json")
    if os.path.exists(legacy) and not s["ai"].get("api_key"):
        try:
            with open(legacy, encoding="utf-8") as f:
                old = json.load(f)
            s["ai"] = {
                "base_url": old.get("base_url", DEFAULT_SETTINGS["ai"]["base_url"]),
                "api_key": old.get("api_key", ""),
                "model": old.get("model", DEFAULT_SETTINGS["ai"]["model"]),
            }
        except (json.JSONDecodeError, OSError):
            pass
    return s


def load_settings(app_dir: str) -> dict:
    """读取设置 (应用默认值 + 迁移旧配置)。"""
    s = json.loads(json.dumps(DEFAULT_SETTINGS))  # 深拷贝
    p = settings_path(app_dir)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                saved = json.load(f)
            for k in s:
                if k in saved:
                    if isinstance(s[k], dict) and isinstance(saved[k], dict):
                        s[k].update(saved[k])
                    else:
                        s[k] = saved[k]
        except (json.JSONDecodeError, OSError):
            pass
    s = _migrate_legacy(app_dir, s)
    return s


def save_settings(app_dir: str, patch: dict) -> dict:
    """合并保存设置。patch 可为部分字段。"""
    s = load_settings(app_dir)
    for k, v in patch.items():
        if k == "ai" and isinstance(v, dict):
            s["ai"].update(v)
        elif k in s:
            s[k] = v
    p = settings_path(app_dir)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    return s


def resolve_data_dir(app_dir: str) -> str:
    """实际数据目录: 用户配置优先, 否则默认 app_dir/data。"""
    s = load_settings(app_dir)
    custom = (s.get("data_dir") or "").strip()
    if custom:
        return os.path.abspath(custom)
    return os.path.join(app_dir, "data")


def chat_completions_url(base_url: str) -> str:
    """兼容多种 base_url 写法。

    - 已含版本段 (/v1, /v4 等, 如智谱 /api/paas/v4、硅基流动 /v1、通义 /compatible-mode/v1) → 直接追加
    - 不含 (DeepSeek/OpenAI 风格 https://api.deepseek.com) → 补 /v1
    """
    import re
    b = (base_url or "").strip().rstrip("/")
    if re.search(r"/v\d+$", b):
        return b + "/chat/completions"
    return b + "/v1/chat/completions"


def public_view(s: dict) -> dict:
    """对外展示 (key 脱敏)。"""
    key = s["ai"].get("api_key", "")
    masked = ""
    if key:
        masked = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
    return {
        "data_dir": s.get("data_dir", ""),
        "theme": s.get("theme", "light-blue"),
        "background": s.get("background", ""),
        "bg_brightness": s.get("bg_brightness", 100),
        "bg_opacity": s.get("bg_opacity", 100),
        "card_opacity": s.get("card_opacity", 100),
        "bg_fill": s.get("bg_fill", "cover"),
        "decor1": s.get("decor1", "static/deco_parts.png"),
        "decor2": s.get("decor2", "static/deco_circuit.png"),
        "ai": {
            "provider": s["ai"].get("provider", "online"),
            "base_url": s["ai"].get("base_url", ""),
            "model": s["ai"].get("model", ""),
            "configured": bool(key),
            "api_key_masked": masked,
        },
    }
