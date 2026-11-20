/* HomeLedger core: api, formatting, dates, keyboard helpers, modal, ledger picker, period bar */
"use strict";
const HL = window.HL = { S: { period: null, masters: null, status: null }, screens: {}, stack: [], cur: null };

/* ---------- tiny DOM helpers ---------- */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const k in attrs || {}) {
    const v = attrs[k];
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "html") e.innerHTML = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "value") e.value = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
}
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ---------- money & dates ---------- */
function inr(p, dec = 2) {            // integer paise -> "1,23,456.00"
  p = Math.round(Number(p) || 0);
  const neg = p < 0; p = Math.abs(p);
  let r = Math.floor(p / 100), ps = p % 100, s = String(r);
  if (s.length > 3) { let head = s.slice(0, -3), tail = s.slice(-3), parts = []; while (head.length > 2) { parts.unshift(head.slice(-2)); head = head.slice(0, -2); } if (head) parts.unshift(head); s = parts.concat(tail).join(","); }
  return (neg ? "-" : "") + s + (dec ? "." + String(ps).padStart(2, "0") : "");
}
const rs = (p, dec = 2) => "₹" + inr(p, dec);
function short(p) {                   // compact: 12.5k / 1.2L / 3.4Cr
  const n = Math.abs(p) / 100, sg = p < 0 ? "-" : "";
  const f = (x, u) => sg + (x >= 100 ? Math.round(x) : Math.round(x * 10) / 10) + u;
  if (n >= 1e7) return f(n / 1e7, "Cr");
  if (n >= 1e5) return f(n / 1e5, "L");
  if (n >= 1e3) return f(n / 1e3, "k");
  return sg + Math.round(n);
}
function drcr(signed) { return signed === 0 ? "" : (signed > 0 ? "Dr" : "Cr"); }
function bal(signed) { return signed === 0 ? "0.00" : inr(Math.abs(signed)) + " " + drcr(signed); }
const qtyStr = m => m == null ? "" : (m / 1000).toLocaleString("en-IN", { maximumFractionDigits: 3 });
const pad = n => String(n).padStart(2, "0");
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DOW = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
function isoDate(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
function toDate(iso) { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d); }
function showDate(iso) { if (!iso) return ""; const [y, m, d] = iso.split("-"); return d + "-" + MON[+m - 1] + "-" + y; }
function showDay(iso) { return DOW[toDate(iso).getDay()]; }
function monthLabel(ym, long) { const [y, m] = ym.split("-"); return MON[+m - 1] + (long ? " " + y : " '" + y.slice(2)); }
function todayIso() { return HL.S.status ? HL.S.status.today : isoDate(new Date()); }
function addDays(iso, n) { const d = toDate(iso); d.setDate(d.getDate() + n); return isoDate(d); }
function lastDayOfMonth(y, m) { return isoDate(new Date(y, m, 0)); }

/** Lenient date typing: 5 -> 5th of working month, 5-3 -> 5 Mar, 5/3/26, 05032026, 5.3.2026 ... returns ISO or null */
function parseDateInput(txt, ref) {
  txt = (txt || "").trim().toLowerCase();
  if (!txt) return null;
  if (txt === "t" || txt === "today") return todayIso();
  const base = toDate(ref || todayIso());
  let m = txt.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  let d, mo, y;
  if (m) { y = +m[1]; mo = +m[2]; d = +m[3]; }
  else {
    const parts = txt.replace(/[^\w]+/g, " ").trim().split(" ");
    const mi = i => { const k = MON.findIndex(x => x.toLowerCase() === (parts[i] || "").slice(0, 3)); return k >= 0 ? k + 1 : +parts[i]; };
    if (parts.length === 1 && /^\d{6,8}$/.test(parts[0])) { const s = parts[0]; d = +s.slice(0, 2); mo = +s.slice(2, 4); y = +s.slice(4); }
    else if (parts.length === 1) { d = +parts[0]; mo = base.getMonth() + 1; y = base.getFullYear(); }
    else if (parts.length === 2) { d = +parts[0]; mo = mi(1); y = base.getFullYear(); }
    else { d = +parts[0]; mo = mi(1); y = +parts[2]; }
  }
  if (y < 100) y += 2000;
  if (!(y >= 1990 && y <= 2100 && mo >= 1 && mo <= 12 && d >= 1 && d <= 31)) return null;
  const dt = new Date(y, mo - 1, d);
  if (dt.getMonth() !== mo - 1) return null;
  return isoDate(dt);
}

/* ---------- API ---------- */
async function api(path, body) {
  let res;
  try {
    res = await fetch(path, body === undefined ? { cache: "no-store" } :
      { method: "POST", headers: { "Content-Type": "application/json", "X-HomeLedger": "1" }, body: JSON.stringify(body) });
  } catch (e) {
    HL.connectionLost();
    throw new Error("HomeLedger is not running. Please close this window and open HomeLedger again.");
  }
  let data = null;
  try { data = await res.json(); } catch (e) { /* ignore */ }
  if (res.status === 401 && data && data.locked) { HL.showLogin && HL.showLogin("Please sign in again."); const e = new Error("Please sign in again."); e.locked = true; throw e; }
  if (!res.ok) throw new Error((data && data.error) || "Something went wrong.");
  return data;
}
const qs = o => Object.entries(o).filter(([, v]) => v !== null && v !== undefined && v !== "").map(([k, v]) => encodeURIComponent(k) + "=" + encodeURIComponent(v)).join("&");
HL.get = (path, o) => api(path + (o ? "?" + qs(o) : ""));
HL.post = (path, body) => api(path, body || {});
HL.connectionLost = function () {
  if (HL._lost) return; HL._lost = true;
  modal({ title: "HomeLedger has stopped", body: h("p", {}, "The program is no longer running, so nothing more can be saved. Your earlier entries are safe. Please close this window and start HomeLedger again from the desktop icon."), buttons: [] });
};

/* ---------- status line ---------- */
let msgTimer;
function say(text, kind) {
  const m = $("#msg"); m.textContent = text; m.className = "msg " + (kind || "");
  clearTimeout(msgTimer); if (kind) msgTimer = setTimeout(() => { m.textContent = "Ready"; m.className = "msg"; }, kind === "err" ? 12000 : 5000);
}
function fail(e) { say(e.message || String(e), "err"); }

/* ---------- tooltip ---------- */
const tipEl = () => $("#tip");
function showTip(ev, html) {
  const t = tipEl(); t.innerHTML = html; t.style.display = "block";
  const w = t.offsetWidth, hh = t.offsetHeight;
  let x = ev.clientX + 14, y = ev.clientY + 14;
  if (x + w > innerWidth - 6) x = ev.clientX - w - 14;
  if (y + hh > innerHeight - 6) y = ev.clientY - hh - 14;
  t.style.left = Math.max(4, x) + "px"; t.style.top = Math.max(4, y) + "px";
}
function hideTip() { tipEl().style.display = "none"; }

/* ---------- modal ---------- */
let modalStack = [];
function modal({ title, body, buttons, wide, onclose, focus }) {
  const root = $("#modal-root");
  const prev = document.activeElement;
  const box = h("div", { class: "modal" + (wide ? " wide" : ""), role: "dialog", "aria-modal": "true", "aria-label": title },
    h("div", { class: "mh" }, title), h("div", { class: "mb" }, body));
  const m = { box, prev, onclose, close(result) { closeModal(m, result); } };
  if (buttons && buttons.length) {
    const foot = h("div", { class: "mf" });
    for (const b of buttons) foot.append(h("button", { class: "btn " + (b.cls || ""), type: "button", onclick: () => b.onclick ? b.onclick(m) : m.close() }, b.label));
    box.append(foot);
  }
  modalStack.push(m);
  root.replaceChildren(box); root.classList.add("on");
  setTimeout(() => { (focus ? $(focus, box) : $("input,select,textarea,.btn.primary", box) || $(".btn", box))?.focus(); }, 30);
  return m;
}
function closeModal(m, result) {
  const i = modalStack.indexOf(m); if (i < 0) return;
  modalStack.splice(i, 1);
  const root = $("#modal-root");
  if (modalStack.length) root.replaceChildren(modalStack[modalStack.length - 1].box);
  else { root.classList.remove("on"); root.replaceChildren(); }
  m.prev && m.prev.focus && m.prev.focus();
  m.onclose && m.onclose(result);
}
const topModal = () => modalStack[modalStack.length - 1];
function confirmBox(title, text, yesLabel, danger) {
  return new Promise(res => {
    modal({ title, body: h("p", {}, text), onclose: r => res(r === true),
      buttons: [{ label: "No, go back", onclick: m => m.close(false) },
                { label: yesLabel || "Yes", cls: danger ? "danger" : "primary", onclick: m => m.close(true) }], focus: ".btn.primary,.btn.danger" });
  });
}

/* ---------- keyboard: Enter = next field (Tally habit) ---------- */
function enterAsTab(container, onLast) {
  container.addEventListener("keydown", e => {
    if (e.key !== "Enter" || e.shiftKey || e.ctrlKey || e.defaultPrevented) return;
    const t = e.target;
    if (t.tagName === "BUTTON" || t.tagName === "TEXTAREA" || t.dataset.noEnter) return;
    if (t.closest(".dd")) return;
    e.preventDefault();
    const f = $$("input:not([type=hidden]):not([disabled]),select,textarea,button.stop", container).filter(x => x.offsetParent !== null && x.tabIndex >= 0);
    const i = f.indexOf(t);
    if (i >= 0 && i < f.length - 1) { f[i + 1].focus(); f[i + 1].select && f[i + 1].select(); }
    else if (onLast) onLast();
  });
}

/* ---------- searchable picker (ledgers, groups, activities...) ---------- */
function picker({ options, value, placeholder, onpick, allowNew, newLabel, onnew, width, clearable }) {
  const wrap = h("div", { class: "combo" });
  const inp = h("input", { type: "text", autocomplete: "off", placeholder: placeholder || "Type to search...", "aria-label": placeholder || "Choose", style: width ? "width:" + width : "" });
  const dd = h("div", { class: "dd", style: "display:none" });
  wrap.append(inp, dd);
  let cur = null, idx = 0, list = [], open = false;
  const label = o => o ? o.label : "";
  const api_ = {
    el: wrap, input: inp,
    get value() { return cur ? cur.value : null; },
    get option() { return cur; },
    set(v) { cur = options().find(o => String(o.value) === String(v)) || null; inp.value = label(cur); },
    focus() { inp.focus(); inp.select(); },
  };
  function filt() {
    const q = inp.value.trim().toLowerCase();
    const all = options();
    if (!q || (cur && inp.value === label(cur))) list = all.slice(0, 200);
    else {
      const w = q.split(/\s+/);
      list = all.filter(o => w.every(x => o.label.toLowerCase().includes(x) || (o.hint || "").toLowerCase().includes(x)));
      list.sort((a, b) => (b.label.toLowerCase().startsWith(q) ? 1 : 0) - (a.label.toLowerCase().startsWith(q) ? 1 : 0));
      list = list.slice(0, 200);
    }
  }
  function render() {
    dd.replaceChildren();
    list.forEach((o, i) => dd.append(h("div", { class: "o" + (i === idx ? " sel" : ""), onmousedown: ev => { ev.preventDefault(); choose(o); } },
      h("span", {}, o.label), o.hint ? h("small", {}, o.hint) : null)));
    if (allowNew) dd.append(h("div", { class: "o new" + (idx === list.length ? " sel" : ""), onmousedown: ev => { ev.preventDefault(); createNew(); } }, "+ " + (newLabel || "Create new") + (inp.value.trim() ? ': "' + inp.value.trim() + '"' : "")));
    if (!list.length && !allowNew) dd.append(h("div", { class: "o" }, h("span", { class: "muted" }, "Nothing found")));
    const s = $(".sel", dd); s && s.scrollIntoView({ block: "nearest" });
  }
  function show() { filt(); idx = Math.min(idx, list.length); if (idx < 0) idx = 0; open = true; dd.style.display = "block"; render(); }
  function hide() { open = false; dd.style.display = "none"; }
  function choose(o) { cur = o; inp.value = label(o); hide(); onpick && onpick(o); }
  function createNew() { const t = inp.value.trim(); hide(); onnew && onnew(t, o => { if (o) { cur = o; inp.value = label(o); onpick && onpick(o); } }); }
  inp.addEventListener("focus", () => { inp.select(); });
  inp.addEventListener("input", () => { cur = null; idx = 0; show(); });
  inp.addEventListener("keydown", e => {
    if (e.key === "ArrowDown") { e.preventDefault(); if (!open) show(); else { idx = Math.min(idx + 1, list.length - (allowNew ? 0 : 1)); render(); } }
    else if (e.key === "ArrowUp") { e.preventDefault(); if (open) { idx = Math.max(idx - 1, 0); render(); } }
    else if (e.key === "Enter") {
      if (open) {
        e.preventDefault(); e.stopPropagation();
        if (idx < list.length && list[idx]) { choose(list[idx]); inp.dispatchEvent(new CustomEvent("picked", { bubbles: true })); }
        else if (allowNew) createNew();
      } else if (!cur && inp.value.trim()) { e.preventDefault(); e.stopPropagation(); show(); }
    }
    else if (e.key === "Escape" && open) { e.stopPropagation(); hide(); }
    else if (e.key === "Tab" && open && list[idx] && !cur) { choose(list[idx]); }
  });
  inp.addEventListener("blur", () => {
    setTimeout(() => {
      if (!cur && inp.value.trim()) { const ex = options().find(o => o.label.toLowerCase() === inp.value.trim().toLowerCase()); if (ex) cur = ex; }
      if (cur) inp.value = label(cur); else if (clearable !== false || !inp.value.trim()) { if (!cur) inp.value = ""; }
      hide();
    }, 120);
  });
  if (value != null) api_.set(value);
  return api_;
}

/* option builders from masters */
const M = () => HL.S.masters;
function ledgerOptions(filter) {
  return M().ledgers.filter(l => (l.is_active || (filter && filter.includeInactive)) && (!filter || !filter.test || filter.test(l)))
    .map(l => ({ value: l.id, label: l.name, hint: l.group_name, data: l }));
}
function groupOptions(filter) { return M().groups.filter(g => !filter || filter(g)).map(g => ({ value: g.id, label: g.name, hint: g.nature })); }
function ccOptions(onlyActive) {
  const byId = Object.fromEntries(M().cost_centres.map(c => [c.id, c]));
  return M().cost_centres.filter(c => !onlyActive || c.is_active).map(c => ({
    value: c.id, label: c.name, hint: c.parent_id ? byId[c.parent_id].name : "" }));
}
async function loadMasters() {
  HL.S.masters = await HL.get("/api/masters");
  HL.S.status = await HL.get("/api/status");
  HL.updateStatusBar && HL.updateStatusBar();
  return HL.S.masters;
}

/* ---------- period ---------- */
function fyStartOf(iso) {
  const sm = HL.S.status.company.fy_start_month, d = toDate(iso);
  const y = d.getMonth() + 1 >= sm ? d.getFullYear() : d.getFullYear() - 1;
  return isoDate(new Date(y, sm - 1, 1));
}
function fyEndOf(startIso) { const d = toDate(startIso); return isoDate(new Date(d.getFullYear() + 1, d.getMonth(), 0)); }
function periodPresets() {
  const t = todayIso(), d = toDate(t), y = d.getFullYear(), m = d.getMonth();
  const fy = fyStartOf(t), pfy = fyStartOf(addDays(fy, -1));
  return [
    { id: "month", label: "This month", from: isoDate(new Date(y, m, 1)), to: lastDayOfMonth(y, m + 1) },
    { id: "lastmonth", label: "Last month", from: isoDate(new Date(y, m - 1, 1)), to: lastDayOfMonth(y, m) },
    { id: "fy", label: "This year (" + fy.slice(0, 4) + "-" + String(+fy.slice(2, 4) + 1).padStart(2, "0") + ")", from: fy, to: fyEndOf(fy) },
    { id: "lastfy", label: "Last year", from: pfy, to: fyEndOf(pfy) },
    { id: "all", label: "Everything", from: HL.S.status.company.books_begin, to: fyEndOf(fy) },
  ];
}
function getPeriod() {
  if (!HL.S.period) { const p = periodPresets().find(x => x.id === "fy"); HL.S.period = { id: "fy", from: p.from, to: p.to }; }
  return HL.S.period;
}
function periodBar(onchange, opts) {
  const P = getPeriod(), bar = h("div", { class: "period noprint" });
  const chips = h("div", { class: "chips" });
  for (const p of periodPresets()) chips.append(h("button", { type: "button", class: "chip" + (P.id === p.id ? " on" : ""), onclick: () => { HL.S.period = { id: p.id, from: p.from, to: p.to }; onchange(); } }, p.label));
  const f = h("input", { type: "text", value: showDate(P.from), "aria-label": "From date" });
  const t = h("input", { type: "text", value: showDate(P.to), "aria-label": "To date" });
  const apply = () => {
    const a = parseDateInput(f.value, P.from), b = parseDateInput(t.value, P.to);
    if (!a || !b) { say("Please type the dates like 01-04-2026.", "err"); return; }
    if (a > b) { say("The 'From' date is after the 'To' date.", "err"); return; }
    if (a !== P.from || b !== P.to) { HL.S.period = { id: "custom", from: a, to: b }; onchange(); }
  };
  f.addEventListener("change", apply); t.addEventListener("change", apply);
  [f, t].forEach(x => x.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); apply(); } }));
  bar.append(chips, h("span", { class: "muted" }, "From"), f, h("span", { class: "muted" }, "to"), t);
  if (opts && opts.extra) bar.append(opts.extra);
  return bar;
}
function periodText() { const P = getPeriod(); return showDate(P.from) + " to " + showDate(P.to); }

/* ---------- navigation ---------- */
HL.keys = [];                        // current right-hand key panel: [{k:'F5', label, fn, disabled}] | 'sep'
HL.setKeys = function (list) {
  HL.keys = list;
  const box = $("#keys"); box.replaceChildren();
  for (const k of list) {
    if (k === "sep") { box.append(h("div", { class: "sep" })); continue; }
    box.append(h("button", { type: "button", disabled: k.disabled, onclick: () => k.fn && k.fn() }, h("span", { class: "k" }, k.k || ""), k.label));
  }
};
HL.go = function (name, params, opts) {
  if (HL.cur && !(opts && opts.replace)) HL.stack.push(HL.cur);
  HL.cur = { name, params: params || {} };
  HL.render();
};
HL.back = function () {
  if (HL.cur && HL.cur.guard && !HL.cur.guard()) return;
  const prev = HL.stack.pop();
  if (!prev) { HL.cur = { name: "gateway", params: {} }; HL.render(); return; }
  HL.cur = prev; HL.render();
};
HL.refresh = () => HL.render();
HL.render = async function () {
  hideTip();
  const sc = $("#screen");
  const def = HL.screens[HL.cur.name];
  $("#crumb").textContent = def && def.title ? "› " + (typeof def.title === "function" ? def.title(HL.cur.params) : def.title) : "";
  sc.replaceChildren(h("p", { class: "muted" }, "Loading..."));
  HL.cur.guard = null;
  HL.onKey = null;
  HL.setKeys([{ k: "Esc", label: "Back", fn: HL.back }]);
  try { await def.render(sc, HL.cur.params); }
  catch (e) { sc.replaceChildren(h("div", { class: "banner err" }, e.message || String(e))); say(e.message, "err"); }
  if (!sc.contains(document.activeElement)) sc.focus({ preventScroll: true });
};
