/* GST: setup, party and item details, GST Summary (GSTR-3B style), GSTR-1 style lists */

const _gstStates = () => Object.entries(HL.gstCfg ? HL.gstCfg.states : {}).map(([k, v]) => h("option", { value: k }, k + " " + v));
const _gstLoad = async () => { HL.gstCfg = await HL.get("/api/gst/config"); return HL.gstCfg; };
const _pct = bp => (bp / 100).toString() + "%";

HL.gstPartyDialog = async L => {
  await _gstLoad(); const m = (await HL.get("/api/gst/masters")).party[L.id] || {};
  const gstin = h("input", { type: "text", value: m.gstin || "", maxlength: "15", style: "text-transform:uppercase", "aria-label": "GSTIN" });
  const st = h("select", { "aria-label": "State" }, h("option", { value: "" }, "(not set)"), ..._gstStates()); st.value = m.state || "";
  const reg = h("select", { "aria-label": "Registration" }, [["regular", "Registered (regular)"], ["composition", "Composition dealer"], ["unregistered", "Unregistered"], ["consumer", "Consumer"]].map(([v, t]) => h("option", { value: v }, t))); reg.value = m.reg || "unregistered";
  modal({ title: "GST details: " + L.name, body: h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f" }, "GSTIN (leave empty if unregistered)", gstin), h("label", { class: "f" }, "State (taken from the GSTIN when given)", st), h("label", { class: "f" }, "Registration type", reg)),
    buttons: [{ label: "Cancel", onclick: x => x.close() }, { label: "Accept", cls: "primary", onclick: async x => { try { await HL.post("/api/gst/party/save", { ledger_id: L.id, gstin: gstin.value, state: st.value, reg: gstin.value.trim() && reg.value === "unregistered" ? "regular" : reg.value }); x.close(); say("GST details saved.", "ok"); } catch (e) { fail(e); } } }] });
};

HL.gstItemDialog = async it => {
  const m = (await HL.get("/api/gst/masters")).item[it.id] || {};
  const hsn = h("input", { type: "text", value: m.hsn || "", maxlength: "8", inputmode: "numeric", "aria-label": "HSN" });
  const rate = h("input", { type: "text", value: m.rate_bp != null ? String(m.rate_bp / 100) : "", inputmode: "decimal", style: "width:6rem", "aria-label": "GST rate" });
  modal({ title: "GST details: " + it.name, body: h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f" }, "HSN / SAC code (4 to 8 digits)", hsn), h("label", { class: "f" }, "GST rate in % (usual slabs: 0, 0.25, 3, 5, 12, 18, 28)", rate),
    h("p", { class: "hint" }, "Check the code and the rate with your accountant or the GST rate finder; rates are changed by the GST Council from time to time.")),
    buttons: [{ label: "Cancel", onclick: x => x.close() }, { label: "Accept", cls: "primary", onclick: async x => { try { await HL.post("/api/gst/item/save", { item_id: it.id, hsn: hsn.value, rate: rate.value }); x.close(); say("GST details saved.", "ok"); } catch (e) { fail(e); } } }] });
};

HL.screens.gstsetup = {
  title: "GST Setup",
  async render(sc) {
    await loadMasters(); const c = await _gstLoad();
    const on = h("input", { type: "checkbox", checked: c.on });
    const gstin = h("input", { type: "text", value: c.gstin, maxlength: "15", style: "text-transform:uppercase", "aria-label": "GSTIN" });
    const st = h("select", { "aria-label": "State" }, h("option", { value: "" }, "(choose)"), ..._gstStates()); st.value = c.state;
    const miss = await HL.get("/api/gst/missing");
    const save = async () => { try { await HL.post("/api/gst/config/save", { on: on.checked, gstin: gstin.value, state: st.value }); await loadMasters(); say("GST setup saved.", "ok"); HL.refresh(); } catch (e) { fail(e); } };
    sc.replaceChildren(_page("GST Setup", "Switch GST on for this company", h("div", { class: "panel", style: "padding:.9rem;max-width:40rem" },
      h("div", { class: "fgrid", style: "grid-template-columns:1fr" }, h("label", { class: "f", style: "flex-direction:row;gap:.4rem;align-items:center" }, on, "Charge and track GST in this company"),
        h("label", { class: "f" }, "Your GSTIN", gstin), h("label", { class: "f" }, "State of your business (decides CGST + SGST or IGST)", st)),
      h("p", { class: "hint" }, "Switching GST on creates the ledgers CGST, SGST and IGST under Duties & Taxes. Give each stock item its HSN code and rate (Masters > Stock Items > GST). In a Sales or Purchase voucher, add the items and press 'Add GST'."),
      h("div", { class: "row" }, h("button", { class: "btn primary", onclick: save }, "Accept"))),
      miss.items_without_rate.length ? h("div", { class: "banner warn", style: "margin-top:.8rem;max-width:40rem" }, "Stock items without GST details (taxed at 0% until set): " + miss.items_without_rate.slice(0, 8).join(", ") + (miss.items_without_rate.length > 8 ? " and " + (miss.items_without_rate.length - 8) + " more" : "")) : "",
      h("div", { class: "banner warn", style: "margin-top:.8rem;max-width:40rem" }, "Stage 1 covers normal intra-state (CGST + SGST) and inter-state (IGST) sales and purchases. Not covered yet: reverse charge, composition dealers' own returns, cess, input-credit eligibility rules, e-invoice, e-way bill, exports. Please have an accountant check the reports before any return is filed.")));
    HL.setKeys([BACK]);
  },
};

HL.screens.gstsummary = {
  title: "GST Summary",
  async render(sc) {
    await loadMasters(); const P = getPeriod();
    const r = await HL.get("/api/gst/summary", { from: P.from, to: P.to });
    const [t, tb] = _tbl(["Particulars", "Taxable value", "CGST", "SGST", "IGST"]);
    const row = (n, o, cls) => tb.append(h("tr", { class: cls || "" }, h("td", {}, n), h("td", { class: "r" }, o.taxable != null ? inr(o.taxable) : ""), h("td", { class: "r" }, inr(o.cgst)), h("td", { class: "r" }, inr(o.sgst)), h("td", { class: "r" }, inr(o.igst))));
    row("Outward supplies (sales less credit notes)", r.outward);
    row("Inward supplies / input tax credit (purchases less debit notes)", r.inward);
    row("Net tax payable (outward less input credit)", Object.assign({}, r.net), "total");
    sc.replaceChildren(_page("GST Summary (GSTR-3B style)", periodText(), periodBar(() => HL.refresh()), t,
      h("div", { class: "banner " + (r.net_total >= 0 ? "ok" : "warn") }, (r.net_total >= 0 ? "Net GST payable: " : "Excess input credit: ") + inr(Math.abs(r.net_total))),
      h("p", { class: "hint" }, "Worked out from the invoices that carry a GST breakup. It assumes all input credit is eligible. Use it to cross-check, not to file.")));
    HL.setKeys([BACK]);
  },
};

HL.screens.gstr1 = {
  title: "GSTR-1 Lists",
  async render(sc, params) {
    await loadMasters(); const P = getPeriod(), tab = params.tab || "b2b";
    const r = await HL.get("/api/gst/gstr1", { from: P.from, to: P.to });
    const tabs = h("div", { class: "chips", style: "margin:.4rem 0 .8rem" }, [["b2b", "B2B invoices"], ["b2c", "B2C summary"], ["cdn", "Credit notes"], ["hsn", "HSN summary"]].map(([k, l]) => h("button", { class: "chip" + (tab === k ? " on" : ""), type: "button", onclick: () => { HL.cur.params = { tab: k }; HL.refresh(); } }, l)));
    let t, tb;
    const money = ["taxable", "cgst", "sgst", "igst"];
    if (tab === "b2c") { [t, tb] = _tbl(["State", "Rate", "Taxable value", "CGST", "SGST", "IGST"]); r.b2c.forEach(x => tb.append(h("tr", {}, h("td", {}, (x.pos || "") + " " + (HL.gstCfg && HL.gstCfg.states[x.pos] || "")), h("td", { class: "r" }, _pct(x.rate_bp)), ...money.map(k => h("td", { class: "r" }, inr(x[k])))))); }
    else if (tab === "hsn") { [t, tb] = _tbl(["HSN / SAC", "Rate", "Taxable value", "CGST", "SGST", "IGST"]); r.hsn.forEach(x => tb.append(h("tr", {}, h("td", {}, x.hsn || "(none)"), h("td", { class: "r" }, _pct(x.rate_bp)), ...money.map(k => h("td", { class: "r" }, inr(x[k])))))); }
    else { const list = tab === "cdn" ? r.cdn : r.b2b; [t, tb] = _tbl(["Date", "Voucher", "Party", "GSTIN", "Rate", "Taxable value", "CGST", "SGST", "IGST", "Invoice value"]);
      list.forEach(x => tb.append(h("tr", {}, h("td", {}, showDate(x.date)), h("td", {}, x.number), h("td", {}, x.party), h("td", {}, x.gstin), h("td", { class: "r" }, _pct(x.rate_bp)), ...money.map(k => h("td", { class: "r" }, inr(x[k]))), h("td", { class: "r" }, inr(x.value))))); }
    if (!tb.children.length) tb.append(h("tr", {}, h("td", { colspan: 10, class: "empty" }, "Nothing in this period.")));
    sc.replaceChildren(_page("GSTR-1 Lists", periodText(), periodBar(() => HL.refresh()), tabs, h("div", { class: "scroll" }, t)));
    HL.setKeys([BACK]);
  },
};
