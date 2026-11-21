/* Boot, global keys, heartbeat */
"use strict";
(function () {
  const clock = () => { const d = new Date(); $("#clock").textContent = pad(d.getDate()) + "-" + MON[d.getMonth()] + "-" + d.getFullYear() + "  " + pad(d.getHours()) + ":" + pad(d.getMinutes()); };

  // Heartbeat: lets the program know this window is still open (it closes itself when the window is closed).
  async function beat() { try { await fetch("/api/ping", { cache: "no-store" }); } catch (e) { HL.connectionLost(); } }
  setInterval(beat, 5000);
  // Tell the program the window is closing so it can finish (and back up) within seconds. A reload cancels this.
  window.addEventListener("pagehide", () => {
    if (HL._lost) return;
    try { fetch("/api/closing", { method: "POST", keepalive: true, headers: { "X-HomeLedger": "1", "Content-Type": "application/json" }, body: "{}" }); } catch (e) { }
  });
  // paper copy: logo + book name + report title + date, always in light colours
  window.addEventListener("beforeprint", () => {
    const co = HL.S.status && HL.S.status.company; const def = HL.cur && HL.screens[HL.cur.name];
    $("#ph-company").textContent = co ? co.name : "";
    const t = def && def.title ? (typeof def.title === "function" ? def.title(HL.cur.params) : def.title) : "";
    $("#ph-title").textContent = (t || "HomeLedger") + (HL.S.period && /^(daybook|ledger|tb|pnl|bs|activities|activity|commodities|commodity|dashboard)$/.test(HL.cur.name) ? " \u00b7 " + periodText() : "");
    $("#ph-date").textContent = "Printed " + showDate(todayIso()) + " " + pad(new Date().getHours()) + ":" + pad(new Date().getMinutes());
    document.documentElement.dataset.theme = "light";
  });
  window.addEventListener("afterprint", () => { delete document.documentElement.dataset.theme; });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) beat(); });

  const FKEYS = { F4: "Contra", F5: "Payment", F6: "Receipt", F7: "Journal", F8: "Sales", F9: "Purchase" };
  document.addEventListener("keydown", e => {
    if (modalStack.length) {
      if (e.key === "Escape") { e.preventDefault(); topModal().close(); }
      return;
    }
    if (HL.onKey && HL.onKey(e)) return;
    if (HL.onKey2 && HL.onKey2(e)) return;
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
    if (e.key === "Escape") {
      if (e.target.closest && e.target.closest(".combo .dd")) return;
      if (typing && e.target.closest(".combo") && $(".dd", e.target.closest(".combo")).style.display !== "none") return;
      e.preventDefault(); HL.back(); return;
    }
    if (e.ctrlKey && e.key.toLowerCase() === "l") { e.preventDefault(); HL.lockNow(); return; }
    if (e.ctrlKey && e.key.toLowerCase() === "f") { e.preventDefault(); $("#qsearch").focus(); $("#qsearch").select(); return; }
    if (FKEYS[e.key] && HL.cur && HL.cur.name !== "voucher") { e.preventDefault(); HL.go("voucher", { vtype: FKEYS[e.key] }); return; }
    if (e.ctrlKey && (e.key === "F8" || e.key === "F9") && HL.cur && HL.cur.name !== "voucher") { e.preventDefault(); HL.go("voucher", { vtype: e.key === "F8" ? "Credit Note" : "Debit Note" }); return; }
    if (e.key === "F10" && HL.cur && HL.cur.name !== "voucher") { e.preventDefault(); HL.go("menu", { id: "transactions" }); return; }
    if (e.ctrlKey && e.key === "F10" && HL.cur && HL.cur.name !== "voucher") { e.preventDefault(); HL.go("voucher", { vtype: "Memorandum" }); return; }
    if (e.key === "F3") { e.preventDefault(); HL.go("company"); return; }
    if (e.altKey && e.key === "F1") { e.preventDefault(); HL.go("dashboard"); return; }
    if (HL.cur && HL.cur.name === "gateway" && HL.onKey) { /* handled above */ }
  });
  $("#qsearch").addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); const v = e.target.value.trim(); e.target.value = ""; e.target.blur(); HL.go("search", { q: v }); }
    else if (e.key === "Escape") { e.target.blur(); e.stopPropagation(); }
  });
  // swallow F-key browser defaults (F5 reloads the page, F3 opens find, etc.)
  window.addEventListener("keydown", e => { if (/^F(3|4|5|6|7|8|9|10)$/.test(e.key) && !e.ctrlKey) e.preventDefault(); }, true);
  document.addEventListener("contextmenu", e => { if (!/^(INPUT|TEXTAREA)$/.test(e.target.tagName)) e.preventDefault(); });
  window.addEventListener("error", e => say("A screen problem occurred. Your data is safe. Press Esc and try again.", "err"));
  window.addEventListener("unhandledrejection", e => { if (e.reason && e.reason.message) say(e.reason.message, "err"); });

  HL.start = async function () {
    try {
      await loadMasters();
      applySize();
      $("#company").textContent = HL.S.status.company.name;
      HL.cur = { name: "gateway", params: {} };
      HL._booted = true;
      HL.render();
      HL.get("/api/ping").catch(() => { });
    } catch (e) {
      if (e.locked) return;
      $("#screen").replaceChildren(h("div", { class: "banner err" }, "HomeLedger could not start: " + e.message));
    }
  };
  (async function boot() {
    clock(); setInterval(clock, 20000);
    try {
      await HL.loadAuth();
      if (HL.auth.enabled && !HL.auth.loggedIn) { HL.showLogin(); return; }
    } catch (e) { /* fall through: start() shows the problem */ }
    HL.start();
  })();
})();
