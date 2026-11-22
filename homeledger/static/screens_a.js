HL.cfg = {
  get() { try { return Object.assign({ entry: "auto", drcr: "" }, JSON.parse(localStorage.getItem("hl-cfg") || "{}")); } catch (e) { return { entry: "auto", drcr: "" }; } },
  set(o) { try { localStorage.setItem("hl-cfg", JSON.stringify(Object.assign(HL.cfg.get(), o))); } catch (e) { } },
  byTo() { const c = HL.cfg.get(); return (c.drcr || (document.documentElement.dataset.look === "classic" ? "byto" : "drcr")) === "byto"; },
  side(x) { return HL.cfg.byTo() ? (x === "Dr" ? "By" : "To") : x; },
};
/* Screens, part 1: Gateway, Dashboard, Voucher entry, Day Book */
"use strict";

/* ===================== MENUS: Gateway of HomeLedger, laid out like Tally ===================== */
HL.menus = (() => {
  const go = (n, p) => () => HL.go(n, p);
  const menu = id => () => HL.go("menu", { id });
  const util = tab => go("utilities", { tab });
  const cad = (title, tab) => ({ title, sub: "Masters \u203a " + title, items: [
    ["i", "C", "Create", "Add a new one", go("masters", { tab, create: 1 })],
    ["i", "D", "Display", "See the list", go("masters", { tab })],
    ["i", "A", "Alter", "Change or delete an existing one", go("masters", { tab })]] });
  return {
    root: { title: "Gateway of HomeLedger", items: [
      ["i", "M", "Masters", "Groups, ledgers, cost centres", menu("masters")],
      ["i", "T", "Transactions", "Vouchers and Day Book", menu("transactions")],
      ["i", "U", "Utilities", "Backup, health check, export, security", menu("utilities")],
      ["i", "R", "Reports", "Balance Sheet, Profit & Loss, Trial Balance", menu("reports")],
      ["i", "D", "Display", "Ledgers, books, search, more reports", menu("display")],
      ["i", "H", "Dashboard", "Overview and charts", go("dashboard")],
      ["i", "K", "Select Company", "F1: open, create, split, merge, year-end close", go("companies")],
      ["i", "Q", "Quit", "Close HomeLedger", () => HL.quit()]] },
    masters: { title: "Masters", sub: "Accounts Info", items: [
      ["h", "Accounts Info"],
      ["i", "G", "Groups", "", menu("m_groups")],
      ["i", "L", "Ledgers", "", menu("m_ledgers")],
      ["i", "C", "Cost Centres", "", menu("m_cc")],
      ["i", "V", "Voucher Classes", "Ready-made voucher layouts", go("classes")],
      ["i", "T", "Stock Items", "Things bought and sold by quantity", go("stockitems")],
      ["i", "W", "Stock Groups", "Group your items", go("stockgroups")],
      ["i", "Z", "Stock Categories", "A second way to classify items", go("stockcategories")],
      ["i", "N", "Godowns / Locations", "Where stock is kept", go("godowns")],
      ["i", "X", "Price Lists", "Rates by price level and date", go("prices")],
      ["i", "M", "Bills of Material", "What a product is made from", go("boms")],
      ["i", "S", "GST Setup", "Registration, state, tax ledgers", go("gstsetup")],
      ["i", "O", "Opening Balances", "Start-up cash, bank, loans", go("openings")],
      ["i", "I", "Company Info", "Name and books beginning date (F3)", go("company")]] },
    m_groups: cad("Groups", "groups"), m_ledgers: cad("Ledgers", "ledgers"), m_cc: cad("Cost Centres", "activities"),
    transactions: { title: "Transactions", sub: "Accounting Vouchers", items: [
      ["h", "Accounting Vouchers"],
      ["i", "P", "Payment", "F5", go("voucher", { vtype: "Payment" })],
      ["i", "R", "Receipt", "F6", go("voucher", { vtype: "Receipt" })],
      ["i", "C", "Contra", "F4", go("voucher", { vtype: "Contra" })],
      ["i", "J", "Journal", "F7", go("voucher", { vtype: "Journal" })],
      ["i", "S", "Sales", "F8", go("voucher", { vtype: "Sales" })],
      ["i", "U", "Purchase", "F9", go("voucher", { vtype: "Purchase" })],
      ["i", "N", "Credit Note", "Ctrl+F8", go("voucher", { vtype: "Credit Note" })],
      ["i", "E", "Debit Note", "Ctrl+F9", go("voucher", { vtype: "Debit Note" })],
      ["h", "Other Vouchers (F10)"],
      ["i", "M", "Memorandum", "Ctrl+F10 — kept aside, not in totals", go("voucher", { vtype: "Memorandum" })],
      ["i", "V", "Reversing Journal", "A journal for a temporary adjustment", go("voucher", { vtype: "Reversing Journal" })],
      ["i", "O", "Sales Order", "Order received, no stock or accounts effect", go("voucher", { vtype: "Sales Order" })],
      ["i", "H", "Purchase Order", "Order placed, no stock or accounts effect", go("voucher", { vtype: "Purchase Order" })],
      ["i", "D", "Delivery Note", "Goods sent out, stock only", go("voucher", { vtype: "Delivery Note" })],
      ["i", "T", "Receipt Note", "Goods received, stock only", go("voucher", { vtype: "Receipt Note" })],
      ["i", "K", "Stock Journal", "Transfer between godowns, or manufacturing", go("voucher", { vtype: "Stock Journal" })],
      ["h", "Books"],
      ["i", "B", "Day Book", "All entries day by day", go("daybook")]] },
    utilities: { title: "Utilities", items: [
      ["i", "B", "Backup & Restore", "Safe copies of your books", util("backup")],
      ["i", "H", "Health Check", "Verify the data file", util("health")],
      ["i", "E", "Export", "Everything to Excel files", util("export")],
      ["i", "S", "Settings", "Text size, look", util("settings")],
      ["i", "Y", "Security", "Sign-in and users", util("security")],
      ["i", "A", "Audit Trail", "Who changed what", util("audit")]] },
    reports: { title: "Reports", items: [
      ["i", "B", "Balance Sheet", "What you own and owe", go("bs")],
      ["i", "P", "Profit & Loss A/c", "Income less spending", go("pnl")],
      ["i", "T", "Trial Balance", "All ledgers", go("tb")],
      ["i", "S", "Stock Summary", "Quantity and value of stock", go("stocksummary")],
      ["i", "L", "Godown Summary", "Stock in each place", go("godownsummary")],
      ["i", "E", "Batches and Expiry", "Stock by batch, soonest expiry first", go("batchsummary")],
      ["i", "G", "Pending Orders", "Orders not yet delivered or received", go("pendingorders")],
      ["i", "Z", "Post-dated Vouchers", "Future-dated cheques waiting to be activated", go("postdated")],
      ["i", "Q", "Cheque Register", "All cheques, with cheque printing", go("chequereg")],
      ["i", "K", "Bank Reconciliation", "Match entries with the bank statement", go("bankrec")],
      ["i", "F", "Cash Flow", "Money in and out by account type", go("cashflow")],
      ["i", "O", "Outstandings: Receivable", "Who owes you, with ageing", go("receivables")],
      ["i", "Y", "Outstandings: Payable", "Whom you owe, with ageing", go("payables")],
      ["i", "A", "Ratio Analysis", "Working capital, current ratio, profit %", go("ratios")],
      ["i", "H", "GST Summary", "Output tax, input credit, net payable", go("gstsummary")],
      ["i", "J", "GSTR-1 Lists", "B2B, B2C, credit notes, HSN summary", go("gstr1")],
      ["i", "M", "More Reports", "Group Summary, Fund Flow, Budgets, Interest, Scenarios", menu("more")]] },
    more: { title: "More Reports", sub: "Reports", items: [
      ["i", "G", "Group Summary", "One group at a time, down to the ledgers", go("groupsummary")],
      ["i", "R", "Receipts & Payments", "All cash and bank movement by account", go("recpay")],
      ["i", "F", "Fund Flow", "Sources and applications of money", go("fundflow")],
      ["i", "B", "Budgets", "Budget against actual", go("budgets")],
      ["i", "I", "Interest Calculation", "Interest on balances over a period", go("interest")],
      ["i", "S", "Scenarios", "Books as if optional vouchers were real", go("scenario")]] },
    display: { title: "Display", sub: "More Reports", items: [
      ["h", "Account Books"],
      ["i", "L", "Ledger", "Statement of any account", go("ledgers_pick")],
      ["i", "C", "Cash / Bank Book", "Money in hand and in bank", go("cashbook")],
      ["i", "D", "Day Book", "All entries day by day", go("daybook")],
      ["h", "Statements"],
      ["i", "S", "Search", "Find any entry (Ctrl+F)", go("search")],
      ["i", "O", "Cost Centres", "Income and spending by cost centre", go("activities")],
      ["i", "I", "Item-wise Report", "By item name", go("commodities")]] },
  };
})();

function renderMenu(sc, id) {
  const def = HL.menus[id] || HL.menus.root, root = id === "root";
  const items = def.items;
  const ul = h("ul", { class: "menu", role: "menu" });
  const sel = items.filter(x => x[0] === "i");
  HL._menuIdx = HL._menuIdx || {};
  let idx = Math.min(HL._menuIdx[id] || 0, sel.length - 1);
  const lis = [];
  const run = i => { HL._menuIdx[id] = i; sel[i][4](); };
  for (const it of items) {
    if (it[0] === "h") { ul.append(h("li", { class: "h" }, it[1])); continue; }
    const li = h("li", { class: "i", role: "menuitem", tabindex: "-1", onclick: () => run(sel.indexOf(it)) },
      h("span", { class: "hot" }, it[1]), it[2], it[3] ? h("span", { class: "d" }, it[3]) : "");
    lis.push(li); ul.append(li);
  }
  const paint = () => lis.forEach((l, i) => { l.classList.toggle("sel", i === idx); if (i === idx) l.scrollIntoView({ block: "nearest" }); });
  paint();
  HL.onKey = e => {
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;   // typing in the search box must not trigger menu hotkeys
    if (e.key === "ArrowDown") { idx = (idx + 1) % lis.length; paint(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { idx = (idx - 1 + lis.length) % lis.length; paint(); e.preventDefault(); }
    else if (e.key === "Enter") { run(idx); e.preventDefault(); }
    else if (!e.ctrlKey && !e.altKey && !e.metaKey && e.key.length === 1) {
      const k = e.key.toUpperCase(), i = sel.findIndex(x => x[1] === k);
      if (i >= 0) { run(i); e.preventDefault(); }
    }
  };
  const c = HL.S.status.company;
  const head = root
    ? h("div", { style: "padding:.5rem 1rem;text-align:center;border-bottom:1px solid var(--line-soft)" },
        h("div", { class: "muted", style: "font-size:.85em" }, "Current book"), h("b", {}, c.name),
        h("div", { class: "muted", style: "font-size:.85em" }, "Today: " + showDay(todayIso()) + ", " + showDate(todayIso())))
    : (def.sub ? h("div", { class: "muted", style: "padding:.4rem 1rem;text-align:center;border-bottom:1px solid var(--line-soft);font-size:.9em" }, def.sub + " \u00b7 " + c.name) : "");
  sc.replaceChildren(noticeBanner(),
    h("div", { class: "gate-wrap", style: "flex-direction:column;align-items:center" }, root ? h("img", { class: "gate-logo", src: "logo.png", alt: "HomeLedger" }) : "",
      h("div", { class: "gate" }, h("div", { class: "hd" }, def.title), head, ul)),
    root ? backupWarning() : "");
  const keys = root ? [] : [BACK, "sep"];
  keys.push(
    { k: "F5", label: "Payment", fn: () => HL.go("voucher", { vtype: "Payment" }) },
    { k: "F6", label: "Receipt", fn: () => HL.go("voucher", { vtype: "Receipt" }) },
    { k: "F4", label: "Contra", fn: () => HL.go("voucher", { vtype: "Contra" }) },
    { k: "F7", label: "Journal", fn: () => HL.go("voucher", { vtype: "Journal" }) },
    "sep",
    { k: "Alt+G", label: "Go To", fn: () => HL.openGoTo() },
    { k: "F1", label: "Select Company", fn: () => HL.go("companies") },
    { k: "F3", label: "Company Info", fn: () => HL.go("company") },
    { k: "Alt+F1", label: "Dashboard", fn: () => HL.go("dashboard") });
  HL.setKeys(keys);
}
HL.screens.gateway = { title: "", async render(sc) { await loadMasters(); renderMenu(sc, "root"); } };
HL.screens.menu = { title: p => (HL.menus[p.id] || {}).title || "", async render(sc, params) { await loadMasters(); renderMenu(sc, params.id); } };
function noticeBanner() {
  const n = HL.S.status && HL.S.status.notice;
  if (!n) return "";
  return h("div", { class: "banner warn" }, h("div", {}, n), h("button", { class: "x", "aria-label": "Dismiss", onclick: async e => { await HL.post("/api/notice/dismiss"); HL.S.status.notice = null; e.target.closest(".banner").remove(); } }, "×"));
}
function backupWarning() {
  const s = HL.S.status; if (!s) return "";
  const out = [];
  if (s.copy_error) out.push(h("div", { class: "banner warn" }, "The second backup copy could not be saved (" + s.copy_error + "). Check that the pen drive / folder is connected. Open Utilities › Backup."));
  else if (!s.copy_dir) out.push(h("div", { class: "banner warn" }, h("div", {}, "Backups are stored only on this computer. For safety, also choose a second place (such as a pen drive) in "), h("a", { class: "lnk", onclick: () => HL.go("utilities", { tab: "backup" }) }, "Utilities › Backup.")));
  return h("div", { style: "max-width:30rem;margin:1rem auto 0" }, out);
}

/* ===================== DASHBOARD ===================== */
HL.screens.dashboard = {
  title: "Dashboard",
  async render(sc) {
    await loadMasters();
    const P = getPeriod();
    const d = await HL.get("/api/dashboard", { from: P.from, to: P.to });
    const c = d.cards;
    const root = h("div", {});
    root.append(noticeBanner(), periodBar(() => HL.refresh()));
    if (!d.voucher_count) {
      root.append(h("div", { class: "card" }, h("h3", {}, "Welcome! Let's get started"),
        h("ol", {}, h("li", {}, "Press ", h("b", {}, "O"), " on the Gateway and enter what you have today: cash, bank balance, loans."),
          h("li", {}, "Press ", h("b", {}, "F5"), " to record a payment, ", h("b", {}, "F6"), " for money received."),
          h("li", {}, "Come back here to see where the money goes.")),
        h("div", { class: "row" }, h("button", { class: "btn primary", onclick: () => HL.go("openings") }, "Enter opening balances"), h("button", { class: "btn", onclick: () => HL.go("voucher", { vtype: "Payment" }) }, "Record first payment"))));
      HL.setKeys([{ k: "Esc", label: "Gateway", fn: HL.back }]);
      sc.replaceChildren(root); return;
    }
    // --- insights
    const ins = [];
    const pe = c.period_expense, pi = c.period_income;
    if (c.month_expense || c.last_month_expense) {
      let t = `This month you have spent ${rs(c.month_expense, 0)} so far`;
      if (c.last_month_expense) { const diff = c.month_expense - c.last_month_expense; t += `; last month's total was ${rs(c.last_month_expense, 0)}` + (diff > 0 ? ` (this month is already ${rs(diff, 0)} higher).` : "."); }
      else t += ".";
      ins.push(["w", t]);
    }
    if (d.top_expenses.length && pe > 0) { const t = d.top_expenses[0]; ins.push(["b", `Biggest spending in this period: ${t.name}, ${rs(t.amount, 0)} (${Math.round(t.amount / pe * 100)}% of all spending).`]); }
    if (pi || pe) ins.push([pi - pe >= 0 ? "g" : "b", pi - pe >= 0 ? `In this period you earned ${rs(pi, 0)} and spent ${rs(pe, 0)}: ${rs(pi - pe, 0)} saved.` : `In this period you spent ${rs(pe, 0)} but earned ${rs(pi, 0)}: spending was ${rs(pe - pi, 0)} more than income.`]);
    if (c.loans > 0) ins.push(["w", `Loans / money borrowed still to repay: ${rs(c.loans, 0)}.`]);
    if (c.money_lent > 0) ins.push(["", `Money to receive from others: ${rs(c.money_lent, 0)}.`]);
    if (d.last_date && d.last_date < addDays(todayIso(), -7)) ins.push(["w", `The last entry is dated ${showDate(d.last_date)}. If there are newer bills or notes, remember to enter them.`]);
    // --- cards
    const kpi = (lab, val, note, cls) => h("div", { class: "card kpi c3" }, h("div", { class: "lab" }, lab), h("div", { class: "val " + (cls || "") }, val), note ? h("div", { class: "note" }, note) : "");
    const grid = h("div", { class: "dash-grid" });
    grid.append(
      kpi("Cash in hand", rs(c.cash, 0), "As of " + showDate(c.today), c.cash < 0 ? "neg" : ""),
      kpi("Bank balance", rs(c.bank, 0), "All bank accounts", c.bank < 0 ? "neg" : ""),
      kpi("Spent this month", rs(c.month_expense, 0), c.last_month_expense ? "Last month: " + rs(c.last_month_expense, 0) : "Since " + showDate(c.month_start)),
      kpi("Net worth", rs(c.net_worth, 0), "Assets minus loans & dues", c.net_worth < 0 ? "neg" : ""),
      kpi("Income (period)", rs(pi, 0), periodText()),
      kpi("Spending (period)", rs(pe, 0), periodText()),
      kpi("Saved (period)", rs(pi - pe, 0), pi - pe >= 0 ? "Income more than spending" : "Spending more than income", pi - pe < 0 ? "neg" : "pos"),
      kpi("Loans to repay", rs(c.loans, 0), c.money_lent ? "Money to receive: " + rs(c.money_lent, 0) : ""));
    if (ins.length) grid.append(h("div", { class: "card c12" }, h("h3", {}, "What stands out"), h("ul", { class: "insights" }, ins.map(([k, t]) => h("li", { class: k }, t)))));
    const months = d.months, lab = m => monthLabel(m.month), lng = m => monthLabel(m.month, true);
    const drillMonth = (dd) => { const ym = dd.ym; const [y, m] = ym.split("-"); HL.S.period = { id: "custom", from: ym + "-01", to: lastDayOfMonth(+y, +m) }; HL.go("daybook"); };
    const data1 = months.map(m => ({ label: lab(m), long: lng(m), ym: m.month, vals: [m.income, m.expense] }));
    grid.append(chartCard({ cls: "c8", title: "Money in and money out", sub: "Last 12 months · click a month to see its entries",
      legend: [{ name: "Income", color: "var(--s1)" }, { name: "Spending", color: "var(--s2)" }],
      draw: () => barChart({ data: data1, series: [{ name: "Income", c: 1 }, { name: "Spending", c: 2 }], onbar: drillMonth }),
      table: () => simpleTable(["Month", "Income", "Spending"], months.map(m => [monthLabel(m.month, true), rs(m.income), rs(m.expense)])) }));
    grid.append(chartCard({ cls: "c4", title: "Cash + bank balance", sub: "At the end of each month",
      draw: () => lineChart({ data: months.map(m => ({ label: lab(m), long: lng(m), vals: [m.cash_bank] })), series: [{ name: "Cash + bank", c: 1 }] }),
      table: () => simpleTable(["Month", "Cash + bank"], months.map(m => [monthLabel(m.month, true), rs(m.cash_bank)])) }));
    grid.append(chartCard({ cls: "c6", title: "Net worth", sub: "Everything you own minus everything you owe",
      draw: () => lineChart({ data: months.map(m => ({ label: lab(m), long: lng(m), vals: [m.net_worth] })), series: [{ name: "Net worth", c: 3 }] }),
      table: () => simpleTable(["Month", "Net worth"], months.map(m => [monthLabel(m.month, true), rs(m.net_worth)])) }));
    const toLedger = id => () => HL.go("ledger", { ledger_id: id });
    const card = (title, sub, body, cls) => h("div", { class: "card " + cls }, h("h3", {}, title), h("p", { class: "cs" }, sub), body);
    grid.append(
      card("Where the money went", "Top spending accounts · click one for its statement", hbars(d.top_expenses.map(x => ({ label: x.name, value: x.amount, onclick: toLedger(x.id) })), { color: 2 }), "c6"),
      card("Where the money came from", "Income accounts", hbars(d.top_income.map(x => ({ label: x.name, value: x.amount, onclick: toLedger(x.id) })), { color: 1 }), "c6"),
      d.by_activity.length ? card("Spending by cost centre", "Click for details", hbars(d.by_activity.map(x => ({ label: x.name, value: x.amount, color: "var(--s7)", onclick: () => HL.go("activity", { cc_id: x.id }) })), { color: 7 }), "c6") : "",
      card("Most bought items", "By amount (items entered with a quantity or name)", hbars(d.top_items.map(x => ({ label: x.item, value: x.amount, onclick: () => HL.go("search", { item: x.item }) })), { color: 5 }), "c6"));
    const rec = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Date", "Type", "No.", "Particulars", "Amount"].map((x, i) => h("th", { class: i === 4 ? "r" : "" }, x)))));
    const tb = h("tbody", {});
    d.recent.forEach(r => tb.append(h("tr", { class: "row", onclick: () => HL.go("voucher", { id: r.id }) }, h("td", {}, showDate(r.date)), h("td", {}, r.vtype), h("td", {}, r.number), h("td", {}, r.particulars), h("td", { class: "r" }, rs(r.amount_paise)))));
    rec.append(tb);
    grid.append(h("div", { class: "card c12" }, h("h3", {}, "Latest entries"), h("p", { class: "cs" }, "Click to open"), h("div", { class: "scroll" }, rec)));
    root.append(grid);
    sc.replaceChildren(root);
    HL.setKeys([
      { k: "Esc", label: "Gateway", fn: HL.back }, "sep",
      { k: "F5", label: "Payment", fn: () => HL.go("voucher", { vtype: "Payment" }) },
      { k: "F6", label: "Receipt", fn: () => HL.go("voucher", { vtype: "Receipt" }) },
      { k: "Ctrl+F", label: "Search", fn: () => HL.go("search") },
      { k: "", label: "Day Book", fn: () => HL.go("daybook") },
      { k: "", label: "Print", fn: () => window.print() },
    ]);
  },
};

/* ===================== VOUCHER ENTRY ===================== */
const VOUCHER_KEYS = { Contra: "F4", Payment: "F5", Receipt: "F6", Journal: "F7", Sales: "F8", Purchase: "F9", "Credit Note": "Ctrl+F8", "Debit Note": "Ctrl+F9", Memorandum: "Ctrl+F10" };
const VOUCHER_HELP = {
  Payment: "Money paid out. Choose what the money was spent on; the Cash/Bank account above is reduced.",
  Receipt: "Money received. Choose where it came from; the Cash/Bank account above is increased.",
  Contra: "Move money between Cash and Bank (for example, cash deposited into the bank).",
  Journal: "An adjustment that does not move cash or bank (for example, a bill to be paid later). Debits must equal credits.",
  Sales: "A sale. Debit who owes you (or the account the produce was received into); credit the sales account. Use Receipt (F6) when money is actually received.",
  Purchase: "A purchase on credit or an asset purchase. Debit the item bought; credit who you owe. Use Payment (F5) when you pay.",
  "Credit Note": "Goods returned by a customer, or a price reduction given. Debit the sales account; credit the customer. Not for cash: settle with a Payment (F5).",
  Memorandum: "A note of something not yet final (a quote, a promise). It is kept in the records but never counts in any total.",
  "Reversing Journal": "A journal for an adjustment that is meant to be undone later. Debits must equal credits.",
  "Debit Note": "Goods returned to a supplier, or a price reduction received. Debit the supplier; credit the purchase account. Not for cash: settle with a Receipt (F6).",
};
HL.screens.voucher = {
  title: p => (p.id ? "Alter " : p.copy_id ? "Duplicate " : "") + (p.vtype || "Voucher"),
  async render(sc, params) {
    await loadMasters();
    let v = null;
    const srcId = params.id || params.copy_id;
    if (srcId) { v = await HL.get("/api/voucher", { id: srcId }); params = Object.assign({}, params, { vtype: v.vtype }); HL.cur.params = params; }
    const isNew = !params.id;   // a copy is a new voucher that starts from an old one
    const vtype = params.vtype;
    if (["Sales Order", "Purchase Order", "Delivery Note", "Receipt Note", "Stock Journal"].includes(vtype)) { await HL.stock.load(); return HL.screens.stockvoucher.render(sc, params, params.id ? v : null); }
    const cbOpts = () => ledgerOptions({ test: l => !!l.cb_kind });
    const nonCbOpts = () => ledgerOptions({ test: l => !l.cb_kind });
    const allOpts = () => ledgerOptions();
    const simple = ["Payment", "Receipt", "Contra"].includes(vtype);
    // detect whether an existing voucher fits the simple layout
    let mode = simple && !(HL.cfg.get().entry === "double" && vtype !== "Contra") ? "simple" : "generic";
    if (v && simple) {
      const cbLines = v.lines.filter(l => l.cb_kind);
      const wantSide = vtype === "Payment" ? "Cr" : vtype === "Receipt" ? "Dr" : "Cr";
      if (vtype === "Contra") mode = (v.lines.length === 2) ? "simple" : "generic";
      else mode = (cbLines.length === 1 && cbLines[0].side === wantSide) ? "simple" : "generic";
    }
    const dflt = HL.S.lastVoucherDate || todayIso();
    const S = { date: v && !params.copy_id ? v.date : (params.date || dflt), approx: v ? v.date_approx : false, ref: v ? v.ref : "", narration: v ? v.narration : "", dirty: !!params.copy_id, status: v && v.status !== "cancelled" && !params.copy_id ? v.status : "posted" };
    const root = h("div", {});
    const num = h("b", {}, "");
    const dateInp = h("input", { type: "text", value: showDate(S.date), style: "width:9.5rem", "aria-label": "Date" });
    const dow = h("span", { class: "muted" }, showDay(S.date));
    const refInp = h("input", { type: "text", value: S.ref, style: "width:9rem", "aria-label": "Reference", placeholder: "Bill / notebook ref." });
    const approx = h("input", { type: "checkbox", checked: S.approx, id: "approx" });
    const refreshNum = async () => { if (!isNew) { num.textContent = v.number; return; } try { const r = await HL.get("/api/next_number", { vtype, date: S.date }); num.textContent = r.number; } catch (e) { num.textContent = "?"; } };
    dateInp.addEventListener("change", () => {
      const iso = parseDateInput(dateInp.value, S.date);
      if (!iso) { say("Please type the date like 15-11-2026 (or just 15).", "err"); dateInp.value = showDate(S.date); return; }
      S.date = iso; dateInp.value = showDate(iso); dow.textContent = showDay(iso); refreshNum(); S.dirty = true;
    });
    const head = h("div", { class: "vch-head" },
      h("div", { class: "vt" }, vtype), h("div", {}, h("div", { class: "muted", style: "font-size:.8em" }, "No."), num),
      h("label", { class: "f" }, "Date", h("span", { class: "row", style: "gap:.4rem" }, dateInp, dow)),
      h("label", { class: "f" }, "Reference", refInp),
      h("label", { class: "f", style: "flex-direction:row;align-items:center;gap:.4rem", title: "Tick when copying from a notebook and the exact date is not known" }, approx, "Date is approximate"));
    const body = h("div", { class: "vch-body" });
    body.append(h("div", { class: "muted", style: "margin-bottom:.6rem" }, VOUCHER_HELP[vtype]));
    // account selector (simple mode)
    let acct = null, acctBal = h("span", { class: "muted" }), preAcct = null;
    const acctLabel = vtype === "Payment" ? "Paid from (Cash / Bank)" : vtype === "Receipt" ? "Received in (Cash / Bank)" : "Take money out of (Cash / Bank)";
    const updBal = () => {
      const o = acct && acct.option; if (!o) { acctBal.textContent = ""; return; }
      const l = M().ledgers.find(x => x.id === o.value); const b = l && l.balance_paise;
      acctBal.textContent = b == null ? "" : "Balance now: " + bal(b);
    };
    if (mode === "simple") {
      const pre = preAcct = v ? (vtype === "Receipt" ? v.lines.find(l => l.cb_kind && l.side === "Dr") : v.lines.find(l => l.cb_kind && l.side === "Cr")) : null;
      const cash = M().ledgers.find(l => l.name === "Cash");
      acct = picker({ options: cbOpts, value: pre ? pre.ledger_id : (HL.S.lastAcct && cbOpts().some(o => o.value === HL.S.lastAcct) ? HL.S.lastAcct : cash && cash.id), placeholder: "Cash or bank account", onpick: () => { updBal(); S.dirty = true; } });
      body.append(h("div", { class: "row", style: "margin-bottom:.7rem" }, h("label", { class: "f", style: "min-width:18rem" }, acctLabel, acct.el), acctBal));
      updBal();
    } else {
      body.append(h("div", { class: "hint", style: "margin:0 0 .5rem" }, "Each line is a Debit (Dr) or Credit (Cr). Total debit must equal total credit."));
    }
    // lines
    const tbl = h("table", { class: "vtbl" });
    const showItems = vtype !== "Contra";
    const heads = [];
    if (mode === "generic") heads.push(h("th", { class: "sidecol" }, HL.cfg.byTo() ? "By/To" : "Dr/Cr"));
    heads.push(h("th", {}, vtype === "Contra" ? "Put into (Cash / Bank)" : mode === "simple" ? (vtype === "Payment" ? "Particulars (spent on / paid to)" : "Particulars (received from / for)") : "Account"));
    heads.push(h("th", { style: "width:11rem" }, "Cost Centre"));
    if (showItems) heads.push(h("th", { style: "width:10rem" }, "Item (optional)"), h("th", { class: "qtycol" }, "Qty"), h("th", { class: "unitcol" }, "Unit"));
    heads.push(h("th", { class: "amtcol right" }, "Amount (₹)"), h("th", { class: "xcol" }, ""));
    tbl.append(h("thead", {}, h("tr", {}, heads)));
    const tb = h("tbody", {}); tbl.append(tb);
    const rows = [];
    const total = h("span", {}, "0.00"), totalBox = h("div", { class: "vtotal" }, h("span", {}, "Total"), total);
    const itemList = h("datalist", { id: "dl-items" }, M().items.map(i => h("option", { value: i.item })));
    const unitList = h("datalist", { id: "dl-units" }, [...new Set(["kg", "g", "litre", "nos", "bag", "quintal", "tonne", "day", "hour", ...M().units])].map(u => h("option", { value: u })));
    const parse = s => { const x = String(s || "").replace(/[,\s₹]/g, ""); return /^\d+(\.\d{1,2})?$/.test(x) ? Math.round(parseFloat(x) * 100) : (x === "" ? 0 : NaN); };
    function recalc() {
      let dr = 0, cr = 0, bad = false;
      rows.forEach(r => { const a = parse(r.amt.value); if (isNaN(a)) { bad = true; return; } const side = mode === "generic" ? r.side.value : "x"; if (side === "Cr") cr += a; else dr += a; });
      if (mode === "simple") { total.textContent = rs(dr); totalBox.className = "vtotal"; totalBox.firstChild.textContent = "Total"; }
      else { totalBox.className = "vtotal" + (dr !== cr ? " bad" : ""); totalBox.firstChild.textContent = dr === cr ? "Balanced" : "Difference " + rs(Math.abs(dr - cr)); total.textContent = "Dr " + rs(dr) + "    Cr " + rs(cr); }
    }
    function addRow(pre) {
      const r = {};
      const tr = h("tr", {});
      if (mode === "generic") {
        const dflSide = pre ? pre.side : (rows.length === 0 ? (vtype === "Purchase" ? "Dr" : "Dr") : (rows.length === 1 && rows[0].side.value === "Dr" ? "Cr" : "Dr"));
        r.side = h("select", { "aria-label": "Debit or credit" }, h("option", { value: "Dr" }, HL.cfg.side("Dr")), h("option", { value: "Cr" }, HL.cfg.side("Cr")));
        r.side.value = dflSide; r.side.addEventListener("change", () => { recalc(); S.dirty = true; });
        tr.append(h("td", { class: "sidecol" }, r.side));
      }
      const optsFn = vtype === "Contra" ? cbOpts : mode === "simple" ? nonCbOpts : allOpts;
      r.led = picker({ options: optsFn, value: pre ? pre.ledger_id : null, placeholder: "Account...", allowNew: vtype !== "Contra", newLabel: "Create ledger", width: "100%",
        onnew: (name, done) => HL.ledgerForm({ name, onsaved: async id => { await loadMasters(); const o = optsFn().find(x => x.value === id); done(o); fillCc(); } }),
        onpick: () => { fillCc(); S.dirty = true; } });
      function fillCc() { const o = r.led.option; if (o && o.data.default_cc_id && !r.cc.value) r.cc.set(o.data.default_cc_id); }
      tr.append(h("td", {}, r.led.el));
      r.cc = picker({ options: () => ccOptions(true), value: pre ? pre.cc_id : null, placeholder: "Cost centre", width: "100%", onpick: () => { S.dirty = true; } });
      tr.append(h("td", {}, r.cc.el));
      if (showItems) {
        r.item = h("input", { type: "text", list: "dl-items", value: pre ? pre.item : "", placeholder: "Item name", "aria-label": "Item" });
        r.qty = h("input", { type: "text", inputmode: "decimal", value: pre && pre.qty_milli ? qtyStr(pre.qty_milli).replace(/,/g, "") : "", style: "text-align:right", "aria-label": "Quantity" });
        r.unit = h("input", { type: "text", list: "dl-units", value: pre ? pre.unit : "", "aria-label": "Unit" });
        tr.append(h("td", {}, r.item), h("td", { class: "qtycol" }, r.qty), h("td", { class: "unitcol" }, r.unit));
        [r.item, r.qty, r.unit].forEach(x => x.addEventListener("input", () => { S.dirty = true; }));
      }
      r.amt = h("input", { type: "text", inputmode: "decimal", class: "amt", value: pre ? (pre.amount_paise / 100).toFixed(2) : "", "aria-label": "Amount", "data-no-enter": "1", style: "width:100%" });
      r.amt.addEventListener("input", () => { recalc(); S.dirty = true; });
      r.amt.addEventListener("focus", () => r.amt.select());
      r.amt.addEventListener("keydown", e => {
        if (e.key !== "Enter") return;
        e.preventDefault();
        const i = rows.indexOf(r);
        if (i < rows.length - 1) rows[i + 1].led.focus();
        else if (parse(r.amt.value) > 0 && rows.length < 40) { addRow(); rows[rows.length - 1].led.focus(); }
        else narr.focus();
      });
      const afterCc = () => (r.item || r.amt).focus();
      r.led.input.addEventListener("picked", () => { if (r.cc.value) afterCc(); else r.cc.focus(); });
      r.cc.input.addEventListener("picked", afterCc);
      r.led.input.addEventListener("keydown", e => { if (e.key === "Enter" && !r.led.value && !r.led.input.value.trim() && rows.indexOf(r) > 0) { e.preventDefault(); narr.focus(); } });
      r.x = h("button", { class: "delx stop", type: "button", tabindex: "-1", title: "Remove this line", "aria-label": "Remove line", onclick: () => { if (rows.length > 1) { rows.splice(rows.indexOf(r), 1); tr.remove(); recalc(); S.dirty = true; } } }, "×");
      r.bills = pre && v ? v.bills.filter(b => b.ledger_id === pre.ledger_id && b.side === pre.side).map(b => ({ ref: b.ref, kind: b.kind, amount: (b.amount_paise / 100).toFixed(2), due: b.due_date })) : [];
      r.bb = h("button", { class: "btn stop", type: "button", tabindex: "-1", style: "padding:.1rem .45rem;font-size:.8em", title: "Bill-wise details: New Ref, Against Ref, Advance", onclick: () => HL.billsDialog(r, v ? v.id : 0, () => (mode === "generic" ? r.side.value : (vtype === "Receipt" ? "Cr" : "Dr"))) }, "Bills");
      const showBb = () => { const id = r.led.value; r.bb.style.display = id && HL.isParty(id) ? "" : "none"; r.bb.textContent = r.bills.length ? "Bills (" + r.bills.length + ")" : "Bills"; };
      r.showBb = showBb; showBb();
      r.led.input.addEventListener("picked", showBb);
      tr.append(h("td", { class: "amtcol" }, r.amt), h("td", { class: "xcol" }, r.bb, r.x));
      r.tr = tr; rows.push(r); tb.append(tr); recalc();
      return r;
    }
    // initial rows
    if (v) {
      const lines = mode === "simple" ? v.lines.filter(l => l !== preAcct) : v.lines;
      lines.forEach(l => addRow(l));
    } else {
      addRow();
      if (mode === "generic") addRow();
    }
    const addBtn = h("button", { class: "btn stop", type: "button", style: "margin-top:.5rem", onclick: () => { addRow(); rows[rows.length - 1].led.focus(); } }, "+ Add a line");
    const narr = h("textarea", { rows: "2", style: "width:100%", maxlength: "500", placeholder: "Narration: a short note about this entry", "aria-label": "Narration" }, S.narration);
    narr.addEventListener("input", () => { S.dirty = true; });
    narr.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); save(); } });
    // cheque details, post-dated flag, voucher class
    const M0 = v ? v.meta : { post_dated: false, inst_no: "", inst_date: null, bank_name: "", class_name: "" };
    const bankish = ["Payment", "Receipt", "Contra"].includes(vtype);
    const mNo = h("input", { type: "text", value: M0.inst_no, maxlength: "30", style: "width:9rem", "aria-label": "Cheque number" });
    const mDt = h("input", { type: "text", value: M0.inst_date ? showDate(M0.inst_date) : "", style: "width:9rem", placeholder: "dd-mm-yyyy", "aria-label": "Cheque date" });
    const mBk = h("input", { type: "text", value: M0.bank_name, maxlength: "60", style: "width:12rem", "aria-label": "Bank name" });
    const mPd = h("input", { type: "checkbox", checked: M0.post_dated, id: "pdated" });
    [mNo, mDt, mBk, mPd].forEach(x => x.addEventListener("input", () => { S.dirty = true; }));
    const classes = (await HL.get("/api/classes")).filter(c => c.vtype === vtype);
    const clsSel = h("select", { "aria-label": "Voucher class" }, h("option", { value: "" }, "(none)"), classes.map(c => h("option", { value: c.name }, c.name)));
    clsSel.value = M0.class_name || "";
    clsSel.addEventListener("change", () => {
      S.dirty = true;
      const c = classes.find(x => x.name === clsSel.value);
      if (!c || !isNew || rows.some(r => r.amt.value || r.led.value)) return;
      while (rows.length) { rows[0].tr.remove(); rows.shift(); }
      c.lines.forEach(l => {
        const led = M().ledgers.find(x => x.id === l.ledger_id);
        if (mode === "simple" && led && led.cb_kind) { acct.set && acct.set(l.ledger_id); updBal(); return; }
        const r = addRow({ ledger_id: l.ledger_id, side: l.side, amount_paise: 0 }); if (mode === "simple") r.amt.value = "";
      });
      if (!rows.length) addRow();
      recalc();
    });
    const metaRow = h("div", { class: "row", style: "gap:1rem;flex-wrap:wrap;margin-top:.8rem;align-items:flex-end" },
      classes.length ? h("label", { class: "f" }, "Voucher class", clsSel) : null,
      bankish ? [h("label", { class: "f" }, "Cheque no.", mNo), h("label", { class: "f" }, "Cheque date", mDt), h("label", { class: "f" }, "Bank", mBk),
        h("label", { class: "f", style: "flex-direction:row;align-items:center;gap:.4rem", title: "The cheque is dated in the future. It stays out of the books until you activate it (Reports > Post-dated Vouchers)" }, mPd, "Post-dated")] : null);
    // stock lines for Sales / Purchase / Credit Note / Debit Note
    let itemsTable = null, itemsBox = null;
    if (["Sales", "Purchase", "Credit Note", "Debit Note"].includes(vtype)) {
      await HL.stock.load();
      const fill = h("button", { class: "btn", type: "button", title: "Put the items total on the amount boxes that are still empty", onclick: () => { const tot = itemsTable.total(); if (!tot) return; const amts = rows.filter(r => !r.amt.value); amts.forEach(r => { r.amt.value = (tot / 100).toFixed(2); }); if (amts.length) { recalc(); S.dirty = true; say("Items total put on the empty lines.", "ok"); } } }, "Use items total for the amounts");
      S.gst = v && v.gst ? v.gst : null;
      HL.gstCfg = await HL.get("/api/gst/config"); HL.gstM = HL.gstCfg.on ? await HL.get("/api/gst/masters") : { party: {}, item: {} };
      const addGst = h("button", { class: "btn", type: "button", title: "Work out CGST / SGST / IGST from the items and add the tax lines", onclick: async () => {
        try {
          const cfg = HL.gstCfg, tl = Object.values(cfg.tax_ledgers).map(String);
          const its = itemsTable.get().map(i => ({ item_id: i.item_id, amount_paise: Math.round((parseFloat(String(i.amount).replace(/,/g, "")) || 0) * 100) }));
          if (!its.length) { say("Add the stock items (with amounts) first. GST is worked out from them.", "err"); return; }
          rows.filter(r => tl.includes(String(r.led.value))).forEach(r => { rows.splice(rows.indexOf(r), 1); r.tr.remove(); });
          const partyRow = rows.find(r => r.led.value && HL.isParty(r.led.value));
          const res = await HL.post("/api/gst/compute", { vtype, party: partyRow ? partyRow.led.value : null, items: its });
          const put = (kind, p) => { if (!p) return; const r = addRow({ ledger_id: res.ledgers[kind], side: res.side, amount_paise: p }); r.led.set && r.led.set(res.ledgers[kind]); };
          put("cgst", res.totals.cgst); put("sgst", res.totals.sgst); put("igst", res.totals.igst);
          const taxSum = res.totals.cgst + res.totals.sgst + res.totals.igst;
          const others = rows.filter(r => !tl.includes(String(r.led.value)) && r !== partyRow && r.led.value);
          if (partyRow) partyRow.amt.value = ((res.totals.taxable + taxSum) / 100).toFixed(2);
          if (others.length === 1) others[0].amt.value = (res.totals.taxable / 100).toFixed(2);
          S.gst = { rows: res.rows, pos: res.pos }; S.gstParty = partyRow ? partyRow.led.value : null;
          recalc(); S.dirty = true;
          say(`GST added: ${res.intra ? "CGST + SGST" : "IGST"}, tax ${rs(taxSum)}.` + (partyRow ? "" : " Choose the party and press Add GST again to use the party's state.") + (res.warnings.length ? " " + res.warnings[0] : ""), res.warnings.length ? "err" : "ok");
        } catch (e) { fail(e); } } }, "Add GST");
      const extra = h("span", { class: "row", style: "gap:.5rem" }, fill, HL.gstCfg.on ? addGst : "");
      itemsTable = HL.itemsTable({ vtype, getDate: () => S.date, items: v ? v.items.filter(i => i.kind === "normal") : [], extra, onchange: () => { S.dirty = true; } });
      const hasItems = v && v.items.length;
      itemsBox = h("details", { class: "panel", style: "margin-top:.8rem", open: !!hasItems }, h("summary", {}, "Stock items in this " + vtype.toLowerCase() + " (optional)"), itemsTable.el);
    }
    body.append(tbl, addBtn, totalBox, itemsBox, metaRow, h("label", { class: "f", style: "margin-top:.6rem" }, "Narration", narr),
      h("p", { class: "hint" }, "Tip: Enter moves to the next box. After the last amount, Enter adds another line; Enter on the Narration saves (or press Ctrl+A)."));
    if (!isNew) {
      body.append(h("p", { class: "hint" }, "Entered " + v.created_at.slice(0, 16) + (v.updated_at !== v.created_at ? " · last changed " + v.updated_at.slice(0, 16) : "") + (v.status === "cancelled" ? " · CANCELLED" : "")));
    }
    root.append(h("div", { class: "noprint" }), head, body, itemList, unitList);
    sc.replaceChildren(root);
    enterAsTab(root);
    refreshNum();
    dateInp.addEventListener("change", () => { S.dirty = true; });
    [refInp, approx].forEach(x => x.addEventListener("input", () => { S.dirty = true; }));

    let saving = false;
    async function save() {
      if (saving) return; saving = true;
      try {
        const lines = [];
        for (const r of rows) {
          const a = parse(r.amt.value);
          if (isNaN(a)) throw new Error("An amount is not a valid number. Use digits and an optional decimal point.");
          const hasAny = r.led.value || a;
          if (!hasAny && !(r.item && r.item.value.trim())) continue;
          if (!r.led.value) throw new Error("Please choose an account on every line that has an amount.");
          if (!a) throw new Error("Please enter an amount for '" + r.led.input.value + "'.");
          lines.push({ ledger_id: r.led.value, side: mode === "generic" ? r.side.value : (vtype === "Receipt" ? "Cr" : vtype === "Payment" ? "Dr" : "Dr"), amount: (a / 100).toFixed(2), bills: r.bills, cc_id: r.cc.value, item: r.item ? r.item.value : "", qty: r.qty ? r.qty.value : "", unit: r.unit ? r.unit.value : "" });
        }
        if (!lines.length) throw new Error("Nothing to save yet: choose an account and enter an amount.");
        if (mode === "simple") {
          if (!acct.value) throw new Error("Please choose the Cash or Bank account.");
          const t = lines.reduce((s, l) => s + Math.round(parseFloat(l.amount) * 100), 0);
          lines.push({ ledger_id: acct.value, side: vtype === "Receipt" ? "Dr" : "Cr", amount: (t / 100).toFixed(2) });
        }
        const res = await HL.post("/api/voucher/save", { id: isNew ? undefined : v.id, vtype, date: S.date, narration: narr.value, status: S.status, ref: refInp.value, date_approx: approx.checked, lines, items: itemsTable ? itemsTable.get() : undefined, gst: itemsTable && HL.gstCfg && HL.gstCfg.on ? S.gst : undefined, gst_party: S.gstParty || (S.gst && lines.find(l => HL.isParty(l.ledger_id)) || {}).ledger_id,
          meta: { inst_no: mNo.value, inst_date: mDt.value.trim() ? (parseDateInput(mDt.value, S.date) || (() => { throw new Error("Please type the cheque date like 15-11-2026."); })()) : null, bank_name: mBk.value, post_dated: mPd.checked, class_name: clsSel.value } });
        S.dirty = false; HL.S.lastVoucherDate = S.date; if (acct && acct.value) HL.S.lastAcct = acct.value;
        say(`${vtype} no. ${res.number} saved (${rs(res.total_paise)}).`, "ok");
        await loadMasters();
        if (!isNew) HL.back(); else { HL.cur.guard = null; HL.go("voucher", { vtype, date: S.date }, { replace: true }); }
      } catch (e) { fail(e); }
      finally { saving = false; }
    }
    HL.cur.guard = () => !S.dirty || confirm("You have not saved this voucher. Leave without saving?");
    const sw = t => () => { if (!S.dirty || confirm("Switch voucher type? The current entry has not been saved.")) { S.dirty = false; HL.go("voucher", { vtype: t, date: S.date }, { replace: true }); } };
    const optLabel = () => S.status === "optional" ? "Optional: ON" : "Optional voucher";
    const toggleOpt = () => { S.status = S.status === "optional" ? "posted" : "optional"; S.dirty = true; say(S.status === "optional" ? "Optional voucher: it will not count in any total until you make it regular." : "Regular voucher: it counts in totals.", "ok"); };
    HL.onKey = e => {
      if (e.altKey && !isNew && !e.ctrlKey && HL.voucherActs) { const k = e.key.toLowerCase(); if (k === "2" || e.code === "Digit2") { e.preventDefault(); HL.go("voucher", { copy_id: v.id }, { replace: true }); return true; } if (k === "d") { e.preventDefault(); HL.voucherActs.del(); return true; } if (k === "x") { e.preventDefault(); HL.voucherActs.cancel(); return true; } }
      if (e.ctrlKey && e.key.toLowerCase() === "l") { e.preventDefault(); toggleOpt(); return true; }
      if (e.ctrlKey && e.key === "Enter") { e.preventDefault(); save(); return true; }
      if (e.ctrlKey && e.key.toLowerCase() === "a") { e.preventDefault(); save(); return true; }
      const kk = (e.ctrlKey ? "Ctrl+" : "") + e.key;
      const t = Object.keys(VOUCHER_KEYS).find(k => VOUCHER_KEYS[k] === kk);
      if (t && isNew) { e.preventDefault(); sw(t)(); return true; }
    };
    const keys = [{ k: "Ctrl+A", label: "Accept (save)", fn: save }, { k: "Ctrl+L", label: "Optional voucher", fn: toggleOpt }, { k: "Esc", label: "Back", fn: HL.back }, "sep"];
    if (isNew) for (const t of ["Contra", "Payment", "Receipt", "Journal", "Sales", "Purchase", "Credit Note", "Debit Note", "Memorandum", "Reversing Journal"]) keys.push({ k: VOUCHER_KEYS[t], label: t, fn: sw(t) });
    if (!isNew) {
      keys.push({ k: "Alt+2", label: "Duplicate", fn: () => { if (!S.dirty || confirm("Leave without saving?")) { S.dirty = false; HL.go("voucher", { copy_id: v.id }, { replace: true }); } } });
      const toggleCancel = async () => {
        const cancelling = v.status !== "cancelled";
        if (!(await confirmBox(cancelling ? "Cancel this voucher?" : "Restore this voucher?", cancelling ? "It will no longer count in any total, but stays in the records (shown struck through in the Day Book). You can restore it later." : "It will count in totals again.", cancelling ? "Yes, cancel it" : "Yes, restore", cancelling))) return;
        try { await HL.post("/api/voucher/status", { id: v.id, status: cancelling ? "cancelled" : (S.status === "posted" ? "posted" : S.status) }); say(cancelling ? "Voucher cancelled." : "Voucher restored.", "ok"); await loadMasters(); S.dirty = false; HL.back(); } catch (e) { fail(e); }
      };
      const doDelete = async () => {
        if (!(await confirmBox("Delete this voucher?", "It is removed for good (a copy is kept in the audit log). To keep it in the records, use Cancel instead.", "Yes, delete it", true))) return;
        try { await HL.post("/api/voucher/delete", { id: v.id }); say("Voucher deleted.", "ok"); await loadMasters(); S.dirty = false; HL.back(); } catch (e) { fail(e); }
      };
      HL.voucherActs = { cancel: toggleCancel, del: doDelete, print: () => HL.printVoucher(v.id) };
      keys.push({ k: "Alt+P", label: "Print", fn: () => HL.printVoucher(v.id) });
      keys.push({ k: "Alt+D", label: "Delete", fn: doDelete });
      keys.push({ k: "Alt+X", label: v.status === "cancelled" ? "Restore" : "Cancel", fn: toggleCancel });
      if (v.status === "cancelled") keys[0] = { k: "Ctrl+A", label: "Accept (save)", disabled: true };
    }
    keys.push("sep", { k: "", label: "New ledger", fn: () => HL.ledgerForm({ onsaved: async () => { await loadMasters(); say("Ledger created. Choose it in the list.", "ok"); } }) });
    HL.setKeys(keys);
    setTimeout(() => { (mode === "simple" && !v && !acct.value ? acct : rows[0].led).focus(); }, 40);
    // jump straight to the date for quick back-dated entry
    HL.onKey2 = e => { if (e.key === "F2") { e.preventDefault(); dateInp.focus(); dateInp.select(); return true; } };
  },
};

/* ===================== DAY BOOK ===================== */
HL.screens.daybook = {
  title: "Day Book",
  async render(sc, params) {
    await loadMasters();
    const P = getPeriod();
    const typeSel = h("select", { "aria-label": "Voucher type" }, h("option", { value: "" }, "All types"), ["Payment", "Receipt", "Contra", "Journal", "Sales", "Purchase", "Credit Note", "Debit Note", "Memorandum", "Reversing Journal"].map(t => h("option", { value: t }, t)));
    typeSel.value = params.vtype || "";
    const filt = h("input", { type: "search", placeholder: "Filter these rows...", "aria-label": "Filter rows", style: "min-width:14rem" });
    const canc = h("input", { type: "checkbox", id: "showc" }); canc.checked = !!params.cancelled;
    const extra = h("span", { class: "row", style: "gap:.5rem" }, typeSel, filt, h("label", {}, canc, " Show cancelled / optional"));
    const reload = () => { HL.cur.params = Object.assign({}, params, { vtype: typeSel.value, cancelled: canc.checked }); HL.refresh(); };
    typeSel.onchange = reload; canc.onchange = reload;
    const d = await HL.get("/api/daybook", { from: P.from, to: P.to, vtype: typeSel.value, cancelled: canc.checked ? 1 : 0 });
    const root = h("div", {}, h("h1", { class: "title" }, "Day Book"), h("p", { class: "sub" }, periodText()), periodBar(reload, { extra }));
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Date", "Particulars", "Cost Centre", "Item", "Type", "No.", "Amount"].map((x, i) => h("th", { class: i === 6 ? "r" : "" }, x)))));
    const tb = h("tbody", {}); t.append(tb);
    const trs = [];
    let lastDate = "";
    d.rows.forEach(r => {
      const tr = h("tr", { class: "row" + (r.status === "cancelled" ? " cancelled" : r.status === "optional" ? " optional" : ""), tabindex: "0", "data-text": (r.particulars + " " + r.narration + " " + r.items + " " + r.activities + " " + r.vtype + " " + r.ref).toLowerCase(), onclick: () => HL.go("voucher", { id: r.id }) },
        h("td", {}, r.date !== lastDate ? showDate(r.date) + (r.date_approx ? " ~" : "") : ""),
        h("td", {}, r.particulars, r.narration ? h("div", { class: "muted", style: "font-size:.85em" }, r.narration) : ""),
        h("td", {}, r.activities), h("td", {}, r.items), h("td", {}, r.vtype), h("td", {}, r.number), h("td", { class: "r" }, inr(r.amount_paise)));
      tr.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); tr.click(); } else if (e.key === "ArrowDown") { e.preventDefault(); (tr.nextElementSibling || tr).focus(); } else if (e.key === "ArrowUp") { e.preventDefault(); (tr.previousElementSibling || tr).focus(); } });
      lastDate = r.date; trs.push(tr); tb.append(tr);
    });
    tb.append(h("tr", { class: "total" }, h("td", { colspan: 6 }, "Total (" + d.rows.filter(r => r.status === "posted").length + " entries)"), h("td", { class: "r" }, inr(d.total_paise))));
    filt.addEventListener("input", () => { const q = filt.value.toLowerCase().trim(); trs.forEach(tr => { tr.style.display = !q || tr.dataset.text.includes(q) ? "" : "none"; }); });
    root.append(d.rows.length ? h("div", { class: "scroll" }, t) : h("div", { class: "panel empty" }, "No entries in this period. Try 'Everything' above, or press F5 to record a payment."));
    if (d.truncated) root.append(h("p", { class: "muted" }, "Only the first 5000 entries are shown. Choose a shorter period."));
    sc.replaceChildren(root);
    if (trs[0]) trs[0].focus();
    HL.setKeys([{ k: "Enter", label: "Open entry", fn: () => document.activeElement && document.activeElement.click && document.activeElement.click() }, { k: "Esc", label: "Back", fn: HL.back }, "sep",
      { k: "F5", label: "Payment", fn: () => HL.go("voucher", { vtype: "Payment" }) }, { k: "F6", label: "Receipt", fn: () => HL.go("voucher", { vtype: "Receipt" }) }, { k: "Ctrl+F", label: "Search", fn: () => HL.go("search") }, { k: "", label: "Print", fn: () => window.print() }]);
  },
};
