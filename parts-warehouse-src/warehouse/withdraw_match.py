# -*- coding: utf-8 -*-
"""元器件仓库 — BOM 取出匹配 (替换料机制)。

导入 BOM 后, 为每个需要的元件在现有库存中找「值+封装」匹配的候选:
- 电容/电阻/电感: 值 (容值/阻值/感值) 从 名称+规格 提取并归一化比较,
  封装宽松匹配 (C0603≈0603, 0603贴片≈0603)。
- 二极管/芯片等无"值"的: 按元件名字匹配, 封装也需一致。
- 值+封装相同但 耐压/品牌/精度 不同的候选全部列出, 由用户选择替换 (替换料机制)。
- 封装不一致的候选不列出; 完全没有匹配的项单独标记, 方便用户知道缺什么。

返回结构: [{item, candidates: [{subcat, row, name, brand, package, spec, qty}]}]
"""

import re

from warehouse.excel_store import ExcelStore

# ── 值归一化 ──────────────────────────────────────────
def _unify_micro(text: str) -> str:
    """把 µ (U+00B5) 和 μ (U+03BC) 统一为 u (常见于 10uF/10μH 两种写法)。"""
    return str(text).replace("µ", "u").replace("μ", "u")


def _cap_pf(text: str) -> int | None:
    """电容容值 → pF (10uF→10000000, 100nF→100000, 22pF→22)。"""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(u|n|p|m)?F", _unify_micro(text), re.IGNORECASE)
    if not m:
        return None
    v = float(m.group(1))
    u = (m.group(2) or "").lower()
    mult = {"u": 1e6, "n": 1e3, "p": 1, "m": 1e9}.get(u, 1)
    return int(round(v * mult))


def _res_ohm(text: str) -> int | None:
    """电阻阻值 → Ω (10KΩ→10000, 2KΩ→2000, 50mΩ→0→取整? 100Ω→100, 1M→1000000)。"""
    m = re.search(r"(\d+(?:\.\d+)?)\s*([mMkK])?\s*(?:Ω|ohm|R)?", str(text), re.IGNORECASE)
    if not m:
        return None
    v = float(m.group(1))
    u = m.group(2) or ""
    if u == "k" or u == "K":
        v *= 1e3
    elif u == "M":
        v *= 1e6
    elif u == "m":
        v *= 1e-3   # 毫欧 (50mΩ = 0.05Ω)
    return int(round(v))


def _ind_nh(text: str) -> int | None:
    """电感感值 → nH (10uH→10000, 22nH→22, 1mH→1000000)。"""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(m|u|n)?H", _unify_micro(text), re.IGNORECASE)
    if not m:
        return None
    v = float(m.group(1))
    u = (m.group(2) or "").lower()
    mult = {"m": 1e6, "u": 1e3, "n": 1}.get(u, 1)
    return int(round(v * mult))


VALUE_CATS = ("capacitor", "resistor", "inductor")


def norm_value(cat: str, text: str) -> tuple | None:
    """值类元件提取归一化值: ('cap', pF) / ('res', Ω) / ('ind', nH)。"""
    if not text or cat not in VALUE_CATS:
        return None
    if cat == "capacitor":
        v = _cap_pf(text)
        return ("cap", v) if v is not None else None
    if cat == "resistor":
        v = _res_ohm(text)
        return ("res", v) if v is not None else None
    v = _ind_nh(text)
    return ("ind", v) if v is not None else None


# ── 封装归一化 / 匹配 ─────────────────────────────────
def norm_pkg(text) -> str:
    """封装归一化: 小写、去非字母数字 (SMD-3X3→smd3x3, C0603→c0603)。"""
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def pkg_match(a: str, b: str) -> bool:
    """封装匹配: 归一化后相等, 或较短一方(≥3字符)包含于另一方。"""
    a, b = norm_pkg(a), norm_pkg(b)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 3 and len(b) >= 3 and (a in b or b in a):
        return True
    return False


def _norm_name(text) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


# ── 主匹配 ────────────────────────────────────────────
def _name_similar(a: str, b: str) -> bool:
    """名字相似: 归一化后相等 / 包含 / 编辑相似度 ≥ 0.72。"""
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 3 and len(b) >= 3 and (a in b or b in a):
        return True
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio() >= 0.72


def match_items(items: list, data_dir: str) -> list:
    """为 BOM 条目匹配库存候选。

    候选分两级:
      exact   — 值(或名) + 封装 均匹配
      similar — 值(或名) 匹配但封装不同 (替换料/封装写法差异), 标记 pkg_note。
    完全无相似候选的条目 → 前端显示「无库存」。
    """
    store = ExcelStore(data_dir)

    # 预加载全部库存行
    all_rows = []   # [(subcat, row_idx, row)]
    for subcat in store.all_subcat_counts():
        _, rows = store.load(subcat)
        for i, r in enumerate(rows):
            all_rows.append((subcat, i, r))

    # 值类只搜对应一级分类 (避免连接器等名称含 "1.0K" 被误当电阻值)
    from warehouse.config import primary_owner
    VALUE_OWNER = {"capacitor": "capacitor", "resistor": "resistor", "inductor": "inductor"}

    def row_candidate(subcat, i, r, match_type, pkg_note=""):
        return {
            "subcat": subcat,
            "row": i,
            "name": str(r[0] or "") if len(r) > 0 else "",
            "brand": str(r[1] or "") if len(r) > 1 else "",
            "package": str(r[2] or "") if len(r) > 2 else "",
            "qty": str(r[3] or "") if len(r) > 3 else "",
            "spec": str(r[6] or "") if len(r) > 6 else "",
            "match_type": match_type,
            "pkg_note": pkg_note,
        }

    results = []
    for it in items:
        cat = it.get("cat_key") or ""
        item_text = f"{it.get('name', '')} {it.get('spec', '')}"
        need_val = norm_value(cat, item_text)
        need_pkg = it.get("package") or ""
        need_name = _norm_name(it.get("name"))

        exact, similar = [], []
        if need_val is not None:
            # 值类: 值相同 → 候选 (仅搜索同属一个一级分类的库存行)
            owner = VALUE_OWNER.get(cat)
            for subcat, i, r in all_rows:
                if owner is not None and primary_owner(subcat) != owner:
                    continue
                row_text = f"{r[0] if len(r) > 0 else ''} {r[6] if len(r) > 6 else ''}"
                if norm_value(cat, row_text) == need_val:
                    row_pkg = r[2] if len(r) > 2 else ""
                    if pkg_match(need_pkg, row_pkg):
                        exact.append(row_candidate(subcat, i, r, "exact"))
                    else:
                        similar.append(row_candidate(
                            subcat, i, r, "similar",
                            f"封装不同: BOM {need_pkg} / 库存 {row_pkg}",
                        ))
        elif need_name:
            # 名字类 (二极管/芯片等): 型号必须完全一致才算精确;
            # 型号不同但相似的只列「相似」(替换料), 并标注「型号不同」警示。
            for subcat, i, r in all_rows:
                rname = _norm_name(r[0] if len(r) > 0 else "")
                if not rname:
                    continue
                row_pkg = r[2] if len(r) > 2 else ""
                if rname == need_name:
                    # 型号完全一致 → 精确 (封装也一致才算 exact, 否则降级 similar)
                    if pkg_match(need_pkg, row_pkg):
                        exact.append(row_candidate(subcat, i, r, "exact"))
                    else:
                        similar.append(row_candidate(
                            subcat, i, r, "similar",
                            f"封装不同: BOM {need_pkg} / 库存 {row_pkg}",
                        ))
                elif _name_similar(need_name, rname):
                    # 型号不同但相似 → 仅列相似, 标注型号差异 (绝不冒充精确)
                    note = f"型号不同: BOM {it.get('name', '')} / 库存 {r[0] if len(r) > 0 else ''}"
                    if not pkg_match(need_pkg, row_pkg):
                        note += f"; 封装不同: BOM {need_pkg} / 库存 {row_pkg}"
                    similar.append(row_candidate(subcat, i, r, "similar", note))

        results.append({"item": it, "candidates": exact + similar})

    return results
