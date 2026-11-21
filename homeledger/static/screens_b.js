/* Screens, part 2: statements, reports, activities, commodities, search */
"use strict";
const rowKeys = (tr, open) => tr.addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); open ? open() : tr.click(); }
  else if (e.key === "ArrowDown") { e.preventDefault(); let n = tr.nextElementSibling; while (n && n.style.display === "none") n = n.nextElementSibling; (n && n.tabIndex >= 0 ? n : tr).focus(); }
  else if (e.key === "ArrowUp") { e.preventDefault(); let n = tr.previousElementSibling; while (n && n.style.display === "none") n = n.previousElementSibling; (n && n.tabIndex >= 0 ? n : tr).focus(); }
});
const printKey = { k: "", label: "Print", fn: () => window.print() };
const BACK = { k: "Esc", label: "Back", fn: () => HL.back() };
function exportCsv(name, head, rows) {
  const q = v => '"' + String(v ?? "").replace(/"/g, '""') + '"';
  const csv = "﻿" + [head, ...rows].map(r => r.map(q).join(",")).join("\r\n");
  const a = h("a", { href: URL.createObjectURL(new Blob([csv], { type: "text/csv" })), download: name }); document.body.append(a); a.click(); a.remove();
}

/* ===================== ledger / group statement ===================== */
HL.screens.ledgers_pick = {
  title: "Ledger",
  async render(sc, params) {
    await loadMasters();
    const root = h("div", {}, h("h1", { class: "title" }, params.cb ? "Cash / Bank Book" : "Ledger"), h("p", { class: "sub" }, "Choose an account. Type to search, press Enter to open."));
    const opts = params.cb ? ledgerOptions({ test: l => !!l.cb_kind }) : ledgerOptions({ includeInactive: true });
    const inp = h("input", { type: "text", placeholder: "Type account name...", style: "width:100%;max-width:26rem", "aria-label": "Account" });
    const list = h("div", { class: "panel", style: "margin-top:.6rem;max-width:34rem;max-height:60vh;overflow:auto" });
    let idx = 0, cur = [];
    const paint = () => {
      const q = inp.value.trim().toLowerCase();
      cur = opts.filter(o => !q || q.split(/\s+/).every(w => o.label.toLowerCase().includes(w) || (o.hint || "").toLowerCase().includes(w)));
      idx = Math.min(idx, Math.max(0, cur.length - 1));
      list.replaceChildren(...cur.slice(0, 300).map((o, i) => h("div", { class: "combo" }, h("div", { class: "dd", style: "position:static;border:0;box-shadow:none;max-height:none" },
        h("div", { class: "o" + (i === idx ? " sel" : ""), onclick: () => open(o) }, h("span", {}, o.label), h("small", {}, o.hint))))));
      if (!cur.length) list.replaceChildren(h("div", { class: "empty" }, "No account matches."));
      const s = $(".sel", list); s && s.scrollIntoView({ block: "nearest" });
    };
    const open = o => HL.go("ledger", { ledger_id: o.value });
    inp.addEventListener("input", () => { idx = 0; paint(); });
    inp.addEventListener("keydown", e => { if (e.key === "ArrowDown") { idx = Math.min(idx + 1, cur.length - 1); paint(); e.preventDefault(); } else if (e.key === "ArrowUp") { idx = Math.max(0, idx - 1); paint(); e.preventDefault(); } else if (e.key === "Enter" && cur[idx]) { e.preventDefault(); open(cur[idx]); } });
    root.append(inp, list); sc.replaceChildren(root); paint(); inp.focus();
    HL.setKeys([BACK]);
  },
};
HL.screens.cashbook = { title: "Cash / Bank Book", render: (sc) => HL.screens.ledgers_pick.render(sc, { cb: true }) };

HL.screens.ledger = {
  title: p => p.group_id ? "Group Statement" : "Ledger",
  async render(sc, params) {
    await loadMasters();
    const P = getPeriod();
    const monthly = !!params.monthly;
    const arg = { from: P.from, to: P.to, ledger_id: params.ledger_id, group_id: params.group_id };
    const r = await HL.get(monthly ? "/api/monthly" : "/api/ledger_statement", arg);
    const reload = () => HL.refresh();
    const root = h("div", {}, h("h1", { class: "title" }, r.name), h("p", { class: "sub" }, (params.group_id ? "Group · " : "") + periodText() + (monthly ? " · Monthly summary" : "")), periodBar(reload));
    const real = r.nature === "asset" || r.nature === "liability";
    const tblHead = monthly ? ["Month", "Entries", "Debit", "Credit", "Closing balance"] : ["Date", "Particulars", "Cost Centre / Item", "Type", "No.", "Debit", "Credit", "Balance"];
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, tblHead.map((x, i) => h("th", { class: (monthly ? i > 0 : i >= 5) ? "r" : "" }, x)))));
    const tb = h("tbody", {}); t.append(tb);
    const trs = [];
    if (real || r.opening) tb.append(h("tr", {}, h("td", { colspan: monthly ? 4 : 7 }, h("b", {}, "Opening balance")), h("td", { class: "r" }, bal(r.opening))));
    if (monthly) {
      r.rows.forEach(m => { const tr = h("tr", { class: "row", tabindex: "0", onclick: () => { const [y, mm] = m.month.split("-"); HL.S.period = { id: "custom", from: m.month + "-01", to: lastDayOfMonth(+y, +mm) }; HL.cur.params = Object.assign({}, params, { monthly: false }); HL.refresh(); } },
        h("td", {}, monthLabel(m.month, true)), h("td", { class: "r" }, m.n || ""), h("td", { class: "r" }, m.dr ? inr(m.dr) : ""), h("td", { class: "r" }, m.cr ? inr(m.cr) : ""), h("td", { class: "r" }, real ? bal(m.closing) : "")); rowKeys(tr); trs.push(tr); tb.append(tr); });
    } else {
      r.rows.forEach(x => {
        const tr = h("tr", { class: "row", tabindex: "0", onclick: () => HL.go("voucher", { id: x.vid }) },
          h("td", {}, showDate(x.vdate) + (x.date_approx ? " ~" : "")),
          h("td", {}, (params.group_id ? x.ledger + " ← " : "") + (x.counter || "(opening entry)"), x.narration ? h("div", { class: "muted", style: "font-size:.85em" }, x.narration) : ""),
          h("td", {}, [x.cc, x.item ? x.item + (x.qty_milli ? " × " + qtyStr(x.qty_milli) + " " + (x.unit || "") : "") : ""].filter(Boolean).join(" · ")),
          h("td", {}, x.vtype), h("td", {}, x.number),
          h("td", { class: "r" }, x.debit_paise ? inr(x.debit_paise) : ""), h("td", { class: "r" }, x.credit_paise ? inr(x.credit_paise) : ""), h("td", { class: "r" }, real ? bal(x.balance) : ""));
        rowKeys(tr); trs.push(tr); tb.append(tr);
      });
    }
    tb.append(h("tr", { class: "total" }, h("td", { colspan: monthly ? 2 : 5 }, "Totals for the period"), h("td", { class: "r" }, inr(r.total_dr)), h("td", { class: "r" }, inr(r.total_cr)), h("td", { class: "r" }, real ? bal(r.closing) : "")));
    if (real) tb.append(h("tr", { class: "total" }, h("td", { colspan: monthly ? 4 : 7 }, "Closing balance"), h("td", { class: "r" }, bal(r.closing))));
    root.append(r.rows.length || real ? h("div", { class: "scroll" }, t) : h("div", { class: "panel empty" }, "No entries for this account in the selected period."));
    if (monthly && r.rows.some(x => x.dr || x.cr)) {
      root.append(chartCard({ title: "Month by month", sub: real ? "Debit and credit totals" : "Total per month", cls: "", legend: [{ name: "Debit", color: "var(--s2)" }, { name: "Credit", color: "var(--s1)" }],
        draw: () => barChart({ data: r.rows.map(m => ({ label: monthLabel(m.month).split(" ")[0], long: monthLabel(m.month, true), vals: [m.dr, m.cr] })), series: [{ name: "Debit", c: 2 }, { name: "Credit", c: 1 }] }) }));
    }
    sc.replaceChildren(root);
    if (trs[0]) trs[0].focus();
    HL.setKeys([BACK, { k: "", label: monthly ? "Show every entry" : "Monthly summary", fn: () => { HL.cur.params = Object.assign({}, params, { monthly: !monthly }); HL.refresh(); } }, "sep",
      { k: "", label: "Change account", fn: () => HL.go("ledgers_pick", {}, { replace: true }) },
      { k: "", label: "Export to Excel (CSV)", fn: () => exportCsv(r.name + ".csv", ["Date", "Particulars", "Type", "No", "Debit", "Credit", "Balance"], r.rows.map(x => monthly ? [x.month, "", "", "", inr(x.dr), inr(x.cr), ""] : [x.vdate, x.counter || "", x.vtype, x.number, x.debit_paise ? inr(x.debit_paise) : "", x.credit_paise ? inr(x.credit_paise) : "", x.balance != null ? bal(x.balance) : ""])) }, printKey]);
  },
};

/* ===================== trial balance ===================== */
HL.screens.tb = {
  title: "Trial Balance",
  async render(sc) {
    await loadMasters();
    const P = getPeriod();
    const r = await HL.get("/api/tb", { from: P.from, to: P.to });
    const root = h("div", {}, h("h1", { class: "title" }, "Trial Balance"), h("p", { class: "sub" }, periodText() + " · Enter opens a group or ledger"), periodBar(() => HL.refresh()));
    const open = HL._tbOpen || (HL._tbOpen = new Set());
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Particulars", "Opening", "Debit", "Credit", "Closing"].map((x, i) => h("th", { class: i ? "r" : "" }, x)))));
    const tb = h("tbody", {}); t.append(tb);
    const hasData = n => n.opening || n.dr || n.cr || n.closing;
    const addRow = (n, depth, parentOpen) => {
      if (n.type === "group" && !n.children.some(function z(c) { return c.type === "ledger" ? hasData(c) : c.children.some(z); }) && !hasData(n)) return;
      if (n.type === "ledger" && !hasData(n)) return;
      const isG = n.type === "group", key = "g" + n.id, isOpen = open.has(key);
      const tr = h("tr", { class: "row " + (isG ? "grp" : ""), tabindex: "0", onclick: () => { if (isG) { open.has(key) ? open.delete(key) : open.add(key); HL.refresh(); } else HL.go("ledger", { ledger_id: n.id }); } },
        h("td", { class: "ind" + depth }, (isG ? (isOpen ? "▾ " : "▸ ") : "") + n.name),
        h("td", { class: "r" }, n.opening ? bal(n.opening) : ""), h("td", { class: "r" }, n.dr ? inr(n.dr) : ""), h("td", { class: "r" }, n.cr ? inr(n.cr) : ""), h("td", { class: "r" }, n.closing ? bal(n.closing) : ""));
      if (isG) { const go = h("a", {}, ""); }
      rowKeys(tr); tb.append(tr);
      if (isG && isOpen) n.children.forEach(c => addRow(c, depth + 1));
    };
    r.tree.forEach(n => addRow(n, 0));
    r.extra.forEach(n => tb.append(h("tr", {}, h("td", { class: "ind0" }, h("i", {}, n.name)), h("td", { class: "r" }, bal(n.opening)), h("td", { class: "r" }), h("td", { class: "r" }), h("td", { class: "r" }, bal(n.closing)))));
    tb.append(h("tr", { class: "total" }, h("td", {}, "Grand Total"), h("td", { class: "r" }, inr(r.opening_dr) + " Dr / " + inr(r.opening_cr) + " Cr"), h("td", { class: "r" }, inr(r.total_dr)), h("td", { class: "r" }, inr(r.total_cr)), h("td", { class: "r" }, inr(r.closing_dr) + " Dr / " + inr(r.closing_cr) + " Cr")));
    const ok = r.closing_dr === r.closing_cr && r.total_dr === r.total_cr;
    root.append(h("div", { class: "banner " + (ok ? "ok" : "err") }, ok ? "The books are in balance: total debits equal total credits." : "The books do not balance. Open Utilities › Health Check for details."), h("div", { class: "scroll" }, t));
    sc.replaceChildren(root); const f = $("tbody tr", root); f && f.focus();
    HL.setKeys([BACK, { k: "", label: "Expand all", fn: () => { const walk = n => { if (n.type === "group") { open.add("g" + n.id); n.children.forEach(walk); } }; r.tree.forEach(walk); HL.refresh(); } }, { k: "", label: "Collapse all", fn: () => { open.clear(); HL.refresh(); } }, printKey]);
  },
};

/* ===================== P&L and balance sheet (two-sided, Tally layout) ===================== */
function sideLines(nodes, depth, out, kind) {
  for (const n of nodes) {
    out.push({ name: n.name, amount: n.amount, depth, group: n.type === "group", id: n.id, kind });
    if (n.type === "group" && depth < 2) sideLines(n.children, depth + 1, out, kind);
  }
}
function sideEl(title, lines, total, extra) {
  const el = h("div", { class: "side" }, h("h3", {}, title));
  for (const l of lines) {
    const can = l.id != null;
    el.append(h("div", { class: "ln" + (l.group ? " g" : "") + (l.depth ? " l" + Math.min(l.depth, 2) : "") + (can ? " can" : ""), tabindex: can ? "0" : null,
      onclick: can ? () => HL.go("ledger", l.group ? { group_id: l.id } : { ledger_id: l.id }) : null }, h("span", {}, l.name), h("span", { class: "num" }, inr(l.amount))));
  }
  (extra || []).forEach(x => el.append(h("div", { class: "ln g" }, h("span", {}, x.name), h("span", { class: "num" }, inr(x.amount)))));
  el.append(h("div", { class: "ln t" }, h("span", {}, "Total"), h("span", { class: "num" }, inr(total))));
  return el;
}
HL.screens.pnl = {
  title: "Profit & Loss",
  async render(sc) {
    await loadMasters();
    const P = getPeriod(), r = await HL.get("/api/pnl", { from: P.from, to: P.to });
    const e = [], i = [];
    sideLines(r.expenses, 0, e, "e"); sideLines(r.income, 0, i, "i");
    const lossSide = r.net < 0 ? [{ name: "Net Loss", amount: -r.net }] : [], profSide = r.net > 0 ? [{ name: "Net Profit (income more than spending)", amount: r.net }] : [];
    const tot = Math.max(r.total_expense + profSide.reduce((s, x) => s + x.amount, 0), r.total_income + lossSide.reduce((s, x) => s + x.amount, 0));
    const root = h("div", {}, h("h1", { class: "title" }, "Profit & Loss Account"), h("p", { class: "sub" }, periodText() + " · Click a line for its statement"), periodBar(() => HL.refresh()));
    root.append(h("div", { class: "two" }, sideEl("Spending (Expenses)", e, tot, profSide), sideEl("Income", i, tot, lossSide)));
    root.append(h("p", { class: "hint" }, "Asset purchases (land, vehicles, animals bought as stock) and loan repayments are not spending here: they appear in the Balance Sheet."));
    sc.replaceChildren(root); HL.setKeys([BACK, printKey]);
  },
};
HL.screens.bs = {
  title: "Balance Sheet",
  async render(sc) {
    await loadMasters();
    const P = getPeriod(), r = await HL.get("/api/bs", { from: P.from, to: P.to });
    const a = [], l = [];
    sideLines(r.assets, 0, a, "a"); sideLines(r.liabilities, 0, l, "l");
    const root = h("div", {}, h("h1", { class: "title" }, "Balance Sheet"), h("p", { class: "sub" }, "As on " + showDate(P.to) + " · Click a line for its statement"), periodBar(() => HL.refresh()));
    const tot = Math.max(r.total_assets, r.total_liabilities);
    root.append(h("div", { class: "two" }, sideEl("Liabilities & Capital (what you owe)", l, tot, r.extra), sideEl("Assets (what you own)", a, tot)));
    if (!r.balanced) root.append(h("div", { class: "banner err" }, "The Balance Sheet does not balance (difference " + rs(Math.abs(r.total_assets - r.total_liabilities)) + "). Check the opening balances (Gateway › Opening Balances) or run Utilities › Health Check."));
    sc.replaceChildren(root); HL.setKeys([BACK, printKey]);
  },
};

/* ===================== activities (farm / household) ===================== */
HL.screens.activities = {
  title: "Cost Centres",
  async render(sc) {
    await loadMasters();
    const P = getPeriod(), r = await HL.get("/api/activities", { from: P.from, to: P.to });
    const byParent = {}; r.rows.forEach(c => (byParent[c.parent_id || 0] ||= []).push(c));
    const roll = c => { const kids = (byParent[c.id] || []).map(roll); return { c, kids, income: c.income + kids.reduce((s, k) => s + k.income, 0), expense: c.expense + kids.reduce((s, k) => s + k.expense, 0), assets: c.assets_net + kids.reduce((s, k) => s + k.assets, 0) }; };
    const tree = (byParent[0] || []).map(roll);
    const root = h("div", {}, h("h1", { class: "title" }, "Cost Centres"), h("p", { class: "sub" }, periodText() + " · income and spending tagged to each cost centre"), periodBar(() => HL.refresh()));
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Cost Centre", "Income", "Spending", "Surplus / (Shortfall)", "Assets bought"].map((x, i) => h("th", { class: i ? "r" : "" }, x)))));
    const tb = h("tbody", {}); t.append(tb);
    const add = (n, depth) => {
      if (!n.income && !n.expense && !n.assets && depth > 0 && !n.c.is_active) return;
      const net = n.income - n.expense;
      const tr = h("tr", { class: "row" + (depth ? "" : " grp"), tabindex: "0", onclick: () => HL.go("activity", { cc_id: n.c.id }) },
        h("td", { class: "ind" + depth }, n.c.name), h("td", { class: "r" }, n.income ? inr(n.income) : ""), h("td", { class: "r" }, n.expense ? inr(n.expense) : ""),
        h("td", { class: "r " + (net < 0 ? "neg" : "") }, net ? (net < 0 ? "(" + inr(-net) + ")" : inr(net)) : ""), h("td", { class: "r" }, n.assets ? inr(n.assets) : ""));
      rowKeys(tr); tb.append(tr); n.kids.forEach(k => add(k, depth + 1));
    };
    tree.forEach(n => add(n, 0));
    const u = r.unallocated;
    if (u.income || u.expense) { const tr = h("tr", { class: "row", tabindex: "0", onclick: () => HL.go("activity", { cc_id: 0 }) }, h("td", {}, h("i", {}, "Not tagged to any activity")), h("td", { class: "r" }, u.income ? inr(u.income) : ""), h("td", { class: "r" }, u.expense ? inr(u.expense) : ""), h("td", { class: "r" }, inr(u.income - u.expense)), h("td", { class: "r" }, "")); rowKeys(tr); tb.append(tr); }
    root.append(h("div", { class: "scroll" }, t));
    const kids = tree.flatMap(n => n.kids).filter(k => k.expense > 0 || k.income > 0);
    if (kids.length) {
      const g = h("div", { class: "dash-grid", style: "margin-top:.8rem" });
      g.append(chartCard({ cls: "c12", title: "Income and spending by cost centre", sub: "Click a bar to open the cost centre", legend: [{ name: "Income", color: "var(--s1)" }, { name: "Spending", color: "var(--s2)" }],
        draw: () => barChart({ data: kids.map(k => ({ label: k.c.name.length > 9 ? k.c.name.slice(0, 8) + "…" : k.c.name, long: k.c.name, id: k.c.id, vals: [k.income, k.expense] })), series: [{ name: "Income", c: 1 }, { name: "Spending", c: 2 }], onbar: d => HL.go("activity", { cc_id: d.id }) }),
        table: () => simpleTable(["Cost Centre", "Income", "Spending"], kids.map(k => [k.c.name, rs(k.income), rs(k.expense)])) }));
      root.append(g);
    }
    root.append(h("p", { class: "hint" }, "'Surplus' here is simple income less spending for the cost centre."));
    sc.replaceChildren(root); const f = $("tbody tr", root); f && f.focus(); HL.setKeys([BACK, printKey]);
  },
};
HL.screens.activity = {
  title: "Cost Centre",
  async render(sc, params) {
    await loadMasters();
    const P = getPeriod(), r = await HL.get("/api/activity", { from: P.from, to: P.to, cc_id: params.cc_id });
    const root = h("div", {}, h("h1", { class: "title" }, r.name), h("p", { class: "sub" }, periodText()), periodBar(() => HL.refresh()));
    const inc = r.ledgers.filter(l => l.nature === "income"), exp = r.ledgers.filter(l => l.nature === "expense"), oth = r.ledgers.filter(l => l.nature !== "income" && l.nature !== "expense");
    const ti = inc.reduce((s, l) => s + l.cr - l.dr, 0), te = exp.reduce((s, l) => s + l.dr - l.cr, 0);
    root.append(h("div", { class: "dash-grid" },
      h("div", { class: "card kpi c4" }, h("div", { class: "lab" }, "Income"), h("div", { class: "val" }, rs(ti, 0))),
      h("div", { class: "card kpi c4" }, h("div", { class: "lab" }, "Spending"), h("div", { class: "val" }, rs(te, 0))),
      h("div", { class: "card kpi c4" }, h("div", { class: "lab" }, ti >= te ? "Surplus" : "Shortfall"), h("div", { class: "val " + (ti < te ? "neg" : "pos") }, rs(Math.abs(ti - te), 0)))));
    const mk = (title, list, sign, color) => h("div", { class: "card c6", style: "margin-top:.8rem" }, h("h3", {}, title), hbars(list.map(l => ({ label: l.name, value: sign * (l.cr - l.dr), color: "var(--s" + color + ")", onclick: () => HL.go("ledger", { ledger_id: l.id }) })).filter(x => x.value > 0)));
    root.append(h("div", { class: "dash-grid" }, mk("Spent on", exp.map(l => ({ ...l, cr: l.cr, dr: l.dr })), -1, 2), mk("Earned from", inc, 1, 1)));
    if (oth.length) root.append(h("div", { class: "card", style: "margin-top:.8rem" }, h("h3", {}, "Assets and other entries tagged here"), simpleTable(["Account", "Debit", "Credit"], oth.map(l => [l.name, rs(l.dr), rs(l.cr)]))));
    root.append(h("div", { class: "dash-grid", style: "margin-top:.8rem" }, chartCard({ cls: "c12", title: "Month by month", legend: [{ name: "Income", color: "var(--s1)" }, { name: "Spending", color: "var(--s2)" }],
      draw: () => barChart({ data: r.months.map(m => ({ label: monthLabel(m.month).split(" ")[0], long: monthLabel(m.month, true), vals: [m.income, m.expense] })), series: [{ name: "Income", c: 1 }, { name: "Spending", c: 2 }] }),
      table: () => simpleTable(["Month", "Income", "Spending"], r.months.map(m => [monthLabel(m.month, true), rs(m.income), rs(m.expense)])) })));
    if (params.cc_id) root.append(h("div", { style: "margin-top:.6rem" }, h("button", { class: "btn", onclick: () => HL.go("search", { cc_id: params.cc_id, name: r.name }) }, "See every entry for " + r.name)));
    sc.replaceChildren(root); HL.setKeys([BACK, printKey]);
  },
};

/* ===================== commodities ===================== */
HL.screens.commodities = {
  title: "Commodities",
  async render(sc) {
    await loadMasters();
    const P = getPeriod(), r = await HL.get("/api/commodities", { from: P.from, to: P.to });
    const root = h("div", {}, h("h1", { class: "title" }, "Commodities (Items)"), h("p", { class: "sub" }, periodText() + " · anything you typed in the 'Item' box of a voucher"), periodBar(() => HL.refresh()));
    if (!r.rows.length) { root.append(h("div", { class: "panel empty" }, "No items yet. When you enter a payment or sale, fill the 'Item' (and Qty / Unit) box, for example Urea, 50, kg, and it will show up here with average prices.")); sc.replaceChildren(root); HL.setKeys([BACK]); return; }
    const filt = h("input", { type: "search", placeholder: "Filter items...", "aria-label": "Filter items" });
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Item", "Unit", "Entries", "Bought / paid", "Qty bought", "Avg buy price", "Sold / received", "Qty sold", "Avg sell price"].map((x, i) => h("th", { class: i > 1 ? "r" : "" }, x)))));
    const tb = h("tbody", {}); t.append(tb);
    const trs = [];
    r.rows.forEach(x => {
      const tr = h("tr", { class: "row", tabindex: "0", "data-t": x.item.toLowerCase(), onclick: () => HL.go("commodity", { item: x.item, unit: x.unit }) },
        h("td", {}, x.item), h("td", {}, x.unit), h("td", { class: "r" }, x.n), h("td", { class: "r" }, x.paid ? inr(x.paid) : ""), h("td", { class: "r" }, x.qty_in ? qtyStr(x.qty_in) : ""),
        h("td", { class: "r" }, x.avg_buy ? inr(x.avg_buy) + "/" + (x.unit || "unit") : ""), h("td", { class: "r" }, x.received ? inr(x.received) : ""), h("td", { class: "r" }, x.qty_out ? qtyStr(x.qty_out) : ""), h("td", { class: "r" }, x.avg_sell ? inr(x.avg_sell) + "/" + (x.unit || "unit") : ""));
      rowKeys(tr); trs.push(tr); tb.append(tr);
    });
    filt.addEventListener("input", () => { const q = filt.value.toLowerCase().trim(); trs.forEach(tr => tr.style.display = !q || tr.dataset.t.includes(q) ? "" : "none"); });
    root.append(h("div", { style: "margin-bottom:.6rem" }, filt), h("div", { class: "scroll" }, t));
    const top = r.rows.filter(x => x.paid > 0).slice(0, 8);
    if (top.length) root.append(h("div", { class: "dash-grid", style: "margin-top:.8rem" }, h("div", { class: "card c12" }, h("h3", {}, "Most spent on"), hbars(top.map(x => ({ label: x.item + (x.unit ? " (" + x.unit + ")" : ""), value: x.paid, onclick: () => HL.go("commodity", { item: x.item, unit: x.unit }) })), { color: 2 }))));
    root.append(h("p", { class: "hint" }, "Average price is worked out only from entries that have a quantity. Different units (kg vs bag) are kept separate, never mixed."));
    sc.replaceChildren(root); trs[0] && trs[0].focus(); HL.setKeys([BACK, printKey]);
  },
};
HL.screens.commodity = {
  title: p => p.item,
  async render(sc, params) {
    await loadMasters();
    const P = getPeriod(), r = await HL.get("/api/commodity", { from: P.from, to: P.to, item: params.item, unit: params.unit || "" });
    const root = h("div", {}, h("h1", { class: "title" }, r.item + (r.unit ? " (" + r.unit + ")" : "")), h("p", { class: "sub" }, periodText()), periodBar(() => HL.refresh()));
    const g = h("div", { class: "dash-grid" });
    const lab = m => monthLabel(m.month).split(" ")[0], lng = m => monthLabel(m.month, true);
    g.append(chartCard({ cls: "c6", title: "Money spent / received", legend: [{ name: "Paid", color: "var(--s2)" }, { name: "Received", color: "var(--s1)" }],
      draw: () => barChart({ data: r.rows.map(m => ({ label: lab(m), long: lng(m), vals: [m.paid, m.received] })), series: [{ name: "Paid", c: 2 }, { name: "Received", c: 1 }] }),
      table: () => simpleTable(["Month", "Paid", "Received"], r.rows.map(m => [lng(m), rs(m.paid), rs(m.received)])) }));
    const pr = r.rows.filter(m => m.avg_buy || m.avg_sell);
    g.append(chartCard({ cls: "c6", title: "Price per " + (r.unit || "unit"), sub: "Average price in months with quantity entered", legend: [{ name: "Bought at", color: "var(--s2)" }, { name: "Sold at", color: "var(--s1)" }],
      draw: () => pr.length ? lineChart({ data: pr.map(m => ({ label: lab(m), long: lng(m), vals: [m.avg_buy, m.avg_sell] })), series: [{ name: "Bought at", c: 2 }, { name: "Sold at", c: 1 }] }) : h("div", { class: "empty" }, "No quantities entered yet, so no price trend."),
      table: () => simpleTable(["Month", "Qty bought", "Avg buy", "Qty sold", "Avg sell"], r.rows.map(m => [lng(m), qtyStr(m.qty_in), m.avg_buy ? rs(m.avg_buy) : "", qtyStr(m.qty_out), m.avg_sell ? rs(m.avg_sell) : ""])) }));
    root.append(g, h("div", { style: "margin-top:.6rem" }, h("button", { class: "btn", onclick: () => HL.go("search", { item: r.item }) }, "See every entry for " + r.item)));
    sc.replaceChildren(root); HL.setKeys([BACK, printKey]);
  },
};

/* ===================== search ===================== */
HL.screens.search = {
  title: "Search",
  async render(sc, params) {
    await loadMasters();
    const q = h("input", { type: "text", value: params.q || "", placeholder: "Words, name, or amount (e.g. urea, milk, 3000)", style: "width:100%", "aria-label": "Search words" });
    const f = h("input", { type: "text", value: params.from ? showDate(params.from) : "", placeholder: "dd-mm-yyyy", "aria-label": "From date" });
    const t = h("input", { type: "text", value: params.to ? showDate(params.to) : "", placeholder: "dd-mm-yyyy", "aria-label": "To date" });
    const item = h("input", { type: "text", list: "dl-s-items", value: params.item || "", "aria-label": "Item" });
    const dl = h("datalist", { id: "dl-s-items" }, M().items.map(i => h("option", { value: i.item })));
    const led = picker({ options: () => ledgerOptions({ includeInactive: true }), value: params.ledger_id, placeholder: "Any account" });
    const cc = picker({ options: () => ccOptions(false), value: params.cc_id, placeholder: "Any cost centre" });
    const vt = h("select", { "aria-label": "Voucher type" }, h("option", { value: "" }, "Any type"), ["Payment", "Receipt", "Contra", "Journal", "Sales", "Purchase", "Credit Note", "Debit Note", "Memorandum", "Reversing Journal", "Sales Order", "Purchase Order", "Delivery Note", "Receipt Note", "Stock Journal"].map(x => h("option", { value: x }, x)));
    const amin = h("input", { type: "text", inputmode: "decimal", placeholder: "from ₹", "aria-label": "Minimum amount" }), amax = h("input", { type: "text", inputmode: "decimal", placeholder: "to ₹", "aria-label": "Maximum amount" });
    const all = h("input", { type: "checkbox" });
    const out = h("div", {});
    const root = h("div", {}, h("h1", { class: "title" }, "Search" + (params.name ? " · " + params.name : "")), h("p", { class: "sub" }, "Find any entry by words, date, account, activity, item or amount. Leave boxes empty to ignore them."), h("div", { class: "panel", style: "padding:.8rem" },
      h("div", { class: "fgrid" },
        h("label", { class: "f", style: "grid-column:1/-1" }, "Words", q), h("label", { class: "f" }, "From date", f), h("label", { class: "f" }, "To date", t),
        h("label", { class: "f" }, "Account", led.el), h("label", { class: "f" }, "Cost Centre", cc.el), h("label", { class: "f" }, "Item", item), h("label", { class: "f" }, "Voucher type", vt),
        h("label", { class: "f" }, "Amount between", h("span", { class: "row", style: "gap:.3rem;flex-wrap:nowrap" }, amin, amax))),
      h("div", { class: "row", style: "margin-top:.7rem" }, h("button", { class: "btn primary", type: "button", onclick: () => run() }, "Search"), h("button", { class: "btn", type: "button", onclick: () => { HL.go("search", {}, { replace: true }); } }, "Clear"),
        h("label", { class: "muted" }, all, " Include the Cash/Bank side of each entry"))), dl, out);
    sc.replaceChildren(root);
    enterAsTab(root, () => run());
    async function run() {
      try {
        const a = {};
        if (f.value.trim()) { a.from = parseDateInput(f.value); if (!a.from) throw new Error("From date is not valid."); }
        if (t.value.trim()) { a.to = parseDateInput(t.value); if (!a.to) throw new Error("To date is not valid."); }
        Object.assign(a, { q: q.value, item: item.value, ledger_id: led.value, cc_id: cc.value, vtype: vt.value, amin: amin.value, amax: amax.value, scope: all.checked ? "all" : "main" });
        const r = await HL.get("/api/search", a);
        const tbl = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Date", "Account", "Item", "Cost Centre", "Type", "No.", "Debit", "Credit"].map((x, i) => h("th", { class: i > 5 ? "r" : "" }, x)))));
        const tb = h("tbody", {}); tbl.append(tb); const trs = [];
        r.rows.forEach(x => { const tr = h("tr", { class: "row", tabindex: "0", title: x.narration, onclick: () => HL.go("voucher", { id: x.vid }) },
          h("td", {}, showDate(x.vdate)), h("td", {}, x.ledger, x.narration ? h("div", { class: "muted", style: "font-size:.85em" }, x.narration) : ""), h("td", {}, x.item ? x.item + (x.qty_milli ? " × " + qtyStr(x.qty_milli) + " " + (x.unit || "") : "") : ""), h("td", {}, x.cc || ""), h("td", {}, x.vtype), h("td", {}, x.number),
          h("td", { class: "r" }, x.debit_paise ? inr(x.debit_paise) : ""), h("td", { class: "r" }, x.credit_paise ? inr(x.credit_paise) : "")); rowKeys(tr); trs.push(tr); tb.append(tr); });
        tb.append(h("tr", { class: "total" }, h("td", { colspan: 6 }, r.count + " matching lines"), h("td", { class: "r" }, inr(r.total_dr)), h("td", { class: "r" }, inr(r.total_cr))));
        out.replaceChildren(h("div", { class: "banner", style: "margin-top:.8rem" }, h("div", {}, h("b", {}, r.count + " found. "), "Spent / debit side: ", h("b", {}, rs(r.total_dr)), " · Received / credit side: ", h("b", {}, rs(r.total_cr)), ". (Spending shows as Debit; income shows as Credit.)")),
          r.count ? h("div", { class: "scroll" }, tbl) : h("div", { class: "panel empty" }, "Nothing matches. Try fewer words or a wider date range."), r.truncated ? h("p", { class: "muted" }, "Showing the newest 1500. Narrow the search to see the rest.") : "");
        if (trs[0]) trs[0].focus({ preventScroll: true });
        HL.lastSearch = a;
      } catch (e) { fail(e); }
    }
    HL.onKey = e => { if (e.key === "Enter" && e.ctrlKey) { run(); return true; } };
    HL.setKeys([{ k: "Enter", label: "Search", fn: run }, BACK, { k: "", label: "Export results (CSV)", fn: () => { const tr = $$("tbody tr.row", out); exportCsv("search.csv", ["Date", "Account", "Item", "Cost Centre", "Type", "No", "Debit", "Credit"], tr.map(r => $$("td", r).map(c => c.firstChild ? c.firstChild.textContent : ""))); } }, printKey]);
    if (params.q || params.item || params.ledger_id || params.cc_id || params.from) run(); else q.focus();
  },
};


HL.screens.ratios = {
  title: "Ratio Analysis",
  async render(sc) {
    await loadMasters();
    const P = getPeriod();
    const r = await HL.get("/api/ratios", { from: P.from, to: P.to });
    const fmt = it => it.value === null ? "n/a" : it.kind === "money" ? rs(it.value) : it.kind === "pct" ? (it.value / 100).toFixed(2) + " %" : (it.value / 100).toFixed(2) + " : 1";
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, h("th", {}, "Particulars"), h("th", { class: "r" }, "Value"))));
    const tb = h("tbody", {}); t.append(tb);
    r.items.forEach(it => tb.append(h("tr", {}, h("td", {}, it.name), h("td", { class: "r" }, fmt(it)))));
    sc.replaceChildren(h("div", {}, h("h1", { class: "title" }, "Ratio Analysis"), h("p", { class: "sub" }, periodText()), periodBar(() => HL.refresh()), t, h("p", { class: "hint" }, r.note)));
    HL.setKeys([BACK]);
  },
};


function outstandingScreen(kind, title) {
  return {
    title,
    async render(sc) {
      await loadMasters();
      const P = getPeriod();
      const r = await HL.get("/api/outstanding", { kind, to: P.to });
      const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Party", "Oldest", "0-30 days", "31-60", "61-90", "Over 90", "Pending"].map((x, i) => h("th", { class: i > 1 ? "r" : "" }, x)))));
      const tb = h("tbody", {}); t.append(tb);
      r.rows.forEach(x => {
        const tr = h("tr", { class: "row", tabindex: "0", onclick: () => HL.go("ledger", { ledger_id: x.ledger_id }) },
          h("td", {}, x.name + (x.advance ? "  (advance " + rs(x.advance) + ")" : ""), x.bills && x.bills.length ? h("div", { class: "muted", style: "font-size:.85em" }, x.bills.map(bl => bl.ref + " " + inr(Math.abs(bl.pending)) + (bl.due ? " (due " + showDate(bl.due) + ")" : "")).join("  ·  ") + (x.on_account ? "  ·  on account " + inr(x.on_account) : "")) : null), h("td", {}, x.brought_forward ? "Opening" : x.oldest ? showDate(x.oldest) : ""),
          ...x.buckets.map(b => h("td", { class: "r" }, b ? inr(b) : "")), h("td", { class: "r" }, inr(x.due)));
        rowKeys(tr); tb.append(tr);
      });
      if (!r.rows.length) tb.append(h("tr", {}, h("td", { colspan: 7, class: "empty" }, "Nothing is pending.")));
      else tb.append(h("tr", { class: "total" }, h("td", {}, "Total"), h("td", {}), ...r.buckets.map(b => h("td", { class: "r" }, inr(b))), h("td", { class: "r" }, inr(r.total))));
      sc.replaceChildren(h("div", {}, h("h1", { class: "title" }, title), h("p", { class: "sub" }, "As on " + showDate(r.as_on) + " · Enter opens the ledger"), periodBar(() => HL.refresh()), t, h("p", { class: "hint" }, r.note)));
      HL.setKeys([BACK]);
      const f = $("tbody tr", sc); f && f.focus();
    },
  };
}
HL.screens.receivables = outstandingScreen("receivable", "Bills Receivable (Outstanding)");
HL.screens.payables = outstandingScreen("payable", "Bills Payable (Outstanding)");


HL.screens.cashflow = {
  title: "Cash Flow",
  async render(sc) {
    await loadMasters();
    const P = getPeriod();
    const r = await HL.get("/api/cashflow", { from: P.from, to: P.to });
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, h("th", {}, "Particulars"), h("th", { class: "r" }, "Amount"))));
    const tb = h("tbody", {}); t.append(tb);
    const line = (n, v, cls) => tb.append(h("tr", { class: cls || "" }, h("td", { class: cls ? "" : "ind1" }, n), h("td", { class: "r" }, inr(v))));
    line("Opening Cash and Bank", r.opening, "grp");
    tb.append(h("tr", { class: "grp" }, h("td", {}, "Money received from"), h("td", {})));
    r.inflow.forEach(x => line(x[0], x[1])); line("Total received", r.total_in, "total");
    tb.append(h("tr", { class: "grp" }, h("td", {}, "Money paid to"), h("td", {})));
    r.outflow.forEach(x => line(x[0], x[1])); line("Total paid", r.total_out, "total");
    line("Closing Cash and Bank", r.closing, "grp");
    sc.replaceChildren(h("div", {}, h("h1", { class: "title" }, "Cash Flow"), h("p", { class: "sub" }, periodText() + " · movement through Cash and Bank, by the account on the other side"), periodBar(() => HL.refresh()), t,
      h("div", { class: "banner " + (r.check ? "ok" : "err") }, r.check ? "Opening + received - paid equals closing." : "These figures do not add up. Open Utilities > Health Check.")));
    HL.setKeys([BACK]);
  },
};


HL.screens.bankrec = {
  title: "Bank Reconciliation",
  async render(sc, params) {
    await loadMasters();
    const P = getPeriod();
    const banks = HL.S.masters.ledgers.filter(l => l.cb_kind === "bank" && l.is_active !== 0);
    const root = h("div", {}, h("h1", { class: "title" }, "Bank Reconciliation"));
    if (!banks.length) { root.append(h("div", { class: "panel empty" }, "There is no bank account yet. Create a ledger under Bank Accounts first.")); sc.replaceChildren(root); HL.setKeys([BACK]); return; }
    const sel = h("select", { "aria-label": "Bank account" }, banks.map(b => h("option", { value: b.id }, b.name)));
    sel.value = String(params.ledger_id || banks[0].id);
    sel.onchange = () => { HL.cur.params = Object.assign({}, params, { ledger_id: sel.value }); HL.refresh(); };
    const r = await HL.get("/api/bankrec", { ledger_id: sel.value, to: P.to });
    root.append(h("p", { class: "sub" }, "As on " + showDate(r.as_on) + " · type the date the bank processed each entry (from your statement); leave empty if it has not cleared"), periodBar(() => HL.refresh(), { extra: sel }));
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Date", "Type", "No.", "Reference", "Debit", "Credit", "Bank date"].map((x, i) => h("th", { class: i === 4 || i === 5 ? "r" : "" }, x)))));
    const tb = h("tbody", {}); t.append(tb);
    r.rows.forEach(x => {
      const inp = h("input", { type: "text", value: x.bank_date ? showDate(x.bank_date) : "", style: "width:9rem", "aria-label": "Bank date", placeholder: "dd-mm-yyyy" });
      inp.addEventListener("change", async () => {
        try {
          const iso = inp.value.trim() ? parseDateInput(inp.value, x.vdate) : "";
          if (inp.value.trim() && !iso) { say("Please type the date like 15-11-2026.", "err"); return; }
          await HL.post("/api/bank/date", { voucher_id: x.vid, ledger_id: r.ledger_id, bank_date: iso });
          HL.refresh();
        } catch (e) { say(e.message || "Could not save.", "err"); }
      });
      tb.append(h("tr", { class: x.cleared ? "" : "optional" }, h("td", {}, showDate(x.vdate)), h("td", {}, x.vtype), h("td", {}, x.number), h("td", {}, x.ref || x.narration || ""),
        h("td", { class: "r" }, x.dr ? inr(x.dr) : ""), h("td", { class: "r" }, x.cr ? inr(x.cr) : ""), h("td", {}, inp)));
    });
    if (!r.rows.length) tb.append(h("tr", {}, h("td", { colspan: 7, class: "empty" }, "No entries in this bank account yet.")));
    const sum = h("table", { class: "tbl", style: "max-width:34rem;margin-top:1rem" }, h("tbody", {},
      h("tr", {}, h("td", {}, "Balance as per company books"), h("td", { class: "r" }, bal(r.books))),
      h("tr", {}, h("td", {}, "Amounts not yet reflected in bank"), h("td", { class: "r" }, bal(r.uncleared_net))),
      h("tr", { class: "total" }, h("td", {}, "Balance as per bank (should match the statement)"), h("td", { class: "r" }, bal(r.bank)))));
    root.append(t, sum);
    sc.replaceChildren(root); HL.setKeys([BACK]);
  },
};


/* ===================== Stock Items (master) and Stock Summary ===================== */
HL.screens.stockitems = {
  title: "Stock Items",
  async render(sc, params) {
    const items = await HL.get("/api/stockitems");
    const root = h("div", {}, h("h1", { class: "title" }, "Stock Items"), h("p", { class: "sub" }, "Things you buy and sell by quantity. In a voucher, type the same name in the Item box, with Qty and Unit."));
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Name", "Unit", "Opening qty", "Opening value"].map((x, i) => h("th", { class: i > 1 ? "r" : "" }, x)))));
    const tb = h("tbody", {}); t.append(tb);
    const edit = it => {
      const nm = h("input", { type: "text", value: it ? it.name : "", maxlength: "60", "aria-label": "Name" });
      const un = h("input", { type: "text", value: it ? it.unit : "", maxlength: "12", "aria-label": "Unit", placeholder: "kg, nos, litre..." });
      const oq = h("input", { type: "text", inputmode: "decimal", value: it && it.opening_qty_milli ? (it.opening_qty_milli / 1000).toString() : "", "aria-label": "Opening quantity" });
      const ov = h("input", { type: "text", inputmode: "decimal", value: it && it.opening_value_paise ? (it.opening_value_paise / 100).toFixed(2) : "", "aria-label": "Opening value" });
      const body = h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f" }, "Name", nm), h("label", { class: "f" }, "Unit", un), h("label", { class: "f" }, "Opening quantity", oq), h("label", { class: "f" }, "Opening value (₹)", ov));
      const m = modal({ title: it ? "Stock Item Alteration" : "Stock Item Creation", body, buttons: [it ? { label: "Delete", cls: "danger", onclick: async m2 => { if (await confirmBox("Delete stock item?", "Only items never used in a voucher can be deleted.", "Delete", true)) { try { await HL.post("/api/stockitem/delete", { id: it.id }); m2.close(); HL.refresh(); } catch (e) { fail(e); } } } } : null, { label: "Cancel", onclick: m => m.close() }, { label: "Accept", cls: "primary", onclick: save }].filter(Boolean) });
      enterAsTab(body, save);
      async function save() { try { await HL.post("/api/stockitem/save", { id: it && it.id, name: nm.value, unit: un.value, opening_qty: oq.value, opening_value: ov.value }); m.close(); HL.refresh(); } catch (e) { fail(e); } }
    };
    items.forEach(it => { const tr = h("tr", { class: "row", tabindex: "0", onclick: () => edit(it) }, h("td", {}, it.name), h("td", {}, it.unit), h("td", { class: "r" }, it.opening_qty_milli ? qtyStr(it.opening_qty_milli) : ""), h("td", { class: "r" }, it.opening_value_paise ? inr(it.opening_value_paise) : "")); rowKeys(tr); tb.append(tr); });
    if (!items.length) tb.append(h("tr", {}, h("td", { colspan: 4, class: "empty" }, "No stock items yet. Press Alt+C to create one.")));
    root.append(t);
    sc.replaceChildren(root);
    HL.setKeys([BACK, { k: "Alt+C", label: "Create stock item", fn: () => edit(null) }]);
    const f = $("tbody tr.row", root); f && f.focus();
    if (params.create) { params.create = 0; setTimeout(() => edit(null), 60); }
  },
};

HL.screens.stocksummary = {
  title: "Stock Summary",
  async render(sc) {
    await loadMasters();
    const P = getPeriod();
    const r = await HL.get("/api/stocksummary", { from: P.from, to: P.to });
    const q = v => v ? qtyStr(v) : "";
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Item", "Unit", "Opening", "Inwards", "Outwards", "Closing qty", "Closing value"].map((x, i) => h("th", { class: i > 1 ? "r" : "" }, x)))));
    const tb = h("tbody", {}); t.append(tb);
    r.rows.forEach(x => { const tr = h("tr", { class: "row", tabindex: "0", onclick: () => HL.go("commodity", { item: x.name, unit: x.unit }) }, h("td", {}, x.name), h("td", {}, x.unit),
      h("td", { class: "r" }, q(x.op_q)), h("td", { class: "r" }, q(x.in_q)), h("td", { class: "r" }, q(x.out_q)), h("td", { class: "r" }, q(x.close_q)), h("td", { class: "r" }, x.close_v ? inr(x.close_v) : "")); rowKeys(tr); tb.append(tr); });
    if (!r.rows.length) tb.append(h("tr", {}, h("td", { colspan: 7, class: "empty" }, "No stock yet. Create stock items, or type Item, Qty and Unit in a voucher.")));
    else tb.append(h("tr", { class: "total" }, h("td", {}, "Total"), h("td", {}), h("td", {}), h("td", {}), h("td", {}), h("td", {}), h("td", { class: "r" }, inr(r.total_value))));
    sc.replaceChildren(h("div", {}, h("h1", { class: "title" }, "Stock Summary"), h("p", { class: "sub" }, periodText() + " · a debit line with a quantity is stock in; a credit line is stock out"), periodBar(() => HL.refresh()), t, h("p", { class: "hint" }, r.note)));
    HL.setKeys([BACK]);
    const f = $("tbody tr.row", sc); f && f.focus();
  },
};
