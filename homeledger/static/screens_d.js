/* Post-dated vouchers, cheque register and printing, voucher classes, F12 Configure */

HL.printHtml = html => {
  const f = document.createElement("iframe");
  f.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
  document.body.append(f);
  const d = f.contentWindow.document;
  d.open(); d.write(html); d.close();
  setTimeout(() => { try { f.contentWindow.focus(); f.contentWindow.print(); } catch (e) { } setTimeout(() => f.remove(), 4000); }, 300);
};

HL.words = n => {   // Indian system: crore, lakh, thousand
  n = Math.round(n);
  const ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"];
  const tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"];
  const two = x => x < 20 ? ones[x] : tens[Math.floor(x / 10)] + (x % 10 ? " " + ones[x % 10] : "");
  const three = x => (x >= 100 ? ones[Math.floor(x / 100)] + " Hundred" + (x % 100 ? " " : "") : "") + (x % 100 ? two(x % 100) : "");
  if (n === 0) return "Zero";
  const parts = []; let r = n;
  const cr = Math.floor(r / 1e7); r %= 1e7; const lk = Math.floor(r / 1e5); r %= 1e5; const th = Math.floor(r / 1e3); r %= 1e3;
  if (cr) parts.push(three(cr) + " Crore"); if (lk) parts.push(two(lk) + " Lakh"); if (th) parts.push(two(th) + " Thousand"); if (r) parts.push(three(r));
  return parts.join(" ");
};
HL.amountWords = paise => {
  const rupees = Math.floor(paise / 100), ps = paise % 100;
  return "Rupees " + HL.words(rupees) + (ps ? " and " + HL.words(ps) + " Paise" : "") + " Only";
};

HL.printVoucher = async id => {
  const v = await HL.get("/api/voucher", { id });
  const co = HL.S.status.company, q = n => (n / 100).toLocaleString("en-IN", { minimumFractionDigits: 2 });
  const inv = ["Sales", "Purchase", "Credit Note", "Debit Note"].includes(v.vtype);
  const title = inv ? ({ Sales: "Sales Invoice", Purchase: "Purchase Voucher", "Credit Note": "Credit Note", "Debit Note": "Debit Note" })[v.vtype] : v.vtype + " Voucher";
  const items = (v.items || []).filter(x => x.kind === "normal");
  const itemRows = items.map((x, i) => `<tr><td>${i + 1}</td><td>${esc(x.item)}</td><td class="r">${(x.qty_milli / 1000).toLocaleString("en-IN")} ${esc(x.unit || "")}</td><td class="r">${q(x.rate_paise)}</td><td class="r">${q(x.amount_paise)}</td></tr>`).join("");
  const lineRows = v.lines.map(l => `<tr><td>${l.side}</td><td>${esc(l.ledger_name)}${l.cc_name ? " <small>(" + esc(l.cc_name) + ")</small>" : ""}</td><td class="r">${l.side === "Dr" ? q(l.amount_paise) : ""}</td><td class="r">${l.side === "Cr" ? q(l.amount_paise) : ""}</td></tr>`).join("");
  const m = v.meta || {};
  let gcfg = null; try { gcfg = await HL.get("/api/gst/config"); } catch (e) { }
  const gstTable = v.gst && v.gst.rows.length ? `<table><thead><tr><th>HSN / SAC</th><th class="r">Rate</th><th class="r">Taxable value</th><th class="r">CGST</th><th class="r">SGST</th><th class="r">IGST</th></tr></thead><tbody>${v.gst.rows.map(x => `<tr><td>${esc(x.hsn)}</td><td class="r">${x.rate_bp / 100}%</td><td class="r">${q(x.taxable_paise)}</td><td class="r">${q(x.cgst_paise)}</td><td class="r">${q(x.sgst_paise)}</td><td class="r">${q(x.igst_paise)}</td></tr>`).join("")}</tbody></table>` : "";
  const gstLine = gcfg && gcfg.on && gcfg.gstin ? `<div>GSTIN: ${esc(gcfg.gstin)}</div>` : "";
  const html = `<!doctype html><meta charset="utf-8"><title>${esc(title)} ${v.number}</title><style>
    @page { size: A4; margin: 14mm } body { font: 13px Arial, sans-serif; color: #111 } h1 { font-size: 20px; margin: 0 } h2 { font-size: 15px; margin: 2px 0 10px; letter-spacing: 1px }
    table { width: 100%; border-collapse: collapse; margin-top: 8px } th, td { border: 1px solid #888; padding: 5px 7px; text-align: left } th { background: #eee } .r { text-align: right }
    .top { display: flex; justify-content: space-between; margin: 8px 0 } .tot td { font-weight: bold; background: #f5f5f5 } .sign { display: flex; justify-content: space-between; margin-top: 60px } small { color: #555 }
    .stamp { color: #b00; border: 2px solid #b00; display: inline-block; padding: 2px 8px; font-weight: bold; transform: rotate(-6deg) }
  </style><h1>${esc(co.name)}</h1>${gstLine}<h2>${esc(title.toUpperCase())}</h2>${v.status === "cancelled" ? '<div class="stamp">CANCELLED</div>' : ""}
  <div class="top"><div>No.: <b>${v.number}</b> (${esc(v.fy)})${v.ref ? "<br>Ref: " + esc(v.ref) : ""}</div><div>Date: <b>${showDate(v.date)}</b></div></div>
  ${m.inst_no ? `<div>Cheque / instrument: ${esc(m.inst_no)} ${m.inst_date ? "dated " + showDate(m.inst_date) : ""} ${esc(m.bank_name || "")}</div>` : ""}
  ${items.length ? `<table><thead><tr><th>#</th><th>Description</th><th class="r">Quantity</th><th class="r">Rate</th><th class="r">Amount</th></tr></thead><tbody>${itemRows}</tbody></table>` : ""}
  <table><thead><tr><th style="width:3rem">Dr/Cr</th><th>Particulars</th><th class="r">Debit</th><th class="r">Credit</th></tr></thead><tbody>${lineRows}
    <tr class="tot"><td></td><td>Total</td><td class="r">${q(v.total_paise)}</td><td class="r">${q(v.total_paise)}</td></tr></tbody></table>
  ${gstTable}
  <p><b>Amount in words:</b> ${esc(HL.amountWords(v.total_paise))}</p>${v.narration ? "<p><b>Narration:</b> " + esc(v.narration) + "</p>" : ""}
  <div class="sign"><div>Prepared by</div><div>Authorised signatory</div></div>`;
  HL.printHtml(html);
};

HL.printCheque = async row => {
  const dt = (row.inst_date || row.vdate).split("-");           // yyyy-mm-dd -> dd mm yyyy boxes
  const boxes = (dt[2] + dt[1] + dt[0]).split("").map(x => `<span class="bx">${x}</span>`).join("");
  const html = `<!doctype html><meta charset="utf-8"><title>Cheque</title><style>
    @page { size: 8.5in 3.7in; margin: 0 } body { margin: 0; font: 14px Arial, sans-serif }
    .chq { position: relative; width: 8.5in; height: 3.7in } .a { position: absolute; white-space: nowrap }
    .bx { display: inline-block; width: 18px; text-align: center; letter-spacing: 0 }
  </style><div class="chq">
    <div class="a" style="left:6.1in;top:.35in;letter-spacing:6px">${boxes}</div>
    <div class="a" style="left:.9in;top:.3in;font-size:11px">A/c Payee</div>
    <div class="a" style="left:1.1in;top:1.0in;font-size:16px">${esc(row.party || "")}</div>
    <div class="a" style="left:1.1in;top:1.45in;font-size:14px;max-width:5.2in;white-space:normal">${esc(HL.amountWords(row.amount_paise))}</div>
    <div class="a" style="left:6.3in;top:1.4in;font-size:17px">${esc((row.amount_paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2 }))}/-</div>
  </div>`;
  HL.printHtml(html);
};

HL.screens.postdated = {
  title: "Post-dated Vouchers",
  async render(sc) {
    await loadMasters();
    const rows = await HL.get("/api/postdated");
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Due date", "Type", "No.", "Cheque", "Bank", "Narration", "Amount", ""].map((x, i) => h("th", { class: i === 6 ? "r" : "" }, x)))));
    const tb = h("tbody", {}); t.append(tb);
    const today = todayIso();
    rows.forEach(x => {
      const due = x.vdate <= today;
      const tr = h("tr", { class: "row", tabindex: "0", onclick: () => HL.go("voucher", { id: x.id }) }, h("td", {}, showDate(x.vdate) + (due ? "  (due)" : "")), h("td", {}, x.vtype), h("td", {}, x.number), h("td", {}, x.inst_no), h("td", {}, x.bank_name), h("td", {}, x.narration || ""), h("td", { class: "r" }, inr(x.amount_paise)),
        h("td", {}, h("button", { class: "btn" + (due ? " primary" : ""), type: "button", onclick: async e => { e.stopPropagation(); try { await HL.post("/api/voucher/activate", { id: x.id }); say("Brought into the books.", "ok"); HL.refresh(); } catch (er) { fail(er); } } }, "Activate")));
      rowKeys(tr); tb.append(tr);
    });
    if (!rows.length) tb.append(h("tr", {}, h("td", { colspan: 8, class: "empty" }, "No post-dated vouchers. Tick Post-dated on a Payment or Receipt that has a future cheque date.")));
    sc.replaceChildren(h("div", {}, h("h1", { class: "title" }, "Post-dated Vouchers"), h("p", { class: "sub" }, "Kept out of the books and reports until you press Activate, usually when the cheque is honoured"), t));
    HL.setKeys([BACK]);
    const f = $("tbody tr.row", sc); f && f.focus();
  },
};

HL.screens.chequereg = {
  title: "Cheque Register",
  async render(sc) {
    await loadMasters();
    const P = getPeriod();
    const rows = await HL.get("/api/chequereg", { from: P.from, to: P.to });
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Cheque date", "Cheque no.", "Type", "Party", "Bank", "Amount", "Status", ""].map((x, i) => h("th", { class: i === 5 ? "r" : "" }, x)))));
    const tb = h("tbody", {}); t.append(tb);
    rows.forEach(x => {
      const tr = h("tr", { class: "row", tabindex: "0", onclick: () => HL.go("voucher", { id: x.id }) }, h("td", {}, showDate(x.inst_date || x.vdate)), h("td", {}, x.inst_no), h("td", {}, x.vtype), h("td", {}, x.party || ""), h("td", {}, x.bank_name || x.bank_ledger || ""), h("td", { class: "r" }, inr(x.amount_paise)),
        h("td", {}, x.post_dated ? "Post-dated" : x.status === "optional" ? "Optional" : "In books"),
        h("td", {}, x.vtype === "Payment" ? h("button", { class: "btn", type: "button", onclick: e => { e.stopPropagation(); HL.printCheque(x); } }, "Print cheque") : ""));
      rowKeys(tr); tb.append(tr);
    });
    if (!rows.length) tb.append(h("tr", {}, h("td", { colspan: 8, class: "empty" }, "No cheques in this period. Type the Cheque no. on a Payment or Receipt to list it here.")));
    sc.replaceChildren(h("div", {}, h("h1", { class: "title" }, "Cheque Register"), h("p", { class: "sub" }, periodText()), periodBar(() => HL.refresh()), t,
      h("p", { class: "hint" }, "Print cheque: put your cheque leaf in the printer. The layout is a standard 8.5 x 3.7 inch cheque; do a test on plain paper first and tell me if the positions need adjusting for your bank.")));
    HL.setKeys([BACK]);
    const f = $("tbody tr.row", sc); f && f.focus();
  },
};

HL.screens.classes = {
  title: "Voucher Classes",
  async render(sc, params) {
    await loadMasters();
    const list = await HL.get("/api/classes");
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Class", "Voucher type", "Pre-filled accounts"].map(x => h("th", {}, x)))));
    const tb = h("tbody", {}); t.append(tb);
    const nameOf = id => (M().ledgers.find(l => l.id === id) || {}).name || "?";
    const edit = c => {
      const nm = h("input", { type: "text", value: c ? c.name : "", maxlength: "40", "aria-label": "Class name" });
      const vt = h("select", { "aria-label": "Voucher type" }, VTYPES_UI().map(x => h("option", { value: x }, x))); vt.value = c ? c.vtype : "Receipt";
      const l1 = picker({ options: () => ledgerOptions(), value: c && c.lines[0] ? c.lines[0].ledger_id : null, placeholder: "First account (optional)" });
      const s1 = h("select", {}, h("option", { value: "Dr" }, HL.cfg.side("Dr")), h("option", { value: "Cr" }, HL.cfg.side("Cr"))); s1.value = c && c.lines[0] ? c.lines[0].side : "Dr";
      const l2 = picker({ options: () => ledgerOptions(), value: c && c.lines[1] ? c.lines[1].ledger_id : null, placeholder: "Second account (optional)" });
      const s2 = h("select", {}, h("option", { value: "Dr" }, HL.cfg.side("Dr")), h("option", { value: "Cr" }, HL.cfg.side("Cr"))); s2.value = c && c.lines[1] ? c.lines[1].side : "Cr";
      const body = h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f" }, "Class name (e.g. Cash Sales)", nm), h("label", { class: "f" }, "Voucher type", vt),
        h("div", { class: "row" }, s1, l1.el), h("div", { class: "row" }, s2, l2.el));
      const m = modal({ title: c ? "Voucher Class Alteration" : "Voucher Class Creation", body, buttons: [c ? { label: "Delete", cls: "danger", onclick: async m2 => { if (await confirmBox("Delete this class?", "Vouchers already saved with it are not changed.", "Delete", true)) { try { await HL.post("/api/class/delete", { id: c.id }); m2.close(); HL.refresh(); } catch (e) { fail(e); } } } } : null, { label: "Cancel", onclick: m => m.close() }, { label: "Accept", cls: "primary", onclick: save }].filter(Boolean) });
      async function save() { try { const lines = []; if (l1.value) lines.push({ ledger_id: l1.value, side: s1.value }); if (l2.value) lines.push({ ledger_id: l2.value, side: s2.value }); await HL.post("/api/class/save", { id: c && c.id, name: nm.value, vtype: vt.value, lines }); m.close(); HL.refresh(); } catch (e) { fail(e); } }
    };
    list.forEach(c => { const tr = h("tr", { class: "row", tabindex: "0", onclick: () => edit(c) }, h("td", {}, c.name), h("td", {}, c.vtype), h("td", {}, c.lines.map(l => HL.cfg.side(l.side) + " " + nameOf(l.ledger_id)).join(",  "))); rowKeys(tr); tb.append(tr); });
    if (!list.length) tb.append(h("tr", {}, h("td", { colspan: 3, class: "empty" }, "No classes yet. A class pre-fills a voucher, for example 'Cash Sales' that starts with Cash and Sales Accounts filled in. Press Alt+C to create one.")));
    sc.replaceChildren(h("div", {}, h("h1", { class: "title" }, "Voucher Classes"), t));
    HL.setKeys([BACK, { k: "Alt+C", label: "Create class", fn: () => edit(null) }]);
    const f = $("tbody tr.row", sc); f && f.focus();
  },
};
function VTYPES_UI() { return ["Payment", "Receipt", "Contra", "Journal", "Sales", "Purchase", "Credit Note", "Debit Note"]; }

/* F12: Configure */
HL.configure = () => {
  const c = HL.cfg.get();
  const entry = h("select", { "aria-label": "Entry style" }, h("option", { value: "auto" }, "Single entry for Payment and Receipt (one Cash/Bank line, then the particulars)"), h("option", { value: "double" }, "Double entry for all vouchers (every line shows Dr/Cr)"));
  entry.value = c.entry || "auto";
  const dr = h("select", { "aria-label": "Debit and credit words" }, h("option", { value: "" }, "Automatic (By/To in the Classic look, Dr/Cr in the Prime look)"), h("option", { value: "drcr" }, "Dr / Cr"), h("option", { value: "byto" }, "By / To"));
  dr.value = c.drcr || "";
  const body = h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f" }, "Voucher entry", entry), h("label", { class: "f" }, "Debit / credit words", dr),
    h("p", { class: "hint" }, "These choices are kept on this computer. They take effect the next time you open a voucher."));
  modal({ title: "Configuration (F12)", body, buttons: [{ label: "Cancel", onclick: m => m.close() }, { label: "Accept", cls: "primary", onclick: m => { HL.cfg.set({ entry: entry.value, drcr: dr.value }); m.close(); say("Saved.", "ok"); } }] });
};


/* Bill-wise references on a party line */
HL.isParty = id => {
  const M = HL.S.masters; if (!M) return false;
  const ledger = M.ledgers.find(l => l.id === id); if (!ledger) return false;
  const root = code => { const out = new Set(); const st = M.groups.filter(g => g.code === code).map(g => g.id); while (st.length) { const i = st.pop(); out.add(i); M.groups.filter(g => g.parent_id === i).forEach(g => st.push(g.id)); } return out; };
  return root("DEBTORS").has(ledger.group_id) || root("CREDITORS").has(ledger.group_id);
};

HL.billsDialog = async (r, voucherId, getSide) => {
  const id = r.led.value; if (!id) { say("Choose the party first.", "err"); return; }
  const open = await HL.get("/api/openbills", { ledger_id: id, exclude: voucherId || 0 });
  const rows = (r.bills.length ? r.bills : [{ ref: "", kind: "new", amount: r.amt.value || "", due: "" }]).map(b => Object.assign({}, b));
  const tb = h("tbody", {});
  const dl = h("datalist", { id: "dl-openbills" }, open.map(b => h("option", { value: b.ref }, inr(Math.abs(b.pending)))));
  const draw = () => {
    tb.replaceChildren();
    rows.forEach((b, i) => {
      const kind = h("select", { "aria-label": "Type" }, [["new", "New Ref"], ["against", "Against Ref"], ["advance", "Advance"]].map(([v, t]) => h("option", { value: v }, t))); kind.value = b.kind;
      const ref = h("input", { type: "text", list: "dl-openbills", value: b.ref, maxlength: "40", style: "width:9rem", "aria-label": "Reference" });
      const amt = h("input", { type: "text", inputmode: "decimal", value: b.amount, style: "width:7rem;text-align:right", "aria-label": "Amount" });
      const due = h("input", { type: "text", value: b.due ? showDate(b.due) : "", placeholder: "dd-mm-yyyy", style: "width:8rem", "aria-label": "Due date" });
      kind.onchange = () => { b.kind = kind.value; };
      ref.oninput = () => { b.ref = ref.value; const o = open.find(x => x.ref.toLowerCase() === ref.value.trim().toLowerCase()); if (o && b.kind === "against" && !amt.value) { amt.value = (Math.abs(o.pending) / 100).toFixed(2); b.amount = amt.value; } };
      amt.oninput = () => { b.amount = amt.value; };
      due.onchange = () => { b.due = due.value.trim() ? (parseDateInput(due.value, todayIso()) || "") : ""; };
      tb.append(h("tr", {}, h("td", {}, kind), h("td", {}, ref), h("td", {}, amt), h("td", {}, due), h("td", {}, h("button", { class: "btn", type: "button", onclick: () => { rows.splice(i, 1); if (!rows.length) rows.push({ ref: "", kind: "new", amount: "", due: "" }); draw(); } }, "×"))));
    });
  };
  draw();
  const body = h("div", {}, h("p", { class: "hint" }, "New Ref: a new bill or invoice. Against Ref: settles an open bill. Advance: money given or taken before a bill exists. Anything not matched to a bill stays 'on account'."), dl,
    h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Type", "Reference", "Amount (₹)", "Due date", ""].map(x => h("th", {}, x)))), tb),
    h("button", { class: "btn", type: "button", style: "margin-top:.5rem", onclick: () => { rows.push({ ref: "", kind: open.length ? "against" : "new", amount: "", due: "" }); draw(); } }, "+ Add a bill"));
  modal({ title: "Bill allocation", body, buttons: [{ label: "Cancel", onclick: m => m.close() }, { label: "Clear", onclick: m => { r.bills = []; r.showBb(); m.close(); } },
    { label: "Accept", cls: "primary", onclick: m => { r.bills = rows.filter(b => b.ref.trim() || b.amount).map(b => ({ ref: b.ref.trim(), kind: b.kind, amount: b.amount, due: b.due || null })); r.showBb(); m.close(); } }] });
};


/* ---- party statement (account statement to send to a customer / supplier) and payment reminder letter ---- */
HL.printStatement = async (ledgerId, from, to) => {
  const r = await HL.get("/api/ledger_statement", { ledger_id: ledgerId, from, to });
  const co = HL.S.status.company, q = n => (n / 100).toLocaleString("en-IN", { minimumFractionDigits: 2 });
  const bal = n => q(Math.abs(n)) + (n > 0 ? " Dr" : n < 0 ? " Cr" : "");
  const rows = r.rows.map(x => `<tr><td>${showDate(x.vdate)}</td><td>${esc(x.vtype)} ${esc(x.number || "")}${x.narration ? "<br><small>" + esc(x.narration) + "</small>" : ""}</td><td class="r">${x.debit_paise ? q(x.debit_paise) : ""}</td><td class="r">${x.credit_paise ? q(x.credit_paise) : ""}</td><td class="r">${bal(x.balance)}</td></tr>`).join("");
  const html = `<!doctype html><meta charset="utf-8"><title>Statement ${esc(r.name)}</title><style>
    @page { size: A4; margin: 14mm } body { font: 13px Arial, sans-serif; color: #111 } h1 { font-size: 20px; margin: 0 } h2 { font-size: 15px; margin: 2px 0 4px }
    table { width: 100%; border-collapse: collapse; margin-top: 10px } th, td { border: 1px solid #888; padding: 4px 7px; text-align: left } th { background: #eee } .r { text-align: right } .tot td { font-weight: bold; background: #f5f5f5 } small { color: #555 }
  </style><h1>${esc(co.name)}</h1><h2>Statement of Account: ${esc(r.name)}</h2><div>${showDate(from)} to ${showDate(to)}</div>
  <table><thead><tr><th>Date</th><th>Particulars</th><th class="r">Debit</th><th class="r">Credit</th><th class="r">Balance</th></tr></thead><tbody>
  <tr><td colspan="4"><b>Opening balance</b></td><td class="r">${bal(r.opening)}</td></tr>${rows}
  <tr class="tot"><td colspan="2">Totals</td><td class="r">${q(r.total_dr)}</td><td class="r">${q(r.total_cr)}</td><td class="r">${bal(r.closing)}</td></tr></tbody></table>
  <p>Closing balance: <b>${bal(r.closing)}</b></p><p>Please tell us if anything here does not match your records.</p>`;
  HL.printHtml(html);
};

HL.printReminder = async (kind, ledgerId) => {
  const o = await HL.get("/api/outstanding", { kind, to: todayIso() });
  const x = o.rows.find(r => r.ledger_id === ledgerId);
  if (!x) { say("Nothing is pending for this party.", "err"); return; }
  const co = HL.S.status.company, q = n => (n / 100).toLocaleString("en-IN", { minimumFractionDigits: 2 });
  const bills = (x.bills || []).filter(b => b.pending !== 0).map(b => `<tr><td>${esc(b.ref)}</td><td>${b.due ? showDate(b.due) : ""}</td><td class="r">${q(Math.abs(b.pending))}</td></tr>`).join("");
  const body = kind === "receivable"
    ? `<p>Our records show that an amount of <b>Rs. ${q(x.due)}</b> is still pending from you as on ${showDate(todayIso())}.</p><p>We request you to arrange the payment at the earliest. If you have already paid, please ignore this letter and let us know the details so that we can update our books.</p>`
    : `<p>This is to confirm the balance of <b>Rs. ${q(x.due)}</b> payable by us to you as on ${showDate(todayIso())}. Please let us know if your records differ.</p>`;
  const html = `<!doctype html><meta charset="utf-8"><title>Letter ${esc(x.name)}</title><style>
    @page { size: A4; margin: 20mm } body { font: 14px Arial, sans-serif; color: #111; line-height: 1.5 } h1 { font-size: 20px; margin: 0 0 24px } table { border-collapse: collapse; margin: 10px 0 } th, td { border: 1px solid #888; padding: 4px 10px } th { background: #eee } .r { text-align: right }
  </style><h1>${esc(co.name)}</h1><div>Date: ${showDate(todayIso())}</div><p>To,<br><b>${esc(x.name)}</b></p>
  <p><b>Subject: ${kind === "receivable" ? "Reminder for pending payment" : "Balance confirmation"}</b></p><p>Dear Sir / Madam,</p>${body}
  ${bills ? `<table><thead><tr><th>Bill</th><th>Due date</th><th class="r">Amount (Rs.)</th></tr></thead><tbody>${bills}</tbody></table>` : ""}
  <p>Thank you.</p><p style="margin-top:50px">For ${esc(co.name)}</p>`;
  HL.printHtml(html);
};
