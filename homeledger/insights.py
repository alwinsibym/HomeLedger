"""Insights: spending by category, year-on-year, and simple alerts. All read-only; amounts are paise."""
import datetime as dt

from .errors import UserError
from .money import add_months, parse_iso


def _fy_start(conn, on: str) -> str:
    m = conn.execute("SELECT fy_start_month FROM company LIMIT 1").fetchone()
    sm = int(m[0]) if m and m[0] else 4
    d = dt.date.fromisoformat(on)
    y = d.year if d.month >= sm else d.year - 1
    return f"{y:04d}-{sm:02d}-01"


def _earlier(iso: str, years: int) -> str:
    d = dt.date.fromisoformat(iso)
    try:
        return d.replace(year=d.year - years).isoformat()
    except ValueError:
        return d.replace(year=d.year - years, day=28).isoformat()


def spending(conn, frm, to, nature="expense") -> dict:
    """Spending (or income) by account for the period, with the same period a year earlier alongside."""
    if nature not in ("expense", "income"):
        raise UserError("Choose expense or income.")
    frm, to = parse_iso(frm, "From date"), parse_iso(to, "To date")
    if frm > to:
        raise UserError("The 'From' date is after the 'To' date.")
    sign = "e.debit_paise - e.credit_paise" if nature == "expense" else "e.credit_paise - e.debit_paise"
    q = f"""SELECT l.id, l.name, g.name AS grp, COALESCE(SUM({sign}),0) AS amt, COUNT(DISTINCT v.id) AS n
            FROM entries e JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
            JOIN ledgers l ON l.id=e.ledger_id JOIN acct_groups g ON g.id=l.group_id
            WHERE l.nature=? AND v.vdate BETWEEN ? AND ? GROUP BY l.id"""
    cur = {r["id"]: dict(r) for r in conn.execute(q, (nature, frm, to))}
    pf, pt = _earlier(frm, 1), _earlier(to, 1)
    prev = {r["id"]: dict(r) for r in conn.execute(q, (nature, pf, pt))}
    rows = []
    for i in set(cur) | set(prev):
        c, p = cur.get(i), prev.get(i)
        base = c or p
        rows.append({"ledger_id": i, "name": base["name"], "group": base["grp"], "amount": c["amt"] if c else 0,
                     "count": c["n"] if c else 0, "previous": p["amt"] if p else 0})
    rows = [r for r in rows if r["amount"] or r["previous"]]
    rows.sort(key=lambda r: -r["amount"])
    total = sum(r["amount"] for r in rows)
    groups = {}
    for r in rows:
        g = groups.setdefault(r["group"], {"group": r["group"], "amount": 0, "previous": 0})
        g["amount"] += r["amount"]
        g["previous"] += r["previous"]
    return {"nature": nature, "from": frm, "to": to, "prev_from": pf, "prev_to": pt, "total": total,
            "previous_total": sum(r["previous"] for r in rows), "rows": rows,
            "groups": sorted(groups.values(), key=lambda g: -g["amount"])}


def yoy(conn, on: str) -> dict:
    """The financial year containing `on`, month by month, against the year before."""
    on = parse_iso(on, "Date")
    start = _fy_start(conn, on)
    y, m = int(start[:4]), int(start[5:7])

    def series(sy, sm):
        out = []
        for i in range(12):
            yy, mm = add_months(sy, sm, i)
            out.append(f"{yy:04d}-{mm:02d}")
        res = {k: {"month": k, "income": 0, "expense": 0} for k in out}
        for r in conn.execute(
                """SELECT substr(v.vdate,1,7) ym,
                     SUM(CASE WHEN l.nature='income' THEN e.credit_paise-e.debit_paise ELSE 0 END) inc,
                     SUM(CASE WHEN l.nature='expense' THEN e.debit_paise-e.credit_paise ELSE 0 END) exp
                   FROM entries e JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted' JOIN ledgers l ON l.id=e.ledger_id
                   WHERE v.vdate BETWEEN ? AND ? GROUP BY ym""", (out[0] + "-01", out[-1] + "-31")):
            if r["ym"] in res:
                res[r["ym"]]["income"], res[r["ym"]]["expense"] = r["inc"], r["exp"]
        return list(res.values())

    return {"this_year": series(y, m), "last_year": series(y - 1, m), "start": start,
            "label": f"{y}-{str(y + 1)[2:]}" if m != 1 else str(y), "prev_label": f"{y - 1}-{str(y)[2:]}" if m != 1 else str(y - 1)}


def alerts(conn, today: str) -> list:
    """Things that need attention. Each: {kind, level (red/amber/info), text, go: [screen, params]}."""
    from . import reports as rp, tds, inventory as inv, templates as tp
    out = []

    def add(kind, level, text, go=None):
        out.append({"kind": kind, "level": level, "text": text, "go": go})

    # overdue bills
    for kind, word in (("receivable", "owes you"), ("payable", "you owe")):
        try:
            data = rp.outstanding(conn, kind, today)
        except Exception:
            continue
        for r in data["rows"]:
            late = [b for b in r.get("bills", []) if b["pending"] > 0 and b.get("due") and b["due"] < today]
            if late:
                amt = sum(b["pending"] for b in late)
                add("overdue", "red" if kind == "receivable" else "amber",
                    f"{r['name']} {word} {amt / 100:,.2f} past the due date ({len(late)} bill{'s' if len(late) > 1 else ''}).", ["receivables" if kind == "receivable" else "payables", {}])
            elif r["buckets"][3] > 0 and not r.get("bill_wise"):
                add("old", "amber", f"{r['name']}: {r['buckets'][3] / 100:,.2f} has been pending over 90 days.", ["receivables" if kind == "receivable" else "payables", {}])
    # TDS
    try:
        for m in tds.deposits(conn, today)["months"]:
            if m["status"] == "Overdue":
                add("tds", "red", f"TDS for {m['month']} ({m['balance_paise'] / 100:,.2f}) was due on {m['due']} and is not deposited.", ["tdsdeposits", {}])
            elif m["status"] == "Due" and (dt.date.fromisoformat(m["due"]) - dt.date.fromisoformat(today)).days <= 7:
                add("tds", "amber", f"TDS for {m['month']} ({m['balance_paise'] / 100:,.2f}) is due by {m['due']}.", ["tdsdeposits", {}])
    except Exception:
        pass
    # low stock
    low = {r["id"]: r["reorder_milli"] for r in conn.execute("SELECT id, reorder_milli FROM stock_items WHERE reorder_milli>0")}
    if low:
        for r in inv.summary(conn, _fy_start(conn, today), today):
            lv = low.get(r["item_id"])
            if lv and r["close_q"] <= lv:
                add("stock", "amber", f"{r['name']} is low: {r['close_q'] / 1000:g} {r['unit']} left (alert at {lv / 1000:g}).", ["stocksummary", {}])
    # unusual entries in the last 30 days: far above the usual for that account, or the same amount entered twice
    since = (dt.date.fromisoformat(today) - dt.timedelta(days=30)).isoformat()
    hist = {r["lid"]: (r["n"], r["a"]) for r in conn.execute(
        """SELECT e.ledger_id lid, COUNT(*) n, AVG(e.debit_paise) a FROM entries e JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted'
           JOIN ledgers l ON l.id=e.ledger_id WHERE l.nature='expense' AND e.debit_paise>0 AND v.vdate<? GROUP BY e.ledger_id""", (since,))}
    for r in conn.execute(
            """SELECT v.id vid, v.vdate, v.vtype, l.name, e.debit_paise amt, l.id lid FROM entries e
               JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted' JOIN ledgers l ON l.id=e.ledger_id
               WHERE l.nature='expense' AND e.debit_paise>0 AND v.vdate BETWEEN ? AND ?""", (since, today)):
        n, a = hist.get(r["lid"], (0, 0))
        if n >= 5 and a and r["amt"] >= 4 * a and r["amt"] >= 100000:
            add("unusual", "amber", f"{r['vdate']}: {r['amt'] / 100:,.2f} on {r['name']} is over 4 times its usual amount ({a / 100:,.2f}).", ["voucher", {"id": r["vid"]}])
    for r in conn.execute(
            """SELECT v.vdate, l.name, e.debit_paise amt, COUNT(DISTINCT v.id) n, MIN(v.id) vid FROM entries e
               JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted' JOIN ledgers l ON l.id=e.ledger_id
               WHERE l.nature='expense' AND e.debit_paise>0 AND v.vdate BETWEEN ? AND ?
               GROUP BY v.vdate, l.id, e.debit_paise HAVING n>1""", (since, today)):
        add("duplicate", "amber", f"{r['vdate']}: {r['amt'] / 100:,.2f} on {r['name']} was entered {r['n']} times. Is one a duplicate?", ["voucher", {"id": r["vid"]}])
    # repeats due
    n = len(tp.due(conn, today))
    if n:
        add("repeat", "info", f"{n} repeat entr{'ies are' if n > 1 else 'y is'} due.", ["repeats", {}])
    # post-dated vouchers that have come due
    k = conn.execute("""SELECT COUNT(*) FROM vouchers v JOIN voucher_meta m ON m.voucher_id=v.id
                        WHERE m.post_dated=1 AND v.status='optional' AND v.vdate<=?""", (today,)).fetchone()[0]
    if k:
        add("postdated", "info", f"{k} post-dated voucher{'s have' if k > 1 else ' has'} reached its date and still not in the books.", ["postdated", {}])
    order = {"red": 0, "amber": 1, "info": 2}
    out.sort(key=lambda a: order[a["level"]])
    return out
