# -*- coding: utf-8 -*-
"""生成示例数据 (子分类文件模型)。

用法: python seed.py
为几个子分类填充示例元器件, 其余子分类不建文件。
再调用 make_catalog.py 生成分类总表。

注意: 会清空 data/ 目录, 正式使用后请勿运行。
"""

import os
import shutil
from warehouse.config import CATEGORIES, fields_for
from warehouse.excel_store import ExcelStore

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# 示例数据: 子分类名 -> 行列表
# (字段顺序: 名称/型号,品牌,封装,数量,库位,子分类,规格参数,数据手册,备注)
SAMPLES = {
    "贴片电容(MLCC)": [
        ["GRM188R71H104KA93D", "村田", "0603", "100", "A1-01", "贴片电容(MLCC)", "100nF 50V ±10% X7R", "", "电源滤波"],
        ["CL21B106KOQNNNE", "三星", "0805", "50", "A1-02", "贴片电容(MLCC)", "10uF 16V ±10% X5R", "", "主滤波"],
    ],
    "直插铝电解电容": [
        ["470uF/25V", "红宝石", "8x12 插件", "30", "A1-03", "直插铝电解电容", "470uF 25V ±20% 105℃", "", "电源输出"],
    ],
    "贴片电阻": [
        ["RC0805FR-0710KL", "YAGEO", "0805", "100", "B2-01", "贴片电阻", "10K ±1% 1/8W ±100ppm", "", "常用分压"],
        ["0603 4.7K", "国巨", "0603", "200", "B2-02", "贴片电阻", "4.7K ±5% 1/10W", "", "上拉"],
    ],
    "插件电阻": [
        ["MFR-25FRF52-100R", "YAGEO", "轴向插件", "50", "B2-03", "插件电阻", "100Ω ±1% 1/4W", "", "限流"],
    ],
    "单片机(MCU / MPU / SOC)": [
        ["STM32H723VGT6", "ST", "LQFP100", "5", "D4-01", "单片机(MCU / MPU / SOC)", "Cortex-M7 550MHz 1MB Flash 564KB RAM", "", "主控"],
        ["ESP32-S3-WROOM-1", "乐鑫", "模组", "8", "D4-02", "单片机(MCU / MPU / SOC)", "双核 240MHz WiFi+BLE 8MB Flash", "", "无线主控"],
    ],
    "肖特基二极管": [
        ["SS34", "MDD", "SMA", "50", "E5-01", "肖特基二极管", "40V 3A Vf=0.5V", "", "反接保护"],
    ],
    "通用二极管": [
        ["1N4148", "ON", "DO-35", "100", "E5-02", "通用二极管", "100V 0.3A 快速开关", "", "信号开关"],
    ],
    "稳压二极管": [
        ["BZT52C5V1", "", "SOD-123", "80", "E5-03", "稳压二极管", "5.1V 500mW", "", "稳压"],
    ],
    "线对板针座": [
        ["XH2.54 2P 卧式", "", "XH 插件", "50", "G7-01", "线对板针座", "2.54mm 2P 额定3A", "", "电池接口"],
        ["PH2.0 4P", "", "PH 插件", "30", "G7-02", "线对板针座", "2.0mm 4P 额定2A", "", "电机接口"],
    ],
    "USB连接器": [
        ["USB-C 16P 母座", "TYPE-C", "SMD 16P", "20", "G7-03", "USB连接器", "USB-C 16Pin 支持PD", "", "充电口"],
    ],
    "无源晶振": [
        ["8MHz", "Epson", "3215", "30", "H8-01", "无源晶振", "8MHz 12pF ±20ppm", "", "主时钟"],
        ["32.768kHz", "Epson", "2012", "50", "H8-02", "无源晶振", "32.768kHz 12.5pF ±20ppm", "", "RTC"],
    ],
    "焊台": [
        ["恒温焊台 T12", "快克", "", "1", "T-01", "焊台", "T12 手柄 200-450℃", "", "焊接"],
    ],
}


def main():
    # 清空数据目录
    if os.path.isdir(DATA_DIR):
        shutil.rmtree(DATA_DIR)
    store = ExcelStore(DATA_DIR)
    headers = [label for _, label in fields_for("resistor")]

    saved = set()
    for subcat, rows in SAMPLES.items():
        path = store.save(subcat, headers, rows)
        saved.add(os.path.basename(path))
        print(f"  ✓ {subcat} ({len(rows)} 条) -> {os.path.relpath(path, BASE_DIR)}")

    print(f"\n完成: {len(saved)} 个子分类文件, 其余子分类不建文件。")
    print("数据目录:", DATA_DIR)


if __name__ == "__main__":
    main()
