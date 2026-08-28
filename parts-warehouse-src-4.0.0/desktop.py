# -*- coding: utf-8 -*-
"""元器件仓库 — 桌面版入口 (pywebview 原生窗口).

双击 exe 或运行本文件: 原生窗口内嵌 Web UI, 无浏览器地址栏。
Flask 服务在本机后台线程运行, 窗口关闭即整体退出。

打包:  pyinstaller parts_warehouse.spec
"""

import os
import shutil
import sys
import threading

# ── 路径解析 ──────────────────────────────────────────
# 打包后: 代码在解包临时目录 (_MEIPASS), 用户数据在 exe 旁边
FROZEN = getattr(sys, "frozen", False)
if FROZEN:
    CODE_DIR = sys._MEIPASS                      # 只读代码+默认资源
    APP_DIR = os.path.dirname(sys.executable)    # exe 所在目录 (可写)
else:
    CODE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = CODE_DIR

DATA_DIR = os.path.join(APP_DIR, "data")

# 让 warehouse 包可导入
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)

# 打包版路径桥接:
#   PARTS_APP_DIR = exe 旁目录 (数据/设置存这里, 可写)
#   PARTS_RES_DIR = _MEIPASS  (模板/静态资源/内置示例数据)
if FROZEN:
    os.environ["PARTS_APP_DIR"] = APP_DIR
    os.environ["PARTS_RES_DIR"] = CODE_DIR

import webview
from app import app as flask_app


class Api:
    """pywebview JS 桥接 API (前端通过 window.pywebview.api.* 调用)。

    供设置页「数据路径 → 浏览」弹出原生文件夹选择对话框。
    """

    def choose_dir(self) -> str:
        """弹出目录选择框, 返回选中的绝对路径; 取消返回空字符串。"""
        if webview.windows:
            result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
            if result and len(result) > 0:
                return str(result[0])
        return ""


def ensure_data_dir():
    """首次运行: 从打包资源把示例数据复制到 exe 旁 (若已存在则跳过)。

    注意: 这是"默认数据目录"初始化。若用户在设置里改了数据路径,
    settings.json 中的 data_dir 生效, 实际读写走自定义目录。
    """
    if not FROZEN:
        os.makedirs(DATA_DIR, exist_ok=True)
        return
    bundled = os.path.join(CODE_DIR, "data")
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.isdir(bundled) and not os.listdir(DATA_DIR):
        # 注意: data/ 内含 backgrounds/ 等子目录, 必须递归复制,
        # 逐文件 copy2 碰到目录会抛 PermissionError (退出码 1)
        shutil.copytree(bundled, DATA_DIR, dirs_exist_ok=True)


def start_flask():
    """Flask 后台线程 (不自动开浏览器). 异常写入 exe 旁 flask_error.log (窗口程序无 stderr)."""
    try:
        flask_app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False,
                      threaded=True)  # 摄像头拍照/探测阻塞端点不能卡死整个服务
    except Exception:
        import traceback
        log_path = os.path.join(APP_DIR, "flask_error.log")
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        raise


def main():
    ensure_data_dir()
    threading.Thread(target=start_flask, daemon=True).start()

    webview.create_window(
        "TuangParts",
        "http://127.0.0.1:5000",
        width=1200,
        height=780,
        min_size=(960, 640),
        # Match the default dark workspace so WebView2 never exposes a white
        # native surface during first paint or a renderer redraw.
        background_color="#101214",
        js_api=Api(),
    )
    # gui=edgechromium: 强制 WebView2 (Qt 已被打包排除, 必须显式指定)
    webview.start(gui="edgechromium")


if __name__ == "__main__":
    main()
