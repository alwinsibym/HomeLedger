/* Payroll: pay heads, employees, monthly run with payslips, register */
const _paise = v => { const x = String(v == null ? "" : v).replace(/[,\s]/g, ""); return /^\d+(\.\d{1,2})?$/.test(x) ? Math.round(parseFloat(x) * 100) : 0; };
const _mf = p => (p / 100).toFixed(2);

HL.screens.payheads = {
  title: "Pay Heads",
  async render(sc) {
    await loadMasters(); const hs = await HL.get("/api/payroll/heads");
    const [t, tb] = _tbl(["Pay head", "Type", "How it is worked out", "Ledger for deductions", "In use"]);
    const ledName = id => { const l = (HL.S.masters.ledgers || []).find(x => x.id === id); return l ? l.name : "(auto)"; };
    const edit = n => {
      const nm = h("input", { type: "text", value: n ? n.name : "", "aria-label": "Name" });
      const kind = h("select", { "aria-label": "Type" }, h("option", { value: "earning" }, "Earning (added to pay)"), h("option", { value: "deduction" }, "Deduction (taken from pay)")); kind.value = n ? n.kind : "earning";
      const calc = h("select", { "aria-label": "Calculation" }, h("option", { value: "fixed" }, "Fixed amount per employee"), h("option", { value: "percent_basic" }, "Percent of basic salary (deductions only)")); calc.value = n ? n.calc : "fixed";
      const basic = h("input", { type: "checkbox", checked: !!(n && n.is_basic) }), act = h("input", { type: "checkbox", checked: n ? !!n.is_active : true });
      modal({ title: n ? "Pay head" : "New pay head", body: h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f" }, "Name", nm), h("label", { class: "f" }, "Type", kind), h("label", { class: "f" }, "Calculation", calc),
        h("label", { class: "f", style: "flex-direction:row;gap:.4rem;align-items:center" }, basic, "This is the basic salary (percent deductions use it)"), h("label", { class: "f", style: "flex-direction:row;gap:.4rem;align-items:center" }, act, "In use"),
        h("p", { class: "hint" }, "A deduction creates its own 'Payable' ledger when salary is posted (for example 'Provident Fund (employee) Payable').")),
        buttons: [{ label: "Cancel", onclick: m => m.close() }, { label: "Accept", cls: "primary", onclick: async m => { try { await HL.post("/api/payroll/head/save", { id: n && n.id, name: nm.value, kind: kind.value, calc: calc.value, is_basic: basic.checked, ledger_id: n && n.ledger_id, sort: n && n.sort, is_active: act.checked }); m.close(); HL.refresh(); } catch (e) { fail(e); } } }] });
    };
    hs.forEach(n => { const tr = h("tr", { class: "row", tabindex: "0", onclick: () => edit(n) }, h("td", {}, n.name + (n.is_basic ? " (basic)" : "")), h("td", {}, n.kind === "earning" ? "Earning" : "Deduction"), h("td", {}, n.calc === "fixed" ? "Fixed amount" : "% of basic"), h("td", {}, n.kind === "deduction" ? ledName(n.ledger_id) : ""), h("td", {}, n.is_active ? "Yes" : "No")); rowKeys(tr); tb.append(tr); });
    sc.replaceChildren(_page("Pay Heads", "Click one to change it", t, h("div", { style: "margin-top:.6rem" }, h("button", { class: "btn", onclick: () => edit(null) }, "New pay head"))));
    HL.setKeys([BACK]);
  },
};

HL.screens.employees = {
  title: "Employees",
  async render(sc) {
    const [hs, es] = await Promise.all([HL.get("/api/payroll/heads"), HL.get("/api/payroll/employees")]);
    const act = hs.filter(x => x.is_active);
    const [t, tb] = _tbl(["Name", "Designation", "PAN", "Joined", "Monthly earnings", "Status"]);
    const edit = e => {
      const f = (v, a) => h("input", Object.assign({ type: "text", value: v || "" }, a || {}));
      const nm = f(e && e.name, { "aria-label": "Name" }), des = f(e && e.designation, { "aria-label": "Designation" }), pan = f(e && e.pan, { maxlength: "10", style: "text-transform:uppercase", "aria-label": "PAN" });
      const jn = f(e && e.joined ? showDate(e.joined) : "", { "aria-label": "Joined" }), lf = f(e && e.left_on ? showDate(e.left_on) : "", { "aria-label": "Left" });
      const ac = h("input", { type: "checkbox", checked: e ? !!e.is_active : true });
      const ins = {};
      const sRows = act.map(x => { const st = e && e.structure[x.id]; const pct = x.calc === "percent_basic";
        const i = h("input", { type: "text", inputmode: "decimal", class: "amt", value: st ? (pct ? st.rate_bp / 100 : _mf(st.amount_paise)) : "", "aria-label": x.name }); ins[x.id] = [i, pct];
        return h("label", { class: "f" }, x.name + (pct ? " (% of basic)" : x.kind === "earning" ? " (₹ per month)" : " (₹ per month)"), i); });
      modal({ title: e ? "Employee" : "New employee", wide: true, body: h("div", { class: "fgrid" }, h("label", { class: "f" }, "Name", nm), h("label", { class: "f" }, "Designation", des), h("label", { class: "f" }, "PAN", pan), h("label", { class: "f" }, "Joined on", jn), h("label", { class: "f" }, "Left on (if any)", lf),
        h("label", { class: "f", style: "flex-direction:row;gap:.4rem;align-items:center" }, ac, "Working here"), h("h4", { style: "grid-column:1/-1;margin:.4rem 0 0" }, "Monthly salary structure (full month)"), ...sRows),
        buttons: [{ label: "Cancel", onclick: m => m.close() }, { label: "Accept", cls: "primary", onclick: async m => { try {
          const structure = {}; for (const [id, [i, pct]] of Object.entries(ins)) { const v = i.value.trim(); if (!v) continue; structure[id] = pct ? { rate_bp: Math.round(parseFloat(v) * 100) || 0 } : { amount_paise: _paise(v) }; }
          const dj = jn.value.trim() ? parseDateInput(jn.value, todayIso()) : "", dl = lf.value.trim() ? parseDateInput(lf.value, todayIso()) : "";
          if ((jn.value.trim() && !dj) || (lf.value.trim() && !dl)) { say("Please type dates like 01-04-2026.", "err"); return; }
          await HL.post("/api/payroll/employee/save", { id: e && e.id, name: nm.value, designation: des.value, pan: pan.value, joined: dj, left_on: dl, is_active: ac.checked, structure }); m.close(); HL.refresh(); } catch (er) { fail(er); } } }] });
    };
    es.forEach(e => { const earn = act.filter(x => x.kind === "earning").reduce((s, x) => s + ((e.structure[x.id] || {}).amount_paise || 0), 0);
      const tr = h("tr", { class: "row", tabindex: "0", onclick: () => edit(e) }, h("td", {}, e.name), h("td", {}, e.designation), h("td", {}, e.pan), h("td", {}, e.joined ? showDate(e.joined) : ""), h("td", { class: "r" }, inr(earn)), h("td", {}, e.is_active ? "Working" : "Left")); rowKeys(tr); tb.append(tr); });
    if (!es.length) tb.append(h("tr", {}, h("td", { colspan: 6, class: "empty" }, "No employees yet.")));
    sc.replaceChildren(_page("Employees", "Click one to change; the salary structure is for a full month", t, h("div", { style: "margin-top:.6rem" }, h("button", { class: "btn primary", onclick: () => edit(null) }, "New employee"))));
    HL.setKeys([BACK]);
  },
};

HL.screens.payrun = {
  title: "Monthly Payroll",
  async render(sc, params) {
    await loadMasters();
    const month = (params && params.month) || todayIso().slice(0, 7);
    const run = await HL.get("/api/payroll/run", { month });
    const posted = run.status === "posted";
    const co = HL.S.status.company;
    const wd = h("input", { type: "text", inputmode: "numeric", value: run.working_days, style: "width:4rem", disabled: posted, "aria-label": "Working days" });
    const mo = h("input", { type: "month", value: month, "aria-label": "Month", onchange: e => { HL.cur.params = { month: e.target.value }; HL.refresh(); } });
    const earn = run.heads.filter(x => x.kind === "earning"), ded = run.heads.filter(x => x.kind === "deduction");
    const cols = ["Employee", "Days present", ...earn.map(x => x.name), "Gross", ...ded.map(x => x.name), "Net pay", ""];
    const [t, tb] = _tbl(cols);
    const state = run.slips.map(s => ({ employee_id: s.employee_id, name: s.name, days_present: s.days_present, lines: Object.assign({}, s.lines), overrides: {}, gross_paise: s.gross_paise, deduct_paise: s.deduct_paise, net_paise: s.net_paise }));
    const cells = [];
    const draw = () => {
      tb.replaceChildren(); cells.length = 0;
      state.forEach((s, ix) => {
        const dp = h("input", { type: "text", inputmode: "decimal", value: s.days_present, style: "width:4rem", disabled: posted, "aria-label": "Days present " + s.name, onchange: async e => { s.days_present = e.target.value; await recalc(); } });
        const edCell = x => { const i = h("input", { type: "text", inputmode: "decimal", class: "amt", value: _mf(s.lines[x.id] || 0), disabled: posted, style: "width:6.5rem", "aria-label": x.name + " " + s.name, onchange: async e => { s.overrides[x.id] = _paise(e.target.value); await recalc(); } }); return h("td", { class: "r" }, i); };
        tb.append(h("tr", {}, h("td", {}, s.name), h("td", {}, dp), ...earn.map(edCell), h("td", { class: "r" }, inr(s.gross_paise)), ...ded.map(edCell), h("td", { class: "r" }, h("b", {}, inr(s.net_paise))),
          h("td", {}, h("button", { class: "btn", type: "button", onclick: () => printSlip(s) }, "Payslip"))));
      });
      const tot = k => state.reduce((a, s) => a + s[k], 0);
      tb.append(h("tr", { class: "total" }, h("td", {}, "Total"), h("td", {}), ...earn.map(x => h("td", { class: "r" }, inr(state.reduce((a, s) => a + (s.lines[x.id] || 0), 0)))), h("td", { class: "r" }, inr(tot("gross_paise"))), ...ded.map(x => h("td", { class: "r" }, inr(state.reduce((a, s) => a + (s.lines[x.id] || 0), 0)))), h("td", { class: "r" }, inr(tot("net_paise"))), h("td", {})));
    };
    const payload = () => ({ month, working_days: parseInt(wd.value, 10) || 0, slips: state.map(s => ({ employee_id: s.employee_id, days_present: s.days_present, overrides: s.overrides })) });
    async function recalc() {
      try {
        const r = await HL.post("/api/payroll/run/calc", payload());
        r.slips.forEach(c => { const s = state.find(x => x.employee_id === c.employee_id); Object.assign(s, { lines: c.lines, gross_paise: c.gross_paise, deduct_paise: c.deduct_paise, net_paise: c.net_paise }); });
        draw();
      } catch (e) { fail(e); }
    }
    wd.onchange = recalc;
    function printSlip(s) {
      const rows = hs => hs.map(x => `<tr><td>${esc(x.name)}</td><td class="r">${inr(s.lines[x.id] || 0)}</td></tr>`).join("");
      HL.printHtml(`<!doctype html><meta charset="utf-8"><title>Payslip ${esc(s.name)}</title><style>@page{size:A4;margin:14mm}body{font:13px Arial,sans-serif;color:#111}h1{font-size:20px;margin:0}table{width:100%;border-collapse:collapse;margin-top:8px}th,td{border:1px solid #888;padding:5px 7px;text-align:left}th{background:#eee}.r{text-align:right}.sign{display:flex;justify-content:space-between;margin-top:60px}</style>
      <h1>${esc(co.name)}</h1><h3 style="margin:2px 0 10px">PAYSLIP for ${esc(month)}</h3><div>Employee: <b>${esc(s.name)}</b></div><div>Days present: <b>${s.days_present}</b> of ${esc(wd.value)}</div>
      <table><thead><tr><th>Earnings</th><th class="r">Amount</th></tr></thead><tbody>${rows(earn)}<tr><td><b>Gross</b></td><td class="r"><b>${inr(s.gross_paise)}</b></td></tr></tbody></table>
      <table><thead><tr><th>Deductions</th><th class="r">Amount</th></tr></thead><tbody>${rows(ded)}<tr><td><b>Total deductions</b></td><td class="r"><b>${inr(s.deduct_paise)}</b></td></tr></tbody></table>
      <p style="font-size:16px"><b>Net pay: ${inr(s.net_paise)}</b></p><p>${esc(HL.amountWords(s.net_paise))}</p><div class="sign"><div>Employee</div><div>Authorised signatory</div></div>`);
    }
    draw();
    const save = async () => { try { await HL.post("/api/payroll/run/save", payload()); say("Payroll saved.", "ok"); HL.refresh(); } catch (e) { fail(e); } };
    const post = async () => { try { if (!await confirmBox("Post to the books", "This makes a Journal voucher dated the last day of the month: Dr Salaries & Wages, Cr deduction ledgers and Salary Payable. Pay the salary afterwards with a Payment voucher (Dr Salary Payable). Continue?", "Post")) return; await HL.post("/api/payroll/run/save", payload()); const r = await HL.post("/api/payroll/run/post", { month }); say("Posted as Journal voucher.", "ok"); HL.refresh(); } catch (e) { fail(e); } };
    const reopen = async () => { try { await HL.post("/api/payroll/run/reopen", { month }); HL.refresh(); } catch (e) { fail(e); } };
    sc.replaceChildren(_page("Monthly Payroll", posted ? "Posted to the books" : run.status === "draft" ? "Saved, not yet posted" : "New month (not saved)",
      h("div", { class: "row", style: "gap:.8rem;align-items:center;flex-wrap:wrap;margin-bottom:.6rem" }, h("label", {}, "Month ", mo), h("label", {}, "Working days ", wd)),
      state.length ? h("div", { class: "scroll" }, t) : h("div", { class: "banner warn" }, "No employees with a salary structure. Add them in Payroll > Employees."),
      h("div", { class: "row", style: "gap:.5rem;margin-top:.8rem;flex-wrap:wrap" }, posted ? h("button", { class: "btn", onclick: reopen }, "Reopen (after cancelling its voucher)") : [h("button", { class: "btn", onclick: save, disabled: !state.length }, "Save"), h("button", { class: "btn primary", onclick: post, disabled: !state.length }, "Save and post to books")]),
      h("p", { class: "hint" }, "Earnings are cut in proportion to days present. You can type a different amount in any box (for example the month's TDS on salary or an advance recovery). Statutory PF/ESI/professional-tax rules and salary TDS slabs are not applied automatically; please have your accountant set the amounts.")));
    HL.setKeys([BACK]);
  },
};

HL.screens.payregister = {
  title: "Payroll Register",
  async render(sc) {
    await loadMasters(); const P = getPeriod(); const r = await HL.get("/api/payroll/register", { from: P.from, to: P.to });
    const [t, tb] = _tbl(["Month", "Employees", "Gross pay", "Deductions", "Net pay", "Status"]);
    r.rows.forEach(x => tb.append(h("tr", {}, h("td", {}, x.month), h("td", { class: "r" }, x.employees), h("td", { class: "r" }, inr(x.gross)), h("td", { class: "r" }, inr(x.ded)), h("td", { class: "r" }, inr(x.net)), h("td", {}, x.status === "posted" ? "Posted" : "Saved"))));
    if (!r.rows.length) tb.append(h("tr", {}, h("td", { colspan: 6, class: "empty" }, "No payroll in this period.")));
    sc.replaceChildren(_page("Payroll Register", periodText(), periodBar(() => HL.refresh()), t, h("div", { class: "banner ok" }, "Total gross " + inr(r.gross) + " · Total net " + inr(r.net))));
    HL.setKeys([BACK]);
  },
};
