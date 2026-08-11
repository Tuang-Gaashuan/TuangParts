# -*- coding: utf-8 -*-
"""元器件仓库 — 图片文字识别 (OCR)。

基于 RapidOCR (PP-OCRv6) 本地离线识别, 免费无联网。
识别图片中的元器件文字 (料袋标签 / 元器件照片 / BOM 截图),
输出文本行供 AI 解析录入。
"""

import os
import sys

from warehouse.settings import chat_completions_url

_ocr = None


def get_ocr():
    """RapidOCR 单例 (模型只加载一次)。"""
    global _ocr
    if _ocr is None:
        # PyInstaller frozen: onnxruntime 的 DLL 走默认搜索路径找不到
        # _MEIPASS/onnxruntime/capi, 必须先 add_dll_directory (否则 DLL 初始化失败)
        if getattr(sys, "frozen", False):
            for sub in ("onnxruntime", "onnxruntime/capi"):
                d = os.path.join(sys._MEIPASS, sub)
                if os.path.isdir(d):
                    try:
                        os.add_dll_directory(d)
                    except Exception:
                        pass
        from rapidocr import RapidOCR
        _ocr = RapidOCR()
    return _ocr


def recognize(image_bytes: bytes) -> list:
    """识别图片, 返回文本行列表。失败抛异常。"""
    out = get_ocr()(image_bytes)
    return list(out.txts or [])


# 料袋标签整理模板 prompt (用户定义)
FORMAT_PROMPT = """你是电子元器件料袋标签整理助手。把 OCR 识别出的料袋文字整理成规范的一行式清单。

模板: (数量) (型号) (品牌) (封装) (电气参数) (器件名称)
规则:
- 识别文字中用【图N】标记区分不同的图片。
- 每张图片(每个【图N】块)通常是一包元器件, 输出一行;
  只有当一张图里确实包含多种不同元件时才输出多行。
- 未提及的项目留空, 不要写"无"。
- 不要输出数字序号(如 1. 2. ① 或包装序号)。
- 不要物料编码/供应商料号(如 CL10A106KP8NNNC、0603WAF4992T5E 这类长料号不要出现在输出里)。
- 数量直接写数字(如 1000); 型号如 100nF、STM32F103C8T6; 品牌如 村田;
  封装如 0402、SOD-123; 电气参数如 50V X7R、±1%; 器件名称如 贴片电容。
- 只输出整理后的文本, 不要任何解释或标注。

识别到的文字:
{text}"""


def format_text(text: str, cfg: dict) -> str:
    """按料袋模板整理 OCR 文本 (调用 LLM)。cfg: {base_url, api_key, model}。"""
    import httpx
    url = chat_completions_url(cfg['base_url'])
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": FORMAT_PROMPT.format(text=text)}],
        "temperature": 0.1,
        "max_tokens": 2048,
    }
    resp = httpx.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()
