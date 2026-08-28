#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""元器件仓库 — 一键拍照/图片入库 (CLI)。

用法:
  rk                     # 打开摄像头拍照入库 (空格=拍照, 回车=结束, Backspace=撤回, ESC=取消)
  rk a.jpg b.jpg ...     # 指定图片文件入库
  rk -d 目录             # 处理目录下所有图片
  rk -y                  # 跳过逐条确认直接入库
  rk --app-dir PATH      # 指定数据目录 (默认: 本脚本同目录 data/; 打包版用 exe 旁 data)
  rk --device N          # 摄像头编号 (默认 1, 0=内置)

流程: 拍照/图片 → OCR 识别 → AI 按料袋模板整理 → 解析分类 → 确认 → 入库
(入库复用主程序全部质量红线: 位号防护 / NC剔除 / 电容规范化 / 四键合并 / 未分类区 / 撤回记录)
"""
import argparse
import logging
import os
import sys
import time

logging.getLogger("rapidocr").setLevel(logging.ERROR)   # 抑制 RapidOCR INFO 噪音

# 允许直接以脚本方式运行 (python rk.py)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


# ── 数据目录 ────────────────────────────────────────────
def find_data_dir(app_dir: str) -> str:
    """数据目录: --app-dir 指定 > 脚本同目录 data/ > dist/parts-warehouse/data (exe 旁真实数据)。"""
    if app_dir:
        if os.path.isdir(app_dir):
            return app_dir
        print(f"! 指定的数据目录不存在: {app_dir}")
    base = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(base, "data"),
                 os.path.join(base, "dist", "parts-warehouse", "data")):
        if os.path.isdir(cand):
            return cand
    os.makedirs(os.path.join(base, "data"), exist_ok=True)
    return os.path.join(base, "data")


# ── AI 配置 (与 app.py get_ai_cfg 同逻辑) ──
def get_ai_cfg(app_dir: str) -> dict | None:
    from warehouse.settings import load_settings
    from warehouse.ai_fill import get_api_key
    ai = load_settings(app_dir)["ai"]
    provider = ai.get("provider", "online")
    if provider == "ollama":
        return {
            "provider": "ollama",
            "base_url": (ai.get("base_url") or "http://localhost:11434/v1").strip(),
            "api_key": "ollama",
            "model": ai.get("model") or "qwen2.5:7b",
        }
    # 用户配置 > 环境变量 DEEPSEEK_API_KEY > 项目根 .env (兼容旧环境)
    key = ai.get("api_key") or get_api_key()
    if not key:
        return None
    cfg = dict(ai)
    cfg["api_key"] = key
    return cfg


# ── 摄像头拍照 (空格=拍照 回车=结束 BS=撤回 ESC=取消) ──
def camera_capture(data_dir: str, device: int = 1, max_photos: int = 30,
                   timeout_s: int = 180) -> list:
    """返回 [(path, bytes)], 照片存 data/cache/ 由调用方识别后删除。"""
    import cv2
    cap = None
    for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF):
        cap = cv2.VideoCapture(device, backend)
        if cap.isOpened():
            break
        cap.release()
        cap = None
    if cap is None:
        return []
    # 外置 USB 摄像头: 切 MJPG + 720p 降带宽, 避免 read 失败/黑屏
    try:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    except Exception:
        pass
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cache_dir = os.path.join(data_dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    photos = []
    start = time.time()
    no_frame = 0
    try:
        while time.time() - start < timeout_s:
            ret, frame = cap.read()
            if not ret:
                # 丢帧重试, 连续约 2s 无帧才放弃
                no_frame += 1
                if no_frame >= 60:
                    break
                time.sleep(0.03)
                continue
            no_frame = 0
            frame = cv2.resize(frame, (960, 540))
            hint = f"Cam{device}  SPACE=CAPTURE({len(photos)})  BS=UNDO  ENTER=DONE  ESC=EXIT"
            cv2.putText(frame, hint, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
            cv2.imshow("PartsWarehouse-Camera (SPACE=CAP BS=UNDO ENTER=DONE)", frame)
            k = cv2.waitKey(30) & 0xFF
            if k in (13, 10):
                break
            elif k == 32:
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                if ok:
                    fname = f"cam_{int(time.time()*1000)}_{len(photos)}.jpg"
                    path = os.path.join(cache_dir, fname)
                    with open(path, "wb") as f:
                        f.write(buf.tobytes())
                    photos.append((path, buf.tobytes()))
                    print(f"  已拍照 {len(photos)}/{max_photos} 张 (Backspace 撤回)")
                if len(photos) >= max_photos:
                    break
            elif k == 8:
                if photos:
                    path, _ = photos.pop()
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    print(f"  撤回一张, 剩 {len(photos)} 张")
            elif k == 27:
                photos.clear()
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
    return photos


# ── 图片读取 ────────────────────────────────────────────
def collect_images(paths: list, directory: str) -> list:
    """收集图片文件路径。返回 [] 表示没有可用图片。"""
    files = []
    for p in paths:
        if os.path.isdir(p):
            files.extend(os.path.join(p, f) for f in sorted(os.listdir(p))
                         if f.lower().endswith(IMG_EXTS))
        elif os.path.isfile(p) and p.lower().endswith(IMG_EXTS):
            files.append(p)
        else:
            print(f"! 忽略非图片: {p}")
    if directory:
        files.extend(os.path.join(directory, f) for f in sorted(os.listdir(directory))
                     if f.lower().endswith(IMG_EXTS))
    return files


# ── 主流程 ──────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        prog="rk", description="元器件仓库 — 一键拍照/图片识别入库")
    ap.add_argument("images", nargs="*", help="图片文件 (缺省=摄像头拍照)")
    ap.add_argument("-d", "--dir", help="图片目录 (处理其中全部图片)")
    ap.add_argument("-y", "--yes", action="store_true", help="跳过确认直接入库")
    ap.add_argument("--no-ai", action="store_true",
                    help="纯规则解析 (无需 AI/网络/key): 正则+关键词表识别, 适合固定格式料袋")
    ap.add_argument("--app-dir", help="数据目录 (默认自动探测)")
    ap.add_argument("--device", type=int, default=1, help="摄像头编号 (默认 1)")
    args = ap.parse_args()

    # 1. 数据目录 & AI 配置 (--no-ai 不需要 AI)
    data_dir = find_data_dir(args.app_dir)
    project_dir = args.app_dir or os.path.dirname(os.path.abspath(__file__))
    cfg = None if args.no_ai else get_ai_cfg(project_dir)
    if not args.no_ai and not cfg:
        print("✗ 未配置 AI。请先在软件「设置 → AI」填写 API Key，")
        print("  或选「本地离线 (Ollama)」模式；也可用 rk --no-ai 纯规则解析(无需AI)。")
        sys.exit(1)
    print(f"数据目录 : {data_dir}")
    if cfg:
        print(f"AI 服务   : {'本地离线 Ollama ' + cfg['model'] if cfg.get('provider') == 'ollama' else cfg['base_url']} / {cfg['model']}")
    else:
        print("解析模式 : 纯规则 (--no-ai, 无 AI 参与)")

    # 2. 采集图片 (拍照 or 文件)
    photos = []          # [(path, bytes)]
    if not args.images and not args.dir:
        print("打开摄像头… 空格=拍照 回车=结束 Backspace=撤回 ESC=取消")
        photos = camera_capture(data_dir, device=args.device)
        if not photos:
            print(f"✗ 摄像头 {args.device} 不可用或未拍到照片")
            sys.exit(1)
        print(f"共拍 {len(photos)} 张")
    else:
        files = collect_images(args.images, args.dir)
        if not files:
            print("✗ 没有找到可用图片 (png/jpg/jpeg/webp/bmp)")
            sys.exit(1)
        photos = [(f, open(f, "rb").read()) for f in files]
        print(f"共 {len(files)} 张图片")

    # 3. OCR + 模板整理
    from warehouse.ocr import recognize, format_text
    groups = []
    for i, (path, buf) in enumerate(photos, 1):
        try:
            lines = recognize(buf)
            print(f"  [{i}/{len(photos)}] OCR {os.path.basename(path)}: {len(lines)} 行")
        except Exception as e:
            lines = []
            print(f"  [{i}/{len(photos)}] OCR 失败: {e}")
        groups.append(lines)
        # 照片用完即删 (缓存不残留)
        if path.startswith(os.path.join(data_dir, "cache")):
            try:
                os.remove(path)
            except OSError:
                pass

    raw_text = "\n".join(
        (f"【图{i + 1}】\n" + "\n".join(g)) if g else f"【图{i + 1}】(无文字)"
        for i, g in enumerate(groups))

    # 4. 解析 (AI 或纯规则)
    if args.no_ai:
        from warehouse.rules import RuleParser
        print("纯规则解析中…")
        parser = RuleParser()
        items = parser.parse_text(raw_text)
        dropped_nc = parser.dropped_nc
    else:
        print("按料袋模板整理中…")
        try:
            text = format_text(raw_text, cfg)
        except Exception as e:
            print(f"✗ 模板整理失败: {e}")
            sys.exit(1)
        if not text.strip():
            print("✗ 未识别到有效文字")
            sys.exit(1)
        from warehouse.batch_import import BatchParser
        parser = BatchParser(cfg["api_key"], cfg["base_url"], cfg["model"])
        print("AI 解析分类中…")
        try:
            items = parser.parse_text(text)
        except Exception as e:
            print(f"✗ 解析失败: {e}")
            sys.exit(1)
        dropped_nc = parser.dropped_nc
    if not items:
        print("✗ 没有解析出元件")
        sys.exit(1)

    # 5. 展示 & 确认
    print(f"\n解析出 {len(items)} 条" + (f" (已剔除 NC/不贴装 {dropped_nc} 条)" if dropped_nc else ""))
    print("-" * 72)
    print(f"{'名称':<24}{'品牌':<12}{'封装':<14}{'数量':<6}{'分类'}")
    n_uncat = 0
    for it in items:
        cat = it.get("cat_key") or "未分类"
        sub = it.get("subcat") or ""
        label = f"{cat}/{sub}" if sub else cat
        if not it.get("cat_key"):
            n_uncat += 1
        print(f"{str(it.get('name',''))[:24]:<24}{str(it.get('brand',''))[:12]:<12}"
              f"{str(it.get('package',''))[:14]:<14}{str(it.get('qty','')):<6}{label}")
    if n_uncat:
        print(f"\n⚠ {n_uncat} 条未识别分类, 将进入「未分类」区, 可在软件里手动归类")
    print("-" * 72)

    if not args.yes:
        try:
            ans = input(f"确认入库以上 {len(items)} 条? [y/N] ").strip().lower()
        except EOFError:
            ans = "n"
        if ans not in ("y", "yes"):
            print("已取消")
            sys.exit(0)

    # 6. 入库
    result = parser.commit(items, data_dir)
    total = sum(result.values())
    print(f"\n✅ 入库完成: {total} 条")
    for subcat, n in result.items():
        print(f"   {subcat}: {n} 条")


if __name__ == "__main__":
    main()
