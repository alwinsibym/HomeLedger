/* Hands-on guided lessons ("learn by doing").
   The tour makes a separate PRACTICE company, switches to it, then walks the user through real screens: it opens each one,
   highlights where to type, waits for the user to do it, and moves on. Real books are never touched.
   The window reloads when the company switches, so progress lives in localStorage (key hl_walk). */

(function () {
HL.lang = () => { try { return localStorage.getItem("hl_lang") || "en"; } catch (e) { return "en"; } };
HL.setLang = l => { try { localStorage.setItem("hl_lang", l); } catch (e) { } };
HL.lessonData = null;
HL.loadLessons = async () => { if (!HL.lessonData) { const r = await fetch("/guide/lessons.json"); HL.lessonData = await r.json(); try { const m = await fetch("/guide/lessons_ml.json"); if (m.ok) HL.lessonML = await m.json(); } catch (e) { } } return HL.lessonData; };
HL.tx = (obj) => { if (!obj) return ""; const l = HL.lang(); return (l !== "en" && obj[l]) || obj.en || ""; };
HL.lt = key => { const d = HL.lessonData || {}, m = (HL.lessonML || {}).ui || {}; return (HL.lang() !== "en" && m[key] && m[key][HL.lang()]) || ((d.ui || {})[key] || {}).en || key; };

const W = { st: null, el: {}, timer: null, saved: false, backup: false, token: 0 };
const _q = s => document.querySelector(s);
const _t = (s, re) => [...document.querySelectorAll(s)].find(e => re.test(e.textContent || "")) || null;
const _val = s => { const e = _q(s); return e ? e.value : ""; };
const _num = s => parseFloat(String(_val(s)).replace(/[^0-9.]/g, "")) || 0;
const _stepText = id => { const d = HL.lessonData.steps[id], m = ((HL.lessonML || {}).steps || {})[id]; return (HL.lang() !== "en" && m && m[HL.lang()]) || d.en; };
const _lessonText = (id, k) => { const d = HL.lessonData.lessons[id][k], m = (((HL.lessonML || {}).lessons || {})[id] || {})[k]; return (HL.lang() !== "en" && m && m[HL.lang()]) || d.en; };

// events from the app that steps can wait for
(function () {
  const orig = HL.post;
  HL.post = async function (path, body) {
    const r = await orig(path, body);
    if (/\/api\/voucher\/save/.test(path)) W.saved = true;
    if (/\/api\/backup/.test(path)) W.backup = true;
    return r;
  };
})();

// a box counts as filled only once the choice is confirmed: the text matches and the drop-down list has closed
const _picked = (sel, re) => { const e = _q(sel); if (!e || !re.test(e.value)) return false; const dd = e.closest(".combo") && e.closest(".combo").querySelector(".dd"); return !dd || dd.style.display === "none"; };
const _ledgerId = name => ((HL.S.masters || {}).ledgers || []).find(l => l.name === name);

/* ---------------- lessons: each step = {id, go, target, until, next, demo} ---------------- */
const LESSONS = {
  first: [
    { id: "f1", go: ["gateway"], next: true },
    { id: "f2", go: ["voucher", { vtype: "Payment" }], target: () => _q(".vch-head .vt"), next: true },
    { id: "f3", target: () => _q('input[aria-label="Cash or bank account"]'), next: true },
    { id: "f4", target: () => _q('input[aria-label="Account..."]'), until: () => _picked('input[aria-label="Account..."]', /groceries/i), focus: true },
    { id: "f5", target: () => _q("input.amt"), until: () => _num("input.amt") > 0, focus: true, demo: ["input.amt", "1250"] },
    { id: "f6", target: () => _q('textarea[aria-label="Narration"]'), until: () => _val('textarea[aria-label="Narration"]').trim().length > 2, focus: true, demo: ['textarea[aria-label="Narration"]', "Weekly groceries"] },
    { id: "f7", target: () => _t("#keys button", /Accept|Save/), until: () => W.saved, reset: () => { W.saved = false; } },
    { id: "f8", go: ["daybook"], target: () => { const r = document.querySelectorAll("tbody tr.row"); return r.length ? r[r.length - 1] : null; }, next: true },
    { id: "f9", go: async () => { await loadMasters(); const l = _ledgerId("Groceries"); HL.go("ledger", { ledger_id: l && l.id }); }, target: () => _q("tbody tr.row"), next: true },
  ],
  see: [
    { id: "s1", go: ["dashboard"], target: () => _q(".card"), next: true },
    { id: "s2", target: () => _t(".card", /stands out|Needs attention/i) || _q(".card"), next: true },
    { id: "s3", go: ["spending"], target: () => _q("tbody tr.row"), next: true },
    { id: "s4", go: ["alerts"], target: () => _q(".alerts, .banner"), next: true },
    { id: "s5", go: ["spending"], target: () => _t("#keys button", /Excel/), next: true },
  ],
  notebook: [
    { id: "n1", go: ["quickentry"], target: () => _q("table.tbl, .vtbl, table"), next: true },
    { id: "n2", target: () => _q('input[aria-label="Narration"]'), until: () => _val('input[aria-label="Narration"]').trim().length > 1, focus: true, demo: ['input[aria-label="Narration"]', "Milk"] },
    { id: "n3", target: () => _q("input.amt"), until: () => _num("input.amt") > 0, focus: true, demo: ["input.amt", "60"] },
    { id: "n4", go: ["billinbox"], target: () => _q("#screen input[type=file]") && _q("#screen input[type=file]").closest("label, div") || _q("#screen"), next: true },
    { id: "n5", target: () => _t("#screen button, #screen label", /Add to inbox|Choose|Add bills/i) || _q("#screen input[type=file]"), next: true },
    { id: "n6", go: ["bulkimport"], target: () => _q("#screen input[type=file]") && _q("#screen input[type=file]").parentElement || _q("#screen"), next: true },
  ],
  safe: [
    { id: "b1", go: ["utilities"], target: () => _t("#screen button", /Backup & Restore/), next: true },
    { id: "b2", target: () => _t("#screen button", /Create backup now/), until: () => W.backup, reset: () => { W.backup = false; } },
    { id: "b3", target: () => _t("#screen .card, #screen section, #screen div", /Your data is backed up automatically/) ? _t("#screen .card, #screen section", /Your data is backed up automatically/) : _q("#screen .card"), next: true },
    { id: "b4", target: () => _q('#screen input[placeholder*="Backups"]'), next: true },
    { id: "b5", target: () => _t("#screen button", /^Security$/), next: true },
    { id: "b6", target: () => _t("#screen button", /Health Check/), next: true },
  ],
};
HL.LESSON_IDS = Object.keys(LESSONS);

/* ---------------- practice books ---------------- */
const _save = () => { try { localStorage.setItem("hl_walk", JSON.stringify(W.st)); } catch (e) { } };
const _load = () => { try { return JSON.parse(localStorage.getItem("hl_walk") || "null"); } catch (e) { return null; } };
const _clear = () => { try { localStorage.removeItem("hl_walk"); } catch (e) { } };

HL.startLesson = async (lessonId) => {
  await HL.loadLessons();
  if (HL.auth && HL.auth.enabled && HL.auth.role !== "owner") { say(HL.lt("owner_only"), "err"); return; }
  const cos = await HL.get("/api/companies");
  const cur = cos.companies.find(c => c.current) || cos.companies[0];
  const practiceRunning = /^Practice Books/.test(cur.name);
  if (practiceRunning && _load()) { W.st = _load(); W.st.lesson = lessonId; W.st.step = 0; _save(); HL.walkResume(); return; }
  const m = modal({ title: HL.lt("preparing"), body: h("p", {}, HL.lt("preparing")), buttons: [] });
  try {
    const home = cur.id;
    const old = cos.companies.find(c => /^Practice Books/.test(c.name) && !c.current);
    if (old) await HL.post("/api/companies/discard", { id: old.id });
    const r = await HL.post("/api/companies/create", { name: "Practice Books (safe to delete)", books_begin: addDays(todayIso(), -200), open: 0 });
    W.st = { lesson: lessonId, step: 0, home, practice: r.id, phase: "seed" };
    _save();
    await HL.post("/api/companies/open", { id: r.id });
    try { sessionStorage.clear(); } catch (e) { }
    location.reload();
  } catch (e) { m.close(); fail(e); }
};

const _seed = async () => {
  await loadMasters();
  const G = HL.S.masters.groups, gid = c => G.find(x => x.code === c).id;
  const mk = async (n, c) => (await HL.post("/api/ledger/save", { name: n, group_id: gid(c) })).id;
  const ex = {};
  for (const n of ["Groceries", "Electricity", "Mobile & Internet", "Medical", "Transport & Fuel", "House Rent"]) ex[n] = await mk(n, "INDIRECT_EXP");
  const sal = await mk("Salary Received", "DIRECT_INC"), bk = await mk("State Bank Account", "BANK");
  await loadMasters();
  const cash = HL.S.masters.ledgers.find(l => l.cb_kind === "cash").id, today = todayIso();
  const rec = (d, l, a, acct, n) => HL.post("/api/voucher/save", { vtype: "Receipt", date: d, narration: n, lines: [{ ledger_id: l, side: "Cr", amount: String(a) }, { ledger_id: acct, side: "Dr", amount: String(a) }] });
  const pay = (d, l, a, acct, n) => HL.post("/api/voucher/save", { vtype: "Payment", date: d, narration: n, lines: [{ ledger_id: l, side: "Dr", amount: String(a) }, { ledger_id: acct, side: "Cr", amount: String(a) }] });
  for (let m = 3; m >= 0; m--) {
    const b = addDays(today, -m * 30);
    await rec(addDays(b, -25), sal, 60000, bk, "Monthly salary");
    await rec(addDays(b, -24), sal, 8000, cash, "Cash in hand");
    await pay(addDays(b, -22), ex["House Rent"], 12000, bk, "House rent");
    await pay(addDays(b, -15), ex["Groceries"], 900 + m * 130, cash, "Groceries");
    await pay(addDays(b, -12), ex["Electricity"], 1400 + m * 90, bk, "Electricity bill");
    await pay(addDays(b, -9), ex["Mobile & Internet"], 1299, bk, "Internet");
    await pay(addDays(b, -5), ex["Transport & Fuel"], 1500, cash, "Petrol");
  }
  await loadMasters();
};

HL.walkResume = async () => {
  await HL.loadLessons();
  if (!W.st) W.st = _load();
  if (!W.st) return;
  if (W.st.phase === "seed") {
    const m = modal({ title: HL.lt("preparing"), body: h("p", {}, HL.lt("preparing")), buttons: [] });
    try { await _seed(); } catch (e) { m.close(); fail(e); HL.walkExit(); return; }
    m.close(); W.st.phase = "run"; _save();
  }
  _runStep();
};

/* ---------------- overlay ---------------- */
const _ensureOverlay = () => {
  if (W.el.dim) return;
  W.el.dim = h("div", { class: "walk-dim", "aria-hidden": "true" });
  W.el.bub = h("div", { class: "walk-bub", role: "dialog", "aria-live": "polite" });
  document.body.append(W.el.dim, W.el.bub);
  window.addEventListener("resize", _place);
  W.timer = setInterval(_tick, 350);
};
const _teardown = () => { clearInterval(W.timer); window.removeEventListener("resize", _place); Object.values(W.el).forEach(e => e && e.remove()); W.el = {}; };

const _place = () => {
  const st = W.cur; if (!W.el.dim || !st) return;
  const t = st.el && document.contains(st.el) ? st.el : null;
  const dim = W.el.dim, bub = W.el.bub;
  if (t) {
    t.scrollIntoView({ block: "nearest" });
    const r = t.getBoundingClientRect(), pad = 6;
    dim.style.cssText = `left:${r.left - pad}px;top:${r.top - pad}px;width:${r.width + pad * 2}px;height:${r.height + pad * 2}px;`;
    dim.className = "walk-dim spot";
    const bw = bub.offsetWidth || 340, bh = bub.offsetHeight || 160;
    let x = Math.min(Math.max(12, r.left), innerWidth - bw - 12);
    let y = r.bottom + 16;
    if (y + bh > innerHeight - 12) y = r.top - bh - 16;
    if (y < 12) { y = Math.min(innerHeight - bh - 12, r.bottom + 16); x = Math.min(Math.max(12, r.right + 16), innerWidth - bw - 12); if (x < r.right && y < r.bottom) y = Math.max(12, innerHeight - bh - 12); }
    bub.style.left = x + "px"; bub.style.top = y + "px";
  } else {
    dim.style.cssText = ""; dim.className = "walk-dim full";
    const bw = bub.offsetWidth || 340, bh = bub.offsetHeight || 160;
    bub.style.left = Math.max(12, (innerWidth - bw) / 2) + "px"; bub.style.top = Math.max(12, (innerHeight - bh) / 3) + "px";
  }
};

const _typeDemo = async (sel, text) => {
  const e = _q(sel); if (!e) return;
  e.focus(); e.value = "";
  for (const ch of text) { e.value += ch; e.dispatchEvent(new Event("input", { bubbles: true })); await new Promise(r => setTimeout(r, 120)); }
};

const _draw = () => {
  const st = W.cur, lesson = W.st.lesson, steps = LESSONS[lesson], bub = W.el.bub;
  const last = W.st.step >= steps.length - 1;
  bub.replaceChildren(
    h("div", { class: "walk-head" }, h("b", {}, _lessonText(lesson, "title")),
      h("span", { class: "walk-lang" }, ["en", "ml"].map(l => h("button", { type: "button", class: "lnk" + (HL.lang() === l ? " on" : ""), onclick: () => { HL.setLang(l); _draw(); _place(); } }, l === "en" ? "EN" : "മലയാളം")))),
    h("div", { class: "walk-step" }, `${HL.lt("step")} ${W.st.step + 1} ${HL.lt("of")} ${steps.length}`),
    h("p", { class: "walk-text" }, _stepText(st.def.id)),
    st.ok ? h("div", { class: "walk-ok" }, "✓ " + HL.lt("good")) : "",
    h("div", { class: "walk-btns" },
      h("button", { type: "button", class: "btn", onclick: () => HL.walkStop() }, HL.lt("stop")),
      st.def.demo && !st.ok ? h("button", { type: "button", class: "btn", onclick: () => _typeDemo(st.def.demo[0], st.def.demo[1]) }, HL.lt("showme")) : "",
      !st.def.next && !st.ok ? h("button", { type: "button", class: "btn", onclick: () => _advance() }, HL.lt("skip")) : "",
      (st.def.next || st.ok) ? h("button", { type: "button", class: "btn primary", onclick: () => _advance() }, last ? HL.lt("done") : HL.lt("next")) : ""));
};

const _tick = () => {
  const st = W.cur; if (!st || st.busy) return;
  if (!st.el || !document.contains(st.el)) { const e = st.def.target && st.def.target(); if (e && e !== st.el) { st.el = e; if (st.def.focus && e.focus) { try { e.focus({ preventScroll: true }); } catch (x) { } } _draw(); } }
  if (st.def.until && !st.ok && st.def.until()) { st.ok = true; _draw(); setTimeout(() => { if (W.cur === st) _advance(); }, 900); }
  _place();
};

const _runStep = async () => {
  const steps = LESSONS[W.st.lesson], def = steps[W.st.step];
  _ensureOverlay();
  const my = ++W.token;
  W.cur = { def, el: null, ok: false, busy: true };
  W.el.dim.className = "walk-dim full";
  if (def.reset) def.reset();
  if (def.go) { if (typeof def.go === "function") await def.go(); else { await loadMasters(); HL.go(def.go[0], def.go[1]); } await new Promise(r => setTimeout(r, 700)); }
  if (my !== W.token) return;
  W.cur.busy = false;
  const e = def.target ? def.target() : null;
  W.cur.el = e;
  if (def.focus && e && e.focus) { try { e.focus({ preventScroll: true }); } catch (x) { } }
  _draw(); _place();
};

const _advance = () => {
  const steps = LESSONS[W.st.lesson];
  if (W.st.step >= steps.length - 1) return _finish();
  W.st.step++; _save(); _runStep();
};

const _finish = () => {
  _teardown(); W.cur = null;
  const m = modal({ title: HL.lt("end_title"), body: h("p", {}, HL.lt("end_text")), buttons: [
    { label: HL.lt("another"), onclick: m => { m.close(); HL.go("guide", { at: "lessons" }); } },
    { label: HL.lt("stay"), onclick: m => { m.close(); } },
    { label: HL.lt("back_real"), cls: "primary", onclick: () => HL.walkExit() }] });
};

HL.walkStop = () => { _teardown(); W.cur = null; W.token++; HL.go("guide", { at: "lessons" }); };

HL.walkExit = async () => {
  const st = W.st || _load();
  _teardown(); W.cur = null;
  if (!st) return;
  try {
    try { localStorage.setItem("hl_discard", st.practice); } catch (e) { }
    _clear(); W.st = null;
    await HL.post("/api/companies/open", { id: st.home || "main" });
    try { sessionStorage.clear(); } catch (e) { }
    location.reload();
  } catch (e) { fail(e); }
};

/* ---------------- boot: resume a lesson, clean up practice books, show the practice banner ---------------- */
HL.walkBoot = async () => {
  await HL.loadLessons();
  let discard = null;
  try { discard = localStorage.getItem("hl_discard"); } catch (e) { }
  const name = (HL.S.status && HL.S.status.company && HL.S.status.company.name) || "";
  const inPractice = /^Practice Books/.test(name);
  if (discard && !inPractice) { try { await HL.post("/api/companies/discard", { id: discard }); } catch (e) { } try { localStorage.removeItem("hl_discard"); } catch (e) { } }
  const st = _load();
  if (inPractice) {
    const bar = h("div", { class: "practice-bar" }, h("span", {}, "🧪 "), h("b", {}, HL.lt("practice_banner")), " ",
      h("button", { type: "button", class: "btn", onclick: () => HL.walkExit() }, HL.lt("back_real")));
    document.body.prepend(bar); document.body.classList.add("in-practice");
    if (!st) { try { const cos = await HL.get("/api/companies"); const cur = cos.companies.find(c => c.current); const home = (cos.companies.find(c => !/^Practice Books/.test(c.name)) || {}).id || "main"; W.st = { lesson: "first", step: 0, home, practice: cur && cur.id, phase: "none" }; } catch (e) { } }
  }
  if (st && inPractice) { W.st = st; HL.walkResume(); return true; }
  if (st && !inPractice && st.phase !== "seed") { _clear(); }
  return false;
};

/* ---------------- the lessons list inside the Guide ---------------- */
HL.lessonCards = async () => {
  await HL.loadLessons();
  const box = h("section", { class: "card guide-sec", id: "g-lessons", tabindex: "-1" }, h("h2", {}, HL.lang() === "ml" && (HL.lessonML || {}).heading ? HL.lessonML.heading.ml : "Learn by doing"),
    h("p", {}, HL.lang() === "ml" && (HL.lessonML || {}).intro ? HL.lessonML.intro.ml : "Short hands-on lessons in a separate set of practice books. I open each screen for you, show where to type, and wait for you to try it. Your real accounts are never touched, and the practice books are deleted when you finish."));
  const grid = h("div", { class: "lesson-grid" });
  HL.LESSON_IDS.forEach(id => grid.append(h("div", { class: "lesson-card" }, h("b", {}, _lessonText(id, "title")), h("p", { class: "hint" }, _lessonText(id, "about")),
    h("button", { type: "button", class: "btn primary", onclick: () => HL.startLesson(id) }, "▶ " + (HL.lang() === "ml" ? "തുടങ്ങുക" : "Start")))));
  box.append(grid);
  return box;
};


/* ---------------- help for the screen you are on (Shift+F1) ---------------- */
HL.screenHelp = null;
HL.loadScreenHelp = async () => { if (!HL.screenHelp) { try { HL.screenHelp = await (await fetch("/guide/screen_help.json")).json(); } catch (e) { HL.screenHelp = {}; } } return HL.screenHelp; };
HL.screenHelpBlock = async () => {
  const all = await HL.loadScreenHelp(), name = HL.cur && HL.cur.name;
  const e = all[name]; if (!e) return null;
  const l = HL.lang(), d = (l !== "en" && e[l]) || e.en;
  return h("div", { class: "screenhelp" }, h("h3", {}, d.title), h("p", {}, d.what),
    d.todo && d.todo.length ? h("ul", {}, d.todo.map(t => h("li", {}, t))) : "",
    d.watch ? h("p", { class: "hint" }, h("b", {}, (l === "ml" ? "ശ്രദ്ധിക്കുക: " : "Watch out: ")), d.watch) : "");
};
})();
