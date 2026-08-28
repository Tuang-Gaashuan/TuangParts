# -*- coding: utf-8 -*-
"""只读测试 TEST 目录前 12 张图片的 OCR 与 AI 结构化性能。"""
import json
import time
from contextlib import ExitStack
from pathlib import Path

import requests

ROOT = Path(r"F:\Study\TEST")
BASE_URL = "http://127.0.0.1:5000"
OUTPUT = ROOT / "ocr_ai_test_12_report.json"

images = sorted(ROOT.glob("*.jpg"))[:12]
if len(images) != 12:
    raise SystemExit(f"需要至少 12 张 JPG，实际仅找到 {len(images)} 张")

started = time.perf_counter()
with ExitStack() as stack:
    files = [
        ("files", (image.name, stack.enter_context(image.open("rb")), "image/jpeg"))
        for image in images
    ]
    ocr_started = time.perf_counter()
    ocr_response = requests.post(
        f"{BASE_URL}/api/ocr/batch", files=files, data={"workers": "4"}, timeout=300
    )
    ocr_elapsed = time.perf_counter() - ocr_started
ocr_response.raise_for_status()
ocr = ocr_response.json()
if not ocr.get("ok"):
    raise RuntimeError(ocr.get("error", "OCR failed"))

groups = ocr.get("groups", [])
raw_text = "\n".join(
    f"【图{index}】\n{' '.join(lines)}" if lines else f"【图{index}】(无文字)"
    for index, lines in enumerate(groups, 1)
)

parse_started = time.perf_counter()
parse_response = requests.post(
    f"{BASE_URL}/api/ocr/parse_text", json={"text": raw_text}, timeout=300
)
parse_elapsed = time.perf_counter() - parse_started
parse_response.raise_for_status()
parsed = parse_response.json()
if not parsed.get("ok"):
    raise RuntimeError(parsed.get("error", "AI parse failed"))

items = parsed.get("items", [])
covered = sorted({item.get("source_image") for item in items if item.get("source_image")})
report = {
    "image_count": len(images),
    "files": [image.name for image in images],
    "ocr_seconds": round(ocr_elapsed, 3),
    "ocr_workers": ocr.get("workers"),
    "ocr_line_count": sum(len(group) for group in groups),
    "ai_seconds": round(parse_elapsed, 3),
    "total_seconds": round(time.perf_counter() - started, 3),
    "ai_usage": parsed.get("usage", {}),
    "item_count": len(items),
    "covered_images": covered,
    "missing_images": [f"图{index}" for index in range(1, len(images) + 1) if f"图{index}" not in covered],
    "items": items,
    "raw_ocr_groups": groups,
}
OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({key: report[key] for key in report if key not in {"items", "raw_ocr_groups"}}, ensure_ascii=False, indent=2))
