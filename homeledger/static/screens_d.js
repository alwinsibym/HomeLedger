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
