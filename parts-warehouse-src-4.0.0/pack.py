# -*- coding: utf-8 -*-
"""元器件仓库 — 一键打包脚本 (数据安全版).

流程:
  1. 自动备份 exe 旁 data → backups/parts-warehouse_data_<时间戳>/
  2. 关闭占用 5000 端口的旧实例 (exe / 开发服务器)
  3. PyInstaller 打包到临时目录 (不动正式 dist)
  4. 只把新程序文件覆盖到 dist/parts-warehouse/, data 目录原样保留

用法:  python pack.py
"""
import datetime
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "parts-warehouse"
DIST = os.path.join(ROOT, "dist", APP_NAME)
DATA = os.path.join(DIST, "data")
BACKUP_ROOT = os.path.join(ROOT, "backups")
TMP_DIST = os.path.join(ROOT, "build_tmp_dist")
SPEC = os.path.join(ROOT, "parts_warehouse.spec")


def step(msg: str):
    print(f"\n=== {msg} ===")


def kill_port_5000():
    """杀掉占用 5000 端口的进程 (exe 的 Flask / 开发服务器)。"""
    step("关闭旧实例 (占用 5000 端口)")
    try:
        out = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, encoding="gbk", errors="ignore"
        ).stdout
        pids = set()
        for line in out.splitlines():
            if ":5000" in line and "LISTENING" in line.upper():
                parts = line.split()
                if parts:
                    pids.add(parts[-1])
        for pid in pids:
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
            print(f"  已结束 PID {pid}")
        if not pids:
            print("  没有占用 5000 的进程")
    except Exception as e:
        print(f"  警告: 无法自动关闭旧实例 ({e}), 请手动关闭 exe 后重试")
        sys.exit(1)


def backup_data() -> str | None:
    """备份 exe 旁 data, 返回备份目录路径。"""
    step("备份当前数据")
    if not os.path.isdir(DATA) or not os.listdir(DATA):
        print("  exe 旁 data 为空或不存在, 跳过备份")
        return None
    os.makedirs(BACKUP_ROOT, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bk = os.path.join(BACKUP_ROOT, f"{APP_NAME}_data_{ts}")
    shutil.copytree(DATA, bk)
    print(f"  已备份 {len(os.listdir(DATA))} 项 → {bk}")
    return bk


def build():
    step("打包到临时目录 (不动正式 dist)")
    if os.path.exists(TMP_DIST):
        shutil.rmtree(TMP_DIST)
    cmd = [
        sys.executable, "-m", "PyInstaller", SPEC,
        "--noconfirm", "--distpath", TMP_DIST,
        "--workpath", os.path.join(ROOT, "build"),
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)
    print(f"  打包完成 → {TMP_DIST}")


def deploy():
    """把新程序文件覆盖到正式 dist, data 目录保留 (data 全程不动)。"""
    step("更新正式 dist (保留 data)")
    src = os.path.join(TMP_DIST, APP_NAME)
    if not os.path.isdir(src):
        print("  错误: 临时打包产物不存在")
        sys.exit(1)
    os.makedirs(DIST, exist_ok=True)

    # 清旧程序文件 (跳过 data, data 全程不移动不清除)
    for name in os.listdir(DIST):
        p = os.path.join(DIST, name)
        if name == "data":
            continue
        if os.path.isdir(p):
            shutil.rmtree(p)
        else:
            os.remove(p)
    # 复制新程序文件 (临时产物理论上无 data, 有则跳过)
    for name in os.listdir(src):
        if name == "data":
            continue
        s = os.path.join(src, name)
        d = os.path.join(DIST, name)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
    n = len(os.listdir(DATA)) if os.path.isdir(DATA) else 0
    print(f"  已更新程序文件, data 保留 ({n} 项)")


def refresh_vc_runtime():
    """onnxruntime 兼容: PyInstaller 收集的 VC 运行库可能是旧版,
    新版 onnxruntime.dll DllMain 会失败 (WinError 1114)。
    打包后用 System32 的新版覆盖 _internal 里的旧版。"""
    step("刷新 VC 运行库 (onnxruntime 兼容)")
    internal = os.path.join(DIST, "_internal")
    if not os.path.isdir(internal):
        print("  _internal 不存在, 跳过")
        return
    sys32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    replaced = []
    for name in ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
        s = os.path.join(sys32, name)
        d = os.path.join(internal, name)
        if os.path.exists(s) and os.path.exists(d) and os.path.getsize(s) != os.path.getsize(d):
            shutil.copy2(s, d)
            replaced.append(name)
    print(f"  已刷新: {replaced if replaced else '无 (已是最新)'}")


def cleanup():
    step("清理临时目录")
    if os.path.exists(TMP_DIST):
        shutil.rmtree(TMP_DIST)
    print("  完成")


if __name__ == "__main__":
    print(f"元器件仓库 打包脚本 — {APP_NAME}")
    backup_data()
    kill_port_5000()
    build()
    deploy()
    refresh_vc_runtime()
    cleanup()
    print("\n✅ 打包完成! 数据已保留, 可直接启动 dist/parts-warehouse/parts-warehouse.exe")
