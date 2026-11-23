/* In-app guide, shortcut map and first-run tour. The text lives in guide/guide.json (also used to build docs/USER_GUIDE.md). */

HL.guideData = null;
HL.loadGuide = async () => { if (!HL.guideData) { const r = await fetch("/guide/guide.json"); HL.guideData = await r.json(); try { const m = await fetch("/guide/guide_ml.json"); if (m.ok) HL.guideML = await m.json(); } catch (e) { } } return HL.guideData; };
HL.guideML = null;

HL.screens.guide = {
  title: "Guide",
  async render(sc, params) {
    const g = await HL.loadGuide();
    const M = HL.lang() === "ml" && HL.guideML ? HL.guideML : null, U = M ? M.ui : {};
    const T = (k, en) => (M && U[k]) || en;
    const root = h("div", {}, h("h1", { class: "title" }, M ? M.title : g.title), h("p", { class: "sub" }, M ? M.intro : g.intro));
    if (HL.guideML) root.append(h("div", { class: "walk-lang", style: "margin:.2rem 0" }, ["en", "ml"].map(l => h("button", { type: "button", class: "lnk" + (HL.lang() === l ? " on" : ""), onclick: () => { HL.setLang(l); HL.screens.guide.render(sc, params); } }, l === "en" ? "English" : "മലയാളം"))));
    if (M && U.note) root.append(h("p", { class: "hint" }, U.note));
    const nav = h("div", { class: "guide-nav" });
    const body = h("div", { class: "guide-body" });
    const jump = id => { const e = body.querySelector("#g-" + id); if (e) { e.scrollIntoView({ block: "start" }); e.focus && e.focus(); } };
    g.sections.forEach(s => {
      const x = (M && M.sections[s.id]) || s, title = x.title || s.title, text = x.text || s.text, tips = x.tips || s.tips;
      if (/^\d+\./.test(s.title)) nav.append(h("a", { href: "#", onclick: ev => { ev.preventDefault(); jump(s.id); } }, title));
      const card = h("section", { class: "card guide-sec", id: "g-" + s.id, tabindex: "-1" }, h("h2", {}, title), text.map(t => h("p", {}, t)));
      if (tips) card.append(h("div", { class: "banner" }, h("b", {}, T("good", "Good to know: ")), tips.join(" ")));
      if (s.image) card.append(h("img", { class: "guide-img", src: "/guide/" + s.image + ".png", alt: "Screenshot: " + s.title, loading: "lazy" }));
      body.append(card);
    });
    body.prepend(await HL.lessonCards());
    nav.prepend(h("a", { href: "#", onclick: ev => { ev.preventDefault(); jump("lessons"); } }, T("learn", "Learn by doing")));
    nav.append(h("a", { href: "#", onclick: ev => { ev.preventDefault(); jump("keys"); } }, T("keys", "Shortcut map")), h("a", { href: "#", onclick: ev => { ev.preventDefault(); jump("faq"); } }, T("faq", "Questions and answers")));
    const keys = h("section", { class: "card guide-sec", id: "g-keys", tabindex: "-1" }, h("h2", {}, T("keys", "Shortcut map")), h("p", {}, T("keys_note", "Keys with a plus sign are pressed together, for example Ctrl+A means hold Ctrl and press A.")));
    g.shortcuts.forEach(grp => { const [t, tb] = _tbl([M ? (M.groups[grp.group] || grp.group) : grp.group, ""]); grp.rows.forEach(([k, d]) => tb.append(h("tr", {}, h("td", {}, h("kbd", {}, k)), h("td", {}, M ? (M.rows[d] || d) : d)))); keys.append(t); });
    body.append(keys);
    const faq = h("section", { class: "card guide-sec", id: "g-faq", tabindex: "-1" }, h("h2", {}, T("faq", "Questions and answers")));
    (M ? M.faq : g.faq).forEach(([q, a]) => faq.append(h("p", {}, h("b", {}, q), h("br"), a)));
    body.append(faq);
    root.append(h("div", { class: "row", style: "gap:.5rem;margin:.5rem 0" }, h("button", { class: "btn primary", onclick: () => HL.startTour(true) }, T("quick_tour", "Take the quick tour")), h("button", { class: "btn", onclick: () => window.print() }, T("print", "Print this guide"))), nav, body);
    sc.replaceChildren(root);
    HL.setKeys([BACK]);
    if (params && params.at) setTimeout(() => jump(params.at), 50);
  },
};

/* ---- first-run tour: a few friendly cards, shown once, and again whenever asked for ---- */
HL.TOUR = [
  ["Welcome to HomeLedger", "Your accounts live only on this computer. They are saved after every entry and backed up on their own. This short tour takes one minute."],
  ["Moving around", "Press the letter next to a line on the Gateway, or press Alt+G and type where you want to go. Esc always takes you one step back. The panel on the right shows the keys for the screen you are on."],
  ["Writing entries", "F5 is a payment, F6 is money received. Choose the account, type the amount and press Ctrl+A to save. For many lines at once, use Transactions, then Quick Entry."],
  ["Old notebooks and bills", "Take photos of bills in Bill Inbox, and bring typed-up notebooks or bank statements in from Excel under Utilities, then Import from Excel / CSV."],
  ["Where did the money go?", "The Dashboard (Alt+F1) shows spending, savings and plain-sentence observations. Click any chart bar to see the entries behind it. Needs Attention under Reports lists what to look at."],
  ["Staying safe", "Open Utilities (Alt+Y) to make a backup copy and to choose a second place such as a pen drive. Keep a second copy. You can open this guide any time from Shift+F1."],
];
HL.startTour = async (force) => {
  try { await HL.loadGuide(); } catch (e) { }
  try { if (!force && localStorage.getItem("hl_tour_done")) return; } catch (e) { }
  if (typeof modalStack !== "undefined" && modalStack.length && !force) return;
  let i = 0;
  const title = h("div", { style: "font-weight:700;font-size:1.15em;margin-bottom:.4rem" }), txt = h("p", {}), dots = h("div", { class: "hint" });
  const body = h("div", {}, title, txt, dots);
  let m;
  const done = () => { try { localStorage.setItem("hl_tour_done", "1"); } catch (e) { } m.close(); };
  const tour = () => (HL.lang() === "ml" && HL.guideML && HL.guideML.tour) || HL.TOUR, tu = () => (HL.lang() === "ml" && HL.guideML && HL.guideML.tour_ui) || null;
  const draw = () => { const T = tour(), u = tu(); title.textContent = T[i][0]; txt.textContent = T[i][1]; dots.textContent = u ? u.step + " " + (i + 1) + " " + u.of + " " + T.length : "Step " + (i + 1) + " of " + T.length; };
  m = modal({ title: "Quick tour", body, onclose: () => { try { localStorage.setItem("hl_tour_done", "1"); } catch (e) { } }, buttons: [
    { label: "Skip", onclick: () => done() },
    { label: "Try it hands-on", onclick: () => { done(); HL.go("guide", { at: "lessons" }); } },
    { label: "Open the full guide", onclick: () => { done(); HL.go("guide"); } },
    { label: "Next", cls: "primary", onclick: () => { if (i < HL.TOUR.length - 1) { i++; draw(); relabel(); } else done(); } }].concat(HL.guideML ? [{ label: "EN / മലയാളം", onclick: () => { HL.setLang(HL.lang() === "ml" ? "en" : "ml"); draw(); relabel(); } }] : []) });
  // modal buttons close the dialog by default; keep it open for Next
  const relabel = () => { const u = tu(), last = i === HL.TOUR.length - 1, L = u ? [u.skip, u.hands_on, u.full, last ? u.finish : u.next] : ["Skip", "Try it hands-on", "Open the full guide", last ? "Finish" : "Next"]; m.box.querySelectorAll("button").forEach((b, n) => { if (n < 4 && L[n]) b.textContent = L[n]; }); };
  draw(); relabel();
};
