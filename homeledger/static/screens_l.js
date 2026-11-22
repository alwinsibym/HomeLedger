/* Templates and repeats, Needs Attention (alerts), Spending Analysis, Year on Year */

HL.templateDialog = v => {
  const nm = h("input", { type: "text", maxlength: 60, placeholder: "e.g. Monthly rent" });
  const ev = h("select", {}, [["", "Do not repeat"], ["monthly", "Every month"], ["weekly", "Every week"], ["quarterly", "Every 3 months"], ["yearly", "Every year"]].map(([k, t]) => h("option", { value: k }, t)));
  const nd = h("input", { type: "date", value: addDays(v.date, 30) });
  const m = modal({ title: "Save as Template", body: h("div", { class: "form" },
      h("label", {}, "Template name", nm), h("label", {}, "Repeat", ev), h("label", {}, "Next one due on", nd),
      h("p", { class: "hint" }, "Repeating entries are never posted by themselves. They wait on the 'Due repeat entries' list until you tick and enter them.")),
    buttons: [{ label: "Cancel", onclick: m => m.close() }, { label: "Save template", cls: "primary", onclick: async () => {
      try { await HL.post("/api/template/save", { voucher_id: v.id, name: nm.value, repeat_every: ev.value, next_due: nd.value }); m.close(); say("Template saved.", "ok"); } catch (e) { fail(e); } } }] });
  nm.focus();
};

HL.screens.templates = {
  title: "Templates & Repeats",
  async render(sc) {
    await loadMasters();
    const d = await HL.get("/api/templates");
    const [t, tb] = _tbl(["Name", "Type", "Amount", "Repeats", "Next due", ""]);
    d.rows.forEach(r => tb.append(h("tr", {},
      h("td", {}, h("b", {}, r.name), h("div", { class: "hint" }, r.lines.map(l => l.ledger_name).join(" / "))), h("td", {}, r.vtype), h("td", { class: "r" }, rs(r.total_paise)),
      h("td", {}, r.repeat_label), h("td", {}, r.next_due ? showDate(r.next_due) : ""),
      h("td", { class: "r" }, h("button", { class: "btn primary", type: "button", onclick: () => HL.go("voucher", { tpl_id: r.id, vtype: r.vtype }) }, "Use"), " ",
        h("button", { class: "btn", type: "button", onclick: () => repeatDlg(r) }, "Repeat…"), " ",
        h("button", { class: "btn", type: "button", onclick: async () => { if (await confirmBox("Delete template?", "Entries already made from it stay.", "Delete", true)) { await HL.post("/api/template/delete", { id: r.id }); HL.refresh(); } } }, "Delete")))));
    if (!d.rows.length) tb.append(h("tr", {}, h("td", { colspan: 6, class: "empty" }, "No templates yet. Open any saved Payment, Receipt, Contra or Journal and choose 'Save as template'.")));
    const repeatDlg = r => {
      const ev = h("select", {}, [["", "Do not repeat"], ["monthly", "Every month"], ["weekly", "Every week"], ["quarterly", "Every 3 months"], ["yearly", "Every year"]].map(([k, x]) => h("option", { value: k, selected: k === r.repeat_every }, x)));
      const nd = h("input", { type: "date", value: r.next_due || todayIso() });
      modal({ title: "Repeat: " + r.name, body: h("div", { class: "form" }, h("label", {}, "Repeat", ev), h("label", {}, "Next one due on", nd)),
        buttons: [{ label: "Cancel", onclick: m => m.close() }, { label: "Save", cls: "primary", onclick: async m => { try { await HL.post("/api/template/repeat", { id: r.id, repeat_every: ev.value, next_due: nd.value }); m.close(); HL.refresh(); } catch (e) { fail(e); } } }] });
    };
    sc.replaceChildren(_page("Templates & Repeats", "Use saves typing; repeating entries wait for your OK", t,
      h("div", { style: "margin-top:.8rem" }, h("button", { class: "btn", onclick: () => HL.go("repeats") }, "Due repeat entries…"))));
    HL.setKeys([BACK, { k: "", label: "Due repeats", fn: () => HL.go("repeats") }]);
  },
};

HL.screens.repeats = {
  title: "Due Repeat Entries",
  async render(sc) {
    await loadMasters();
    const d = await HL.get("/api/repeats/due");
    const rows = d.rows.map(r => Object.assign({ use: true }, r));
    const [t, tb] = _tbl(["Enter", "Date", "Template", "Type", "Amount"]);
    rows.forEach(r => { const c = h("input", { type: "checkbox", checked: true, onchange: () => { r.use = c.checked; } });
      tb.append(h("tr", {}, h("td", {}, c), h("td", {}, showDate(r.date)), h("td", {}, r.name), h("td", {}, r.vtype), h("td", { class: "r" }, rs(r.total_paise)))); });
    if (!rows.length) tb.append(h("tr", {}, h("td", { colspan: 5, class: "empty" }, "Nothing is due.")));
    const go = async () => {
      const u = rows.filter(r => r.use); if (!u.length) { say("Tick at least one.", "err"); return; }
      // entries of one template must go in date order: only allow a ticked run starting from the earliest
      if (!await confirmBox("Enter " + u.length + " voucher(s)?", "Each becomes a normal voucher with the date shown.", "Enter them")) return;
      try { const r = await HL.post("/api/repeats/run", { items: u.map(x => ({ template_id: x.template_id, date: x.date })) }); say(r.made + " voucher(s) entered.", "ok"); await loadMasters(); HL.refresh(); } catch (e) { fail(e); }
    };
    sc.replaceChildren(_page("Due Repeat Entries", "Tick what to enter. Missed months show as separate lines.", t, rows.length ? h("div", { style: "margin-top:.8rem" }, h("button", { class: "btn primary", onclick: go }, "Enter the ticked entries")) : ""));
    HL.setKeys([BACK, { k: "Ctrl+A", label: "Enter ticked", fn: go }]);
  },
};

HL.alertList = (rows, limit) => {
  const ul = h("ul", { class: "alerts" });
  rows.slice(0, limit || rows.length).forEach(a => ul.append(h("li", { class: "al " + a.level },
    h("span", { class: "dot", "aria-hidden": "true" }), h("span", { class: "tx" }, a.text),
    a.go ? h("button", { class: "btn", type: "button", onclick: () => HL.go(a.go[0], a.go[1]) }, "Open") : "")));
  return ul;
};

HL.screens.alerts = {
  title: "Needs Attention",
  async render(sc) {
    await loadMasters();
    const d = await HL.get("/api/alerts");
    sc.replaceChildren(_page("Needs Attention", "Overdue bills, TDS due, low stock, repeats and unusual entries",
      d.rows.length ? HL.alertList(d.rows) : h("div", { class: "banner ok" }, "Nothing needs attention right now.")));
    HL.setKeys([BACK]);
  },
};

HL.screens.spending = {
  title: "Spending Analysis",
  async render(sc, params) {
    await loadMasters();
    const nature = params.nature || "expense", P = getPeriod();
    const d = await HL.get("/api/insights/spending", { from: P.from, to: P.to, nature });
    const word = nature === "expense" ? "Spending" : "Income";
    const root = _page(word + " Analysis", periodText() + " · compared with " + showDate(d.prev_from) + " to " + showDate(d.prev_to) + " · click a row for its entries", periodBar(() => HL.refresh()));
    root.append(h("div", { class: "row", style: "gap:.5rem;margin:.4rem 0" },
      h("button", { class: "btn" + (nature === "expense" ? " primary" : ""), onclick: () => HL.go("spending", { nature: "expense" }, { replace: true }) }, "Spending"),
      h("button", { class: "btn" + (nature === "income" ? " primary" : ""), onclick: () => HL.go("spending", { nature: "income" }, { replace: true }) }, "Income")));
    const chg = (a, b) => b ? (a >= b ? "+" : "") + Math.round((a - b) / b * 100) + "%" : (a ? "new" : "");
    root.append(h("div", { class: "card" }, h("h3", {}, "By group"),
      hbars(d.groups.map(g => ({ label: g.group + " (" + chg(g.amount, g.previous) + ")", value: g.amount })), { color: nature === "expense" ? 2 : 1 })));
    const [t, tb] = _tbl(["Account", "Group", "Entries", "This period", "Share", "Last year", "Change"]);
    d.rows.forEach(r => tb.append(h("tr", { class: "row", tabindex: "0", onclick: () => HL.go("ledger", { ledger_id: r.ledger_id }) },
      h("td", {}, r.name), h("td", {}, r.group), h("td", { class: "r" }, r.count), h("td", { class: "r" }, rs(r.amount)),
      h("td", { class: "r" }, d.total ? Math.round(r.amount / d.total * 100) + "%" : ""), h("td", { class: "r" }, rs(r.previous)), h("td", { class: "r" }, chg(r.amount, r.previous)))));
    tb.append(h("tr", { class: "total" }, h("td", {}, "Total"), h("td"), h("td"), h("td", { class: "r" }, rs(d.total)), h("td"), h("td", { class: "r" }, rs(d.previous_total)), h("td", { class: "r" }, chg(d.total, d.previous_total))));
    root.append(h("div", { class: "scroll", style: "margin-top:.8rem" }, t));
    sc.replaceChildren(root);
    HL.setKeys([BACK, { k: "", label: "Print", fn: () => window.print() }]);
  },
};

HL.screens.yoy = {
  title: "Year on Year",
  async render(sc) {
    await loadMasters();
    const d = await HL.get("/api/insights/yoy", { on: todayIso() });
    const lab = m => monthLabel(m.month);
    const mk = key => d.this_year.map((m, i) => ({ label: lab(m), long: monthLabel(m.month, true), vals: [m[key], d.last_year[i][key]] }));
    const ser = [{ name: d.label, c: 1 }, { name: d.prev_label, c: 5 }];
    const leg = [{ name: d.label, color: "var(--s1)" }, { name: d.prev_label, color: "var(--s5)" }];
    const tot = (a, k) => a.reduce((x, m) => x + m[k], 0);
    const root = _page("Year on Year", "Financial year " + d.label + " against " + d.prev_label);
    root.append(h("div", { class: "banner" }, `Spending: ${rs(tot(d.this_year, "expense"), 0)} against ${rs(tot(d.last_year, "expense"), 0)} · Income: ${rs(tot(d.this_year, "income"), 0)} against ${rs(tot(d.last_year, "income"), 0)}`));
    for (const [key, title] of [["expense", "Spending by month"], ["income", "Income by month"]])
      root.append(chartCard({ title, sub: "Click a month to see its entries", legend: leg,
        draw: () => barChart({ data: mk(key), series: ser, onbar: dd => { const i = d.this_year.findIndex(m => lab(m) === dd.label); if (i < 0) return; const ym = d.this_year[i].month; const [y, mo] = ym.split("-"); HL.S.period = { id: "custom", from: ym + "-01", to: lastDayOfMonth(+y, +mo) }; HL.go("daybook"); } }),
        table: () => simpleTable(["Month", d.label, d.prev_label], d.this_year.map((m, i) => [monthLabel(m.month, true), rs(m[key]), rs(d.last_year[i][key])])) }));
    sc.replaceChildren(root);
    HL.setKeys([BACK, { k: "", label: "Print", fn: () => window.print() }]);
  },
};
