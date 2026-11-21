/* Inventory: item lines in vouchers, stock-only vouchers, stock masters, godowns, batches, price lists, BOM, stock reports */

HL.stock = {
  lists: null, items: [],
  async load() { const [l, i] = await Promise.all([HL.get("/api/stocklists"), HL.get("/api/stockitems")]); this.lists = l; this.items = i; },
  itemOptions() { return this.items.map(i => ({ value: i.id, label: i.name, hint: i.unit, data: i })); },
  godownSel(v) { const s = h("select", { "aria-label": "Godown" }, this.lists.godowns.map(g => h("option", { value: g.id }, g.name))); s.value = String(v || 1); return s; },
};
const STOCK_ONLY_TYPES = ["Sales Order", "Purchase Order", "Delivery Note", "Receipt Note", "Stock Journal"];
const ITEM_TYPES = ["Sales", "Purchase", "Credit Note", "Debit Note"].concat(STOCK_ONLY_TYPES);
const _money = v => (v / 100).toFixed(2);
const _num = v => (v / 1000).toString();

/* The item table used inside Sales/Purchase/... and by the stock-only vouchers */
HL.itemsTable = function (opts) {
  const { vtype, getDate, level } = opts;
  const sj = vtype === "Stock Journal";
  const rows = [];
  const tb = h("tbody", {});
  const heads = (sj ? ["Movement"] : []).concat(["Item", sj ? "From godown" : "Godown"]).concat(sj ? ["To godown"] : []).concat(["Batch", "Expiry", "Qty", "Rate", "Amount"]).concat(vtype.includes("Order") || vtype.includes("Note") ? ["Order no."] : []);
  const t = h("table", { class: "tbl items" }, h("thead", {}, h("tr", {}, heads.map(x => h("th", {}, x)).concat(h("th", {})))), tb);
  const sum = h("span", { class: "total-amt" });
  const calc = () => { let q = 0; rows.forEach(r => { q += parseFloat(r.amt.value.replace(/,/g, "")) || 0; }); sum.textContent = "Items total: " + inr(Math.round(q * 100)); };
  function add(x) {
    x = x || {};
    const r = {};
    r.kind = sj ? h("select", { "aria-label": "Movement" }, [["transfer", "Transfer"], ["consume", "Consumed"], ["produce", "Produced"]].map(([v, l]) => h("option", { value: v }, l))) : null;
    if (r.kind) r.kind.value = x.kind || "transfer";
    r.item = picker({ options: () => HL.stock.itemOptions(), value: x.item_id || null, placeholder: "Item", width: "9rem",
      onpick: async o => { if (o && !r.rate.value) { try { const p = await HL.get("/api/price", { item_id: o.value, level: level || "Standard", on: getDate() }); if (p.rate_paise) r.rate.value = _money(p.rate_paise); } catch (e) { } } r.upd(); } });
    r.gf = HL.stock.godownSel(x.godown_id); r.gt = sj ? HL.stock.godownSel(x.godown_to_id) : null;
    r.batch = h("input", { type: "text", value: x.batch || "", maxlength: "30", style: "width:6rem", "aria-label": "Batch" });
    r.exp = h("input", { type: "text", value: x.expiry ? showDate(x.expiry) : "", placeholder: "dd-mm-yyyy", style: "width:6.8rem", "aria-label": "Expiry" });
    r.qty = h("input", { type: "text", inputmode: "decimal", value: x.qty_milli ? _num(x.qty_milli) : "", style: "width:4.6rem;text-align:right", "aria-label": "Quantity" });
    r.rate = h("input", { type: "text", inputmode: "decimal", value: x.rate_paise ? _money(x.rate_paise) : "", style: "width:5rem;text-align:right", "aria-label": "Rate" });
    r.amt = h("input", { type: "text", inputmode: "decimal", value: x.amount_paise ? _money(x.amount_paise) : "", style: "width:6rem;text-align:right", "aria-label": "Amount" });
    r.ord = vtype.includes("Order") || vtype.includes("Note") ? h("input", { type: "text", value: x.order_ref || "", style: "width:5rem", "aria-label": "Order number" }) : null;
    r.upd = () => { const q = parseFloat(r.qty.value.replace(/,/g, "")), rt = parseFloat(r.rate.value.replace(/,/g, "")); if (q > 0 && rt >= 0 && r.rate.value) r.amt.value = (Math.round(q * rt * 100) / 100).toFixed(2); calc(); opts.onchange && opts.onchange(); };
    r.qty.addEventListener("input", r.upd); r.rate.addEventListener("input", r.upd); r.amt.addEventListener("input", () => { calc(); opts.onchange && opts.onchange(); });
    const unit = h("small", { class: "muted" }, "");
    const del = h("button", { class: "btn stop", type: "button", tabindex: "-1", onclick: () => { r.tr.remove(); rows.splice(rows.indexOf(r), 1); calc(); opts.onchange && opts.onchange(); } }, "×");
    const cells = [r.kind, h("div", {}, r.item.el), r.gf, r.gt, r.batch, r.exp, h("div", {}, r.qty), r.rate, r.amt, r.ord].filter(Boolean).map(c => h("td", {}, c));
    r.tr = h("tr", {}, ...cells, h("td", {}, del));
    if (r.kind) r.kind.onchange = () => { const c = r.kind.value; r.gt.style.display = c === "transfer" ? "" : "none"; };
    if (r.kind) r.kind.onchange();
    if (x.item_id) r.item.set(x.item_id);
    rows.push(r); tb.append(r.tr); calc();
    return r;
  }
  const addBtn = h("button", { class: "btn", type: "button", onclick: () => add().item.focus() }, "+ Add an item");
  const el = h("div", { class: "itemsbox" }, h("div", { style: "overflow-x:auto" }, t), h("div", { class: "row", style: "gap:1rem;align-items:center;margin-top:.4rem" }, addBtn, opts.extra || null, sum));
  (opts.items && opts.items.length ? opts.items : [{}]).forEach(add);
  return {
    el, add, total() { return rows.reduce((q, r) => q + (Math.round((parseFloat(r.amt.value.replace(/,/g, "")) || 0) * 100)), 0); },
    clear() { rows.splice(0).forEach(r => r.tr.remove()); },
    get() {
      return rows.filter(r => r.item.value).map(r => ({
        item_id: r.item.value, godown_id: +r.gf.value, godown_to_id: r.gt ? +r.gt.value : undefined, kind: r.kind ? r.kind.value : undefined, batch: r.batch.value, qty: r.qty.value, rate: r.rate.value, amount: r.amt.value,
        expiry: r.exp.value.trim() ? (parseDateInput(r.exp.value, getDate()) || (() => { throw new Error("Please type the expiry date like 31-12-2026."); })()) : null, order_ref: r.ord ? r.ord.value : "",
      }));
    },
  };
};

/* Vouchers that carry only stock: orders, delivery/receipt notes, stock journal */
HL.screens.stockvoucher = {
  title: p => (p.id ? "Alter " : "") + p.vtype,
  async render(sc, params, v) {
    await Promise.all([loadMasters(), HL.stock.load()]);
    const vtype = params.vtype;
    const S = { dirty: false };
    const date = h("input", { type: "text", value: showDate(v ? v.date : todayIso()), style: "width:9rem", "aria-label": "Date" });
    const ref = h("input", { type: "text", value: v ? v.ref || "" : "", maxlength: "60", style: "width:12rem", "aria-label": "Reference" });
    const narr = h("textarea", { rows: 2, maxlength: "500", placeholder: "Narration: a short note about this entry", "aria-label": "Narration" }, v ? v.narration || "" : "");
    const dateIso = () => parseDateInput(date.value, todayIso()) || todayIso();
    let bomSel = null;
    const boms = vtype === "Stock Journal" ? await HL.get("/api/boms") : [];
    let table;
    const extra = vtype === "Stock Journal" && boms.length ? (() => {
      bomSel = h("select", { "aria-label": "Bill of material" }, boms.map(b => h("option", { value: b.id }, b.product + " (" + b.name + ")")));
      const mult = h("input", { type: "text", value: "1", style: "width:4rem", "aria-label": "Batches" });
      return h("span", { class: "row", style: "gap:.4rem;align-items:center" }, h("small", {}, "Make from"), bomSel, h("small", {}, "× batches"), mult,
        h("button", { class: "btn", type: "button", onclick: () => { const b = boms.find(x => x.id === +bomSel.value), n = parseFloat(mult.value) || 1; if (!b) return; table.clear(); b.lines.forEach(l => table.add({ kind: "consume", item_id: l.item_id, qty_milli: Math.round(l.qty_milli * n) })); table.add({ kind: "produce", item_id: b.product_id, qty_milli: Math.round(b.out_qty_milli * n) }); } }, "Fill lines"));
    })() : null;
    table = HL.itemsTable({ vtype, getDate: dateIso, items: v ? v.items.filter(i => i.kind !== "transfer" || i.dir === "out").map(i => Object.assign({}, i, i.kind === "transfer" ? { godown_to_id: (v.items.find(j => j.kind === "transfer" && j.dir === "in" && j.item_id === i.item_id && j.qty_milli === i.qty_milli) || {}).godown_id } : {})) : [], extra, onchange: () => { S.dirty = true; } });
    [date, ref, narr].forEach(x => x.addEventListener("input", () => { S.dirty = true; }));
    const hints = { "Sales Order": "An order received from a customer. It does not change stock or accounts. Use the order number on the delivery or sale to tick it off.", "Purchase Order": "An order you have placed. It does not change stock or accounts.",
      "Delivery Note": "Goods sent out. Reduces stock only, with no accounts entry. Put the order number if it is against an order.", "Receipt Note": "Goods received. Increases stock only, with no accounts entry.",
      "Stock Journal": "Move stock between godowns, or make a product from its components (Consumed lines use up stock; Produced lines create it, costed from what was consumed)." };
    async function save() {
      try {
        const items = table.get();
        if (!items.length) { say("Add at least one item.", "err"); return; }
        const d = parseDateInput(date.value, todayIso()); if (!d) { say("Please type the date like 15-11-2026.", "err"); return; }
        const r = await HL.post("/api/voucher/save", { id: v ? v.id : undefined, vtype, date: d, ref: ref.value, narration: narr.value, items });
        S.dirty = false; say(vtype + " " + r.number + " saved.", "ok");
        if (v) HL.back(); else HL.go("voucher", { vtype }, { replace: true });
      } catch (e) { fail(e); }
    }
    sc.replaceChildren(h("div", { class: "panel" }, h("div", { class: "row", style: "gap:1rem;align-items:flex-end;flex-wrap:wrap" }, h("span", { class: "vt" }, vtype), h("label", { class: "f" }, "Date", date), h("label", { class: "f" }, "Reference", ref)),
      h("p", { class: "hint" }, hints[vtype]), table.el, h("label", { class: "f", style: "margin-top:.8rem" }, "Narration", narr)));
    const keys = [{ k: "Ctrl+A", label: "Accept (save)", fn: save }, { k: "Esc", label: "Back", fn: () => HL.back() }];
    if (v) {
      keys.push({ k: "Alt+D", label: "Delete", fn: async () => { if (await confirmBox("Delete this voucher?", "It is removed for good (a copy is kept in the audit log).", "Yes, delete it", true)) { try { await HL.post("/api/voucher/delete", { id: v.id }); S.dirty = false; HL.back(); } catch (e) { fail(e); } } } });
      keys.push({ k: "Alt+X", label: "Cancel", fn: async () => { if (await confirmBox("Cancel this voucher?", "Its stock movement stops counting.", "Yes, cancel it", true)) { try { await HL.post("/api/voucher/status", { id: v.id, status: "cancelled" }); S.dirty = false; HL.back(); } catch (e) { fail(e); } } } });
    }
    HL.setKeys(keys);
    HL.cur.guard = () => !S.dirty || confirm("Leave without saving?");
    HL.onKey = e => { if ((e.ctrlKey && e.key.toLowerCase() === "a") || (e.ctrlKey && e.key === "Enter")) { e.preventDefault(); save(); return true; } };
  },
};

/* Stock masters */
function _masterList(id, title, table, saveUrl, blurb) {
  HL.screens[id] = {
    title,
    async render(sc) {
      await HL.stock.load();
      const list = HL.stock.lists[table];
      const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, h("th", {}, "Name"), h("th", {}, "Under"))));
      const tb = h("tbody", {}); t.append(tb);
      const nm = Object.fromEntries(list.map(x => [x.id, x.name]));
      const edit = x => {
        const n = h("input", { type: "text", value: x ? x.name : "", maxlength: "60", "aria-label": "Name" });
        const par = h("select", { "aria-label": "Under" }, h("option", { value: "" }, "(Primary)"), list.filter(y => !x || y.id !== x.id).map(y => h("option", { value: y.id }, y.name))); par.value = x && x.parent_id ? String(x.parent_id) : "";
        const body = h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f" }, "Name", n), h("label", { class: "f" }, "Under", par));
        const m = modal({ title: title.replace(/s$/, "") + (x ? " Alteration" : " Creation"), body, buttons: [x && !(table === "godowns" && x.id === 1) ? { label: "Delete", cls: "danger", onclick: async m2 => { if (await confirmBox("Delete?", "Only unused ones can be deleted.", "Delete", true)) { try { await HL.post("/api/stockmaster/delete", { table: { groups: "stock_groups", categories: "stock_categories", godowns: "godowns" }[table], id: x.id }); m2.close(); HL.refresh(); } catch (e) { fail(e); } } } } : null, { label: "Cancel", onclick: m => m.close() }, { label: "Accept", cls: "primary", onclick: save }].filter(Boolean) });
        enterAsTab(body, save);
        async function save() { try { await HL.post(saveUrl, { id: x && x.id, name: n.value, parent_id: par.value }); m.close(); HL.refresh(); } catch (e) { fail(e); } }
      };
      list.forEach(x => { const tr = h("tr", { class: "row", tabindex: "0", onclick: () => edit(x) }, h("td", {}, x.name), h("td", {}, x.parent_id ? nm[x.parent_id] : "(Primary)")); rowKeys(tr); tb.append(tr); });
      if (!list.length) tb.append(h("tr", {}, h("td", { colspan: 2, class: "empty" }, "None yet. Press Alt+C to create one.")));
      sc.replaceChildren(h("div", {}, h("h1", { class: "title" }, title), h("p", { class: "sub" }, blurb), t));
      HL.setKeys([BACK, { k: "Alt+C", label: "Create", fn: () => edit(null) }]);
      const f = $("tbody tr.row", sc); f && f.focus();
    },
  };
}
_masterList("stockgroups", "Stock Groups", "groups", "/api/stockgroup/save", "Group your items, for example Fertilisers, Feed, Tools.");
_masterList("stockcategories", "Stock Categories", "categories", "/api/stockcategory/save", "A second way to classify items that cuts across groups.");
_masterList("godowns", "Godowns", "godowns", "/api/godown/save", "Places where stock is kept. Stock Journal moves goods between them.");

HL.screens.stockitems = {
  title: "Stock Items",
  async render(sc, params) {
    await HL.stock.load();
    const items = HL.stock.items, L = HL.stock.lists;
    const root = h("div", {}, h("h1", { class: "title" }, "Stock Items"), h("p", { class: "sub" }, "Things you buy and sell by quantity. Create stock groups, categories and godowns from the Masters menu."));
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Name", "Group", "Unit", "Valuation", "Opening qty", "Opening value"].map((x, i) => h("th", { class: i > 3 ? "r" : "" }, x)))));
    const tb = h("tbody", {}); t.append(tb);
    const gname = Object.fromEntries(L.groups.map(g => [g.id, g.name]));
    const edit = it => {
      const f = (label, el) => h("label", { class: "f" }, label, el);
      const nm = h("input", { type: "text", value: it ? it.name : "", maxlength: "60" }), un = h("input", { type: "text", value: it ? it.unit : "", maxlength: "12", placeholder: "kg, nos, litre..." });
      const gr = h("select", {}, h("option", { value: "" }, "(None)"), L.groups.map(g => h("option", { value: g.id }, g.name))); gr.value = it && it.group_id ? String(it.group_id) : "";
      const ca = h("select", {}, h("option", { value: "" }, "(None)"), L.categories.map(g => h("option", { value: g.id }, g.name))); ca.value = it && it.category_id ? String(it.category_id) : "";
      const va = h("select", {}, Object.entries(L.valuations).map(([k, v]) => h("option", { value: k }, v))); va.value = it ? it.valuation : "avg";
      const sr = h("input", { type: "text", inputmode: "decimal", value: it && it.std_rate_paise ? _money(it.std_rate_paise) : "" });
      const bt = h("input", { type: "checkbox", checked: !!(it && it.track_batches) });
      const oq = h("input", { type: "text", inputmode: "decimal", value: it && it.opening_qty_milli ? _num(it.opening_qty_milli) : "" }), ov = h("input", { type: "text", inputmode: "decimal", value: it && it.opening_value_paise ? _money(it.opening_value_paise) : "" });
      const body = h("div", { class: "fgrid", style: "grid-template-columns:1fr 1fr;gap:.6rem 1rem" }, f("Name", nm), f("Unit", un), f("Stock group", gr), f("Stock category", ca), f("Valuation method", va), f("Standard rate (₹, for standard cost)", sr),
        f("Opening quantity", oq), f("Opening value (₹)", ov), h("label", { class: "f", style: "flex-direction:row;gap:.4rem;align-items:center" }, bt, "Track by batch and expiry"));
      const m = modal({ title: it ? "Stock Item Alteration" : "Stock Item Creation", body, wide: true, buttons: [it ? { label: "Delete", cls: "danger", onclick: async m2 => { if (await confirmBox("Delete stock item?", "Only items never used in a voucher can be deleted.", "Delete", true)) { try { await HL.post("/api/stockitem/delete", { id: it.id }); m2.close(); HL.refresh(); } catch (e) { fail(e); } } } } : null, { label: "Cancel", onclick: m => m.close() }, { label: "Accept", cls: "primary", onclick: save }].filter(Boolean) });
      async function save() { try { await HL.post("/api/stockitem/save", { id: it && it.id, name: nm.value, unit: un.value, group_id: gr.value, category_id: ca.value, valuation: va.value, std_rate: sr.value, track_batches: bt.checked, opening_qty: oq.value, opening_value: ov.value }); m.close(); HL.refresh(); } catch (e) { fail(e); } }
    };
    items.forEach(it => { const tr = h("tr", { class: "row", tabindex: "0", onclick: () => edit(it) }, h("td", {}, it.name), h("td", {}, it.group_id ? gname[it.group_id] : ""), h("td", {}, it.unit), h("td", {}, L.valuations[it.valuation].split(" (")[0]), h("td", { class: "r" }, it.opening_qty_milli ? qtyStr(it.opening_qty_milli) : ""), h("td", { class: "r" }, it.opening_value_paise ? inr(it.opening_value_paise) : "")); rowKeys(tr); tb.append(tr); });
    if (!items.length) tb.append(h("tr", {}, h("td", { colspan: 6, class: "empty" }, "No stock items yet. Press Alt+C to create one.")));
    root.append(t); sc.replaceChildren(root);
    HL.setKeys([BACK, { k: "Alt+C", label: "Create stock item", fn: () => edit(null) }]);
    const first = $("tbody tr.row", root); first && first.focus();
    if (params.create) { params.create = 0; setTimeout(() => edit(null), 60); }
  },
};

/* Reports */
HL.screens.stocksummary = {
  title: "Stock Summary",
  async render(sc) {
    await loadMasters();
    const P = getPeriod();
    const r = await HL.get("/api/stocksummary", { from: P.from, to: P.to });
    const q = v => v ? qtyStr(v) : "";
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Item", "Unit", "Opening", "Inwards", "Outwards", "Closing qty", "Rate", "Closing value"].map((x, i) => h("th", { class: i > 1 ? "r" : "" }, x)))));
    const tb = h("tbody", {}); t.append(tb);
    r.rows.forEach(x => { const tr = h("tr", { class: "row", tabindex: "0", onclick: () => HL.go("commodity", { item: x.name, unit: x.unit }) }, h("td", {}, x.name), h("td", {}, x.unit),
      h("td", { class: "r" }, q(x.op_q)), h("td", { class: "r" }, q(x.in_q)), h("td", { class: "r" }, q(x.out_q)), h("td", { class: "r", style: x.close_q < 0 ? "color:#b3261e" : "" }, q(x.close_q)),
      h("td", { class: "r" }, x.close_q > 0 && x.close_v ? inr(Math.round(x.close_v * 1000 / x.close_q)) : ""), h("td", { class: "r" }, x.close_v ? inr(x.close_v) : "")); rowKeys(tr); tb.append(tr); });
    if (!r.rows.length) tb.append(h("tr", {}, h("td", { colspan: 8, class: "empty" }, "No stock yet. Create stock items, then buy or sell them with the item list in a voucher.")));
    else tb.append(h("tr", { class: "total" }, h("td", {}, "Total"), ...[1, 2, 3, 4, 5, 6].map(() => h("td", {})), h("td", { class: "r" }, inr(r.total_value))));
    sc.replaceChildren(h("div", {}, h("h1", { class: "title" }, "Stock Summary"), h("p", { class: "sub" }, periodText() + " · each item is valued by its own method (set on the item)"), periodBar(() => HL.refresh()), t, h("p", { class: "hint" }, r.note)));
    HL.setKeys([BACK]);
    const f = $("tbody tr.row", sc); f && f.focus();
  },
};

HL.screens.godownsummary = {
  title: "Godown Summary",
  async render(sc) {
    await loadMasters();
    const P = getPeriod();
    const rows = await HL.get("/api/godownsummary", { to: P.to });
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Godown", "Item", "Unit", "Quantity", "Value"].map((x, i) => h("th", { class: i > 2 ? "r" : "" }, x)))));
    const tb = h("tbody", {}); t.append(tb);
    rows.forEach(x => tb.append(h("tr", {}, h("td", {}, x.godown), h("td", {}, x.item), h("td", {}, x.unit), h("td", { class: "r" }, qtyStr(x.qty)), h("td", { class: "r" }, x.value ? inr(x.value) : ""))));
    if (!rows.length) tb.append(h("tr", {}, h("td", { colspan: 5, class: "empty" }, "No stock in any godown yet.")));
    sc.replaceChildren(h("div", {}, h("h1", { class: "title" }, "Godown Summary"), h("p", { class: "sub" }, "Stock in each place as on " + showDate(P.to)), periodBar(() => HL.refresh()), t));
    HL.setKeys([BACK]);
  },
};

HL.screens.batchsummary = {
  title: "Batches and Expiry",
  async render(sc) {
    await loadMasters();
    const P = getPeriod();
    const rows = await HL.get("/api/batches", { to: P.to });
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Item", "Batch", "Quantity", "Expiry", "Days left"].map((x, i) => h("th", { class: i === 2 || i === 4 ? "r" : "" }, x)))));
    const tb = h("tbody", {}); t.append(tb);
    rows.forEach(x => tb.append(h("tr", { style: x.days_left !== null && x.days_left < 0 ? "color:#b3261e" : x.days_left !== null && x.days_left <= 30 ? "color:#a15c00" : "" }, h("td", {}, x.item), h("td", {}, x.batch), h("td", { class: "r" }, qtyStr(x.qty) + " " + x.unit), h("td", {}, x.expiry ? showDate(x.expiry) : ""), h("td", { class: "r" }, x.days_left === null ? "" : x.days_left < 0 ? "Expired" : x.days_left))));
    if (!rows.length) tb.append(h("tr", {}, h("td", { colspan: 5, class: "empty" }, "No batches. Switch on 'Track by batch and expiry' on an item, then enter batches when buying.")));
    sc.replaceChildren(h("div", {}, h("h1", { class: "title" }, "Batches and Expiry"), h("p", { class: "sub" }, "Soonest expiry first. Red = expired, orange = expires within 30 days"), periodBar(() => HL.refresh()), t));
    HL.setKeys([BACK]);
  },
};

HL.screens.pendingorders = {
  title: "Pending Orders",
  async render(sc) {
    await loadMasters();
    const rows = await HL.get("/api/pendingorders");
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Date", "Order", "No.", "Item", "Ordered", "Done", "Pending"].map((x, i) => h("th", { class: i > 3 ? "r" : "" }, x)))));
    const tb = h("tbody", {}); t.append(tb);
    rows.forEach(x => { const tr = h("tr", { class: "row", tabindex: "0", onclick: () => HL.go("voucher", { id: x.voucher_id }) }, h("td", {}, showDate(x.date)), h("td", {}, x.vtype), h("td", {}, x.order_no), h("td", {}, x.item), h("td", { class: "r" }, qtyStr(x.ordered)), h("td", { class: "r" }, qtyStr(x.done)), h("td", { class: "r" }, qtyStr(x.pending) + " " + x.unit)); rowKeys(tr); tb.append(tr); });
    if (!rows.length) tb.append(h("tr", {}, h("td", { colspan: 7, class: "empty" }, "No pending orders.")));
    sc.replaceChildren(h("div", {}, h("h1", { class: "title" }, "Pending Orders"), h("p", { class: "sub" }, "Orders not yet fully delivered or received. Put the order number on the Delivery Note, Receipt Note or invoice line to tick it off."), t));
    HL.setKeys([BACK]);
  },
};

HL.screens.prices = {
  title: "Price Lists",
  async render(sc) {
    await HL.stock.load();
    const rows = await HL.get("/api/prices");
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Price level", "Item", "From", "Rate"].map((x, i) => h("th", { class: i === 3 ? "r" : "" }, x)))));
    const tb = h("tbody", {}); t.append(tb);
    const edit = x => {
      const lv = h("input", { type: "text", value: x ? x.level : "Standard", maxlength: "30", list: "dl-levels" });
      const dl = h("datalist", { id: "dl-levels" }, [...new Set(rows.map(r => r.level))].map(l => h("option", { value: l })));
      const it = picker({ options: () => HL.stock.itemOptions(), value: x ? x.item_id : null, placeholder: "Item" });
      const fd = h("input", { type: "text", value: showDate(x ? x.from_date : todayIso()), "aria-label": "From date" });
      const rt = h("input", { type: "text", inputmode: "decimal", value: x ? _money(x.rate_paise) : "", "aria-label": "Rate" });
      const body = h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, dl, h("label", { class: "f" }, "Price level (e.g. Standard, Retail, Wholesale)", lv), h("label", { class: "f" }, "Item", it.el), h("label", { class: "f" }, "Applies from", fd), h("label", { class: "f" }, "Rate per unit (₹); 0 removes this entry", rt));
      const m = modal({ title: "Price", body, buttons: [{ label: "Cancel", onclick: m => m.close() }, { label: "Accept", cls: "primary", onclick: async () => { try { const d = parseDateInput(fd.value, todayIso()); if (!d) { say("Please type the date like 15-11-2026.", "err"); return; } await HL.post("/api/price/set", { level: lv.value, item_id: it.value, from_date: d, rate: rt.value }); m.close(); HL.refresh(); } catch (e) { fail(e); } } }] });
    };
    rows.forEach(x => { const tr = h("tr", { class: "row", tabindex: "0", onclick: () => edit(x) }, h("td", {}, x.level), h("td", {}, x.item), h("td", {}, showDate(x.from_date)), h("td", { class: "r" }, inr(x.rate_paise) + " / " + x.unit)); rowKeys(tr); tb.append(tr); });
    if (!rows.length) tb.append(h("tr", {}, h("td", { colspan: 4, class: "empty" }, "No prices yet. Press Alt+C to add one. A price fills the Rate when you pick that item in a voucher.")));
    sc.replaceChildren(h("div", {}, h("h1", { class: "title" }, "Price Lists"), h("p", { class: "sub" }, "Selling or buying rates by price level and date"), t));
    HL.setKeys([BACK, { k: "Alt+C", label: "Add a price", fn: () => edit(null) }]);
    const f = $("tbody tr.row", sc); f && f.focus();
  },
};

HL.screens.boms = {
  title: "Bills of Material",
  async render(sc) {
    await HL.stock.load();
    const list = await HL.get("/api/boms");
    const t = h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Product", "Name", "Makes", "Made from"].map(x => h("th", {}, x)))));
    const tb = h("tbody", {}); t.append(tb);
    const edit = b => {
      const prod = picker({ options: () => HL.stock.itemOptions(), value: b ? b.product_id : null, placeholder: "Finished product" });
      const nm = h("input", { type: "text", value: b ? b.name : "Standard", maxlength: "40" }), oq = h("input", { type: "text", value: b ? _num(b.out_qty_milli) : "1", style: "width:6rem" });
      const lines = []; const lb = h("div", {});
      const addLine = l => { const it = picker({ options: () => HL.stock.itemOptions(), value: l ? l.item_id : null, placeholder: "Component", width: "14rem" }), q = h("input", { type: "text", value: l ? _num(l.qty_milli) : "", style: "width:6rem", placeholder: "Qty" }); const row = h("div", { class: "row", style: "gap:.5rem;margin:.2rem 0" }, it.el, q); const o = { it, q, row }; lines.push(o); lb.append(row); };
      (b ? b.lines : [null, null]).forEach(addLine);
      const body = h("div", {}, h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f" }, "Finished product", prod.el), h("label", { class: "f" }, "Name of this recipe", nm), h("label", { class: "f" }, "Quantity one batch makes", oq)), h("h4", {}, "Components for one batch"), lb, h("button", { class: "btn", type: "button", onclick: () => addLine(null) }, "+ Add component"));
      const m = modal({ title: "Bill of Material", body, wide: true, buttons: [b ? { label: "Delete", cls: "danger", onclick: async m2 => { if (await confirmBox("Delete this bill of material?", "", "Delete", true)) { try { await HL.post("/api/bom/delete", { id: b.id }); m2.close(); HL.refresh(); } catch (e) { fail(e); } } } } : null, { label: "Cancel", onclick: m => m.close() }, { label: "Accept", cls: "primary", onclick: async () => { try { await HL.post("/api/bom/save", { product_id: prod.value, name: nm.value, out_qty: oq.value, lines: lines.filter(l => l.it.value).map(l => ({ item_id: l.it.value, qty: l.q.value })) }); m.close(); HL.refresh(); } catch (e) { fail(e); } } }].filter(Boolean) });
    };
    list.forEach(b => { const tr = h("tr", { class: "row", tabindex: "0", onclick: () => edit(b) }, h("td", {}, b.product), h("td", {}, b.name), h("td", {}, qtyStr(b.out_qty_milli) + " " + b.unit), h("td", {}, b.lines.map(l => qtyStr(l.qty_milli) + " " + l.unit + " " + l.item).join(", "))); rowKeys(tr); tb.append(tr); });
    if (!list.length) tb.append(h("tr", {}, h("td", { colspan: 4, class: "empty" }, "No recipes yet. Press Alt+C to create one. In a Stock Journal you can then fill the Consumed and Produced lines from it.")));
    sc.replaceChildren(h("div", {}, h("h1", { class: "title" }, "Bills of Material"), h("p", { class: "sub" }, "What a product is made from"), t));
    HL.setKeys([BACK, { k: "Alt+C", label: "Create", fn: () => edit(null) }]);
    const f = $("tbody tr.row", sc); f && f.focus();
  },
};
