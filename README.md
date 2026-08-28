# 元器件仓库 (Parts Warehouse)

本地元器件库存管理工具。库存数据保存为 Excel，支持 AI 辅助录入、BOM 匹配取出、出入账本审计、撤回和 Git 事件同步。

[![Release](https://img.shields.io/github/v/release/Tuang-Gaashuan/parts-warehouse)](https://github.com/Tuang-Gaashuan/parts-warehouse/releases/latest)
[![License](https://img.shields.io/github/license/Tuang-Gaashuan/parts-warehouse)](LICENSE)

下载地址将在发布后更新到 GitHub Releases 页面。

## 功能

- Excel 库存：每个一级分类一个 `.xlsx`，可直接用 WPS 或 Excel 查看。
- AI 填入：在线 OpenAI 兼容 API 或离线模型均可选配；不配置 AI 也可使用手动录入和规则导入。
- 批量导入：支持 `.xls`、`.xlsx` 与文本，自动定位采购或 BOM 表头。
- BOM 清单：严格匹配仓库具体型号，显示精确、相似、不足与缺料状态，确认后按生产份数取出。
- 出入账本：一次业务操作对应一条主记录，保留明细和审计历史。
- 撤回：支持整笔、明细和批量撤回，以及取消撤回。
- 线上同步：在 GitHub/Git 或 Gitee 间提交、读取账本事件，并按事件 ID 防止重复读取。
- 数据包：可导出和导入数据，便于迁移和备份。
- OCR：使用 RapidOCR 离线识别图片或摄像头内容。

## v3.0.0

- 账本采用单一主记录与撤回快照，跨分类 BOM 取出保持为一个业务事务。
- 同步配置严格检查平台和远端地址，读取与提交操作分离，远端事件幂等入账。
- 首页和页面内为“出入账本”提供红色审计语义，为“线上同步”提供青蓝网络语义，并适配深色主题。

完整更新说明见 `RELEASE_NOTES_v3.0.0.md`。

## 发布包

| 形态 | 文件 | 内容 |
| --- | --- | --- |
| 单文件版 | `parts-warehouse.exe` | 一个可执行文件。首次运行会生成干净 `data\` 目录，不含个人库存、API Key、远端地址或本机路径。 |
| 完整目录版 | `parts-warehouse-full.zip` | 解压即用的目录运行环境，启动更快；同样只包含干净种子数据。 |
| 源码 | `parts-warehouse-src/` | 源码、测试、打包配置和文档；不包含二进制、构建缓存、用户数据或凭据。 |

两种 EXE 的功能相同，均不需要安装 Python。数据始终保存在运行目录旁的 `data\`，复制该目录即可备份。

## 开发

```bash
git clone <仓库地址>
cd parts-warehouse-src
pip install -r requirements.txt
python desktop.py
```

浏览器模式：`python app.py`，默认地址为 `http://127.0.0.1:5000`。

目录版打包：`python pack.py`。单文件版：`python -m PyInstaller parts_warehouse_onefile.spec --noconfirm`。

## License

MIT © 2026 Tuang-Gaashuan
