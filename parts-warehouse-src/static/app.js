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
  for (const id of ["homePage", "overviewPage", "subcatPage", "detailPage", "lowstockPage", "unclassifiedPage", "withdrawPage", "inputPage", "bomMatchPage"]) {
    document.getElementById(id).style.display = "none";
  }
}

// ── 统一导航 ───────────────────────────
// page: 'home' | 'categories' | 'category:<key>' | 'subcat:<name>' | 'lowstock' | 'input'
async function render(page, push = true) {
  if (push) pageStack.push(page);
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
  else if (page === "input")      await renderInput();
}

// 导航入口 (HTML onclick 调用这些)
function goHome()        { render("home"); }
function goCategories()  { render("categories"); }
function goLowStock()    { render("lowstock"); }
function goInput()       { render("input"); }
function goWithdraw()    { render("withdraw"); }
function goBomMatch()    { render("bommatch"); }
function goCategory(key) { render("category:" + key); }
function goSubcat(name)  { render("subcat:" + name); }

function goBack() {
  if (pageStack.length <= 1) { render("home", false); return; }
  pageStack.pop();
  const prev = pageStack[pageStack.length - 1];
  render(prev, false);
}

// ── 首页: 浏览仪表盘 ────────────────────
async function renderHome() {
  document.getElementById("homePage").style.display = "";
  const data = await api("/api/dashboard");
  renderStats(data.stats);
  renderLogs(data.logs);
  renderTopCat(data.stats);
  loadLowStockBadge();
  applyDecors();
}

function renderStats(s) {
  document.getElementById("statCategories").textContent = s.categories;
  document.getElementById("statSubcats").textContent = s.subcats;
  document.getElementById("statItems").textContent = s.items;
  document.getElementById("statQty").textContent = s.total_qty;
}

function renderTopCat(s) {
  const el = document.getElementById("topCatName");
  if (s.top_subcat) {
    el.textContent = `${s.top_subcat.name} · ${s.top_subcat.count} 条`;
    el.title = "条目数最多的子分类";
  } else {
    el.textContent = "暂无数据";
  }
}

function renderLogs(logs) {
  const wheel = document.getElementById("logWheel");
  if (!logs.length) {
    wheel.innerHTML = '<div class="wheel-placeholder">暂无操作记录<br>保存元器件后这里会显示存入/使用情况</div>';
    return;
  }
  wheel.innerHTML = "";
  logs.forEach((log) => {
    const div = document.createElement("div");
    const cls = log.qty_delta > 0 ? "act-in" : (log.qty_delta < 0 ? "act-out" : "act-neutral");
    const tagCls = log.qty_delta > 0 ? "tag-in" : (log.qty_delta < 0 ? "tag-out" : "tag-neutral");
    const tagTxt = log.qty_delta > 0 ? `存入 +${log.qty_delta}` :
                   (log.qty_delta < 0 ? `使用 ${log.qty_delta}` : "修改");
    div.className = `log-entry ${cls}`;
    div.innerHTML = `
      <div class="log-time">${log.time}</div>
      <div class="log-sub">${log.subcat}</div>
      <div class="log-act"><span class="tag ${tagCls}">${tagTxt}</span>
        ${log.action} (${log.old}→${log.new} 条)</div>`;
    wheel.appendChild(div);
  });
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
  await wdMatchItems(data.items, data.dropped_nc || 0, data.usage);
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
  await wdMatchItems(data.items, data.dropped_nc || 0, null);
}

async function wdMatchItems(items, droppedNc, usage) {
  const statusEl = document.getElementById("wdMatchStatus");
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
  statusEl.textContent =
    `✅ 匹配完成：${m.matched}/${m.total} 项有库存可取出，其余需要采购${ncNote}${tkNote}`;
}

function renderWdMatch(results) {
  const mBody = document.getElementById("wdMatchBody");
  const nBody = document.getElementById("wdNoStockBody");
  mBody.innerHTML = "";
  nBody.innerHTML = "";
  let matched = 0, noStock = 0;
  results.forEach((r, idx) => {
    const it = r.item;
    const need = `${escHtml(it.name)}${it.spec ? " " + escHtml(it.spec) : ""}`;
    if (!r.candidates.length) {
      noStock++;
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${need}</td><td>${escHtml(it.spec)}</td><td>${escHtml(it.package)}</td><td>${escHtml(it.qty)}</td>`;
      nBody.appendChild(tr);
      return;
    }
    matched++;
    // 库存情况 (三色: 充足/可替代/不足) — 与 BOM匹配 同一套判定
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
      const warn = isExact ? "" : `<span class="wdm-warn">⚠️ ${escHtml(c.pkg_note || "型号/封装不同")}</span>`;
      choiceHtml += `
        <label class="wdm-choice${isExact ? "" : " wdm-similar"}">
          <input type="radio" name="wdm${idx}" value="${escHtml(c.subcat)}|||${c.row}"${(isExact && !hasExact) || (!hasExact && ci === 0) ? " checked" : ""}>
          <span class="wdm-info">${escHtml(c.name)} | ${escHtml(c.brand || "—")} | ${escHtml(c.spec || "—")} | 库存 ${escHtml(c.qty)}</span>
          <span class="wdm-subcat">${escHtml(c.subcat)}</span>
          ${warn}
          <input type="number" class="wdm-qty" min="1" value="${escHtml(it.qty)}" style="width:64px">
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

// ── BOM 匹配 (只读, 不扣数量) ─────────────────
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
      r.candidates.forEach((c) => {
        const isExact = c.match_type === "exact";
        const warn = isExact ? "" : ` <span class="wdm-warn">⚠️ ${escHtml(c.pkg_note || "封装不同")}</span>`;
        candHtml += `<div class="bm-cand">
          <span class="bm-tag ${isExact ? "bm-tag-exact" : "bm-tag-sim"}">${isExact ? "精确" : "相似"}</span>
          <span>${escHtml(c.name)} | ${escHtml(c.brand || "—")} | ${escHtml(c.spec || "—")}</span>
          <span class="bm-stock">库存 ${escHtml(c.qty)}</span>
          <span class="bm-subcat">${escHtml(c.subcat)}</span>${warn}
        </div>`;
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
  statusEl.textContent = "取出中…";
  let taken = 0, errs = [];
  for (const [subcat, items] of Object.entries(groups)) {
    const res = await api("/api/withdraw", {
      method: "POST", body: JSON.stringify({ name: subcat, items }),
    });
    if (res.ok) taken += res.taken;
    else errs.push(`「${subcat}」${res.error}`);
  }
  if (errs.length) {
    statusEl.textContent = `✅ 取出 ${taken} 件；部分失败：${errs.join("；")}`;
  } else {
    statusEl.textContent = `✅ 已取出 ${taken} 件，库存已更新`;
    showToast(`已取出 ${taken} 件`);
    document.getElementById("wdMatchResult").style.display = "none";
  }
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
  if (!files.length) return;
  statusEl.textContent = `识别中… 0/${files.length}（首次加载模型约几秒）`;

  // 逐张 OCR, 按图片分组保存文本行
  let imageGroups = [];   // [[行,...], [行,...], ...] 每张图一组
  for (let i = 0; i < files.length; i++) {
    statusEl.textContent = `识别中… ${i + 1}/${files.length}`;
    const form = new FormData();
    form.append("file", files[i]);
    try {
      const res = await fetch("/api/ocr", { method: "POST", body: form });
      const data = await res.json();
      if (data.ok && data.lines) {
        imageGroups.push(data.lines);
      } else {
        imageGroups.push([]);
        statusEl.textContent = `第 ${i + 1} 张失败: ${data.error || "未知错误"}`;
      }
    } catch (e) {
      imageGroups.push([]);
      statusEl.textContent = `第 ${i + 1} 张失败: ${e.message}`;
    }
  }

  const allLines = imageGroups.flat();
  if (!allLines.length) { statusEl.textContent = "❌ 没有识别出文字"; return; }
  // 带图片边界标记, 防止整理时把一张图的内容拆成多份
  const rawText = imageGroups
    .map((g, i) => (g.length ? `【图${i + 1}】\n${g.join("\n")}` : `【图${i + 1}】(无文字)`))
    .join("\n");
  document.getElementById("ocrText").value = allLines.join("\n");
  statusEl.textContent = `✅ 共识别 ${allLines.length} 行（${files.length} 张图），正在按模板整理…`;

  // 按料袋模板自动整理 (数量 型号 品牌 封装 电气参数 器件名称)
  try {
    const fmt = await api("/api/ocr/format", {
      method: "POST", body: JSON.stringify({ text: rawText }),
    });
    if (fmt.ok && fmt.text) {
      document.getElementById("ocrText").value = fmt.text;
      statusEl.textContent = `✅ 识别 ${files.length} 张图并已按模板整理，检查后点「AI 解析」`;
    } else {
      statusEl.textContent = `✅ 识别完成（自动整理失败：${fmt.error || "未知"}，可手动编辑）`;
    }
  } catch (e) {
    statusEl.textContent = "✅ 识别完成（整理失败，可手动编辑后解析）";
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
    statusEl.textContent = `✅ 拍摄 ${res.n} 张，识别 ${allLines.length} 行，正在按模板整理…`;
    try {
      const fmt = await api("/api/ocr/format", {
        method: "POST", body: JSON.stringify({ text: rawText }),
      });
      if (fmt.ok && fmt.text) {
        document.getElementById("ocrText").value = fmt.text;
        statusEl.textContent = `✅ 拍摄 ${res.n} 张并已按模板整理，检查后点「AI 解析」${warn}`;
      } else {
        statusEl.textContent = `✅ 识别完成（自动整理失败：${fmt.error || "未知"}，可手动编辑）`;
      }
    } catch (e) {
      statusEl.textContent = "✅ 识别完成（整理失败，可手动编辑后解析）";
    }
  } catch (e) {
    statusEl.textContent = `❌ 摄像头失败: ${e.message}`;
  }
}

async function ocrParse() {
  const text = document.getElementById("ocrText").value.trim();
  const statusEl = document.getElementById("ocrStatus");
  if (!text) { statusEl.textContent = "请先上传图片识别文字（或手动输入）"; return; }
  statusEl.textContent = "AI 解析中…";
  const res = await api("/api/import_parse_text", {
    method: "POST", body: JSON.stringify({ text }),
  });
  if (!res.ok) { statusEl.textContent = `❌ ${res.error}`; return; }
  ocrItems = res.items.map((it) => ({ ...it, _checked: true }));
  document.getElementById("ocrResult").style.display = "";
  document.getElementById("ocrResultCount").textContent = `${ocrItems.length} 条`;
  renderOcrResult();
  const ncNote = res.dropped_nc ? `（已剔除 ${res.dropped_nc} 条 NC/不贴装）` : "";
  statusEl.textContent = `✅ 解析完成 ${ocrItems.length} 条${ncNote}，请核对后确认写入`;
}

function renderOcrResult() {
  const body = document.getElementById("ocrResultBody");
  body.innerHTML = "";
  ocrItems.forEach((it, i) => {
    const tr = document.createElement("tr");
    if (!it.cat_key) tr.style.background = "#fef3c7";  // 未识别分类标黄
    tr.innerHTML = `
      <td><input type="checkbox" class="ocr-check" data-i="${i}" ${it._checked ? "checked" : ""} onchange="ocrItems[${i}]._checked=this.checked"></td>
      <td>${escHtml(it.name)}</td>
      <td>${escHtml(it.brand)}</td>
      <td>${escHtml(it.package)}</td>
      <td>${escHtml(it.qty)}</td>
      <td>${escHtml(it.spec)}</td>
      <td>${escHtml(it.cat_key || "⚠️ 未识别")}</td>
      <td>${escHtml(it.subcat)}</td>`;
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
const bgState = { background: "", brightness: 100, opacity: 100, cardOpacity: 100, fill: "cover" };

function loadBgState(s) {
  bgState.background = s.background || "";
  bgState.brightness = s.bg_brightness ?? 100;
  bgState.opacity = s.bg_opacity ?? 100;
  bgState.cardOpacity = s.card_opacity ?? 100;
  bgState.fill = s.bg_fill || "cover";
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

/* 按填充方式设置背景层的 background-size/repeat/position (主背景 + 预览弹窗同步) */
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
  document.getElementById("setUIStatus").textContent = s.background
    ? `当前背景: ${s.background}` : "当前为纯色背景";
  document.getElementById("decorHint1").textContent = !s.decor1
    ? "已隐藏" : (s.decor1.startsWith("static/") ? "使用默认内置图" : `当前: ${s.decor1}`);
  document.getElementById("decorHint2").textContent = !s.decor2
    ? "已隐藏" : (s.decor2.startsWith("static/") ? "使用默认内置图" : `当前: ${s.decor2}`);

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
  const map = { path: "setTabPath", ai: "setTabAI", ui: "setTabUI", data: "setTabData" };
  for (const [k, id] of Object.entries(map)) {
    document.getElementById(id).className = "tab2" + (k === tab ? " active" : "");
  }
  document.getElementById("setPanelPath").style.display = tab === "path" ? "" : "none";
  document.getElementById("setPanelAI").style.display = tab === "ai" ? "" : "none";
  document.getElementById("setPanelUI").style.display = tab === "ui" ? "" : "none";
  document.getElementById("setPanelData").style.display = tab === "data" ? "" : "none";
  if (tab === "data") loadDataStat();
}

// ── 数据包 导出/导入 ───────────────────
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

/* ── 首页装饰图片 (可在设置中自定义/隐藏) ── */
function setDecoImg(id, path) {
  const img = document.getElementById(id);
  if (!img) return;
  if (!path) { img.style.display = "none"; return; }
  img.style.display = "";
  img.src = path.startsWith("static/") ? "/" + path : "/data/" + path;
}

function applyDecors() {
  const s = currentSettings;
  setDecoImg("decoImg1", s ? s.decor1 : "static/deco_parts.png");
  setDecoImg("decoImg2", s ? s.decor2 : "static/deco_circuit.png");
}

async function uploadDecor(i) {
  const f = document.getElementById(`decorFile${i}`).files[0];
  const hint = document.getElementById(`decorHint${i}`);
  if (!f) return;
  hint.textContent = "上传中…";
  const form = new FormData();
  form.append("file", f);
  form.append("index", String(i));
  const res = await fetch("/api/settings/decor", { method: "POST", body: form });
  const data = await res.json();
  if (!data.ok) { hint.textContent = `❌ ${data.error}`; return; }
  currentSettings = await api("/api/settings");
  applyDecors();
  hint.textContent = `✅ 已应用 (${data.decor})`;
  showToast(`装饰图${i} 已更新`);
}

async function clearDecor(i) {
  const hint = document.getElementById(`decorHint${i}`);
  currentSettings = await api("/api/settings", {
    method: "POST", body: JSON.stringify({ [`decor${i}`]: "" }),
  });
  applyDecors();
  hint.textContent = "已清除，该位置不再显示装饰图";
  showToast(`装饰图${i} 已清除`);
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
    applyDecors();
  } catch (e) { /* 服务未就绪时忽略 */ }
})();

// 启动时探测可用摄像头列表
loadCameraList();

// 点击遮罩关闭
document.getElementById("aiConfigModal").addEventListener("click", (e) => {
  if (e.target.id === "aiConfigModal") closeAIConfig();
});

// ── 启动 ───────────────────────────────
pageStack = ["home"];
render("home", false);
