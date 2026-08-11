# 元器件仓库 (Parts Warehouse) — 源码说明

本地元器件库存管理工具：数据即 Excel、AI/规则双引擎解析、BOM 一键匹配取出。

> 使用说明（下载、界面操作、AI 配置）见外层 README。
> 本文档面向开发者：讲解**功能是如何实现的**。

## 架构总览

```
┌────────────────────────────────────────────────────┐
│  前端 (templates/index.html + static/app.js)       │
│  原生窗口: pywebview (WebView2)  ← 或浏览器直连      │
└──────────────┬─────────────────────────────────────┘
               │ HTTP /api/* (Flask, 127.0.0.1:5000)
┌──────────────▼─────────────────────────────────────┐
│  后端 app.py (路由 + 业务编排)                       │
│  warehouse/ 各模块 (解析 / 匹配 / 存储 / OCR)        │
└──────────────┬─────────────────────────────────────┘
               │ openpyxl
┌──────────────▼─────────────────────────────────────┐
│  data/<分类>.xlsx   ← 无数据库，一切就是 Excel       │
│  data/settings.json / undo_log.jsonl / activity_log │
└────────────────────────────────────────────────────┘
```

设计要点：

- **Excel 即数据库**：没有 SQLite/MySQL。每个一级分类一个 `.xlsx`，读写全部走 openpyxl，用户用 WPS/Excel 直接改文件也生效
- **AI 是可插拔的**：AI 只做"自然语言 → 结构化字段"的解析，所有解析结果都要过同一套质量红线（位号防护、NC 剔除、电容规范化、重复合并），AI 缺席时纯规则引擎兜底
- **桌面/浏览器同源**：桌面版 = pywebview 原生窗口套同一个 Flask 服务，无任何浏览器 API 依赖

## 数据模型

统一表头（所有分类共用，定义在 `warehouse/config.py` 的 `COMMON_FIELDS`）：

```
名称/型号 | 品牌 | 封装 | 数量 | 库位 | 子分类 | 规格参数 | 数据手册链接 | 备注
   name     brand  package  qty  location subcat   spec     datasheet     note
```

- 字段 key 用英文，展示标签用中文，AI 返回中文标签时按 `label_to_key` 映射回 key
- **一级分类 = Excel 文件**（`电容.xlsx` 等），文件名由分类名经 `safe_filename()` 安全化（`/`、`\`、`:`、`*` 等替换为 `-`）
- **子分类 = 行内字段**，不做单独文件
- **多入口共享物理文件**：同一个子分类可能归属多个一级分类（如「磁珠」同时在 电感 和 滤波器 下），`subcat_owners()` 返回所有归属，`primary_owner()` 取第一个作为物理文件所在分类——避免同一批元件存两份
- 空分类不建文件、总览页不显示卡片，存入第一条记录时才创建 xlsx

## 目录结构与模块职责

```
├── app.py               # Flask 后端：全部 /api/* 路由 + 业务编排（~1200 行）
├── desktop.py           # 桌面版入口：pywebview 原生窗口 + frozen 路径桥接
├── main.py              # 旧版 tkinter 入口（功能已迁移 Web，仅保留）
├── rk.py                # CLI：拍照/图片一键入库（复用后端全部质量红线）
├── seed.py              # 生成示例数据（会清空 data/，正式使用勿跑）
├── make_catalog.py      # 由 CATEGORIES 生成《category_catalog.xlsx》分类总表
├── pack.py              # 一键打包脚本（数据安全版）
├── parts_warehouse.spec # PyInstaller onedir 打包配置
├── parts_warehouse_onefile.spec # PyInstaller 单文件打包配置
├── templates/index.html # 前端页面
├── static/app.js        # 前端逻辑；style.css 主题；icons/ 分类图标
└── warehouse/           # 后端核心（见下表）
```

| 模块 | 职责 |
| --- | --- |
| `config.py` | 分类体系（36 一级 / 585 子分类）、统一字段、`primary_owner`/`safe_filename` |
| `excel_store.py` | Excel 读写、库存统计、低库存查询、行级增删改 |
| `batch_import.py` | BOM/文本批量解析管线（AI + 纯规则双引擎） |
| `ai_fill.py` | 自然语言 → 结构化字段（AI 提示词工程 + 结果规整） |
| `rules.py` | 纯规则解析（正则，零 AI 零网络） |
| `withdraw_match.py` | BOM 与库存匹配、四色状态、批量扣减 |
| `packfile.py` | 数据包 ZIP 导出/导入（合并模式 + 自动备份） |
| `ocr.py` | 图片文字识别（RapidOCR 离线单例） |
| `undo.py` | 撤销（快照式 jsonl） |
| `activity.py` | 操作流水记录 |
| `unclassified.py` | 未分类区（解析后无法定归属的元件） |
| `settings.py` | 设置读写、data_dir 解析、`chat_completions_url` 兼容 |

## 核心实现

### 1. BOM 解析管线（batch_import.py）

流程：原始文本/Excel → 拆行 → 逐批（每批约 40 行）解析 → 规整 → 去重合并 → 提交。

解析按顺序过四道质量红线（AI 和纯规则共用同一套后处理）：

1. **位号防护 `_fix_part_ref_name`**：嘉立创 BOM 把位号（C1、R2、L3…）写在名称列。名称若匹配
   `^(C|R|L|D|U|Q|F|J|P|SW|LED|EC|FB|T|CN|XTAL|BZ|LS|BT|RN|JK|X|Y|Z|K)\d+$`
   就替换为规格值（如 10uF、10kΩ），防止把位号当型号入库。正则要求纯字母+数字，所以真实型号（W25Q128JVEIQ、SS34）不会误伤。
2. **电容规范化 `_normalize_capacitor`**：名称只留容值（`1UF@35V` → 名称 `1uF`），耐压（35V）和材质（X7R/电解…）进规格参数，单位统一大小写（1UF→1uF）。
3. **NC/不贴装剔除 `_drop_nc_items`**：词边界匹配 `NC|DNP|N/C|不贴装|不贴|空贴`，行首/行尾/逗号分隔才算，`NC7SZ08` 这种型号安全。
4. **重复合并**：见下文"重复合并"。

提交走 `_merge_rows(old_rows, new_items, subcat)`——注意新行必须转成 dict（name/brand/package/qty/spec），传 list-of-list 会静默跳过合并。

### 2. 库存匹配与取出（withdraw_match.py）

BOM 行 vs 库存行的匹配分两级：

**值类（电阻/电容/电感/磁珠）** 按解析后的数值比较，绝不比原始字符串：

| 元件 | 归一化基准 | 规则 | 示例 |
| --- | --- | --- | --- |
| 电容 | pF | `(\d+(\.\d+)?)\s*(u|n|p|m)?F` | 10uF == 10UF == 10µF |
| 电阻 | Ω | `(\d+(\.\d+)?)\s*([mMkK])?\s*(Ω|ohm|R)?` | 10KΩ == 10000 |
| 电感 | nH | `(\d+(\.\d+)?)\s*(m|u|n)?H` | 1.5uH == 1500 |

> **µ 字符陷阱**：Excel 里常见希腊字母 µ（U+03BC），代码统一先
> `text.replace("µ","u").replace("μ","u")` 再走正则，否则 `10μH` 提取失败静默失配。

**封装模糊匹配**：小写 + 去非字母数字后，短的一侧包含在长的一侧即算匹配（长度 ≥3）：
`C1206 → c1206`，`0603贴片 → 0603`，`SMA(DO-214AC) → smado214ac`。

**替换料两级（精确保底 + 相似提示）**：

- exact：值（或名称）**和**封装都匹配 → 绿
- similar：值（或名称）匹配但封装/品牌不同 → 黄，标注 `⚠️ 封装不同: BOM X / 库存 Y`，供用户决定是否替代
- 型号类（二极管/IC，无"值"概念）：**严格相等才算精确**（SS34 永不匹配 SS36）；相似档用包含或 difflib 相似度 ≥0.72，且仅作提示。名称相等但封装不同 → 相似档带封装提示
- 值类搜索**限定在同一级分类**（`primary_owner(subcat)`），否则连接器料号 `1.0K-FX-4PWB-RL` 会被当成 1KΩ 电阻匹配

前端按行给四色状态：`✅ 充足` / `⚠️ 可替代` / `⚠️ 不足（差 N）` / `❌ 缺料`，缺料自动汇总到「需要采购」表。确认后按分类批量扣减，扣减动作入撤销栈。

### 3. 重复合并（相同元件合并）

合并键 = `(name, brand, package, spec)`：同名同品牌同封装同规格 → 数量相加、备注拼接。两处生效：

- 批量导入提交时：重复导入同一料号累加数量而不是堆行
- 「🔀 合并重复」按钮：整子分类手动去重（返回前后条数）

### 4. AI 解析（ai_fill.py）

- 提示词一次性注入：当前分类、可用字段（英文 key + 中文标签）、子分类候选列表
- 硬性要求写进 prompt：只输出 JSON；位号不得当名称；电容名称只填容值、耐压材质进 spec；所有电气参数合并写入 spec；数量默认 10；分类可疑时在 note 标注
- 返回结果按 `label_to_key` 把中文标签映射回英文 key，并按字段顺序重排（只保留本分类字段）
- key 来源优先级：用户配置（settings.json）> 环境变量 `DEEPSEEK_API_KEY` > 项目根 `.env` 文件
- `chat_completions_url()` 兼容各种 base_url：已含 `/v\d+`（如智谱 `/api/paas/v4`）直接追加 `/chat/completions`，否则补 `/v1`（DeepSeek/OpenAI 风格）

### 5. 纯规则解析（rules.py）

- 纯正则，零 AI 零网络（用户偏好：免费、快、离线、结果可预期）
- 用于固定格式的料袋标签/BOM 文本；AI 仅兜底乱格式
- `rk --no-ai` 走同一条链路

### 6. OCR 与拍照（ocr.py + app.py）

- RapidOCR（PP-OCRv6）本地离线识别，模型只加载一次（模块级单例）
- frozen 模式下需 `os.add_dll_directory(_MEIPASS/onnxruntime/capi)` 否则 DLL 初始化失败
- 摄像头拍照用 OpenCV（cv2）：空格=拍照、回车=结束、Backspace=撤回、ESC=取消；拍照窗口文字用英文（cv2.putText 中文乱码）
- 识别出的文本行 → AI 按"料袋模板"整理 → 同一套解析/合并/入库管线

### 7. 数据包（packfile.py）

- 导出：所有分类 xlsx + 未分类 + manifest.json（含设置）→ ZIP，排除运行时数据（cache/backgrounds/decor/日志/设置）
- 导入：**合并模式**——同名子分类按四键规则合并数量，导入前自动备份整个 data/ 到 `backups/parts-warehouse_data_<时间戳>/`
- 路径可指定（导出到任意目录）；旧名归一化（兼容老文件名）

### 8. 撤销与流水（undo.py + activity.py）

- 每次导入/取出/保存前写快照到 `undo_log.jsonl`，可回退最近操作
- `activity_log.jsonl` 记录全部操作流水（仪表盘展示最近 50 条）
- 均为 JSON Lines 追加写，Excel 不锁文件

### 9. 前端（static/app.js）

- 原生 JS 无框架；`fetch` 调用 `/api/*`
- 表格编辑：单元格直接编辑 → `保存` 批量写回；表头点击排序（▲/▼）
- **值类数值排序**：阻容感子分类按解析后的数值排，而不是字符串——`localeCompare(numeric:true)` 会把 1MΩ 排在 10kΩ 前，所以前端内置完整解析器（10K / 4.7uF / 104 EIA 码 / 4R7 / 2K2，m/M 大小写敏感、容差剥离），解析失败按型号字符串兜底且排在数值之后
- BOM 状态四色样式：`.bm-ok`（绿）/ `.bm-warn`（黄）/ `.bm-miss`（红），匹配页与取出页共用
- 桌面版通过 `window.pywebview.api.choose_dir()` 调原生文件夹选择框

## API 一览（app.py）

| 分组 | 端点 |
| --- | --- |
| 总览/数据 | `/api/overview` `/api/dashboard` `/api/lowstock` `/api/category/<key>` `/api/subcat` |
| 增删改 | `/api/save` `/api/addstock` `/api/subcat/merge` `/api/subcat/delete` `/api/data/clear` |
| 取出 | `/api/withdraw` `/api/withdraw/match` |
| 批量导入 | `/api/import_parse_text` `/api/import_parse_excel` `/api/import_parse_rules` `/api/import_commit` |
| AI | `/api/ai_fill` `/api/ai_test` `/api/ollama/models` |
| OCR/摄像头 | `/api/ocr` `/api/ocr/format` `/api/camera/list` `/api/camera/capture` |
| 数据包 | `/api/data/export` `/api/data/import` |
| 未分类 | `/api/unclassified` `/api/unclassified/assign` |
| 撤销 | `/api/undo` |
| 设置 | `/api/settings` `/api/settings/background` `/api/settings/decor` |

## 打包机制

**frozen 路径桥接**（desktop.py）：打包后代码在 `_MEIPASS`（只读），用户数据必须在 exe 旁。启动时设
`PARTS_APP_DIR`（exe 旁，可写）与 `PARTS_RES_DIR`（_MEIPASS，只读），后端据此定位数据/资源。

**两个 spec**：
- `parts_warehouse.spec`：onedir 目录版（启动快，dist 分发）
- `parts_warehouse_onefile.spec`：单文件版（一个 exe 全包）

**spec 关键点**（缺了会崩，都在注释里）：
- pywebview 必须显式收集 `webview/lib/runtimes/*/WebView2Loader.dll`，且保持包内相对路径（`webview/lib/...`），否则 `interop_dll_path()` 找不到 → 启动即崩
- RapidOCR 模型 `.onnx` + config 必须打进 `rapidocr/models`
- **VC 运行库替换**：PyInstaller 收集的 msvcp140/vcruntime140 可能旧于 onnxruntime 1.28 所需，DLL 初始化报 WinError 1114。onedir 在 pack.py 里打包后用 System32 新版覆盖；onefile 在 spec 层剔除旧版、改塞 System32 的
- `gui="edgechromium"` 强制 WebView2（Qt 已被 excludes 剔除）
- `console=False` 窗口程序；异常写 exe 旁 `flask_error.log`

**pack.py 数据安全**：打包前自动备份 exe 旁 data → `backups/`，杀占用 5000 的旧实例，打包到临时目录再覆盖正式 dist，**data 全程不移动不清除**。

**种子机制**：spec 会把项目 `data/` 打进包内，首次运行 `ensure_data_dir()` 把种子复制到 exe 旁。因此发布前清空 data/（或跑 seed.py）即可产出纯净分享包。

## 二次开发指南

- **加一级分类/子分类**：改 `warehouse/config.py` 的 `CATEGORIES` 字典 → 重启生效 → `python make_catalog.py` 重新生成分类总表
- **改字段**：改 `COMMON_FIELDS`（注意前端表头渲染与 AI prompt 同步变化）
- **换 AI 接口**：任意 OpenAI 兼容，设置页填 base_url/key/model；本地用 Ollama（provider=ollama，免 key）
- **加解析规则**：纯规则引擎在 `warehouse/rules.py`（正则），AI 兜底在 `batch_import.py` 的提示词
- **调低库存阈值**：`/api/lowstock?threshold=N`

## 快速运行

```bash
pip install -r requirements.txt
python seed.py       # 可选：示例数据
python desktop.py    # 桌面版（或 python app.py 浏览器版 :5000）
```

打包：`python pack.py`（onedir 完整版）或
`pyinstaller parts_warehouse_onefile.spec --noconfirm`（单文件版）。

## 技术栈

Flask 3 + pywebview (WebView2) + openpyxl + RapidOCR (PP-OCRv6) + OpenCV + httpx + PyInstaller；AI 接口任意 OpenAI 兼容（DeepSeek / 智谱 GLM / Ollama）。

## License

MIT © 2026 Tuang-Gaashuan
