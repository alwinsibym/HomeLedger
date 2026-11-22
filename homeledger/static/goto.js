/* Go To (Alt+G): type a few letters to jump to any screen, voucher, ledger or activity. Menu bar and Help. */
"use strict";
HL.gotoItems = function () {
  const it = [], add = (label, hint, fn, kind) => it.push({ label, hint: hint || "", fn, kind: kind || "Screen" });
  add("Gateway of HomeLedger", "Main menu", () => HL.go("gateway"));
  add("Select Company (F1)", "Open, create, split, merge, year-end close", () => HL.go("companies"));
  add("GST Setup", "Registration and state", () => HL.go("gstsetup"));
  add("GST Summary", "Output tax, input credit and net payable", () => HL.go("gstsummary"));
  add("GSTR-1 Lists", "B2B, B2C, credit notes, HSN summary", () => HL.go("gstr1"));
  add("TDS Setup", "Natures of payment, rates, limits", () => HL.go("tdssetup"));
  add("TDS Statement", "Tax deducted party by party", () => HL.go("tdsstatement"));
  add("TDS Deposits", "Deducted, deposited and due dates", () => HL.go("tdsdeposits"));
  add("Monthly Payroll", "Salary, payslips", () => HL.go("payrun"));
  add("Employees", "Payroll staff", () => HL.go("employees"));
  add("Pay Heads", "Salary components", () => HL.go("payheads"));
  add("Payroll Register", "Month-wise totals", () => HL.go("payregister"));
  add("Templates & Repeats", "Saved vouchers, rent / EMI repeats", () => HL.go("templates"));
  add("Due Repeat Entries", "Repeats waiting to be entered", () => HL.go("repeats"));
  add("Needs Attention", "Alerts: overdue, TDS, low stock, unusual", () => HL.go("alerts"));
  add("Spending Analysis", "By account, with last year", () => HL.go("spending"));
  add("Year on Year", "This year against last year", () => HL.go("yoy"));
  add("Quick Entry", "Many payments and receipts at once", () => HL.go("quickentry"));
  add("Bill Inbox", "Bill photos waiting to be entered", () => HL.go("billinbox"));
  add("Import from Excel / CSV", "Typed-up notebook or bank statement", () => HL.go("bulkimport"));
  add("Auto-categorise Rules", "Where shops and items belong", () => HL.go("catrules"));
  add("Dashboard", "Overview and charts", () => HL.go("dashboard"));
  add("Day Book", "All entries day by day", () => HL.go("daybook"));
  add("Search", "Find any entry", () => HL.go("search"));
  add("Ledger", "Statement of any account", () => HL.go("ledgers_pick"));
  add("Cash / Bank Book", "Money in hand and in bank", () => HL.go("cashbook"));
  add("Trial Balance", "", () => HL.go("tb"));
  add("Outstandings: Receivable", "", () => HL.go("receivables"));
  add("Outstandings: Payable", "", () => HL.go("payables"));
  add("Bank Reconciliation", "", () => HL.go("bankrec"));
  add("Stock Summary", "", () => HL.go("stocksummary"));
  add("Stock Items", "Masters", () => HL.go("stockitems"));
  add("Post-dated Vouchers", "", () => HL.go("postdated"));
  add("Cheque Register", "", () => HL.go("chequereg"));
  add("Voucher Classes", "Masters", () => HL.go("classes"));
  add("Configuration (F12)", "", () => HL.configure());
  add("Group Summary", "", () => HL.go("groupsummary"));
  add("Receipts & Payments", "", () => HL.go("recpay"));
  add("Fund Flow", "", () => HL.go("fundflow"));
  add("Budgets", "", () => HL.go("budgets"));
  add("Interest Calculation", "", () => HL.go("interest"));
  add("Scenarios", "", () => HL.go("scenario"));
  [["Stock Groups", "stockgroups"], ["Stock Categories", "stockcategories"], ["Godowns / Locations", "godowns"], ["Price Lists", "prices"], ["Bills of Material", "boms"], ["Godown Summary", "godownsummary"], ["Batches and Expiry", "batchsummary"], ["Pending Orders", "pendingorders"]].forEach(([n, id]) => add(n, "", () => HL.go(id)));
  ["Sales Order", "Purchase Order", "Delivery Note", "Receipt Note", "Stock Journal"].forEach(n => add(n, "", () => HL.go("voucher", { vtype: n })));
  add("Cash Flow", "", () => HL.go("cashflow"));
  add("Ratio Analysis", "", () => HL.go("ratios"));
  add("Profit & Loss", "Income less spending", () => HL.go("pnl"));
  add("Balance Sheet", "What you own and owe", () => HL.go("bs"));
  add("Cost Centres", "Income and spending by cost centre", () => HL.go("activities"));
  add("Item-wise Report", "By item name", () => HL.go("commodities"));
  add("Masters", "Ledgers, groups, cost centres", () => HL.go("masters"));
  add("Opening Balances", "Start-up cash, bank, loans", () => HL.go("openings"));
  add("Company Info", "Name and books beginning date", () => HL.go("company"));
  [["backup", "Backup & Restore"], ["health", "Health Check"], ["export", "Export to Excel"], ["settings", "Settings (text size, look)"], ["security", "Security (sign-in)"], ["audit", "Audit Trail"]]
    .forEach(([k, l]) => add(l, "Utilities", () => HL.go("utilities", { tab: k })));
  [["Payment", "F5"], ["Receipt", "F6"], ["Contra", "F4"], ["Journal", "F7"], ["Sales", "F8"], ["Purchase", "F9"], ["Memorandum", "Ctrl+F10"], ["Reversing Journal", ""], ["Credit Note", "Ctrl+F8"], ["Debit Note", "Ctrl+F9"]]
    .forEach(([v, k]) => add(v + " Voucher", "New entry (" + k + ")", () => HL.go("voucher", { vtype: v }), "Voucher"));
  const m = HL.S.masters;
  if (m) {
    m.ledgers.filter(l => l.is_active).forEach(l => add(l.name, "Ledger · " + l.group_name, () => HL.go("ledger", { ledger_id: l.id }), "Ledger"));
    m.cost_centres.filter(c => c.is_active).forEach(c => add(c.name, "Cost Centre", () => HL.go("activity", { cc_id: c.id }), "Activity"));
  }
  add("Lock", "Sign out until the password is typed", () => HL.lockNow());
  add("Quit", "Close HomeLedger", () => HL.quit());
  return it;
};

HL.openGoTo = function () {
  if (modalStack.length) return;
  const all = HL.gotoItems();
  const inp = h("input", { type: "text", class: "goto-in", placeholder: "Type to search: ledger, report, voucher, activity...", "aria-label": "Go To", autocomplete: "off" });
  const list = h("ul", { class: "goto-list", role: "listbox" });
  let shown = [], sel = 0, m;
  const score = (x, words) => {
    const l = x.label.toLowerCase(), hay = l + " " + x.hint.toLowerCase();
    let sc = 0;
    for (const w of words) { if (!hay.includes(w)) return -1; sc += l.startsWith(w) ? 3 : l.split(/[\s&/()-]+/).some(t => t.startsWith(w)) ? 2 : 1; }
    return sc;
  };
  const draw = () => {
    const words = inp.value.toLowerCase().split(/\s+/).filter(Boolean);
    shown = (words.length ? all.map(x => [score(x, words), x]).filter(p => p[0] >= 0).sort((a, b) => b[0] - a[0]).map(p => p[1]) : all.filter(x => x.kind !== "Ledger" && x.kind !== "Activity")).slice(0, 12);
    sel = Math.min(sel, Math.max(0, shown.length - 1));
    list.replaceChildren(...shown.map((x, i) => h("li", { role: "option", class: i === sel ? "on" : "", onclick: () => pick(i), onmousemove: () => { if (sel !== i) { sel = i; draw(); } } },
      h("span", { class: "gl" }, x.label), h("span", { class: "gh" }, x.hint))));
    if (!shown.length) list.replaceChildren(h("li", { class: "none" }, "Nothing matches “" + inp.value + "”"));
    const on = $("li.on", list); on && on.scrollIntoView({ block: "nearest" });
  };
  const pick = i => { const x = shown[i]; if (!x) return; m.close(); setTimeout(() => x.fn(), 0); };
  inp.addEventListener("input", () => { sel = 0; draw(); });
  inp.addEventListener("keydown", e => {
    if (e.key === "ArrowDown") { e.preventDefault(); sel = Math.min(shown.length - 1, sel + 1); draw(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(0, sel - 1); draw(); }
    else if (e.key === "Enter") { e.preventDefault(); pick(sel); }
  });
  m = modal({ title: "Go To", body: h("div", {}, inp, list), buttons: [], onclose: () => { } });
  m.box.classList.add("goto");
  draw(); inp.focus();
};

HL.openHelp = function () {
  const rows = [["F5 / F6 / F4 / F7", "Payment / Receipt / Contra / Journal"], ["F8 / F9", "Sales / Purchase"], ["Alt+G", "Go To: jump to any screen, ledger or activity"], ["Ctrl+F", "Search entries"], ["Alt+F1", "Dashboard"],
    ["F3 / Alt+K", "Company info"], ["Ctrl+F8 / Ctrl+F9", "Credit Note / Debit Note"], ["Alt+Y", "Data: backup, health check, security"], ["Alt+E", "Export everything to Excel"], ["Ctrl+P / Alt+P", "Print this screen"], ["Ctrl+L / Alt+L", "Lock (when sign-in is on)"],
    ["Enter", "Accept and go to the next field"], ["Esc", "Go back"], ["Ctrl+A", "Accept (save) a voucher"]];
  modal({ title: "Keys and help", wide: true, body: h("div", {}, h("table", { class: "tbl" }, h("tbody", {}, rows.map(([k, d]) => h("tr", {}, h("td", { style: "white-space:nowrap" }, h("b", {}, k)), h("td", {}, d))))),
    h("p", { class: "hint" }, "HomeLedger works only on this computer and does not use the internet. Your data is saved after every entry and backed up automatically.")), buttons: [{ label: "Close", cls: "primary" }] });
};

HL.menuAction = function (a) {
  if (a === "goto") HL.openGoTo();
  else if (a === "company") HL.go("company");
  else if (a === "data") HL.go("utilities");
  else if (a === "export") { const l = h("a", { href: "/api/export", download: "" }); document.body.append(l); l.click(); l.remove(); }
  else if (a === "print") { if (HL.cur && HL.cur.name === "voucher" && HL.cur.params && HL.cur.params.id && HL.voucherActs && HL.voucherActs.print) HL.voucherActs.print(); else window.print(); }
  else if (a === "lock") HL.lockNow();
  else if (a === "help") HL.openHelp();
};
document.addEventListener("click", e => { const b = e.target.closest && e.target.closest("#menubar button"); if (b) HL.menuAction(b.dataset.a); });
document.addEventListener("keydown", e => {
  if (!e.altKey || e.ctrlKey || e.metaKey || (typeof modalStack !== "undefined" && modalStack.length) || (window.HL && HL._lost)) return;
  if (document.getElementById("lock")) return;
  const k = e.key.toLowerCase(), map = { g: "goto", k: "company", y: "data", e: "export", p: "print", l: "lock" };
  if (map[k]) { e.preventDefault(); e.stopPropagation(); HL.menuAction(map[k]); }
}, true);
document.addEventListener("keydown", e => { if (e.key === "F1" && !e.altKey && !document.getElementById("lock")) { e.preventDefault(); e.stopPropagation(); if (!modalStack.length) { if (e.shiftKey) HL.openHelp(); else if (!HL.cur || HL.cur.name !== "voucher") HL.go("companies"); } } }, true);

HL.applyLook = function (look) {
  look = look === "classic" ? "classic" : "prime";
  document.documentElement.dataset.look = look;
  try { localStorage.setItem("hl-look", look); } catch (e) { }
};
