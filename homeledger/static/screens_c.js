/* Screens, part 3: masters, opening balances, utilities, company, quit */
"use strict";

/* ---------- ledger create / alter form (modal) ---------- */
HL.ledgerForm = function ({ id, name, onsaved }) {
  const L = id ? M().ledgers.find(l => l.id === id) : null;
  const nm = h("input", { type: "text", value: L ? L.name : (name || ""), maxlength: "60", "aria-label": "Ledger name" });
  const grp = picker({ options: () => groupOptions(), value: L ? L.group_id : null, placeholder: "Choose a group (e.g. Indirect Expenses)", width: "100%" });
  const op = h("input", { type: "text", inputmode: "decimal", class: "amt", value: L && L.opening_paise ? (L.opening_paise / 100).toFixed(2) : "", "aria-label": "Opening balance" });
  const ot = h("select", { "aria-label": "Dr or Cr" }, h("option", { value: "Dr" }, "Dr (you have / are owed)"), h("option", { value: "Cr" }, "Cr (you owe)")); ot.value = L ? L.opening_type : "Dr";
  const cc = picker({ options: () => ccOptions(true), value: L ? L.default_cc_id : null, placeholder: "None", width: "100%" });
  const act = h("input", { type: "checkbox", checked: L ? !!L.is_active : true });
  const notes = h("input", { type: "text", value: L ? L.notes : "", maxlength: "300", "aria-label": "Notes" });
  const body = h("div", { class: "fgrid", style: "grid-template-columns:1fr" },
    h("label", { class: "f" }, "Name", nm), h("label", { class: "f" }, "Under group", grp.el),
    h("div", { class: "row" }, h("label", { class: "f" }, "Opening balance (only for cash, bank, loans, land, etc.)", h("span", { class: "row" }, op, ot))),
    h("label", { class: "f" }, "Usual cost centre (auto-filled in vouchers)", cc.el), h("label", { class: "f" }, "Notes", notes),
    L ? h("label", { class: "f", style: "flex-direction:row;gap:.4rem;align-items:center" }, act, "Active (untick to hide from lists)") : "");
  enterAsTab(body, () => doSave());
  let m;
  async function doSave() {
    try {
      const res = await HL.post("/api/ledger/save", { id, name: nm.value, group_id: grp.value, opening: op.value, opening_type: ot.value, default_cc_id: cc.value, is_active: act.checked, notes: notes.value });
      m.close(); say("Ledger saved.", "ok"); await loadMasters(); onsaved && onsaved(res.id);
    } catch (e) { fail(e); }
  }
  m = modal({ title: L ? "Ledger Alteration" : "Ledger Creation", body, focus: "input",
    buttons: [L ? { label: "GST details", onclick: () => HL.gstPartyDialog(L) } : null, { label: "Cancel (Esc)", onclick: m => m.close() }, { label: "Accept (Ctrl+A)", cls: "primary", onclick: doSave }].filter(Boolean) });
  m.box.addEventListener("keydown", e => { if (e.ctrlKey && e.key.toLowerCase() === "a") { e.preventDefault(); doSave(); } });
  return m;
};

/* ---------- masters ---------- */
HL.screens.masters = {
  title: "Masters",
  async render(sc, params) {
    await loadMasters();
    const tab = params.tab || "ledgers";
    const tabs = h("div", { class: "chips", style: "margin-bottom:.8rem" }, [["ledgers", "Ledgers"], ["groups", "Groups"], ["activities", "Cost Centres"]].map(([k, l]) => h("button", { class: "chip" + (tab === k ? " on" : ""), type: "button", onclick: () => { HL.cur.params = { tab: k }; HL.refresh(); } }, l)));
    const root = h("div", {}, h("h1", { class: "title" }, "Masters"), h("p", { class: "sub" }, "Ledgers are your accounts (Cash, Groceries, Sales...). Groups collect ledgers. Cost centres tag entries to a purpose or place (optional)."), tabs);
    let keys = [BACK];
    if (tab === "ledgers") {
      const filt = h("input", { type: "search", placeholder: "Filter ledgers...", "aria-label": "Filter", style: "min-width:16rem" });
      const showOff = h("input", { type: "checkbox" });
      const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Ledger", "Group", "Used", "Balance now"].map((x, i) => h("th", { class: i > 1 ? "r" : "" }, x)))));
      const tb = h("tbody", {}); t.append(tb);
      const trs = [];
      M().ledgers.forEach(l => {
        const tr = h("tr", { class: "row", tabindex: "0", "data-t": (l.name + " " + l.group_name).toLowerCase(), "data-off": l.is_active ? "" : "1", onclick: () => HL.ledgerForm({ id: l.id, onsaved: () => HL.refresh() }) },
          h("td", {}, l.name, l.is_active ? "" : h("span", { class: "tag", style: "margin-left:.5rem" }, "hidden")), h("td", {}, l.group_name), h("td", { class: "r" }, l.n_entries || ""), h("td", { class: "r" }, l.balance_paise == null ? "" : bal(l.balance_paise)));
        rowKeys(tr); trs.push(tr); tb.append(tr);
      });
      const apply = () => { const q = filt.value.toLowerCase().trim(); trs.forEach(tr => tr.style.display = (!q || tr.dataset.t.includes(q)) && (showOff.checked || !tr.dataset.off) ? "" : "none"); };
      filt.addEventListener("input", apply); showOff.addEventListener("change", apply); apply();
      root.append(h("div", { class: "row", style: "margin-bottom:.6rem" }, filt, h("label", {}, showOff, " Show hidden ledgers")), h("div", { class: "scroll" }, t));
      keys.push({ k: "Alt+C", label: "Create ledger", fn: () => HL.ledgerForm({ onsaved: () => HL.refresh() }) }, { k: "", label: "Delete selected", fn: async () => {
        const tr = document.activeElement.closest && document.activeElement.closest("tr.row"); const i = trs.indexOf(tr); if (i < 0) { say("Select a ledger row first (arrow keys).", "err"); return; }
        const l = M().ledgers[i];
        if (await confirmBox("Delete ledger?", "Delete '" + l.name + "'? This only works for ledgers that have never been used.", "Delete", true)) { try { await HL.post("/api/ledger/delete", { id: l.id }); say("Deleted.", "ok"); HL.refresh(); } catch (e) { fail(e); } }
      } });
      HL.onKey = e => { if (e.altKey && e.key.toLowerCase() === "c") { e.preventDefault(); HL.ledgerForm({ onsaved: () => HL.refresh() }); return true; } };
      if (params.create) { params.create = 0; setTimeout(() => HL.ledgerForm({ onsaved: () => HL.refresh() }), 60); }
    } else if (tab === "groups") {
      const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Group", "Kind", ""].map(x => h("th", {}, x)))));
      const tb = h("tbody", {}); t.append(tb);
      const byP = {}; M().groups.forEach(g => (byP[g.parent_id || 0] ||= []).push(g));
      const nat = { asset: "Assets", liability: "Liabilities", income: "Income", expense: "Expenses" };
      const add = (g, d) => { const tr = h("tr", { class: g.is_system ? "" : "row", tabindex: g.is_system ? null : "0", onclick: g.is_system ? null : () => editGroup(g) }, h("td", { class: "ind" + d }, g.name), h("td", {}, nat[g.nature]), h("td", {}, g.is_system ? h("span", { class: "tag" }, "built in") : h("span", { class: "tag" }, "yours"))); if (!g.is_system) rowKeys(tr); tb.append(tr); (byP[g.id] || []).forEach(c => add(c, Math.min(d + 1, 3))); };
      (byP[0] || []).forEach(g => add(g, 0));
      root.append(h("div", { class: "scroll" }, t));
      const editGroup = g => {
        const nmI = h("input", { type: "text", value: g ? g.name : "", maxlength: "60", "aria-label": "Group name" });
        const par = picker({ options: () => groupOptions(), value: g ? g.parent_id : null, placeholder: "Which group does it belong to?", width: "100%" });
        const body = h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f" }, "Group name", nmI), g ? "" : h("label", { class: "f" }, "Belongs under", par.el));
        const m = modal({ title: g ? "Group Alteration" : "Group Creation", body, buttons: [g ? { label: "Delete", cls: "danger", onclick: async m2 => { if (await confirmBox("Delete group?", "Only empty groups can be deleted.", "Delete", true)) { try { await HL.post("/api/group/delete", { id: g.id }); m2.close(); HL.refresh(); } catch (e) { fail(e); } } } } : null, { label: "Cancel", onclick: m => m.close() }, { label: "Accept", cls: "primary", onclick: save }].filter(Boolean) });
        enterAsTab(body, save);
        async function save() { try { await HL.post("/api/group/save", { id: g && g.id, name: nmI.value, parent_id: par.value }); m.close(); await loadMasters(); HL.refresh(); } catch (e) { fail(e); } }
      };
      keys.push({ k: "Alt+C", label: "Create group", fn: () => editGroup(null) });
      if (params.create) { params.create = 0; setTimeout(() => editGroup(null), 60); }
    } else {
      const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Cost Centre", "Under"].map(x => h("th", {}, x)))));
      const tb = h("tbody", {}); t.append(tb);
      const byP = {}; M().cost_centres.forEach(c => (byP[c.parent_id || 0] ||= []).push(c));
      const nameOf = id => (M().cost_centres.find(c => c.id === id) || {}).name || "";
      const editCc = c => {
        const nmI = h("input", { type: "text", value: c ? c.name : "", maxlength: "60", "aria-label": "Cost centre name" });
        const par = picker({ options: () => M().cost_centres.filter(x => !x.parent_id).map(x => ({ value: x.id, label: x.name })), value: c ? c.parent_id : null, placeholder: "None (top level)", width: "100%" });
        const act = h("input", { type: "checkbox", checked: c ? !!c.is_active : true });
        const body = h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f" }, "Cost centre name", nmI), c ? "" : h("label", { class: "f" }, "Belongs to", par.el), c ? h("label", { class: "f", style: "flex-direction:row;gap:.4rem;align-items:center" }, act, "Active") : "");
        const m = modal({ title: c ? "Cost Centre Alteration" : "Cost Centre Creation", body, buttons: [c ? { label: "Delete", cls: "danger", onclick: async m2 => { if (await confirmBox("Delete activity?", "Only activities that were never used can be deleted. Otherwise untick Active.", "Delete", true)) { try { await HL.post("/api/cc/delete", { id: c.id }); m2.close(); await loadMasters(); HL.refresh(); } catch (e) { fail(e); } } } } : null, { label: "Cancel", onclick: m => m.close() }, { label: "Accept", cls: "primary", onclick: save }].filter(Boolean) });
        enterAsTab(body, save);
        async function save() { try { await HL.post("/api/cc/save", { id: c && c.id, name: nmI.value, parent_id: par.value, is_active: act.checked }); m.close(); await loadMasters(); HL.refresh(); } catch (e) { fail(e); } }
      };
      const add = (c, d) => { const tr = h("tr", { class: "row", tabindex: "0", onclick: () => editCc(c) }, h("td", { class: "ind" + d }, c.name, c.is_active ? "" : h("span", { class: "tag", style: "margin-left:.5rem" }, "hidden")), h("td", {}, nameOf(c.parent_id)), h("td", {}, c.kind === "farm" ? "Farm" : "Household")); rowKeys(tr); tb.append(tr); (byP[c.id] || []).forEach(k => add(k, d + 1)); };
      (byP[0] || []).forEach(c => add(c, 0));
      root.append(h("div", { class: "scroll" }, t));
      keys.push({ k: "Alt+C", label: "Create cost centre", fn: () => editCc(null) });
      if (params.create) { params.create = 0; setTimeout(() => editCc(null), 60); }
    }
    sc.replaceChildren(root); const f = $("tbody tr.row", root); f && f.focus(); HL.setKeys(keys);
  },
};

/* ---------- opening balances ---------- */
HL.screens.openings = {
  title: "Opening Balances",
  async render(sc) {
    await loadMasters();
    const co = HL.S.status.company;
    const root = h("div", {}, h("h1", { class: "title" }, "Opening Balances"), h("p", { class: "sub" }, "What you had on the books beginning date, " + showDate(co.books_begin) + ". Enter cash in hand, bank balance, loans, land, savings, and money lent or borrowed."));
    const list = M().ledgers.filter(l => l.nature === "asset" || l.nature === "liability");
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Account", "Group", "Amount (\u20b9)", "Dr / Cr"].map((x, i) => h("th", { class: i === 2 ? "r" : "" }, x)))));
    const tb = h("tbody", {}); t.append(tb);
    const rows = [], diff = h("span", { class: "num" });
    const parse = s => { const x = String(s || "").replace(/[,\s\u20b9]/g, ""); return x === "" ? 0 : (/^\d+(\.\d{1,2})?$/.test(x) ? Math.round(parseFloat(x) * 100) : NaN); };
    const calc = () => { let n = 0; rows.forEach(r => { const a = parse(r.amt.value); if (!isNaN(a)) n += r.typ.value === "Dr" ? a : -a; }); diff.textContent = n === 0 ? "Balanced \u2713" : rs(Math.abs(n)) + (n > 0 ? " more on the Dr side" : " more on the Cr side"); diff.style.color = n === 0 ? "var(--good)" : "var(--bad)"; };
    list.forEach(l => {
      const amt = h("input", { type: "text", inputmode: "decimal", class: "amt", value: l.opening_paise ? (l.opening_paise / 100).toFixed(2) : "", "aria-label": l.name + " opening amount" });
      const typ = h("select", { "aria-label": "Dr or Cr" }, h("option", { value: "Dr" }, "Dr"), h("option", { value: "Cr" }, "Cr")); typ.value = l.opening_type;
      amt.addEventListener("input", calc); typ.addEventListener("change", calc); amt.addEventListener("focus", () => amt.select());
      rows.push({ l, amt, typ });
      tb.append(h("tr", {}, h("td", {}, l.name), h("td", { class: "muted" }, l.group_name), h("td", { class: "r" }, amt), h("td", {}, typ)));
    });
    root.append(h("div", { class: "banner" }, h("div", {}, "How it works: assets (cash, bank, land, savings, money you are to receive) are normally ", h("b", {}, "Dr"), "; loans and money you owe are ", h("b", {}, "Cr"), ". Anything left over is your own capital: enter it on the Capital Account line as Cr. The two sides must match.")),
      h("div", { class: "scroll" }, t), h("div", { class: "row", style: "margin-top:.7rem" }, h("b", {}, "Difference: "), diff));
    sc.replaceChildren(root); calc(); enterAsTab(root);
    const save = async () => {
      try {
        const items = rows.map(r => ({ ledger_id: r.l.id, amount: r.amt.value, type: r.typ.value }));
        const res = await HL.post("/api/openings/save", { items }); await loadMasters();
        say(res.difference_paise === 0 ? "Opening balances saved and balanced." : "Saved, but the two sides differ by " + rs(Math.abs(res.difference_paise)) + ". Put the difference on Capital Account.", res.difference_paise === 0 ? "ok" : "err");
        HL.refresh();
      } catch (e) { fail(e); }
    };
    HL.onKey = e => { if (e.ctrlKey && e.key.toLowerCase() === "a") { e.preventDefault(); save(); return true; } };
    HL.setKeys([{ k: "Ctrl+A", label: "Accept (save)", fn: save }, BACK, "sep", { k: "", label: "Create ledger", fn: () => HL.ledgerForm({ onsaved: () => HL.refresh() }) }, { k: "F3", label: "Books begin date", fn: () => HL.go("company") }]);
    const f = $("input.amt", root); f && f.focus();
  },
};

/* ---------- company ---------- */
HL.screens.company = {
  title: "Company Info",
  async render(sc) {
    await loadMasters();
    const co = HL.S.status.company;
    const nm = h("input", { type: "text", value: co.name, maxlength: "80", "aria-label": "Name" }), bb = h("input", { type: "text", value: showDate(co.books_begin), "aria-label": "Books beginning" });
    const root = h("div", {}, h("h1", { class: "title" }, "Company Info"), h("p", { class: "sub" }, "The name shown at the top, and the date your books begin (opening balances are as on this date)."),
      h("div", { class: "panel", style: "padding:.9rem;max-width:34rem" }, h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f" }, "Name of the book", nm), h("label", { class: "f" }, "Books beginning from", bb)),
        h("p", { class: "hint" }, "Financial year runs April to March. If you will copy older notebook entries, set the beginning date to the start of the oldest notebook year."),
        h("div", { class: "row" }, h("button", { class: "btn primary", onclick: save }, "Accept"))));
    sc.replaceChildren(root); enterAsTab(root, save); nm.focus();
    async function save() { try { const iso = parseDateInput(bb.value, co.books_begin); if (!iso) throw new Error("Please type the date like 01-04-2025."); await HL.post("/api/company/save", { name: nm.value, books_begin: iso }); await loadMasters(); $("#company").textContent = HL.S.status.company.name; say("Saved.", "ok"); HL.back(); } catch (e) { fail(e); } }
    HL.setKeys([{ k: "Enter", label: "Accept", fn: save }, BACK]);
  },
};

/* ---------- utilities ---------- */
HL.screens.utilities = {
  title: "Utilities",
  async render(sc, params) {
    await loadMasters();
    const tab = params.tab || "backup";
    const defs = [["backup", "Backup & Restore"], ["health", "Health Check"], ["repair", "Data Repair"], ["tally", "Tally XML"], ["export", "Export to Excel"], ["settings", "Settings"], ["security", "Security"], ["audit", "Audit Trail"]];
    const root = h("div", {}, h("h1", { class: "title" }, "Utilities"), h("div", { class: "chips", style: "margin:.4rem 0 .9rem" }, defs.map(([k, l]) => h("button", { class: "chip" + (tab === k ? " on" : ""), type: "button", onclick: () => { HL.cur.params = { tab: k }; HL.refresh(); } }, l))));
    const st = HL.S.status;
    if (tab === "backup") {
      const b = await HL.get("/api/backups");
      let pwTouched = false;
      const copyP = h("input", { type: "password", autocomplete: "new-password", placeholder: st.copy_protected ? "\u2022\u2022\u2022\u2022\u2022\u2022 (set)" : "", style: "width:100%", "aria-label": "Backup password", oninput: () => { pwTouched = true; } });
      const copyI = h("input", { type: "text", value: st.copy_dir || "", placeholder: st.default_copy_dir, style: "width:100%", "aria-label": "Second copy folder" });
      root.append(
        h("div", { class: "panel", style: "padding:.9rem;margin-bottom:.8rem" }, h("h3", { style: "margin-top:0" }, "Your data is backed up automatically"),
          h("p", {}, "A safe copy is made each time HomeLedger starts, about hourly while you are entering data, and when you close it. Latest: ", h("b", {}, st.last_backup ? st.last_backup.slice(0, 16) : "none yet"), ". Backups kept here: ", h("b", {}, b.rows.length)),
          h("p", { class: "muted" }, "Stored in: " + b.dir),
          h("button", { class: "btn primary", onclick: async e => { e.target.disabled = true; try { const r = await HL.post("/api/backup/create"); say(r.copy_error ? "Backup made, but the second copy failed: " + r.copy_error : "Backup created.", r.copy_error ? "err" : "ok"); await loadMasters(); HL.refresh(); } catch (er) { fail(er); e.target.disabled = false; } } }, "Create backup now")),
        h("div", { class: "panel", style: "padding:.9rem;margin-bottom:.8rem" }, h("h3", { style: "margin-top:0" }, "Second copy (strongly recommended)"),
          h("p", {}, "Every backup is also copied to this folder. Choose a pen drive, an external disk, or a OneDrive/Google Drive folder so the data survives if this computer fails."),
          st.copy_error ? h("div", { class: "banner err" }, "Last attempt failed: " + st.copy_error) : "",
          h("label", { class: "f" }, "Folder (for example E:\\HomeLedger Backups)", copyI),
          h("label", { class: "f", style: "margin-top:.5rem" }, st.copy_protected ? "Backup password (protected now; type a new one to change, clear to turn off)" : "Protect the copy with a password (recommended for Google Drive or OneDrive; optional)", copyP),
          h("p", { class: "hint" }, "A protected copy is scrambled so nobody who opens the folder can read your accounts. KEEP THIS PASSWORD SAFE: without it, protected copies cannot be opened. The backups kept on this computer are not scrambled."),
          h("div", { class: "row", style: "margin-top:.5rem" }, h("button", { class: "btn primary", onclick: async () => { try { await HL.post("/api/settings/save", { copy_dir: copyI.value, ...(copyP.value !== "" || pwTouched ? { copy_password: copyP.value } : {}) }); await loadMasters(); say(copyI.value.trim() ? "Second copy folder saved." : "Second copy turned off.", "ok"); HL.refresh(); } catch (e) { fail(e); } } }, "Save folder"), st.last_external_copy ? h("span", { class: "muted" }, "Last second copy: " + st.last_external_copy.slice(0, 16)) : "")));
      const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Backup made", "Kind", "Size", ""].map(x => h("th", {}, x)))));
      const tb = h("tbody", {}); t.append(tb);
      const kind = { auto: "Automatic", manual: "Manual", "pre-restore": "Before a restore" };
      b.rows.slice(0, 60).forEach(r => tb.append(h("tr", {}, h("td", {}, r.when.slice(0, 16)), h("td", {}, kind[r.reason] || r.reason), h("td", {}, Math.max(1, Math.round(r.size / 1024)) + " KB"),
        h("td", { class: "r" }, h("button", { class: "btn", onclick: async () => {
          if (!(await confirmBox("Restore this backup?", "HomeLedger will go back to how it was on " + r.when.slice(0, 16) + ". Anything entered after that time will be removed from the live book. A backup of the current state is made first, so this can be undone.", "Yes, restore", true))) return;
          try { await HL.post("/api/backup/restore", { name: r.name }); await loadMasters(); say("Restored.", "ok"); HL.stack = []; HL.cur = { name: "gateway", params: {} }; HL.render(); } catch (e) { fail(e); } } }, "Restore")))));
      const rfPath = h("input", { type: "text", placeholder: "G:\\My Drive\\HomeLedger\\homeledger-20261120-101500-auto.db.hlbk", style: "width:100%", "aria-label": "Protected copy file" });
      const rfPw = h("input", { type: "password", style: "width:100%", "aria-label": "Backup password" });
      root.append(h("h3", {}, "Backups on this computer"), h("div", { class: "scroll" }, t),
        h("div", { class: "panel", style: "padding:.9rem;margin-top:.8rem" }, h("h3", { style: "margin-top:0" }, "Restore from a protected copy"),
          h("p", { class: "muted" }, "For a copy kept in Google Drive / a pen drive (a file ending in .hlbk), for example on a new computer."),
          h("label", { class: "f" }, "Full location of the file", rfPath), h("label", { class: "f" }, "Backup password", rfPw),
          h("div", { class: "row", style: "margin-top:.5rem" }, h("button", { class: "btn", onclick: async () => {
            if (!(await confirmBox("Restore this protected copy?", "HomeLedger will go back to how it was when that copy was made. A backup of the current state is made first.", "Yes, restore", true))) return;
            try { await HL.post("/api/backup/restore_file", { path: rfPath.value, password: rfPw.value }); await loadMasters(); say("Restored.", "ok"); HL.stack = []; HL.cur = { name: "gateway", params: {} }; HL.render(); } catch (e) { fail(e); } } }, "Restore"))));
    } else if (tab === "health") {
      const r = await HL.get("/api/health");
      root.append(h("div", { class: "banner " + (r.all_ok ? "ok" : "warn") }, r.all_ok ? "Everything looks healthy." : "Some checks need attention."), h("div", { class: "checks" }, r.checks.map(c => h("div", { class: "ck " + (c.ok ? "ok" : "bad") }, h("b", {}, (c.ok ? "\u2713 " : "\u26a0 ") + c.name), h("span", {}, c.detail)))),
        h("p", { class: "hint" }, "These checks never change your data."));
    } else if (tab === "repair") {
      const out = h("div", {});
      const run = h("button", { class: "btn primary", onclick: async () => {
        if (!await confirmBox("Repair data", "HomeLedger will take a safety copy, check every record, rebuild its indexes and compact the file. No entry is changed or removed. It may take a few seconds.", "Start repair")) return;
        try { const r = await HL.post("/api/repair", {});
          out.replaceChildren(h("div", { class: "banner " + (r.ok ? "ok" : "warn") }, r.message), h("div", { class: "checks" }, r.steps.map(c => h("div", { class: "ck " + (c.ok ? "ok" : "bad") }, h("b", {}, (c.ok ? "\u2713 " : "\u26a0 ") + c.name), h("span", {}, c.detail)))));
        } catch (e) { fail(e); } } }, "Check and repair now");
      root.append(h("div", { class: "panel", style: "padding:.9rem;max-width:44rem" }, h("h3", { style: "margin-top:0" }, "Data Repair"), h("p", {}, "Like Tally's Rewrite / Repair: checks the data file for damage, confirms every voucher balances, rebuilds the search tables and compacts the file. If the file itself is damaged and cannot be fixed, HomeLedger restores the latest good backup when it starts."), run), out);
    } else if (tab === "tally") {
      const f = h("input", { type: "file", accept: ".xml,text/xml", "aria-label": "Tally XML file" }), res = h("div", {});
      const imp = h("button", { class: "btn primary", onclick: async () => {
        const file = f.files[0]; if (!file) { say("Choose an XML file first.", "err"); return; }
        if (!await confirmBox("Import from Tally XML", "Masters and vouchers in the file will be added to this company (a backup is taken first). Existing ledgers are not changed. Import a file only once.", "Import")) return;
        try { const r = await HL.post("/api/tallyxml/import", { xml: await file.text() }); await loadMasters();
          res.replaceChildren(h("div", { class: "banner " + (r.skipped.length || r.errors.length ? "warn" : "ok") }, `Added ${r.groups} groups, ${r.ledgers} ledgers, ${r.vouchers} vouchers.`),
            ...(r.skipped.concat(r.errors).length ? [h("p", { class: "hint" }, "Not imported:"), h("ul", {}, r.skipped.concat(r.errors).map(x => h("li", {}, x)))] : []));
        } catch (e) { fail(e); } } }, "Import");
      const P = getPeriod();
      root.append(h("div", { class: "panel", style: "padding:.9rem;max-width:44rem" }, h("h3", { style: "margin-top:0" }, "Export to Tally (XML)"), h("p", {}, "Groups, ledgers with opening balances, and posted vouchers for the current period (" + periodText() + ") in Tally's XML import format."),
        h("a", { class: "btn primary", href: "/api/tallyxml?from=" + P.from + "&to=" + P.to, download: "" }, "Download XML"),
        h("h3", {}, "Import from Tally (XML)"), h("p", {}, "Accepts masters (groups, ledgers) and accounting vouchers (Payment, Receipt, Contra, Journal, Sales, Purchase, notes). Inventory, GST and bill details in the file are ignored."), f, h("div", { style: "margin-top:.5rem" }, imp),
        h("p", { class: "hint" }, "The format follows Tally's published XML layout but has been checked only against HomeLedger's own files. Try a small file first and compare totals.")), res);
    } else if (tab === "export") {
      root.append(h("div", { class: "panel", style: "padding:.9rem;max-width:40rem" }, h("h3", { style: "margin-top:0" }, "Export everything to Excel"), h("p", {}, "Downloads one zip file with every entry, ledger, activity and the audit trail as spreadsheets (CSV) that open in Excel. This is a read-only copy for your own records and for sharing with an accountant; to protect your data use Backup."),
        h("a", { class: "btn primary", href: "/api/export", download: "" }, "Download export (zip)")));
    } else if (tab === "security") {
      await securityTab(root);
    } else if (tab === "settings") {
      const size = h("select", { "aria-label": "Text size" }, [["normal", "Normal"], ["large", "Large (default)"], ["xlarge", "Extra large"]].map(([v, l]) => h("option", { value: v }, l))); size.value = st.text_size;
      size.onchange = async () => { try { await HL.post("/api/settings/save", { text_size: size.value }); st.text_size = size.value; applySize(); say("Text size changed.", "ok"); } catch (e) { fail(e); } };
      const look = h("select", { "aria-label": "Look" }, h("option", { value: "prime" }, "TallyPrime style (clean, default)"), h("option", { value: "classic" }, "Classic (Tally ERP 9 style)")); look.value = st.look || "prime";
      look.onchange = async () => { try { await HL.post("/api/settings/save", { look: look.value }); st.look = look.value; HL.applyLook(look.value); say("Look changed.", "ok"); } catch (e) { fail(e); } };
      root.append(h("div", { class: "panel", style: "padding:.9rem;max-width:34rem" }, h("label", { class: "f" }, "Text size", size), h("label", { class: "f", style: "margin-top:.6rem" }, "Look", look), h("div", { class: "row", style: "margin-top:.8rem" }, h("button", { class: "btn", onclick: () => HL.go("company") }, "Company name and books beginning date")), h("p", { class: "muted" }, "Data folder: " + st.data_dir + " \u00b7 Version " + st.version)));
    } else {
      const r = await HL.get("/api/audit", { limit: 300 });
      const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["When", "What", "On", "Details"].map(x => h("th", {}, x)))));
      const tb = h("tbody", {}); t.append(tb);
      const pretty = x => { try { const o = JSON.parse(x.detail); if (o.after) return o.after.vtype + " no. " + o.after.number + " dated " + showDate(o.after.date) + ", " + rs(o.after.total_paise); if (o.vtype) return o.vtype + " no. " + o.number + " dated " + showDate(o.date) + ", " + rs(o.total); } catch (e) { } return x.detail; };
      r.rows.forEach(x => tb.append(h("tr", {}, h("td", {}, x.ts.slice(0, 16)), h("td", {}, x.action), h("td", {}, x.entity + (x.entity_id ? " #" + x.entity_id : "")), h("td", {}, pretty(x)))));
      root.append(h("p", { class: "sub" }, "A permanent log of every change (newest first). Entries are never silently removed."), h("div", { class: "scroll" }, t));
    }
    sc.replaceChildren(root); HL.setKeys([BACK]);
  },
};

/* ---------- quit ---------- */
HL.quit = async function () {
  if (!(await confirmBox("Close HomeLedger?", "Your data is saved. A backup will be made as the program closes.", "Yes, close"))) return;
  try { await HL.post("/api/quit"); } catch (e) { /* server may already be gone */ }
  HL._lost = true;
  document.body.innerHTML = '<div style="font-family:sans-serif;padding:3rem;text-align:center"><h2>HomeLedger has closed.</h2><p>Your data is saved and backed up. You can close this window.</p></div>';
  setTimeout(() => window.close(), 400);
};
function applySize() { document.body.className = "sz-" + ((HL.S.status && HL.S.status.text_size) || "large"); }


/* ---------- security tab ---------- */
async function securityTab(root) {
  const A = HL.auth;
  const done = async msg => { await HL.loadAuth(); await loadMasters(); say(msg, "ok"); HL.refresh(); };
  if (!A.enabled) {
    const un = h("input", { type: "text", autocomplete: "off", "aria-label": "User name", placeholder: "for example: father" });
    const p1 = h("input", { type: "password", autocomplete: "new-password", "aria-label": "Password or PIN" });
    const p2 = h("input", { type: "password", autocomplete: "new-password", "aria-label": "Password again" });
    root.append(h("div", { class: "panel", style: "padding:.9rem;max-width:40rem" }, h("h3", { style: "margin-top:0" }, "Sign-in is OFF"),
      h("p", {}, "Anyone who opens HomeLedger on this computer can see and change the accounts. You can ask for a user name and password (or a short PIN) every time it opens, and lock it when idle."),
      h("label", { class: "f" }, "Owner user name", un), h("label", { class: "f" }, "Password or PIN (at least 4 characters)", p1), h("label", { class: "f" }, "Type it again", p2),
      h("div", { class: "row", style: "margin-top:.6rem" }, h("button", { class: "btn primary", onclick: async () => {
        try {
          if (p1.value !== p2.value) throw new Error("The two passwords are not the same.");
          const r = await HL.post("/api/auth/enable", { username: un.value, password: p1.value });
          await HL.loadAuth(); await loadMasters(); HL.showNewKey(r.recovery_key, "Sign-in is now ON. This is your recovery key, for the day the password is forgotten."); HL.refresh();
        } catch (e) { fail(e); } } }, "Turn on sign-in")),
      h("p", { class: "hint" }, "Honest note: this keeps other people at the computer out of HomeLedger. To also protect the data file itself if the computer is lost or copied, turn on Windows BitLocker or use a Windows account password.")));
    return;
  }
  const idle = h("select", { "aria-label": "Lock after" }, A.choices.map(m => h("option", { value: m }, m === 0 ? "Never" : m + " minutes"))); idle.value = String(A.idle);
  const owner = A.role === "owner";
  root.append(h("div", { class: "panel", style: "padding:.9rem;max-width:44rem;margin-bottom:.8rem" }, h("h3", { style: "margin-top:0" }, "Sign-in is ON"),
    h("p", {}, "Signed in as ", h("b", {}, A.user), " (" + (owner ? "owner: can change everything" : "view only") + ")."),
    h("div", { class: "row" }, h("button", { class: "btn", onclick: HL.lockNow }, "Lock now (Ctrl+L)")),
    owner ? h("label", { class: "f", style: "margin-top:.7rem" }, "Lock automatically after no use for", idle) : ""));
  idle.onchange = async () => { try { await HL.post("/api/auth/idle", { minutes: +idle.value }); await done("Saved."); } catch (e) { fail(e); } };
  const o = h("input", { type: "password", autocomplete: "current-password", "aria-label": "Current password" }), n = h("input", { type: "password", autocomplete: "new-password", "aria-label": "New password" });
  root.append(h("div", { class: "panel", style: "padding:.9rem;max-width:44rem;margin-bottom:.8rem" }, h("h3", { style: "margin-top:0" }, "Change my password"),
    h("div", { class: "fgrid" }, h("label", { class: "f" }, "Current", o), h("label", { class: "f" }, "New", n)),
    h("div", { class: "row", style: "margin-top:.5rem" }, h("button", { class: "btn", onclick: async () => { try { await HL.post("/api/auth/password", { old: o.value, new: n.value }); o.value = n.value = ""; say("Password changed.", "ok"); } catch (e) { fail(e); } } }, "Change password"))));
  if (!owner) return;
  const us = await HL.get("/api/auth/users");
  const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["User", "Can", ""].map(x => h("th", {}, x))))); const tb = h("tbody", {}); t.append(tb);
  us.rows.forEach(u => tb.append(h("tr", {}, h("td", {}, u.username), h("td", {}, ({ owner: "Owner: everything", accountant: "Accountant: entries and masters", entry: "Data entry: vouchers only", viewer: "View only" })[u.role] || u.role),
    h("td", { class: "r" }, u.username.toLowerCase() === A.user.toLowerCase() ? "" : h("button", { class: "btn", onclick: async () => { if (await confirmBox("Remove " + u.username + "?", "They will no longer be able to sign in.", "Yes, remove", true)) { try { await HL.post("/api/auth/user/remove", { id: u.id }); await done("User removed."); } catch (e) { fail(e); } } } }, "Remove")))));
  const nu = h("input", { type: "text", autocomplete: "off", "aria-label": "New user name" }), np = h("input", { type: "password", autocomplete: "new-password", "aria-label": "New user password" });
  const role = h("select", { "aria-label": "Role" }, h("option", { value: "viewer" }, "View only (cannot change anything)"), h("option", { value: "entry" }, "Data entry (vouchers only)"), h("option", { value: "accountant" }, "Accountant (entries and masters; no security, restore or company changes)"), h("option", { value: "owner" }, "Owner (can change everything)"));
  root.append(h("div", { class: "panel", style: "padding:.9rem;max-width:44rem;margin-bottom:.8rem" }, h("h3", { style: "margin-top:0" }, "Users"), h("div", { class: "scroll" }, t),
    h("h4", {}, "Add a user"), h("div", { class: "fgrid" }, h("label", { class: "f" }, "User name", nu), h("label", { class: "f" }, "Password or PIN", np), h("label", { class: "f" }, "Can", role)),
    h("div", { class: "row", style: "margin-top:.5rem" }, h("button", { class: "btn", onclick: async () => { try { await HL.post("/api/auth/user/add", { username: nu.value, password: np.value, role: role.value }); await done("User added."); } catch (e) { fail(e); } } }, "Add user"))));
  const dp = h("input", { type: "password", autocomplete: "current-password", "aria-label": "Your password" });
  root.append(h("div", { class: "panel", style: "padding:.9rem;max-width:44rem" }, h("h3", { style: "margin-top:0" }, "Turn sign-in off"), h("label", { class: "f" }, "Type your password to confirm", dp),
    h("div", { class: "row", style: "margin-top:.5rem" }, h("button", { class: "btn", onclick: async () => { try { await HL.post("/api/auth/disable", { password: dp.value }); await done("Sign-in is off."); } catch (e) { fail(e); } } }, "Turn off sign-in"))));
}
