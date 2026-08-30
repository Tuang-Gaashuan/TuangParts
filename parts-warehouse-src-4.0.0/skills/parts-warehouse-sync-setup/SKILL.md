---
name: parts-warehouse-sync-setup
description: Create a Gitee/GitHub data repository and configure parts-warehouse (元器件仓库) in-app 线上同步 settings. Covers repo creation (with empty-repo/main-branch pitfall), Windows credentials (Git Credential Manager + PAT / SSH), field-by-field UI setup for the 4.0.x app, first-sync verification, and known pitfalls. Use when the user asks to 配置线上同步 / 创建同步数据仓库 / 排查同步失败 / 首次提交账本.
---

# parts-warehouse 线上同步设置（数据仓库创建 + 软件内配置）

本 SKILL 供 AI 执行使用：帮用户**创建 Gitee/GitHub 数据仓库**并把元器件仓库（parts-warehouse，4.0.x）的**线上同步配置**跑通到首次提交成功。

配套文档（同目录，给人看）：
- 《线上同步指导手册.md》—— 用户操作手册（建仓库 / 凭据 / 软件内设置 / FAQ）
- 《使用说明书.md》第 11 章与 15.5 节 —— 概念与字段速查

## 安装方法（分享给其他 AI / 其他电脑）
1. 把本目录 `parts-warehouse-sync-setup/` 整体复制到目标 AI 客户端的 skills 目录：
   - Hermes：`~/AppData/Local/hermes/skills/<分类>/parts-warehouse-sync-setup/SKILL.md`
   - 其他客户端：按各自 skills 目录规范放置（保留 frontmatter 的 name/description）
2. 客户端启动后按 description 自动发现；也可手动加载本 SKILL.md

## 前提与现状（4.0.x）
- 设置文件位置：源码版 `BASE_DIR/data/settings.json`，打包版 exe 旁 `data/settings.json`。**不是** `get_data_dir()` 指向的 dist 数据目录——改完配置去 dist/data 下查会扑空
- 同步架构：Git 只存 `events/` 增量事件 JSON（`event_version=2`，**一条账本记录 = 一条事件文件**，明细全放 `items[]`），不上传库存 Excel / settings / 凭据
- 浏览不联网；只有真正改库存的确认动作前检查一次远端（`ensureGitBeforeWrite()` 按 active provider）
- 双平台可同时配置、软件内一键切换；远端地址与所选平台严格绑定，禁止跨平台回退

## 1. 创建数据仓库（Gitee 主用 / GitHub 异地备份）
1. Gitee：登录 gitee.com → 右上角「+」→ 新建仓库
   - 仓库名英文小写（如 `parts-warehouse-sync`），建议「私有」（库存含采购信息）
   - ⚠️ **必须勾选「使用 Readme 文件初始化这个仓库」**：空仓库没有 main 分支，软件 `git clone --branch main` 直接失败（`Remote branch main not found`）
   - 复制 HTTPS 地址 `https://gitee.com/<login>/<repo>.git`（login 在 设置→账号资料，≠显示名）
2. GitHub：New repository → 同样勾选 `Add a README file` → 复制 `https://github.com/<user>/<repo>.git`
3. 仓库地址格式：HTTPS `https://…/<repo>.git` 或 SSH `git@gitee.com:<user>/<repo>.git`

## 2. 凭据（Windows，软件不保存 Token）
- 推荐 Git Credential Manager + PAT：
  - Gitee PAT：设置 → 安全设置 → 私人令牌 → 生成（勾 `projects` 权限）
  - GitHub PAT：Settings → Developer settings → Personal access tokens（勾 `repo` 权限）
  - 首次 clone/push 弹窗：Gitee 用户名填 **login**、密码填 **PAT**（不是登录密码）；GitHub 可浏览器登录
  - 令牌只进 Windows 凭据管理器；绝不写 settings.json / remote URL / 代码 / README / 聊天
  - 命令行存凭据：`printf 'protocol=https\nhost=gitee.com\nusername=<login>\npassword=<PAT>\n\n' | git credential approve`
- 备选 SSH：`ssh-keygen -t ed25519 -C "邮箱"` → 公钥贴平台 → 地址改 SSH 格式
- GitHub 国内常 TCP 层连接重置（`Recv failure: Connection was reset`，5 次 `git ls-remote` 约 3 成 2 败、失败单次等 21s）→ 换 Gitee 或 SSH；改 URL/token 无用

## 3. 软件内设置（4.0.x 实际 UI，字段 ID）
设置 → 线上同步页签（`setPanelGit`）：
1. `syncProviderSel`：选 Gitee（国内推荐）/ Git
2. 对应平台块填（gitee 前缀 / git 前缀字段同构）：
   - `giteeCfgUsername` 同步用户名（操作者标识，进每条记录）
   - `giteeCfgRemote` 仓库地址（`.git` 结尾）
   - `giteeCfgLocal` 本地同步目录（📁 浏览选**空目录**，如 `C:\Users\<user>\AppData\Local\parts-warehouse-sync`）
   - `giteeCfgBranch` 默认 `main`；`giteeCfgEvents` 默认 `events`
3. 勾 `giteeCfgEnabled`（启用增量同步）→ 点「保存 Gitee 配置」（`saveGiteeConfig()`）
4. `inspectGitConfig()` 检查配置（不联网、不建文件）；`checkGitSync()` 检测远端更新（首次执行 clone，弹凭据窗）
5. 线上同步页（`gitSyncPage`）三面板语义：
   - 左栏「读取内容」：本次拉到的远端新增事件
   - 右栏「远端同步」`runGitSync()` = fetch + 读未读事件，**不**上传本机账本
   - 右栏「提交本机账本」勾选 → `submitPendingLedger()` = 推送；可重复提交（新事件 ID，不覆盖历史）
6. 首次跑通：先在软件做一次入库/取出产生本机账本记录 → 线上同步页勾选提交 → 回显事件文件名

settings.json 结构：`sync_provider`（gitee|git，默认 gitee）+ `gitee_sync` / `git_sync` 两段（enabled/remote_url/local_dir/branch/events_dir/username）。`active_sync_cfg()` 按 sync_provider 严格取段；旧版只有 `git_sync` 且已配置 → 自动迁移为 `gitee_sync`。

## 4. 验证（真实链路，不能只看设置保存成功）
1. GET `/api/settings` 确认字段已存、凭据不返回
2. 检查配置通过 → 检测远端更新出现「已首次克隆 Git 仓库」
3. 用一条**真实本机账本 record_id** 调提交 → 返回 ok/submitted/events/paths
4. 对配置的完整 `remote_url` 执行 `git fetch` + `git ls-tree -r --name-only origin/<branch> -- events`，核对事件文件确实出现在远端分支
5. 重新读 pending：`event_ids` 追加而非覆盖；账本出现 origin=remote 只读记录属正常（提交后游标已推进，不会把自己 push 的事件重复读回）
6. 改动 UI/模板后：核对监听 PID/端口与当前源码一致再测；打包版必须重新构建 EXE，源码预览 ≠ 交付

## Pitfalls
- 空仓库无 main 分支 → clone 失败：网页勾 README 初始化，或推送一个初始提交
- 本地同步目录非空且非 Git 仓库 → 报错「请更换目录或清空后重试」
- push 用当前配置的完整 `<remote_url>` 而非 `git push origin`（origin 可能与界面所选平台不一致）；命令加 `-c commit.gpgsign=false` 防用户全局 GPG 签名弹窗（报 `gpg failed to sign the data` 与此同理，与平台无关）
- **提交成功后必须 `read_unread_event_files(mark_read=True)` 推进 sync_state.json 游标**，否则自己 push 的事件被 diff 成「远端新事件」，账本出现重复 origin=remote 记录
- 已提交记录可重复提交；批量提交仍一条记录一个事件文件
- 线上事件读回账本 origin=remote 只读（无 undo_id、不可撤回勾选、不自动改库存——重放是后续版本）
- 凭据泄漏排查：`grep -n 'gitee.com.*@' .git/config` 应为空（`git push -u` 会把带 token 的 URL 写进上游跟踪，必须清理）
- 设置文件在 `BASE_DIR/data/settings.json`（源码版）/ exe 旁 `data/settings.json`（打包版），不是 dist 数据目录

## 代码位置（源码版）
- `warehouse/git_sync.py`：inspect_config / init_or_update / read_event_files / upload_events / read_unread_event_files
- `warehouse/settings.py`：sync_provider + gitee_sync/git_sync 默认与迁移
- `templates/index.html`：`setPanelGit`（设置 Tab5）+ `gitSyncPage`；`static/app.js`：saveGiteeConfig / saveGitConfig / runGitSync / submitPendingLedger / loadPendingLedger
- 事件文件格式细节：见同目录《Excel-JSON转换手册.md》
