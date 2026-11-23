"""Local web server. Listens on 127.0.0.1 only; nothing is reachable from the network."""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import logging
import mimetypes
import os
import socket
import sqlite3
import threading
import time
import traceback
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import auth
from . import backup as bk
from . import config
from . import db as dbm
from . import inventory as inv
from .money import parse_iso
from . import reports as rp
from . import service as sv
from .errors import UserError

log = logging.getLogger("homeledger")

GRACE_SECONDS = 240         # fallback: a hidden/minimised window may answer slowly, so wait a long time
CLOSE_SECONDS = 8           # after the window says it is closing, wait this long for a reload before stopping
FIRST_PING_SECONDS = 180    # if no window ever connects, quit
SNAPSHOT_EVERY = 3600       # automatic snapshot at most hourly while entries are being made


class App:
    def __init__(self, db_file: Path, backup_dir: Path):
        self.db_file = db_file
        self.backup_dir = backup_dir
        self.lock = threading.RLock()
        self.started = time.time()
        self.last_ping = time.time()
        self.had_ping = False
        self.closing_at = None
        self.notice = None
        self.httpd = None
        self.stopping = False
        self._snap_busy = False
        self.last_auto = 0.0
        self.last_copy_error = ""
        self.dirty = False   # entries changed since the last backup
        self.sessions = auth.Sessions()
        self.auth_on = False
        self.idle_min = 15
        self.refresh_auth()
        for b in bk.list_backups(backup_dir):
            if b["reason"] == "auto":
                self.last_auto = max(self.last_auto, dt.datetime.fromisoformat(b["when"]).timestamp())

    # -- helpers ----------------------------------------------------------
    def switch_company(self, cid: str):
        """Open another company. A backup of the one being left is taken first if it has unsaved changes."""
        from . import companies as co
        f, b = co.paths(cid)
        if not f.exists():
            raise UserError("The data file of that company is missing.")
        dbm.init_database(f)                      # verifies, and upgrades an older company file
        if self.dirty:
            try:
                self.snapshot("auto")
            except Exception:
                log.exception("backup before switching failed")
        co.set_current(cid)
        b.mkdir(parents=True, exist_ok=True)
        self.db_file, self.backup_dir = f, b
        self.dirty = False
        self.last_auto = 0.0
        self.sessions.clear()
        self.refresh_auth()

    def refresh_auth(self):
        c = self.conn()
        try:
            self.auth_on = auth.enabled(c)
            self.idle_min = auth.idle_minutes(c)
        finally:
            c.close()

    def conn(self):
        return dbm.connect(self.db_file)

    @staticmethod
    def today() -> str:
        return dt.date.today().isoformat()

    # -- backups ----------------------------------------------------------
    def snapshot(self, reason="auto") -> dict:
        path = bk.make_snapshot(self.db_file, self.backup_dir, reason)
        self.dirty = False
        if reason == "auto":
            self.last_auto = time.time()
        info = {"name": path.name, "copy_error": ""}
        c = self.conn()
        try:
            folder = dbm.get_setting(c, "copy_dir", "")
            if folder:
                try:
                    pw = dbm.get_setting(c, "copy_password", "")
                    if pw:
                        bk.copy_protected(path, folder, pw)
                    else:
                        bk.copy_to(path, folder)
                    dbm.set_setting(c, "last_external_copy", dbm.now_iso())
                    self.last_copy_error = ""
                except Exception as e:  # drive unplugged, folder missing...
                    self.last_copy_error = f"{e}"
                    info["copy_error"] = self.last_copy_error
                    log.warning("second copy failed: %s", e)
            dbm.set_setting(c, "last_backup", dbm.now_iso())
        finally:
            c.close()
        try:
            bk.rotate(self.backup_dir)
        except Exception:
            log.exception("rotation failed")
        return info

    def maybe_snapshot(self, force_daily=False):
        if self._snap_busy or time.time() - self.last_auto < SNAPSHOT_EVERY:
            return
        self._snap_busy = True

        def run():
            try:
                with self.lock:
                    self.snapshot("auto")
            except Exception:
                log.exception("automatic backup failed")
            finally:
                self._snap_busy = False
        threading.Thread(target=run, daemon=True).start()

    def final_backup(self):
        try:
            if self.dirty:      # something was entered since the last backup
                with self.lock:
                    self.snapshot("auto")
        except Exception:
            log.exception("backup on exit failed")

    # -- lifecycle ----------------------------------------------------------
    def shutdown(self):
        if self.stopping:
            return
        self.stopping = True
        self.final_backup()
        if self.httpd:
            self.httpd.shutdown()

    def watchdog(self):
        last_tick = time.time()
        while not self.stopping:
            time.sleep(2)
            now = time.time()
            if now - last_tick > 15:  # the computer was asleep: give the window time to wake up
                self.last_ping = now
            last_tick = now
            if self.closing_at and self.last_ping < self.closing_at and now - self.closing_at > CLOSE_SECONDS:
                log.info("window closed - shutting down")
                threading.Thread(target=self.shutdown, daemon=True).start()
                return
            if self.had_ping and now - self.last_ping > GRACE_SECONDS:
                log.info("window closed - shutting down")
                threading.Thread(target=self.shutdown, daemon=True).start()
                return
            if not self.had_ping and now - self.started > FIRST_PING_SECONDS:
                log.info("no window connected - shutting down")
                threading.Thread(target=self.shutdown, daemon=True).start()
                return


# =============================================================================
# route handlers  (app, query, body) -> json-able
# =============================================================================
GET, POST = {}, {}


def route(table, path):
    def deco(fn):
        table[path] = fn
        return fn
    return deco


def _int(q, key, required=False):
    v = q.get(key)
    if v in (None, ""):
        if required:
            raise UserError("Something is missing in the request.")
        return None
    try:
        return int(v)
    except ValueError:
        raise UserError("Invalid request.")


@route(GET, "/api/ping")
def r_ping(app, q, b):
    app.last_ping = time.time()
    app.had_ping = True
    app.closing_at = None
    return {"app": "HomeLedger", "ok": True, "version": config.VERSION}


@route(POST, "/api/closing")
def r_closing(app, q, b):
    app.closing_at = time.time()      # the window is closing (or reloading: its next ping cancels this)
    return {"ok": True}


@route(GET, "/api/status")
def r_status(app, q, b):
    c = app.conn()
    try:
        company = dbm.get_company(c)
        backups = bk.list_backups(app.backup_dir)
        st = {k: dbm.get_setting(c, k, "") for k in ("copy_dir", "text_size", "last_backup", "last_external_copy", "look")}
        return {"version": config.VERSION, "today": app.today(), "company": company,
                "notice": app.notice, "backup_count": len(backups),
                "last_backup": st["last_backup"] or (backups[0]["when"] if backups else ""),
                "copy_dir": st["copy_dir"], "default_copy_dir": config.default_copy_dir(),
                "last_external_copy": st["last_external_copy"], "copy_error": app.last_copy_error,
                "text_size": st["text_size"] or "large", "data_dir": str(config.data_dir()),
                "look": st["look"] or "prime", "copy_protected": bool(dbm.get_setting(c, "copy_password", "")), "auth_on": app.auth_on}
    finally:
        c.close()


@route(POST, "/api/notice/dismiss")
def r_notice(app, q, b):
    app.notice = None
    return {"ok": True}


@route(GET, "/api/masters")
def r_masters(app, q, b):
    c = app.conn()
    try:
        return sv.list_masters(c, app.today())
    finally:
        c.close()


def _reader(fn):
    def h(app, q, b):
        c = app.conn()
        try:
            return fn(c, q)
        finally:
            c.close()
    return h


GET["/api/voucher"] = _reader(lambda c, q: sv.get_voucher(c, _int(q, "id", True)))
GET["/api/next_number"] = _reader(lambda c, q: {"number": sv.next_number(c, q.get("vtype", ""), q.get("date", ""))})
GET["/api/daybook"] = _reader(lambda c, q: sv.day_book(
    c, q.get("from"), q.get("to"), q.get("vtype") or None, q.get("cancelled") == "1"))
GET["/api/ledger_statement"] = _reader(lambda c, q: rp.ledger_statement(
    c, q.get("from"), q.get("to"), _int(q, "ledger_id"), _int(q, "group_id")))
GET["/api/monthly"] = _reader(lambda c, q: rp.monthly_summary(
    c, q.get("from"), q.get("to"), _int(q, "ledger_id"), _int(q, "group_id")))
GET["/api/tb"] = _reader(lambda c, q: rp.trial_balance(c, q.get("from"), q.get("to")))
GET["/api/ratios"] = _reader(lambda c, q: rp.ratio_analysis(c, q.get("from"), q.get("to")))
GET["/api/stocksummary"] = _reader(lambda c, q: rp.stock_summary(c, q.get("from"), q.get("to")))
GET["/api/bankrec"] = _reader(lambda c, q: rp.bank_reconciliation(c, _int(q, "ledger_id", True), q.get("as_on") or q.get("to")))
GET["/api/cashflow"] = _reader(lambda c, q: rp.cash_flow(c, q.get("from"), q.get("to")))
GET["/api/outstanding"] = _reader(lambda c, q: rp.outstanding(c, q.get("kind", "receivable"), min(q.get("as_on") or q.get("to") or dt_today(), dt_today())))
GET["/api/pnl"] = _reader(lambda c, q: rp.profit_and_loss(c, q.get("from"), q.get("to")))
GET["/api/bs"] = _reader(lambda c, q: rp.balance_sheet(c, q.get("from"), q.get("to")))
GET["/api/activities"] = _reader(lambda c, q: rp.activity_summary(c, q.get("from"), q.get("to")))
GET["/api/activity"] = _reader(lambda c, q: rp.activity_detail(c, q.get("from"), q.get("to"), _int(q, "cc_id", True)))
GET["/api/commodities"] = _reader(lambda c, q: rp.commodity_summary(c, q.get("from"), q.get("to")))
GET["/api/commodity"] = _reader(lambda c, q: rp.commodity_detail(
    c, q.get("from"), q.get("to"), q.get("item"), q.get("unit")))
GET["/api/search"] = _reader(lambda c, q: rp.search(c, q))
GET["/api/dashboard"] = _reader(lambda c, q: rp.dashboard(c, q.get("from"), q.get("to"), dt.date.today().isoformat()))


@route(GET, "/api/audit")
def r_audit(app, q, b):
    c = app.conn()
    try:
        lim = min(_int(q, "limit") or 200, 1000)
        rows = [dict(r) for r in c.execute(
            "SELECT id, ts, action, entity, entity_id, substr(detail,1,300) AS detail FROM audit_log "
            "ORDER BY id DESC LIMIT ?", (lim,))]
        return {"rows": rows}
    finally:
        c.close()


# ---- writes (serialised by app.lock in the handler) ---------------------------
def _writer(fn):
    def h(app, q, b):
        c = app.conn()
        try:
            return fn(c, b or {})
        finally:
            c.close()
    h.is_write = True
    return h


POST["/api/voucher/save"] = _writer(lambda c, b: sv.save_voucher(c, b))
POST["/api/voucher/status"] = _writer(lambda c, b: sv.set_voucher_status(
    c, int(b.get("id") or 0), b.get("status") if b.get("status") in ("cancelled", "optional", "memo") else "posted"))
def dt_today():
    import datetime
    return datetime.date.today().isoformat()


GET["/api/openbills"] = _reader(lambda c, q: sv.open_bills(c, _int(q, "ledger_id", True), int(q.get("exclude") or 0)))
GET["/api/groupsummary"] = _reader(lambda c, q: rp.group_summary(c, q.get("from"), q.get("to"), int(q.get("group_id") or 0) or None))
GET["/api/recpay"] = _reader(lambda c, q: rp.receipts_payments(c, q.get("from"), q.get("to")))
GET["/api/fundflow"] = _reader(lambda c, q: rp.fund_flow(c, q.get("from"), q.get("to")))
GET["/api/scenario"] = _reader(lambda c, q: rp.scenario(c, q.get("from"), q.get("to"), q.get("optional", "1") == "1", q.get("memo") == "1"))
GET["/api/interest"] = _reader(lambda c, q: rp.interest(c, q.get("from"), q.get("to"), int(round(float(q.get("rate") or 0) * 100)), int(q.get("group_id") or 0) or None, "Cr" if q.get("side") == "Cr" else "Dr"))
GET["/api/budgetreport"] = _reader(lambda c, q: sv.budget_report(c, q.get("from"), q.get("to")))
GET["/api/budgets"] = _reader(lambda c, q: sv.list_budgets(c))
POST["/api/budget/save"] = _writer(lambda c, b: sv.save_budget(c, b))
GET["/api/stocklists"] = _reader(lambda c, q: inv.lists(c))
GET["/api/stockitems"] = _reader(lambda c, q: inv.list_items(c))
GET["/api/godownsummary"] = _reader(lambda c, q: inv.godown_summary(c, parse_iso(q.get("to") or dt_today())))
GET["/api/batches"] = _reader(lambda c, q: inv.batch_summary(c, parse_iso(q.get("to") or dt_today()), dt_today()))
GET["/api/pendingorders"] = _reader(lambda c, q: inv.pending_orders(c))
GET["/api/prices"] = _reader(lambda c, q: inv.list_prices(c))
GET["/api/price"] = _reader(lambda c, q: inv.price_for(c, int(q.get("item_id") or 0), q.get("level") or "Standard", q.get("on") or dt_today()))
GET["/api/boms"] = _reader(lambda c, q: inv.list_boms(c))
POST["/api/stockitem/save"] = _writer(lambda c, b: inv.save_item(c, b))
POST["/api/stockgroup/save"] = _writer(lambda c, b: inv.save_stock_group(c, b))
POST["/api/stockcategory/save"] = _writer(lambda c, b: inv.save_category(c, b))
POST["/api/godown/save"] = _writer(lambda c, b: inv.save_godown(c, b))
POST["/api/stockmaster/delete"] = _writer(lambda c, b: inv.delete_master(c, b.get("table"), b.get("id")) or {"ok": True})
POST["/api/price/set"] = _writer(lambda c, b: inv.set_price(c, b))
POST["/api/bom/save"] = _writer(lambda c, b: inv.save_bom(c, b))
POST["/api/bom/delete"] = _writer(lambda c, b: inv.delete_bom(c, b.get("id")) or {"ok": True})
GET["/api/postdated"] = _reader(lambda c, q: sv.list_postdated(c))
GET["/api/chequereg"] = _reader(lambda c, q: sv.cheque_register(c, q.get("from"), q.get("to")))
GET["/api/classes"] = _reader(lambda c, q: sv.list_classes(c))
POST["/api/voucher/activate"] = _writer(lambda c, b: sv.activate_postdated(c, int(b.get("id") or 0)))
POST["/api/class/save"] = _writer(lambda c, b: sv.save_class(c, b))
POST["/api/class/delete"] = _writer(lambda c, b: sv.delete_class(c, int(b.get("id") or 0)) or {"ok": True})
POST["/api/voucher/delete"] = _writer(lambda c, b: sv.delete_voucher(c, int(b.get("id") or 0)))
POST["/api/stockitem/delete"] = _writer(lambda c, b: sv.delete_stock_item(c, int(b.get("id") or 0)) or {"ok": True})
POST["/api/bank/date"] = _writer(lambda c, b: sv.set_bank_date(c, int(b.get("voucher_id") or 0), int(b.get("ledger_id") or 0), b.get("bank_date") or None))
POST["/api/ledger/save"] = _writer(lambda c, b: sv.save_ledger(c, b))
POST["/api/ledger/delete"] = _writer(lambda c, b: sv.delete_ledger(c, int(b.get("id") or 0)) or {"ok": True})
POST["/api/group/save"] = _writer(lambda c, b: sv.save_group(c, b))
POST["/api/group/delete"] = _writer(lambda c, b: sv.delete_group(c, int(b.get("id") or 0)) or {"ok": True})
POST["/api/cc/save"] = _writer(lambda c, b: sv.save_cc(c, b))
POST["/api/cc/delete"] = _writer(lambda c, b: sv.delete_cc(c, int(b.get("id") or 0)) or {"ok": True})
def _co():
    from . import companies as co
    return co


@route(GET, "/api/companies")
def r_companies(app, q, b):
    return {"companies": _co().listing()}


@route(POST, "/api/companies/open")
def r_co_open(app, q, b):
    with app.lock:
        app.switch_company(str(b.get("id") or ""))
    return {"ok": True}


@route(POST, "/api/companies/create")
def r_co_create(app, q, b):
    cid = _co().create(b.get("name"), b.get("books_begin") or None)
    if b.get("open"):
        with app.lock:
            app.switch_company(cid)
    return {"ok": True, "id": cid}


@route(POST, "/api/companies/remove")
def r_co_remove(app, q, b):
    _co().remove_from_list(str(b.get("id") or ""))
    return {"ok": True}


@route(POST, "/api/companies/discard")
def r_co_discard(app, q, b):
    _co().discard_practice(str(b.get("id") or ""))
    return {"ok": True}


@route(POST, "/api/companies/carry")
def r_co_carry(app, q, b):
    """Split / year-end close: a new company that starts on `cutoff` with the balances carried forward."""
    with app.lock:
        app.snapshot("pre-split")
        c = app.conn()
        try:
            cid, pending = _co().carry_forward(c, app.db_file, b.get("cutoff"), b.get("name") or "")
        finally:
            c.close()
    if b.get("open"):
        with app.lock:
            app.switch_company(cid)
    return {"ok": True, "id": cid, "pending": pending}


@route(POST, "/api/companies/merge")
def r_co_merge(app, q, b):
    cid = str(b.get("id") or "")
    f, _ = _co().paths(cid)
    if cid == _co().current_id() or not f.exists():
        raise UserError("Please choose a different company to merge from.")
    with app.lock:
        app.snapshot("pre-merge")
        c = app.conn()
        try:
            res = _co().merge_from(c, f)
        finally:
            c.close()
        app.dirty = True
    return res


for _p in ("/api/companies/open", "/api/companies/create", "/api/companies/remove", "/api/companies/discard", "/api/companies/carry", "/api/companies/merge"):
    POST[_p].owner_only = True


POST["/api/company/save"] = _writer(lambda c, b: sv.save_company(c, b) or {"ok": True})
POST["/api/openings/save"] = _writer(lambda c, b: sv.set_openings(c, b.get("items") or []))


@route(POST, "/api/settings/save")
def r_settings_save(app, q, b):
    c = app.conn()
    try:
        with dbm.write_tx(c):
            if "text_size" in b:
                if b["text_size"] not in ("normal", "large", "xlarge"):
                    raise UserError("Unknown text size.")
                dbm.set_setting(c, "text_size", b["text_size"])
            if "look" in b:
                if b["look"] not in ("prime", "classic"):
                    raise UserError("Unknown look.")
                dbm.set_setting(c, "look", b["look"])
            if "copy_dir" in b:
                folder = str(b["copy_dir"] or "").strip()
                if folder:
                    try:
                        Path(folder).mkdir(parents=True, exist_ok=True)
                        probe = Path(folder) / ".homeledger-write-test"
                        probe.write_text("ok")
                        probe.unlink()
                    except Exception:
                        raise UserError("HomeLedger cannot write to that folder. Check the drive is connected "
                                        "and the folder name is correct.")
                dbm.set_setting(c, "copy_dir", folder)
            if "copy_password" in b:
                pw = str(b["copy_password"] or "")
                if pw and len(pw) < 6:
                    raise UserError("Use at least 6 characters for the backup password.")
                dbm.set_setting(c, "copy_password", pw)
        return {"ok": True}
    finally:
        c.close()


POST["/api/settings/save"].is_write = True


@route(GET, "/api/backups")
def r_backups(app, q, b):
    return {"rows": bk.list_backups(app.backup_dir), "dir": str(app.backup_dir)}


@route(POST, "/api/backup/create")
def r_backup_create(app, q, b):
    info = app.snapshot("manual")
    return info


@route(POST, "/api/backup/restore")
def r_backup_restore(app, q, b):
    name = str(b.get("name") or "")
    if "/" in name or "\\" in name or not bk.NAME_RE.match(name):
        raise UserError("Unknown backup.")
    src = app.backup_dir / name
    bk.validate_backup(src)
    app.snapshot("pre-restore")       # always keep what is there now
    bk.restore_into(app.db_file, src)
    app.notice = None
    app.refresh_auth()
    app.sessions.clear()          # a restored book may have different users: everyone signs in again
    return {"ok": True}


@route(POST, "/api/backup/restore_file")
def r_backup_restore_file(app, q, b):
    """Restore from a password-protected copy (for example one kept in Google Drive)."""
    path = Path(str(b.get("path") or "").strip().strip('"'))
    if not path.is_file():
        raise UserError("That file was not found. Type or paste its full location.")
    tmp = app.backup_dir / "restore-temp.db"
    try:
        bk.decrypt_file(path, tmp, str(b.get("password") or ""))
        bk.validate_backup(tmp)
        app.snapshot("pre-restore")
        bk.restore_into(app.db_file, tmp)
    finally:
        tmp.unlink(missing_ok=True)
    app.notice = None
    app.refresh_auth()
    app.sessions.clear()
    return {"ok": True}


for _p in ("/api/backup/create", "/api/backup/restore", "/api/backup/restore_file"):
    POST[_p].is_write = True


# ---- sign-in ------------------------------------------------------------------
ENTRY_OK = {"/api/voucher/save", "/api/voucher/status", "/api/voucher/activate", "/api/notice/dismiss", "/api/bank/date"}
PUBLIC = {"/api/ping", "/api/closing", "/api/auth/state", "/api/auth/login", "/api/auth/reset", "/api/quit"}


def _authw(fn, owner_only=False, viewer_ok=False):
    def h(app, q, b):
        c = app.conn()
        try:
            return fn(app, c, q, b or {})
        finally:
            c.close()
    h.is_write = True
    h.owner_only = owner_only
    h.viewer_ok = viewer_ok
    return h


@route(GET, "/api/auth/state")
def r_auth_state(app, q, b):
    s = app.sessions.get(q.get("_tok"), app.idle_min, touch=False) if app.auth_on else None
    ok = isinstance(s, dict)
    return {"enabled": app.auth_on, "logged_in": ok or not app.auth_on, "idle_minutes": app.idle_min,
            "user": s["username"] if ok else "", "role": s["role"] if ok else ("owner" if not app.auth_on else ""),
            "idle_choices": list(auth.IDLE_CHOICES), "expired": s == "expired"}


def _login(app, c, q, b):
    if not app.auth_on:
        raise UserError("Sign-in is not turned on.")
    u = auth.verify(c, b.get("username"), b.get("password"))
    return {"user": u["username"], "role": u["role"], "_cookie": app.sessions.start(u)}


def _enable(app, c, q, b):
    key = auth.enable(c, b.get("username"), b.get("password"))
    app.refresh_auth()
    u = auth.verify(c, b.get("username"), b.get("password"))
    return {"recovery_key": key, "_cookie": app.sessions.start(u)}


def _disable(app, c, q, b):
    user = q["_user"]
    auth.verify(c, user["username"], b.get("password"))
    auth.disable(c)
    app.refresh_auth()
    app.sessions.clear()
    return {"ok": True}


def _logout(app, c, q, b):
    app.sessions.end(q.get("_tok"))
    return {"ok": True, "_clear": True}


def _change_pw(app, c, q, b):
    auth.change_password(c, q["_user"]["id"], b.get("old"), b.get("new"))
    return {"ok": True}


def _reset(app, c, q, b):
    return {"recovery_key": auth.reset_with_recovery_key(c, b.get("key"), b.get("new"))}


def _add_user(app, c, q, b):
    auth.add_user(c, b.get("username"), b.get("password"), b.get("role"))
    return {"ok": True}


def _remove_user(app, c, q, b):
    uid = int(b.get("id") or 0)
    if uid == q["_user"]["id"]:
        raise UserError("You cannot remove the user you are signed in as.")
    auth.remove_user(c, uid)
    return {"ok": True}


def _idle(app, c, q, b):
    m = int(b.get("minutes") if b.get("minutes") is not None else 15)
    if m not in auth.IDLE_CHOICES:
        raise UserError("Unknown time.")
    with dbm.write_tx(c):
        dbm.set_setting(c, "idle_minutes", str(m))
    app.refresh_auth()
    return {"ok": True}


POST["/api/auth/login"] = _authw(_login, viewer_ok=True)
POST["/api/auth/enable"] = _authw(_enable)
POST["/api/auth/disable"] = _authw(_disable, owner_only=True)
POST["/api/auth/logout"] = _authw(_logout, viewer_ok=True)
POST["/api/auth/password"] = _authw(_change_pw, viewer_ok=True)
POST["/api/auth/reset"] = _authw(_reset, viewer_ok=True)
POST["/api/auth/user/add"] = _authw(_add_user, owner_only=True)
POST["/api/auth/user/remove"] = _authw(_remove_user, owner_only=True)
POST["/api/auth/idle"] = _authw(_idle, owner_only=True)


@route(GET, "/api/auth/touch")
def r_auth_touch(app, q, b):
    return {"ok": True}


@route(GET, "/api/auth/users")
def r_auth_users(app, q, b):
    if app.auth_on and q["_user"]["role"] != "owner":
        raise UserError("Only the owner can see the users.")
    c = app.conn()
    try:
        return {"rows": auth.users(c)}
    finally:
        c.close()


@route(POST, "/api/quit")
def r_quit(app, q, b):
    threading.Thread(target=app.shutdown, daemon=True).start()
    return {"ok": True}


@route(GET, "/api/health")
def r_health(app, q, b):
    c = app.conn()
    try:
        out = []

        def add(name, ok, detail):
            out.append({"name": name, "ok": ok, "detail": detail})
        rows = [r[0] for r in c.execute("PRAGMA integrity_check").fetchall()]
        add("Data file integrity", rows == ["ok"],
            "The data file is healthy." if rows == ["ok"] else "Problems found: " + "; ".join(rows[:3]))
        fk = c.execute("PRAGMA foreign_key_check").fetchall()
        add("Links between records", not fk, "All records link correctly." if not fk
            else f"{len(fk)} broken link(s) found.")
        unb = c.execute(
            """SELECT v.id, v.vtype, v.number, v.vdate FROM vouchers v
               WHERE v.status='posted' AND (SELECT COALESCE(SUM(debit_paise),0) FROM entries WHERE voucher_id=v.id)
                  <> (SELECT COALESCE(SUM(credit_paise),0) FROM entries WHERE voucher_id=v.id)""").fetchall()
        add("Every voucher balances", not unb, "Debit equals credit in every voucher." if not unb else
            "Unbalanced: " + ", ".join(f"{u['vtype']} {u['number']} ({u['vdate']})" for u in unb[:5]))
        empty = c.execute("""SELECT COUNT(*) FROM vouchers v WHERE NOT EXISTS
                             (SELECT 1 FROM entries e WHERE e.voucher_id=v.id)""").fetchone()[0]
        add("No empty vouchers", empty == 0, "No empty vouchers." if not empty else f"{empty} voucher(s) have no lines.")
        diff = c.execute(
            """SELECT COALESCE(SUM(CASE WHEN opening_type='Dr' THEN opening_paise ELSE -opening_paise END),0)
               FROM ledgers WHERE nature IN ('asset','liability')""").fetchone()[0]
        add("Opening balances agree", diff == 0,
            "Opening balances are in balance." if diff == 0 else
            "Opening balances differ by " + f"{abs(diff) / 100:,.2f}" + (" (debit side higher)." if diff > 0 else
                                                                         " (credit side higher).") +
            " Use Utilities > Opening Balances to fix.")
        nb = len(bk.list_backups(app.backup_dir))
        add("Backups exist", nb > 0, f"{nb} backup(s) stored." if nb else "No backups yet. Press Create Backup Now.")
        return {"checks": out, "all_ok": all(x["ok"] for x in out if x["name"] != "Opening balances agree")}
    finally:
        c.close()


def _rupees(p) -> str:
    p = int(p or 0)
    return f"{'-' if p < 0 else ''}{abs(p) // 100}.{abs(p) % 100:02d}"


@route(GET, "/api/export")
def r_export(app, q, b):
    """Everything as CSV files in one zip (opens in Excel)."""
    c = app.conn()
    try:
        files = {}

        def table(name, header, rows):
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(header)
            w.writerows(rows)
            files[name] = ("﻿" + buf.getvalue()).encode("utf-8")  # BOM so Excel reads rupee/UTF-8 text properly
        table("entries.csv",
              ["Date", "Voucher type", "Voucher no", "Financial year", "Status", "Ledger", "Group", "Debit", "Credit",
               "Activity", "Item", "Quantity", "Unit", "Narration", "Reference", "Date approximate"],
              [(r["vdate"], r["vtype"], r["number"], r["fy"], r["status"], r["lname"], r["gname"],
                _rupees(r["debit_paise"]) if r["debit_paise"] else "", _rupees(r["credit_paise"]) if r["credit_paise"] else "",
                r["cc"] or "", r["item"] or "", (r["qty_milli"] or 0) / 1000 if r["qty_milli"] else "", r["unit"] or "",
                r["narration"], r["ref"], "yes" if r["date_approx"] else "")
               for r in c.execute(
                   """SELECT v.vdate, v.vtype, v.number, v.fy, v.status, l.name AS lname, g.name AS gname,
                             e.debit_paise, e.credit_paise, cc.name AS cc, e.item, e.qty_milli, e.unit,
                             v.narration, v.ref, v.date_approx
                      FROM entries e JOIN vouchers v ON v.id=e.voucher_id JOIN ledgers l ON l.id=e.ledger_id
                      JOIN acct_groups g ON g.id=l.group_id LEFT JOIN cost_centres cc ON cc.id=e.cc_id
                      ORDER BY v.vdate, v.id, e.line_no""")])
        table("ledgers.csv", ["Ledger", "Group", "Kind", "Opening balance", "Dr/Cr", "Active"],
              [(r["name"], r["gname"], r["nature"], _rupees(r["opening_paise"]), r["opening_type"],
                "yes" if r["is_active"] else "no")
               for r in c.execute("""SELECT l.*, g.name AS gname FROM ledgers l JOIN acct_groups g ON g.id=l.group_id
                                     ORDER BY g.sort, l.name""")])
        table("activities.csv", ["Activity", "Belongs to", "Kind", "Active"],
              [(r["name"], r["pname"] or "", r["kind"], "yes" if r["is_active"] else "no")
               for r in c.execute("""SELECT a.*, p.name AS pname FROM cost_centres a
                                     LEFT JOIN cost_centres p ON p.id=a.parent_id ORDER BY a.sort""")])
        table("audit_log.csv", ["Time", "Action", "Item", "Id", "Details"],
              [(r["ts"], r["action"], r["entity"], r["entity_id"], r["detail"])
               for r in c.execute("SELECT * FROM audit_log ORDER BY id")])
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for n, data in files.items():
                z.writestr(n, data)
        return ("zip", f"HomeLedger-export-{app.today().replace('-', '')}.zip", buf.getvalue())
    finally:
        c.close()


def _gst():
    from . import gst
    return gst


GET["/api/gst/config"] = _reader(lambda c, q: _gst().get_config(c))
GET["/api/gst/masters"] = _reader(lambda c, q: _gst().masters(c))
GET["/api/gst/summary"] = _reader(lambda c, q: _gst().summary(c, parse_iso(q.get("from")), parse_iso(q.get("to"))))
GET["/api/gst/gstr1"] = _reader(lambda c, q: _gst().gstr1(c, parse_iso(q.get("from")), parse_iso(q.get("to"))))
GET["/api/gst/missing"] = _reader(lambda c, q: _gst().missing_details(c))
POST["/api/gst/config/save"] = _writer(lambda c, b: _gst().save_config(c, b))
POST["/api/gst/party/save"] = _writer(lambda c, b: _gst().save_party(c, b))
POST["/api/gst/item/save"] = _writer(lambda c, b: _gst().save_item(c, b))


@route(POST, "/api/gst/compute")
def r_gst_compute(app, q, b):          # only calculates; nothing is saved
    c = app.conn()
    try:
        return _gst().compute(c, b.get("vtype"), b.get("party"), b.get("pos") or "", b.get("items") or [])
    finally:
        c.close()


def _tds():
    from . import tds
    return tds


@route(GET, "/api/tds/setup")
def r_tds_setup(app, q, b):
    with app.lock:
        c = app.conn()
        try:
            return _tds().setup(c)
        finally:
            c.close()


GET["/api/tds/statement"] = _reader(lambda c, q: _tds().statement(c, parse_iso(q.get("from")), parse_iso(q.get("to"))))
POST["/api/tds/nature/save"] = _writer(lambda c, b: _tds().save_nature(c, b))
POST["/api/tds/pan/save"] = _writer(lambda c, b: _tds().save_pan(c, b))
POST["/api/tds/challan/save"] = _writer(lambda c, b: _tds().save_challan(c, b))
POST["/api/tds/challan/delete"] = _writer(lambda c, b: _tds().delete_challan(c, b.get("id")))


@route(GET, "/api/tds/deposits")
def r_tds_deposits(app, q, b):
    c = app.conn()
    try:
        return _tds().deposits(c, app.today())
    finally:
        c.close()


@route(POST, "/api/tds/compute")
def r_tds_compute(app, q, b):          # calculates only; nothing is saved
    from .money import parse_amount
    c = app.conn()
    try:
        return _tds().compute(c, b.get("nature_id"), b.get("party"), parse_amount(b.get("base"), "Amount"), parse_iso(b.get("date")),
                              b.get("voucher_id"), b.get("rate"))
    finally:
        c.close()


def _pr():
    from . import payroll
    return payroll


GET["/api/payroll/heads"] = _reader(lambda c, q: _pr().heads(c))
GET["/api/payroll/employees"] = _reader(lambda c, q: _pr().employees(c))
GET["/api/payroll/run"] = _reader(lambda c, q: _pr().get_run(c, q.get("month")))
GET["/api/payroll/register"] = _reader(lambda c, q: _pr().register(c, parse_iso(q.get("from")), parse_iso(q.get("to"))))
POST["/api/payroll/head/save"] = _writer(lambda c, b: _pr().save_head(c, b))
POST["/api/payroll/employee/save"] = _writer(lambda c, b: _pr().save_employee(c, b))
POST["/api/payroll/run/save"] = _writer(lambda c, b: _pr().save_run(c, b))
POST["/api/payroll/run/post"] = _writer(lambda c, b: _pr().post_run(c, b.get("month")))
POST["/api/payroll/run/reopen"] = _writer(lambda c, b: _pr().reopen_run(c, b.get("month")))


@route(POST, "/api/payroll/run/calc")
def r_pr_calc(app, q, b):          # calculates only
    c = app.conn()
    try:
        return _pr().calc_run(c, b)
    finally:
        c.close()


def _att():
    from . import attach
    return attach


def _bulk():
    from . import bulk
    return bulk


GET["/api/attach/list"] = _reader(lambda c, q: _att().listing(c, q.get("voucher_id"), q.get("inbox") == "1"))
GET["/api/attach/counts"] = _reader(lambda c, q: _att().counts(c))
GET["/api/attach/file"] = _reader(lambda c, q: _att().get_file(c, q.get("id")))
POST["/api/attach/upload"] = _writer(lambda c, b: _att().add(c, b))
POST["/api/attach/link"] = _writer(lambda c, b: _att().link(c, b.get("id"), b.get("voucher_id")))
POST["/api/attach/delete"] = _writer(lambda c, b: _att().delete(c, b.get("id")))
GET["/api/bulk/suggest"] = _reader(lambda c, q: dict(zip(("ledger_id", "source"), _bulk().suggest(c, q.get("text") or ""))))
GET["/api/bulk/rules"] = _reader(lambda c, q: _bulk().rules(c))
POST["/api/bulk/rule/save"] = _writer(lambda c, b: _bulk().save_rule(c, b))
POST["/api/bulk/rule/delete"] = _writer(lambda c, b: _bulk().delete_rule(c, b.get("id")))
POST["/api/bulk/commit"] = _writer(lambda c, b: _bulk().commit(c, b))


@route(POST, "/api/bulk/parse")
def r_bulk_parse(app, q, b):
    return _bulk().parse_file(b.get("filename") or "", b.get("data") or "")


@route(POST, "/api/bulk/preview")
def r_bulk_preview(app, q, b):
    c = app.conn()
    try:
        return _bulk().preview(c, b)
    finally:
        c.close()


@route(GET, "/api/tallyxml")
def r_tally_export(app, q, b):
    from . import utilities as ut
    c = app.conn()
    try:
        frm = parse_iso(q.get("from") or "0001-01-01"); to = parse_iso(q.get("to") or "9999-12-31")
        return ("xml", f"HomeLedger-tally-{app.today().replace('-', '')}.xml", ut.export_xml(c, frm, to))
    finally:
        c.close()


@route(POST, "/api/tallyxml/import")
def r_tally_import(app, q, b):
    from . import utilities as ut
    with app.lock:
        app.snapshot("pre-import")
        c = app.conn()
        try:
            return ut.import_xml(c, str(b.get("xml") or "").encode("utf-8"))
        finally:
            c.close()


@route(POST, "/api/repair")
def r_repair(app, q, b):
    from . import utilities as ut
    with app.lock:
        app.snapshot("pre-repair")
        c = app.conn()
        try:
            return ut.repair(c)
        finally:
            c.close()


r_tally_import.is_write = False
for _f in (r_tally_import, r_repair, r_backup_restore, r_backup_restore_file):
    _f.owner_only = True


# =============================================================================
# HTTP plumbing
# =============================================================================
def make_handler(app: App):
    static = config.static_dir()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "HomeLedger"

        def log_message(self, fmt, *args):
            log.debug("%s - %s", self.address_string(), fmt % args)

        # -- response helpers
        def _send(self, status, body: bytes, ctype="application/json; charset=utf-8", headers=None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            if "Cache-Control" not in (headers or {}):
                self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, obj, status=200):
            self._send(status, json.dumps(obj, separators=(",", ":"), default=str).encode("utf-8"))

        def _host_ok(self):
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
            return host in ("127.0.0.1", "localhost")

        # -- dispatch
        def _cookie(self):
            for part in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == "hl_session":
                    return v
            return ""

        def _handle(self, table, body):
            u = urlparse(self.path)
            fn = table.get(u.path)
            if fn is None:
                return self._json({"error": "Not found"}, 404)
            q = {k: v[0] for k, v in parse_qs(u.query, keep_blank_values=True).items()}
            q.pop("_tok", None); q.pop("_user", None)          # these are set only by the program itself
            tok = self._cookie()
            q["_tok"] = tok
            if app.auth_on and u.path not in PUBLIC:
                s = app.sessions.get(tok, app.idle_min, touch=True)
                if not isinstance(s, dict):
                    return self._json({"error": "Please sign in again.", "locked": True}, 401)
                if getattr(fn, "owner_only", False) and s["role"] != "owner":
                    return self._json({"error": "Only the owner can do this."}, 403)
                if getattr(fn, "is_write", False) and s["role"] != "owner" and not getattr(fn, "viewer_ok", False):
                    if s["role"] == "viewer":
                        return self._json({"error": "This user can only view. Sign in as the owner to make changes."}, 403)
                    if s["role"] == "entry" and u.path not in ENTRY_OK:
                        return self._json({"error": "This user can enter and cancel vouchers only. Ask the owner for other changes."}, 403)
                q["_user"] = s
            elif not app.auth_on:
                q["_user"] = {"id": 0, "username": "", "role": "owner"}
            else:
                q["_user"] = {"id": 0, "username": "", "role": ""}
            try:
                if getattr(fn, "is_write", False):
                    with app.lock:
                        res = fn(app, q, body)
                        app.dirty = True
                    app.maybe_snapshot()
                else:
                    res = fn(app, q, body)
            except UserError as e:
                return self._json({"error": str(e)}, 400)
            except sqlite3.OperationalError as e:
                log.exception("database busy/error")
                msg = ("HomeLedger is busy. Please try again in a moment." if "locked" in str(e).lower()
                       else "HomeLedger could not read or write its data file. Your data is safe; "
                            "please close and reopen HomeLedger. (Details are in the log file.)")
                return self._json({"error": msg}, 503)
            except sqlite3.IntegrityError as e:
                log.exception("integrity error")
                return self._json({"error": "That change was refused by the data safety checks, so nothing was saved. "
                                            f"({e})"}, 400)
            except Exception:
                log.error("unhandled error on %s\n%s", self.path, traceback.format_exc())
                return self._json({"error": "Something went wrong inside HomeLedger. Nothing was saved and your "
                                            "existing data is safe. Please try again; if it keeps happening, "
                                            "tell the person who set this up (details are in the log file)."}, 500)
            if isinstance(res, tuple) and res and res[0] == "bin":
                return self._send(200, res[2], res[3], {"Content-Disposition": 'inline; filename="%s"' % res[1].replace('"', ""),
                                                        "Content-Security-Policy": "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'"})
            if isinstance(res, tuple) and res and res[0] in ("zip", "xml"):
                return self._send(200, res[2], "application/zip" if res[0] == "zip" else "application/xml",
                                  {"Content-Disposition": f'attachment; filename="{res[1]}"'})
            hdrs = None
            if isinstance(res, dict) and ("_cookie" in res or res.get("_clear")):
                ck = res.pop("_cookie", "")
                res.pop("_clear", None)
                hdrs = {"Set-Cookie": f"hl_session={ck}; HttpOnly; SameSite=Strict; Path=/" + ("" if ck else "; Max-Age=0")}
            self._send(200, json.dumps(res, separators=(",", ":"), default=str).encode("utf-8"), headers=hdrs)

        def do_GET(self):
            if not self._host_ok():
                return self._json({"error": "Forbidden"}, 403)
            path = urlparse(self.path).path
            if path.startswith("/api/"):
                return self._handle(GET, None)
            if path in ("/", ""):
                path = "/index.html"
            target = (static / path.lstrip("/")).resolve()
            if static.resolve() not in target.parents or not target.is_file():
                return self._send(404, b"Not found", "text/plain")
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
                ctype += "; charset=utf-8" if "charset" not in ctype else ""
            st = target.stat()
            etag = '"%x-%x"' % (st.st_mtime_ns, st.st_size)
            if self.headers.get("If-None-Match") == etag:     # unchanged: nothing to send, so pages open instantly
                self.send_response(304); self.send_header("ETag", etag); self.send_header("Cache-Control", "no-cache")
                self.send_header("Content-Length", "0"); self.end_headers(); return
            self._send(200, target.read_bytes(), ctype, {"ETag": etag, "Cache-Control": "no-cache"})

        do_HEAD = do_GET

        def do_POST(self):
            if not self._host_ok():
                return self._json({"error": "Forbidden"}, 403)
            if self.headers.get("X-HomeLedger") != "1":  # blocks other websites from posting to this port
                return self._json({"error": "Forbidden"}, 403)
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            limit = 14_000_000 if self.path.split('?')[0] in ("/api/attach/upload", "/api/bulk/parse") else 2_000_000
            if n > limit:
                return self._json({"error": "Request too large."}, 413)
            raw = self.rfile.read(n) if n else b""
            try:
                body = json.loads(raw.decode("utf-8")) if raw else {}
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                return self._json({"error": "Invalid request."}, 400)
            self._handle(POST, body)

    return Handler


class QuietServer(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows, SO_REUSEADDR lets a second program share a port that is already in use; there we ask for
    # exclusive use instead, so a clash is detected and the next port is tried.
    allow_reuse_address = (os.name != "nt")

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def handle_error(self, request, client_address):  # broken pipes when a window closes are normal
        log.debug("connection error", exc_info=True)


def create_server(app: App, port: int) -> ThreadingHTTPServer:
    httpd = QuietServer(("127.0.0.1", port), make_handler(app))
    app.httpd = httpd
    return httpd


# ---- templates, repeats, insights --------------------------------------------------------------------
def _tp():
    from . import templates
    return templates


def _ins():
    from . import insights
    return insights


GET["/api/templates"] = _reader(lambda c, q: {"rows": _tp().listing(c)})
GET["/api/template"] = _reader(lambda c, q: _tp().as_voucher(c, _int(q, "id", True), dt_today()))
POST["/api/template/save"] = _writer(lambda c, b: _tp().save_from_voucher(c, b))
POST["/api/template/repeat"] = _writer(lambda c, b: _tp().set_repeat(c, b))
POST["/api/template/delete"] = _writer(lambda c, b: _tp().delete(c, int(b.get("id") or 0)) or {"ok": True})
GET["/api/repeats/due"] = _reader(lambda c, q: {"rows": _tp().due(c, dt_today())})
POST["/api/repeats/run"] = _writer(lambda c, b: _tp().run_due(c, b, dt_today()))
GET["/api/insights/spending"] = _reader(lambda c, q: _ins().spending(c, q.get("from"), q.get("to"), q.get("nature") or "expense"))
GET["/api/insights/yoy"] = _reader(lambda c, q: _ins().yoy(c, q.get("on") or dt_today()))
GET["/api/alerts"] = _reader(lambda c, q: {"rows": _ins().alerts(c, dt_today())})
