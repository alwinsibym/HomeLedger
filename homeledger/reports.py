"""Reports, dashboard and search. Amounts are signed paise (Dr positive) unless a field says otherwise."""
from __future__ import annotations

import datetime as dt

from . import db as dbm
from .errors import UserError
from .money import add_months, parse_amount, parse_iso
from .service import NOMINAL, REAL, VTYPES, _particulars, get_voucher


def _period(frm, to):
    frm, to = parse_iso(frm, "From date"), parse_iso(to, "To date")
    if frm > to:
        raise UserError("The 'From' date is after the 'To' date.")
    return frm, to


# ---------------------------------------------------------------------------
# core per-ledger numbers
# ---------------------------------------------------------------------------
def ledger_rows(conn, frm: str, to: str) -> list:
    """Every ledger with opening / debit / credit / closing for the period.

    Real ledgers (assets, liabilities) carry their balance forward.
    Income/expense ledgers show only the movement inside the period (their earlier
    result is carried in 'Profit & Loss A/c (brought forward)').
    """
    rows = []
    for r in conn.execute(
            """SELECT l.id, l.name, l.group_id, l.nature, l.cb_kind, l.opening_paise, l.opening_type, l.is_active,
                      l.default_cc_id,
                 COALESCE(SUM(CASE WHEN v.vdate < ? THEN e.debit_paise - e.credit_paise END), 0) AS before_net,
                 COALESCE(SUM(CASE WHEN v.vdate >= ? AND v.vdate <= ? THEN e.debit_paise END), 0) AS dr,
                 COALESCE(SUM(CASE WHEN v.vdate >= ? AND v.vdate <= ? THEN e.credit_paise END), 0) AS cr
               FROM ledgers l
               LEFT JOIN entries e ON e.ledger_id = l.id
               LEFT JOIN vouchers v ON v.id = e.voucher_id AND v.status = 'posted'
               GROUP BY l.id""", (frm, frm, to, frm, to)):
        d = dict(r)
        open_signed = d["opening_paise"] if d["opening_type"] == "Dr" else -d["opening_paise"]
        if d["nature"] in REAL:
            d["opening"] = open_signed + d["before_net"]
            d["open_base"] = open_signed
        else:
            d["opening"] = 0
            d["open_base"] = 0
        d["closing"] = d["opening"] + d["dr"] - d["cr"]
        rows.append(d)
    return rows


def _synthetics(rows):
    """(P&L brought forward, difference in opening balances) as signed Dr-positive numbers for the Trial Balance."""
    pl_bf = sum(r["before_net"] for r in rows if r["nature"] in NOMINAL)
    x = sum(r["open_base"] for r in rows if r["nature"] in REAL)
    return pl_bf, -x


def _tree(groups, rows):
    """Nested group/ledger tree with rolled-up opening, dr, cr, closing."""
    by_parent = {}
    for g in groups:
        by_parent.setdefault(g["parent_id"], []).append(g)
    led_by_group = {}
    for r in rows:
        led_by_group.setdefault(r["group_id"], []).append(r)

    def build(g):
        kids = [build(c) for c in by_parent.get(g["id"], [])]
        leds = [{"type": "ledger", "id": r["id"], "name": r["name"], "nature": r["nature"], "cb_kind": r["cb_kind"],
                 "opening": r["opening"], "dr": r["dr"], "cr": r["cr"], "closing": r["closing"],
                 "active": bool(r["is_active"])}
                for r in sorted(led_by_group.get(g["id"], []), key=lambda x: x["name"].lower())]
        children = kids + leds
        return {"type": "group", "id": g["id"], "name": g["name"], "nature": g["nature"], "code": g["code"],
                "opening": sum(c["opening"] for c in children), "dr": sum(c["dr"] for c in children),
                "cr": sum(c["cr"] for c in children), "closing": sum(c["closing"] for c in children),
                "children": children}
    return [build(g) for g in sorted(by_parent.get(None, []), key=lambda x: (x["sort"], x["name"]))]


def _groups(conn):
    return [dict(r) for r in conn.execute("SELECT id, code, name, parent_id, nature, sort FROM acct_groups")]


def trial_balance(conn, frm, to) -> dict:
    frm, to = _period(frm, to)
    rows = ledger_rows(conn, frm, to)
    tree = _tree(_groups(conn), rows)
    pl_bf, diff = _synthetics(rows)
    extra = []
    if pl_bf:
        extra.append({"type": "synthetic", "name": "Profit & Loss A/c (brought forward)",
                      "opening": pl_bf, "dr": 0, "cr": 0, "closing": pl_bf})
    if diff:
        extra.append({"type": "synthetic", "name": "Difference in opening balances",
                      "opening": diff, "dr": 0, "cr": 0, "closing": diff})
    # column totals shown as debit / credit sides
    def side_totals(key):
        dr = cr = 0
        for r in rows:
            v = r[key]
            dr += v if v > 0 else 0
            cr += -v if v < 0 else 0
        for e in extra:
            v = e[key]
            dr += v if v > 0 else 0
            cr += -v if v < 0 else 0
        return dr, cr
    o_dr, o_cr = side_totals("opening")
    c_dr, c_cr = side_totals("closing")
    return {"from": frm, "to": to, "tree": [t for t in tree], "extra": extra,
            "total_dr": sum(r["dr"] for r in rows), "total_cr": sum(r["cr"] for r in rows),
            "opening_dr": o_dr, "opening_cr": o_cr, "closing_dr": c_dr, "closing_cr": c_cr}


def _natural(node_value, nature):
    return node_value if nature in ("asset", "expense") else -node_value


def _prune(node, nature, key):
    """Keep only non-zero branches, expressed in natural sign (positive = normal balance)."""
    if node["type"] == "ledger":
        v = _natural(node[key], nature)
        if v == 0:
            return None
        return {"type": "ledger", "id": node["id"], "name": node["name"], "amount": v}
    kids = [k for k in (_prune(c, nature, key) for c in node["children"]) if k]
    if not kids:
        return None
    return {"type": "group", "id": node["id"], "name": node["name"], "amount": sum(k["amount"] for k in kids),
            "children": kids}


def profit_and_loss(conn, frm, to) -> dict:
    frm, to = _period(frm, to)
    rows = ledger_rows(conn, frm, to)
    tree = _tree(_groups(conn), rows)
    exp = [p for p in (_prune(n, "expense", "closing") for n in tree if n["nature"] == "expense") if p]
    inc = [p for p in (_prune(n, "income", "closing") for n in tree if n["nature"] == "income") if p]
    te = sum(p["amount"] for p in exp)
    ti = sum(p["amount"] for p in inc)
    return {"from": frm, "to": to, "expenses": exp, "income": inc, "total_expense": te, "total_income": ti,
            "net": ti - te}


def balance_sheet(conn, frm, to) -> dict:
    """Position at the end of the period. 'frm' decides what is 'brought forward' vs 'this period'."""
    frm, to = _period(frm, to)
    rows = ledger_rows(conn, frm, to)
    tree = _tree(_groups(conn), rows)
    assets = [p for p in (_prune(n, "asset", "closing") for n in tree if n["nature"] == "asset") if p]
    liabs = [p for p in (_prune(n, "liability", "closing") for n in tree if n["nature"] == "liability") if p]
    pl_bf = sum(r["before_net"] for r in rows if r["nature"] in NOMINAL)
    pl_cur = sum(r["dr"] - r["cr"] for r in rows if r["nature"] in NOMINAL)
    x = sum(r["open_base"] for r in rows if r["nature"] in REAL)
    extra = []
    if pl_bf:
        extra.append({"name": "Profit & Loss A/c (brought forward)", "amount": -pl_bf})
    extra.append({"name": "Profit & Loss A/c (this period)", "amount": -pl_cur})
    if x:
        extra.append({"name": "Difference in opening balances", "amount": x})
    ta = sum(p["amount"] for p in assets)
    tl = sum(p["amount"] for p in liabs) + sum(e["amount"] for e in extra)
    return {"from": frm, "to": to, "assets": assets, "liabilities": liabs, "extra": extra,
            "total_assets": ta, "total_liabilities": tl, "balanced": ta == tl}


def group_summary_ledgers(conn, group_id: int) -> list:
    """Ledger ids under a group (including sub-groups)."""
    ids = [group_id]
    out = []
    while ids:
        g = ids.pop()
        out += [r[0] for r in conn.execute("SELECT id FROM ledgers WHERE group_id=?", (g,))]
        ids += [r[0] for r in conn.execute("SELECT id FROM acct_groups WHERE parent_id=?", (g,))]
    return out


# ---------------------------------------------------------------------------
# ledger / group statements
# ---------------------------------------------------------------------------
def _target_ledgers(conn, ledger_id, group_id):
    if ledger_id:
        r = conn.execute("SELECT id, name, nature FROM ledgers WHERE id=?", (ledger_id,)).fetchone()
        if not r:
            raise UserError("That ledger no longer exists.")
        return [r["id"]], r["name"], r["nature"]
    if group_id:
        g = conn.execute("SELECT name, nature FROM acct_groups WHERE id=?", (group_id,)).fetchone()
        if not g:
            raise UserError("That group no longer exists.")
        return group_summary_ledgers(conn, group_id), g["name"], g["nature"]
    raise UserError("Choose a ledger or group.")


def _opening_for(conn, ids, nature, frm):
    if nature in NOMINAL or not ids:
        return 0
    ph = ",".join("?" * len(ids))
    op = conn.execute(
        f"SELECT COALESCE(SUM(CASE WHEN opening_type='Dr' THEN opening_paise ELSE -opening_paise END),0) "
        f"FROM ledgers WHERE id IN ({ph})", ids).fetchone()[0]
    before = conn.execute(
        f"""SELECT COALESCE(SUM(e.debit_paise - e.credit_paise),0) FROM entries e
            JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
            WHERE e.ledger_id IN ({ph}) AND v.vdate < ?""", ids + [frm]).fetchone()[0]
    return op + before


def ledger_statement(conn, frm, to, ledger_id=None, group_id=None) -> dict:
    frm, to = _period(frm, to)
    ids, name, nature = _target_ledgers(conn, ledger_id, group_id)
    opening = _opening_for(conn, ids, nature, frm)
    rows = []
    if ids:
        ph = ",".join("?" * len(ids))
        for r in conn.execute(
                f"""SELECT v.id AS vid, v.vdate, v.vtype, v.number, v.narration, v.date_approx, l.name AS ledger,
                           e.debit_paise, e.credit_paise, e.item, e.qty_milli, e.unit, c.name AS cc,
                      (SELECT group_concat(l2.name, ', ') FROM entries e2 JOIN ledgers l2 ON l2.id = e2.ledger_id
                        WHERE e2.voucher_id = e.voucher_id AND e2.id <> e.id) AS counter
                    FROM entries e
                    JOIN vouchers v ON v.id = e.voucher_id AND v.status = 'posted'
                    JOIN ledgers l ON l.id = e.ledger_id
                    LEFT JOIN cost_centres c ON c.id = e.cc_id
                    WHERE e.ledger_id IN ({ph}) AND v.vdate BETWEEN ? AND ?
                    ORDER BY v.vdate, v.id, e.id""", ids + [frm, to]):
            rows.append(dict(r))
    bal = opening
    tdr = tcr = 0
    for r in rows:
        bal += r["debit_paise"] - r["credit_paise"]
        r["balance"] = bal
        tdr += r["debit_paise"]
        tcr += r["credit_paise"]
    return {"from": frm, "to": to, "name": name, "nature": nature, "opening": opening, "rows": rows,
            "total_dr": tdr, "total_cr": tcr, "closing": opening + tdr - tcr}


def monthly_summary(conn, frm, to, ledger_id=None, group_id=None) -> dict:
    frm, to = _period(frm, to)
    ids, name, nature = _target_ledgers(conn, ledger_id, group_id)
    opening = _opening_for(conn, ids, nature, frm)
    per = {}
    if ids:
        ph = ",".join("?" * len(ids))
        for r in conn.execute(
                f"""SELECT substr(v.vdate,1,7) AS ym, SUM(e.debit_paise) AS dr, SUM(e.credit_paise) AS cr, COUNT(*) AS n
                    FROM entries e JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
                    WHERE e.ledger_id IN ({ph}) AND v.vdate BETWEEN ? AND ? GROUP BY ym""", ids + [frm, to]):
            per[r["ym"]] = (r["dr"], r["cr"], r["n"])
    rows = []
    y, m = int(frm[:4]), int(frm[5:7])
    ey, em = int(to[:4]), int(to[5:7])
    bal = opening
    while (y, m) <= (ey, em):
        ym = f"{y:04d}-{m:02d}"
        dr, cr, n = per.get(ym, (0, 0, 0))
        bal += dr - cr
        rows.append({"month": ym, "dr": dr, "cr": cr, "n": n, "closing": bal})
        y, m = add_months(y, m, 1)
    return {"from": frm, "to": to, "name": name, "nature": nature, "opening": opening, "rows": rows,
            "total_dr": sum(r["dr"] for r in rows), "total_cr": sum(r["cr"] for r in rows), "closing": bal}


# ---------------------------------------------------------------------------
# activities (farm / household cost centres)
# ---------------------------------------------------------------------------
def activity_summary(conn, frm, to) -> dict:
    frm, to = _period(frm, to)
    ccs = [dict(r) for r in conn.execute(
        "SELECT id, name, parent_id, kind, is_active, sort FROM cost_centres ORDER BY sort, name")]
    agg = {}
    for r in conn.execute(
            """SELECT e.cc_id,
                 SUM(CASE WHEN l.nature='income' THEN e.credit_paise - e.debit_paise ELSE 0 END) AS income,
                 SUM(CASE WHEN l.nature='expense' THEN e.debit_paise - e.credit_paise ELSE 0 END) AS expense,
                 SUM(CASE WHEN l.nature='asset' AND l.cb_kind IS NULL THEN e.debit_paise - e.credit_paise ELSE 0 END)
                      AS assets_net
               FROM entries e JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
               JOIN ledgers l ON l.id=e.ledger_id
               WHERE v.vdate BETWEEN ? AND ? GROUP BY e.cc_id""", (frm, to)):
        agg[r["cc_id"]] = (r["income"] or 0, r["expense"] or 0, r["assets_net"] or 0)
    for c in ccs:
        i, x, a = agg.get(c["id"], (0, 0, 0))
        c["income"], c["expense"], c["assets_net"] = i, x, a
    un = agg.get(None, (0, 0, 0))
    return {"from": frm, "to": to, "rows": ccs,
            "unallocated": {"income": un[0], "expense": un[1], "assets_net": un[2]}}


def _cc_ids(conn, cc_id, include_children=True):
    ids = [cc_id]
    if include_children:
        todo = [cc_id]
        while todo:
            p = todo.pop()
            kids = [r[0] for r in conn.execute("SELECT id FROM cost_centres WHERE parent_id=?", (p,))]
            ids += kids
            todo += kids
    return ids


def activity_detail(conn, frm, to, cc_id) -> dict:
    frm, to = _period(frm, to)
    if cc_id == 0:  # unallocated
        name, ids, cond, args = "Not assigned to an activity", [], "e.cc_id IS NULL", []
    else:
        c = conn.execute("SELECT name FROM cost_centres WHERE id=?", (cc_id,)).fetchone()
        if not c:
            raise UserError("That activity no longer exists.")
        name = c["name"]
        ids = _cc_ids(conn, cc_id)
        cond, args = f"e.cc_id IN ({','.join('?' * len(ids))})", ids
    ledgers = [dict(r) for r in conn.execute(
        f"""SELECT l.id, l.name, l.nature, SUM(e.debit_paise) AS dr, SUM(e.credit_paise) AS cr
            FROM entries e JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
            JOIN ledgers l ON l.id=e.ledger_id
            WHERE {cond} AND v.vdate BETWEEN ? AND ? AND l.cb_kind IS NULL
            GROUP BY l.id ORDER BY l.nature, l.name""", args + [frm, to])]
    months = {}
    for r in conn.execute(
            f"""SELECT substr(v.vdate,1,7) AS ym,
                  SUM(CASE WHEN l.nature='income' THEN e.credit_paise - e.debit_paise ELSE 0 END) AS income,
                  SUM(CASE WHEN l.nature='expense' THEN e.debit_paise - e.credit_paise ELSE 0 END) AS expense
                FROM entries e JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
                JOIN ledgers l ON l.id=e.ledger_id
                WHERE {cond} AND v.vdate BETWEEN ? AND ? GROUP BY ym""", args + [frm, to]):
        months[r["ym"]] = (r["income"], r["expense"])
    rows = []
    y, m = int(frm[:4]), int(frm[5:7])
    while (y, m) <= (int(to[:4]), int(to[5:7])):
        ym = f"{y:04d}-{m:02d}"
        i, x = months.get(ym, (0, 0))
        rows.append({"month": ym, "income": i, "expense": x})
        y, m = add_months(y, m, 1)
    return {"from": frm, "to": to, "name": name, "ledgers": ledgers, "months": rows}


# ---------------------------------------------------------------------------
# commodities
# ---------------------------------------------------------------------------
def commodity_summary(conn, frm, to) -> dict:
    frm, to = _period(frm, to)
    rows = []
    for r in conn.execute(
            """SELECT MIN(trim(e.item)) AS item, COALESCE(e.unit,'') AS unit, COUNT(*) AS n,
                 SUM(e.debit_paise) AS paid, SUM(e.credit_paise) AS received,
                 SUM(CASE WHEN e.debit_paise>0 THEN COALESCE(e.qty_milli,0) ELSE 0 END) AS qty_in,
                 SUM(CASE WHEN e.credit_paise>0 THEN COALESCE(e.qty_milli,0) ELSE 0 END) AS qty_out,
                 SUM(CASE WHEN e.debit_paise>0 AND e.qty_milli>0 THEN e.debit_paise ELSE 0 END) AS paid_q,
                 SUM(CASE WHEN e.credit_paise>0 AND e.qty_milli>0 THEN e.credit_paise ELSE 0 END) AS received_q
               FROM entries e JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
               JOIN ledgers l ON l.id=e.ledger_id
               WHERE e.item IS NOT NULL AND trim(e.item) <> '' AND l.cb_kind IS NULL
                 AND v.vdate BETWEEN ? AND ?
               GROUP BY lower(trim(e.item)), COALESCE(e.unit,'')
               ORDER BY (SUM(e.debit_paise) + SUM(e.credit_paise)) DESC""", (frm, to)):
        d = dict(r)
        d["avg_buy"] = round(d["paid_q"] * 1000 / d["qty_in"]) if d["qty_in"] else None
        d["avg_sell"] = round(d["received_q"] * 1000 / d["qty_out"]) if d["qty_out"] else None
        rows.append(d)
    return {"from": frm, "to": to, "rows": rows}


def commodity_detail(conn, frm, to, item, unit) -> dict:
    frm, to = _period(frm, to)
    item = (item or "").strip()
    unit = unit or ""
    if not item:
        raise UserError("Choose an item.")
    per = {}
    for r in conn.execute(
            """SELECT substr(v.vdate,1,7) AS ym, SUM(e.debit_paise) AS paid, SUM(e.credit_paise) AS received,
                 SUM(CASE WHEN e.debit_paise>0 THEN COALESCE(e.qty_milli,0) ELSE 0 END) AS qty_in,
                 SUM(CASE WHEN e.credit_paise>0 THEN COALESCE(e.qty_milli,0) ELSE 0 END) AS qty_out,
                 SUM(CASE WHEN e.debit_paise>0 AND e.qty_milli>0 THEN e.debit_paise ELSE 0 END) AS paid_q,
                 SUM(CASE WHEN e.credit_paise>0 AND e.qty_milli>0 THEN e.credit_paise ELSE 0 END) AS received_q
               FROM entries e JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
               JOIN ledgers l ON l.id=e.ledger_id
               WHERE lower(trim(e.item)) = lower(?) AND COALESCE(e.unit,'') = ? AND l.cb_kind IS NULL
                 AND v.vdate BETWEEN ? AND ? GROUP BY ym""", (item, unit, frm, to)):
        per[r["ym"]] = dict(r)
    rows = []
    y, m = int(frm[:4]), int(frm[5:7])
    while (y, m) <= (int(to[:4]), int(to[5:7])):
        ym = f"{y:04d}-{m:02d}"
        d = per.get(ym, {"paid": 0, "received": 0, "qty_in": 0, "qty_out": 0, "paid_q": 0, "received_q": 0})
        rows.append({"month": ym, "paid": d["paid"], "received": d["received"], "qty_in": d["qty_in"],
                     "qty_out": d["qty_out"],
                     "avg_buy": round(d["paid_q"] * 1000 / d["qty_in"]) if d["qty_in"] else None,
                     "avg_sell": round(d["received_q"] * 1000 / d["qty_out"]) if d["qty_out"] else None})
        y, m = add_months(y, m, 1)
    return {"from": frm, "to": to, "item": item, "unit": unit, "rows": rows}


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------
def _like(s: str) -> str:
    return "%" + s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search(conn, p: dict, limit: int = 1500) -> dict:
    conds = ["v.status = 'posted'"]
    args = []
    if p.get("from"):
        conds.append("v.vdate >= ?")
        args.append(parse_iso(p["from"], "From date"))
    if p.get("to"):
        conds.append("v.vdate <= ?")
        args.append(parse_iso(p["to"], "To date"))
    if p.get("vtype"):
        if p["vtype"] not in VTYPES:
            raise UserError("Unknown voucher type.")
        conds.append("v.vtype = ?")
        args.append(p["vtype"])
    if p.get("ledger_id"):
        conds.append("e.ledger_id = ?")
        args.append(int(p["ledger_id"]))
    if p.get("group_id"):
        ids = group_summary_ledgers(conn, int(p["group_id"]))
        conds.append(f"e.ledger_id IN ({','.join('?' * len(ids)) or 'NULL'})")
        args += ids
    if p.get("cc_id"):
        ids = _cc_ids(conn, int(p["cc_id"]))
        conds.append(f"e.cc_id IN ({','.join('?' * len(ids))})")
        args += ids
    if p.get("item"):
        conds.append("e.item LIKE ? ESCAPE '\\' COLLATE NOCASE")
        args.append(_like(p["item"].strip()))
    if p.get("amin"):
        conds.append("(e.debit_paise + e.credit_paise) >= ?")
        args.append(parse_amount(p["amin"], "Minimum amount"))
    if p.get("amax"):
        conds.append("(e.debit_paise + e.credit_paise) <= ?")
        args.append(parse_amount(p["amax"], "Maximum amount"))
    side = p.get("side")
    if side == "Dr":
        conds.append("e.debit_paise > 0")
    elif side == "Cr":
        conds.append("e.credit_paise > 0")
    if (p.get("scope") or "main") == "main":
        conds.append("l.cb_kind IS NULL")  # hide the Cash/Bank half so each transaction appears once
    q = " ".join((p.get("q") or "").split())
    for word in q.split(" ") if q else []:
        like = _like(word)
        sub = ["v.narration LIKE ? ESCAPE '\\'", "l.name LIKE ? ESCAPE '\\'", "e.item LIKE ? ESCAPE '\\'",
               "v.ref LIKE ? ESCAPE '\\'", "COALESCE(c.name,'') LIKE ? ESCAPE '\\'", "g.name LIKE ? ESCAPE '\\'"]
        a = [like] * 6
        try:
            amt = parse_amount(word.replace("₹", ""), "x")
            sub.append("(e.debit_paise + e.credit_paise) = ?")
            a.append(amt)
        except UserError:
            pass
        conds.append("(" + " OR ".join(sub) + ")")
        args += a
    base = """FROM entries e JOIN vouchers v ON v.id = e.voucher_id
              JOIN ledgers l ON l.id = e.ledger_id JOIN acct_groups g ON g.id = l.group_id
              LEFT JOIN cost_centres c ON c.id = e.cc_id WHERE """ + " AND ".join(conds)
    tot = conn.execute(f"SELECT COUNT(*), COALESCE(SUM(e.debit_paise),0), COALESCE(SUM(e.credit_paise),0) {base}",
                       args).fetchone()
    rows = [dict(r) for r in conn.execute(
        f"""SELECT v.id AS vid, v.vdate, v.vtype, v.number, v.narration, l.name AS ledger, l.nature, c.name AS cc,
                   e.item, e.qty_milli, e.unit, e.debit_paise, e.credit_paise
            {base} ORDER BY v.vdate DESC, v.id DESC, e.id LIMIT ?""", args + [limit])]
    return {"rows": rows, "count": tot[0], "total_dr": tot[1], "total_cr": tot[2], "truncated": tot[0] > limit}


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------
def _month_list(end_iso: str, n: int = 12):
    y, m = int(end_iso[:4]), int(end_iso[5:7])
    sy, sm = add_months(y, m, -(n - 1))
    out = []
    for i in range(n):
        yy, mm = add_months(sy, sm, i)
        out.append(f"{yy:04d}-{mm:02d}")
    return out


def dashboard(conn, frm, to, today: str) -> dict:
    frm, to = _period(frm, to)
    end = min(to, today) if to >= frm else today
    months = _month_list(end, 12)
    first_day = months[0] + "-01"

    # --- cards -------------------------------------------------------------
    def nat_sum(f, t, nature, cc_kind=None):
        sign = "e.credit_paise - e.debit_paise" if nature == "income" else "e.debit_paise - e.credit_paise"
        q = f"""SELECT COALESCE(SUM({sign}),0) FROM entries e JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
                JOIN ledgers l ON l.id=e.ledger_id LEFT JOIN cost_centres c ON c.id=e.cc_id
                WHERE l.nature=? AND v.vdate BETWEEN ? AND ?"""
        a = [nature, f, t]
        if cc_kind:
            q += " AND c.kind = ?"
            a.append(cc_kind)
        return conn.execute(q, a).fetchone()[0]

    ty, tm = int(today[:4]), int(today[5:7])
    this_m0 = f"{ty:04d}-{tm:02d}-01"
    py, pm = add_months(ty, tm, -1)
    last_m0 = f"{py:04d}-{pm:02d}-01"
    last_m1 = (dt.date.fromisoformat(this_m0) - dt.timedelta(days=1)).isoformat()

    # balances as of today
    cap_row = conn.execute("SELECT id FROM acct_groups WHERE code='CAPITAL'").fetchone()
    cap_ids = set(group_summary_ledgers(conn, cap_row[0])) if cap_row else set()
    bal = {"cash": 0, "bank": 0, "assets": 0, "liabilities": 0, "debtors": 0, "loans": 0}
    for r in conn.execute(
            """SELECT l.id, l.nature, l.cb_kind, l.opening_paise, l.opening_type, g.code,
                 COALESCE((SELECT SUM(e.debit_paise - e.credit_paise) FROM entries e
                           JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
                           WHERE e.ledger_id=l.id AND v.vdate <= ?),0) AS net
               FROM ledgers l JOIN acct_groups g ON g.id=l.group_id WHERE l.nature IN ('asset','liability')""",
            (today,)):
        signed = (r["opening_paise"] if r["opening_type"] == "Dr" else -r["opening_paise"]) + r["net"]
        if r["cb_kind"]:
            bal[r["cb_kind"]] += signed
        if r["nature"] == "asset":
            bal["assets"] += signed
        elif r["id"] not in cap_ids:       # the family's own capital is not a debt
            bal["liabilities"] += -signed
        if r["code"] == "DEBTORS":
            bal["debtors"] += signed
        if r["code"] == "LOANS_LIAB":
            bal["loans"] += -signed
    cards = {
        "cash": bal["cash"], "bank": bal["bank"], "net_worth": bal["assets"] - bal["liabilities"],
        "money_lent": bal["debtors"], "loans": bal["loans"],
        "month_income": nat_sum(this_m0, today, "income"), "month_expense": nat_sum(this_m0, today, "expense"),
        "last_month_expense": nat_sum(last_m0, last_m1, "expense"),
        "last_month_income": nat_sum(last_m0, last_m1, "income"),
        "period_income": nat_sum(frm, to, "income"), "period_expense": nat_sum(frm, to, "expense"),
        "farm_income": nat_sum(frm, to, "income", "farm"), "farm_expense": nat_sum(frm, to, "expense", "farm"),
        "house_income": nat_sum(frm, to, "income", "household"),
        "house_expense": nat_sum(frm, to, "expense", "household"),
        "today": today, "month_start": this_m0,
    }

    # --- monthly series ------------------------------------------------------
    mm = {m: {"month": m, "income": 0, "expense": 0, "farm_expense": 0, "house_expense": 0, "other_expense": 0,
              "cash_in": 0, "cash_out": 0} for m in months}
    for r in conn.execute(
            """SELECT substr(v.vdate,1,7) AS ym,
                 SUM(CASE WHEN l.nature='income' THEN e.credit_paise - e.debit_paise ELSE 0 END) AS income,
                 SUM(CASE WHEN l.nature='expense' THEN e.debit_paise - e.credit_paise ELSE 0 END) AS expense,
                 SUM(CASE WHEN l.nature='expense' AND c.kind='farm' THEN e.debit_paise - e.credit_paise ELSE 0 END) AS farm,
                 SUM(CASE WHEN l.nature='expense' AND c.kind='household' THEN e.debit_paise - e.credit_paise ELSE 0 END) AS house,
                 SUM(CASE WHEN l.cb_kind IS NOT NULL AND v.vtype <> 'Contra' THEN e.debit_paise ELSE 0 END) AS cin,
                 SUM(CASE WHEN l.cb_kind IS NOT NULL AND v.vtype <> 'Contra' THEN e.credit_paise ELSE 0 END) AS cout
               FROM entries e JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
               JOIN ledgers l ON l.id=e.ledger_id LEFT JOIN cost_centres c ON c.id=e.cc_id
               WHERE v.vdate BETWEEN ? AND ? GROUP BY ym""", (first_day, end)):
        d = mm.get(r["ym"])
        if d:
            d.update(income=r["income"], expense=r["expense"], farm_expense=r["farm"], house_expense=r["house"],
                     other_expense=r["expense"] - r["farm"] - r["house"], cash_in=r["cin"], cash_out=r["cout"])
    # net worth at each month end (the family's own capital account is left out: it is the result, not a debt)
    cap_list = list(cap_ids) or [-1]
    capq = ",".join("?" * len(cap_list))
    nw_base = conn.execute(
        """SELECT COALESCE((SELECT SUM(CASE WHEN opening_type='Dr' THEN opening_paise ELSE -opening_paise END)
                            FROM ledgers WHERE nature IN ('asset','liability') AND id NOT IN (%s)),0)
               + COALESCE((SELECT SUM(e.debit_paise - e.credit_paise) FROM entries e
                           JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
                           JOIN ledgers l ON l.id=e.ledger_id
                           WHERE l.nature IN ('asset','liability') AND l.id NOT IN (%s) AND v.vdate < ?),0)""" % (capq, capq), cap_list + cap_list + [first_day]).fetchone()[0]
    nw_month = {r["ym"]: r["net"] for r in conn.execute(
        """SELECT substr(v.vdate,1,7) AS ym, SUM(e.debit_paise - e.credit_paise) AS net
           FROM entries e JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
           JOIN ledgers l ON l.id=e.ledger_id
           WHERE l.nature IN ('asset','liability') AND l.id NOT IN (%s) AND v.vdate BETWEEN ? AND ? GROUP BY ym""" % capq,
        cap_list + [first_day, end])}
    run = nw_base
    for m in months:
        run += nw_month.get(m, 0)
        mm[m]["net_worth"] = run
    cb_base = conn.execute(
        """SELECT COALESCE((SELECT SUM(CASE WHEN opening_type='Dr' THEN opening_paise ELSE -opening_paise END)
                            FROM ledgers WHERE cb_kind IS NOT NULL),0)
               + COALESCE((SELECT SUM(e.debit_paise - e.credit_paise) FROM entries e
                           JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
                           JOIN ledgers l ON l.id=e.ledger_id
                           WHERE l.cb_kind IS NOT NULL AND v.vdate < ?),0)""", (first_day,)).fetchone()[0]
    cb_month = {r["ym"]: r["net"] for r in conn.execute(
        """SELECT substr(v.vdate,1,7) AS ym, SUM(e.debit_paise - e.credit_paise) AS net
           FROM entries e JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
           JOIN ledgers l ON l.id=e.ledger_id WHERE l.cb_kind IS NOT NULL AND v.vdate BETWEEN ? AND ? GROUP BY ym""",
        (first_day, end))}
    run = cb_base
    for m in months:
        run += cb_month.get(m, 0)
        mm[m]["cash_bank"] = run

    # --- breakdowns for the chosen period -------------------------------------
    top_exp = [dict(r) for r in conn.execute(
        """SELECT l.id, l.name, SUM(e.debit_paise - e.credit_paise) AS amount
           FROM entries e JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
           JOIN ledgers l ON l.id=e.ledger_id
           WHERE l.nature='expense' AND v.vdate BETWEEN ? AND ?
           GROUP BY l.id HAVING amount > 0 ORDER BY amount DESC LIMIT 10""", (frm, to))]
    top_inc = [dict(r) for r in conn.execute(
        """SELECT l.id, l.name, SUM(e.credit_paise - e.debit_paise) AS amount
           FROM entries e JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
           JOIN ledgers l ON l.id=e.ledger_id
           WHERE l.nature='income' AND v.vdate BETWEEN ? AND ?
           GROUP BY l.id HAVING amount > 0 ORDER BY amount DESC LIMIT 8""", (frm, to))]
    by_activity = [dict(r) for r in conn.execute(
        """SELECT c.id, c.name, c.kind, SUM(e.debit_paise - e.credit_paise) AS amount
           FROM entries e JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
           JOIN ledgers l ON l.id=e.ledger_id JOIN cost_centres c ON c.id=e.cc_id
           WHERE l.nature='expense' AND v.vdate BETWEEN ? AND ?
           GROUP BY c.id HAVING amount > 0 ORDER BY amount DESC LIMIT 12""", (frm, to))]
    top_items = [dict(r) for r in conn.execute(
        """SELECT MIN(trim(e.item)) AS item, SUM(e.debit_paise) AS amount
           FROM entries e JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
           JOIN ledgers l ON l.id=e.ledger_id
           WHERE e.item IS NOT NULL AND trim(e.item) <> '' AND l.cb_kind IS NULL AND e.debit_paise > 0
             AND v.vdate BETWEEN ? AND ?
           GROUP BY lower(trim(e.item)) ORDER BY amount DESC LIMIT 8""", (frm, to))]
    recent = []
    for r in conn.execute("SELECT id FROM vouchers WHERE status='posted' ORDER BY vdate DESC, id DESC LIMIT 8"):
        v = get_voucher(conn, r[0])
        recent.append({"id": v["id"], "date": v["date"], "vtype": v["vtype"], "number": v["number"],
                       "particulars": _particulars(v["lines"], v["vtype"]), "amount_paise": v["total_paise"]})
    counts = conn.execute(
        "SELECT COUNT(*), MIN(vdate), MAX(vdate) FROM vouchers WHERE status='posted'").fetchone()
    return {"from": frm, "to": to, "cards": cards, "months": [mm[m] for m in months], "top_expenses": top_exp,
            "top_income": top_inc, "by_activity": by_activity, "top_items": top_items, "recent": recent,
            "voucher_count": counts[0], "first_date": counts[1], "last_date": counts[2]}


def ratio_analysis(conn, frm, to) -> dict:
    """Tally-style Ratio Analysis, worked from the same figures as the Balance Sheet and Profit & Loss."""
    frm, to = _period(frm, to)
    rows = ledger_rows(conn, frm, to)
    groups = _groups(conn)
    kids = {}
    for g in groups:
        kids.setdefault(g["parent_id"], []).append(g["id"])
    code_id = {g["code"]: g["id"] for g in groups}

    def subtree(code):
        out, stack = set(), [code_id[code]]
        while stack:
            i = stack.pop()
            out.add(i)
            stack.extend(kids.get(i, []))
        return out

    def bal(code):   # closing balance, Dr positive
        ids = subtree(code)
        return sum(r["closing"] for r in rows if r["group_id"] in ids)

    ca, cl = bal("CURRENT_ASSETS"), -bal("CURRENT_LIAB")
    stock = bal("STOCK")
    cash_bank = bal("CASH") + bal("BANK")
    loans = -(bal("LOANS_LIAB"))
    capital = -bal("CAPITAL")
    sales = -bal("SALES")
    direct_inc = -bal("DIRECT_INC")
    purchase = bal("PURCHASE")
    direct_exp = bal("DIRECT_EXP")
    pl = profit_and_loss(conn, frm, to)
    net = pl["net"]
    gross = sales + direct_inc - purchase - direct_exp   # opening/closing stock is not tracked in value

    def pct(a, b):
        return None if not b else round(a * 10000 / b)       # hundredths of a percent
    def ratio(a, b):
        return None if not b else round(a * 100 / b)         # hundredths
    return {"from": frm, "to": to, "items": [
        {"name": "Working Capital", "kind": "money", "value": ca - cl},
        {"name": "Cash-in-Hand + Bank", "kind": "money", "value": cash_bank},
        {"name": "Current Ratio", "kind": "ratio", "value": ratio(ca, cl)},
        {"name": "Quick Ratio", "kind": "ratio", "value": ratio(ca - stock, cl)},
        {"name": "Debt / Equity", "kind": "ratio", "value": ratio(loans, capital + net)},
        {"name": "Gross Profit %", "kind": "pct", "value": pct(gross, sales + direct_inc)},
        {"name": "Net Profit %", "kind": "pct", "value": pct(net, pl["total_income"])},
        {"name": "Expense % of Income", "kind": "pct", "value": pct(pl["total_expense"], pl["total_income"])},
    ], "note": "Stock is not valued in the books, so Gross Profit % ignores opening and closing stock."}


def outstanding(conn, kind: str, as_on: str) -> dict:
    """Receivables (Sundry Debtors) or Payables (Sundry Creditors) with ageing.
    Settlements are matched to the oldest open amounts first (FIFO), because entries are not tagged bill by bill."""
    if kind not in ("receivable", "payable"):
        raise UserError("Choose receivables or payables.")
    as_on = parse_iso(as_on)
    code = "DEBTORS" if kind == "receivable" else "CREDITORS"
    groups = _groups(conn)
    kids = {}
    for g in groups:
        kids.setdefault(g["parent_id"], []).append(g["id"])
    ids, stack = set(), [next(g["id"] for g in groups if g["code"] == code)]
    while stack:
        i = stack.pop()
        ids.add(i)
        stack.extend(kids.get(i, []))
    asd = dt.date.fromisoformat(as_on)
    sign = 1 if kind == "receivable" else -1          # +ve = owed (increase), -ve = settled
    out, total = [], [0, 0, 0, 0]
    for l in conn.execute("SELECT id, name, group_id, opening_paise, opening_type FROM ledgers ORDER BY name COLLATE NOCASE"):
        if l["group_id"] not in ids:
            continue
        bills = []      # [date, amount]
        op = l["opening_paise"] if l["opening_type"] == "Dr" else -l["opening_paise"]
        op *= sign
        credit_pool = 0
        if op > 0:
            bills.append(["0001-01-01", op])
        else:
            credit_pool -= op
        for e in conn.execute(
                """SELECT v.vdate, e.debit_paise - e.credit_paise AS net FROM entries e
                   JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
                   WHERE e.ledger_id=? AND v.vdate<=? ORDER BY v.vdate, v.id""", (l["id"], as_on)):
            amt = e["net"] * sign
            if amt > 0:
                bills.append([e["vdate"], amt])
            else:
                credit_pool += -amt
        for b in bills:
            if credit_pool <= 0:
                break
            take = min(b[1], credit_pool)
            b[1] -= take
            credit_pool -= take
        open_bills = [b for b in bills if b[1] > 0]
        advance = credit_pool    # settled more than owed
        if not open_bills and not advance:
            continue
        buckets = [0, 0, 0, 0]
        oldest = None
        for d, a in open_bills:
            age = (asd - dt.date.fromisoformat(d)).days if d != "0001-01-01" else 9999
            buckets[0 if age <= 30 else 1 if age <= 60 else 2 if age <= 90 else 3] += a
            oldest = oldest or d
        due = sum(buckets)
        for i in range(4):
            total[i] += buckets[i]
        out.append({"ledger_id": l["id"], "name": l["name"], "due": due, "buckets": buckets, "advance": advance,
                    "oldest": None if oldest in (None, "0001-01-01") else oldest, "brought_forward": oldest == "0001-01-01"})
    return {"kind": kind, "as_on": as_on, "rows": out, "total": sum(total), "buckets": total,
            "note": "Matched oldest-first. Opening balances count as the oldest amount."}


def cash_flow(conn, frm, to) -> dict:
    """Cash and bank movement in the period, grouped by the kind of account on the other side of each voucher."""
    frm, to = _period(frm, to)
    rows = ledger_rows(conn, frm, to)
    opening = sum(r["opening"] for r in rows if r["cb_kind"])
    closing = sum(r["closing"] for r in rows if r["cb_kind"])
    gname = {g["id"]: g["name"] for g in _groups(conn)}
    inflow, outflow = {}, {}
    vids = [r[0] for r in conn.execute(
        """SELECT DISTINCT v.id FROM vouchers v JOIN entries e ON e.voucher_id=v.id JOIN ledgers l ON l.id=e.ledger_id
           WHERE v.status='posted' AND v.vdate BETWEEN ? AND ? AND l.cb_kind IS NOT NULL""", (frm, to))]
    for vid in vids:
        ents = [dict(r) for r in conn.execute(
            "SELECT e.debit_paise-e.credit_paise AS net, l.cb_kind, l.group_id FROM entries e JOIN ledgers l ON l.id=e.ledger_id WHERE e.voucher_id=?", (vid,))]
        if all(e["cb_kind"] for e in ents):
            continue                                   # money only moved between cash and bank
        for e in ents:
            if e["cb_kind"]:
                continue
            amt = -e["net"]                            # other side's credit = money in
            name = gname[e["group_id"]]
            if amt > 0:
                inflow[name] = inflow.get(name, 0) + amt
            elif amt < 0:
                outflow[name] = outflow.get(name, 0) - amt
    tin, tout = sum(inflow.values()), sum(outflow.values())
    return {"from": frm, "to": to, "opening": opening, "closing": closing,
            "inflow": sorted(inflow.items()), "outflow": sorted(outflow.items()),
            "total_in": tin, "total_out": tout, "check": opening + tin - tout == closing}
