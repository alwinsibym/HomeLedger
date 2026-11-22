/* TDS: setup, PAN, Add TDS on a voucher, statement, deposits */
const _rs = p => inr(p);

HL.panDialog = async L => {
  const s = await HL.get("/api/tds/setup"); const cur = s.pan[L.id] || "";
  const pan = h("input", { type: "text", value: cur, maxlength: "10", style: "text-transform:uppercase", "aria-label": "PAN" });
  modal({ title: "PAN: " + L.name, body: h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f" }, "PAN of this party (needed for TDS at the normal rate)", pan),
    h("p", { class: "hint" }, "Without a PAN, TDS is deducted at the higher rate (20% or twice the normal rate).")),
    buttons: [{ label: "Cancel", onclick: x => x.close() }, { label: "Accept", cls: "primary", onclick: async x => { try { await HL.post("/api/tds/pan/save", { ledger_id: L.id, pan: pan.value }); x.close(); say("PAN saved.", "ok"); } catch (e) { fail(e); } } }] });
};

HL.tdsDialog = async ctx => {
  const { rows, S, recalc, addRow } = ctx;
  const setup = await HL.get("/api/tds/setup"); await loadMasters();
  const tl = String(setup.ledger_id);
  const isTds = r => String(r.led.value) === tl;
  const num = r => { const x = String(r.amt.value || "").replace(/[,\s]/g, ""); return /^\d+(\.\d{1,2})?$/.test(x) ? Math.round(parseFloat(x) * 100) : 0; };
  const party = rows.find(r => r.led.value && HL.isParty(r.led.value) && !isTds(r));
  if (!party) { say("Add the party's line first (the person you are paying), then press Add TDS.", "err"); return; }
  const undo = () => {                      // take back an earlier TDS deduction from this voucher
    const old = S.tds; if (!old) return;
    rows.filter(isTds).forEach(r => { rows.splice(rows.indexOf(r), 1); r.tr.remove(); });
    const target = party.side && party.side.value === "Dr" ? rows.find(r => r !== party && !isTds(r) && r.side && r.side.value === "Cr") : party;
    if (target) target.amt.value = ((num(target) + old.tax_paise) / 100).toFixed(2);
    S.tds = null; recalc(); S.dirty = true;
  };
  const nat = h("select", { "aria-label": "Nature of payment" }, setup.natures.filter(n => n.is_active).map(n => h("option", { value: n.id }, `${n.name} (${n.section}, ${n.rate_bp / 100}%)`)));
  if (S.tds) nat.value = String(S.tds.nature_id);
  const base = h("input", { type: "text", inputmode: "decimal", class: "amt", value: ((S.tds ? S.tds.base_paise : num(party) + 0) / 100).toFixed(2), "aria-label": "Amount" });
  const rate = h("input", { type: "text", inputmode: "decimal", style: "width:6rem", placeholder: "auto", "aria-label": "Rate override" });
  const out = h("div", { class: "banner", style: "margin-top:.6rem" }, "Press Calculate.");
  let last = null;
  const calc = async () => {
    try {
      last = await HL.post("/api/tds/compute", { nature_id: nat.value, party: party.led.value, base: base.value, date: S.date, voucher_id: ctx.voucherId, rate: rate.value || null });
      out.className = "banner " + (last.liable ? "ok" : "warn");
      out.replaceChildren(h("b", {}, last.liable ? `TDS ${_rs(last.tax_paise)} at ${last.rate_bp / 100}% on ${_rs(last.taxable_base_paise)}` : "No TDS on this payment"), ...last.notes.map(n => h("div", {}, n)));
    } catch (e) { last = null; fail(e); }
  };
  const apply = async m => {
    if (!last) await calc(); if (!last) return;
    if (!last.liable) { m.close(); return; }
    undo();
    const tax = last.tax_paise;
    const target = party.side && party.side.value === "Dr" ? rows.find(r => r !== party && r.side && r.side.value === "Cr" && num(r) > tax) : party;
    if (!target) { say("Could not find the line to reduce. Reduce the cash / bank line yourself by the TDS amount.", "err"); }
    else target.amt.value = ((num(target) - tax) / 100).toFixed(2);
    addRow({ ledger_id: setup.ledger_id, side: "Cr", amount_paise: tax });
    S.tds = { nature_id: +nat.value, party: +party.led.value, base_paise: Math.round(parseFloat(base.value.replace(/,/g, "")) * 100), taxed_base_paise: last.taxable_base_paise, rate_bp: last.rate_bp, tax_paise: tax };
    recalc(); S.dirty = true; m.close(); say(`TDS ${_rs(tax)} deducted. Party line reduced and 'TDS Payable' line added.`, "ok");
  };
  modal({ title: "Add TDS: " + party.led.input.value, wide: true, body: h("div", {},
    h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f" }, "Nature of payment", nat), h("label", { class: "f" }, "Payment amount (before TDS)", base),
      h("label", { class: "f" }, "Rate % (leave empty to use the standard rate; type one only for a lower-deduction certificate)", rate)), out,
    h("p", { class: "hint" }, "TDS = tax deducted from the payment and paid to the government later (see Reports > TDS Deposits). Rates and limits come from Masters > TDS Setup; please confirm them with your accountant.")),
    buttons: [S.tds ? { label: "Remove TDS", cls: "danger", onclick: m => { undo(); m.close(); } } : null, { label: "Cancel", onclick: m => m.close() }, { label: "Calculate", onclick: calc }, { label: "Apply", cls: "primary", onclick: apply }].filter(Boolean) });
};

HL.screens.tdssetup = {
  title: "TDS Setup",
  async render(sc) {
    await loadMasters(); const s = await HL.get("/api/tds/setup");
    const [t, tb] = _tbl(["Nature of payment", "Section", "Code", "Rate", "Single-payment limit", "Yearly limit", "In use"]);
    const edit = n => {
      const f = (v, a) => h("input", Object.assign({ type: "text", value: v == null ? "" : v }, a || {}));
      const nm = f(n && n.name, { "aria-label": "Name" }), se = f(n && n.section, { "aria-label": "Section" }), co = f(n && n.code, { "aria-label": "Code" }),
        ra = f(n ? n.rate_bp / 100 : "", { "aria-label": "Rate" }), si = f(n ? n.single_paise / 100 : "0", { "aria-label": "Single limit" }), an = f(n ? n.annual_paise / 100 : "0", { "aria-label": "Yearly limit" });
      const act = h("input", { type: "checkbox", checked: n ? !!n.is_active : true });
      modal({ title: n ? "Nature of payment" : "New nature of payment", body: h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f" }, "Name", nm), h("label", { class: "f" }, "Section", se), h("label", { class: "f" }, "Payment code", co), h("label", { class: "f" }, "Rate %", ra),
        h("label", { class: "f" }, "Single-payment limit (₹; tax only if one payment is above this, 0 = none)", si), h("label", { class: "f" }, "Yearly limit (₹; tax once the year's total to a party crosses this, 0 = none)", an),
        h("label", { class: "f", style: "flex-direction:row;gap:.4rem;align-items:center" }, act, "In use")),
        buttons: [{ label: "Cancel", onclick: m => m.close() }, { label: "Accept", cls: "primary", onclick: async m => { try { await HL.post("/api/tds/nature/save", { id: n && n.id, name: nm.value, section: se.value, code: co.value, rate: ra.value, single: si.value, annual: an.value, is_active: act.checked }); m.close(); HL.refresh(); } catch (e) { fail(e); } } }] });
    };
    s.natures.forEach(n => { const tr = h("tr", { class: "row", tabindex: "0", onclick: () => edit(n) }, h("td", {}, n.name), h("td", {}, n.section), h("td", {}, n.code), h("td", { class: "r" }, n.rate_bp / 100 + "%"), h("td", { class: "r" }, n.single_paise ? inr(n.single_paise) : "-"), h("td", { class: "r" }, n.annual_paise ? inr(n.annual_paise) : "-"), h("td", {}, n.is_active ? "Yes" : "No")); rowKeys(tr); tb.append(tr); });
    sc.replaceChildren(_page("TDS Setup", "Natures of payment: click one to change it", t, h("div", { style: "margin-top:.6rem" }, h("button", { class: "btn", onclick: () => edit(null) }, "New nature of payment")),
      h("div", { class: "banner warn", style: "margin-top:.8rem;max-width:46rem" }, "These starting rates and limits follow published FY 2026-27 charts (section 393 of the Income-tax Act, 2025) and may be out of date or not fit your case. Rent limits are per payment (the rule is per month). Please confirm every line with your accountant. Not covered: salary, TCS, payments to non-residents, purchase of goods, filing the return (Form 26Q), interest on late payment.")));
    HL.setKeys([BACK]);
  },
};

HL.screens.tdsstatement = {
  title: "TDS Statement",
  async render(sc) {
    await loadMasters(); const P = getPeriod(); const r = await HL.get("/api/tds/statement", { from: P.from, to: P.to });
    const [t, tb] = _tbl(["Date", "Voucher", "Party", "PAN", "Section", "Payment", "Taxed on", "Rate", "TDS"]);
    r.rows.forEach(x => tb.append(h("tr", {}, h("td", {}, showDate(x.vdate)), h("td", {}, x.vtype + " " + x.number), h("td", {}, x.party), h("td", {}, x.pan || "missing"), h("td", {}, x.section), h("td", { class: "r" }, inr(x.base_paise)), h("td", { class: "r" }, inr(x.taxed_base_paise)), h("td", { class: "r" }, x.rate_bp / 100 + "%"), h("td", { class: "r" }, inr(x.tax_paise)))));
    if (!r.rows.length) tb.append(h("tr", {}, h("td", { colspan: 9, class: "empty" }, "No TDS deducted in this period.")));
    const [t2, tb2] = _tbl(["Nature of payment", "Section", "Payments", "Paid amount", "TDS"]);
    r.by_nature.forEach(x => tb2.append(h("tr", {}, h("td", {}, x.nature), h("td", {}, x.section), h("td", { class: "r" }, x.count), h("td", { class: "r" }, inr(x.base)), h("td", { class: "r" }, inr(x.tax)))));
    sc.replaceChildren(_page("TDS Statement", periodText(), periodBar(() => HL.refresh()), t2, h("div", { class: "banner ok" }, "Total TDS deducted: " + inr(r.total_tax)),
      r.missing_pan.length ? h("div", { class: "banner warn" }, "PAN missing for: " + r.missing_pan.join(", ") + ". Open the ledger and use 'PAN (TDS)'.") : "", h("div", { class: "scroll", style: "margin-top:.6rem" }, t),
      h("p", { class: "hint" }, "This is the data a Form 26Q return needs. HomeLedger does not file returns.")));
    HL.setKeys([BACK]);
  },
};

HL.screens.tdsdeposits = {
  title: "TDS Deposits",
  async render(sc) {
    await loadMasters(); const r = await HL.get("/api/tds/deposits");
    const mname = m => new Date(m + "-01T00:00:00").toLocaleString("en-IN", { month: "short", year: "numeric" });
    const [t, tb] = _tbl(["Month deducted", "Deducted", "Deposited", "Balance to deposit", "Due date", "Status"]);
    r.months.forEach(x => tb.append(h("tr", { class: x.status === "Overdue" ? "bad" : "" }, h("td", {}, mname(x.month)), h("td", { class: "r" }, inr(x.deducted_paise)), h("td", { class: "r" }, inr(x.deposited_paise)), h("td", { class: "r" }, inr(x.balance_paise)), h("td", {}, showDate(x.due)), h("td", {}, x.status))));
    if (!r.months.length) tb.append(h("tr", {}, h("td", { colspan: 6, class: "empty" }, "Nothing deducted or deposited yet.")));
    const [t2, tb2] = _tbl(["Deposited on", "For month", "BSR code", "Challan no.", "Amount", "Interest", ""]);
    r.challans.forEach(c => tb2.append(h("tr", {}, h("td", {}, showDate(c.paid_on)), h("td", {}, mname(c.for_month)), h("td", {}, c.bsr), h("td", {}, c.serial), h("td", { class: "r" }, inr(c.amount_paise)), h("td", { class: "r" }, c.interest_paise ? inr(c.interest_paise) : ""),
      h("td", {}, h("button", { class: "btn", type: "button", onclick: async () => { if (await confirmBox("Delete this challan record?", "", "Delete", true)) { try { await HL.post("/api/tds/challan/delete", { id: c.id }); HL.refresh(); } catch (e) { fail(e); } } } }, "Delete")))));
    const add = () => {
      const d = h("input", { type: "text", value: showDate(todayIso()), "aria-label": "Date" }), mo = h("input", { type: "month", value: todayIso().slice(0, 7), "aria-label": "Month" }), am = h("input", { type: "text", inputmode: "decimal", class: "amt", "aria-label": "Amount" }),
        bsr = h("input", { type: "text", "aria-label": "BSR" }), se = h("input", { type: "text", "aria-label": "Challan" }), it = h("input", { type: "text", inputmode: "decimal", "aria-label": "Interest" });
      modal({ title: "Record a TDS deposit", body: h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f" }, "Date deposited", d), h("label", { class: "f" }, "For tax deducted in (month)", mo), h("label", { class: "f" }, "Amount (₹)", am), h("label", { class: "f" }, "BSR code", bsr), h("label", { class: "f" }, "Challan serial no.", se), h("label", { class: "f" }, "Interest paid, if any (₹)", it),
        h("p", { class: "hint" }, "Also enter the payment itself as a Payment voucher (Dr TDS Payable, Cr Bank) so your books show it. This list is only the challan record.")),
        buttons: [{ label: "Cancel", onclick: m => m.close() }, { label: "Accept", cls: "primary", onclick: async m => { try { const iso = parseDateInput(d.value, todayIso()); if (!iso) { say("Please type the date like 07-12-2026.", "err"); return; } await HL.post("/api/tds/challan/save", { paid_on: iso, for_month: mo.value, amount: am.value, bsr: bsr.value, serial: se.value, interest: it.value }); m.close(); HL.refresh(); } catch (e) { fail(e); } } }] });
    };
    sc.replaceChildren(_page("TDS Deposits", "Due: 7th of the next month (30 April for March)", t, h("div", { class: "banner " + (r.balance_total > 0 ? "warn" : "ok") }, r.balance_total > 0 ? "Still to deposit: " + inr(r.balance_total) : "All tax deducted has been deposited."),
      h("h3", { style: "margin-top:1rem" }, "Challans"), t2, h("div", { style: "margin-top:.6rem" }, h("button", { class: "btn primary", onclick: add }, "Record a deposit"))));
    HL.setKeys([BACK]);
  },
};
