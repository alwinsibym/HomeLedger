/* Companies (F1): select, create, close, split / year-end close, merge */

const _coCall = async (path, body) => { try { return await HL.post(path, body); } catch (e) { fail(e); return null; } };
const _afterSwitch = () => { try { sessionStorage.clear(); } catch (e) { } location.reload(); };

HL.screens.companies = {
  title: "Select Company",
  async render(sc) {
    await loadMasters();
    const r = await HL.get("/api/companies");
    const cur = r.companies.find(c => c.current) || r.companies[0];
    const [t, tb] = _tbl(["Company", "Books begin", "Size", ""]);
    r.companies.forEach(c => {
      const tr = h("tr", { class: "row", tabindex: "0", onclick: () => open(c) },
        h("td", {}, c.name + (c.current ? "  (open)" : "")), h("td", { class: "r" }, c.books_begin ? showDate(c.books_begin) : ""),
        h("td", { class: "r" }, (c.size / 1048576).toFixed(1) + " MB"),
        h("td", { class: "r" }, c.id === "main" || c.current ? "" : h("button", { class: "btn", type: "button", onclick: e => { e.stopPropagation(); unlist(c); } }, "Remove from list")));
      tr.dataset.id = c.id; rowKeys(tr); tb.append(tr);
    });
    async function open(c) {
      if (c.current) { HL.go("gateway"); return; }
      if (await _coCall("/api/companies/open", { id: c.id })) _afterSwitch();
    }
    async function unlist(c) {
      if (!await confirmBox("Remove from list", `Take "${c.name}" off the list? Its data file is NOT deleted; it stays in the companies folder.`, "Remove")) return;
      if (await _coCall("/api/companies/remove", { id: c.id })) HL.refresh();
    }
    function create() {
      const nm = h("input", { type: "text", maxlength: "80", "aria-label": "Name" });
      const bb = h("input", { type: "text", value: "01-04-" + (new Date().getMonth() >= 3 ? new Date().getFullYear() : new Date().getFullYear() - 1), "aria-label": "Books beginning" });
      modal({ title: "Create company", body: h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f" }, "Name of the company", nm), h("label", { class: "f" }, "Books beginning from", bb)),
        buttons: [{ label: "Cancel", onclick: m => m.close() }, { label: "Create and open", cls: "primary", onclick: async m => {
          const iso = parseDateInput(bb.value, todayIso()); if (!iso) { say("Please type the date like 01-04-2026.", "err"); return; }
          if (await _coCall("/api/companies/create", { name: nm.value, books_begin: iso, open: 1 })) { m.close(); _afterSwitch(); } } }] });
    }
    function carry(yearEnd) {
      const nx = (() => { const d = new Date(); const y = d.getMonth() >= 3 ? d.getFullYear() : d.getFullYear() - 1; return "01-04-" + y; })();
      const cut = h("input", { type: "text", value: nx, "aria-label": "New books beginning" });
      const nm = h("input", { type: "text", value: cur.name + (yearEnd ? " (next year)" : " (from here)"), maxlength: "80", "aria-label": "Name" });
      modal({ title: yearEnd ? "Year-end close" : "Split company", wide: true,
        body: h("div", {}, h("p", { class: "hint" }, "A NEW company is created that begins on the date below. Balance-sheet ledgers start with their closing balances, earlier profit or loss is carried into 'Profit & Loss A/c (carried forward)', and stock starts with its closing quantity and value. Entries from that date onward are copied. Your present company is not changed, and a backup is taken first. Open bills of parties are carried as one opening balance per party."),
          h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f" }, "New books begin on", cut), h("label", { class: "f" }, "Name of the new company", nm))),
        buttons: [{ label: "Cancel", onclick: m => m.close() }, { label: "Create new company", cls: "primary", onclick: async m => {
          const iso = parseDateInput(cut.value, todayIso()); if (!iso) { say("Please type the date like 01-04-2026.", "err"); return; }
          const res = await _coCall("/api/companies/carry", { cutoff: iso, name: nm.value, open: 0 }); if (!res) return;
          m.close(); say("New company created." + (res.pending ? ` ${res.pending} memo/optional voucher(s) before that date were not carried.` : ""), "ok"); HL.refresh(); } }] });
    }
    function merge() {
      const others = r.companies.filter(c => !c.current);
      if (!others.length) { say("There is no other company to merge from. Create or split one first.", "err"); return; }
      const sel = h("select", { "aria-label": "Company" }, others.map(c => h("option", { value: c.id }, c.name)));
      modal({ title: "Merge data into " + cur.name, body: h("div", {}, h("p", { class: "hint" }, "Copies the entries of the chosen company into the open one. Ledgers, groups, cost centres and stock items are matched by name and added when missing; entries dated before this company's books begin are skipped. A backup is taken first. Merge only once: doing it twice copies the entries twice."), h("label", { class: "f" }, "Merge from", sel)),
        buttons: [{ label: "Cancel", onclick: m => m.close() }, { label: "Merge", cls: "primary", onclick: async m => {
          const res = await _coCall("/api/companies/merge", { id: sel.value }); if (!res) return;
          m.close(); say(`Merged: ${res.vouchers} entries, ${res.ledgers} new ledgers, ${res.items} new items` + (res.skipped ? `; ${res.skipped} skipped (before books begin).` : "."), "ok"); await loadMasters(); } }] });
    }
    sc.replaceChildren(_page("Select Company", "Enter opens the company · the open one is marked", t,
      h("div", { class: "row", style: "margin-top:.8rem;gap:.5rem;flex-wrap:wrap" },
        h("button", { class: "btn", onclick: create }, "Create company (Alt+C)"), h("button", { class: "btn", onclick: () => carry(false) }, "Split company (Alt+S)"),
        h("button", { class: "btn", onclick: () => carry(true) }, "Year-end close (Alt+Y)"), h("button", { class: "btn", onclick: merge }, "Merge data (Alt+M)"),
        h("button", { class: "btn", onclick: () => HL.go("gateway") }, "Shut: back to Gateway (Esc)"))));
    HL.setKeys([BACK, { k: "Alt+C", label: "Create", fn: create }, { k: "Alt+S", label: "Split", fn: () => carry(false) }, { k: "Alt+Y", label: "Year-end close", fn: () => carry(true) }, { k: "Alt+M", label: "Merge", fn: merge }]);
    const f = $("tbody tr.row", sc); f && f.focus();
  },
};
