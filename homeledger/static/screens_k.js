/* Bills and receipts, Bill Inbox, Quick Entry, Import from Excel/CSV, auto-categorise rules */

/* ---- reading a file in the browser: photos are shrunk so the database stays small ---- */
HL.readFile = file => new Promise((resolve, reject) => {
  const done = (b64, name) => resolve({ filename: name || file.name, data: b64 });
  const raw = () => { const r = new FileReader(); r.onload = () => done(String(r.result).split(",")[1]); r.onerror = () => reject(new Error("The file could not be read.")); r.readAsDataURL(file); };
  if (!/^image\/(jpeg|png|webp)$/.test(file.type)) return raw();
  const url = URL.createObjectURL(file), img = new Image();
  img.onload = () => {
    const k = Math.min(1, 1800 / Math.max(img.width, img.height)), c = document.createElement("canvas");
    c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
    c.getContext("2d").drawImage(img, 0, 0, c.width, c.height); URL.revokeObjectURL(url);
    const out = c.toDataURL("image/jpeg", 0.82).split(",")[1];
    done(out, file.name.replace(/\.[^.]+$/, "") + ".jpg");
  };
  img.onerror = () => { URL.revokeObjectURL(url); raw(); };
  img.src = url;
});

HL.uploadFiles = async (files, voucherId) => {
  let ok = 0, last = "";
  for (const f of files) {
    try { const d = await HL.readFile(f); await HL.post("/api/attach/upload", { filename: d.filename, data: d.data, voucher_id: voucherId || null }); ok++; }
    catch (e) { last = e.message; say(f.name + ": " + e.message, "err"); }
  }
  return ok;
};

const _thumb = a => a.mime === "application/pdf"
  ? h("div", { class: "pdfthumb" }, "PDF")
  : h("img", { src: "/api/attach/file?id=" + a.id, alt: a.filename, loading: "lazy", style: "max-width:100%;max-height:100%" });

HL.attachDialog = async (voucherId, title) => {
  const list = await HL.get("/api/attach/list", { voucher_id: voucherId });
  const inp = h("input", { type: "file", multiple: true, accept: "image/*,application/pdf", "aria-label": "Choose bill photos or PDFs" });
  const grid = h("div", { class: "attgrid" }, list.map(a => h("figure", { class: "att" },
    h("a", { href: "/api/attach/file?id=" + a.id, target: "_blank", rel: "noopener", class: "attimg" }, _thumb(a)),
    h("figcaption", {}, a.filename + " · " + Math.round(a.size / 1024) + " KB"),
    h("button", { class: "btn", type: "button", onclick: async () => { if (await confirmBox("Remove this file?", "It will be deleted from the database.", "Remove", true)) { await HL.post("/api/attach/delete", { id: a.id }); m.close(); HL.attachDialog(voucherId, title); } } }, "Remove"))));
  const m = modal({ title: title || "Bills and receipts", wide: true, body: h("div", {}, list.length ? grid : h("p", { class: "hint" }, "No bill or receipt is attached yet."), h("div", { style: "margin-top:.8rem" }, inp)),
    buttons: [{ label: "Close", onclick: x => x.close() }, { label: "Attach", cls: "primary", onclick: async x => { if (!inp.files.length) { say("Choose a photo or PDF first.", "err"); return; } const n = await HL.uploadFiles([...inp.files], voucherId); if (n) { x.close(); say(n + " file(s) attached.", "ok"); HL.refresh(); } } }] });
};

/* ---- one reviewed entry row, used by Quick Entry ---- */
const _accOpts = () => ledgerOptions({ test: l => !l.cb_kind });
const _cbOpts = () => ledgerOptions({ test: l => !!l.cb_kind });

HL.screens.quickentry = {
  title: "Quick Entry",
  async render(sc) {
    await loadMasters();
    const cb = picker({ options: _cbOpts, placeholder: "Cash or bank" });
    const first = _cbOpts().find(o => o.label.toLowerCase() === "cash") || _cbOpts()[0]; if (first) cb.set(first.value);
    const [t, tb] = _tbl(["Date", "Money", "Account", "Amount (₹)", "Narration / shop / item", ""]);
    const rows = [];
    let lastDate = showDate(todayIso());
    const addRow = () => {
      const date = h("input", { type: "text", value: lastDate, style: "width:7.5rem", "aria-label": "Date" });
      const dir = h("select", { "aria-label": "Money in or out" }, h("option", { value: "out" }, "Paid out"), h("option", { value: "in" }, "Received"));
      const acc = picker({ options: _accOpts, placeholder: "Account..." });
      const amt = h("input", { type: "text", inputmode: "decimal", class: "amt", "aria-label": "Amount" });
      const desc = h("input", { type: "text", maxlength: "200", style: "width:100%", "aria-label": "Narration" });
      const r = { date, dir, acc, amt, desc };
      desc.addEventListener("change", async () => { if (acc.value || !desc.value.trim()) return; try { const s = await HL.get("/api/bulk/suggest", { text: desc.value }); if (s.ledger_id) acc.set(s.ledger_id); } catch (e) { } });
      desc.addEventListener("keydown", e => { if (e.key === "Enter" && !e.ctrlKey) { e.preventDefault(); lastDate = date.value; const n = addRow(); n.date.focus(); n.date.select(); } });
      date.addEventListener("change", () => { lastDate = date.value; });
      const tr = h("tr", {}, h("td", {}, date), h("td", {}, dir), h("td", {}, acc.el), h("td", {}, amt), h("td", {}, desc), h("td", {}, h("button", { class: "btn", type: "button", onclick: () => { rows.splice(rows.indexOf(r), 1); tr.remove(); } }, "×")));
      r.tr = tr; rows.push(r); tb.append(tr); return r;
    };
    const save = async () => {
      const out = [];
      for (const r of rows) {
        if (!r.amt.value.trim() && !r.desc.value.trim() && !r.acc.value) continue;
        const iso = parseDateInput(r.date.value, todayIso()); const x = String(r.amt.value).replace(/[,\s]/g, "");
        if (!iso) { say("Please check the date " + r.date.value, "err"); r.date.focus(); return; }
        if (!/^\d+(\.\d{1,2})?$/.test(x) || !(parseFloat(x) > 0)) { say("Please check the amount on the row dated " + r.date.value, "err"); r.amt.focus(); return; }
        if (!r.acc.value) { say("Please choose the account on the row dated " + r.date.value, "err"); r.acc.focus(); return; }
        out.push({ date: iso, dir: r.dir.value, amount_paise: Math.round(parseFloat(x) * 100), ledger_id: r.acc.value, desc: r.desc.value });
      }
      if (!out.length) { say("There is nothing to save yet.", "err"); return; }
      if (!cb.value) { say("Choose the Cash or Bank ledger first.", "err"); return; }
      try { const res = await HL.post("/api/bulk/commit", { bank_ledger_id: cb.value, rows: out, remember: true }); say(res.entered + " entries saved.", "ok"); HL.refresh(); } catch (e) { fail(e); }
    };
    for (let i = 0; i < 5; i++) addRow();
    sc.replaceChildren(_page("Quick Entry", "Like writing in the notebook: one line per payment or receipt", h("div", { class: "row", style: "gap:.6rem;align-items:center;margin-bottom:.6rem" }, h("span", {}, "Money moves through:"), cb.el),
      h("div", { class: "scroll" }, t), h("div", { class: "row", style: "gap:.5rem;margin-top:.6rem" }, h("button", { class: "btn", onclick: () => addRow() }, "Add a line"), h("button", { class: "btn primary", onclick: save }, "Save all (Ctrl+A)")),
      h("p", { class: "hint" }, "Each line becomes a Payment (paid out) or Receipt (received). Enter in the last box adds a new line. When you type a shop or item, the account is suggested from your earlier entries.")));
    HL.setKeys([BACK, { k: "Ctrl+A", label: "Save all", fn: save }]);
    rows[0].date.focus();
  },
};

/* ---- Bill Inbox: photos waiting to be entered, shown beside a quick form ---- */
HL.screens.billinbox = {
  title: "Bill Inbox",
  async render(sc, params) {
    await loadMasters();
    const list = await HL.get("/api/attach/list", { inbox: 1 });
    const inp = h("input", { type: "file", multiple: true, accept: "image/*,application/pdf", "aria-label": "Add bills" });
    const up = async () => { if (!inp.files.length) return; const n = await HL.uploadFiles([...inp.files], null); if (n) { say(n + " file(s) added to the inbox.", "ok"); HL.refresh(); } };
    const cur = list.find(a => String(a.id) === String(params && params.id)) || list[0];
    const strip = h("div", { class: "inbox-strip" }, list.map(a => h("button", { type: "button", class: "inbox-item" + (cur && a.id === cur.id ? " on" : ""), onclick: () => { HL.cur.params = { id: a.id }; HL.refresh(); } }, _thumb(a))));
    let form = h("p", { class: "hint" }, "The inbox is empty. Add photos or PDFs of bills and receipts; you can enter each one here and it stays attached to its entry.");
    let viewer = "";
    if (cur) {
      viewer = cur.mime === "application/pdf" ? h("iframe", { src: "/api/attach/file?id=" + cur.id, class: "inbox-view", title: cur.filename }) : h("div", { class: "inbox-view imgv" }, h("img", { src: "/api/attach/file?id=" + cur.id, alt: cur.filename }));
      const cb = picker({ options: _cbOpts, placeholder: "Cash or bank" }); const f0 = _cbOpts().find(o => o.label.toLowerCase() === "cash") || _cbOpts()[0]; if (f0) cb.set(f0.value);
      const dir = h("select", { "aria-label": "Money in or out" }, h("option", { value: "out" }, "Paid out (a bill I paid)"), h("option", { value: "in" }, "Received"));
      const date = h("input", { type: "text", value: showDate(todayIso()), "aria-label": "Date" });
      const acc = picker({ options: _accOpts, placeholder: "Account (expense / income)..." });
      const amt = h("input", { type: "text", inputmode: "decimal", class: "amt", "aria-label": "Amount" });
      const desc = h("input", { type: "text", maxlength: "200", "aria-label": "Narration" });
      desc.addEventListener("change", async () => { if (acc.value || !desc.value.trim()) return; try { const s = await HL.get("/api/bulk/suggest", { text: desc.value }); if (s.ledger_id) acc.set(s.ledger_id); } catch (e) { } });
      const enter = async () => {
        const iso = parseDateInput(date.value, todayIso()), x = String(amt.value).replace(/[,\s]/g, "");
        if (!iso) { say("Please check the date.", "err"); return; } if (!/^\d+(\.\d{1,2})?$/.test(x) || !(parseFloat(x) > 0)) { say("Please type the amount.", "err"); return; }
        if (!acc.value || !cb.value) { say("Choose the account and the cash / bank ledger.", "err"); return; }
        try { await HL.post("/api/bulk/commit", { bank_ledger_id: cb.value, remember: true, rows: [{ date: iso, dir: dir.value, amount_paise: Math.round(parseFloat(x) * 100), ledger_id: acc.value, desc: desc.value, att_id: cur.id }] }); say("Entered, and the bill is attached to it.", "ok"); HL.cur.params = {}; HL.refresh(); } catch (e) { fail(e); }
      };
      const del = async () => { if (await confirmBox("Remove from the inbox?", "The file will be deleted.", "Remove", true)) { await HL.post("/api/attach/delete", { id: cur.id }); HL.cur.params = {}; HL.refresh(); } };
      form = h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f" }, "Date on the bill", date), h("label", { class: "f" }, "What happened", dir), h("label", { class: "f" }, "Shop / item (the account is suggested)", desc), h("label", { class: "f" }, "Account", acc.el), h("label", { class: "f" }, "Amount (₹)", amt),
        h("label", { class: "f" }, "Paid from / received into", cb.el), h("div", { class: "row", style: "gap:.5rem" }, h("button", { class: "btn primary", onclick: enter }, "Enter and attach"), h("button", { class: "btn", onclick: del }, "Remove file")));
    }
    sc.replaceChildren(_page("Bill Inbox", list.length + " waiting", h("div", { class: "row", style: "gap:.6rem;align-items:center;margin-bottom:.6rem" }, inp, h("button", { class: "btn", onclick: up }, "Add to inbox")), strip, cur ? h("div", { class: "inbox" }, viewer, h("div", {}, form)) : form));
    HL.setKeys([BACK]);
  },
};

/* ---- Import from Excel / CSV ---- */
HL.screens.bulkimport = {
  title: "Import from Excel / CSV",
  async render(sc) {
    await loadMasters();
    const inp = h("input", { type: "file", accept: ".csv,.txt,.xlsx", "aria-label": "Choose file" });
    const body = h("div", {});
    const guess = (hd, words) => hd.findIndex(x => words.some(w => x.toLowerCase().includes(w)));
    const go = async () => {
      if (!inp.files.length) { say("Choose a file first.", "err"); return; }
      let parsed; try { const d = await HL.readFile(inp.files[0]); parsed = await HL.post("/api/bulk/parse", { filename: d.filename, data: d.data }); } catch (e) { fail(e); return; }
      mapping(parsed);
    };
    function mapping(p) {
      const hd = p.headers, opt = (sel) => [h("option", { value: "" }, "(none)"), ...hd.map((x, i) => h("option", { value: i }, x || "Column " + (i + 1)))];
      const mk = (label, key, g) => { const s = h("select", { "aria-label": label }, opt()); const i = guess(hd, g); if (i >= 0) s.value = i; return [key, s, h("label", { class: "f" }, label, s)]; };
      const f = [mk("Date", "date", ["date", "dt", "day"]), mk("Description / shop / item", "desc", ["desc", "particular", "narration", "item", "detail", "name"]), mk("Amount", "amount", ["amount", "amt", "value"]),
        mk("Debit / paid out (if separate)", "debit", ["debit", "withdraw", "paid", "dr"]), mk("Credit / received (if separate)", "credit", ["credit", "deposit", "received", "cr"]), mk("In / Out or Dr / Cr marker", "type", ["type", "dr/cr"]), mk("Reference / bill no.", "ref", ["ref", "bill", "cheque", "chq"])];
      const flip = h("input", { type: "checkbox" });
      body.replaceChildren(h("p", {}, `${p.rows.length} lines found` + (p.truncated ? " (only the first 5,000 are read)" : "") + ". Tell HomeLedger which column is which:"), h("div", { class: "fgrid" }, f.map(x => x[2])),
        h("label", { class: "f", style: "flex-direction:row;gap:.4rem;align-items:center" }, flip, "Swap in and out (use this if bank-statement debits should count as money received)"),
        h("div", { style: "margin-top:.6rem" }, h("button", { class: "btn primary", onclick: async () => { const map = {}; f.forEach(x => { map[x[0]] = x[1].value; }); try { review(p, await HL.post("/api/bulk/preview", { rows: p.rows, map, flip: flip.checked })); } catch (e) { fail(e); } } }, "Next: review the lines")));
    }
    function review(p, pv) {
      const rows = pv.rows.map(r => Object.assign({ use: !r.problem && !r.duplicate }, r));
      const cb = picker({ options: _cbOpts, placeholder: "Cash or bank" }); const f0 = _cbOpts().find(o => o.label.toLowerCase() === "cash") || _cbOpts()[0]; if (f0) cb.set(f0.value);
      const norm = s => (s || "").toLowerCase().replace(/[^a-z ]/g, " ").replace(/\s+/g, " ").trim();
      let page = 0; const PER = 60;
      const [t, tb] = _tbl(["Enter", "Date", "Description", "In/Out", "Amount", "Account", "Note"]);
      const draw = () => {
        tb.replaceChildren();
        rows.slice(page * PER, page * PER + PER).forEach(r => {
          const use = h("input", { type: "checkbox", checked: r.use, disabled: !!r.problem, onchange: e => { r.use = e.target.checked; sum(); } });
          const dir = h("select", { disabled: !!r.problem, onchange: e => { r.dir = e.target.value; } }, h("option", { value: "out" }, "Out"), h("option", { value: "in" }, "In")); dir.value = r.dir || "out";
          const acc = picker({ options: _accOpts, placeholder: "Account...", onpick: o => { r.ledger_id = o ? o.value : null; if (o && r.desc) { rows.forEach(x => { if (x !== r && !x.ledger_id && norm(x.desc) === norm(r.desc)) x.ledger_id = o.value; }); } } }); if (r.ledger_id) acc.set(r.ledger_id);
          tb.append(h("tr", { class: r.problem ? "bad" : "" }, h("td", {}, use), h("td", {}, r.date ? showDate(r.date) : "?"), h("td", {}, r.desc), h("td", {}, dir), h("td", { class: "r" }, r.amount_paise ? inr(r.amount_paise) : "?"), h("td", {}, r.problem ? "" : acc.el),
            h("td", {}, r.problem ? r.problem : r.duplicate ? "Already entered?" : r.source === "rule" ? "from your rule" : r.source === "history" ? "like earlier entries" : "")));
        });
        pager.replaceChildren(h("button", { class: "btn", disabled: page === 0, onclick: () => { page--; draw(); } }, "Previous"), h("span", {}, ` Page ${page + 1} of ${Math.max(1, Math.ceil(rows.length / PER))} `), h("button", { class: "btn", disabled: (page + 1) * PER >= rows.length, onclick: () => { page++; draw(); } }, "Next"));
        sum();
      };
      const pager = h("div", { class: "row", style: "gap:.4rem;margin:.5rem 0;align-items:center" }), sumBox = h("div", { class: "banner" });
      const sum = () => { const u = rows.filter(r => r.use); const miss = u.filter(r => !r.ledger_id).length; sumBox.className = "banner " + (miss ? "warn" : "ok"); sumBox.textContent = `${u.length} lines will be entered` + (miss ? `; ${miss} still need an account.` : "."); };
      const commit = async () => {
        const u = rows.filter(r => r.use); if (!u.length) { say("No lines are ticked.", "err"); return; }
        if (u.some(r => !r.ledger_id)) { say("Choose an account for every ticked line (use the Next/Previous buttons to check all pages).", "err"); return; }
        if (!cb.value) { say("Choose the Cash or Bank ledger first.", "err"); return; }
        if (!await confirmBox("Enter " + u.length + " lines?", "They become Payment and Receipt vouchers. A backup is taken first.", "Enter them")) return;
        try { const res = await HL.post("/api/bulk/commit", { bank_ledger_id: cb.value, remember: true, rows: u.map(r => ({ date: r.date, dir: r.dir, amount_paise: r.amount_paise, ledger_id: r.ledger_id, desc: r.desc, ref: r.ref })) }); say(res.entered + " entries added.", "ok"); HL.go("daybook"); } catch (e) { fail(e); }
      };
      body.replaceChildren(h("div", { class: "row", style: "gap:.6rem;align-items:center;margin-bottom:.4rem" }, h("span", {}, "Money moves through:"), cb.el), sumBox, pager, h("div", { class: "scroll" }, t),
        h("div", { style: "margin-top:.6rem" }, h("button", { class: "btn primary", onclick: commit }, "Enter the ticked lines")),
        h("p", { class: "hint" }, "Lines already in your books are left unticked. Picking an account for one line fills the same shop / item on other lines. HomeLedger remembers your choices as rules for next time."));
      draw();
    }
    sc.replaceChildren(_page("Import from Excel / CSV", "A typed-up notebook or a bank statement", h("div", { class: "row", style: "gap:.6rem;align-items:center;margin-bottom:.8rem" }, inp, h("button", { class: "btn primary", onclick: go }, "Read the file")),
      h("p", { class: "hint" }, "The file needs a heading row. It can have a Date, a Description, and either one Amount column or separate Debit / Credit columns. Dates like 05-06-2026, 5/6/2026 or 2026-06-05 are understood."), body));
    HL.setKeys([BACK]);
  },
};

HL.screens.catrules = {
  title: "Auto-categorise Rules",
  async render(sc) {
    await loadMasters(); const rules = await HL.get("/api/bulk/rules");
    const [t, tb] = _tbl(["When the description contains", "Use the account", ""]);
    rules.forEach(r => tb.append(h("tr", {}, h("td", {}, r.keyword), h("td", {}, r.ledger), h("td", {}, h("button", { class: "btn", type: "button", onclick: async () => { await HL.post("/api/bulk/rule/delete", { id: r.id }); HL.refresh(); } }, "Remove")))));
    if (!rules.length) tb.append(h("tr", {}, h("td", { colspan: 3, class: "empty" }, "No rules yet. They are added as you enter lines in Quick Entry, Bill Inbox and Import.")));
    const kw = h("input", { type: "text", placeholder: "e.g. fertiliser", "aria-label": "Keyword" }), acc = picker({ options: _accOpts, placeholder: "Account..." });
    sc.replaceChildren(_page("Auto-categorise Rules", "Teach HomeLedger where things belong", t, h("div", { class: "row", style: "gap:.5rem;margin-top:.8rem;align-items:center" }, kw, acc.el, h("button", { class: "btn primary", onclick: async () => { try { await HL.post("/api/bulk/rule/save", { keyword: kw.value, ledger_id: acc.value }); HL.refresh(); } catch (e) { fail(e); } } }, "Add rule"))));
    HL.setKeys([BACK]);
  },
};
