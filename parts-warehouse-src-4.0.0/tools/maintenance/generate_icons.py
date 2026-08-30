# -*- coding: utf-8 -*-
"""为 36 个一级分类生成扁平图标 (cogview-4), 存到 static/icons/<key>.png。

用法: python tools/maintenance/generate_icons.py [key]   # 不带参数生成全部
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error

from warehouse.config import CATEGORIES

KEY = "4b03215f4d164073bda2231f03e05dd7.37CPzMSQldwiy2wQ"
PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT_DIR = os.path.join(PROJECT_DIR, "static", "icons")
os.makedirs(OUT_DIR, exist_ok=True)

# 每个分类的图标描述 (英文, cogview 对英文理解更好)
ICON_HINTS = {
    "capacitor": "capacitor electronic component, cylinder with two legs",
    "resistor": "resistor electronic component, rectangle body with two bent legs",
    "inductor": "inductor coil component, coiled wire on a spool",
    "mcu": "microcontroller chip, square IC with many pins",
    "logic": "logic gate symbol, AND gate shape on chip",
    "diode": "diode component, arrow symbol with bar",
    "transistor": "transistor component, TO-92 package with three legs",
    "sic": "silicon carbide power device, hexagon crystal with circuit",
    "gan": "gallium nitride device, lightning bolt in hexagon",
    "protection": "safety shield with lightning bolt, circuit protection",
    "power_mgmt": "power management, lightning bolt in circle with wave",
    "comm_ic": "communication chip, signal waves between two chips",
    "clock": "clock timer chip, clock face on IC",
    "connector": "connector plug, pin header socket",
    "terminal": "wire terminal block, screw terminal",
    "switch": "push button switch, tactile switch button",
    "adc_dac": "analog digital converter, wave to steps conversion",
    "rf": "radio frequency, antenna with signal waves",
    "opto": "optoelectronics, light emitting diode with rays",
    "led_driver": "LED driver, LED bulb with control circuit",
    "optocoupler": "optocoupler, LED and phototransistor inside package",
    "display": "display screen, monitor with pixels",
    "emi": "electromagnetic filter, shielded inductor with waves",
    "oscillator": "crystal oscillator, crystal with two terminals",
    "memory": "memory chip, stack of storage layers",
    "sensor": "sensor device, gauge with sensing element",
    "isolator": "signal isolator, two circuits with barrier between",
    "relay": "relay, coil with switch contacts",
    "audio": "audio device, speaker with sound waves",
    "module": "function module, circuit board module block",
    "iot_module": "IoT module, cloud with antenna connections",
    "opamp": "operational amplifier, triangle op-amp symbol",
    "devkit": "development board, breadboard with jumper wires",
    "tool": "soldering iron tool, crossed screwdriver and pliers",
    "instrument": "multimeter instrument, measurement gauge",
    "consumable": "consumables, solder wire spool and flux",
}

STYLE = (
    "flat minimalist icon design, single centered object, "
    "soft light gradient background, rounded square tile, "
    "clean vector style, no text, no letters, professional, high quality"
)


def gen(prompt, out, size="1024x1024"):
    body = json.dumps({"model": "cogview-3-flash", "prompt": prompt, "size": size}).encode("utf-8")
    req = urllib.request.Request(
        "https://open.bigmodel.cn/api/paas/v4/images/generations",
        data=body,
        headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = json.loads(r.read().decode("utf-8"))
            url = data.get("data", [{}])[0].get("url", "")
            if not url:
                return False, "no url"
            with urllib.request.urlopen(url, timeout=240) as ir:
                img = ir.read()
            with open(out, "wb") as f:
                f.write(img)
            return True, len(img)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                # 限流: 等待更久再重试 (45s, 90s, 135s, 180s, 225s)
                wait = 45 * (attempt + 1)
                print(f"  429 限流, 等待 {wait}s 重试", flush=True)
                time.sleep(wait)
            elif attempt == 4:
                return False, str(e)[:120]
            else:
                time.sleep(10)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == 4:
                return False, str(e)[:120]
            print(f"  网络错误 {type(e).__name__}, 等待 {20*(attempt+1)}s 重试", flush=True)
            time.sleep(20 * (attempt + 1))
    return False, "unknown"


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    targets = [only] if only else list(CATEGORIES.keys())

    for key in targets:
        out = os.path.join(OUT_DIR, f"{key}.png")
        if os.path.exists(out) and os.path.getsize(out) > 1000:
            print(f"[SKIP] {key} 已存在", flush=True)
            continue
        name = CATEGORIES[key][0]
        hint = ICON_HINTS.get(key, "electronic component")
        prompt = f"{hint}, {STYLE}"
        ok, info = gen(prompt, out)
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {key} ({name}) {info}", flush=True)
        time.sleep(15)  # 每次请求间隔 15s, 降低限流概率

    print("DONE", flush=True)


if __name__ == "__main__":
    main()
