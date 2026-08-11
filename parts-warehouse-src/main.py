# -*- coding: utf-8 -*-
"""元器件仓库 — 主程序入口 (UI方案4: 卡片总览风)。

界面结构:
  ┌─────────────────────────────────────────────────┐
  │  元器件仓库                    [搜索]  [AI填入] [保存] │
  │  ┌───────────────────────────────────────────┐ │
  │  │  [电阻]  [电容]  [IC]  [二极管]  [三极管]     │ │  ← 分类卡片总览
  │  │  [连接器] [电感]  [晶振]  [保险丝]  [其他]     │ │     (点击进入详情)
  │  └───────────────────────────────────────────┘ │
  │  [← 返回]  分类名: 电阻           (搜索过滤)     │
  │  ┌───────────────────────────────────────────┐ │
  │  │  Treeview 表格 (双击单元格编辑)              │ │
  │  └───────────────────────────────────────────┘ │
  │  状态栏                                        │
  └─────────────────────────────────────────────────┘

启动: python main.py
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from warehouse.config import CATEGORIES, fields_for
from warehouse.excel_store import ExcelStore
from warehouse.ai_fill import AIFiller, get_api_key

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# ── 方案4 配色: 浅灰背景 + 彩色分类卡片 + 蓝绿渐变 ──
BG = "#f3f5f9"        # 主背景浅灰
BG2 = "#ffffff"       # 卡片/面板白
FG = "#1f2937"        # 深灰文字
MUTED = "#6b7280"     # 次要文字
BORDER = "#e5e7eb"    # 边框
ACCENT = "#2563eb"    # 主蓝
ACCENT2 = "#16a34a"   # 绿
CARD_COLORS = {       # 每分类卡片配色 (bg, fg)
    "resistor":    ("#e0eaff", "#1e40af"),
    "capacitor":   ("#dcfce7", "#166534"),
    "ic":          ("#f3e8ff", "#7e22ce"),
    "diode":       ("#fef3c7", "#b45309"),
    "transistor":  ("#fee2e2", "#b91c1c"),
    "connector":   ("#cffafe", "#0e7490"),
    "inductor":    ("#e0e7ff", "#4338ca"),
    "crystal":     ("#d1fae5", "#047857"),
    "fuse":        ("#ffedd5", "#c2410c"),
    "other":       ("#e5e7eb", "#374151"),
}

# 分两行排列的卡片顺序
CARD_ORDER = [
    ["resistor", "capacitor", "ic", "diode", "transistor"],
    ["connector", "inductor", "crystal", "fuse", "other"],
]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("元器件仓库")
        self.geometry("1160x720")
        self.configure(bg=BG)
        self.minsize(960, 600)

        self.store = ExcelStore(DATA_DIR)
        self.current_key = None
        self.headers = []
        self.rows = []
        self.search_text = ""

        self._build_style()
        self._build_layout()
        self.show_overview()
        # 窗口关闭时正常退出
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── 样式 ────────────────────────────────────────────
    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
                        background=BG2, fieldbackground=BG2, foreground=FG,
                        rowheight=28, borderwidth=0, font=("Microsoft YaHei", 10))
        style.configure("Treeview.Heading",
                        background="#eef1f6", foreground="#374151",
                        relief="flat", font=("Microsoft YaHei", 10, "bold"))
        style.map("Treeview",
                  background=[("selected", "#dbeafe")],
                  foreground=[("selected", "#1e40af")])
        style.map("Treeview.Heading", background=[("active", "#e2e8f0")])

    # ── 布局 ────────────────────────────────────────────
    def _build_layout(self):
        self.top = tk.Frame(self, bg=BG)
        self.top.pack(fill="x", padx=20, pady=(14, 8))

        tk.Label(self.top, text="元器件仓库", bg=BG, fg="#111827",
                 font=("Microsoft YaHei", 18, "bold")).pack(side="left")

        tk.Button(self.top, text="保存", bg=ACCENT2, fg="white", relief="flat",
                  font=("Microsoft YaHei", 10, "bold"), padx=16, pady=4,
                  command=self.save).pack(side="right", padx=(6, 0))
        tk.Button(self.top, text="AI 填入", bg=ACCENT, fg="white", relief="flat",
                  font=("Microsoft YaHei", 10, "bold"), padx=16, pady=4,
                  command=self.ai_fill).pack(side="right", padx=6)
        tk.Button(self.top, text="+ 新增行", bg="#64748b", fg="white", relief="flat",
                  font=("Microsoft YaHei", 10), padx=14, pady=4,
                  command=self.add_row).pack(side="right", padx=(6, 0))

        self.search_var = tk.StringVar()
        search = tk.Entry(self.top, textvariable=self.search_var, bg=BG2, fg=FG,
                          insertbackground=FG, relief="solid", bd=1,
                          font=("Microsoft YaHei", 10), width=24)
        search.pack(side="right", padx=10, ipady=2)
        search.bind("<KeyRelease>", lambda e: self.apply_filter())

        # 内容区 (总览页 / 详情页 共用)
        self.content = tk.Frame(self, bg=BG)
        self.content.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        # 状态栏
        self.status = tk.Label(self, text="", bg="#eef1f6", fg=MUTED,
                               anchor="w", padx=20, pady=5,
                               font=("Microsoft YaHei", 9))
        self.status.pack(fill="x", side="bottom")

    # ── 总览页 (方案4: 分类卡片) ─────────────────────────
    def show_overview(self):
        for w in self.content.winfo_children():
            w.destroy()
        self.current_key = None
        self.title_label = None

        counts = self.store.all_counts()
        total = sum(counts.values())

        head = tk.Frame(self.content, bg=BG)
        head.pack(fill="x", pady=(16, 20))
        tk.Label(head, text=f"库存总览", bg=BG, fg="#111827",
                 font=("Microsoft YaHei", 15, "bold")).pack(side="left")
        tk.Label(head, text=f"共 {total} 条元器件记录", bg=BG, fg=MUTED,
                 font=("Microsoft YaHei", 10)).pack(side="left", padx=12)

        cards = tk.Frame(self.content, bg=BG)
        cards.pack(fill="both", expand=True)

        for row_keys in CARD_ORDER:
            rowf = tk.Frame(cards, bg=BG)
            rowf.pack(fill="x", pady=6)
            for key in row_keys:
                self._make_card(rowf, key, counts.get(key, 0))

    def _make_card(self, parent, key: str, count: int):
        name, _ = CATEGORIES[key]
        cbg, cfg = CARD_COLORS.get(key, ("#e5e7eb", "#374151"))

        card = tk.Frame(parent, bg=BG2, highlightbackground=BORDER,
                        highlightthickness=1, cursor="hand2")
        card.pack(side="left", expand=True, fill="x", padx=6)
        card.bind("<Button-1>", lambda e, k=key: self.select_category(k))

        icon = tk.Frame(card, bg=cbg, width=56, height=56)
        icon.pack(side="left", padx=16, pady=16)
        icon.pack_propagate(False)
        tk.Label(icon, text=name[0], bg=cbg, fg=cfg,
                 font=("Microsoft YaHei", 22, "bold")).pack(expand=True)

        body = tk.Frame(card, bg=BG2)
        body.pack(side="left", padx=(4, 16), pady=16)
        tk.Label(body, text=name, bg=BG2, fg="#111827",
                 font=("Microsoft YaHei", 13, "bold")).pack(anchor="w")
        tk.Label(body, text=f"{count} 条记录", bg=BG2, fg=MUTED,
                 font=("Microsoft YaHei", 10)).pack(anchor="w")

        # 整卡可点击
        for w in (card, icon, body):
            for c in w.winfo_children():
                c.bind("<Button-1>", lambda e, k=key: self.select_category(k))

        self.status.config(text="点击分类卡片进入详情 · 双击单元格编辑 · Ctrl+V 粘贴 · 保存写回 Excel")

    # ── 详情页 ──────────────────────────────────────────
    def select_category(self, key: str):
        self.current_key = key
        for w in self.content.winfo_children():
            w.destroy()

        name, _ = CATEGORIES[key]

        # 返回 + 标题 + 搜索
        bar = tk.Frame(self.content, bg=BG)
        bar.pack(fill="x", pady=(8, 8))
        tk.Button(bar, text="‹ 返回总览", bg=BG2, fg=ACCENT, relief="solid", bd=1,
                  font=("Microsoft YaHei", 10), padx=12, pady=3,
                  command=self.show_overview).pack(side="left")
        tk.Label(bar, text=name, bg=BG, fg="#111827",
                 font=("Microsoft YaHei", 15, "bold")).pack(side="left", padx=16)

        # 表格容器
        frame = tk.Frame(self.content, bg=BG2, highlightbackground=BORDER,
                         highlightthickness=1)
        frame.pack(fill="both", expand=True)

        self.headers, self.rows = self.store.load(key)
        self.tree = ttk.Treeview(frame, columns=list(range(len(self.headers))),
                                 show="headings", selectmode="browse")
        for i, h in enumerate(self.headers):
            self.tree.heading(i, text=h)
            self.tree.column(i, width=110, anchor="center", stretch=False)
        self.tree.column(0, width=200, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)

        self.tree.bind("<Double-1>", self._edit_cell)
        self._reload_tree()
        self.update_status()

    def _reload_tree(self):
        """把 self.rows 刷进表格（按搜索过滤）。"""
        self.tree.delete(*self.tree.get_children())
        text = self.search_var.get().strip().lower()
        for i, row in enumerate(self.rows):
            if text and not any(text in str(c).lower() for c in row if c is not None):
                continue
            self.tree.insert("", "end", iid=str(i),
                             values=[c if c is not None else "" for c in row])

    def apply_filter(self):
        if self.current_key:
            self._reload_tree()

    def add_row(self):
        if not self.current_key:
            return
        self.rows.append([""] * len(self.headers))
        self._reload_tree()
        self.update_status()

    # ── 单元格编辑 (双击) ────────────────────────────────
    def _edit_cell(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        iid = self.tree.identify_row(event.y)
        col = int(self.tree.identify_column(event.x)[1:]) - 1
        if not iid:
            return
        row_idx = int(iid)
        bbox = self.tree.bbox(iid, f"#{col + 1}")
        if not bbox:
            return
        x, y, w, h = bbox

        entry = tk.Entry(self.tree)
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, str(self.rows[row_idx][col] or ""))
        entry.focus_set()
        entry.selection_range(0, "end")

        def commit(_=None):
            val = entry.get()
            row = list(self.rows[row_idx])
            row[col] = val
            self.rows[row_idx] = row
            self._reload_tree()
            self.update_status()

        def cancel(_=None):
            entry.destroy()

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", lambda e: (commit(), entry.destroy()))
        entry.bind("<Escape>", cancel)

    # ── 保存 / 状态 ──────────────────────────────────────
    def save(self):
        if not self.current_key:
            messagebox.showinfo("提示", "当前在总览页，先点击分类卡片进入详情再保存。")
            return
        try:
            self.store.save(self.current_key, self.headers, self.rows)
            self.status.config(text=f"✅ 已保存到 data/{CATEGORIES[self.current_key][0]}.xlsx")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def update_status(self):
        if not self.current_key:
            return
        name, _ = CATEGORIES[self.current_key]
        n = len(self.rows)
        self.status.config(
            text=f"分类: {name}  |  条目: {n}  |  双击单元格编辑 · Enter 确认 · 保存写回 Excel"
        )

    # ── AI 填入 ─────────────────────────────────────────
    def ai_fill(self):
        if not self.current_key:
            messagebox.showinfo("提示", "先点击分类卡片进入详情，再使用 AI 填入。")
            return
        if not get_api_key():
            messagebox.showerror(
                "缺少 API Key",
                "未找到 AI API key。\n请到「设置 → AI」填写 API Key，"
                "或设置环境变量 DEEPSEEK_API_KEY。",
            )
            return
        name, _ = CATEGORIES[self.current_key]

        dlg = tk.Toplevel(self)
        dlg.title("AI 快速填入")
        dlg.geometry("540x280")
        dlg.configure(bg=BG2)
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text=f"当前分类: {name}", bg=BG2, fg=ACCENT,
                 font=("Microsoft YaHei", 12, "bold")).pack(anchor="w", padx=18, pady=(16, 4))
        tk.Label(dlg, text='例如: "100个 0805 10K ±1% 贴片电阻 富信"',
                 bg=BG2, fg=MUTED, font=("Microsoft YaHei", 9)).pack(anchor="w", padx=18)

        txt = tk.Text(dlg, height=5, bg="#f8fafc", fg=FG, insertbackground=FG,
                      relief="solid", bd=1, font=("Microsoft YaHei", 10))
        txt.pack(fill="both", expand=True, padx=18, pady=10)

        status = tk.Label(dlg, text="", bg=BG2, fg="#d97706")
        status.pack(anchor="w", padx=18)

        def submit():
            desc = txt.get("1.0", "end").strip()
            if not desc:
                return
            status.config(text="AI 解析中…")
            dlg.update()

            def worker():
                try:
                    fields = fields_for(self.current_key)
                    parsed = AIFiller().parse(name, desc, fields)
                    row = [parsed.get(k, "") for k, _ in fields]
                    self.rows.append(row)
                    self._reload_tree()
                    self.update_status()
                    filled = len([v for v in row if v])
                    status.config(text=f"✅ 已填入 {filled} 个字段，检查后点顶部「保存」")
                except Exception as e:
                    status.config(text=f"❌ 失败: {e}")

            threading.Thread(target=worker, daemon=True).start()

        tk.Button(dlg, text="解析并填入", bg=ACCENT, fg="white", relief="flat",
                  font=("Microsoft YaHei", 10, "bold"), padx=20, pady=5,
                  command=submit).pack(pady=(0, 14))

    # ── 退出 ────────────────────────────────────────────
    def _on_close(self):
        self.destroy()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
