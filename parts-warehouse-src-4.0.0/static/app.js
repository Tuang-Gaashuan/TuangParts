/* 元器件仓库 — 前端逻辑
   页面: 首页(仪表盘) / 分类界面 / 子分类 / 表格 / 补货 / 录入
   导航: 统一 render(page) + 页面栈 pageStack, "返回"逐级回退
*/
"use strict";

let currentCatKey = null;   // 当前一级分类 key
let currentSubcat = null;   // 当前子分类名
let currentFields = [];     // 当前表格字段 [{key,label}]
let currentItems = [];      // 当前表格数据 [{key:val}]
let LOW_THRESHOLD = 10;     // 补货阈值

// ── 页面栈 (逐级返回) ──────────────────
let pageStack = [];

const PALETTE = [
  ["#e0eaff", "#1e40af"], ["#dcfce7", "#166534"], ["#f3e8ff", "#7e22ce"],
  ["#fef3c7", "#b45309"], ["#fee2e2", "#b91c1c"], ["#cffafe", "#0e7490"],
  ["#e0e7ff", "#4338ca"], ["#d1fae5", "#047857"], ["#ffedd5", "#c2410c"],
  ["#e5e7eb", "#374151"], ["#dbeafe", "#1d4ed8"], ["#ecfccb", "#3f6212"],
  ["#fce7f3", "#be185d"], ["#fef9c3", "#a16207"], ["#e0f2fe", "#0369a1"],
  ["#f5f3ff", "#6d28d9"], ["#ccfbf1", "#0f766e"], ["#fff7ed", "#c2410c"],
  ["#f1f5f9", "#475569"], ["#fdf2f8", "#9d174d"], ["#eff6ff", "#1e40af"],
  ["#f0fdfa", "#115e59"], ["#faf5ff", "#7e22ce"], ["#fefce8", "#854d0e"],
  ["#f8fafc", "#334155"], ["#fffbeb", "#b45309"], ["#f0f9ff", "#075985"],
  ["#fdf4ff", "#a21caf"], ["#ecfeff", "#0e7490"], ["#f7fee7", "#4d7c0f"],
  ["#fef2f2", "#b91c1c"], ["#eef2ff", "#4338ca"], ["#f9fafb", "#374151"],
  ["#fff1f2", "#be123c"], ["#f0fdf4", "#15803d"], ["#eff6ff", "#1d4ed8"],
];

// ── 工具 ───────────────────────────────
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  return res.json();
}

function showToast(msg, ms = 2200) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove("show"), ms);
}

function setCrumbs(text) {
  const el = document.getElementById("crumbs");
  if (text) { el.textContent = text; el.style.display = ""; }
  else el.style.display = "none";
}

function hideToolbar(ids) {
  for (const id of ids) document.getElementById(id).style.display = "none";
}

function hideAllPages() {
  for (const id of ["homePage", "overviewPage", "subcatPage", "detailPage", "lowstockPage", "unclassifiedPage", "withdrawPage", "inputPage", "bomMatchPage", "bomManagePage", "brandsPage", "brandDetailPage", "gitSyncPage", "ledgerPage", "workspaceSearchPage"]) {
    document.getElementById(id).style.display = "none";
  }
}

async function checkGitBeforeInventory(page) {
  // 页面浏览不再触发网络同步；保留此函数名兼容 Git 页面之外的旧调用。
  return true;
}

async function ensureGitBeforeWrite() {
  try {
    const s = currentSettings || await api("/api/settings");
    currentSettings = s;
    const prov = s.sync_provider === "gitee" ? "gitee_sync" : "git_sync";
    const g = s[prov] || {};
    if (!g.enabled) return true;
    const r = await api("/api/git-sync/check", { method: "POST" });
    if (!r.ok) {
      showToast(`远端未同步，已阻止写入：${r.message || "检查失败"}`, 4500);
      return false;
    }
    return true;
  } catch (e) {
    showToast(`线上同步失败，已阻止写入：${e.message}`, 4500);
    return false;
  }
}

// ── 页面跳转前的库存增量同步检测 ──────────
async function render(page, push = true) {
  if (push) pageStack.push(page);
  setActiveSidebar(page);
  document.getElementById("btnBack").style.display =
    page === "home" ? "none" : "";
  hideToolbar(["searchBox", "btnNew", "btnAI", "btnSave", "btnMerge", "btnAddStock", "btnWithdrawStock"]);
  hideAllPages();
  setCrumbs("");

  if (page === "home")            await renderHome();
  else if (page === "categories") await renderCategories();
  else if (page === "category:unclassified") await renderUnclassified();
  else if (page.startsWith("category:")) await renderCategory(page.slice(9));
  else if (page.startsWith("subcat:"))   await renderSubcat(page.slice(7));
  else if (page === "lowstock")   await renderLowStock();
  else if (page === "withdraw")   await renderWithdraw();
  else if (page === "bommatch")   await renderBomMatch();
  else if (page === "bommanage")  await renderBomManage();
  else if (page === "input")      await renderInput();
  else if (page === "brands")     await renderBrands();
  else if (page === "gitsync")    await renderGitSync();
  else if (page === "workspace-search") await renderWorkspaceSearch();
  else if (page === "ledger")     await renderLedger();
  else if (page.startsWith("brand:")) await renderBrandDetail(page.slice(6));
}

// 导航入口 (HTML onclick 调用这些)
function goHome()        { render("home"); }
function goCategories()  { render("categories"); }
function goLowStock()    { render("lowstock"); }
function goInput()       { render("input"); }
function goWithdraw()    { render("withdraw"); }
function goBomMatch()    { render("bommatch"); }
function goBomManage()   { render("bommanage"); }
function goBrands()      { render("brands"); }
function goGitSync()     { render("gitsync"); }
function goLedger()      { render("ledger"); }
function goCategory(key) { render("category:" + key); }
function goSubcat(name)  { render("subcat:" + name); }
function goBrand(name)   { render("brand:" + name); }

function goBack() {
  if (pageStack.length <= 1) { render("home", false); return; }
  pageStack.pop();
  const prev = pageStack[pageStack.length - 1];
  render(prev, false);
}

async function renderLedger() {
  document.getElementById("ledgerPage").style.display = "";
  await loadLedger();
}

async function loadLedger() {
  const qs = new URLSearchParams();
  for (const [id, key] of [["ledgerStart", "start"], ["ledgerEnd", "end"], ["ledgerAction", "action"]]) {
    const v = document.getElementById(id).value;
    if (v) qs.set(key, v);
  }
  const data = await api(`/api/ledger?${qs}`);
  const rows = data.records || [];
  document.getElementById("ledgerCount").textContent = `${rows.length} 笔`;
  const list = document.getElementById("ledgerList");
  if (!rows.length) { list.innerHTML = '<div class="wheel-placeholder">暂无符合条件的出入库记录</div>'; return; }
  const thead = `<thead><tr><th class="col-cb">选择</th><th>时间</th><th>动作</th><th>状态</th><th>来源</th><th>数量</th><th>操作者</th><th>原因</th><th>明细</th><th class="col-op">操作</th></tr></thead>`;
  const body = rows.map((r, idx) => {
    const cls = r.action === "录入" ? "ledger-in" : (r.action === "取出" ? "ledger-out" : "ledger-adjust");
    const isRemote = r.origin === "remote";
    const badge = isRemote
      ? '<span class="ledger-origin ledger-origin-remote">🌐 线上</span>'
      : (r.sync_status === "submitted"
          ? '<span class="ledger-origin ledger-origin-sub">⬆ 已提交</span>'
          : '<span class="ledger-origin ledger-origin-local">🖥️ 本机</span>');
    const state = r.status || "正常";
    const isUndone = state === "已撤回" || state === "部分撤回";
    const isOriginalAction = ["录入", "取出", "调整"].includes(r.action);
    const hasNormalDetails = (r.details || []).some(d => (d.status || "正常") === "正常");
    const hasUndoneDetails = (r.details || []).some(d => d.status === "已撤回");
    const canUndo = !!r.undo_id && !isRemote && isOriginalAction && hasNormalDetails;
    const canRestore = !!r.undo_id && !isRemote && isOriginalAction && hasUndoneDetails;
    const cbMode = canRestore && !canUndo ? "restore" : "undo";
    const cb = `<input type="checkbox" class="ledger-select" data-mode="${cbMode}" data-undo-id="${escHtml(r.undo_id || "")}" ${canUndo || canRestore ? "" : "disabled"}>`;
    const undoWhole = canUndo && canRestore
      ? `<button class="btn btn-danger btn-mini" onclick="undoLedgerWhole('${escHtml(r.undo_id || "")}')">↩ 撤回剩余</button><button class="btn btn-restore btn-mini" onclick="restoreLedgerWhole('${escHtml(r.undo_id || "")}')">↪ 取消已撤回</button>`
      : (canUndo
          ? `<button class="btn btn-danger btn-mini" onclick="undoLedgerWhole('${escHtml(r.undo_id || "")}')">↩ 整笔撤回</button>`
          : (canRestore ? `<button class="btn btn-restore btn-mini" onclick="restoreLedgerWhole('${escHtml(r.undo_id || "")}')">↪ 取消撤回</button>` : ""));
    const stateHtml = isUndone
      ? `<span class="ledger-state ledger-state-undone">${escHtml(state)}</span>`
      : `<span class="ledger-state ledger-state-active">正常</span>`;
    const total = r.total_delta > 0 ? `+${r.total_delta}` : (r.total_delta || 0);
    const details = (r.details || []).map((d, di) => {
      const detailState = d.status || "正常";
      const detailCanUndo = canUndo && detailState === "正常";
      const detailCanRestore = canRestore && detailState === "已撤回";
      const dcb = detailCanUndo || detailCanRestore
        ? `<input type="checkbox" class="ledger-item-select" data-mode="${detailCanRestore ? "restore" : "undo"}" data-undo-id="${escHtml(r.undo_id || "")}" data-subcat="${escHtml(d.subcat || "")}" data-row="${d.row ?? di}" data-detail-index="${di}">`
        : "";
      const itemBtn = detailCanUndo
        ? `<button class="btn btn-danger btn-mini" onclick="undoLedgerItem('${escHtml(r.undo_id || "")}','${escHtml(d.subcat || "")}','${d.row ?? di}',${di})">↩ 撤回</button>`
        : (detailCanRestore ? `<button class="btn btn-restore btn-mini" onclick="restoreLedgerItem('${escHtml(r.undo_id || "")}','${escHtml(d.subcat || "")}','${d.row ?? di}',${di})">↪ 取消撤回</button>` : "");
      return `<tr><td class="col-cb">${dcb}</td><td>${escHtml(d.subcat || "")}</td><td>${escHtml(d.name || "")}</td><td class="ld-num">${d.delta > 0 ? "+" : ""}${d.delta}</td><td class="ld-num">${d.quantity_before ?? ""} → ${d.quantity_after ?? ""}</td><td><span class="ledger-detail-state ${detailState === "正常" ? "ledger-detail-active" : "ledger-detail-undone"}">${escHtml(detailState)}</span>${d.note ? ` <span class="ld-note">${escHtml(d.note)}</span>` : ""}</td><td class="col-op">${itemBtn}</td></tr>`;
    }).join("") || '<tr><td class="col-cb"></td><td colspan="6" class="ld-empty">无明细</td></tr>';
    return `<tr class="ledger-row ${cls}" onclick="toggleLedger(${idx})"><td class="col-cb" onclick="event.stopPropagation()">${cb}</td>
      <td class="ld-time">${escHtml((r.time || "").slice(0, 16).replace("T", " "))}</td>
      <td class="ld-action">${escHtml(r.action || "调整")}</td>
      <td>${stateHtml}</td>
      <td>${badge}</td>
      <td class="ld-num ld-total">${total}</td>
      <td>${escHtml(r.operator || "未设置")}</td>
      <td class="ld-reason" title="${escHtml(r.reason || "")}">${escHtml(r.reason || "")}</td>
      <td class="ld-detail-btn">${(r.details || []).length} 项 <span class="ld-toggle-hint">▾</span></td>
      <td class="col-op" onclick="event.stopPropagation()">${undoWhole}</td>
    </tr>
    <tr class="ld-detail-wrap" id="ledgerDetail${idx}"><td colspan="10"><table class="ledger-detail-table"><thead><tr><th class="col-cb">选择</th><th>子分类</th><th>名称</th><th>数量变化</th><th>变化前 → 变化后</th><th>状态 / 备注</th><th class="col-op">操作</th></tr></thead><tbody>${details}</tbody></table></td></tr>`;
  }).join("");
  list.innerHTML = `<div class="ledger-table-wrap"><table class="ledger-table">${thead}<tbody>${body}</tbody></table></div>`;
}

function toggleLedger(idx) {
  const el = document.getElementById(`ledgerDetail${idx}`);
  el.classList.toggle("open");
  const btn = el.previousElementSibling.querySelector(".ld-toggle-hint");
  if (btn) btn.textContent = el.classList.contains("open") ? "▴" : "▾";
}

async function undoLedgerWhole(undoId) {
  if (!undoId) return;
  if (!confirm("撤回这笔完整操作（恢复该操作涉及的全部物料数量）？")) return;
  await undoLedger(undoId);
}

async function undoLedgerItem(undoId, subcat, row, detailIndex = null) {
  if (!undoId) return;
  if (!confirm(`撤回这笔操作中的「${subcat}」这一项？`)) return;
  await undoLedger(undoId, [{ subcat, row: Number(row), detail_index: detailIndex }]);
}

async function restoreLedgerWhole(undoId) {
  if (!undoId) return;
  if (!confirm("取消撤回这笔操作（恢复该操作已撤回的全部明细）？")) return;
  await restoreLedger(undoId);
}

async function restoreLedgerItem(undoId, subcat, row, detailIndex = null) {
  if (!undoId) return;
  if (!confirm(`取消撤回「${subcat}」这一项？`)) return;
  await restoreLedger(undoId, [{ subcat, row: Number(row), detail_index: detailIndex }]);
}

async function restoreLedger(undoId, items = [], skipSync = false) {
  if (!undoId) return;
  if (!skipSync && !await ensureGitBeforeWrite()) return;
  const result = await api("/api/ledger/restore", {method: "POST", body: JSON.stringify({undo_id: undoId, items})});
  toast(result.ok ? `已${result.status === "正常" ? "取消撤回" : result.status}` : (result.error || "取消撤回失败"));
  if (result.ok) await loadLedger();
}

async function undoLedger(undoId, items = [], skipSync = false) {
  if (!undoId) return;
  if (!skipSync && !await ensureGitBeforeWrite()) return;
  const result = await api("/api/ledger/undo", {method: "POST", body: JSON.stringify({undo_id: undoId, items})});
  toast(result.ok ? `已${result.status || "撤回"}` : (result.error || "撤回失败"));
  if (result.ok) await loadLedger();
}

async function undoSelectedLedger() {
  const grouped = {undo: {}, restore: {}};
  document.querySelectorAll(".ledger-item-select:checked").forEach(el => {
    const mode = el.dataset.mode || "undo";
    (grouped[mode][el.dataset.undoId] ||= []).push({subcat: el.dataset.subcat, row: Number(el.dataset.row), detail_index: Number(el.dataset.detailIndex)});
  });
  const whole = {undo: [], restore: []};
  document.querySelectorAll(".ledger-select:checked").forEach(el => {
    const mode = el.dataset.mode || "undo";
    whole[mode].push(el.dataset.undoId);
  });
  const wholeCount = whole.undo.length + whole.restore.length;
  const itemCount = Object.values(grouped.undo).reduce((s, a) => s + a.length, 0) + Object.values(grouped.restore).reduce((s, a) => s + a.length, 0);
  if (!wholeCount && !itemCount) { showToast("请先勾选要操作的账本记录（行首勾选=整笔，展开后勾选=单项）"); return; }
  if (!confirm(`确定执行所选：${wholeCount} 笔整笔、${itemCount} 个单项？`)) return;
  if (!await ensureGitBeforeWrite()) return;
  for (const id of whole.undo) await undoLedger(id, [], true);
  for (const id of whole.restore) await restoreLedger(id, [], true);
  for (const [id, items] of Object.entries(grouped.undo)) if (!whole.undo.includes(id)) await undoLedger(id, items, true);
  for (const [id, items] of Object.entries(grouped.restore)) if (!whole.restore.includes(id)) await restoreLedger(id, items, true);
}

async function clearHomeLogs() {
  if (!confirm("清除主页最近出入摘要？不会修改库存，也不会清除出入账本。")) return;
  const result = await api("/api/data/clear", {
    method: "POST", body: JSON.stringify({scope: "activity"}),
  });
  toast(result.message || "已清除");
  const wheel = document.getElementById("logWheel");
  if (wheel) wheel.innerHTML = '<div class="wheel-placeholder">暂无操作记录<br>保存元器件后这里会显示存入/使用情况</div>';
}
async function clearLedger() {
  if (!confirm("清除全部出入账本记录？不会修改库存，也不会清除主页摘要。")) return;
  const result = await api("/api/ledger/clear", {method: "POST"});
  toast(result.message || "账本已清除");
  await loadLedger();
}

async function renderGitSync() {
  document.getElementById("gitSyncPage").style.display = "";
  const s = currentSettings || await api("/api/settings");
  currentSettings = s;
  const prov = s.sync_provider === "gitee" ? "gitee" : "git";
  const g = s[`${prov}_sync`] || {};
  const provName = prov === "gitee" ? "🌐 Gitee" : "🔄 Git";
  document.getElementById("gitSyncProviderHint").textContent = `当前平台：${provName}`;
  document.getElementById("gitSyncInfo").textContent = g.configured
    ? `${g.remote_url} · ${g.branch || "main"} · 用户：${g.username || "未设置"}`
    : "尚未配置所选平台的同步信息，请先在设置 → 线上同步中填写仓库地址和本地目录。";
  document.getElementById("gitSyncState").textContent = g.enabled ? "已启用" : "未启用";
  document.getElementById("gitSyncStatus").textContent = "";
  document.getElementById("gitUploadStatus").textContent = "";
  document.getElementById("gitEventList").textContent = "暂无本次同步事件";
  loadPendingLedger();
}

async function runGitSync() {
  const state = document.getElementById("gitSyncStatus");
  state.textContent = "正在同步远端…首次同步可能需要克隆仓库。";
  try {
    const r = await api("/api/git-sync/check", { method: "POST" });
    state.textContent = r.ok
      ? `✅ ${r.message === "Git 没有新提交" ? "远端已是最新，没有新提交" : r.message}`
      : `❌ ${r.message}`;
    document.getElementById("gitSyncState").textContent = r.ok ? "已连接" : "失败";
    if (r.ok) {
      const ev = await api("/api/git-sync/events", { method: "POST", body: JSON.stringify({ mark_read: true }) });
      const list = document.getElementById("gitEventList");
      if (ev.ok && ev.events.length) {
        list.textContent = ev.events.map(x => `${x.event_id} · ${x.operation} · ${x.part_id} · ${x.delta} · ${x.username || ""}`).join("\n");
      } else {
        const known = (ev.known_ids || []).filter(Boolean);
        list.textContent = known.length
          ? `远端没有新的未读事件\n本机已读取 ${known.length} 条：${known.join("、")}`
          : "远端没有新的未读事件，本机暂无已读记录";
      }
      list.style.whiteSpace = "pre-line";
    }
  } catch (e) { state.textContent = `❌ 同步失败: ${e.message}`; }
}

async function loadPendingLedger() {
  const info = document.getElementById("syncPendingInfo");
  const list = document.getElementById("syncPendingList");
  try {
    const d = await api("/api/sync/pending");
    if (!d.enabled) {
      info.textContent = "线上同步未启用，请在设置 → 线上同步中启用当前平台。";
      list.innerHTML = "";
      return;
    }
    if (d.config_error) {
      info.textContent = `配置错误：${d.config_error}`;
      list.innerHTML = "";
      return;
    }
    if (!d.count) {
      info.textContent = "本机暂无账本记录。";
      list.innerHTML = "";
      return;
    }
    info.textContent = `本机账本 ${d.count} 笔（共 ${d.detail_count} 条物料明细）· 平台：${d.provider === "gitee" ? "Gitee" : "GitHub"}`;
    list.innerHTML = (d.records || []).map(r => {
      const sign = r.total_delta > 0 ? "+" : "";
      const state = r.sync_status === "submitted" ? "⬆ 已提交，可重复提交" : "🖥️ 待提交";
      return `<label class="sync-pending-item"><input type="checkbox" class="sync-record-check" value="${escHtml(r.record_id)}" checked><span class="sp-time">${escHtml((r.time || "").slice(0, 16).replace("T", " "))}</span><span class="sp-action">${escHtml(r.action || "调整")}</span><span class="sp-total">${sign}${r.total_delta || 0} 件</span><span class="sp-detail">${(r.details || []).length} 项</span><span class="sp-status">${state}</span></label>`;
    }).join("");
  } catch (e) {
    info.textContent = `加载失败: ${e.message}`;
  }
}

async function submitPendingLedger() {
  const status = document.getElementById("gitUploadStatus");
  const info = document.getElementById("syncPendingInfo");
  if (!confirm("将当前勾选的本机账本记录提交为线上事件；已提交记录也会作为新事件再次提交，继续吗？")) return;
  const recordIds = [...document.querySelectorAll(".sync-record-check:checked")].map(el => el.value);
  if (!recordIds.length) { status.textContent = "⚠️ 请先勾选要提交的账本记录"; return; }
  status.textContent = "正在提交并推送…";
  try {
    const r = await api("/api/sync/submit", { method: "POST", body: JSON.stringify({ record_ids: recordIds }) });
    if (!r.ok) { status.textContent = `❌ ${r.message}`; return; }
    status.textContent = `✅ ${r.message}：${r.submitted} 笔账本 → ${r.events} 条事件`;
    const list = document.getElementById("gitEventList");
    const lines = (r.paths || []).map(p => `⬆ 已上传：${p.split("/").pop()}`);
    if (lines.length) {
      list.textContent = lines.join("\n");
      list.style.whiteSpace = "pre-line";
    }
    info.textContent = "已提交，列表正在刷新…";
    await loadPendingLedger();
  } catch (e) {
    status.textContent = `❌ 提交失败: ${e.message}`;
  }
}

async function renderHome() {
  document.getElementById("homePage").style.display = "";
  const [data, lowStock] = await Promise.all([
    api("/api/dashboard"),
    api("/api/lowstock").catch(() => ({ items: [] })),
  ]);
  renderStats(data.stats, lowStock.items || lowStock.rows || []);
  renderLogs(data.logs || []);
  renderHomeInventory(data.recent_items || []);
}

function renderStats(s, lowStock = []) {
  document.getElementById("homeMetricItems").textContent = s.items ?? 0;
  document.getElementById("homeMetricQty").textContent = s.total_qty ?? 0;
  document.getElementById("homeMetricCategories").textContent = `${s.categories ?? 0} 个一级分类`;
  document.getElementById("homeMetricSubcats").textContent = `${s.subcats ?? 0} 个子分类`;
  document.getElementById("homeMetricLow").textContent = lowStock.length;
}

function renderHomeInventory(items) {
  const tbody = document.getElementById("homeInventoryBody");
  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="workspace-empty">暂无库存记录。打开完整库存后录入元器件，近期条目会显示在这里。</td></tr>';
    return;
  }
  tbody.innerHTML = items.slice(0, 5).map((item) => {
    const qty = Number(item.qty ?? item.quantity ?? 0);
    const low = qty <= LOW_THRESHOLD;
    return `<tr><td>${escHtml(item.subcat || item.category || "未分类")}</td><td class="workspace-mpn">${escHtml(item.name || item.model || "-")}</td><td>${escHtml(item.brand || "-")}</td><td>${qty}</td><td class="workspace-location">${escHtml(item.location || "-")}</td><td><span class="workspace-state ${low ? "is-low" : "is-healthy"}">${low ? "低库存" : "充足"}</span></td></tr>`;
  }).join("");
}

function renderLogs(logs) {
  const wheel = document.getElementById("logWheel");
  if (!logs.length) {
    wheel.innerHTML = '<div class="workspace-empty">暂无操作记录。库存录入、取出或调整后，操作会显示在这里。</div>';
    return;
  }
  wheel.innerHTML = logs.slice(0, 4).map((log) => {
    const positive = log.qty_delta > 0;
    const negative = log.qty_delta < 0;
    const kind = positive ? "is-in" : (negative ? "is-out" : "is-neutral");
    const label = positive ? "库存入库" : (negative ? "库存取出" : "库存调整");
    const delta = log.qty_delta ? `${positive ? "+" : ""}${log.qty_delta}` : "";
    return `<div class="workspace-activity ${kind}"><i></i><div><b>${escHtml(label)}</b><span>${escHtml(log.subcat || "库存记录")} ${delta ? `· ${delta}` : ""} · ${escHtml(log.time || "")}</span></div></div>`;
  }).join("");
}

async function loadLowStockBadge() {
  const d = await api(`/api/lowstock?threshold=${LOW_THRESHOLD}`);
  const badge = document.getElementById("lowStockBadge");
  if (d.items.length > 0) {
    badge.textContent = d.items.length;
    badge.style.display = "flex";
  } else {
    badge.style.display = "none";
  }
}

// ── 分类界面 (第1级) ───────────────────
async function renderCategories() {
  document.getElementById("overviewPage").style.display = "";
  const data = await api("/api/overview");
  document.getElementById("totalBadge").textContent = `共 ${data.total} 条记录`;

  const grid = document.getElementById("cardGrid");
  grid.innerHTML = "";
  data.cards.forEach((card, i) => {
    const [bg, fg] = PALETTE[i % PALETTE.length];
    const el = document.createElement("div");
    el.className = "card" + (card.key === "unclassified" ? " card-warn" : "");
    // 一级分类图标: 优先用生成的图片, 无图回退单字
    const iconHtml = `<img class="card-img" src="/static/icons/${card.key}.png" alt="${card.name}" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"><div class="card-icon" style="background:${bg};color:${fg};display:none">${card.name[0]}</div>`;
    el.innerHTML = `
      ${iconHtml}
      <div class="card-name">${card.name}</div>
      <div class="card-count">${card.count} 条记录</div>`;
    el.onclick = () => goCategory(card.key);
    grid.appendChild(el);
  });
}

// ── 第2级: 子分类列表 ──────────────────
async function renderCategory(key) {
  currentCatKey = key;
  currentSubcat = null;
  document.getElementById("subcatPage").style.display = "";

  const data = await api(`/api/category/${key}`);
  document.getElementById("subcatTitle").textContent = data.name;
  document.getElementById("subcatCount").textContent = `${data.subcats.length} 个子分类`;

  const grid = document.getElementById("subcatGrid");
  grid.innerHTML = "";
  data.subcats.forEach((s, i) => {
    const [bg, fg] = PALETTE[i % PALETTE.length];
    const el = document.createElement("div");
    el.className = "card";
    el.innerHTML = `
      <div class="card-icon" style="background:${bg};color:${fg}">${s.name[0]}</div>
      <div class="card-name">${s.name}</div>
      <div class="card-count">${s.count} 条元器件</div>`;
    el.onclick = () => goSubcat(s.name);
    grid.appendChild(el);
  });
  if (!data.subcats.length) {
    grid.innerHTML = '<div class="empty-hint">该分类暂无元器件，可去「录入界面」添加</div>';
  }
}

// ── 未分类界面 (手动归类) ───────────────
let uncatTree = null;

function escHtml(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function renderUnclassified() {
  currentCatKey = "unclassified";
  currentSubcat = null;
  document.getElementById("unclassifiedPage").style.display = "";
  const data = await api("/api/unclassified");
  uncatTree = data.cat_tree;
  document.getElementById("uncatCount").textContent = `${data.count} 条待归类`;
  document.getElementById("uncatStatus").textContent = "";

  // 一级分类下拉 (36 个大类)
  const catSel = document.getElementById("uncatCatSel");
  catSel.innerHTML = '<option value="">— 选择一级分类 —</option>';
  for (const [key, info] of Object.entries(uncatTree)) {
    const opt = document.createElement("option");
    opt.value = key;
    opt.textContent = info.name;
    catSel.appendChild(opt);
  }
  document.getElementById("uncatSubcatSel").innerHTML = '<option value="">— 选择子分类 —</option>';

  // 表格
  const tbody = document.getElementById("uncatBody");
  tbody.innerHTML = "";
  if (!data.items.length) {
    tbody.innerHTML = '<tr><td colspan="7"><div class="empty-hint">未分类列表为空 🎉 批量导入时未识别出分类的元件会自动出现在这里</div></td></tr>';
    return;
  }
  data.items.forEach((it) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><input type="checkbox" class="uncat-check" data-index="${it.index}"></td>
      <td>${escHtml(it.name)}</td>
      <td>${escHtml(it.brand)}</td>
      <td>${escHtml(it.package)}</td>
      <td>${escHtml(it.qty)}</td>
      <td>${escHtml(it.spec)}</td>
      <td class="uncat-raw">${escHtml(it.raw)}</td>`;
    tbody.appendChild(tr);
  });
}

function onUncatCatChange() {
  const key = document.getElementById("uncatCatSel").value;
  const subSel = document.getElementById("uncatSubcatSel");
  subSel.innerHTML = '<option value="">— 选择子分类 —</option>';
  if (!key || !uncatTree || !uncatTree[key]) return;
  uncatTree[key].subs.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = s;
    subSel.appendChild(opt);
  });
}

function toggleUncatAll(cb) {
  document.querySelectorAll(".uncat-check").forEach((c) => { c.checked = cb.checked; });
}

function selectedUncatIndices() {
  return [...document.querySelectorAll(".uncat-check:checked")].map((c) => +c.dataset.index);
}

async function assignUnclassified() {
  const statusEl = document.getElementById("uncatStatus");
  const indices = selectedUncatIndices();
  const catKey = document.getElementById("uncatCatSel").value;
  const subcat = document.getElementById("uncatSubcatSel").value;
  if (!indices.length) { statusEl.textContent = "请先勾选要归类的元件"; return; }
  if (!catKey || !subcat) { statusEl.textContent = "请选择一级分类和子分类"; return; }
  if (!await ensureGitBeforeWrite()) { statusEl.textContent = "远端未同步，已取消归类"; return; }
  statusEl.textContent = "归类中…";
  const res = await api("/api/unclassified/assign", {
    method: "POST", body: JSON.stringify({ indices, cat_key: catKey, subcat }),
  });
  if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
  showToast(`已归类 ${res.moved} 条到「${subcat}」`);
  await renderUnclassified();
}

// ── 取出界面 (出库) ─────────────────────
let wdItems = [];

async function renderWithdraw() {
  document.getElementById("withdrawPage").style.display = "";
  document.getElementById("wdStatus").textContent = "";
  const data = await api("/api/overview");
  const catSel = document.getElementById("wdCatSel");
  catSel.innerHTML = '<option value="">— 选择一级分类 —</option>';
  data.cards.forEach((c) => {
    if (c.key === "unclassified") return;  // 未分类不参与取出
    const opt = document.createElement("option");
    opt.value = c.key;
    opt.textContent = `${c.name} (${c.count} 条)`;
    catSel.appendChild(opt);
  });
  document.getElementById("wdSubcatSel").innerHTML = '<option value="">— 选择子分类 —</option>';
  document.getElementById("wdCheckAll").checked = false;
  document.getElementById("wdCount").textContent = "";
  document.getElementById("wdBody").innerHTML =
    '<tr><td colspan="7"><div class="empty-hint">先选择一级分类和子分类</div></td></tr>';
  loadWdBomLists();
}

async function onWdCatChange() {
  const key = document.getElementById("wdCatSel").value;
  const subSel = document.getElementById("wdSubcatSel");
  subSel.innerHTML = '<option value="">— 选择子分类 —</option>';
  document.getElementById("wdBody").innerHTML =
    '<tr><td colspan="7"><div class="empty-hint">请选择子分类</div></td></tr>';
  document.getElementById("wdCount").textContent = "";
  if (!key) return;
  const data = await api(`/api/category/${key}`);
  data.subcats.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.name;
    opt.textContent = `${s.name} (${s.count} 条)`;
    subSel.appendChild(opt);
  });
}

async function onWdSubcatChange() {
  const name = document.getElementById("wdSubcatSel").value;
  const tbody = document.getElementById("wdBody");
  const statusEl = document.getElementById("wdStatus");
  document.getElementById("wdCheckAll").checked = false;
  statusEl.textContent = "";
  if (!name) {
    tbody.innerHTML = '<tr><td colspan="7"><div class="empty-hint">请选择子分类</div></td></tr>';
    document.getElementById("wdCount").textContent = "";
    return;
  }
  const data = await api(`/api/subcat?name=${encodeURIComponent(name)}`);
  wdItems = data.items;
  document.getElementById("wdCount").textContent = `${data.items.length} 种元件`;
  tbody.innerHTML = "";
  if (!data.items.length) {
    tbody.innerHTML = '<tr><td colspan="7"><div class="empty-hint">该子分类暂无元件</div></td></tr>';
    return;
  }
  data.items.forEach((it, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><input type="checkbox" class="wd-check" data-row="${i}"></td>
      <td>${escHtml(it.name)}</td>
      <td>${escHtml(it.brand)}</td>
      <td>${escHtml(it.package)}</td>
      <td class="wd-stock">${escHtml(it.qty || 0)}</td>
      <td><input type="number" class="wd-qty" data-row="${i}" min="1" placeholder="0" style="width:70px"></td>
      <td class="uncat-raw">${escHtml(it.spec)}</td>`;
    tbody.appendChild(tr);
  });
}

function toggleWdAll(cb) {
  document.querySelectorAll(".wd-check").forEach((c) => { c.checked = cb.checked; });
}

async function doWithdraw() {
  const statusEl = document.getElementById("wdStatus");
  const name = document.getElementById("wdSubcatSel").value;
  if (!name) { statusEl.textContent = "请先选择子分类"; return; }
  const items = [];
  document.querySelectorAll(".wd-check:checked").forEach((cb) => {
    const row = +cb.dataset.row;
    const qtyInput = document.querySelector(`.wd-qty[data-row="${row}"]`);
    const qty = qtyInput ? parseInt(qtyInput.value, 10) : 0;
    if (qty > 0) items.push({ row, qty });
  });
  if (!items.length) { statusEl.textContent = "请勾选元件并填写取出数量"; return; }
  if (!await ensureGitBeforeWrite()) { statusEl.textContent = "远端未同步，已取消取出"; return; }
  statusEl.textContent = "取出中…";
  const res = await api("/api/withdraw", {
    method: "POST", body: JSON.stringify({ name, items }),
  });
  if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
  showToast(`已取出 ${res.taken} 件 (${res.subcat})`);
  statusEl.textContent = `✅ 已取出 ${res.taken} 件`;
  await onWdSubcatChange();   // 刷新剩余库存
  loadLowStockBadge();        // 联动补货提醒
}

// ── 取出页 Tab 切换 ─────────────────────
function switchWdTab(tab) {
  document.getElementById("wdTabManual").className = "tab" + (tab === "manual" ? " active" : "");
  document.getElementById("wdTabImport").className = "tab" + (tab === "import" ? " active" : "");
  document.getElementById("wdPanelManual").style.display = tab === "manual" ? "" : "none";
  document.getElementById("wdPanelImport").style.display = tab === "import" ? "" : "none";
}

function switchWdImpMode(mode) {
  document.getElementById("wdTabPaste").className = "tab2" + (mode === "paste" ? " active" : "");
  document.getElementById("wdTabFile").className = "tab2" + (mode === "file" ? " active" : "");
  document.getElementById("wdPastePanel").style.display = mode === "paste" ? "" : "none";
  document.getElementById("wdFilePanel").style.display = mode === "file" ? "" : "none";
}

// ── tokens 显示工具 ─────────────────────
function fmtUsage(u) {
  if (!u || !u.total) return "";
  return `（消耗 ${u.total} tokens：提示 ${u.prompt} / 生成 ${u.completion}）`;
}

// ── 导入 BOM 取出 (替换料机制) ──────────
function wdFileSelected() {
  const f = document.getElementById("wdBomFile").files[0];
  document.getElementById("wdFileHint").textContent = f
    ? `已选择: ${f.name} (${(f.size/1024).toFixed(1)} KB)，选好解析方式后点按钮` : "";
}

async function wdParseText() {
  const text = document.getElementById("wdBomText").value.trim();
  const statusEl = document.getElementById("wdParseStatus");
  if (!text) { statusEl.textContent = "请先粘贴 BOM 清单"; return; }
  statusEl.textContent = "AI 解析中…（批量条目可能需要几十秒）";
  const res = await api("/api/import_parse_text", {
    method: "POST", body: JSON.stringify({ text }),
  });
  if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
  await wdMatchItems(res.items, res.dropped_nc || 0, res.usage);
}

async function wdParseTextRules() {
  const text = document.getElementById("wdBomText").value.trim();
  const statusEl = document.getElementById("wdParseStatus");
  if (!text) { statusEl.textContent = "请先粘贴 BOM 清单"; return; }
  statusEl.textContent = "脚本解析中…";
  const res = await api("/api/import_parse_rules", {
    method: "POST", body: JSON.stringify({ text }),
  });
  if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
  await wdMatchItems(res.items, res.dropped_nc || 0, null);
}

let wdPendingFileItems = null;
let wdPendingFileDroppedNc = 0;
let wdPendingFileUsage = null;
let wdPendingFileStatusId = "wdFileStatus";

function openWdCopiesBar(items, droppedNc, usage, statusId = "wdFileStatus") {
  wdPendingFileItems = items;
  wdPendingFileDroppedNc = droppedNc || 0;
  wdPendingFileUsage = usage || null;
  wdPendingFileStatusId = statusId;
  document.getElementById("wdCopiesRead").textContent = `BOM 已读取：${items.length} 条`;
  document.getElementById("wdCopiesInput").value = "1";
  document.getElementById("wdCopiesBar").style.display = "flex";
}

function applyWdCopies() {
  const input = document.getElementById("wdCopiesInput");
  const copies = parseInt(input.value, 10);
  const statusEl = document.getElementById(wdPendingFileStatusId);
  if (!Number.isInteger(copies) || copies < 1) {
    statusEl.textContent = "取出几份必须是大于等于 1 的整数";
    input.focus();
    return;
  }
  if (!wdPendingFileItems || !wdPendingFileItems.length) {
    statusEl.textContent = "请先读取 BOM 文件";
    return;
  }
  const scaled = wdPendingFileItems.map((item) => {
    const copy = { ...item };
    const qty = bmParseQty(copy.qty);
    if (qty != null) copy.qty = String(qty * copies);
    return copy;
  });
  statusEl.textContent = `已按 ${copies} 份计算，正在匹配库存…`;
  wdMatchItems(scaled, wdPendingFileDroppedNc, wdPendingFileUsage, copies, wdPendingFileStatusId);
}

async function wdParseFile() {
  const f = document.getElementById("wdBomFile").files[0];
  const statusEl = document.getElementById("wdFileStatus");
  if (!f) { statusEl.textContent = "请先选择文件"; return; }
  statusEl.textContent = "AI 解析中…";
  const form = new FormData();
  form.append("file", f);
  const res = await fetch("/api/import_parse_excel", { method: "POST", body: form });
  const data = await res.json();
  if (!data.ok) { statusEl.textContent = `❌ ${data.error}`; return; }
  openWdCopiesBar(data.items, data.dropped_nc || 0, data.usage);
}

async function wdParseFileRules() {
  const f = document.getElementById("wdBomFile").files[0];
  const statusEl = document.getElementById("wdFileStatus");
  if (!f) { statusEl.textContent = "请先选择文件"; return; }
  statusEl.textContent = "脚本解析中…";
  const form = new FormData();
  form.append("file", f);
  const res = await fetch("/api/import_parse_rules", { method: "POST", body: form });
  const data = await res.json();
  if (!data.ok) { statusEl.textContent = `❌ ${data.error}`; return; }
  openWdCopiesBar(data.items, data.dropped_nc || 0, null);
}

async function wdMatchItems(items, droppedNc, usage, copies = 1, statusId = "wdMatchStatus") {
  const statusEl = document.getElementById(statusId);
  if (!items.length) { statusEl.textContent = "没有解析出元件"; return; }
  statusEl.textContent = "匹配现有库存中…";
  const m = await api("/api/withdraw/match", {
    method: "POST", body: JSON.stringify({ items }),
  });
  if (!m.ok) { statusEl.textContent = `❌ ${m.error}`; return; }
  renderWdMatch(m.results);
  document.getElementById("wdMatchResult").style.display = "";
  const ncNote = droppedNc ? `（已剔除 ${droppedNc} 条 NC/不贴装）` : "";
  const tkNote = usage ? fmtUsage(usage) : "（脚本解析，未使用 AI）";
  const copyNote = copies > 1 ? `，按 ${copies} 份计算` : "";
  statusEl.textContent =
    `✅ 匹配完成：${m.matched}/${m.total} 项有库存可取出，其余需要采购${copyNote}${ncNote}${tkNote}`;
}

function renderWdMatch(results) {
  const mBody = document.getElementById("wdMatchBody");
  const nBody = document.getElementById("wdNoStockBody");
  mBody.innerHTML = "";
  nBody.innerHTML = "";
  let matched = 0, noStock = 0;
  results.forEach((r, idx) => {
    const it = r.item;
    const savedSubcat = (r.saved_selected || {}).subcat || "";
    const need = `${escHtml(it.name)}${it.spec ? " " + escHtml(it.spec) : ""}`;
    if (!savedSubcat && !r.candidates.length) {
      noStock++;
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${need}</td><td>${escHtml(it.spec)}</td><td>${escHtml(it.package)}</td><td>${escHtml(it.qty)}</td>`;
      nBody.appendChild(tr);
      return;
    }
    matched++;
    const needQty = bmParseQty(it.qty) || 1;
    const exacts = r.candidates.filter((c) => c.match_type === "exact");
    const sims = r.candidates.filter((c) => c.match_type !== "exact");
    const availExact = exacts.reduce((s, c) => s + bmParseQty(c.qty), 0);
    const availAll = availExact + sims.reduce((s, c) => s + bmParseQty(c.qty), 0);
    let stHtml, stCls;
    if (availExact >= needQty) {
      stHtml = `✅ 充足（库存 ${availExact}）`; stCls = "bm-ok";
    } else if (availAll >= needQty) {
      stHtml = `⚠️ 可替代（精确 ${availExact}，相似合计 ${availAll}）`; stCls = "bm-warn";
    } else {
      stHtml = `⚠️ 不足（库存 ${availAll}，差 ${needQty - availAll}）`; stCls = "bm-warn";
    }
    const tr = document.createElement("tr");
    let choiceHtml = "";
    let hasExact = r.candidates.some((c) => c.match_type === "exact");
    r.candidates.forEach((c, ci) => {
      const isExact = c.match_type === "exact";
      const available = bmParseQty(c.qty);
      const canTake = available >= needQty;
      const warn = isExact ? "" : `<span class="wdm-warn">⚠️ ${escHtml(c.pkg_note || "型号/封装不同")}</span>`;
      choiceHtml += `
        <label class="wdm-choice${isExact ? "" : " wdm-similar"}${canTake ? "" : " wdm-unavailable"}">
          <input type="radio" name="wdm${idx}" value="${escHtml(c.subcat)}|||${c.row}"${(hasExact ? ci === 0 && isExact : ci === 0) && canTake ? " checked" : ""}${canTake ? "" : " disabled"}>
          <span class="wdm-info">${escHtml(c.name)} | ${escHtml(c.brand || "—")} | ${escHtml(c.spec || "—")} | 库存 ${escHtml(c.qty)}</span>
          <span class="wdm-subcat">${escHtml(c.subcat)}</span>
          ${warn}
          <input type="number" class="wdm-qty" min="1" value="${escHtml(it.qty)}" style="width:64px"${canTake ? "" : " disabled"}>
        </label>`;
    });
    tr.innerHTML = `
      <td>${need}</td>
      <td>${escHtml(it.package)}</td>
      <td>${escHtml(it.qty)}</td>
      <td>${choiceHtml}</td>
      <td class="${stCls}">${stHtml}</td>`;
    mBody.appendChild(tr);
  });
  document.getElementById("wdMatchCount").textContent =
    `有库存 ${matched} 项 / 无库存 ${noStock} 项`;
  document.getElementById("wdNoStock").style.display = noStock ? "" : "none";
}

// ── BOM 清单 (导入、匹配、保存，不直接扣数量) ───────
function renderBomMatch() {
  document.getElementById("bomMatchPage").style.display = "";
  document.getElementById("bmResult").style.display = "none";
  document.getElementById("bmStatus").textContent = "";
  document.getElementById("bmParseStatus").textContent = "";
  document.getElementById("bmFileStatus").textContent = "";
}

function switchBmMode(mode) {
  document.getElementById("bmTabPaste").classList.toggle("active", mode === "paste");
  document.getElementById("bmTabFile").classList.toggle("active", mode === "file");
  document.getElementById("bmPastePanel").style.display = mode === "paste" ? "" : "none";
  document.getElementById("bmFilePanel").style.display = mode === "file" ? "" : "none";
}

function bmFileSelected() {
  const f = document.getElementById("bmBomFile").files[0];
  document.getElementById("bmFileHint").textContent = f
    ? `已选择: ${f.name} (${(f.size/1024).toFixed(1)} KB)，选好解析方式后点按钮` : "";
}

function bmParseQty(v) {
  const n = parseInt(String(v == null ? "" : v).replace(/[^\d]/g, ""), 10);
  return isNaN(n) ? 0 : n;
}

async function bmParseText() {
  const text = document.getElementById("bmBomText").value.trim();
  const statusEl = document.getElementById("bmParseStatus");
  if (!text) { statusEl.textContent = "请先粘贴 BOM 清单"; return; }
  statusEl.textContent = "AI 解析中…（批量条目可能需要几十秒）";
  const res = await api("/api/import_parse_text", {
    method: "POST", body: JSON.stringify({ text }),
  });
  if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
  await bmMatchItems(res.items, res.dropped_nc || 0, res.usage);
}

async function bmParseTextRules() {
  const text = document.getElementById("bmBomText").value.trim();
  const statusEl = document.getElementById("bmParseStatus");
  if (!text) { statusEl.textContent = "请先粘贴 BOM 清单"; return; }
  statusEl.textContent = "脚本解析中…";
  const res = await api("/api/import_parse_rules", {
    method: "POST", body: JSON.stringify({ text }),
  });
  if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
  await bmMatchItems(res.items, res.dropped_nc || 0, null);
}

async function bmParseFile() {
  const f = document.getElementById("bmBomFile").files[0];
  const statusEl = document.getElementById("bmFileStatus");
  if (!f) { statusEl.textContent = "请先选择文件"; return; }
  statusEl.textContent = "AI 解析中…";
  const form = new FormData();
  form.append("file", f);
  const res = await fetch("/api/import_parse_excel", { method: "POST", body: form });
  const data = await res.json();
  if (!data.ok) { statusEl.textContent = `❌ ${data.error}`; return; }
  await bmMatchItems(data.items, data.dropped_nc || 0, data.usage);
}

async function bmParseFileRules() {
  const f = document.getElementById("bmBomFile").files[0];
  const statusEl = document.getElementById("bmFileStatus");
  if (!f) { statusEl.textContent = "请先选择文件"; return; }
  statusEl.textContent = "脚本解析中…";
  const form = new FormData();
  form.append("file", f);
  const res = await fetch("/api/import_parse_rules", { method: "POST", body: form });
  const data = await res.json();
  if (!data.ok) { statusEl.textContent = `❌ ${data.error}`; return; }
  await bmMatchItems(data.items, data.dropped_nc || 0, null);
}

let bmLastResults = [];
let bmLastSource = "";
let bomManageItem = null;

async function renderBomManage() {
  const page = document.getElementById("bomManagePage");
  page.style.display = "";
  document.getElementById("bomManageEditor").style.display = "none";
  const sel = document.getElementById("bomManageSel");
  const data = await api("/api/bom-lists");
  sel.innerHTML = '<option value="">— 选择 BOM 清单 —</option>';
  (data.items || []).forEach((it) => {
    const opt = document.createElement("option"); opt.value = it.id;
    opt.textContent = `${it.name}（${it.count} 项）`; sel.appendChild(opt);
  });
  document.getElementById("bomManageCount").textContent = `${(data.items || []).length} 份清单`;
}

async function loadBomManageDetail() {
  const id = document.getElementById("bomManageSel").value;
  const editor = document.getElementById("bomManageEditor");
  if (!id) { editor.style.display = "none"; bomManageItem = null; return; }
  const data = await api(`/api/bom-lists/${encodeURIComponent(id)}`);
  if (!data.ok) { document.getElementById("bomManageStatus").textContent = `❌ ${data.error}`; return; }
  bomManageItem = data.item;
  document.getElementById("bomManageTitle").textContent = `${bomManageItem.name}（${bomManageItem.items.length} 项）`;
  const body = document.getElementById("bomManageBody"); body.innerHTML = "";
  bomManageItem.items.forEach((entry, i) => {
    const req = entry.item || {}, selected = entry.selected || {}, snap = selected.snapshot || {};
    const tr = document.createElement("tr");
    tr.dataset.index = i;
    tr.innerHTML = `<td>${i + 1}</td>
      <td><input data-key="name" value="${escHtml(req.name || "")}"></td>
      <td><input data-key="brand" value="${escHtml(req.brand || "")}"></td>
      <td><input data-key="package" value="${escHtml(req.package || "")}"></td>
      <td><input data-key="qty" type="number" min="0" value="${escHtml(req.qty || "")}"></td>
      <td><input data-key="spec" value="${escHtml(req.spec || "")}"></td>
      <td>${selected.subcat ? "✅ 已匹配" : "⏳ 未匹配/待补料"}</td>
      <td>${selected.subcat ? `${escHtml(selected.subcat)} / ${escHtml(snap.name || "")}` : "—"}</td>`;
    body.appendChild(tr);
  });
  editor.style.display = "";
}

async function saveBomManage() {
  if (!bomManageItem) return;
  const name = prompt("清单名称", bomManageItem.name);
  if (name === null || !name.trim()) return;
  document.querySelectorAll("#bomManageBody tr").forEach((tr) => {
    const i = Number(tr.dataset.index), req = bomManageItem.items[i].item || {};
    tr.querySelectorAll("input[data-key]").forEach((input) => { req[input.dataset.key] = input.value; });
    bomManageItem.items[i].item = req;
  });
  bomManageItem.name = name.trim();
  const res = await api("/api/bom-lists", { method: "POST", body: JSON.stringify(bomManageItem) });
  const status = document.getElementById("bomManageStatus");
  if (!res.ok) { status.textContent = `❌ ${res.error}`; return; }
  status.textContent = `✅ 已保存「${bomManageItem.name}」的修改`;
  await renderBomManage();
  showToast("BOM 清单修改已保存");
}

async function deleteBomManage() {
  const sel = document.getElementById("bomManageSel"), id = sel.value;
  if (!id) { document.getElementById("bomManageStatus").textContent = "请先选择 BOM 清单"; return; }
  const name = sel.options[sel.selectedIndex].textContent;
  if (!confirm(`确定删除 ${name}？对应 Excel 文件也会删除。`)) return;
  const res = await api(`/api/bom-lists/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!res.ok) { document.getElementById("bomManageStatus").textContent = `❌ ${res.error}`; return; }
  bomManageItem = null;
  document.getElementById("bomManageEditor").style.display = "none";
  document.getElementById("bomManageStatus").textContent = "✅ BOM 清单已删除";
  await renderBomManage();
  loadWdBomLists();
  showToast("BOM 清单已删除");
}

function saveBomList() {
  const name = document.getElementById("bmListName").value.trim();
  const statusEl = document.getElementById("bmStatus");
  if (!name) { statusEl.textContent = "请先输入 BOM 清单名称"; return; }
  if (!bmLastResults.length) { statusEl.textContent = "没有可保存的匹配结果"; return; }
  const items = [];
  for (const [idx, r] of bmLastResults.entries()) {
    const radio = document.querySelector(`#bmTable input[name="bmc${idx}"]:checked`);
    if (!radio) {
      items.push({ item: r.item, selected: {} });
    } else {
      const [subcat, row] = radio.value.split("|||");
      items.push({ item: r.item, selected: { subcat, row: Number(row) } });
    }
  }
  api("/api/bom-lists", {
    method: "POST",
    body: JSON.stringify({ name, source: bmLastSource, items }),
  }).then((res) => {
    if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
    const missing = items.filter((x) => !x.selected.subcat).length;
    statusEl.textContent = `✅ BOM 清单「${name}」已保存${missing ? `，其中 ${missing} 项未匹配，已保留待补料` : ""}，可在取出页调用`;
    showToast("BOM 清单已保存");
    loadWdBomLists();
  });
}

async function loadWdBomLists() {
  const sel = document.getElementById("wdBomListSel");
  if (!sel) return;
  const data = await api("/api/bom-lists");
  sel.innerHTML = '<option value="">— 选择 BOM 清单 —</option>';
  (data.items || []).forEach((it) => {
    const opt = document.createElement("option");
    opt.value = it.id;
    opt.textContent = `${it.name}（${it.count} 项）`;
    sel.appendChild(opt);
  });
}

function onWdBomListChange() {
  const sel = document.getElementById("wdBomListSel");
  const hint = document.getElementById("wdBomListHint");
  hint.textContent = sel.value ? "已选择清单，填写份数后点击按份数取出。系统会重新核验实时库存。" : "保存过的 BOM 清单会绑定已确认的仓库型号，调用时只检查实时库存。";
}

async function prepareSavedBom() {
  const listId = document.getElementById("wdBomListSel").value;
  const copies = parseInt(document.getElementById("wdBomListCopies").value, 10);
  const hint = document.getElementById("wdBomListHint");
  if (!listId) { hint.textContent = "请先选择 BOM 清单"; return; }
  if (!Number.isInteger(copies) || copies < 1) { hint.textContent = "份数必须是大于等于 1 的整数"; return; }
  hint.textContent = "读取清单并检查实时库存…";
  const res = await api(`/api/bom-lists/${encodeURIComponent(listId)}/prepare`, {
    method: "POST", body: JSON.stringify({ copies }),
  });
  if (!res.ok) { hint.textContent = `❌ ${res.error}`; return; }
  renderWdMatch(res.results);
  document.getElementById("wdMatchResult").style.display = "";
  document.getElementById("wdMatchStatus").textContent = `✅ 已调用「${res.name}」，按 ${copies} 份核验实时库存`;
}

async function bmMatchItems(items, droppedNc, usage) {
  const statusEl = document.getElementById("bmStatus");
  if (!items.length) { statusEl.textContent = "没有解析出元件"; return; }
  statusEl.textContent = "匹配现有库存中…";
  const m = await api("/api/withdraw/match", {
    method: "POST", body: JSON.stringify({ items }),
  });
  if (!m.ok) { statusEl.textContent = `❌ ${m.error}`; return; }
  renderBmMatch(m.results, droppedNc, usage);
}

function renderBmMatch(results, droppedNc, usage) {
  bmLastResults = results;
  const bBody = document.getElementById("bmBody");
  const nBody = document.getElementById("bmNeedBuyBody");
  bBody.innerHTML = "";
  nBody.innerHTML = "";
  let ok = 0, sub = 0, lack = 0, miss = 0;
  const needBuy = [];

  results.forEach((r) => {
    const it = r.item;
    const need = bmParseQty(it.qty) || 1;
    const needHtml = `${escHtml(it.name)}${it.spec ? " <span style='color:#64748b'>" + escHtml(it.spec) + "</span>" : ""}`;
    const exacts = r.candidates.filter((c) => c.match_type === "exact");
    const sims = r.candidates.filter((c) => c.match_type !== "exact");
    const availExact = exacts.reduce((s, c) => s + bmParseQty(c.qty), 0);
    const availAll = availExact + sims.reduce((s, c) => s + bmParseQty(c.qty), 0);

    let status, cls;
    if (!r.candidates.length) {
      status = `❌ 缺料`; cls = "bm-miss"; miss++;
    } else if (availExact >= need) {
      status = `✅ 充足（库存 ${availExact}）`; cls = "bm-ok"; ok++;
    } else if (availAll >= need) {
      status = `⚠️ 可替代（精确 ${availExact}，相似合计 ${availAll}）`; cls = "bm-warn"; sub++;
    } else {
      status = `⚠️ 不足（库存 ${availAll}，差 ${need - availAll}）`; cls = "bm-warn"; lack++;
    }
    if (!r.candidates.length || availAll < need) {
      needBuy.push({ it, need, status, cls });
    }

    const tr = document.createElement("tr");
    let candHtml = "";
    if (!r.candidates.length) {
      candHtml = `<span style="color:#dc2626">无匹配库存</span>`;
    } else {
      r.candidates.forEach((c, ci) => {
        const isExact = c.match_type === "exact";
        const warn = isExact ? "" : ` <span class="wdm-warn">⚠️ ${escHtml(c.pkg_note || "封装不同")}</span>`;
        candHtml += `<label class="bm-cand">
          <input type="radio" name="bmc${results.indexOf(r)}" value="${escHtml(c.subcat)}|||${c.row}"${ci === 0 ? " checked" : ""}>
          <span class="bm-tag ${isExact ? "bm-tag-exact" : "bm-tag-sim"}">${isExact ? "精确" : "相似"}</span>
          <span>${escHtml(c.name)} | ${escHtml(c.brand || "—")} | ${escHtml(c.spec || "—")}</span>
          <span class="bm-stock">库存 ${escHtml(c.qty)}</span>
          <span class="bm-subcat">${escHtml(c.subcat)}</span>${warn}
        </label>`;
      });
    }
    tr.innerHTML = `
      <td>${needHtml}</td>
      <td>${escHtml(it.package)}</td>
      <td>${escHtml(it.qty)}</td>
      <td>${candHtml}</td>
      <td class="${cls}">${status}</td>`;
    bBody.appendChild(tr);
  });

  document.getElementById("bmMatchCount").textContent =
    `充足 ${ok} / 可替代 ${sub} / 不足 ${lack} / 缺料 ${miss}`;

  // 需要采购清单
  needBuy.forEach(({ it, need, status, cls }) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escHtml(it.name)}</td>
      <td>${escHtml(it.spec || "—")}</td>
      <td>${escHtml(it.package)}</td>
      <td>${escHtml(it.qty)}</td>
      <td class="${cls}">${status}</td>`;
    nBody.appendChild(tr);
  });
  document.getElementById("bmNeedBuy").style.display = needBuy.length ? "" : "none";
  document.getElementById("bmResult").style.display = "";

  const ncNote = droppedNc ? `（已剔除 ${droppedNc} 条 NC/不贴装）` : "";
  const tkNote = usage ? fmtUsage(usage) : "（脚本解析，未使用 AI）";
  document.getElementById("bmStatus").textContent =
    `✅ 匹配完成，只读检查未改动库存${ncNote}${tkNote}`;
}

async function wdConfirm() {
  const statusEl = document.getElementById("wdMatchStatus");
  const groups = {};   // subcat -> [{row, qty}]
  document.querySelectorAll("#wdMatchTable input[type=radio]:checked").forEach((radio) => {
    if (radio.disabled) return;
    const [subcat, row] = radio.value.split("|||");
    const label = radio.closest("label");
    const qtyInput = label ? label.querySelector(".wdm-qty") : null;
    const qty = qtyInput ? parseInt(qtyInput.value, 10) : 0;
    if (qty > 0) {
      if (!groups[subcat]) groups[subcat] = [];
      groups[subcat].push({ row: +row, qty });
    }
  });
  const lines = Object.values(groups).reduce((s, a) => s + a.length, 0);
  if (!lines) { statusEl.textContent = "请为要取出的元件选择库存并填写数量"; return; }
  if (!confirm(`将取出 ${lines} 种元件的指定数量，确定继续？`)) return;
  if (!await ensureGitBeforeWrite()) { statusEl.textContent = "远端未同步，已取消取出"; return; }
  statusEl.textContent = "取出中…";
  const res = await api("/api/withdraw/batch", {
    method: "POST", body: JSON.stringify({ groups }),
  });
  if (!res.ok) {
    statusEl.textContent = `❌ ${res.error}`;
    return;
  }
  statusEl.textContent = `✅ 已取出 ${res.taken} 件（${res.lines} 种物料 / ${res.subcats} 个子分类），已记为一笔操作`;
  showToast(`已取出 ${res.taken} 件`);
  document.getElementById("wdMatchResult").style.display = "none";
  loadLowStockBadge();
}

// ── 第3级: 子分类元器件表格 ────────────
async function renderSubcat(name) {
  currentSubcat = name;
  document.getElementById("detailPage").style.display = "";
  document.getElementById("searchBox").style.display = "";
  document.getElementById("btnNew").style.display = "";
  document.getElementById("btnAI").style.display = "";
  document.getElementById("btnSave").style.display = "";
  document.getElementById("btnMerge").style.display = "";
  document.getElementById("btnAddStock").style.display = "";
  document.getElementById("btnWithdrawStock").style.display = "";
  document.getElementById("searchBox").value = "";

  const data = await api(`/api/subcat?name=${encodeURIComponent(name)}`);
  currentFields = data.fields;
  currentItems = data.items;
  sortState = { key: null, dir: 1 };   // 重置排序

  document.getElementById("detailTitle").textContent = data.name;
  document.getElementById("detailCount").textContent = `${data.items.length} 条`;
  document.getElementById("detailOwners").textContent =
    data.owners.length > 1 ? `同时归属: ${data.owners.join("、")}` : "";
  document.getElementById("aiCatName").textContent = `· ${data.name}`;

  const catName = currentCatKey ? await api(`/api/category/${currentCatKey}`) : null;
  setCrumbs(`${catName ? catName.name + " / " : ""}${name}`);

  // 值类子分类 (阻容感) 默认按数值升序排列, 找值更方便; 其他分类保持录入顺序
  if (valueBaseForSubcat(name) != null) {
    sortItems("name", 1);
  } else {
    renderTable();
  }
}

function renderTable() {
  const head = document.getElementById("tableHead");
  head.innerHTML = "";
  const hr = document.createElement("tr");
  // 勾选列 (库存操作用)
  const thc = document.createElement("th");
  thc.style.width = "32px";
  thc.innerHTML = '<input type="checkbox" id="tableCheckAll" onchange="toggleTableAll(this)">';
  hr.appendChild(thc);
  currentFields.forEach((f) => {
    const th = document.createElement("th");
    th.textContent = f.label;
    // 名称/数量/封装 支持点击排序
    if (SORTABLE_KEYS.includes(f.key)) {
      th.style.cursor = "pointer";
      th.title = "点击排序";
      th.onclick = () => sortItems(f.key);
      if (sortState.key === f.key) {
        th.textContent += sortState.dir === 1 ? " ▲" : " ▼";
      }
    }
    hr.appendChild(th);
  });
  head.appendChild(hr);

  const body = document.getElementById("tableBody");
  body.innerHTML = "";
  currentItems.forEach((item, i) => {
    const tr = document.createElement("tr");
    if (item._new) tr.className = "new-row";
    const tdc = document.createElement("td");
    tdc.innerHTML = `<input type="checkbox" class="row-check" data-row="${i}">`;
    tr.appendChild(tdc);
    currentFields.forEach((f) => {
      const td = document.createElement("td");
      td.textContent = item[f.key] ?? "";
      td.contentEditable = "true";
      td.title = item[f.key] ?? "";
      td.addEventListener("input", () => {
        item[f.key] = td.textContent;
        item._dirty = true;
      });
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
}

// ── 阻容感数值排序 ──────────────────────
// 值类元件的名称是 "10K" / "4.7UF" / "104" / "4R7" / "2K2" 这类,
// 必须解析成数值比大小, 否则 "1M" 会排到 "10K" 前面。
// 注意 m(毫) 与 M(兆) 严格区分大小写, 不能 toLowerCase 查表!
const VAL_PREFIX = {
  p: 1e-12, P: 1e-12, n: 1e-9, N: 1e-9, u: 1e-6, U: 1e-6, "µ": 1e-6,
  m: 1e-3, k: 1e3, K: 1e3, M: 1e6, G: 1e9, g: 1e9,
};

function valueBaseForSubcat(name) {
  if (/电阻/.test(name || "")) return 1;          // Ω
  if (/电容/.test(name || "")) return 1e-12;      // pF (EIA 三位码基准)
  if (/电感|磁珠/.test(name || "")) return 1e-6;  // uH (EIA 三位码基准)
  return null;                                    // 芯片/二极管等非值类 → 保持字符串排序
}

function valueSortKey(raw, eiaBase) {
  let s = String(raw ?? "").trim()
    .replace(/µ/g, "u").replace(/Ω/g, "R")
    .replace(/\s*\d*[±%].*$/, "");     // 去掉 公差/百分比 后缀: "10K 1%" / "10K±5%" → "10K"
  if (!s) return null;
  // 中间字母当小数点: 4R7=4.7, 2K2=2.2k, 1M5=1.5M, 1u5=1.5u
  let m = s.match(/^(\d+)([pPnNuUmMkKgGRr])(\d)$/);
  if (m) {
    const ch = m[2];
    const f = (ch === "R" || ch === "r") ? 1 : (VAL_PREFIX[ch] ?? 1);
    return (parseFloat(m[1]) + parseFloat(m[3]) * 0.1) * f;
  }
  // 普通格式: [数字][前缀?][单位?]  →  "10K"=1e4, "4.7UF"=4.7e-6, "10R"=10
  m = s.match(/^(\d+(?:\.\d+)?)([pPnNuUmMkKgG]?)([A-Za-z]*)$/);
  if (m) {
    const num = parseFloat(m[1]);
    const pre = m[2];
    if (pre) return num * (VAL_PREFIX[pre] ?? 1);   // 原字符查表, 区分 m/M
    if (m[3]) return num;              // 无前缀带单位: "10R" → 10
    if (/^\d{3}$/.test(s)) {           // 三位纯数字 → EIA 码: 104 → 10×10^4 × 基准
      return (parseInt(s[0] + s[1])) * Math.pow(10, parseInt(s[2])) * eiaBase;
    }
    return num;                        // 纯数字: 同分类默认单位一致, 直接比
  }
  return null;                         // "1N4148" / "STM32F103" / "0805 10K" → 字符串排序
}

// ── 表格排序 (名称/数量/封装) ───────────
const SORTABLE_KEYS = ["name", "package", "qty"];
let sortState = { key: null, dir: 1 };   // dir: 1 升序, -1 降序

function sortItems(key, dirOverride) {
  if (dirOverride !== undefined) {
    sortState.key = key;
    sortState.dir = dirOverride;
  } else if (sortState.key === key) {
    sortState.dir = -sortState.dir;      // 同列再点: 切换升/降
  } else {
    sortState.key = key;
    sortState.dir = 1;
  }
  const valBase = key === "name" ? valueBaseForSubcat(currentSubcat) : null;
  currentItems.sort((a, b) => {
    const va = a[key] ?? "", vb = b[key] ?? "";
    // 空值永远排最后
    if (va === "" || va == null) return 1;
    if (vb === "" || vb == null) return -1;
    let cmp;
    if (key === "qty") {
      cmp = (parseFloat(va) || 0) - (parseFloat(vb) || 0);
    } else if (valBase != null) {
      // 阻容感: 按解析后的数值比大小; 解析失败 (型号类) 的排在被解析值后面, 相互间字符串比
      const ka = valueSortKey(va, valBase), kb = valueSortKey(vb, valBase);
      if (ka != null && kb != null) cmp = ka - kb;
      else if (ka != null) cmp = -1;
      else if (kb != null) cmp = 1;
      else cmp = String(va).localeCompare(String(vb), "zh-Hans-CN", { numeric: true });
    } else {
      cmp = String(va).localeCompare(String(vb), "zh-Hans-CN", { numeric: true });
    }
    return cmp * sortState.dir;
  });
  renderTable();
}

// ── 表格操作 ───────────────────────────
function addRow() {
  const item = {};
  currentFields.forEach((f) => (item[f.key] = ""));
  item._new = true;
  item._dirty = true;
  currentItems.push(item);
  renderTable();
  const rows = document.querySelectorAll("#tableBody tr");
  if (rows.length) rows[rows.length - 1].scrollIntoView({ block: "nearest" });
}

async function saveCategory() {
  if (!currentSubcat) return;
  const clean = currentItems.map((it) => {
    const copy = {};
    currentFields.forEach((f) => (copy[f.key] = it[f.key] ?? ""));
    return copy;
  });
  if (!await ensureGitBeforeWrite()) return;
  const res = await api("/api/save", {
    method: "POST",
    body: JSON.stringify({ name: currentSubcat, items: clean }),
  });
  if (res.ok) {
    showToast(`✅ 已保存 ${res.saved} 条 (${res.path})`);
    currentItems.forEach((it) => { delete it._dirty; delete it._new; });
    loadLowStockBadge();
  } else {
    showToast(`❌ ${res.error || "保存失败"}`);
  }
}

// ── 表格页库存操作 (增加/取出) ──────────
let stockMode = "add";

function toggleTableAll(cb) {
  document.querySelectorAll(".row-check").forEach((c) => { c.checked = cb.checked; });
}

function selectedTableRows() {
  return [...document.querySelectorAll(".row-check:checked")]
    .filter((c) => c.closest("tr").style.display !== "none")  // 跳过搜索过滤隐藏的行
    .map((c) => +c.dataset.row);
}

function openStockModal(mode) {
  stockMode = mode;
  const indices = selectedTableRows();
  if (!indices.length) { showToast("请先勾选要操作的元件行"); return; }
  document.getElementById("stockModalTitle").textContent =
    mode === "add" ? "＋ 增加库存" : "📤 取出元器件";
  document.getElementById("stockModalHint").textContent =
    `已选 ${indices.length} 行，填写的数量将应用到每一行`;
  document.getElementById("stockQty").value = "";
  document.getElementById("stockStatus").textContent = "";
  document.getElementById("stockConfirmBtn").textContent =
    mode === "add" ? "确认增加" : "确认取出";
  document.getElementById("stockModal").style.display = "flex";
  document.getElementById("stockQty").focus();
}

function closeStockModal() {
  document.getElementById("stockModal").style.display = "none";
}

async function doStockAction() {
  const qty = parseInt(document.getElementById("stockQty").value, 10);
  const statusEl = document.getElementById("stockStatus");
  if (!qty || qty <= 0) { statusEl.textContent = "请输入大于 0 的数量"; return; }
  if (currentItems.some((it) => it._dirty)) {
    statusEl.textContent = "⚠️ 有未保存的修改，请先点「保存」再操作";
    return;
  }
  statusEl.textContent = "处理中…";
  const items = selectedTableRows().map((row) => ({ row, qty }));
  if (!items.length) { statusEl.textContent = "请勾选要操作的元件行"; return; }
  if (!await ensureGitBeforeWrite()) { statusEl.textContent = "远端未同步，已取消操作"; return; }
  const url = stockMode === "add" ? "/api/addstock" : "/api/withdraw";
  const res = await api(url, {
    method: "POST", body: JSON.stringify({ name: currentSubcat, items }),
  });
  if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
  closeStockModal();
  const n = stockMode === "add" ? res.added : res.taken;
  showToast(`✅ ${stockMode === "add" ? "增加" : "取出"} ${n} 件`);
  await renderSubcat(currentSubcat);  // 刷新库存
  loadLowStockBadge();
}

// 点击遮罩关闭
document.getElementById("stockModal").addEventListener("click", (e) => {
  if (e.target.id === "stockModal") closeStockModal();
});

// ── 撤回系统 ────────────────────────────
async function openUndoModal() {
  document.getElementById("undoModal").style.display = "flex";
  document.getElementById("undoStatus").textContent = "";
  const listEl = document.getElementById("undoList");
  listEl.innerHTML = '<div class="file-hint" style="padding:20px;text-align:center">加载中…</div>';
  try {
    const d = await api("/api/undo");
    renderUndoList(d.items);
  } catch (e) {
    listEl.innerHTML = '<div class="file-hint" style="padding:20px;text-align:center">加载失败</div>';
  }
}

function renderUndoList(items) {
  const listEl = document.getElementById("undoList");
  listEl.innerHTML = "";
  if (!items.length) {
    listEl.innerHTML = '<div class="file-hint" style="padding:24px;text-align:center">暂无可以撤回的操作</div>';
    return;
  }
  items.forEach((it) => {
    const row = document.createElement("div");
    row.className = "undo-item";
    row.innerHTML = `
      <div class="undo-info">
        <span class="undo-action">${escHtml(it.action || "操作")}</span>
        <span class="undo-subcat">${escHtml(it.subcat)}</span>
        <div class="undo-time">${escHtml(it.time)}</div>
      </div>
      <button class="btn btn-dark" style="padding:4px 12px" onclick="undoAction('${escHtml(it.time)}')">↩ 撤回</button>`;
    listEl.appendChild(row);
  });
}

async function undoAction(time) {
  const statusEl = document.getElementById("undoStatus");
  if (!confirm("将恢复到该操作前的数据（该操作及其撤销记录将被移除）。\n确定撤回？")) return;
  if (!await ensureGitBeforeWrite()) { statusEl.textContent = "远端未同步，已取消撤回"; return; }
  const res = await api("/api/undo", {
    method: "POST", body: JSON.stringify({ time }),
  });
  if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
  statusEl.textContent = `✅ 已撤回「${res.action}」：${res.restored.join("、")}`;
  showToast("撤回成功");
  // 若当前正查看被撤回的子分类, 刷新表格
  if (currentSubcat && res.restored.includes(currentSubcat)) {
    await renderSubcat(currentSubcat);
  }
  loadLowStockBadge();
  await openUndoModal();   // 刷新列表 (保留弹窗)
}

function closeUndoModal() {
  document.getElementById("undoModal").style.display = "none";
}

// 点击遮罩关闭
document.getElementById("undoModal").addEventListener("click", (e) => {
  if (e.target.id === "undoModal") closeUndoModal();
});

// 合并重复行 (表格页)
async function mergeSubcat() {
  if (!currentSubcat) return;
  if (currentItems.some((it) => it._dirty)) {
    showToast("⚠️ 有未保存的修改，请先点「保存」");
    return;
  }
  if (!confirm(`将合并「${currentSubcat}」中 名称/品牌/封装/规格 完全相同的重复行，数量自动累加。\n确定继续？`)) return;
  if (!await ensureGitBeforeWrite()) return;
  const res = await api("/api/subcat/merge", {
    method: "POST", body: JSON.stringify({ name: currentSubcat }),
  });
  if (!res.ok) { showToast(`❌ ${res.error}`); return; }
  if (res.removed === 0) { showToast("没有发现重复行"); return; }
  showToast(`✅ 合并了 ${res.removed} 行重复 (${res.before} → ${res.after} 行)`);
  await renderSubcat(currentSubcat);
  loadLowStockBadge();
}

// 搜索过滤
document.getElementById("searchBox").addEventListener("input", (e) => {
  const q = e.target.value.trim().toLowerCase();
  const rows = document.querySelectorAll("#tableBody tr");
  rows.forEach((tr, i) => {
    const item = currentItems[i];
    if (!q) { tr.style.display = ""; return; }
    const hit = currentFields.some((f) =>
      String(item[f.key] ?? "").toLowerCase().includes(q));
    tr.style.display = hit ? "" : "none";
  });
});

// ── 补货提醒界面 ───────────────────────
async function renderLowStock() {
  document.getElementById("lowstockPage").style.display = "";
  const d = await api(`/api/lowstock?threshold=${LOW_THRESHOLD}`);
  document.getElementById("lowstockCount").textContent =
    d.items.length ? `共 ${d.items.length} 项需补货` : "库存充足 🎉";

  const body = document.getElementById("lowstockBody");
  body.innerHTML = "";
  if (!d.items.length) {
    body.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:40px">所有元器件库存充足</td></tr>';
    return;
  }
  d.items.forEach((it) => {
    const tr = document.createElement("tr");
    const qtyTd = document.createElement("td");
    qtyTd.innerHTML = `<span class="tag tag-out" style="font-size:13px">${it.qty}</span>`;
    const nameTd = document.createElement("td");
    nameTd.innerHTML = `<b>${it.name}</b>`;
    const subTd = document.createElement("td");
    subTd.textContent = it.subcat;
    const thrTag = document.createElement("span");
    thrTag.className = "tag tag-neutral";
    thrTag.style.fontSize = "11px";
    thrTag.textContent = `阈值 <${it.threshold}`;
    subTd.appendChild(thrTag);
    const actTd = document.createElement("td");
    const btn = document.createElement("button");
    btn.className = "btn btn-dark";
    btn.textContent = "去补货";
    btn.style.padding = "4px 14px";
    btn.onclick = () => {
      currentCatKey = it.owner;
      goSubcat(it.subcat);   // 补货 -> 表格, 返回回补货页
    };
    actTd.appendChild(btn);
    tr.append(qtyTd, nameTd, subTd, actTd);
    body.appendChild(tr);
  });
}

// ── 录入界面 ───────────────────────────
async function renderInput() {
  document.getElementById("inputPage").style.display = "";
  // 加载全部分类 (含空的, 用全量 API)
  const all = await api("/api/overview");
  // 缓存分类名映射 (批量结果表格用)
  window._catNames = {};
  all.cards.forEach((c) => (window._catNames[c.key] = c.name));
  const catSelect = document.getElementById("inputCatSelect");
  catSelect.innerHTML = "";
  all.cards.forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c.key;
    opt.textContent = c.name;
    catSelect.appendChild(opt);
  });
  catSelect.onchange = loadInputSubcats;
  await loadInputSubcats();
  initOcrWorkers();
  document.getElementById("inputStatus").textContent = "";
}

async function loadInputSubcats() {
  const key = document.getElementById("inputCatSelect").value;
  if (!key) return;
  const subSelect = document.getElementById("inputSubcatSelect");
  const allSubs = await api(`/api/subcats_all?key=${key}`);
  subSelect.innerHTML = "";
  (allSubs.subcats || []).forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = s;
    subSelect.appendChild(opt);
  });
}

async function openSubcatFromInput() {
  const name = document.getElementById("inputSubcatSelect").value;
  if (!name) return;
  currentCatKey = document.getElementById("inputCatSelect").value;
  goSubcat(name);   // 录入 -> 表格, 返回回录入页
}

async function quickAIFill() {
  const name = document.getElementById("inputSubcatSelect").value;
  const desc = document.getElementById("inputDesc").value.trim();
  const statusEl = document.getElementById("inputStatus");
  if (!name) { statusEl.textContent = "请先选择子分类"; return; }
  if (!desc) { statusEl.textContent = "请输入元器件描述"; return; }
  statusEl.textContent = "AI 解析中…";
  const res = await api("/api/ai_fill", {
    method: "POST",
    body: JSON.stringify({ subcat: name, desc }),
  });
  if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
  currentCatKey = document.getElementById("inputCatSelect").value;
  goSubcat(name);   // 跳表格
  currentItems.push({ ...res.item, _new: true, _dirty: true });
  renderTable();
  statusEl.textContent = "✅ 已填入，请核对后点「保存」";
  document.getElementById("detailCount").textContent = `${currentItems.length} 条`;
}

// ── 批量导入 ───────────────────────────
let batchItems = [];   // 解析结果 [{name,brand,package,qty,spec,cat_key,subcat,_checked}]

function switchInputTab(mode) {
  document.getElementById("tabSingle").className = mode === "single" ? "tab active" : "tab";
  document.getElementById("tabBatch").className = mode === "batch" ? "tab active" : "tab";
  document.getElementById("tabOcr").className = mode === "ocr" ? "tab active" : "tab";
  document.getElementById("inputSinglePanel").style.display = mode === "single" ? "" : "none";
  document.getElementById("inputBatchPanel").style.display = mode === "batch" ? "" : "none";
  document.getElementById("inputOcrPanel").style.display = mode === "ocr" ? "" : "none";
}

// ── 图片识别 (OCR) ──────────────────────
let ocrItems = [];

async function ocrUpload() {
  const files = [...document.getElementById("ocrFile").files];
  const statusEl = document.getElementById("ocrStatus");
  const workersEl = document.getElementById("ocrWorkers");
  if (!files.length) return;
  const workers = workersEl ? parseInt(workersEl.value, 10) || 0 : 0;
  localStorage.setItem("ocrWorkers", String(workers));
  const workerLabel = workers ? `${workers}线程` : "自动线程";
  statusEl.textContent = `识别中… 共 ${files.length} 张（${workerLabel}，首次加载模型约几秒）`;

  // 一次提交整批图片, 避免多张图片逐张 HTTP 往返。
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  form.append("workers", String(workers));
  let data;
  try {
    const res = await fetch("/api/ocr/batch", { method: "POST", body: form });
    data = await res.json();
    if (!data.ok) throw new Error(data.error || "OCR 失败");
  } catch (e) {
    statusEl.textContent = `❌ 图片识别失败: ${e.message}`;
    return;
  }

  const imageGroups = data.groups || [];
  const allLines = imageGroups.flat();
  if (!allLines.length) { statusEl.textContent = "❌ 没有识别出文字"; return; }
  // 带图片边界标记, 防止整理时把一张图的内容拆成多份
  const rawText = imageGroups
    .map((g, i) => (g.length ? `【图${i + 1}】\n${g.join("\n")}` : `【图${i + 1}】(无文字)`))
    .join("\n");
  document.getElementById("ocrText").value = allLines.join("\n");
  const actualWorkers = data.workers || workers;
  statusEl.textContent = `✅ ${actualWorkers}线程识别 ${allLines.length} 行（${files.length} 张图），正在整理…`;

  await ocrParseText(rawText, `✅ ${actualWorkers}线程识别 ${files.length} 张图，正在结构化解析…`);
}

function initOcrWorkers() {
  const select = document.getElementById("ocrWorkers");
  if (!select) return;
  const saved = localStorage.getItem("ocrWorkers");
  if (["0", "1", "2", "4", "6", "8"].includes(saved)) {
    select.value = saved;
  }
}

// ── 摄像头拍照识别 ──────────────────────
async function loadCameraList(force = false) {
  const sel = document.getElementById("cameraSelect");
  const hint = document.getElementById("cameraHint");
  if (!sel) return;
  try {
    const res = await api(`/api/camera/list${force ? "?force=1" : ""}`, { method: "GET" });
    const devs = (res.devices || []).filter(d => d.ok);
    sel.innerHTML = "";
    if (!devs.length) {
      sel.innerHTML = '<option value="-1">未检测到摄像头</option>';
      hint.textContent = "未检测到：请确认摄像头已插入/开启，或关闭占用摄像头的程序后点 🔄 重新检测";
      return;
    }
    const last = localStorage.getItem("camDevice");
    devs.forEach(d => {
      const opt = document.createElement("option");
      opt.value = d.index;
      const nm = (d.name || "").trim();
      opt.textContent = nm ? `摄像头 ${d.index} · ${nm}` : `摄像头 ${d.index}`;
      sel.appendChild(opt);
    });
    // 优先选中上次使用过的摄像头, 否则第一个可用
    const remember = devs.find(d => String(d.index) === last);
    sel.value = remember ? String(remember.index) : String(devs[0].index);
    hint.textContent = devs.length > 1
      ? `共 ${devs.length} 个可用：${devs.map(d => `${d.index}${(d.name || "").trim() ? "·" + (d.name || "").trim() : ""}`).join("、")}`
      : ((devs[0].name || "").trim() ? `已检测到：${(devs[0].name || "").trim()}` : "");
  } catch (e) {
    hint.textContent = "设备列表加载失败";
  }
}

async function cameraCapture() {
  const statusEl = document.getElementById("ocrStatus");
  const sel = document.getElementById("cameraSelect");
  const device = sel ? parseInt(sel.value) : 1;
  if (isNaN(device) || device < 0) { statusEl.textContent = "❌ 未选择可用摄像头"; return; }
  localStorage.setItem("camDevice", String(device));
  statusEl.textContent = `正在打开摄像头 ${device}…（弹出窗口后：空格=拍照，回车=结束）`;
  try {
    const res = await api("/api/camera/capture", {
      method: "POST", body: JSON.stringify({ device }),
    });
    if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
    const groups = res.groups || [];
    const warn = res.warn_light ? ` ⚠️${res.warn_light}` : "";
    if (!groups.length) { statusEl.textContent = "❌ 没有识别到文字" + warn; return; }
    const allLines = groups.flat();
    // 带图片边界标记整理
    const rawText = groups
      .map((g, i) => (g.length ? `【图${i + 1}】\n${g.join("\n")}` : `【图${i + 1}】(无文字)`))
      .join("\n");
    document.getElementById("ocrText").value = allLines.join("\n");
    await ocrParseText(rawText, `✅ 拍摄 ${res.n} 张，识别 ${allLines.length} 行，正在结构化解析…${warn}`);
  } catch (e) {
    statusEl.textContent = `❌ 摄像头失败: ${e.message}`;
  }
}

async function ocrParse() {
  const text = document.getElementById("ocrText").value.trim();
  const statusEl = document.getElementById("ocrStatus");
  if (!text) { statusEl.textContent = "请先上传图片识别文字（或手动输入）"; return; }
  await ocrParseText(text, "AI 解析中…");
}

async function ocrParseText(text, progressText) {
  const statusEl = document.getElementById("ocrStatus");
  document.getElementById("ocrText").value = text;
  statusEl.textContent = progressText || "AI 解析中…";
  const res = await api("/api/ocr/parse_text", {
    method: "POST", body: JSON.stringify({ text }),
  });
  if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
  ocrItems = res.items.map((it) => ({ ...it, _checked: true }));
  document.getElementById("ocrResult").style.display = "";
  document.getElementById("ocrResultCount").textContent = `${ocrItems.length} 条`;
  renderOcrResult();
  const ncNote = res.dropped_nc ? `（已剔除 ${res.dropped_nc} 条 NC/不贴装）` : "";
  const tkNote = fmtUsage(res.usage);
  statusEl.textContent = `✅ 解析完成 ${ocrItems.length} 条${ncNote}${tkNote}，请核对后确认写入`;
}

function renderOcrResult() {
  const body = document.getElementById("ocrResultBody");
  body.innerHTML = "";
  const editableFields = ["name", "brand", "package", "qty", "spec"];
  ocrItems.forEach((it, i) => {
    const tr = document.createElement("tr");
    if (!it.cat_key) tr.style.background = "#fef3c7";  // 未识别分类标黄
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "ocr-check";
    checkbox.checked = it._checked;
    checkbox.onchange = () => { it._checked = checkbox.checked; };
    const checkCell = document.createElement("td");
    checkCell.appendChild(checkbox);
    tr.appendChild(checkCell);

    editableFields.forEach((field) => {
      const cell = document.createElement("td");
      cell.contentEditable = "true";
      cell.textContent = it[field] || "";
      cell.title = "点击修改";
      cell.oninput = () => { it[field] = cell.textContent.trim(); };
      tr.appendChild(cell);
    });

    const categoryCell = document.createElement("td");
    categoryCell.textContent = it.cat_key || "⚠️ 未识别";
    categoryCell.title = "分类可在写入后从未分类区调整";
    const subcategoryCell = document.createElement("td");
    subcategoryCell.textContent = it.subcat || "";
    subcategoryCell.title = "分类可在写入后从未分类区调整";
    tr.append(categoryCell, subcategoryCell);
    body.appendChild(tr);
  });
}

function toggleOcrAll(cb) {
  document.querySelectorAll(".ocr-check").forEach((c) => {
    c.checked = cb.checked;
    ocrItems[+c.dataset.i]._checked = cb.checked;
  });
}

async function ocrCommit() {
  const sel = ocrItems.filter((it) => it._checked);
  const statusEl = document.getElementById("ocrCommitStatus");
  if (!sel.length) { statusEl.textContent = "没有勾选任何条目"; return; }
  if (!await ensureGitBeforeWrite()) { statusEl.textContent = "远端未同步，已取消写入"; return; }
  statusEl.textContent = "写入中…";
  const res = await api("/api/import_commit", {
    method: "POST", body: JSON.stringify({ items: sel }),
  });
  if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
  statusEl.textContent = `✅ 已写入 ${res.total} 条：` +
    Object.entries(res.result).map(([k, v]) => `${k}×${v}`).join("、");
  loadLowStockBadge();
  setTimeout(() => { document.getElementById("ocrResult").style.display = "none"; }, 6000);
}

function switchBatchMode(mode) {
  document.getElementById("tabPaste").className = mode === "paste" ? "tab2 active" : "tab2";
  document.getElementById("tabFile").className = mode === "file" ? "tab2 active" : "tab2";
  document.getElementById("batchPastePanel").style.display = mode === "paste" ? "" : "none";
  document.getElementById("batchFilePanel").style.display = mode === "file" ? "" : "none";
}

function batchFileSelected() {
  const f = document.getElementById("batchFile").files[0];
  if (!f) return;
  document.getElementById("batchFileHint").textContent = `已选择: ${f.name} (${(f.size/1024).toFixed(1)} KB)`;
}

async function batchParseText() {
  const text = document.getElementById("batchText").value.trim();
  const statusEl = document.getElementById("batchPasteStatus");
  if (!text) { statusEl.textContent = "请先粘贴元器件清单"; return; }
  statusEl.textContent = "AI 解析中…（批量条目可能需要几十秒）";
  const res = await api("/api/import_parse_text", {
    method: "POST", body: JSON.stringify({ text }),
  });
  if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
  batchItems = res.items.map((it) => ({ ...it, _checked: true }));
  const ncNote = res.dropped_nc ? `（已剔除 ${res.dropped_nc} 条 NC/不贴装）` : "";
  const tkNote = fmtUsage(res.usage);
  statusEl.textContent = `✅ 解析完成 ${res.items.length} 条${ncNote}${tkNote}，请核对后确认写入`;
  renderBatchResult();
}

async function batchParseTextRules() {
  const text = document.getElementById("batchText").value.trim();
  const statusEl = document.getElementById("batchPasteStatus");
  if (!text) { statusEl.textContent = "请先粘贴元器件清单"; return; }
  statusEl.textContent = "脚本解析中…";
  const res = await api("/api/import_parse_rules", {
    method: "POST", body: JSON.stringify({ text }),
  });
  if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
  batchItems = res.items.map((it) => ({ ...it, _checked: true }));
  const ncNote = res.dropped_nc ? `（已剔除 ${res.dropped_nc} 条 NC/不贴装）` : "";
  statusEl.textContent = `✅ 脚本解析完成 ${res.items.length} 条${ncNote}（未使用 AI），请核对后确认写入`;
  renderBatchResult();
}

async function batchParseFile() {
  const f = document.getElementById("batchFile").files[0];
  const statusEl = document.getElementById("batchFileStatus");
  if (!f) { statusEl.textContent = "请先选择文件"; return; }
  statusEl.textContent = "AI 解析中…（Excel 列识别 + 逐行解析）";
  const form = new FormData();
  form.append("file", f);
  const res = await fetch("/api/import_parse_excel", { method: "POST", body: form });
  const data = await res.json();
  if (!data.ok) { statusEl.textContent = `❌ ${data.error}`; return; }
  batchItems = data.items.map((it) => ({ ...it, _checked: true }));
  const ncNote = data.dropped_nc ? `（已剔除 ${data.dropped_nc} 条 NC/不贴装）` : "";
  const tkNote = fmtUsage(data.usage);
  statusEl.textContent = `✅ ${data.filename} 解析完成 ${data.items.length} 条${ncNote}${tkNote}，请核对后确认写入`;
  renderBatchResult();
}

async function batchParseFileRules() {
  const f = document.getElementById("batchFile").files[0];
  const statusEl = document.getElementById("batchFileStatus");
  if (!f) { statusEl.textContent = "请先选择文件"; return; }
  statusEl.textContent = "脚本解析中…";
  const form = new FormData();
  form.append("file", f);
  const res = await fetch("/api/import_parse_rules", { method: "POST", body: form });
  const data = await res.json();
  if (!data.ok) { statusEl.textContent = `❌ ${data.error}`; return; }
  batchItems = data.items.map((it) => ({ ...it, _checked: true }));
  const ncNote = data.dropped_nc ? `（已剔除 ${data.dropped_nc} 条 NC/不贴装）` : "";
  statusEl.textContent = `✅ ${data.filename} 脚本解析完成 ${data.items.length} 条${ncNote}（未使用 AI），请核对后确认写入`;
  renderBatchResult();
}

function renderBatchResult() {
  const box = document.getElementById("batchResult");
  box.style.display = "";
  document.getElementById("batchResultCount").textContent = `${batchItems.length} 条`;
  const body = document.getElementById("batchResultBody");
  body.innerHTML = "";
  batchItems.forEach((it, i) => {
    const tr = document.createElement("tr");
    if (!it.cat_key) tr.style.background = "#fef3c7";  // 未识别分类标黄
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = it._checked;
    cb.onchange = () => { it._checked = cb.checked; };
    const tdCb = document.createElement("td");
    tdCb.appendChild(cb);
    const catName = it.cat_key ? (window._catNames && window._catNames[it.cat_key]) || it.cat_key : "⚠️ 未识别";
    const cells = [
      it.name, it.brand, it.package, it.qty, it.spec,
      catName, it.subcat || "—",
    ].map((v) => {
      const td = document.createElement("td");
      td.textContent = v || "";
      td.title = v || "";
      return td;
    });
    tr.append(tdCb, ...cells);
    body.appendChild(tr);
  });
}

function toggleBatchAll(cb) {
  batchItems.forEach((it) => (it._checked = cb.checked));
  document.querySelectorAll("#batchResultBody input[type=checkbox]").forEach((c) => (c.checked = cb.checked));
}

async function batchCommit() {
  const sel = batchItems.filter((it) => it._checked);
  const statusEl = document.getElementById("batchCommitStatus");
  if (!sel.length) { statusEl.textContent = "没有勾选任何条目"; return; }
  if (!await ensureGitBeforeWrite()) { statusEl.textContent = "远端未同步，已取消写入"; return; }
  statusEl.textContent = "写入中…";
  const res = await api("/api/import_commit", {
    method: "POST", body: JSON.stringify({ items: sel }),
  });
  if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
  statusEl.textContent = `✅ 已写入 ${res.total} 条：` +
    Object.entries(res.result).map(([k, v]) => `${k}×${v}`).join("、");
  loadLowStockBadge();
  // 清空输入, 3 秒后隐藏结果区
  document.getElementById("batchText").value = "";
  document.getElementById("batchFile").value = "";
  document.getElementById("batchFileHint").textContent = "支持 BOM 表（位号/型号/规格/数量/品牌/封装 等任意表头），AI 自动识别列含义";
  setTimeout(() => { document.getElementById("batchResult").style.display = "none"; }, 6000);
}

// ── AI 填入弹窗 (表格页内) ─────────────
function openAIModal() {
  document.getElementById("aiModal").style.display = "flex";
  document.getElementById("aiInput").value = "";
  document.getElementById("aiStatus").textContent = "";
  document.getElementById("aiInput").focus();
}
function closeAIModal() {
  document.getElementById("aiModal").style.display = "none";
}

async function aiFill() {
  const desc = document.getElementById("aiInput").value.trim();
  if (!desc) return;
  const statusEl = document.getElementById("aiStatus");
  const btn = document.getElementById("aiSubmitBtn");
  btn.disabled = true;
  statusEl.textContent = "AI 解析中…";

  const res = await api("/api/ai_fill", {
    method: "POST",
    body: JSON.stringify({ subcat: currentSubcat, desc }),
  });
  btn.disabled = false;

  if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
  const item = res.item;
  item._new = true;
  item._dirty = true;
  currentItems.push(item);
  renderTable();
  const filled = Object.keys(item).filter((k) => item[k]).length;
  statusEl.textContent = `✅ 已填入 ${filled} 个字段，请核对后点「保存」`;
  document.getElementById("detailCount").textContent = `${currentItems.length} 条`;
}

document.getElementById("aiInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); aiFill(); }
});
document.getElementById("aiModal").addEventListener("click", (e) => {
  if (e.target.id === "aiModal") closeAIModal();
});

// ── 设置 (数据路径 / AI / 界面) ────────
const THEMES = {
  "light-blue": ["#e0eaff", "#2563eb", "浅蓝"],
  "dark":       ["#0f172a", "#1e293b", "深色"],
  "green":      ["#dcfce7", "#0f9d58", "墨绿"],
  "orange":     ["#fef3c7", "#ea7a2f", "暖橙"],
  "purple":     ["#f3e8ff", "#7c3aed", "紫色"],
};

let currentSettings = null;
let currentTheme = "light-blue";
/* 背景图预览状态: 上传/滑轨只改这里, 点"保存背景设置"才写盘 */
const bgState = { background: "", brightness: 100, opacity: 100, cardOpacity: 100, fill: "cover", fontSize: 100, darkStrength: 72, fontFamily: "system" };

function loadBgState(s) {
  bgState.background = s.background || "";
  bgState.brightness = s.bg_brightness ?? 100;
  bgState.opacity = s.bg_opacity ?? 100;
  bgState.cardOpacity = s.card_opacity ?? 100;
  bgState.fill = s.bg_fill || "cover";
  bgState.fontSize = s.font_size ?? 100;
  bgState.darkStrength = s.dark_strength ?? 72;
  bgState.fontFamily = s.font_family || "system";
}

/* hex 色 (#fff / #ffffff) → rgba (卡片透明度用, 不依赖 color-mix) */
function hexToRgba(hex, alpha) {
  hex = (hex || "#ffffff").replace("#", "").trim();
  if (hex.length === 3) hex = hex.split("").map(c => c + c).join("");
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  if ([r, g, b].some(Number.isNaN)) return `rgba(255,255,255,${alpha})`;
  return `rgba(${r},${g},${b},${alpha})`;
}

function applyAppearance() {
  const scale = bgState.fontSize / 100;
  document.documentElement.style.setProperty("--app-font-scale", String(scale));
  document.body.style.fontFamily = { system: 'Inter,"Segoe UI","Microsoft YaHei",sans-serif', microsoft: '"Microsoft YaHei",sans-serif', segoe: '"Segoe UI",sans-serif', mono: 'Consolas,"Courier New",monospace' }[bgState.fontFamily] || 'Inter,"Segoe UI","Microsoft YaHei",sans-serif';
  document.body.style.setProperty("--workspace-overlay-alpha", `${bgState.darkStrength / 100}`);
  document.body.classList.toggle("appearance-dark", currentTheme === "dark");
}
function onAppearanceTune() {
  bgState.fontSize = +document.getElementById("fontSizeRange").value;
  bgState.darkStrength = +document.getElementById("darkStrengthRange").value;
  bgState.fontFamily = document.getElementById("fontFamilySel").value;
  document.getElementById("fontSizeVal").textContent = bgState.fontSize + "%";
  document.getElementById("darkStrengthVal").textContent = bgState.darkStrength + "%";
  applyAppearance(); applyTheme(currentTheme);
}


function applyBgFill() {
  const size = { cover: "cover", contain: "contain", stretch: "100% 100%", repeat: "auto", original: "auto" }[bgState.fill] || "cover";
  const repeat = bgState.fill === "repeat" ? "repeat" : "no-repeat";
  const pos = "center center";
  for (const id of ["bgLayer", "bgModalLayer"]) {
    const el = document.getElementById(id);
    if (!el) continue;
    el.style.backgroundSize = size;
    el.style.backgroundRepeat = repeat;
    el.style.backgroundPosition = pos;
  }
  const sel = document.getElementById("bgFillSel");
  if (sel) sel.value = bgState.fill;
}

/* 按卡片透明度把 --card-bg 覆盖为半透明 (跟随当前主题的 --card 色) */
function applyCardOpacity() {
  if (!bgState.background) return;
  const cardColor = getComputedStyle(document.body).getPropertyValue("--card").trim();
  document.body.style.setProperty("--card-bg", hexToRgba(cardColor, bgState.cardOpacity / 100));
}

function applyTheme(theme) {
  currentTheme = theme || "light-blue";
  document.body.setAttribute("data-theme", currentTheme);
  const layer = document.getElementById("bgLayer");
  const modalLayer = document.getElementById("bgModalLayer");
  if (bgState.background) {
    document.body.classList.add("has-bg");
    layer.style.backgroundImage = `url('/data/${bgState.background}')`;
    layer.style.filter = `brightness(${bgState.brightness}%)`;
    layer.style.opacity = bgState.opacity / 100;
    if (modalLayer) {
      modalLayer.style.backgroundImage = layer.style.backgroundImage;
      modalLayer.style.filter = layer.style.filter;
      modalLayer.style.opacity = layer.style.opacity;
    }
  } else {
    document.body.classList.remove("has-bg");
    layer.style.backgroundImage = "";
    layer.style.filter = "";
    layer.style.opacity = "";
    if (modalLayer) {
      modalLayer.style.backgroundImage = "";
      modalLayer.style.filter = "";
      modalLayer.style.opacity = "";
    }
  }
  applyBgFill();
  applyCardOpacity();
  applyAppearance();
  syncBgPreview();
}

/* 设置弹窗里的背景图预览 (无背景图时隐藏) */
function syncBgPreview() {
  const wrap = document.getElementById("bgPreviewWrap");
  const tune = document.getElementById("bgTune");
  const saveBtn = document.getElementById("btnSaveBg");
  if (!bgState.background) {
    wrap.style.display = "none";
    tune.style.display = "none";
    saveBtn.style.display = "none";
    return;
  }
  wrap.style.display = "";
  tune.style.display = "";
  saveBtn.style.display = "";
  const img = document.getElementById("bgPreview");
  img.src = `/data/${bgState.background}?t=${Date.now()}`;
  img.style.filter = `brightness(${bgState.brightness}%)`;
  img.style.opacity = bgState.opacity / 100;
  applyBgFill();
}

/* 放大预览弹窗: 打开时同步当前效果 */
function openBgPreviewModal() {
  if (!bgState.background) return;
  syncBgPreviewModal();
  document.getElementById("bgPreviewModal").style.display = "flex";
}

function closeBgPreviewModal() {
  document.getElementById("bgPreviewModal").style.display = "none";
}

function syncBgPreviewModal() {
  const layer = document.getElementById("bgModalLayer");
  if (!layer) return;
  layer.style.backgroundImage = `url('/data/${bgState.background}')`;
  layer.style.filter = `brightness(${bgState.brightness}%)`;
  layer.style.opacity = bgState.opacity / 100;
  applyBgFill();
  const fillNames = { cover: "铺满(裁剪)", contain: "完整显示(留边)", stretch: "拉伸填满", repeat: "平铺", original: "原始尺寸" };
  const tip = document.getElementById("bgModalTip");
  if (tip) tip.textContent =
    `图片: 亮度 ${bgState.brightness}% · 透明度 ${bgState.opacity}% · 填充 ${fillNames[bgState.fill] || bgState.fill} · 卡片透明度 ${bgState.cardOpacity}%`;
}

/* 滑轨实时预览 (不写盘) */
function onBgTune() {
  bgState.brightness = +document.getElementById("bgBrightness").value;
  bgState.opacity = +document.getElementById("bgOpacity").value;
  bgState.cardOpacity = +document.getElementById("cardOpacity").value;
  const sel = document.getElementById("bgFillSel");
  if (sel) bgState.fill = sel.value;
  document.getElementById("bgBrightnessVal").textContent = bgState.brightness + "%";
  document.getElementById("bgOpacityVal").textContent = bgState.opacity + "%";
  document.getElementById("cardOpacityVal").textContent = bgState.cardOpacity + "%";
  const layer = document.getElementById("bgLayer");
  layer.style.filter = `brightness(${bgState.brightness}%)`;
  layer.style.opacity = bgState.opacity / 100;
  applyBgFill();
  applyCardOpacity();
  const img = document.getElementById("bgPreview");
  if (img.src) {
    img.style.filter = `brightness(${bgState.brightness}%)`;
    img.style.opacity = bgState.opacity / 100;
  }
  syncBgPreviewModal();
}

function setSlider(id, val, valId) {
  val = val ?? 100;
  document.getElementById(id).value = val;
  document.getElementById(valId).textContent = val + "%";
}

async function openAIConfig() {
  const s = await api("/api/settings");
  currentSettings = s;
  loadBgState(s);
  applyTheme(s.theme);

  // 数据路径 Tab
  document.getElementById("setDataDir").value = s.data_dir || "";
  document.getElementById("setDataDirHint").textContent = s.resolved_data_dir
    ? `当前实际使用: ${s.resolved_data_dir}` : "";
  document.getElementById("setPathStatus").textContent = "";

  // AI Tab
  document.getElementById("aiCfgProvider").value = s.ai.provider || "online";
  switchAIProvider();
  document.getElementById("aiCfgUrl").value = s.ai.base_url || "";
  document.getElementById("aiCfgKey").value = "";
  document.getElementById("aiCfgModel").value = s.ai.model || "";
  document.getElementById("aiCfgStatus").textContent = (s.ai.provider === "ollama")
    ? "💻 本地离线模式：无需 API Key，数据不出本机"
    : (s.ai.configured
      ? `✅ 已配置 (${s.ai.api_key_masked})，留空 Key 保存则保持不变`
      : "⚠️ 尚未配置，AI 功能不可用");
  document.getElementById("aiCfgTestResult").textContent = "";
  if (s.ai.provider === "ollama") loadOllamaModels();

  // 界面 Tab
  renderThemeGrid(s.theme);
  setSlider("bgBrightness", bgState.brightness, "bgBrightnessVal");
  setSlider("bgOpacity", bgState.opacity, "bgOpacityVal");
  setSlider("cardOpacity", bgState.cardOpacity, "cardOpacityVal");
  setSlider("fontSizeRange", bgState.fontSize, "fontSizeVal");
  setSlider("darkStrengthRange", bgState.darkStrength, "darkStrengthVal");
  document.getElementById("fontFamilySel").value = bgState.fontFamily;
  applyAppearance();
  document.getElementById("setUIStatus").textContent = s.background
    ? `当前背景: ${s.background}` : "当前为纯色背景";

  // 线上同步 Tab
  document.getElementById("syncProviderSel").value = s.sync_provider === "git" ? "git" : "gitee";
  const prov = s.sync_provider === "git" ? "git" : "gitee";
  const g = s[`${prov}_sync`] || {};
  document.getElementById("gitCfgEnabled").checked = !!g.enabled;
  document.getElementById("gitCfgUsername").value = g.username || "";
  document.getElementById("gitCfgRemote").value = g.remote_url || "";
  document.getElementById("gitCfgLocal").value = g.local_dir || "";
  document.getElementById("gitCfgBranch").value = g.branch || "main";
  document.getElementById("gitCfgEvents").value = g.events_dir || "events";
  document.getElementById("gitCfgStatus").textContent = g.configured
    ? `✅ 已填写 ${s.sync_provider === "gitee" ? "Gitee" : "GitHub"} 同步配置`
    : `⚠️ 尚未配置当前平台`;

  const ge = s.gitee_sync || {};
  document.getElementById("giteeCfgEnabled").checked = !!ge.enabled;
  document.getElementById("giteeCfgUsername").value = ge.username || "";
  document.getElementById("giteeCfgRemote").value = ge.remote_url || "";
  document.getElementById("giteeCfgLocal").value = ge.local_dir || "";
  document.getElementById("giteeCfgBranch").value = ge.branch || "main";
  document.getElementById("giteeCfgEvents").value = ge.events_dir || "events";
  document.getElementById("giteeCfgStatus").textContent = ge.configured
    ? "✅ 已填写 Gitee 同步配置"
    : "⚠️ 尚未配置 Gitee 同步";

  // 数据管理 Tab (数据量统计)
  document.getElementById("setDataStatus").textContent = "";
  loadDataStat();
  fillDelCatSel();

  switchSetTab("path");
  document.getElementById("aiConfigModal").style.display = "flex";
}

function closeAIConfig() {
  document.getElementById("aiConfigModal").style.display = "none";
}

function switchSetTab(tab) {
  const map = { path: "setTabPath", ai: "setTabAI", ui: "setTabUI", data: "setTabData", git: "setTabGit" };
  for (const [k, id] of Object.entries(map)) {
    document.getElementById(id).className = "tab2" + (k === tab ? " active" : "");
  }
  document.getElementById("setPanelPath").style.display = tab === "path" ? "" : "none";
  document.getElementById("setPanelAI").style.display = tab === "ai" ? "" : "none";
  document.getElementById("setPanelUI").style.display = tab === "ui" ? "" : "none";
  document.getElementById("setPanelData").style.display = tab === "data" ? "" : "none";
  document.getElementById("setPanelGit").style.display = tab === "git" ? "" : "none";
  if (tab === "data") loadDataStat();
}

// ── Git 增量同步实验 ───────────────────
function gitConfigPayload() {
  return {
    sync_provider: "git",
    git_sync: {
      enabled: document.getElementById("gitCfgEnabled").checked,
      username: document.getElementById("gitCfgUsername").value.trim(),
      remote_url: document.getElementById("gitCfgRemote").value.trim(),
      local_dir: document.getElementById("gitCfgLocal").value.trim(),
      branch: document.getElementById("gitCfgBranch").value.trim() || "main",
      events_dir: document.getElementById("gitCfgEvents").value.trim() || "events",
    },
  };
}

async function saveGitConfig() {
  const status = document.getElementById("gitCfgStatus");
  try {
    const s = await api("/api/settings", {
      method: "POST", body: JSON.stringify(gitConfigPayload()),
    });
    currentSettings = s;
    const saved = s.git_sync || {};
    status.textContent = saved.configured
      ? "✅ GitHub 配置已保存，当前同步平台已切换为 GitHub"
      : "⚠️ 已保存，但仓库地址或本地目录为空";
    document.getElementById("syncProviderSel").value = "git";
    showToast("GitHub 配置已保存并设为当前平台");
  } catch (e) {
    status.textContent = `❌ 保存失败: ${e.message}`;
  }
}

function giteeConfigPayload() {
  return {
    sync_provider: "gitee",
    gitee_sync: {
      enabled: document.getElementById("giteeCfgEnabled").checked,
      username: document.getElementById("giteeCfgUsername").value.trim(),
      remote_url: document.getElementById("giteeCfgRemote").value.trim(),
      local_dir: document.getElementById("giteeCfgLocal").value.trim(),
      branch: document.getElementById("giteeCfgBranch").value.trim() || "main",
      events_dir: document.getElementById("giteeCfgEvents").value.trim() || "events",
    },
  };
}

async function saveGiteeConfig() {
  const status = document.getElementById("giteeCfgStatus");
  try {
    const s = await api("/api/settings", {
      method: "POST", body: JSON.stringify(giteeConfigPayload()),
    });
    currentSettings = s;
    const saved = s.gitee_sync || {};
    status.textContent = saved.configured
      ? "✅ Gitee 配置已保存，当前同步平台已切换为 Gitee"
      : "⚠️ 已保存，但仓库地址或本地目录为空";
    document.getElementById("syncProviderSel").value = "gitee";
    showToast("Gitee 配置已保存并设为当前平台");
  } catch (e) {
    status.textContent = `❌ 保存失败: ${e.message}`;
  }
}

async function saveSyncProvider() {
  const v = document.getElementById("syncProviderSel").value;
  try {
    const s = await api("/api/settings", {
      method: "POST", body: JSON.stringify({ sync_provider: v }),
    });
    currentSettings = s;
    await openAIConfig();
    switchSetTab("git");
    showToast(`线上同步平台已切换为 ${v === "gitee" ? "Gitee" : "GitHub"}`);
  } catch (e) {
    showToast(`切换失败: ${e.message}`);
  }
}

async function inspectGitConfig() {
  const result = document.getElementById("gitCfgStatus");
  result.textContent = "检查中…";
  try {
    const r = await api("/api/git-sync/inspect", { method: "POST" });
    result.textContent = r.ok ? `✅ ${r.message}` : `❌ ${r.message}`;
  } catch (e) {
    result.textContent = `❌ 检查失败: ${e.message}`;
  }
}

async function checkGitSync() {
  const result = document.getElementById("gitCfgStatus");
  result.textContent = "正在检测远端更新…首次检测可能需要克隆仓库。";
  try {
    const r = await api("/api/git-sync/check", { method: "POST" });
    result.textContent = r.ok
      ? `✅ ${r.message}${r.remote_commit ? `（${r.remote_commit.slice(0, 8)}）` : ""}`
      : `❌ ${r.message}`;
  } catch (e) {
    result.textContent = `❌ 检测失败: ${e.message}`;
  }
}

async function browseGitDir(targetId) {
  try {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.choose_dir) {
      const dir = await window.pywebview.api.choose_dir();
      if (dir) document.getElementById(targetId || "gitCfgLocal").value = dir;
    } else {
      showToast("浏览器模式请手动输入本地同步目录");
    }
  } catch (e) {
    showToast(`目录选择失败: ${e.message}`);
  }
}

async function browsePkgDir() {
  try {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.choose_dir) {
      const dir = await window.pywebview.api.choose_dir();
      if (dir) document.getElementById("pkgOutDir").value = dir;
    } else {
      showToast("浏览器模式无法弹出目录选择框（桌面版 exe 支持），请手动输入路径");
    }
  } catch (e) {
    showToast(`目录选择失败: ${e.message}`);
  }
}

async function exportPackage() {
  const statusEl = document.getElementById("pkgStatus");
  const outDir = document.getElementById("pkgOutDir").value.trim();
  const btn = event && event.target ? event.target : null;
  if (btn) btn.disabled = true;
  statusEl.textContent = "打包中…";
  try {
    const r = await api("/api/data/export", {
      method: "POST", body: JSON.stringify({ out_dir: outDir }),
    });
    if (!r.ok) { statusEl.textContent = `❌ ${r.error}`; return; }
    statusEl.textContent =
      `✅ 已导出 ${r.subcats} 个子分类 / ${r.items} 条 → ${r.path}`;
    showToast(`数据包已导出: ${r.path}`);
  } catch (e) {
    statusEl.textContent = `❌ 导出失败: ${e.message}`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function importPackage() {
  const input = document.getElementById("pkgFile");
  const statusEl = document.getElementById("pkgStatus");
  const f = input.files[0];
  if (!f) return;
  if (!confirm(`将导入数据包「${f.name}」，以合并方式并入当前仓库（导入前自动备份，相同元件自动合并数量）。继续？`)) {
    input.value = "";
    return;
  }
  if (!await ensureGitBeforeWrite()) { statusEl.textContent = "远端未同步，已取消导入"; return; }
  statusEl.textContent = "导入中…（同名子分类自动合并）";
  const form = new FormData();
  form.append("file", f);
  try {
    const res = await fetch("/api/data/import", { method: "POST", body: form });
    const data = await res.json();
    if (!data.ok) { statusEl.textContent = `❌ ${data.error}`; return; }
    let lines = [`✅ 导入完成：${data.subcats} 个子分类，净增 ${data.items} 条`];
    if (data.backup) lines.push(`导入前已自动备份 → ${data.backup}`);
    const skips = Object.entries(data.detail || {}).filter(([k]) => String(k).includes("跳过"));
    if (skips.length) lines.push(`⚠ ${skips.length} 个子分类跳过: ${skips.map(([k]) => k).join("、")}`);
    statusEl.textContent = lines.join("；");
    loadDataStat();
    showToast("数据包导入完成");
  } catch (e) {
    statusEl.textContent = `❌ 导入失败: ${e.message}`;
  } finally {
    input.value = "";
  }
}

// ── 数据管理 ────────────────────────────
async function loadDataStat() {
  const hint = document.getElementById("dataStatHint");
  try {
    const [dash, uncat] = await Promise.all([
      api("/api/dashboard"), api("/api/unclassified"),
    ]);
    const s = dash.stats;
    hint.textContent =
      `元器件 ${s.items} 条（${s.categories} 个分类 / ${s.subcats} 个子分类），` +
      `未分类 ${uncat.count} 条`;
  } catch (e) { hint.textContent = "统计加载失败"; }
}

async function clearData(scope) {
  const statusEl = document.getElementById("setDataStatus");
  const labels = {
    all: "清空全部数据",
    unclassified: "清空未分类",
    activity: "清除操作日志",
  };
  if (scope === "all") {
    if (!confirm("⚠️ 将删除全部元器件数据（所有分类、未分类、操作日志），此操作不可恢复！\n确定继续？")) return;
    if (!confirm("再次确认：真的要清空全部数据吗？")) return;
  } else {
    if (!confirm(`确定${labels[scope]}？`)) return;
  }
  if (scope !== "activity" && !await ensureGitBeforeWrite()) { statusEl.textContent = "远端未同步，已取消清理"; return; }
  const res = await api("/api/data/clear", {
    method: "POST", body: JSON.stringify({ scope }),
  });
  if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
  statusEl.textContent = `✅ ${labels[scope]}完成`;
  showToast(`${labels[scope]}完成`);
  if (scope === "all") {
    closeAIConfig();
    render("home", false);   // 回首页, 界面立即干净
    loadLowStockBadge();
  } else {
    loadDataStat();
  }
}

// ── 数据管理: 删除指定子分类 ────────────
async function fillDelCatSel() {
  const sel = document.getElementById("delCatSel");
  sel.innerHTML = '<option value="">— 选择一级分类 —</option>';
  try {
    const data = await api("/api/overview");
    data.cards.forEach((c) => {
      if (c.key === "unclassified") return;
      const opt = document.createElement("option");
      opt.value = c.key;
      opt.textContent = `${c.name}（${c.count} 条）`;
      sel.appendChild(opt);
    });
  } catch (e) { /* 忽略 */ }
}

async function onDelCatChange() {
  const key = document.getElementById("delCatSel").value;
  const box = document.getElementById("delSubcatList");
  box.innerHTML = "";
  if (!key) { box.innerHTML = '<div class="file-hint">选择一级分类后显示其子分类</div>'; return; }
  const data = await api(`/api/category/${key}`);
  if (!data.subcats.length) {
    box.innerHTML = '<div class="file-hint">该分类暂无数据</div>';
    return;
  }
  data.subcats.forEach((s) => {
    const label = document.createElement("label");
    label.className = "del-item";
    label.innerHTML = `<input type="checkbox" value="${escHtml(s.name)}"> ${escHtml(s.name)}（${s.count} 条）`;
    box.appendChild(label);
  });
}

async function deleteSubcats() {
  const statusEl = document.getElementById("setDataStatus");
  const names = [...document.querySelectorAll("#delSubcatList input:checked")].map((c) => c.value);
  if (!names.length) { statusEl.textContent = "请勾选要删除的子分类"; return; }
  if (!confirm(`将删除 ${names.length} 个子分类的全部元件数据，此操作不可恢复。\n确定继续？`)) return;
  if (!await ensureGitBeforeWrite()) { statusEl.textContent = "远端未同步，已取消删除"; return; }
  const res = await api("/api/subcat/delete", {
    method: "POST", body: JSON.stringify({ names }),
  });
  if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
  statusEl.textContent = `✅ 已删除 ${res.deleted.length} 个子分类`;
  showToast(`已删除 ${res.deleted.length} 个子分类`);
  fillDelCatSel();
  onDelCatChange();
  loadDataStat();
  loadLowStockBadge();
}

function renderThemeGrid(current) {
  const grid = document.getElementById("themeGrid");
  grid.innerHTML = "";
  for (const [key, [c1, c2, name]] of Object.entries(THEMES)) {
    const card = document.createElement("div");
    card.className = "theme-card" + (key === current ? " active" : "");
    card.innerHTML = `
      <div class="theme-swatch" style="background:linear-gradient(135deg,${c1},${c2})"></div>
      <div class="theme-name">${name}</div>`;
    card.onclick = async () => {
      const s = await api("/api/settings", {
        method: "POST", body: JSON.stringify({ theme: key }),
      });
      currentSettings = s;
      loadBgState(s);
      applyTheme(s.theme);
      renderThemeGrid(key);
      document.getElementById("setUIStatus").textContent = "✅ 主题已切换";
    };
    grid.appendChild(card);
  }
}

async function saveDataDir() {
  const dir = document.getElementById("setDataDir").value.trim();
  const statusEl = document.getElementById("setPathStatus");
  const s = await api("/api/settings", {
    method: "POST", body: JSON.stringify({ data_dir: dir }),
  });
  statusEl.textContent = "✅ 已保存。新路径将在重启软件后生效。";
  document.getElementById("setDataDirHint").textContent = `当前实际使用: ${s.resolved_data_dir}`;
}

/* 数据路径: 桌面版弹原生目录选择框, 浏览器模式只能手动输入 */
async function browseDataDir() {
  const input = document.getElementById("setDataDir");
  try {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.choose_dir) {
      const dir = await window.pywebview.api.choose_dir();
      if (dir) input.value = dir;
    } else {
      showToast("浏览器模式无法弹出目录选择框（桌面版 exe 支持），请手动输入路径");
    }
  } catch (e) {
    showToast(`目录选择失败: ${e.message}`);
  }
}

async function uploadBg() {
  const f = document.getElementById("bgFile").files[0];
  const statusEl = document.getElementById("setUIStatus");
  if (!f) return;
  statusEl.textContent = "上传中…";
  const form = new FormData();
  form.append("file", f);
  const res = await fetch("/api/settings/background", { method: "POST", body: form });
  const data = await res.json();
  if (!data.ok) { statusEl.textContent = `❌ ${data.error}`; return; }
  bgState.background = data.background;
  applyTheme();
  statusEl.textContent = "✅ 已预览新背景，点「保存背景设置」生效";
}

async function saveAppearanceSettings() {
  currentSettings = await api("/api/settings", { method: "POST", body: JSON.stringify({ font_size: bgState.fontSize, dark_strength: bgState.darkStrength, font_family: bgState.fontFamily }) });
  document.getElementById("setUIStatus").textContent = "界面设置已保存";
  showToast("界面设置已保存");
}

async function saveBgSettings() {
  const statusEl = document.getElementById("setUIStatus");
  const s = await api("/api/settings", {
    method: "POST",
    body: JSON.stringify({
      background: bgState.background,
      bg_brightness: bgState.brightness,
      bg_opacity: bgState.opacity,
      card_opacity: bgState.cardOpacity,
      bg_fill: bgState.fill,
      font_size: bgState.fontSize,
      dark_strength: bgState.darkStrength,
      font_family: bgState.fontFamily,
    }),
  });
  currentSettings = s;
  statusEl.textContent = "✅ 背景设置已保存";
  showToast("背景设置已保存");
}

async function clearBg() {
  const statusEl = document.getElementById("setUIStatus");
  bgState.background = "";
  applyTheme();
  statusEl.textContent = "已清除背景图预览，点「保存背景设置」生效";
}

const AI_PRESETS = {
  deepseek: ["https://api.deepseek.com", "deepseek-chat"],
  glmflash: ["https://open.bigmodel.cn/api/paas/v4", "glm-4-flash"],
  glm: ["https://open.bigmodel.cn/api/paas/v4", "glm-4.7"],
  siliconflow: ["https://api.siliconflow.cn/v1", "Qwen/Qwen2.5-7B-Instruct"],
  qwen: ["https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-turbo"],
  openai: ["https://api.openai.com", "gpt-4o-mini"],
};

function applyAIPreset() {
  const v = document.getElementById("aiCfgPreset").value;
  if (!v || !AI_PRESETS[v]) return;
  const [url, model] = AI_PRESETS[v];
  document.getElementById("aiCfgUrl").value = url;
  document.getElementById("aiCfgModel").value = model;
}

// ── AI 服务切换 (在线 / 本地 Ollama) ────
function switchAIProvider() {
  const p = document.getElementById("aiCfgProvider").value;
  const ollama = p === "ollama";
  document.getElementById("aiCfgOnlineBox").style.display = ollama ? "none" : "";
  document.getElementById("aiCfgKeyBox").style.display = ollama ? "none" : "";
  document.getElementById("aiCfgPresetBox").style.display = ollama ? "none" : "";
  document.getElementById("aiCfgModelBox").style.display = ollama ? "none" : "";
  document.getElementById("aiCfgOllamaBox").style.display = ollama ? "" : "none";
  if (ollama) {
    document.getElementById("aiCfgUrl").value = document.getElementById("aiCfgUrl").value
      || "http://localhost:11434/v1";
    loadOllamaModels();
  }
}

// 加载 Ollama 本地已装模型列表
async function loadOllamaModels() {
  const sel = document.getElementById("aiCfgOllamaModel");
  const hint = document.getElementById("aiCfgOllamaHint");
  if (!sel) return;
  sel.innerHTML = '<option value="">— 检测中… —</option>';
  try {
    const res = await api("/api/ollama/models", { method: "GET" });
    sel.innerHTML = "";
    if (!res.running) {
      sel.innerHTML = '<option value="">— 未检测到 Ollama —</option>';
      hint.textContent = res.error || "请先安装并启动 Ollama";
      return;
    }
    const models = res.models || [];
    if (!models.length) {
      sel.innerHTML = '<option value="">— 未安装模型 —</option>';
      hint.textContent = "Ollama 已运行，但还没有模型。安装：ollama pull qwen2.5:7b（或 3b 更省内存）";
      return;
    }
    models.forEach(m => {
      const opt = document.createElement("option");
      opt.value = m.name;
      opt.textContent = `${m.name}（${m.size_gb}GB）`;
      sel.appendChild(opt);
    });
    hint.textContent = `Ollama 已运行，共 ${models.length} 个本地模型；选择后自动填入模型名`;
    // 若当前已配置模型在列表里则选中
    const cur = document.getElementById("aiCfgModel").value;
    if (cur && models.some(m => m.name === cur)) sel.value = cur;
  } catch (e) {
    sel.innerHTML = '<option value="">— 检测失败 —</option>';
    hint.textContent = String(e.message || e);
  }
}

async function saveAIConfig() {
  const btn = document.getElementById("aiCfgSaveBtn");
  const statusEl = document.getElementById("aiCfgStatus");
  btn.disabled = true;
  const provider = document.getElementById("aiCfgProvider").value;
  const s = await api("/api/settings", {
    method: "POST",
    body: JSON.stringify({
      ai: {
        provider,
        base_url: document.getElementById("aiCfgUrl").value,
        api_key: document.getElementById("aiCfgKey").value,
        model: document.getElementById("aiCfgModel").value,
      },
    }),
  });
  btn.disabled = false;
  if (provider === "ollama") {
    statusEl.textContent = "✅ 已切换到本地离线模式 (Ollama)";
    showToast("AI 配置已保存（本地离线）");
  } else if (s.ai.configured) {
    statusEl.textContent = `✅ 配置已保存 (${s.ai.api_key_masked})`;
    showToast("AI 配置已保存");
  } else {
    statusEl.textContent = "❌ 未填写 API Key";
  }
}

// AI 连通性测试: 先保存当前表单配置, 再发最小请求验证
async function testAIConfig() {
  const btn = document.getElementById("aiCfgTestBtn");
  const resultEl = document.getElementById("aiCfgTestResult");
  const provider = document.getElementById("aiCfgProvider").value;
  await api("/api/settings", {
    method: "POST",
    body: JSON.stringify({
      ai: {
        provider,
        base_url: document.getElementById("aiCfgUrl").value,
        api_key: document.getElementById("aiCfgKey").value,
        model: document.getElementById("aiCfgModel").value,
      },
    }),
  });
  btn.disabled = true;
  resultEl.textContent = "🔌 测试中…";
  const res = await api("/api/ai_test", { method: "POST", body: "{}" });
  btn.disabled = false;
  if (res.ok) {
    resultEl.textContent = `✅ 连接正常，模型回复: "${res.reply}"`;
    resultEl.style.color = "#16a34a";
  } else {
    resultEl.textContent = `❌ 测试失败: ${res.error || "未知错误"}`;
    resultEl.style.color = "#dc2626";
  }
}

// 启动时应用已保存的主题
(async () => {
  try {
    const s = await api("/api/settings");
    currentSettings = s;
    loadBgState(s);
    applyTheme(s.theme);
  } catch (e) { /* 服务未就绪时忽略 */ }
})();

// 启动时探测可用摄像头列表
loadCameraList();

// 点击遮罩关闭
document.getElementById("aiConfigModal").addEventListener("click", (e) => {
  if (e.target.id === "aiConfigModal") closeAIConfig();
});

// ── 品牌库 (品牌 / 采购量 / 经营的元器件类别) ──────────
let brandAll = [];          // 品牌聚合列表缓存 (搜索过滤用)
let brandReqSeq = 0;        // 请求序号: 防止快速切换时旧请求结果覆盖新页面 (乱串)

function brandAvatar(brand) {
  const b = String(brand || "").trim();
  if (!b) return "?";
  // 英文/数字品牌取前 2 个字母大写, 中文取第 1 个字
  if (!/[\u4e00-\u9fff]/.test(b[0])) {
    const m = b.match(/[A-Za-z0-9]/g);
    if (m && m.length >= 2) return (m[0] + m[1]).toUpperCase();
  }
  return b[0].toUpperCase();
}

async function renderBrands() {
  const seq = ++brandReqSeq;
  document.getElementById("brandsPage").style.display = "";
  document.getElementById("brandSearch").value = "";
  const data = await api("/api/brands");
  if (seq !== brandReqSeq) return;   // 期间已切换到其他页面, 丢弃旧结果
  brandAll = data.brands;
  const st = data.stats;
  document.getElementById("brandStats").textContent =
    `${st.brand_count} 个品牌 · ${st.item_count} 种元件 · 共 ${st.total_qty} 件` +
    (st.no_brand ? `（另有 ${st.no_brand} 条未填写品牌）` : "");
  renderBrandGrid(brandAll);
}

function renderBrandGrid(list) {
  const grid = document.getElementById("brandGrid");
  grid.innerHTML = "";
  if (!list.length) {
    grid.innerHTML = '<div class="empty-hint">暂无品牌数据 —— 库存里还没有填写「品牌」字段的元器件</div>';
    return;
  }
  list.forEach((b, i) => {
    const [bg, fg] = PALETTE[i % PALETTE.length];
    const el = document.createElement("div");
    el.className = "card";
    el.title = `点击查看 ${b.brand} 的全部元器件` +
      (b.aliases && b.aliases.length ? `\n同品牌其他写法: ${b.aliases.join(" / ")}` : "");
    el.innerHTML = `
      <div class="brand-avatar" style="background:${bg};color:${fg}">${escHtml(brandAvatar(b.brand))}</div>
      <div class="card-name" style="font-size:15px">${escHtml(b.brand)}${b.aliases && b.aliases.length ? '<span class="alias-badge" title="同品牌其他写法已合并">多写法</span>' : ""}</div>
      <div class="brand-biz" title="${escHtml(b.business || "")}">${escHtml(b.business || "")}</div>
      <div class="brand-stats">${b.count} 种 · 共 ${b.total_qty} 件</div>
      <div class="brand-tags">${b.owners.map(o => `<span class="tag-chip">${escHtml(o)}</span>`).join("")}</div>`;
    el.onclick = () => goBrand(b.brand);
    grid.appendChild(el);
  });
}

async function rebuildCatalog() {
  const hint = document.getElementById("brandCatalogHint");
  hint.textContent = "生成中…";
  const res = await api("/api/brands/catalog", { method: "POST", body: "{}" });
  if (!res.ok) { hint.textContent = `❌ ${res.error}`; return; }
  hint.textContent = `✅ 已生成 ${res.path}（品牌/业务/已购种类/总件数，可随时用 WPS/Excel 打开查看）`;
  showToast("品牌库 Excel 已重建");
}

function filterBrands() {
  const q = document.getElementById("brandSearch").value.trim().toLowerCase();
  if (!q) { renderBrandGrid(brandAll); return; }
  const list = brandAll.filter((b) =>
    b.brand.toLowerCase().includes(q) ||
    b.owners.some((o) => o.toLowerCase().includes(q)) ||
    b.subcats.some((s) => s.toLowerCase().includes(q)) ||
    b.samples.some((s) => s.toLowerCase().includes(q)));
  renderBrandGrid(list);
}

async function renderBrandDetail(name) {
  const seq = ++brandReqSeq;
  document.getElementById("brandDetailPage").style.display = "";
  const data = await api(`/api/brands/detail?brand=${encodeURIComponent(name)}`);
  if (seq !== brandReqSeq) return;   // 期间已切换到其他品牌/页面, 丢弃旧结果
  document.getElementById("brandDetailTitle").textContent = `🏷️ ${data.brand}`;
  document.getElementById("brandDetailCount").textContent = `${data.items.length} 条记录`;
  const owners = [...new Set(data.items.map((it) => it.owner).filter(Boolean))];
  const tags = owners.map((o) => `<span class="tag-chip">${escHtml(o)}</span>`);
  if (data.aliases && data.aliases.length) {
    tags.push(`<span class="tag-chip alias-chip" title="同一品牌的不同写法已合并统计">≈ ${escHtml(data.aliases.join(" / "))}</span>`);
  }
  document.getElementById("brandDetailOwners").innerHTML = tags.join("");
  const tbody = document.getElementById("brandDetailBody");
  tbody.innerHTML = "";
  if (!data.items.length) {
    tbody.innerHTML = '<tr><td colspan="7"><div class="empty-hint">没有该品牌的库存记录</div></td></tr>';
    return;
  }
  data.items.forEach((it) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escHtml(it.name)}</td>
      <td>${escHtml(it.package)}</td>
      <td>${escHtml(it.qty)}</td>
      <td>${escHtml(it.location)}</td>
      <td>${escHtml(it.subcat)}</td>
      <td class="uncat-raw">${escHtml(it.spec)}</td>
      <td>${escHtml(it.note)}</td>`;
    tbody.appendChild(tr);
  });
}

function exportBrands() {
  window.location.href = "/api/brands/export";
}

// ── 4.0 工作区侧栏 ─────────────────────
function setActiveSidebar(page) {
  const root = page === "home" ? "home" : page.split(":")[0];
  document.querySelectorAll(".sidebar-nav-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.page === root);
  });
}

function toggleSidebar() {
  if (window.matchMedia("(max-width: 760px)").matches) {
    document.body.classList.toggle("ws-sidebar-open");
    return;
  }
  document.body.classList.toggle("ws-sidebar-collapsed");
  localStorage.setItem("tp-sidebar-collapsed", document.body.classList.contains("ws-sidebar-collapsed") ? "1" : "0");
}

function focusWorkspaceSearch() {
    render("workspace-search");
}

function goWorkspaceSearch(query = "", keepSidebarFocus = false) {
  if (pageStack[pageStack.length - 1] === "workspace-search") {
    const input = document.getElementById("workspaceSearchInput");
    if (input && query) { input.value = query; searchWorkspace(query); }
    (keepSidebarFocus ? document.getElementById("sidebarSearchInput") : input)?.focus();
    return;
  }
  render("workspace-search").then(() => {
    const input = document.getElementById("workspaceSearchInput");
    if (!input) return;
    if (query) { input.value = query; searchWorkspace(query); }
    const sidebarInput = document.getElementById("sidebarSearchInput");
    if (keepSidebarFocus && sidebarInput) sidebarInput.focus();
    else input.focus();
  });
}

async function renderWorkspaceSearch() {
  const input = document.getElementById("workspaceSearchInput");
  const state = document.getElementById("workspaceSearchState");
  const results = document.getElementById("workspaceSearchResults");
  if (!input || !state || !results) return;
  if (input._bound !== true) {
    input.addEventListener("input", () => searchWorkspace(input.value));
    input._bound = true;
  }
  if (input.value.trim()) await searchWorkspace(input.value);
  else { state.textContent = "输入关键词开始搜索"; results.innerHTML = ""; }
}

async function openWorkspaceSearchFromSidebar(value) {
  if (pageStack[pageStack.length - 1] !== "workspace-search") await render("workspace-search");
  const pageInput = document.getElementById("workspaceSearchInput");
  if (pageInput) pageInput.value = value;
  if (value.trim()) await searchWorkspace(value);
}

async function searchWorkspace(value) {
  const q = value.trim();
  const state = document.getElementById("workspaceSearchState");
  const results = document.getElementById("workspaceSearchResults");
  if (!q) { state.textContent = "输入关键词开始搜索"; results.innerHTML = ""; return; }
  state.textContent = "搜索中…";
  const data = await api(`/api/search?q=${encodeURIComponent(q)}`);
  const items = data.items || [];
  state.textContent = items.length ? `找到 ${data.total} 条结果` : "没有找到匹配的库存记录";
  results.innerHTML = items.map((it, index) => `<button class="workspace-search-result" type="button" data-search-index="${index}"><span class="workspace-search-result-main"><b>${escHtml(it.name || "未命名")}</b><small>${escHtml(it.brand)} · ${escHtml(it.package)}</small></span><span class="workspace-search-result-meta"><b>${escHtml(it.qty || "0")} 件</b><small>${escHtml(it.category)} / ${escHtml(it.subcat)} · ${escHtml(it.location)}</small></span></button>`).join("");
  results.querySelectorAll(".workspace-search-result").forEach((el, index) => el.addEventListener("click", () => goSubcat(items[index].subcat)));
}

document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    goWorkspaceSearch();
  }
});

function initWorkspaceSidebar() {
  const sidebarInput = document.getElementById("sidebarSearchInput");
  sidebarInput?.addEventListener("focus", () => {
    openWorkspaceSearchFromSidebar(sidebarInput.value);
  });
  sidebarInput?.addEventListener("input", () => {
    openWorkspaceSearchFromSidebar(sidebarInput.value);
  });

  if (localStorage.getItem("tp-sidebar-collapsed") === "1") document.body.classList.add("ws-sidebar-collapsed");
  const resize = document.getElementById("sidebarResize");
  let resizing = false;
  resize.addEventListener("pointerdown", (event) => {
    if (document.body.classList.contains("ws-sidebar-collapsed")) return;
    resizing = true;
    resize.setPointerCapture(event.pointerId);
    document.body.style.userSelect = "none";
  });
  resize.addEventListener("pointermove", (event) => {
    if (!resizing) return;
    const width = Math.max(190, Math.min(380, event.clientX));
    document.documentElement.style.setProperty("--ws-sidebar-width", `${width}px`);
    localStorage.setItem("tp-sidebar-width", String(width));
  });
  resize.addEventListener("pointerup", () => {
    resizing = false;
    document.body.style.userSelect = "";
  });
  const savedWidth = Number(localStorage.getItem("tp-sidebar-width"));
  if (savedWidth >= 190 && savedWidth <= 380) document.documentElement.style.setProperty("--ws-sidebar-width", `${savedWidth}px`);
  document.querySelector("body > header")?.addEventListener("click", (event) => {
    if (window.matchMedia("(max-width: 760px)").matches && event.target === event.currentTarget) document.body.classList.toggle("ws-sidebar-open");
  });
}

// ── 启动 ───────────────────────────────
initWorkspaceSidebar();
pageStack = ["home"];
render("home", false);
