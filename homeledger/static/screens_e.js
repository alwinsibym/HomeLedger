/* More reports: Group Summary, Receipts & Payments, Fund Flow, Scenarios, Interest, Budgets */

const _tbl = heads => { const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, heads.map((x, i) => h("th", { class: i > 0 ? "r" : "" }, x))))); const tb = h("tbody", {}); t.append(tb); return [t, tb]; };
const _page = (title, sub, ...kids) => h("div", {}, h("h1", { class: "title" }, title), h("p", { class: "sub" }, sub), ...kids);

HL.screens.groupsummary = {
  title: "Group Summary",
  async render(sc, params) {
    await loadMasters();
    const P = getPeriod();
    const r = await HL.get("/api/groupsummary", { from: P.from, to: P.to, group_id: params.group_id || 0 });
    const [t, tb] = _tbl(["Particulars", "Opening", "Debit", "Credit", "Closing"]);
    const bal2 = v => v ? bal(v) : "";
    r.items.forEach(x => {
      const tr = h("tr", { class: "row", tabindex: "0", onclick: () => x.type === "group" ? HL.go("groupsummary", { group_id: x.id }) : HL.go("ledger", { ledger_id: x.id }) },
        h("td", { class: x.type === "group" ? "grp" : "" }, x.name), h("td", { class: "r" }, bal2(x.opening)), h("td", { class: "r" }, x.dr ? inr(x.dr) : ""), h("td", { class: "r" }, x.cr ? inr(x.cr) : ""), h("td", { class: "r" }, bal2(x.closing)));
      rowKeys(tr); tb.append(tr);
    });
    if (!r.items.length) tb.append(h("tr", {}, h("td", { colspan: 5, class: "empty" }, "Nothing under this group yet.")));
    else tb.append(h("tr", { class: "total" }, h("td", {}, "Total"), h("td", { class: "r" }, bal2(r.total.opening)), h("td", { class: "r" }, inr(r.total.dr)), h("td", { class: "r" }, inr(r.total.cr)), h("td", { class: "r" }, bal2(r.total.closing))));
    sc.replaceChildren(_page("Group Summary: " + r.title, periodText() + " · Enter opens a group or ledger", periodBar(() => HL.refresh()), t));
    HL.setKeys([BACK, params.group_id ? { k: "Alt+Up", label: "Up one level", fn: () => HL.go("groupsummary", { group_id: r.parent_id || 0 }, { replace: true }) } : null].filter(Boolean));
    const f = $("tbody tr.row", sc); f && f.focus();
  },
};

HL.screens.recpay = {
  title: "Receipts & Payments",
  async render(sc) {
    await loadMasters();
    const P = getPeriod();
    const r = await HL.get("/api/recpay", { from: P.from, to: P.to });
    const [t, tb] = _tbl(["Particulars", "Amount"]);
    const line = (n, v, c) => tb.append(h("tr", { class: c || "" }, h("td", { class: c ? "" : "ind1" }, n), h("td", { class: "r" }, inr(v))));
    line("Opening Cash and Bank", r.opening, "grp");
    tb.append(h("tr", { class: "grp" }, h("td", {}, "Receipts"), h("td", {}))); r.receipts.forEach(x => line(x[0], x[1])); line("Total receipts", r.total_receipts, "total");
    tb.append(h("tr", { class: "grp" }, h("td", {}, "Payments"), h("td", {}))); r.payments.forEach(x => line(x[0], x[1])); line("Total payments", r.total_payments, "total");
    line("Closing Cash and Bank", r.closing, "grp");
    sc.replaceChildren(_page("Receipts & Payments", periodText(), periodBar(() => HL.refresh()), t,
      h("div", { class: "banner " + (r.check ? "ok" : "err") }, r.check ? "Opening + receipts - payments equals closing." : "These figures do not add up.")));
    HL.setKeys([BACK]);
  },
};

HL.screens.fundflow = {
  title: "Fund Flow",
  async render(sc) {
    await loadMasters();
    const P = getPeriod();
    const r = await HL.get("/api/fundflow", { from: P.from, to: P.to });
    const [t, tb] = _tbl(["Particulars", "Amount"]);
    const line = (n, v, c) => tb.append(h("tr", { class: c || "" }, h("td", { class: c ? "" : "ind1" }, n), h("td", { class: "r" }, inr(v))));
    tb.append(h("tr", { class: "grp" }, h("td", {}, "Sources of funds"), h("td", {}))); r.sources.forEach(x => line(x[0], x[1])); line("Total sources", r.total_sources, "total");
    tb.append(h("tr", { class: "grp" }, h("td", {}, "Applications of funds"), h("td", {}))); r.applications.forEach(x => line(x[0], x[1])); line("Total applications", r.total_applications, "total");
    line("Increase / (decrease) in Cash and Bank", r.cash_change, "grp");
    sc.replaceChildren(_page("Fund Flow", periodText() + " · worked out from the changes in your balance sheet", periodBar(() => HL.refresh()), t,
      h("div", { class: "banner " + (r.check ? "ok" : "err") }, r.check ? "Sources less applications equals the change in Cash and Bank." : "These figures do not add up.")));
    HL.setKeys([BACK]);
  },
};

HL.screens.scenario = {
  title: "Scenarios",
  async render(sc, params) {
    await loadMasters();
    const P = getPeriod();
    const opt = params.optional !== 0, memo = !!params.memo;
    const r = await HL.get("/api/scenario", { from: P.from, to: P.to, optional: opt ? 1 : 0, memo: memo ? 1 : 0 });
    const cOpt = h("input", { type: "checkbox", checked: opt, id: "s_opt" }), cMemo = h("input", { type: "checkbox", checked: memo, id: "s_memo" });
    const go = () => HL.go("scenario", { optional: cOpt.checked ? 1 : 0, memo: cMemo.checked ? 1 : 0 }, { replace: true });
    cOpt.onchange = go; cMemo.onchange = go;
    const [t, tb] = _tbl(["Profit & Loss", "As it is", "In this scenario"]);
    const named = (list, side) => list.forEach(x => tb.append(h("tr", {}, h("td", { class: "ind1" }, x.name), h("td", { class: "r" }, ""), h("td", { class: "r" }, inr(x.amount)))));
    tb.append(h("tr", { class: "grp" }, h("td", {}, "Income"), h("td", {}), h("td", {}))); named(r.pl.income);
    tb.append(h("tr", { class: "grp" }, h("td", {}, "Expenses"), h("td", {}), h("td", {}))); named(r.pl.expenses);
    tb.append(h("tr", { class: "total" }, h("td", {}, "Net profit / (loss)"), h("td", { class: "r" }, bal(r.actual_net)), h("td", { class: "r" }, bal(r.scenario_net))));
    sc.replaceChildren(_page("Scenarios", periodText() + " · " + r.vouchers_added + " extra voucher(s) included", periodBar(() => HL.refresh()),
      h("div", { class: "row", style: "gap:1.2rem;margin:.4rem 0 .8rem" }, h("label", { class: "f", style: "flex-direction:row;gap:.4rem;align-items:center" }, cOpt, "Include Optional vouchers"), h("label", { class: "f", style: "flex-direction:row;gap:.4rem;align-items:center" }, cMemo, "Include Memorandum vouchers")), t,
      h("p", { class: "hint" }, "Use this to see the effect of cheques you have post-dated or things you have only noted down. Nothing here changes your real books.")));
    HL.setKeys([BACK]);
  },
};

HL.screens.interest = {
  title: "Interest Calculation",
  async render(sc, params) {
    await loadMasters();
    const P = getPeriod();
    const groups = HL.S.masters.groups;
    const sel = h("select", { "aria-label": "Group" }, h("option", { value: "" }, "All real accounts"), groups.map(g => h("option", { value: g.id }, g.name)));
    const dg = groups.find(g => g.code === "DEBTORS");
    sel.value = String(params.group_id !== undefined ? params.group_id : (dg ? dg.id : ""));
    const rate = h("input", { type: "text", inputmode: "decimal", value: params.rate || "12", style: "width:5rem", "aria-label": "Rate percent per year" });
    const side = h("select", { "aria-label": "Balance side" }, h("option", { value: "Dr" }, "On debit balances (owed to you)"), h("option", { value: "Cr" }, "On credit balances (you owe)")); side.value = params.side || "Dr";
    const apply = () => HL.go("interest", { group_id: sel.value, rate: rate.value, side: side.value }, { replace: true });
    [sel, side].forEach(x => x.onchange = apply); rate.onchange = apply;
    let r = null, err = "";
    try { r = await HL.get("/api/interest", { from: P.from, to: P.to, rate: rate.value, group_id: sel.value || 0, side: side.value }); } catch (e) { err = e.message; }
    const [t, tb] = _tbl(["Account", "Closing balance", "Average balance", "Interest"]);
    if (r) {
      r.rows.forEach(x => tb.append(h("tr", {}, h("td", {}, x.name), h("td", { class: "r" }, bal(x.closing)), h("td", { class: "r" }, inr(x.avg)), h("td", { class: "r" }, inr(x.interest)))));
      if (!r.rows.length) tb.append(h("tr", {}, h("td", { colspan: 4, class: "empty" }, "No balances to charge interest on in this period.")));
      else tb.append(h("tr", { class: "total" }, h("td", {}, "Total interest"), h("td", {}), h("td", {}), h("td", { class: "r" }, inr(r.total))));
    }
    sc.replaceChildren(_page("Interest Calculation", periodText() + (r ? " · " + r.days + " days" : ""), periodBar(() => HL.refresh()),
      h("div", { class: "row", style: "gap:1rem;flex-wrap:wrap;margin:.4rem 0 .8rem;align-items:flex-end" }, h("label", { class: "f" }, "Group", sel), h("label", { class: "f" }, "Rate % per year", rate), h("label", { class: "f" }, "Charge", side)),
      err ? h("div", { class: "banner err" }, err) : t, r ? h("p", { class: "hint" }, r.note) : null));
    HL.setKeys([BACK]);
  },
};

HL.screens.budgets = {
  title: "Budgets",
  async render(sc) {
    await loadMasters();
    const P = getPeriod();
    const r = await HL.get("/api/budgetreport", { from: P.from, to: P.to });
    const [t, tb] = _tbl(["Account", "Budget (" + r.fy + ")", "Actual (this period)", "Left / (over)", "Used"]);
    r.rows.forEach(x => {
      const over = x.variance < 0;
      const tr = h("tr", { class: "row" + (over ? " cancelled" : ""), tabindex: "0", onclick: () => edit(x.kind, x.target_id, x.budget) }, h("td", {}, x.name), h("td", { class: "r" }, inr(x.budget)), h("td", { class: "r" }, inr(x.actual)),
        h("td", { class: "r", style: over ? "color:#b3261e" : "" }, over ? "(" + inr(-x.variance) + ")" : inr(x.variance)), h("td", { class: "r" }, x.used_pct == null ? "" : x.used_pct + " %"));
      rowKeys(tr); tb.append(tr);
    });
    if (!r.rows.length) tb.append(h("tr", {}, h("td", { colspan: 5, class: "empty" }, "No budgets for " + r.fy + ". Press Alt+C to set one, for example a yearly limit for an expense account.")));
    function edit(kind, id, cur) {
      const k = h("select", { "aria-label": "Budget for" }, h("option", { value: "ledger" }, "A ledger"), h("option", { value: "group" }, "A group")); k.value = kind || "ledger";
      const pick = picker({ options: () => k.value === "group" ? HL.S.masters.groups.map(g => ({ value: g.id, label: g.name, data: g })) : ledgerOptions(), value: id || null, placeholder: "Choose account..." });
      k.onchange = () => pick.set(null);
      const amt = h("input", { type: "text", inputmode: "decimal", value: cur ? (cur / 100).toFixed(2) : "", "aria-label": "Budget amount" });
      const body = h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f" }, "Budget for", k), h("label", { class: "f" }, "Account", pick.el), h("label", { class: "f" }, "Amount for the year " + r.fy + " (₹); 0 removes it", amt));
      const m = modal({ title: "Budget", body, buttons: [{ label: "Cancel", onclick: m => m.close() }, { label: "Accept", cls: "primary", onclick: async () => { try { await HL.post("/api/budget/save", { kind: k.value, target_id: pick.value, fy: r.fy, amount: amt.value }); m.close(); HL.refresh(); } catch (e) { fail(e); } } }] });
    }
    sc.replaceChildren(_page("Budgets", periodText() + " · yearly budget against what has actually happened in the period", periodBar(() => HL.refresh()), t));
    HL.setKeys([BACK, { k: "Alt+C", label: "Set a budget", fn: () => edit() }]);
    const f = $("tbody tr.row", sc); f && f.focus();
  },
};
