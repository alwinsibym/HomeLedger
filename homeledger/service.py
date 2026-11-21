"""Masters (groups, ledgers, activities) and vouchers. All money is integer paise."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3

from . import db as dbm
from .errors import UserError
from .money import fmt_inr, fy_label, parse_amount, parse_iso, parse_opening, parse_qty

VTYPES = ("Payment", "Receipt", "Contra", "Journal", "Sales", "Purchase", "Credit Note", "Debit Note",
          "Memorandum", "Reversing Journal")
NATURES = ("asset", "liability", "income", "expense")
REAL = ("asset", "liability")
NOMINAL = ("income", "expense")


def _txt(value, maxlen: int, field: str) -> str:
    s = " ".join(str(value or "").split())  # collapse whitespace/newlines
    if len(s) > maxlen:
        raise UserError(f"{field} is too long (maximum {maxlen} characters).")
    return s


def show_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}-{m}-{y}"


# =============================================================================
# Masters
# =============================================================================
def list_masters(conn, today: str) -> dict:
    company = dbm.get_company(conn)
    groups = [dict(r) for r in conn.execute(
        "SELECT id, code, name, parent_id, nature, is_system, sort FROM acct_groups ORDER BY sort, name")]
    ccs = [dict(r) for r in conn.execute(
        "SELECT id, name, parent_id, kind, is_active, sort FROM cost_centres ORDER BY sort, name")]
    ledgers = [dict(r) for r in conn.execute(
        """SELECT l.id, l.name, l.group_id, g.name AS group_name, l.nature, l.cb_kind, l.opening_paise,
                  l.opening_type, l.default_cc_id, l.is_active, l.notes,
                  (SELECT COUNT(*) FROM entries e WHERE e.ledger_id = l.id) AS n_entries
           FROM ledgers l JOIN acct_groups g ON g.id = l.group_id
           ORDER BY l.name COLLATE NOCASE""")]
    bal = {r["ledger_id"]: r["net"] for r in conn.execute(
        """SELECT e.ledger_id, SUM(e.debit_paise - e.credit_paise) AS net
           FROM entries e JOIN vouchers v ON v.id = e.voucher_id
           WHERE v.status = 'posted' AND v.vdate <= ? GROUP BY e.ledger_id""", (today,))}
    for l in ledgers:
        if l["nature"] in REAL:
            op = l["opening_paise"] if l["opening_type"] == "Dr" else -l["opening_paise"]
            l["balance_paise"] = op + bal.get(l["id"], 0)
        else:
            l["balance_paise"] = None
    items = [dict(r) for r in conn.execute(
        """SELECT item, COUNT(*) AS n, MAX(unit) AS unit FROM entries
           WHERE item IS NOT NULL AND item <> '' GROUP BY lower(item) ORDER BY n DESC, item LIMIT 500""")]
    units = [r[0] for r in conn.execute(
        "SELECT unit FROM entries WHERE unit IS NOT NULL AND unit <> '' GROUP BY lower(unit) ORDER BY COUNT(*) DESC")]
    last = conn.execute(
        "SELECT vdate FROM vouchers WHERE status='posted' ORDER BY updated_at DESC, id DESC LIMIT 1").fetchone()
    return {"company": company, "groups": groups, "ledgers": ledgers, "cost_centres": ccs,
            "items": items, "units": units, "last_vdate": last[0] if last else None}


def _group(conn, gid):
    r = conn.execute("SELECT * FROM acct_groups WHERE id=?", (gid,)).fetchone()
    if not r:
        raise UserError("That group no longer exists.")
    return r


def _cb_kind_for_group(conn, group_id):
    """'cash'/'bank' when the group sits under Cash-in-Hand / Bank Accounts."""
    gid = group_id
    seen = 0
    while gid is not None and seen < 20:
        r = conn.execute("SELECT code, parent_id FROM acct_groups WHERE id=?", (gid,)).fetchone()
        if not r:
            break
        if r["code"] == "CASH":
            return "cash"
        if r["code"] in ("BANK", "BANK_OD"):
            return "bank"
        gid = r["parent_id"]
        seen += 1
    return None


def save_ledger(conn, d: dict) -> dict:
    lid = d.get("id")
    name = _txt(d.get("name"), 60, "Ledger name")
    if not name:
        raise UserError("Please enter a ledger name.")
    grp = _group(conn, d.get("group_id"))
    nature = grp["nature"]
    cb = _cb_kind_for_group(conn, grp["id"])
    opening = parse_opening(d.get("opening")) if d.get("opening") not in (None, "") else int(d.get("opening_paise") or 0)
    otype = d.get("opening_type") or ("Cr" if nature == "liability" else "Dr")
    if otype not in ("Dr", "Cr"):
        raise UserError("Opening balance must be Dr or Cr.")
    if nature in NOMINAL and opening:
        raise UserError("Income and expense ledgers cannot have an opening balance. "
                        "Opening balances are only for assets and liabilities (cash, bank, loans, land...).")
    cc = d.get("default_cc_id") or None
    if cc and not conn.execute("SELECT 1 FROM cost_centres WHERE id=?", (cc,)).fetchone():
        raise UserError("The chosen cost centre no longer exists.")
    notes = _txt(d.get("notes"), 300, "Notes")
    with dbm.write_tx(conn):
        dup = conn.execute("SELECT id FROM ledgers WHERE name=? COLLATE NOCASE", (name,)).fetchone()
        if dup and dup["id"] != lid:
            raise UserError(f"A ledger named '{name}' already exists.")
        if lid:
            old = conn.execute("SELECT * FROM ledgers WHERE id=?", (lid,)).fetchone()
            if not old:
                raise UserError("That ledger no longer exists.")
            used = conn.execute("SELECT COUNT(*) FROM entries WHERE ledger_id=?", (lid,)).fetchone()[0]
            if used and (old["nature"] != nature or old["cb_kind"] != cb):
                raise UserError("This ledger already has entries, so it cannot be moved to a group of a different kind "
                                "(for example from Expenses to Assets, or into/out of Cash/Bank). "
                                "Create a new ledger instead.")
            conn.execute(
                """UPDATE ledgers SET name=?, group_id=?, nature=?, cb_kind=?, opening_paise=?, opening_type=?,
                          default_cc_id=?, is_active=?, notes=? WHERE id=?""",
                (name, grp["id"], nature, cb, opening, otype, cc, 0 if d.get("is_active") is False else 1, notes, lid))
            dbm.audit(conn, "alter", "ledger", lid, json.dumps({"before": dict(old), "name": name}))
        else:
            cur = conn.execute(
                """INSERT INTO ledgers(name, group_id, nature, cb_kind, opening_paise, opening_type, default_cc_id,
                                       is_active, notes, created_at) VALUES (?,?,?,?,?,?,?,1,?,?)""",
                (name, grp["id"], nature, cb, opening, otype, cc, notes, dbm.now_iso()))
            lid = cur.lastrowid
            dbm.audit(conn, "create", "ledger", lid, name)
    return {"id": lid}


def delete_ledger(conn, lid: int) -> None:
    with dbm.write_tx(conn):
        r = conn.execute("SELECT * FROM ledgers WHERE id=?", (lid,)).fetchone()
        if not r:
            raise UserError("That ledger no longer exists.")
        if conn.execute("SELECT 1 FROM entries WHERE ledger_id=?", (lid,)).fetchone():
            raise UserError("This ledger has entries and cannot be deleted. "
                            "Open it with Alter and untick 'Active' to hide it instead.")
        if r["opening_paise"]:
            raise UserError("This ledger has an opening balance. Set the opening balance to zero before deleting it.")
        conn.execute("DELETE FROM ledgers WHERE id=?", (lid,))
        dbm.audit(conn, "delete", "ledger", lid, r["name"])


def save_group(conn, d: dict) -> dict:
    gid = d.get("id")
    name = _txt(d.get("name"), 60, "Group name")
    if not name:
        raise UserError("Please enter a group name.")
    with dbm.write_tx(conn):
        dup = conn.execute("SELECT id FROM acct_groups WHERE name=? COLLATE NOCASE", (name,)).fetchone()
        if dup and dup["id"] != gid:
            raise UserError(f"A group named '{name}' already exists.")
        if gid:
            g = _group(conn, gid)
            if g["is_system"]:
                raise UserError("Built-in groups cannot be renamed.")
            conn.execute("UPDATE acct_groups SET name=? WHERE id=?", (name, gid))
            dbm.audit(conn, "alter", "group", gid, name)
        else:
            parent = _group(conn, d.get("parent_id"))
            cur = conn.execute(
                "INSERT INTO acct_groups(name, parent_id, nature, is_system, sort) VALUES (?,?,?,0,1000)",
                (name, parent["id"], parent["nature"]))
            gid = cur.lastrowid
            dbm.audit(conn, "create", "group", gid, name)
    return {"id": gid}


def delete_group(conn, gid: int) -> None:
    with dbm.write_tx(conn):
        g = _group(conn, gid)
        if g["is_system"]:
            raise UserError("Built-in groups cannot be deleted.")
        if conn.execute("SELECT 1 FROM ledgers WHERE group_id=?", (gid,)).fetchone() or \
                conn.execute("SELECT 1 FROM acct_groups WHERE parent_id=?", (gid,)).fetchone():
            raise UserError("This group is not empty. Move or delete its ledgers first.")
        conn.execute("DELETE FROM acct_groups WHERE id=?", (gid,))
        dbm.audit(conn, "delete", "group", gid, g["name"])


def save_cc(conn, d: dict) -> dict:
    cid = d.get("id")
    name = _txt(d.get("name"), 60, "Cost centre name")
    if not name:
        raise UserError("Please enter a cost centre name.")
    with dbm.write_tx(conn):
        dup = conn.execute("SELECT id FROM cost_centres WHERE name=? COLLATE NOCASE", (name,)).fetchone()
        if dup and dup["id"] != cid:
            raise UserError(f"A cost centre named '{name}' already exists.")
        if cid:
            if not conn.execute("SELECT 1 FROM cost_centres WHERE id=?", (cid,)).fetchone():
                raise UserError("That cost centre no longer exists.")
            conn.execute("UPDATE cost_centres SET name=?, is_active=? WHERE id=?",
                         (name, 0 if d.get("is_active") is False else 1, cid))
            dbm.audit(conn, "alter", "activity", cid, name)
        else:
            parent = conn.execute("SELECT * FROM cost_centres WHERE id=?", (d.get("parent_id"),)).fetchone() \
                if d.get("parent_id") else None
            cur = conn.execute(
                "INSERT INTO cost_centres(name, parent_id, kind, sort) VALUES (?,?,?,1000)",
                (name, parent["id"] if parent else None, parent["kind"] if parent else "other"))
            cid = cur.lastrowid
            dbm.audit(conn, "create", "activity", cid, name)
    return {"id": cid}


def delete_cc(conn, cid: int) -> None:
    with dbm.write_tx(conn):
        r = conn.execute("SELECT * FROM cost_centres WHERE id=?", (cid,)).fetchone()
        if not r:
            raise UserError("That cost centre no longer exists.")
        if conn.execute("SELECT 1 FROM entries WHERE cc_id=?", (cid,)).fetchone() or \
                conn.execute("SELECT 1 FROM ledgers WHERE default_cc_id=?", (cid,)).fetchone() or \
                conn.execute("SELECT 1 FROM cost_centres WHERE parent_id=?", (cid,)).fetchone():
            raise UserError("This cost centre is in use. Untick 'Active' to hide it instead of deleting.")
        conn.execute("DELETE FROM cost_centres WHERE id=?", (cid,))
        dbm.audit(conn, "delete", "activity", cid, r["name"])


def save_company(conn, d: dict) -> None:
    name = _txt(d.get("name"), 80, "Name")
    if not name:
        raise UserError("Please enter a name.")
    books = parse_iso(d.get("books_begin"), "Books beginning date")
    cur = dbm.get_company(conn)
    with dbm.write_tx(conn):
        if books > cur["books_begin"]:
            first = conn.execute("SELECT MIN(vdate) FROM vouchers WHERE status='posted'").fetchone()[0]
            if first and first < books:
                raise UserError(
                    f"There are already entries dated {show_date(first)}. "
                    f"The books beginning date cannot be later than that.")
        conn.execute("UPDATE company SET name=?, books_begin=? WHERE id=1", (name, books))
        dbm.audit(conn, "alter", "company", 1, json.dumps({"name": name, "books_begin": books}))


def set_openings(conn, items: list) -> dict:
    """items: [{ledger_id, amount, type}] -> sets opening balances for asset/liability ledgers."""
    with dbm.write_tx(conn):
        for it in items:
            r = conn.execute("SELECT * FROM ledgers WHERE id=?", (it.get("ledger_id"),)).fetchone()
            if not r:
                raise UserError("A ledger in the list no longer exists.")
            if r["nature"] not in REAL:
                raise UserError(f"'{r['name']}' is an income/expense ledger and cannot have an opening balance.")
            amt = parse_opening(it.get("amount"))
            typ = it.get("type") if it.get("type") in ("Dr", "Cr") else r["opening_type"]
            if amt != r["opening_paise"] or typ != r["opening_type"]:
                conn.execute("UPDATE ledgers SET opening_paise=?, opening_type=? WHERE id=?", (amt, typ, r["id"]))
                dbm.audit(conn, "opening", "ledger", r["id"],
                          f"{r['name']}: {fmt_inr(r['opening_paise'])} {r['opening_type']} -> {fmt_inr(amt)} {typ}")
        net = conn.execute(
            """SELECT COALESCE(SUM(CASE WHEN opening_type='Dr' THEN opening_paise ELSE -opening_paise END),0)
               FROM ledgers WHERE nature IN ('asset','liability')""").fetchone()[0]
    return {"difference_paise": net}


# =============================================================================
# Vouchers
# =============================================================================
def _canonical(conn, table_col: str, value: str):
    """Reuse the spelling already used for an item/unit (case-insensitive)."""
    if not value:
        return None
    r = conn.execute(f"SELECT {table_col} FROM entries WHERE lower({table_col}) = lower(?) LIMIT 1", (value,)).fetchone()
    return r[0] if r else value


def _prepare(conn, p: dict, existing: dict | None):
    vtype = p.get("vtype")
    if vtype not in VTYPES:
        raise UserError("Unknown voucher type.")
    vdate = parse_iso(p.get("date"), "Voucher date")
    company = dbm.get_company(conn)
    if vdate < company["books_begin"]:
        raise UserError(
            f"The date {show_date(vdate)} is before the books beginning date {show_date(company['books_begin'])}. "
            f"Choose a later date, or change the books beginning date in Company Info.")
    raw = p.get("lines")
    if not isinstance(raw, list) or not raw:
        raise UserError("Please enter at least one line.")
    if len(raw) > 80:
        raise UserError("Too many lines in one voucher (maximum 80).")
    ids = {int(x.get("ledger_id") or 0) for x in raw}
    ledgers = {}
    for lid in ids:
        r = conn.execute("SELECT * FROM ledgers WHERE id=?", (lid,)).fetchone()
        if not r:
            raise UserError("A ledger used in this voucher no longer exists.")
        ledgers[lid] = r
    keep_ids = {l["ledger_id"] for l in existing["lines"]} if existing else set()
    lines = []
    dr_total = cr_total = 0
    for i, x in enumerate(raw, 1):
        lid = int(x.get("ledger_id") or 0)
        led = ledgers[lid]
        if not led["is_active"] and lid not in keep_ids:
            raise UserError(f"Ledger '{led['name']}' is switched off (inactive).")
        side = x.get("side")
        if side not in ("Dr", "Cr"):
            raise UserError(f"Line {i}: choose Dr or Cr.")
        amt = parse_amount(x.get("amount"), f"Line {i} amount")
        item = _txt(x.get("item"), 60, f"Line {i} item")
        unit = _txt(x.get("unit"), 12, f"Line {i} unit")
        qty = parse_qty(x.get("qty"))
        if qty and not item:
            raise UserError(f"Line {i}: a quantity needs an item name (for example 'Urea').")
        if qty and not unit:
            raise UserError(f"Line {i}: please enter a unit for the quantity (kg, litre, nos...).")
        if unit and not qty:
            unit = ""
        cc = x.get("cc_id") or None
        if cc is not None:
            if not conn.execute("SELECT 1 FROM cost_centres WHERE id=?", (int(cc),)).fetchone():
                raise UserError(f"Line {i}: the chosen cost centre no longer exists.")
            cc = int(cc)
        elif led["default_cc_id"]:
            cc = led["default_cc_id"]
        if side == "Dr":
            dr_total += amt
        else:
            cr_total += amt
        lines.append({"ledger": led, "side": side, "amount": amt, "cc": cc, "bills_raw": x.get("bills") or [],
                      "item": _canonical(conn, "item", item) if item else None,
                      "qty": qty, "unit": _canonical(conn, "unit", unit) if unit else None})
    if dr_total != cr_total:
        diff = abs(dr_total - cr_total)
        raise UserError(f"The voucher does not balance: debit {fmt_inr(dr_total)} and credit {fmt_inr(cr_total)} "
                        f"differ by {fmt_inr(diff)}.")
    if not any(l["side"] == "Dr" for l in lines) or not any(l["side"] == "Cr" for l in lines):
        raise UserError("A voucher needs at least one debit and one credit line.")
    # voucher-type rules (keep transfers and cash handling honest)
    cb = lambda l: l["ledger"]["cb_kind"] is not None
    if vtype == "Payment":
        if any(l["side"] == "Cr" and not cb(l) for l in lines):
            raise UserError("In a Payment, the money must come from Cash or Bank. "
                            "Use a Journal (F7) or Purchase (F9) for entries that do not move cash or bank.")
        if any(l["side"] == "Dr" and cb(l) for l in lines):
            raise UserError("A Payment cannot add money to a Cash/Bank account. "
                            "Use Contra (F4) to move money between Cash and Bank.")
    elif vtype == "Receipt":
        if any(l["side"] == "Dr" and not cb(l) for l in lines):
            raise UserError("In a Receipt, the money must go into Cash or Bank. "
                            "Use a Journal (F7) or Sales (F8) for entries that do not move cash or bank.")
        if any(l["side"] == "Cr" and cb(l) for l in lines):
            raise UserError("A Receipt cannot take money out of a Cash/Bank account. "
                            "Use Contra (F4) to move money between Cash and Bank.")
    elif vtype == "Contra":
        if any(not cb(l) for l in lines):
            raise UserError("A Contra can only use Cash and Bank accounts (moving money between them).")
    elif vtype in ("Journal", "Reversing Journal"):
        if any(cb(l) for l in lines):
            raise UserError("A Journal cannot use Cash or Bank accounts. Use Payment (F5) or Receipt (F6).")
    elif vtype in ("Credit Note", "Debit Note"):
        if any(cb(l) for l in lines):
            raise UserError(f"A {vtype} cannot use Cash or Bank accounts. Settle it with a Payment (F5) or Receipt (F6).")
    narration = _txt(p.get("narration"), 500, "Narration")
    ref = _txt(p.get("ref"), 60, "Reference")
    return {"vtype": vtype, "vdate": vdate, "lines": lines, "narration": narration, "ref": ref,
            "status": ("memo" if vtype == "Memorandum" else p.get("status") if p.get("status") in ("posted", "optional", "memo") else "posted"),
            "date_approx": 1 if p.get("date_approx") else 0, "fy": fy_label(vdate, company["fy_start_month"])}


def get_voucher(conn, vid: int) -> dict:
    v = conn.execute("SELECT * FROM vouchers WHERE id=?", (vid,)).fetchone()
    if not v:
        raise UserError("That voucher no longer exists.")
    lines = []
    for r in conn.execute(
            """SELECT e.id, e.line_no, e.ledger_id, l.name AS ledger_name, l.nature, l.cb_kind,
                      e.debit_paise, e.credit_paise, e.cc_id, c.name AS cc_name, e.item, e.qty_milli, e.unit
               FROM entries e JOIN ledgers l ON l.id = e.ledger_id LEFT JOIN cost_centres c ON c.id = e.cc_id
               WHERE e.voucher_id = ? ORDER BY e.line_no""", (vid,)):
        lines.append({
            "id": r["id"], "ledger_id": r["ledger_id"], "ledger_name": r["ledger_name"], "nature": r["nature"],
            "cb_kind": r["cb_kind"], "side": "Dr" if r["debit_paise"] else "Cr",
            "amount_paise": r["debit_paise"] or r["credit_paise"], "cc_id": r["cc_id"], "cc_name": r["cc_name"],
            "item": r["item"] or "", "qty_milli": r["qty_milli"], "unit": r["unit"] or ""})
    total = sum(l["amount_paise"] for l in lines if l["side"] == "Dr")
    return {"id": v["id"], "vtype": v["vtype"], "fy": v["fy"], "number": v["number"], "date": v["vdate"],
            "narration": v["narration"], "ref": v["ref"], "date_approx": bool(v["date_approx"]),
            "status": v["status"], "created_at": v["created_at"], "updated_at": v["updated_at"],
            "lines": lines, "total_paise": total, "meta": get_meta(conn, vid), "bills": get_bills(conn, vid)}


def get_bills(conn, vid: int) -> list:
    return [dict(r) for r in conn.execute(
        "SELECT ledger_id, side, ref_name AS ref, kind, amount_paise, due_date FROM bill_refs WHERE voucher_id=? ORDER BY id", (vid,))]


def _party_group_ids(conn, code: str) -> set:
    groups = conn.execute("SELECT id, parent_id, code FROM acct_groups").fetchall()
    kids = {}
    for g in groups:
        kids.setdefault(g["parent_id"], []).append(g["id"])
    root = [g["id"] for g in groups if g["code"] == code]
    out, stack = set(), list(root)
    while stack:
        i = stack.pop()
        out.add(i)
        stack.extend(kids.get(i, []))
    return out


def _save_bills(conn, vid: int, d: dict) -> None:
    """Bill-wise references on Sundry Debtor / Creditor lines: New Ref, Against Ref, Advance."""
    party = _party_group_ids(conn, "DEBTORS") | _party_group_ids(conn, "CREDITORS")
    for n, l in enumerate(d["lines"], 1):
        raw = l.get("bills_raw") or []
        if not raw:
            continue
        led = l["ledger"]
        if led["group_id"] not in party:
            raise UserError(f"Line {n}: bill references can only be used for Sundry Debtors and Sundry Creditors.")
        total = 0
        seen = set()
        for b in raw:
            ref = _txt(b.get("ref"), 40, "Bill reference")
            if not ref:
                raise UserError(f"Line {n}: every bill allocation needs a reference name or number.")
            kind = b.get("kind")
            if kind not in ("new", "against", "advance"):
                raise UserError(f"Line {n}: choose New Ref, Against Ref or Advance for '{ref}'.")
            amt = parse_amount(b.get("amount"), f"Bill '{ref}' amount")
            if not amt:
                raise UserError(f"Line {n}: please enter an amount for bill '{ref}'.")
            if (ref.lower(), kind) in seen:
                raise UserError(f"Line {n}: bill '{ref}' is listed twice.")
            seen.add((ref.lower(), kind))
            due = parse_iso(b["due"], "Due date") if b.get("due") else None
            if kind == "against":
                # must settle an existing bill of this party: one raised on the opposite side
                row = conn.execute(
                    "SELECT 1 FROM bill_refs WHERE ledger_id=? AND ref_name=? COLLATE NOCASE AND side<>? AND voucher_id<>? LIMIT 1",
                    (led["id"], ref, l["side"], vid)).fetchone()
                if not row:
                    raise UserError(f"Line {n}: there is no open bill '{ref}' for {led['name']} to settle. Use New Ref to create it first.")
            elif conn.execute("SELECT 1 FROM bill_refs WHERE ledger_id=? AND ref_name=? COLLATE NOCASE AND kind IN ('new') AND side=? AND voucher_id<>? LIMIT 1",
                              (led["id"], ref, l["side"], vid)).fetchone() and kind == "new":
                raise UserError(f"Line {n}: a bill named '{ref}' already exists for {led['name']}. Use Against Ref to settle it, or a different name.")
            total += amt
            conn.execute("INSERT INTO bill_refs(voucher_id, ledger_id, side, ref_name, kind, amount_paise, due_date) VALUES (?,?,?,?,?,?,?)",
                         (vid, led["id"], l["side"], ref, kind, amt, due))
        if total > l["amount"]:
            raise UserError(f"Line {n}: bill amounts ({fmt_inr(total)}) are more than the line amount ({fmt_inr(l['amount'])}).")


def get_meta(conn, vid: int) -> dict:
    r = conn.execute("SELECT post_dated, inst_no, inst_date, bank_name, class_name FROM voucher_meta WHERE voucher_id=?", (vid,)).fetchone()
    if not r:
        return {"post_dated": False, "inst_no": "", "inst_date": None, "bank_name": "", "class_name": ""}
    return {"post_dated": bool(r["post_dated"]), "inst_no": r["inst_no"], "inst_date": r["inst_date"],
            "bank_name": r["bank_name"], "class_name": r["class_name"]}


def _save_meta(conn, vid: int, m: dict, vdate: str) -> None:
    m = m or {}
    inst_no = _txt(m.get("inst_no"), 30, "Cheque / instrument number")
    inst_date = parse_iso(m["inst_date"], "Cheque date") if m.get("inst_date") else None
    bank = _txt(m.get("bank_name"), 60, "Bank name")
    cls = _txt(m.get("class_name"), 40, "Voucher class")
    pd = 1 if m.get("post_dated") else 0
    if not (pd or inst_no or inst_date or bank or cls):
        conn.execute("DELETE FROM voucher_meta WHERE voucher_id=?", (vid,))
        return
    conn.execute("INSERT OR REPLACE INTO voucher_meta(voucher_id, post_dated, inst_no, inst_date, bank_name, class_name) VALUES (?,?,?,?,?,?)",
                 (vid, pd, inst_no, inst_date, bank, cls))


def _write_lines(conn, vid, lines):
    for i, l in enumerate(lines, 1):
        conn.execute(
            """INSERT INTO entries(voucher_id, line_no, ledger_id, debit_paise, credit_paise, cc_id, item, qty_milli, unit)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (vid, i, l["ledger"]["id"], l["amount"] if l["side"] == "Dr" else 0,
             l["amount"] if l["side"] == "Cr" else 0, l["cc"], l["item"], l["qty"], l["unit"]))


def _verify_balanced(conn, vid):
    r = conn.execute("SELECT COALESCE(SUM(debit_paise),0), COALESCE(SUM(credit_paise),0), COUNT(*) "
                     "FROM entries WHERE voucher_id=?", (vid,)).fetchone()
    if r[0] != r[1] or r[2] < 2:
        raise UserError("Internal check failed: the voucher did not balance, so nothing was saved.")


def save_voucher(conn, p: dict) -> dict:
    vid = p.get("id")
    with dbm.write_tx(conn):
        existing = get_voucher(conn, vid) if vid else None
        if existing and existing["status"] == "cancelled":
            raise UserError("This voucher is cancelled. Restore it first if you want to change it.")
        if existing and existing["vtype"] != p.get("vtype"):
            raise UserError("The voucher type of an existing voucher cannot be changed.")
        d = _prepare(conn, p, existing)
        if (p.get("meta") or {}).get("post_dated"):
            if d["status"] == "posted":
                d["status"] = "optional"          # a post-dated voucher stays out of the books until it is activated
        now = dbm.now_iso()
        if existing:
            number = existing["number"]
            if d["fy"] != existing["fy"]:
                number = _next_number(conn, d["vtype"], d["fy"])
            conn.execute(
                """UPDATE vouchers SET fy=?, number=?, vdate=?, narration=?, ref=?, date_approx=?, status=?, updated_at=?
                   WHERE id=?""",
                (d["fy"], number, d["vdate"], d["narration"], d["ref"], d["date_approx"], d["status"], now, vid))
            conn.execute("DELETE FROM entries WHERE voucher_id=?", (vid,))
            action = "alter"
        else:
            number = _next_number(conn, d["vtype"], d["fy"])
            cur = conn.execute(
                """INSERT INTO vouchers(vtype, fy, number, vdate, narration, ref, date_approx, status, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (d["vtype"], d["fy"], number, d["vdate"], d["narration"], d["ref"], d["date_approx"], d["status"], now, now))
            vid = cur.lastrowid
            action = "create"
        _write_lines(conn, vid, d["lines"])
        _verify_balanced(conn, vid)
        conn.execute("DELETE FROM bill_refs WHERE voucher_id=?", (vid,))
        _save_bills(conn, vid, d)
        if "meta" in p:
            _save_meta(conn, vid, p.get("meta"), d["vdate"])
        after = get_voucher(conn, vid)
        dbm.audit(conn, action, "voucher", vid, json.dumps({"before": existing, "after": after}, default=str))
    return after


def _next_number(conn, vtype, fy) -> int:
    return conn.execute("SELECT COALESCE(MAX(number),0)+1 FROM vouchers WHERE vtype=? AND fy=?",
                        (vtype, fy)).fetchone()[0]


def next_number(conn, vtype: str, vdate: str) -> int:
    if vtype not in VTYPES:
        raise UserError("Unknown voucher type.")
    fy = fy_label(parse_iso(vdate), dbm.get_company(conn)["fy_start_month"])
    return _next_number(conn, vtype, fy)


def delete_voucher(conn, vid: int) -> dict:
    """Alt+D in Tally: remove a voucher for good. The full voucher is kept in the audit log."""
    with dbm.write_tx(conn):
        v = get_voucher(conn, vid)
        conn.execute("DELETE FROM entries WHERE voucher_id=?", (vid,))
        conn.execute("DELETE FROM vouchers WHERE id=?", (vid,))
        dbm.audit(conn, "delete", "voucher", vid, json.dumps({"before": v}, default=str))
    return {"ok": True}


def set_voucher_status(conn, vid: int, status: str) -> dict:
    if status not in ("posted", "cancelled", "optional", "memo"):
        raise UserError("Unknown voucher status.")
    with dbm.write_tx(conn):
        v = get_voucher(conn, vid)
        if v["status"] == status:
            return v
        conn.execute("UPDATE vouchers SET status=?, updated_at=? WHERE id=?", (status, dbm.now_iso(), vid))
        dbm.audit(conn, "cancel" if status == "cancelled" else "restore", "voucher", vid,
                  json.dumps({"vtype": v["vtype"], "number": v["number"], "fy": v["fy"], "date": v["date"],
                              "total": v["total_paise"]}))
    return get_voucher(conn, vid)


# =============================================================================
# Day book
# =============================================================================
def _particulars(v_lines, vtype):
    """Short description of who/what a voucher is for, in Tally Day Book style."""
    def names(side, non_cb_only=True):
        out = []
        for l in v_lines:
            if l["side"] != side:
                continue
            if non_cb_only and l["cb_kind"]:
                continue
            if l["ledger_name"] not in out:
                out.append(l["ledger_name"])
        return out
    if vtype == "Payment":
        n = names("Dr")
    elif vtype == "Receipt":
        n = names("Cr")
    elif vtype == "Contra":
        to, frm = names("Dr", False), names("Cr", False)
        return ", ".join(to) + (" \u2190 " + ", ".join(frm) if frm else "")
    else:
        n = names("Dr", False) or names("Cr", False)
    return ", ".join(n)


def day_book(conn, frm: str, to: str, vtype: str | None = None, include_cancelled: bool = False,
             limit: int = 5000) -> dict:
    q = "SELECT id FROM vouchers WHERE vdate BETWEEN ? AND ?"
    a = [parse_iso(frm), parse_iso(to)]
    if not include_cancelled:
        q += " AND status='posted'"
    if vtype:
        if vtype not in VTYPES:
            raise UserError("Unknown voucher type.")
        q += " AND vtype=?"
        a.append(vtype)
    q += " ORDER BY vdate, id LIMIT ?"
    a.append(limit + 1)
    ids = [r[0] for r in conn.execute(q, a)]
    truncated = len(ids) > limit
    ids = ids[:limit]
    rows = []
    tdr = 0
    for vid in ids:
        v = get_voucher(conn, vid)
        items = []
        for l in v["lines"]:
            if l["item"] and l["item"] not in items:
                items.append(l["item"])
        ccs = []
        for l in v["lines"]:
            if l["cc_name"] and not l["cb_kind"] and l["cc_name"] not in ccs:
                ccs.append(l["cc_name"])
        rows.append({"id": v["id"], "date": v["date"], "vtype": v["vtype"], "number": v["number"], "fy": v["fy"],
                     "particulars": _particulars(v["lines"], v["vtype"]), "amount_paise": v["total_paise"],
                     "narration": v["narration"], "items": ", ".join(items), "activities": ", ".join(ccs),
                     "status": v["status"], "ref": v["ref"], "date_approx": v["date_approx"]})
        if v["status"] == "posted":
            tdr += v["total_paise"]
    return {"rows": rows, "total_paise": tdr, "truncated": truncated}


def set_bank_date(conn, voucher_id: int, ledger_id: int, bank_date) -> dict:
    """Mark a bank entry as processed by the bank on a date (or clear the mark with an empty date)."""
    with dbm.write_tx(conn):
        ok = conn.execute("""SELECT 1 FROM entries e JOIN ledgers l ON l.id=e.ledger_id
                             WHERE e.voucher_id=? AND e.ledger_id=? AND l.cb_kind='bank'""", (voucher_id, ledger_id)).fetchone()
        if not ok:
            raise UserError("That entry is not in a bank account.")
        if bank_date:
            conn.execute("INSERT OR REPLACE INTO bank_clearing(voucher_id, ledger_id, bank_date) VALUES (?,?,?)",
                         (voucher_id, ledger_id, parse_iso(bank_date, "Bank date")))
        else:
            conn.execute("DELETE FROM bank_clearing WHERE voucher_id=? AND ledger_id=?", (voucher_id, ledger_id))
        dbm.audit(conn, "bank_date", "voucher", voucher_id, json.dumps({"ledger": ledger_id, "bank_date": bank_date or None}))
    return {"ok": True}


# =============================================================================
# Stock items (inventory masters)
# =============================================================================
def list_stock_items(conn) -> list:
    return [dict(r) for r in conn.execute(
        "SELECT id, name, unit, opening_qty_milli, opening_value_paise FROM stock_items ORDER BY name COLLATE NOCASE")]


def save_stock_item(conn, d: dict) -> dict:
    sid = d.get("id")
    name = _txt(d.get("name"), 60, "Item name")
    if not name:
        raise UserError("Please enter the item name.")
    unit = _txt(d.get("unit"), 12, "Unit")
    qty = parse_qty(d.get("opening_qty")) if str(d.get("opening_qty") or "").strip() else 0
    val = parse_amount(d.get("opening_value")) if str(d.get("opening_value") or "").strip() else 0
    if qty < 0 or val < 0:
        raise UserError("Opening quantity and value cannot be negative.")
    if val and not qty:
        raise UserError("An opening value needs an opening quantity.")
    with dbm.write_tx(conn):
        dup = conn.execute("SELECT id FROM stock_items WHERE name=? COLLATE NOCASE", (name,)).fetchone()
        if dup and dup["id"] != sid:
            raise UserError(f"A stock item named '{name}' already exists.")
        if sid:
            if not conn.execute("SELECT 1 FROM stock_items WHERE id=?", (sid,)).fetchone():
                raise UserError("That stock item no longer exists.")
            conn.execute("UPDATE stock_items SET name=?, unit=?, opening_qty_milli=?, opening_value_paise=? WHERE id=?",
                         (name, unit, qty, val, sid))
            dbm.audit(conn, "alter", "stock_item", sid, name)
        else:
            sid = conn.execute("INSERT INTO stock_items(name, unit, opening_qty_milli, opening_value_paise, created_at) VALUES (?,?,?,?,?)",
                               (name, unit, qty, val, dbm.now_iso())).lastrowid
            dbm.audit(conn, "create", "stock_item", sid, name)
    return {"id": sid}


def delete_stock_item(conn, sid: int) -> None:
    with dbm.write_tx(conn):
        r = conn.execute("SELECT name FROM stock_items WHERE id=?", (sid,)).fetchone()
        if not r:
            raise UserError("That stock item no longer exists.")
        used = conn.execute("SELECT 1 FROM entries WHERE lower(trim(item))=lower(?) LIMIT 1", (r["name"],)).fetchone()
        if used:
            raise UserError("This item is used in vouchers, so it cannot be deleted.")
        conn.execute("DELETE FROM stock_items WHERE id=?", (sid,))
        dbm.audit(conn, "delete", "stock_item", sid, r["name"])


# =============================================================================
# Post-dated vouchers, cheque register, voucher classes
# =============================================================================
def activate_postdated(conn, vid: int) -> dict:
    """Bring a post-dated voucher into the books (its date has arrived and the cheque is being honoured)."""
    with dbm.write_tx(conn):
        v = get_voucher(conn, vid)
        if not v["meta"]["post_dated"]:
            raise UserError("This is not a post-dated voucher.")
        conn.execute("UPDATE vouchers SET status='posted', updated_at=? WHERE id=?", (dbm.now_iso(), vid))
        conn.execute("UPDATE voucher_meta SET post_dated=0 WHERE voucher_id=?", (vid,))
        dbm.audit(conn, "activate", "voucher", vid, "post-dated voucher activated")
    return {"ok": True}


def list_postdated(conn) -> list:
    return [dict(r) for r in conn.execute(
        """SELECT v.id, v.vtype, v.number, v.vdate, v.narration, m.inst_no, m.inst_date, m.bank_name,
                  (SELECT COALESCE(SUM(debit_paise),0) FROM entries WHERE voucher_id=v.id) AS amount_paise
           FROM vouchers v JOIN voucher_meta m ON m.voucher_id=v.id
           WHERE m.post_dated=1 AND v.status<>'cancelled' ORDER BY v.vdate, v.id""")]


def cheque_register(conn, frm: str, to: str) -> list:
    frm, to = parse_iso(frm), parse_iso(to)
    out = []
    for r in conn.execute(
            """SELECT v.id, v.vtype, v.number, v.vdate, v.status, v.narration, m.inst_no, m.inst_date, m.bank_name, m.post_dated,
                      (SELECT COALESCE(SUM(debit_paise),0) FROM entries WHERE voucher_id=v.id) AS amount_paise,
                      (SELECT group_concat(l.name, ', ') FROM entries e JOIN ledgers l ON l.id=e.ledger_id
                        WHERE e.voucher_id=v.id AND l.cb_kind IS NULL) AS party,
                      (SELECT group_concat(l.name, ', ') FROM entries e JOIN ledgers l ON l.id=e.ledger_id
                        WHERE e.voucher_id=v.id AND l.cb_kind='bank') AS bank_ledger
               FROM vouchers v JOIN voucher_meta m ON m.voucher_id=v.id
               WHERE m.inst_no<>'' AND v.vdate BETWEEN ? AND ? AND v.status<>'cancelled' ORDER BY v.vdate, v.id""", (frm, to)):
        out.append(dict(r))
    return out


def save_class(conn, d: dict) -> dict:
    name = _txt(d.get("name"), 40, "Class name")
    if not name:
        raise UserError("Please enter a class name.")
    vt = d.get("vtype")
    if vt not in VTYPES:
        raise UserError("Choose a voucher type.")
    lines = []
    for l in d.get("lines") or []:
        lid = int(l.get("ledger_id") or 0)
        if not conn.execute("SELECT 1 FROM ledgers WHERE id=?", (lid,)).fetchone():
            raise UserError("A ledger in this class no longer exists.")
        lines.append({"ledger_id": lid, "side": "Cr" if l.get("side") == "Cr" else "Dr"})
    with dbm.write_tx(conn):
        cid = d.get("id")
        dup = conn.execute("SELECT id FROM voucher_classes WHERE name=? COLLATE NOCASE", (name,)).fetchone()
        if dup and dup["id"] != cid:
            raise UserError(f"A class named '{name}' already exists.")
        if cid:
            conn.execute("UPDATE voucher_classes SET name=?, vtype=?, lines_json=? WHERE id=?", (name, vt, json.dumps(lines), cid))
        else:
            cid = conn.execute("INSERT INTO voucher_classes(name, vtype, lines_json) VALUES (?,?,?)", (name, vt, json.dumps(lines))).lastrowid
        dbm.audit(conn, "save", "voucher_class", cid, name)
    return {"id": cid}


def list_classes(conn) -> list:
    out = []
    for r in conn.execute("SELECT id, name, vtype, lines_json FROM voucher_classes ORDER BY vtype, name COLLATE NOCASE"):
        out.append({"id": r["id"], "name": r["name"], "vtype": r["vtype"], "lines": json.loads(r["lines_json"])})
    return out


def delete_class(conn, cid: int) -> None:
    with dbm.write_tx(conn):
        conn.execute("DELETE FROM voucher_classes WHERE id=?", (cid,))
        dbm.audit(conn, "delete", "voucher_class", cid, "")


def open_bills(conn, ledger_id: int, exclude_voucher: int = 0) -> list:
    """Bills of one party that still have something pending (for the 'Against Ref' picker)."""
    led = conn.execute("SELECT group_id FROM ledgers WHERE id=?", (ledger_id,)).fetchone()
    if not led:
        return []
    nat = "Dr" if led["group_id"] in _party_group_ids(conn, "DEBTORS") else "Cr"
    m = {}
    for br in conn.execute("SELECT ref_name, side, amount_paise, due_date FROM bill_refs br JOIN vouchers v ON v.id=br.voucher_id "
                           "WHERE br.ledger_id=? AND v.status='posted' AND v.id<>? ORDER BY br.id", (ledger_id, exclude_voucher)):
        b = m.setdefault(br["ref_name"].lower(), {"ref": br["ref_name"], "due": br["due_date"], "pending": 0})
        b["pending"] += br["amount_paise"] if br["side"] == nat else -br["amount_paise"]
    return [b for b in m.values() if b["pending"] != 0]


# =============================================================================
# Budgets
# =============================================================================
def save_budget(conn, d: dict) -> dict:
    kind = d.get("kind")
    if kind not in ("ledger", "group"):
        raise UserError("Choose a ledger or a group for the budget.")
    tid = int(d.get("target_id") or 0)
    table = "ledgers" if kind == "ledger" else "acct_groups"
    if not conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (tid,)).fetchone():
        raise UserError("That account no longer exists.")
    fy = _txt(d.get("fy"), 10, "Financial year")
    if not fy:
        raise UserError("Please choose the financial year.")
    amt = parse_amount(d.get("amount"), "Budget amount")
    with dbm.write_tx(conn):
        if amt == 0:
            conn.execute("DELETE FROM budgets WHERE kind=? AND target_id=? AND fy=?", (kind, tid, fy))
        else:
            conn.execute("INSERT INTO budgets(kind, target_id, fy, amount_paise) VALUES (?,?,?,?) "
                         "ON CONFLICT(kind, target_id, fy) DO UPDATE SET amount_paise=excluded.amount_paise", (kind, tid, fy, amt))
        dbm.audit(conn, "budget", kind, tid, f"{fy}: {amt}")
    return {"ok": True}


def budget_report(conn, frm: str, to: str) -> dict:
    """Budget against actual for the financial year that contains the period's end date."""
    from . import reports as rp
    frm, to = parse_iso(frm), parse_iso(to)
    fy = fy_label(parse_iso(to), dbm.get_company(conn)["fy_start_month"])
    rows = rp.ledger_rows(conn, frm, to)
    groups = rp._groups(conn)
    kids = {}
    for g in groups:
        kids.setdefault(g["parent_id"], []).append(g["id"])
    out = []
    for b in conn.execute("SELECT kind, target_id, amount_paise FROM budgets WHERE fy=?", (fy,)):
        if b["kind"] == "ledger":
            sel = [r for r in rows if r["id"] == b["target_id"]]
            name = sel[0]["name"] if sel else "?"
        else:
            ids, st = set(), [b["target_id"]]
            while st:
                i = st.pop()
                ids.add(i)
                st.extend(kids.get(i, []))
            sel = [r for r in rows if r["group_id"] in ids]
            name = next((g["name"] for g in groups if g["id"] == b["target_id"]), "?")
        if not sel:
            continue
        nature = sel[0]["nature"]
        move = sum(r["dr"] - r["cr"] for r in sel)
        actual = move if nature in ("expense", "asset") else -move
        out.append({"kind": b["kind"], "target_id": b["target_id"], "name": name + (" (group)" if b["kind"] == "group" else ""),
                    "budget": b["amount_paise"], "actual": actual, "variance": b["amount_paise"] - actual,
                    "used_pct": round(actual * 100 / b["amount_paise"]) if b["amount_paise"] else None})
    out.sort(key=lambda x: x["name"].lower())
    return {"fy": fy, "from": frm, "to": to, "rows": out}


def list_budgets(conn) -> list:
    return [dict(r) for r in conn.execute("SELECT kind, target_id, fy, amount_paise FROM budgets ORDER BY fy DESC, kind, target_id")]
