# -*- mode: python ; coding: utf-8 -*-
"""元器件仓库 — 单文件发布版 spec (--onefile).

产出: share_dist/parts-warehouse.exe   (一个文件, 不含任何用户数据)
- 首次运行在 exe 旁边自动生成干净 data/ (种子 = 项目 data/, 空仓库无 key)
- 全部依赖打进 exe: Python 运行时 / Flask / pywebview / onnxruntime / OCR 模型
- VC 运行库: 剔除 PyInstaller 收集的旧版, 换 System32 新版 (onnxruntime 1.28 需要,
  否则 onnxruntime.dll 加载报 WinError 1114)

用法: pyinstaller parts_warehouse_onefile.spec --noconfirm --distpath share_dist --workpath build_onefile
"""

import os

block_cipher = None
project_dir = os.getcwd()

# ── pywebview 打包支持 (WebView2Loader.dll) ─────────────────
import webview as _webview
_WV_DIR = os.path.dirname(_webview.__file__)


def _collect_webview_binaries():
    runtimes = os.path.join(_WV_DIR, "lib", "runtimes")
    bins = []
    if os.path.isdir(runtimes):
        for root, _, files in os.walk(runtimes):
            for f in files:
                if f == "WebView2Loader.dll":
                    src = os.path.join(root, f)
                    dest = os.path.relpath(root, runtimes)
                    bins.append((src, dest))
    if not bins:
        for f in os.listdir(_WV_DIR):
            if f.lower() == "webview2loader.dll":
                bins.append((os.path.join(_WV_DIR, f), "."))
    return bins


webview_binaries = _collect_webview_binaries()
print(f"[spec] webview binaries: {webview_binaries}")

# ── RapidOCR 模型 + 配置 ───────────────────────────────────
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
        # 种子数据 = 项目 data/ (空仓库无 key, 首次运行复制到 exe 旁)
        (os.path.join(project_dir, "data"), "data"),
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
        "openpyxl",
        "openpyxl.cell._writer",
        "openpyxl.styles",
        "httpx",
        "httpcore",
        "flask",
        "rapidocr",
        "rapidocr.main",
        "rapidocr.cli",
        "rapidocr.inference_engine.onnxruntime_engine",
        "onnxruntime",
        "webview",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "clr",
        "clr_loader",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "tksheet", "PyQt5", "PyQt6", "PyQt6.QtCore", "PySide6", "PySide2"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ── VC 运行库替换: 剔除旧版 → 塞入 System32 新版 ────────────
# PyInstaller 从 Python 安装目录收集的 msvcp140/vcruntime140 可能旧于
# onnxruntime 1.28 所需, 导致 DLL 初始化失败 (WinError 1114)。
# 单文件无法事后覆盖, 必须在 spec 层换源。
_VC_NAMES = {
    "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
    "msvcp140_atomic_wait.dll", "msvcp140_codecvt_ids.dll",
    "vcruntime140.dll", "vcruntime140_1.dll",
}
a.binaries = [b for b in a.binaries if os.path.basename(b[0]).lower() not in _VC_NAMES]
_sys32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
_vc_added = []
for _vc in ("msvcp140.dll", "msvcp140_1.dll", "vcruntime140.dll", "vcruntime140_1.dll",
            "msvcp140_atomic_wait.dll", "msvcp140_codecvt_ids.dll"):
    _p = os.path.join(_sys32, _vc)
    if os.path.exists(_p):
        # TOC 元组必须为 3 元: (dest_name, src_name, "BINARY")
        a.binaries.append((_vc, _p, "BINARY"))
        _vc_added.append(_vc)
print(f"[spec] VC runtime: 旧版已剔除, System32 版已加入: {_vc_added}")

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# onefile: exe 直接包含 binaries+datas, 无 COLLECT
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="parts-warehouse",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=os.path.join(project_dir, "app.ico"),
)
