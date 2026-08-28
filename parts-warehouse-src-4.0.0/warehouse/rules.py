# -*- coding: utf-8 -*-
"""元器件仓库 — 纯规则解析器 (无 AI)。

从料袋模板行 / OCR 原始行提取字段:
  数量 型号 品牌 封装 电气参数 器件名称
适合格式固定的料袋标签 / BOM 行; 复杂歧义文本建议用 AI 解析 (batch_import)。

分类识别优先级: 值单位(电容/电阻/电感) > 器件名称关键词 > 型号特征前缀。
复用 batch_import 的后处理: 位号防护 / NC剔除 / 电容规范化。
"""
import re

from warehouse.config import CATEGORIES
from warehouse.batch_import import (
    _fix_part_ref_name, _normalize_capacitor, _drop_nc_items,
)

# ── 品牌表 (关键词 -> 标准名) ────────────────────────────
BRANDS = [
    ("村田", "村田(Murata)"), ("muRata", "村田(Murata)"), ("murata", "村田(Murata)"),
    ("三星", "三星(Samsung)"), ("samsung", "三星(Samsung)"),
    ("厚声", "厚声(UniOhm)"), ("uniohm", "厚声(UniOhm)"),
    ("国巨", "国巨(Yageo)"), ("yageo", "国巨(Yageo)"),
    ("风华", "风华(FH)"), ("FH", "风华(FH)"),
    ("TDK", "TDK"), ("AVX", "AVX"), ("KEMET", "KEMET"), ("基美", "基美(KEMET)"),
    ("松下", "松下(Panasonic)"), ("panasonic", "松下(Panasonic)"),
    ("威世", "威世(Vishay)"), ("vishay", "威世(Vishay)"),
    ("长电", "长电(JCET)"), ("长晶", "长晶(Changjing)"),
    ("ST", "意法半导体(ST)"), ("意法", "意法半导体(ST)"),
    ("TI", "德州仪器(TI)"), ("德州仪器", "德州仪器(TI)"),
    ("NXP", "恩智浦(NXP)"), ("恩智浦", "恩智浦(NXP)"),
    ("ADI", "亚德诺(ADI)"), ("亚德诺", "亚德诺(ADI)"),
    ("微芯", "微芯(Microchip)"), ("microchip", "微芯(Microchip)"),
    ("英飞凌", "英飞凌(Infineon)"), ("infineon", "英飞凌(Infineon)"),
    ("兆易", "兆易创新(GigaDevice)"), ("gigadevice", "兆易创新(GigaDevice)"),
    ("瑞萨", "瑞萨(Renesas)"), ("renesas", "瑞萨(Renesas)"),
    ("华润", "华润微(CRM)"), ("士兰微", "士兰微(Silan)"),
    ("乐山", "乐山无线电(LRC)"), ("LRC", "乐山无线电(LRC)"),
    ("先科", "先科(SEMTECH)"), ("SEMTECH", "先科(SEMTECH)"),
    ("永铭", "永铭(Yongming)"), ("江海", "江海(Jianghai)"),
    ("尼吉康", "尼吉康(Nichicon)"), ("nichicon", "尼吉康(Nichicon)"),
    ("红宝石", "红宝石(Rubycon)"), ("rubycon", "红宝石(Rubycon)"),
    ("艾华", "艾华(AiSHi)"), ("立隆", "立隆(Lelon)"),
    ("顺络", "顺络(Sunlord)"), ("sunlord", "顺络(Sunlord)"),
    ("三环", "三环(CCTC)"), ("宇阳", "宇阳(EYANG)"),
    ("微盟", "微盟(MicrOne)"), ("矽力杰", "矽力杰(Silergy)"),
    ("芯朋", "芯朋(Chipown)"), ("晶丰明源", "晶丰明源(Bright)"),
    ("圣邦", "圣邦微(SGMICRO)"), ("sgmicro", "圣邦微(SGMICRO)"),
    ("思瑞浦", "思瑞浦(3PEAK)"), ("3peak", "思瑞浦(3PEAK)"),
    ("纳芯微", "纳芯微(Novosense)"), ("novosense", "纳芯微(Novosense)"),
]

# ── 封装表 (正则 -> 标准封装名) ──────────────────────────
PACKAGES = [
    (r"C?0402", "0402"), (r"C?0603", "0603"), (r"C?0805", "0805"),
    (r"C?1206", "1206"), (r"C?1210", "1210"), (r"C?2512", "2512"),
    (r"C?0201", "0201"), (r"C?1005", "0402"), (r"C?1608", "0603"),
    (r"C?2012", "0805"), (r"C?3216", "1206"), (r"C?3225", "1210"),
    (r"SOT-?23[-\d]*", "SOT-23"), (r"SOT-?89", "SOT-89"),
    (r"SOT-?223", "SOT-223"), (r"SOT-?363", "SOT-363"),
    (r"SOD-?123", "SOD-123"), (r"SOD-?323", "SOD-323"), (r"SOD-?523", "SOD-523"),
    (r"SMA\(DO-214AC\)|DO-214AC|SMA", "SMA(DO-214AC)"),
    (r"SMB\(DO-214AA\)|DO-214AA|SMB", "SMB(DO-214AA)"),
    (r"SMC\(DO-214AB\)|DO-214AB|SMC", "SMC(DO-214AB)"),
    (r"LQFP-?\d+", None), (r"QFN-?\d+", None), (r"SOP-?\d+", None),
    (r"TSSOP-?\d+", None), (r"MSOP-?\d+", None), (r"DFN-?\d+", None),
    (r"TO-?92", "TO-92"), (r"TO-?220", "TO-220"), (r"TO-?252", "TO-252(DPAK)"),
    (r"TO-?263", "TO-263(D2PAK)"), (r"TO-?247", "TO-247"),
    (r"DIP-?\d+", None), (r"插件", "插件"), (r"贴片", "贴片"),
    (r"BGA-?\d+", None), (r"QFP-?\d+", None), (r"PLCC", None),
]

# ── 值类正则 (数字前不能是字母, 防 X7R 的 R / C0G 误判) ──
CAP_RE = re.compile(r"(?<![A-Za-z0-9])(\d+(?:\.\d+)?)\s*(p|n|u|µ|m|k)?\s?F(?![a-zA-Z])", re.I)
RES_RE = re.compile(r"(?<![A-Za-z0-9])(\d+(?:\.\d+)?)\s*([kKmM])?\s?(?:Ω|ohm|R)(?![a-zA-Z])", re.I)
IND_RE = re.compile(r"(?<![A-Za-z0-9])(\d+(?:\.\d+)?)\s*(n|u|µ|m)?\s?H(?![a-zA-Z])", re.I)

# ── 器件名称关键词 -> (cat_key, subcat) ─────────────────
NAME_KEYWORDS = [
    # 电容
    ("钽电容", "capacitor", "钽电容"), ("钽", "capacitor", "钽电容"),
    ("铝电解", "capacitor", "贴片型铝电解电容"),
    ("电解电容", "capacitor", "贴片型铝电解电容"),
    ("独石", "capacitor", "直插独石电容(MLCC)"),
    ("安规电容", "capacitor", "安规电容"), ("CBB", "capacitor", "CBB电容"),
    ("薄膜电容", "capacitor", "薄膜电容"), ("瓷片", "capacitor", "瓷片电容"),
    ("超级电容", "capacitor", "超级电容 / 法拉电容"),
    ("电容", "capacitor", "贴片电容(MLCC)"),
    # 电阻
    ("采样电阻", "resistor", "电流采样电阻 / 分流器"), ("分流器", "resistor", "电流采样电阻 / 分流器"),
    ("排阻", "resistor", "排阻"),
    ("电位器", "resistor", "可调电阻 / 电位器"), ("可调电阻", "resistor", "可调电阻 / 电位器"),
    ("铝壳电阻", "resistor", "铝壳 / 瓷管电阻"), ("瓷管电阻", "resistor", "铝壳 / 瓷管电阻"),
    ("水泥电阻", "resistor", "水泥电阻"),
    ("插件电阻", "resistor", "插件电阻"),
    ("电阻", "resistor", "贴片电阻"),
    # 电感
    ("色环电感", "inductor", "色环 / 插件电感"),
    ("一体成型", "inductor", "一体成型电感"),
    ("功率电感", "inductor", "功率电感"),
    ("共模电感", "inductor", "共模电感"),
    ("变压器", "inductor", "网口变压器"),
    ("电感", "inductor", "贴片电感"),
    # 二极管
    ("稳压二极管", "diode", "稳压二极管"), ("稳压管", "diode", "稳压二极管"),
    ("肖特基", "diode", "肖特基二极管"),
    ("快恢复", "diode", "快恢复 / 高效率二极管"),
    ("整流桥", "diode", "整流桥"), ("整流", "diode", "通用二极管"),
    ("TVS", "transistor", "静电和浪涌保护(TVS / ESD)"),
    ("ESD", "transistor", "静电和浪涌保护(TVS / ESD)"),
    ("二极管", "diode", "通用二极管"),
    # 三极管/MOS
    ("MOS管", "transistor", "场效应管(MOSFET)"), ("MOSFET", "transistor", "场效应管(MOSFET)"),
    ("场效应", "transistor", "场效应管(MOSFET)"),
    ("IGBT", "transistor", "IGBT管 / 模块"),
    ("晶闸管", "transistor", "晶闸管(可控硅) / 模块"), ("可控硅", "transistor", "晶闸管(可控硅) / 模块"),
    ("三极管", "transistor", "三极管(BJT)"), ("晶体管", "transistor", "三极管(BJT)"),
    # 保险丝/保护
    ("保险丝", "protection", "一次性保险丝"),
    ("自恢复", "protection", "自恢复保险丝"),
    ("压敏电阻", "protection", "压敏电阻"),
    ("气体放电", "protection", "气体放电管(GDT)"),
    # 单片机/芯片
    ("单片机", "mcu", "单片机(MCU / MPU / SOC)"), ("微控制器", "mcu", "单片机(MCU / MPU / SOC)"),
    ("MCU", "mcu", "单片机(MCU / MPU / SOC)"), ("SOC", "mcu", "单片机(MCU / MPU / SOC)"),
    ("DSP", "mcu", "数字信号处理器(DSP / DSC)"),
    ("CPLD", "mcu", "可编程逻辑器件(CPLD / FPGA)"), ("FPGA", "mcu", "可编程逻辑器件(CPLD / FPGA)"),
    ("逻辑门", "logic", "逻辑门"), ("反相器", "logic", "反相器"),
    ("运放", "logic", "运算放大器 / 比较器"), ("比较器", "logic", "运算放大器 / 比较器"),
    ("存储器", "memory", "EEPROM"), ("FLASH", "memory", "NOR FLASH"),
    ("EEPROM", "memory", "EEPROM"), ("RAM", "memory", "随机存取存储器(RAM)"),
    # 时钟
    ("晶振", "oscillator", "无源晶振"), ("谐振器", "oscillator", "陶瓷谐振器(无源)"),
    ("振荡器", "oscillator", "有源晶振"),
    # 电源
    ("LDO", "power_mgmt", "线性稳压器(LDO)"), ("稳压器", "power_mgmt", "线性稳压器(LDO)"),
    ("DC-DC", "power_mgmt", "DC-DC电源芯片"), ("DC/DC", "power_mgmt", "DC-DC电源芯片"),
    ("升压", "power_mgmt", "升压芯片"), ("降压", "power_mgmt", "降压芯片"),
    ("充电管理", "power_mgmt", "电池充电管理芯片"),
    ("电源管理", "power_mgmt", "线性稳压器(LDO)"),
    # 通信
    ("CAN收发器", "comm_ic", "CAN收发器"), ("CAN", "comm_ic", "CAN收发器"),
    ("RS485", "comm_ic", "RS-485 / RS-422芯片"), ("RS232", "comm_ic", "RS232芯片"),
    ("USB转", "comm_ic", "USB转换芯片"),
    ("网卡", "comm_ic", "以太网芯片"), ("以太网", "comm_ic", "以太网芯片"),
    ("无线", "comm_ic", "无线收发芯片"),
    ("蓝牙", "rf", "蓝牙芯片"), ("WiFi", "rf", "WiFi模块"), ("WIFI", "rf", "WiFi模块"),
    # 光电器件
    ("LED", "opto", "发光二极管 / LED"), ("发光二极管", "opto", "发光二极管 / LED"),
    ("红外发射", "opto", "红外发射管"), ("光电", "opto", "光电晶体管"),
    ("数码管", "display", "LED数码管"), ("显示屏", "display", "LCD显示屏"),
    ("OLED", "display", "OLED显示屏"), ("LCD", "display", "LCD显示屏"),
    # 连接器/开关
    ("连接器", "connector", "线对板针座"), ("针座", "connector", "线对板针座"),
    ("排针", "connector", "排针"), ("排母", "connector", "排母"),
    ("胶壳", "connector", "胶壳(线对板 / 线对线)"),
    ("端子", "terminal", "针型端子"),
    ("USB接口", "connector", "USB连接器"), ("Type-C", "connector", "USB连接器"), ("TYPE-C", "connector", "USB连接器"),
    ("按键", "switch", "轻触开关"), ("开关", "switch", "轻触开关"),
    ("继电器", "relay", "功率继电器"),
    # 其他
    ("蜂鸣器", "audio", "蜂鸣器"), ("蜂鸣片", "audio", "蜂鸣片"), ("喇叭", "audio", "扬声器 / 喇叭"),
    ("磁珠", "emi", "磁珠"), ("滤波器", "emi", "EMC滤波器"), ("EMI", "emi", "EMC滤波器"),
    ("光耦", "optocoupler", "晶体管输出光耦"),
    ("传感器", "sensor", "传感器模块"),
    ("模块", "module", "其他模块"),
]

# ── 型号特征前缀 -> (cat_key, subcat) ───────────────────
MODEL_PREFIXES = [
    ("STM32", "mcu", "单片机(MCU / MPU / SOC)"), ("STM8", "mcu", "单片机(MCU / MPU / SOC)"),
    ("GD32", "mcu", "单片机(MCU / MPU / SOC)"), ("AT32", "mcu", "单片机(MCU / MPU / SOC)"),
    ("CH32", "mcu", "单片机(MCU / MPU / SOC)"), ("CH57", "mcu", "单片机(MCU / MPU / SOC)"),
    ("ESP32", "mcu", "单片机(MCU / MPU / SOC)"), ("ESP8266", "mcu", "单片机(MCU / MPU / SOC)"),
    ("PIC16", "mcu", "单片机(MCU / MPU / SOC)"), ("AVR", "mcu", "单片机(MCU / MPU / SOC)"),
    ("MSP430", "mcu", "单片机(MCU / MPU / SOC)"), ("KL", "mcu", "单片机(MCU / MPU / SOC)"),
    ("AMS1117", "power_mgmt", "线性稳压器(LDO)"), ("LM78", "power_mgmt", "线性稳压器(LDO)"),
    ("LM317", "power_mgmt", "线性稳压器(LDO)"), ("ME62", "power_mgmt", "线性稳压器(LDO)"),
    ("RT9013", "power_mgmt", "线性稳压器(LDO)"), ("XC6206", "power_mgmt", "线性稳压器(LDO)"),
    ("MP23", "power_mgmt", "DC-DC电源芯片"), ("MP14", "power_mgmt", "DC-DC电源芯片"),
    ("LM2596", "power_mgmt", "DC-DC电源芯片"), ("TPS", "power_mgmt", "DC-DC电源芯片"),
    ("XL70", "power_mgmt", "DC-DC电源芯片"), ("XL40", "power_mgmt", "DC-DC电源芯片"),
    ("SY8", "power_mgmt", "DC-DC电源芯片"),
    ("MCP2515", "comm_ic", "CAN控制器"), ("TJA10", "comm_ic", "CAN收发器"),
    ("SN65HVD", "comm_ic", "CAN收发器"), ("MAX485", "comm_ic", "RS-485 / RS-422芯片"),
    ("MAX3485", "comm_ic", "RS-485 / RS-422芯片"), ("CH340", "comm_ic", "USB转换芯片"),
    ("CP210", "comm_ic", "USB转换芯片"), ("FT232", "comm_ic", "USB转换芯片"),
    ("W25Q", "memory", "NOR FLASH"), ("AT24C", "memory", "EEPROM"),
    ("24C0", "memory", "EEPROM"), ("24C1", "memory", "EEPROM"), ("24C2", "memory", "EEPROM"),
    ("24C3", "memory", "EEPROM"), ("24C4", "memory", "EEPROM"), ("24C5", "memory", "EEPROM"),
    ("NE555", "clock", "555定时器 / 计时器"), ("DS1302", "clock", "实时时钟(RTC)"),
    ("DS3231", "clock", "实时时钟(RTC)"), ("PCF8563", "clock", "实时时钟(RTC)"),
    ("SS3", "diode", "肖特基二极管"), ("SS1", "diode", "肖特基二极管"),
    ("SS5", "diode", "肖特基二极管"), ("1N400", "diode", "通用二极管"),
    ("1N4148", "diode", "开关二极管"), ("1N5819", "diode", "肖特基二极管"),
    ("MM1Z", "diode", "稳压二极管"), ("BZT52", "diode", "稳压二极管"),
    ("SMAJ", "transistor", "静电和浪涌保护(TVS / ESD)"), ("SMBJ", "transistor", "静电和浪涌保护(TVS / ESD)"),
    ("SMA6", "transistor", "静电和浪涌保护(TVS / ESD)"),
    ("2N2222", "transistor", "三极管(BJT)"), ("2N3904", "transistor", "三极管(BJT)"),
    ("S8050", "transistor", "三极管(BJT)"), ("S8550", "transistor", "三极管(BJT)"),
    ("AO3400", "transistor", "场效应管(MOSFET)"), ("AO3401", "transistor", "场效应管(MOSFET)"),
    ("SI2302", "transistor", "场效应管(MOSFET)"), ("SI2301", "transistor", "场效应管(MOSFET)"),
    ("IRF", "transistor", "场效应管(MOSFET)"),
    ("LM358", "logic", "运算放大器 / 比较器"), ("LM324", "logic", "运算放大器 / 比较器"),
    ("OP07", "logic", "运算放大器 / 比较器"), ("TL07", "logic", "运算放大器 / 比较器"),
    ("ULN2003", "logic", "达林顿晶体管阵列"),
    ("DRV", "power_mgmt", "电机驱动芯片"),
]

# 序号开头: ① 1. 1、 (1) 等 (数字必须带标点, 防误删行首数量如 "1000 ")
SEQ_RE = re.compile(r"^\s*(?:[①-⑳]|\d+[\.、\)）])\s*")


class RuleParser:
    """纯规则解析: parse_line 解析单行, parse_text 解析多行(含后处理)。"""

    def __init__(self):
        self.dropped_nc = 0

    # ── 单行解析 ────────────────────────────────────────
    def parse_line(self, line: str) -> dict | None:
        line = (line or "").strip()
        if not line:
            return None
        line = SEQ_RE.sub("", line).strip()
        if not line:
            return None

        # NC / 不贴装 剔除
        if re.search(r"(?<![A-Za-z0-9])(?:NC|DNP|N/C|不贴装|不贴|空贴)(?![A-Za-z0-9])", line, re.I):
            self.dropped_nc += 1
            return None

        # 数量 (行首数字, 可带 个/片/只/颗/盘/包;
        # 数字后必须跟空格/单位词/行尾, 防止吞掉值类数字如 "100nF" 的 100)
        qty = ""
        m = re.match(r"(\d+(?:\.\d+)?)(?=\s*(?:个|片|只|颗|盘|包|PCS|pcs)?(?:\s|$))", line)
        if m:
            qty = str(int(float(m.group(1)))) if float(m.group(1)).is_integer() else m.group(1)
            line = re.sub(r"^\s*\d+(?:\.\d+)?\s*(?:个|片|只|颗|盘|包|PCS|pcs)?\s*", "", line, count=1)

        # 值类检测 (电容/电阻/电感)
        cap = CAP_RE.search(line)
        res = RES_RE.search(line)
        ind = IND_RE.search(line)
        value = None
        value_unit = None
        kind = None
        if cap:
            value, value_unit, kind = cap, "F", "cap"
        elif res:
            value, value_unit, kind = res, "Ω", "res"
        elif ind:
            value, value_unit, kind = ind, "H", "ind"

        # 品牌 (记录原文关键词, spec 清理用)
        brand = ""
        brand_raw = ""
        low = line
        for kw, std in BRANDS:
            if kw.lower() in low.lower():
                brand = std
                brand_raw = kw
                break

        # 封装 (记录原文, 防 SOD-123 被当型号 / spec 残留)
        package = ""
        pkg_raw = ""
        for pat, std in PACKAGES:
            m = re.search(pat, line, re.I)
            if m:
                pkg_raw = m.group(0)
                if std is None:
                    matched = m.group(0).upper()
                    if "LQFP" in matched:
                        package = f"LQFP-{re.search(r'\d+', matched).group(0)}"
                    elif "QFN" in matched:
                        package = f"QFN-{re.search(r'\d+', matched).group(0)}"
                    elif "SOP" in matched:
                        package = f"SOP-{re.search(r'\d+', matched).group(0)}"
                    elif "TSSOP" in matched:
                        package = f"TSSOP-{re.search(r'\d+', matched).group(0)}"
                    elif "MSOP" in matched:
                        package = f"MSOP-{re.search(r'\d+', matched).group(0)}"
                    elif "DFN" in matched:
                        package = f"DFN-{re.search(r'\d+', matched).group(0)}"
                    elif "DIP" in matched:
                        package = f"DIP-{re.search(r'\d+', matched).group(0)}"
                    elif "BGA" in matched:
                        package = f"BGA-{re.search(r'\d+', matched).group(0)}"
                    elif "QFP" in matched:
                        package = f"QFP-{re.search(r'\d+', matched).group(0)}"
                    elif "PLCC" in matched:
                        package = "PLCC"
                else:
                    package = std
                break

        # 分类: 值类 > 名称关键词 > 型号前缀
        cat_key = subcat = None
        if kind:
            if kind == "cap":
                if "电解" in line or "铝" in line and "电解" in line:
                    cat_key, subcat = "capacitor", "贴片型铝电解电容"
                elif "钽" in line:
                    cat_key, subcat = "capacitor", "钽电容"
                elif "独石" in line:
                    cat_key, subcat = "capacitor", "直插独石电容(MLCC)"
                elif "CBB" in line.upper():
                    cat_key, subcat = "capacitor", "CBB电容"
                elif "安规" in line:
                    cat_key, subcat = "capacitor", "安规电容"
                else:
                    cat_key, subcat = "capacitor", "贴片电容(MLCC)"
            elif kind == "res":
                if "采样" in line or "分流" in line:
                    cat_key, subcat = "resistor", "电流采样电阻 / 分流器"
                elif "电位器" in line or "可调" in line:
                    cat_key, subcat = "resistor", "可调电阻 / 电位器"
                elif "排阻" in line:
                    cat_key, subcat = "resistor", "排阻"
                elif "插件" in line:
                    cat_key, subcat = "resistor", "插件电阻"
                else:
                    cat_key, subcat = "resistor", "贴片电阻"
            else:
                if "色环" in line:
                    cat_key, subcat = "inductor", "色环 / 插件电感"
                elif "一体" in line:
                    cat_key, subcat = "inductor", "一体成型电感"
                elif "功率" in line:
                    cat_key, subcat = "inductor", "功率电感"
                elif "共模" in line:
                    cat_key, subcat = "inductor", "共模电感"
                else:
                    cat_key, subcat = "inductor", "贴片电感"
        else:
            for kw, ck, sc in NAME_KEYWORDS:
                if kw.lower() in line.lower():
                    cat_key, subcat = ck, sc
                    break
            if cat_key is None:
                for pref, ck, sc in MODEL_PREFIXES:
                    if line.upper().startswith(pref.upper()) or \
                       re.search(rf"(?<![A-Za-z0-9]){re.escape(pref)}(?![A-Za-z0-9])", line, re.I):
                        cat_key, subcat = ck, sc
                        break

        # name / spec
        if kind:
            # 值类: name = 值(含单位), spec = 其余电气参数
            num, unit_p = value.groups()
            if value_unit == "F":
                name = f"{num}{unit_p or ''}F".replace("µ", "u")
            elif value_unit == "Ω":
                name = f"{num}{unit_p or ''}Ω"
            else:
                name = f"{num}{unit_p or ''}H".replace("µ", "u")
            spec = line
            # 去掉已用部分
            spec = spec.replace(value.group(0), " ", 1)
        else:
            # 非值类: name = 型号 token (字母数字混合, 尽量长; 先剔除封装原文)
            name_line = line
            if pkg_raw:
                name_line = re.sub(re.escape(pkg_raw), " ", name_line, flags=re.I)
            tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]{2,}", name_line)
            tokens = [t for t in tokens if re.search(r"[A-Za-z]", t)]   # 排除纯数字
            name = ""
            if tokens:
                name = max(tokens, key=len)
            spec = line
            if name:
                spec = spec.replace(name, " ", 1)

        # spec 清理: 品牌/封装原文与标准名都去掉, 压缩空白
        for kw in (brand_raw, pkg_raw, package):
            if kw:
                spec = re.sub(re.escape(kw), " ", spec, flags=re.I)
        # 去掉器件名称词 (如 "贴片电容"、"肖特基二极管" 之类, 分类已确定)
        for kw, _, _ in NAME_KEYWORDS:
            if kw and kw in spec:
                spec = re.sub(re.escape(kw), " ", spec)
        spec = re.sub(r"\s+", " ", spec).strip(" -/|:：,，;；")

        if not name:
            return None

        return {
            "name": name, "brand": brand, "package": package,
            "qty": qty or "10", "spec": spec,
            "cat_key": cat_key, "subcat": subcat or "", "raw": line,
        }

    # ── 多行解析 (含后处理) ─────────────────────────────
    def parse_text(self, text: str) -> list:
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        items = []
        self.dropped_nc = 0
        for ln in lines:
            # 跳过分组标记行 (【图N】)
            if re.match(r"^【图\d+】", ln):
                continue
            it = self.parse_line(ln)
            if it:
                items.append(it)
        items = _fix_part_ref_name(items)
        items = _normalize_capacitor(items)
        items = _drop_nc_items(items)
        return items


    # ── 入库 (复用 batch_import 逻辑: 合并/未分类/撤回记录/activity) ──
    def commit(self, items: list, data_dir: str) -> dict:
        from warehouse.batch_import import BatchParser
        return BatchParser("", "", "").commit(items, data_dir)


def parse_ai_free(text: str) -> tuple:
    """便捷入口: (items, dropped_nc)。"""
    p = RuleParser()
    items = p.parse_text(text)
    return items, p.dropped_nc
