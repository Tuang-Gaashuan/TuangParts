# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置: 元器件仓库 桌面版.

用法:  pyinstaller parts_warehouse.spec --noconfirm
输出:  dist/parts-warehouse/parts-warehouse.exe
"""

import os

block_cipher = None

# spec 由 PyInstaller 在项目目录下 exec, __file__ 不可用, 用 cwd
project_dir = os.getcwd()

# ── pywebview 打包支持 ──────────────────────────────
# 缺这些会导致 exe 启动崩溃 (WebView2Loader.dll / edgechromium 平台模块)
import webview as _webview
_WV_DIR = os.path.dirname(_webview.__file__)

def _collect_webview_binaries():
    """收集 webview lib/runtimes 下的 WebView2Loader.dll (win-x64 优先)。"""
    runtimes = os.path.join(_WV_DIR, "lib", "runtimes")
    bins = []
    if os.path.isdir(runtimes):
        for root, _, files in os.walk(runtimes):
            for f in files:
                if f == "WebView2Loader.dll":
                    src = os.path.join(root, f)
                    dest = os.path.relpath(root, runtimes)  # win-x64/native/...
                    bins.append((src, dest))
    # 兜底: 若未找到, 从 webview 包根目录找
    if not bins:
        for f in os.listdir(_WV_DIR):
            if f.lower() == "webview2loader.dll":
                bins.append((os.path.join(_WV_DIR, f), "."))
    return bins

webview_binaries = _collect_webview_binaries()
print(f"[spec] webview binaries: {webview_binaries}")

# ── RapidOCR 打包支持 (模型 .onnx + 配置, 否则 exe 内 OCR 缺模型) ──
import rapidocr as _rapidocr
_RP_DIR = os.path.dirname(_rapidocr.__file__)
rapidocr_datas = [
    (os.path.join(_RP_DIR, "models"), "rapidocr/models"),
]
for _f in ("config.yaml", "default_models.yaml"):
    _src = os.path.join(_RP_DIR, _f)
    if os.path.exists(_src):
        rapidocr_datas.append((_src, "rapidocr"))
print(f"[spec] rapidocr datas: {rapidocr_datas}")

a = Analysis(
    ["desktop.py"],
    pathex=[project_dir],
    binaries=webview_binaries,
    datas=[
        (os.path.join(project_dir, "templates"), "templates"),
        (os.path.join(project_dir, "static"), "static"),
        (os.path.join(project_dir, "warehouse"), "warehouse"),
        # 预置示例数据 (分享版种子: 空仓库/无个人数据)
        (os.path.join(project_dir, "data"), "data"),
        (os.path.join(project_dir, "LICENSE"), "."),
        # pywebview 运行库: 保持包内相对路径 (webview/lib/...),
        # 否则 frozen 模式下 interop_dll_path() 找不到
        # Microsoft.Web.WebView2.*.dll / WebView2Loader.dll → 启动即崩 (退出码 1)
        (os.path.join(_WV_DIR, "lib"), "webview/lib"),
    ] + rapidocr_datas,
    hiddenimports=[
        "warehouse.config",
        "warehouse.excel_store",
        "warehouse.ai_fill",
        "warehouse.settings",
        "warehouse.batch_import",
        "warehouse.activity",
        "warehouse.rules",
        "warehouse.packfile",
        "warehouse.undo",
        "warehouse.unclassified",
        "warehouse.ocr",
        "warehouse.withdraw_match",
        "warehouse.brands",
        "warehouse.ledger",
        "warehouse.git_sync",
        "openpyxl",
        "openpyxl.cell._writer",
        "openpyxl.styles",
        "httpx",
        "httpcore",
        "flask",
        # RapidOCR / onnxruntime
        "rapidocr",
        "rapidocr.main",
        "rapidocr.cli",
        "rapidocr.inference_engine.onnxruntime_engine",
        "onnxruntime",
        # pywebview 平台模块
        "webview",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "clr",
        "clr_loader",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "tksheet", "PyQt5", "PyQt6", "PyQt6.QtCore", "PySide6", "PySide2", "PyQt5.QtCore", "PyQt5.QtWidgets", "PyQt5.QtNetwork", "PyQt5.QtWebEngineWidgets"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="parts-warehouse",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 无控制台窗口
    disable_windowed_traceback=False,
    icon=os.path.join(project_dir, "app.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="parts-warehouse",
)
