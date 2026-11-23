"""Several companies (books), like Tally's company list.

The first book is the original homeledger.db. Others live in <data>/companies/<id>.db, each with its own
backup folder. The registry (companies.json) is tiny and is rewritten atomically; if it is missing or damaged
HomeLedger simply opens the original book, so this can never stop the app from starting.
"""
import datetime as dt
import json
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path

from . import config, db as dbm
from .errors import UserError
from .money import parse_iso


def _reg_file() -> Path:
    return config.data_dir() / "companies.json"


def _load() -> dict:
    try:
        d = json.loads(_reg_file().read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("companies"), list):
            return d
    except (OSError, ValueError):
        pass
    return {"current": "main", "companies": []}


def _save(d: dict) -> None:
    tmp = _reg_file().with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
    os.replace(tmp, _reg_file())


def paths(cid: str):
    """(database file, backup folder) for a company id."""
    if cid == "main":
        return config.db_path(), config.backup_dir()
    base = config.data_dir() / "companies"
    return base / f"{cid}.db", base / f"{cid}-backups"


def _name_of(db_file: Path) -> str:
    try:
        c = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True, timeout=5)
        try:
            r = c.execute("SELECT name, books_begin FROM company WHERE id=1").fetchone()
            return (r[0], r[1]) if r else ("(unreadable)", "")
        finally:
            c.close()
    except sqlite3.Error:
        return "(unreadable)", ""


def current_id() -> str:
    d = _load()
    cur = d.get("current") or "main"
    return cur if cur == "main" or any(c["id"] == cur and paths(cur)[0].exists() for c in d["companies"]) else "main"


def listing() -> list:
    d = _load()
    cur = current_id()
    ids = ["main"] + [c["id"] for c in d["companies"] if paths(c["id"])[0].exists()]
    out = []
    for cid in ids:
        f, _ = paths(cid)
        name, begin = _name_of(f) if f.exists() else ("(missing)", "")
        size = f.stat().st_size if f.exists() else 0
        out.append({"id": cid, "name": name, "books_begin": begin, "size": size, "current": cid == cur})
    return out


def set_current(cid: str) -> None:
    if cid != "main" and not any(c["id"] == cid for c in _load()["companies"]):
        raise UserError("That company is not in the list.")
    if not paths(cid)[0].exists():
        raise UserError("The data file of that company is missing.")
    d = _load()
    d["current"] = cid
    _save(d)


def _register(cid: str) -> None:
    d = _load()
    if not any(c["id"] == cid for c in d["companies"]):
        d["companies"].append({"id": cid})
    _save(d)


def _new_id() -> str:
    return time.strftime("%y%m%d") + "-" + uuid.uuid4().hex[:6]


def create(name: str, books_begin: str | None = None) -> str:
    name = (name or "").strip()
    if not name:
        raise UserError("Please type the company name.")
    cid = _new_id()
    f, b = paths(cid)
    f.parent.mkdir(parents=True, exist_ok=True)
    b.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".new")
    try:
        dbm._create_fresh(tmp)
        c = dbm.connect(tmp)
        try:
            with dbm.write_tx(c):
                if books_begin:
                    books_begin = parse_iso(books_begin, "Books beginning date")
                    c.execute("UPDATE company SET name=?, books_begin=? WHERE id=1", (name, books_begin))
                else:
                    c.execute("UPDATE company SET name=? WHERE id=1", (name,))
        finally:
            c.close()
        for ext in ("-wal", "-shm"):
            Path(str(tmp) + ext).unlink(missing_ok=True)
        os.replace(tmp, f)
    except BaseException:
        for ext in ("", "-wal", "-shm"):
            Path(str(tmp) + ext).unlink(missing_ok=True)
        raise
    _register(cid)
    return cid


def remove_from_list(cid: str) -> None:
    """Take a company off the list. Its files are NOT deleted (they stay in the companies folder)."""
    if cid == "main":
        raise UserError("The first company cannot be removed from the list.")
    if cid == current_id():
        raise UserError("Close this company first (open another one), then remove it.")
    d = _load()
    d["companies"] = [c for c in d["companies"] if c["id"] != cid]
    _save(d)


PRACTICE_PREFIX = "Practice Books"


def discard_practice(cid: str) -> None:
    """Delete a practice company made by the guided tour (files and list entry). Refuses anything else."""
    if cid == "main" or cid == current_id():
        raise UserError("Open your real books first, then remove the practice books.")
    row = next((c for c in listing() if c["id"] == cid), None)
    if not row:
        return
    if not row["name"].startswith(PRACTICE_PREFIX):
        raise UserError("Only practice books made by the tour can be discarded here.")
    f, b = paths(cid)
    for ext in ("", "-wal", "-shm"):
        Path(str(f) + ext).unlink(missing_ok=True)
    if b.exists():
        import shutil
        shutil.rmtree(b, ignore_errors=True)
    d = _load()
    d["companies"] = [c for c in d["companies"] if c["id"] != cid]
    _save(d)


# ---------------------------------------------------------------------------
# carry-forward: split / year-end close
# ---------------------------------------------------------------------------
def _copy_db(src: Path, dst: Path) -> None:
    s = sqlite3.connect(str(src), timeout=30)
    try:
        d = sqlite3.connect(str(dst))
        try:
            s.backup(d)
        finally:
            d.close()
    finally:
        s.close()


def carry_forward(src_conn, src_file: Path, cutoff: str, new_name: str) -> str:
    """Create a new company holding everything of `src` from `cutoff` onwards.

    Balance-sheet ledgers start with their closing balance as on the day before `cutoff`; the profit or loss
    of the earlier years is carried into 'Profit & Loss A/c (carried forward)'; stock items start with their
    closing quantity and value. The original company is not changed.
    """
    from . import reports as rp, inventory as inv
    cutoff = parse_iso(cutoff, "New books beginning")
    cur = dbm.get_company(src_conn)
    if cutoff <= cur["books_begin"]:
        raise UserError("The new books must begin after the present books beginning date.")
    last = (dt.date.fromisoformat(cutoff) - dt.timedelta(days=1)).isoformat()
    rows = rp.ledger_rows(src_conn, cutoff, "9999-12-31")      # 'opening' = balance carried to cutoff
    stock = inv.summary(src_conn, "0000-00-00", last)
    pending = src_conn.execute(
        "SELECT COUNT(*) FROM vouchers WHERE vdate < ? AND status IN ('memo','optional')", (cutoff,)).fetchone()[0]

    cid = _new_id()
    f, b = paths(cid)
    f.parent.mkdir(parents=True, exist_ok=True)
    b.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".new")
    try:
        _copy_db(src_file, tmp)
        c = dbm.connect(tmp)
        try:
            c.execute("PRAGMA journal_mode = DELETE")
            with dbm.write_tx(c):
                c.execute("DELETE FROM vouchers WHERE vdate < ?", (cutoff,))   # entries etc. go with them
                pl = 0
                for r in rows:
                    if r["nature"] in ("income", "expense"):
                        pl += r["before_net"]            # Dr positive
                        continue
                    v = r["opening"]
                    c.execute("UPDATE ledgers SET opening_paise=?, opening_type=? WHERE id=?",
                              (abs(v), "Dr" if v >= 0 else "Cr", r["id"]))
                if pl:
                    g = c.execute("SELECT id FROM acct_groups WHERE code='RESERVES'").fetchone()
                    lid = c.execute("SELECT id FROM ledgers WHERE name='Profit & Loss A/c (carried forward)'").fetchone()
                    if lid:
                        lid = lid[0]
                    else:
                        lid = c.execute(
                            "INSERT INTO ledgers(name, group_id, nature, opening_paise, opening_type, created_at) "
                            "VALUES ('Profit & Loss A/c (carried forward)', ?, 'liability', 0, 'Cr', ?)",
                            (g[0], dbm.now_iso())).lastrowid
                    # Cr balance for a profit; the opening of a ledger that already had one is added
                    c.execute("UPDATE ledgers SET opening_paise=?, opening_type=? WHERE id=?",
                              (abs(pl), "Dr" if pl > 0 else "Cr", lid))
                # stock: closing becomes opening
                c.execute("UPDATE stock_items SET opening_qty_milli=0, opening_value_paise=0")
                for s in stock:
                    if s["close_q"] <= 0:
                        continue
                    hit = c.execute("SELECT id FROM stock_items WHERE lower(name)=lower(?)", (s["name"],)).fetchone()
                    if hit:
                        c.execute("UPDATE stock_items SET opening_qty_milli=?, opening_value_paise=? WHERE id=?",
                                  (s["close_q"], s["close_v"], hit[0]))
                    else:
                        c.execute("INSERT INTO stock_items(name, unit, opening_qty_milli, opening_value_paise, created_at) "
                                  "VALUES (?,?,?,?,?)", (s["name"], s["unit"] or "", s["close_q"], s["close_v"], dbm.now_iso()))
                c.execute("DELETE FROM entries WHERE item IS NOT NULL AND voucher_id NOT IN (SELECT id FROM vouchers)")
                c.execute("UPDATE company SET name=?, books_begin=? WHERE id=1", (new_name.strip() or cur["name"], cutoff))
                dbm.audit(c, "carry-forward", "company", 1,
                          f"Created from '{cur['name']}' with balances carried forward as on {last}")
            ok = c.execute("PRAGMA integrity_check").fetchone()[0]
            if ok != "ok":
                raise UserError("The new company failed its safety check, so it was not created. Nothing was changed.")
        finally:
            c.close()
        for ext in ("-wal", "-shm"):
            Path(str(tmp) + ext).unlink(missing_ok=True)
        os.replace(tmp, f)
    except BaseException:
        for ext in ("", "-wal", "-shm"):
            Path(str(tmp) + ext).unlink(missing_ok=True)
        raise
    _register(cid)
    return cid, pending


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------
def merge_from(dst_conn, src_file: Path) -> dict:
    """Copy the vouchers of another company into this one.

    Ledgers, groups, cost centres and stock items are matched by name and created when missing (a new ledger
    brings its opening balance; ledgers that already exist keep theirs). Voucher numbers continue this
    company's numbering. Vouchers dated before this company's books begin are skipped.
    """
    s = dbm.connect(src_file)
    s.row_factory = sqlite3.Row
    try:
        if s.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise UserError("That company's data file did not pass the safety check, so nothing was merged.")
        begin = dbm.get_company(dst_conn)["books_begin"]
        added = {"groups": 0, "ledgers": 0, "items": 0, "vouchers": 0, "skipped": 0}
        with dbm.write_tx(dst_conn):
            d = dst_conn
            # groups by name (parents first)
            sg = {r["id"]: r for r in s.execute("SELECT * FROM acct_groups")}
            gmap = {}

            def group(gid):
                if gid is None:
                    return None
                if gid in gmap:
                    return gmap[gid]
                r = sg[gid]
                hit = d.execute("SELECT id FROM acct_groups WHERE lower(name)=lower(?)", (r["name"],)).fetchone()
                if hit:
                    gmap[gid] = hit[0]
                else:
                    gmap[gid] = d.execute(
                        "INSERT INTO acct_groups(code, name, parent_id, nature, is_system, sort) VALUES (NULL,?,?,?,0,?)",
                        (r["name"], group(r["parent_id"]), r["nature"], r["sort"])).lastrowid
                    added["groups"] += 1
                return gmap[gid]
            for gid in sg:
                group(gid)
            # cost centres
            ccmap = {}
            for r in s.execute("SELECT * FROM cost_centres ORDER BY id"):
                hit = d.execute("SELECT id FROM cost_centres WHERE lower(name)=lower(?)", (r["name"],)).fetchone()
                ccmap[r["id"]] = hit[0] if hit else d.execute(
                    "INSERT INTO cost_centres(name, kind, is_active, sort) VALUES (?,?,1,?)", (r["name"], r["kind"], r["sort"])).lastrowid
            # ledgers
            lmap = {}
            for r in s.execute("SELECT * FROM ledgers ORDER BY id"):
                hit = d.execute("SELECT id FROM ledgers WHERE lower(name)=lower(?)", (r["name"],)).fetchone()
                if hit:
                    lmap[r["id"]] = hit[0]
                else:
                    lmap[r["id"]] = d.execute(
                        "INSERT INTO ledgers(name, group_id, nature, cb_kind, opening_paise, opening_type, is_active, notes, created_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (r["name"], group(r["group_id"]), r["nature"], r["cb_kind"], r["opening_paise"], r["opening_type"],
                         r["is_active"], r["notes"], dbm.now_iso())).lastrowid
                    added["ledgers"] += 1
            # stock items / godowns
            imap, gdmap = {}, {1: 1}
            for r in s.execute("SELECT * FROM godowns WHERE id<>1 ORDER BY id"):
                hit = d.execute("SELECT id FROM godowns WHERE lower(name)=lower(?)", (r["name"],)).fetchone()
                gdmap[r["id"]] = hit[0] if hit else d.execute("INSERT INTO godowns(name) VALUES (?)", (r["name"],)).lastrowid
            for r in s.execute("SELECT * FROM stock_items ORDER BY id"):
                hit = d.execute("SELECT id FROM stock_items WHERE lower(name)=lower(?)", (r["name"],)).fetchone()
                if hit:
                    imap[r["id"]] = hit[0]
                else:
                    imap[r["id"]] = d.execute(
                        "INSERT INTO stock_items(name, unit, opening_qty_milli, opening_value_paise, valuation, std_rate_paise, "
                        "track_batches, created_at) VALUES (?,?,?,?,?,?,?,?)",
                        (r["name"], r["unit"], r["opening_qty_milli"], r["opening_value_paise"], r["valuation"],
                         r["std_rate_paise"], r["track_batches"], dbm.now_iso())).lastrowid
                    added["items"] += 1
            # vouchers
            for v in s.execute("SELECT * FROM vouchers ORDER BY vdate, id"):
                if v["vdate"] < begin:
                    added["skipped"] += 1
                    continue
                fy = v["fy"]
                n = d.execute("SELECT COALESCE(MAX(number),0)+1 FROM vouchers WHERE vtype=? AND fy=?", (v["vtype"], fy)).fetchone()[0]
                vid = d.execute(
                    "INSERT INTO vouchers(vtype, fy, number, vdate, narration, ref, date_approx, status, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (v["vtype"], fy, n, v["vdate"], v["narration"], v["ref"], v["date_approx"], v["status"],
                     v["created_at"], v["updated_at"])).lastrowid
                for e in s.execute("SELECT * FROM entries WHERE voucher_id=? ORDER BY line_no", (v["id"],)):
                    d.execute("INSERT INTO entries(voucher_id, line_no, ledger_id, debit_paise, credit_paise, cc_id, item, qty_milli, unit) "
                              "VALUES (?,?,?,?,?,?,?,?,?)",
                              (vid, e["line_no"], lmap[e["ledger_id"]], e["debit_paise"], e["credit_paise"],
                               ccmap.get(e["cc_id"]), e["item"], e["qty_milli"], e["unit"]))
                m = s.execute("SELECT * FROM voucher_meta WHERE voucher_id=?", (v["id"],)).fetchone()
                if m:
                    d.execute("INSERT INTO voucher_meta(voucher_id, post_dated, inst_no, inst_date, bank_name, class_name) VALUES (?,?,?,?,?,?)",
                              (vid, m["post_dated"], m["inst_no"], m["inst_date"], m["bank_name"], m["class_name"]))
                cols = [r[1] for r in s.execute("PRAGMA table_info(voucher_items)") if r[1] not in ("id", "voucher_id", "item_id", "godown_id")]
                for it in s.execute("SELECT * FROM voucher_items WHERE voucher_id=?", (v["id"],)):
                    if it["item_id"] not in imap:
                        continue
                    d.execute(f"INSERT INTO voucher_items(voucher_id, item_id, godown_id, {','.join(cols)}) VALUES (?,?,?,{','.join('?' * len(cols))})",
                              (vid, imap[it["item_id"]], gdmap.get(it["godown_id"], 1), *[it[k] for k in cols]))
                added["vouchers"] += 1
            dbm.audit(d, "merge", "company", 1, json.dumps(added))
        return added
    finally:
        s.close()
