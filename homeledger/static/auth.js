/* Sign-in: lock screen, recovery, status bar, idle lock. Sign-in is optional (turned on in Utilities > Security). */
"use strict";
HL.auth = { enabled: false, user: "", role: "owner", idle: 15 };
HL.isViewer = () => HL.auth.enabled && HL.auth.role === "viewer";

HL.loadAuth = async function () {
  const a = await HL.get("/api/auth/state");
  Object.assign(HL.auth, { enabled: a.enabled, user: a.user, role: a.role, idle: a.idle_minutes, choices: a.idle_choices, loggedIn: a.logged_in, expired: a.expired });
  return a;
};

/* ---------- lock screen ---------- */
let lockEl = null;
HL.showLogin = function (msg) {
  if (lockEl) { if (msg) $("#lock-msg", lockEl).textContent = msg; return; }
  const user = h("input", { type: "text", autocomplete: "username", "aria-label": "User name", value: HL.auth.user || "" });
  const pw = h("input", { type: "password", autocomplete: "current-password", "aria-label": "Password or PIN" });
  const note = h("div", { id: "lock-msg", class: "lock-msg", role: "alert" }, msg || "");
  const go = async () => {
    note.textContent = "";
    try {
      const r = await HL.post("/api/auth/login", { username: user.value, password: pw.value });
      Object.assign(HL.auth, { user: r.user, role: r.role, loggedIn: true });
      lockEl.remove(); lockEl = null;
      if (HL._booted) { await loadMasters(); HL.stack = []; HL.cur = { name: "gateway", params: {} }; HL.render(); HL.updateStatusBar(); }
      else HL.start();
    } catch (e) { note.textContent = e.message; pw.value = ""; pw.focus(); }
  };
  const forgot = h("button", { type: "button", class: "linkbtn", onclick: HL.forgotPassword }, "Forgot password?");
  const quit = h("button", { type: "button", class: "linkbtn", onclick: async () => { try { await HL.post("/api/quit"); } catch (e) { } HL._lost = true; document.body.innerHTML = '<div style="font-family:sans-serif;padding:3rem;text-align:center"><h2>HomeLedger has closed.</h2></div>'; setTimeout(() => window.close(), 400); } }, "Close HomeLedger");
  lockEl = h("div", { id: "lock", role: "dialog", "aria-modal": "true", "aria-label": "Sign in" },
    h("div", { class: "lock-box" }, h("img", { class: "gate-logo", src: "logo.png", alt: "HomeLedger" }),
      h("div", { class: "panel lock-panel" }, h("h2", {}, "Sign in"),
        h("label", { class: "f" }, "User name", user), h("label", { class: "f" }, "Password or PIN", pw), note,
        h("div", { class: "row", style: "margin-top:.7rem" }, h("button", { class: "btn primary", type: "button", onclick: go }, "Sign in"), forgot, quit))));
  lockEl.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); go(); } e.stopPropagation(); }, true);
  document.body.append(lockEl);
  (user.value ? pw : user).focus();
};

HL.lockNow = async function () {
  if (!HL.auth.enabled) { say("Sign-in is not turned on. Turn it on in Utilities > Security.", "err"); return; }
  try { await HL.post("/api/auth/logout"); } catch (e) { }
  HL.showLogin();
};

HL.forgotPassword = function () {
  const key = h("input", { type: "text", placeholder: "XXXXX-XXXXX-XXXXX-XXXXX", "aria-label": "Recovery key" });
  const np = h("input", { type: "password", "aria-label": "New password" });
  const err = h("div", { class: "lock-msg" });
  modal({ title: "Forgot password", body: h("div", {}, h("p", {}, "Type the recovery key you wrote down when sign-in was turned on. It sets a new password for the owner."), h("label", { class: "f" }, "Recovery key", key), h("label", { class: "f" }, "New password or PIN", np), err),
    buttons: [{ label: "Cancel" }, { label: "Set new password", cls: "primary", onclick: async m => {
      try { const r = await HL.post("/api/auth/reset", { key: key.value, new: np.value }); m.close(); HL.showNewKey(r.recovery_key, "Password changed. Here is your NEW recovery key (the old one no longer works)."); }
      catch (e) { err.textContent = e.message; } } }] });
  key.focus();
};

HL.showNewKey = function (k, text) {
  modal({ title: "Your recovery key", wide: true, body: h("div", {}, h("p", {}, text), h("div", { class: "keybox" }, k),
    h("p", { class: "hint" }, "Write it on paper and keep it somewhere safe at home. It is the only way back in if the password is forgotten. It is shown only this once."),
    h("button", { class: "btn", type: "button", onclick: () => window.print() }, "Print")), buttons: [{ label: "I have written it down", cls: "primary" }] });
};

/* ---------- idle lock ---------- */
(function () {
  let last = Date.now(), sentTouch = 0;
  ["keydown", "mousedown", "mousemove", "wheel", "touchstart"].forEach(ev => document.addEventListener(ev, () => { last = Date.now(); }, { passive: true, capture: true }));
  setInterval(async () => {
    if (!HL.auth.enabled || lockEl || HL._lost) return;
    const idleMs = Date.now() - last;
    if (HL.auth.idle && idleMs > HL.auth.idle * 60000) { HL.lockNow(); return; }
    if (idleMs < 60000 && Date.now() - sentTouch > 60000) { sentTouch = Date.now(); try { await HL.get("/api/auth/touch"); } catch (e) { } }   // keeps the sign-in alive while you are working
  }, 10000);
})();

/* ---------- status bar ---------- */
HL.updateStatusBar = function () {
  const s = HL.S.status, el = $("#saved"); if (!s || !el) return;
  const t = iso => { if (!iso) return "never"; const d = iso.slice(0, 10) === todayIso() ? "today" : showDate(iso.slice(0, 10)); return d + " " + iso.slice(11, 16); };
  const parts = [h("span", { class: "dot ok" }, "● Saved"), h("span", {}, "Last backup: " + t(s.last_backup))];
  if (s.copy_dir) parts.push(h("span", { class: s.copy_error ? "bad" : "" }, s.copy_error ? "⚠ Second copy failed" : "Second copy: " + (s.last_external_copy ? t(s.last_external_copy) : "waiting") + (s.copy_protected ? " (protected)" : "")));
  else parts.push(h("span", { class: "warnt" }, "No second copy"));
  parts.push(h("span", { title: "HomeLedger works on this computer only and does not use the internet." }, "Offline"));
  if (HL.auth.enabled) parts.push(h("button", { class: "linkbtn", type: "button", onclick: HL.lockNow, title: "Lock now (Ctrl+L)" }, "🔒 " + HL.auth.user + (HL.isViewer() ? " (view only)" : "")));
  el.replaceChildren(...parts);
};
