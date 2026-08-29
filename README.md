# 元器件仓库 (Parts Warehouse)

本地元器件库存管理工具 —— 每个分类一个 Excel 文件，所见即所得，可手动编辑，也可 AI 快速录入。

- **数据就是 Excel**：无数据库，每个一级分类一个 `.xlsx`，改个文件就能导入导出、随时用 WPS/Excel 打开
- **桌面 + 浏览器双形态**：pywebview 原生窗口（无地址栏）或纯 Web 页面
- **AI 加持但非必须**：自然语言一键入库、BOM 批量解析；纯规则解析也能离线干活，AI 只是加速器
- **36 个一级分类 / 585 个子分类**：参考立创商城商品分类，覆盖常见电子元器件

## 版本目录

| 版本 | 源码 | 说明 |
| --- | --- | --- |
| **4.0.1（最新）** | [parts-warehouse-src-4.0.0/](parts-warehouse-src-4.0.0/) | Codex 风格工作区 + 全库搜索 + 数据包导入分类修复 + **0 数量元器件修复** |
| 4.0.0 | 同 4.0.1 源码目录 | Codex 风格工作区 + 全库搜索 + 数据包导入分类修复 |
| 3.0.0 | [parts-warehouse-src/](parts-warehouse-src/) | 品牌库 + 数据清洗 + 账本体系（历史版本） |

> 4.0.1 为 4.0.0 的修复版：v4.0.0 上传后立即发现「0 数量元器件」数据 bug 并修复（列错位导致的历史脏数据清理 + 全路径数量防线）。发布版 exe / zip 走 GitHub Releases（带版本号），不入仓库。

## 📖 使用说明书（4.0.0 完整版）

[点击查看《使用说明书》](parts-warehouse-src-4.0.0/使用说明书.md)

涵盖全部功能：库存管理、存入/取出、BOM 匹配与清单、全库搜索、账本与撤回、品牌库、线上同步、数据包备份迁移、36 个分类体系介绍、设置详解（数据路径 / AI / 界面 / 数据管理 / 线上同步）及从首版至今的更新记录。

## 🆕 4.0.0 更新介绍

[点击查看《更新介绍-4.0.0》](parts-warehouse-src-4.0.0/更新介绍-4.0.0.md)

- 全新 Codex 风格深色工作区：侧栏导航（展开/收起/拖拽调宽）、高信息密度表格
- 全库搜索工作区（Ctrl+K / Cmd+K），搜索真实库存，结果直达子分类
- **数据包导入分类修复**：旧包不再把元件批量误入未分类；764 条历史未分类全部按原分类归位
- 深色主题 WebView2 首帧修复 + 卡片透明度生效修复
- 新图标（EXE / 窗口 / favicon）

## 功能一览

| 功能 | 说明 |
| --- | --- |
| 库存总览 | 分类卡片总览，只显示有记录的分类，一目了然 |
| 表格编辑 | 直接点单元格编辑，支持排序（阻容感按数值排序，1MΩ 排在 10kΩ 前面） |
| AI 填入 | 一句话描述 → AI 解析成结构化字段入库，如「100个 0805 10K ±1% 贴片电阻」 |
| 批量导入 | 粘贴文本 / 上传 Excel，AI 或纯规则解析（位号防护、NC 剔除、电容值规范化） |
| BOM 匹配取出 | 导入 BOM 自动匹配库存，精确/相似/不足/缺料四色状态，按需扣减库存 |
| BOM 清单 | EDA 匹配结果保存为独立 Excel 清单，按生产份数调用取出 |
| 未分类区 | AI 无法判断归属的元件自动进未分类区，手动归类，绝不丢弃 |
| OCR 拍照入库 | 摄像头拍照或图片识别（RapidOCR 离线识别料袋标签），AI 整理后一键入库 |
| 数据包 | ZIP 一键导出/导入全部数据，换机迁移、分享、备份都靠它 |
| 账本与撤回 | 一次业务操作一笔账本记录，整笔/单项撤回，跨子分类 BOM 取出单一事务 |
| 全库搜索 | Ctrl+K 唤起，搜索名称/型号/品牌/封装/库位/规格/分类，结果直达子分类 |
| 品牌库 | 按品牌聚合采购记录，同品牌多写法自动合并，可导出 Excel、生成品牌库档案 |
| 线上同步 | Gitee / GitHub 双平台，账本一键提交线上，事件粒度 = 一次业务操作 |
| 低库存预警 | 数量低于阈值（默认 10）的元件清单 |
| 设置 | 主题色系、背景图、字号字体、数据目录、AI 接口，全部界面化 |

## 快速开始

### 方式一：直接下载打包版（推荐）

从 [Releases](https://github.com/Tuang-Gaashuan/TuangParts/releases) 下载 `parts-warehouse-4.0.1-windows.zip`（目录版 + 单文件版）或 `parts-warehouse-4.0.1.exe`，双击即用：

- 首次运行会在 exe 旁边自动生成 `data\` 目录（含示例数据）
- 数据永远在 `data\` 目录，重装、重打包都不丢数据
- 依赖 Windows 10/11 自带 WebView2（Edge 内核，通常已预装）

### 方式二：源码运行

需要 Python 3.10+：

```bash
git clone https://github.com/Tuang-Gaashuan/TuangParts.git
cd parts-warehouse/parts-warehouse-src-4.0.0
pip install -r requirements.txt
python seed.py      # 可选：生成示例数据（会清空 data/，正式使用后勿跑）
python desktop.py   # 桌面窗口版
# 或
python app.py       # 纯浏览器版 (http://127.0.0.1:5000)
```

Windows 下直接双击 `start.bat` 也可（源码版入口）。

> 可选依赖说明：`opencv-python` 用于摄像头拍照入库、`rapidocr` 用于图片文字识别，不安装不影响其它功能。

## 数据存储

所有数据在 `data/` 目录（打包版在 exe 旁边，源码版在项目目录）：

```
data/
├── settings.json        # 设置 (数据路径 / 主题 / AI 配置)
├── ledger.jsonl         # 出入账本
├── activity_log.jsonl   # 主页操作摘要
├── backgrounds/         # 背景图
├── exports/             # 数据包导出
├── 撤回日志/            # 操作撤回快照（一个 Excel = 一次操作）
├── 未分类/未分类.xlsx   # 未分类元件
├── BOM清单/             # 已保存的 BOM 清单
└── <一级分类>/<子分类>.xlsx   # 库存数据（有数据才建文件）
```

统一表头：`名称/型号 | 品牌 | 封装 | 数量 | 库位 | 子分类 | 规格参数 | 数据手册链接 | 备注`

**备份 = 复制 data/ 目录**，或使用「数据包导出」。

## 分类体系定制

分类定义在 `warehouse/config.py`（36 个一级分类 + 子分类列表），改完重启生效：

- 一级分类 = 一个 Excel 文件；子分类 = 行内的「子分类」字段
- 同名子分类出现在多个一级分类下时共享同一份物理文件（如「磁珠」同时归属 电感 和 滤波器）
- 新增/修改分类后，用 `python make_catalog.py` 重新生成《category_catalog.xlsx》（纯目录参考，不存元件）

## AI 功能配置

AI 用于「自然语言解析入库」「批量导入解析」「OCR 结果整理」，支持任意 OpenAI 兼容接口。

打开「设置 → AI 设置」，二选一：

### 在线 API（DeepSeek / 智谱 GLM 等）

| 项 | 说明 |
| --- | --- |
| 接口地址 | 如 `https://api.deepseek.com`、`https://open.bigmodel.cn/api/paas/v4`（自动兼容 /v1、/v4 写法） |
| API Key | 在对应平台申请，仅存本机 `data/settings.json` |
| 模型 | 如 `deepseek-chat`、`glm-4-flash`（免费额度） |

也可以不填 Key，改用环境变量：`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`。

### 本地离线（Ollama）

完全免费离线，数据不出本机：

```bash
ollama pull qwen2.5:7b
```

设置页选「本地离线 (Ollama)」，自动探测已装模型，无需 API Key。

> 纯规则解析（批量导入 → 纯规则模式、rk 的 `--no-ai`）完全不依赖 AI，任何环境都能用。

## 命令行工具 rk（拍照入库）

```bash
./rk                     # 打开摄像头拍照入库 (空格=拍照 回车=结束 Backspace=撤回)
./rk a.jpg b.jpg         # 指定图片文件入库
./rk -d ./袋料照片        # 处理目录下所有图片
./rk --no-ai             # 纯规则解析, 无需 AI/key/网络 (适合固定格式料袋)
./rk -y                  # 跳过逐条确认直接入库
./rk --device 0          # 摄像头编号 (默认 1)
```

## 技术栈

Flask + pywebview (WebView2) + openpyxl + RapidOCR (PP-OCRv6) + OpenAI 兼容 AI 接口 / Ollama

## FAQ

**Q: 数据会不会丢？** A: 所有数据都是 `data/` 里的 xlsx，复制目录即备份；每次数据包导入前自动备份；每次操作可撤回。

**Q: 不想用 AI 行不行？** A: 行。手动录入、纯规则批量导入、rk `--no-ai` 都不需要 AI。

**Q: 可以用哪些 AI？** A: 任何 OpenAI 兼容接口：DeepSeek、智谱 GLM、硅基流动、通义、Ollama 本地模型等，设置里填 base_url/key/model 即可。

**Q: 换电脑怎么迁移？** A: 数据包导出 → 拷贝 ZIP → 新电脑导入；或直接复制整个 `data/` 目录。

**Q: 导入旧版数据包会乱分类吗？** A: 不会。4.0.0 导入会跳过撤回日志快照、按 ZIP 目录 + 行内子分类恢复分类、旧命名自动归一化，导入前自动备份。

## License

MIT © 2026 Tuang-Gaashuan
