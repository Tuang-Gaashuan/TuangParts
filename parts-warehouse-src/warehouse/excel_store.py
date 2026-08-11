# -*- coding: utf-8 -*-
"""元器件仓库 — Excel 读写 (子分类文件模型).

结构:
  data/                      数据根目录
    <一级分类>/              按一级分类分子文件夹 (safe_filename 处理)
      <子分类>.xlsx          每个子分类一个 Excel 文件 (有数据才创建)

重名子分类 (如"磁珠"在 电感/EMI 下都有): 物理文件只建一份,
多个一级分类入口指向同一文件 (由 config.primary_owner 决定归属)。

空子分类不生成文件, 界面不显示。
"""

import os
from openpyxl import Workbook, load_workbook
from warehouse.config import CATEGORIES, fields_for, safe_filename, primary_owner


class ExcelStore:
    """子分类 -> Excel 文件的读写层。"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

    # ── 路径 ────────────────────────────────────────────
    def subcat_path(self, subcat: str) -> str:
        """子分类 Excel 的绝对路径 (归属第一个一级分类的文件夹)。"""
        owner = primary_owner(subcat)
        if owner is None:
            raise ValueError(f"子分类不存在: {subcat}")
        owner_dir = os.path.join(self.data_dir, safe_filename(CATEGORIES[owner][0]))
        return os.path.join(owner_dir, f"{safe_filename(subcat)}.xlsx")

    def owner_dir(self, key: str) -> str:
        return os.path.join(self.data_dir, safe_filename(CATEGORIES[key][0]))

    # ── 读 ──────────────────────────────────────────────
    def load(self, subcat: str) -> tuple[list, list]:
        """返回 (表头列表, 行数据列表)。文件不存在返回空。"""
        path = self.subcat_path(subcat)
        headers = [label for _, label in fields_for(subcat)]
        if not os.path.exists(path):
            return headers, []
        wb = load_workbook(path)
        ws = wb.active
        rows = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if any(c is not None and str(c).strip() != "" for c in row):
                rows.append(list(row))
        wb.close()
        return headers, rows

    # ── 写 (有数据才建文件) ─────────────────────────────
    def save(self, subcat: str, headers: list, rows: list) -> str:
        """保存子分类数据。rows 为空时删除文件 (空分类不显示)。返回文件路径。"""
        path = self.subcat_path(subcat)
        if not rows:
            # 空数据: 删除文件, 分类自动从界面消失
            if os.path.exists(path):
                os.remove(path)
                self._prune_empty_owner_dir(path)
            return path

        os.makedirs(os.path.dirname(path), exist_ok=True)
        wb = Workbook()
        ws = wb.active
        ws.title = safe_filename(subcat)[:31]
        ws.append(headers)
        for row in rows:
            padded = list(row) + [""] * (len(headers) - len(row))
            ws.append(padded[: len(headers)])
        for i, h in enumerate(headers, 1):
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = max(
                10, min(28, len(str(h)) * 2 + 4)
            )
        wb.save(path)
        wb.close()
        return path

    def _prune_empty_owner_dir(self, path: str):
        """删除子分类文件后, 若所属一级分类文件夹已空则删除该文件夹。"""
        d = os.path.dirname(path)
        try:
            if not os.listdir(d):
                os.rmdir(d)
        except OSError:
            pass

    # ── 统计 ────────────────────────────────────────────
    def count(self, subcat: str) -> int:
        _, rows = self.load(subcat)
        return len(rows)

    def subcats_with_data(self, key: str) -> list:
        """某一级分类下, 有数据的子分类列表 [(子分类名, 条数), ...]。"""
        result = []
        for subcat in CATEGORIES[key][1]:
            n = self.count(subcat)
            if n > 0:
                result.append((subcat, n))
        return result

    def category_total(self, key: str) -> int:
        """某一级分类下所有子分类的记录总数。"""
        return sum(n for _, n in self.subcats_with_data(key))

    def all_overview(self) -> dict:
        """总览: {一级分类key: 该分类记录总数}, 只含有数据的分类。

        未分类 (data/未分类/未分类.xlsx) 有数据时作为一级分类附加。
        """
        result = {key: self.category_total(key) for key in CATEGORIES}
        from warehouse import unclassified
        n = unclassified.count(self.data_dir)
        if n > 0:
            result["unclassified"] = n
        return result

    # ── 全局统计 ────────────────────────────────────────
    def all_subcat_counts(self) -> dict:
        """所有有数据的子分类 -> 条目数。"""
        result = {}
        for key in CATEGORIES:
            for subcat, n in self.subcats_with_data(key):
                # 重名子分类只统计一次 (物理文件唯一)
                result[subcat] = max(result.get(subcat, 0), n)
        return result

    def global_stats(self) -> dict:
        """浏览页统计: 分类数 / 子分类数 / 总条目 / 总数量 / 最多的子分类。"""
        subcat_counts = self.all_subcat_counts()
        # 有数据的一级分类数 (all_overview 含未分类)
        cat_count = sum(1 for total in self.all_overview().values() if total > 0)
        # 未分类元件数 (计入总条目, 不参与 top 统计)
        from warehouse import unclassified
        uncat_n = unclassified.count(self.data_dir)
        # 总数量: 每个有数据子分类文件的 qty 列(索引3)求和
        total_qty = 0
        for subcat in subcat_counts:
            _, rows = self.load(subcat)
            for r in rows:
                try:
                    total_qty += int(float(str(r[3]).strip()))
                except (ValueError, IndexError, TypeError):
                    pass
        # 最多的元器件种类: 条目数最多的子分类
        top = None
        top_n = -1
        for subcat, n in subcat_counts.items():
            if n > top_n:
                top, top_n = subcat, n
        return {
            "categories": cat_count,                      # 有数据的一级分类数 (含未分类)
            "subcats": len(subcat_counts),                # 有数据的子分类数
            "items": sum(subcat_counts.values()) + uncat_n,  # 总条目数 (含未分类)
            "total_qty": total_qty,                        # 总数量
            "top_subcat": {"name": top, "count": top_n} if top else None,
        }

    # 补货规则: 一级分类key -> 提醒阈值 (qty < 阈值 时提醒)
    #   None  = 该分类不参与补货提醒; 未列出的分类用默认阈值
    LOW_STOCK_RULES = {
        "tool": None,   # 工具类不做补货提醒
        "mcu": 2,       # 单片机/微控制器: 仅剩1个(<=1)时提醒, 即 qty < 2
    }

    def low_stock(self, threshold: int = 10) -> list:
        """库存不足扫描: 返回 [{subcat, name, qty, owner, threshold}]。

        按一级分类的补货规则计算 (工具类跳过, 单片机阈值2, 其余默认10)。
        """
        result = []
        for subcat in self.all_subcat_counts():
            owner = primary_owner(subcat)
            if owner in self.LOW_STOCK_RULES and self.LOW_STOCK_RULES[owner] is None:
                continue  # 该分类明确不参与补货提醒 (如工具类)
            eff_threshold = self.LOW_STOCK_RULES.get(owner) or threshold
            _, rows = self.load(subcat)
            for r in rows:
                if len(r) < 4:
                    continue
                try:
                    qty = int(float(str(r[3]).strip()))
                except (ValueError, TypeError):
                    qty = 0
                if qty < eff_threshold:
                    result.append({
                        "subcat": subcat,
                        "name": r[0] if r and r[0] else "(未命名)",
                        "qty": qty,
                        "owner": owner,
                        "threshold": eff_threshold,
                    })
        result.sort(key=lambda x: x["qty"])
        return result
