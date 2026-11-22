"""Voucher templates and repeat (recurring) entries.

A template remembers the lines of an ordinary voucher (rent, EMI, salary advance...). It can be used to start a new voucher,
or set to repeat weekly / monthly / quarterly / yearly: 'Due repeats' then lists what is due and the user confirms; nothing is
ever posted silently in the background. Only plain vouchers (no stock items, GST or TDS) can be templates."""
import datetime as dt
import json

from . import db as dbm
from . import service as sv
from .errors import UserError
from .money import add_months, parse_iso

EVERY = ("", "weekly", "monthly", "quarterly", "yearly")
LABEL = {"": "No repeat", "weekly": "Every week", "monthly": "Every month", "quarterly": "Every 3 months", "yearly": "Every year"}
PLAIN = ("Payment", "Receipt", "Contra", "Journal")


def _next(iso: str, every: str) -> str:
    d = dt.date.fromisoformat(iso)
    if every == "weekly":
        return (d + dt.timedelta(days=7)).isoformat()
    n = {"monthly": 1, "quarterly": 3, "yearly": 12}[every]
    y, m = add_months(d.year, d.month, n)
    day = d.day
    while True:       # 31 Jan -> 28 Feb: step back to a day that exists
        try:
            return dt.date(y, m, day).isoformat()
        except ValueError:
            day -= 1


def _row(r) -> dict:
    p = json.loads(r["payload"])
    return {"id": r["id"], "name": r["name"], "vtype": r["vtype"], "repeat_every": r["repeat_every"],
            "repeat_label": LABEL[r["repeat_every"]], "next_due": r["next_due"], "narration": p.get("narration", ""),
            "lines": p.get("lines", []), "total_paise": sum(round(float(l["amount"]) * 100) for l in p.get("lines", []) if l["side"] == "Dr")}


def listing(conn) -> list:
    names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM ledgers")}
    out = []
    for r in conn.execute("SELECT * FROM vtemplates ORDER BY name COLLATE NOCASE"):
        x = _row(r)
        for l in x["lines"]:
            l["ledger_name"] = names.get(l["ledger_id"], "(removed)")
        out.append(x)
    return out


def save_from_voucher(conn, d: dict) -> dict:
    name = " ".join(str(d.get("name") or "").split())[:60]
    if not name:
        raise UserError("Please give the template a name.")
    every = d.get("repeat_every") or ""
    if every not in EVERY:
        raise UserError("Choose how often it repeats.")
    v = sv.get_voucher(conn, int(d.get("voucher_id") or 0))
    if v["vtype"] not in PLAIN:
        raise UserError("Templates can be made from Payment, Receipt, Contra and Journal vouchers.")
    if v["items"] or v["gst"] or v["tds"] or v["bills"]:
        raise UserError("This voucher has stock items, GST, TDS or bill references, so it cannot be a template. Use Duplicate (Alt+2) instead.")
    lines = [{"ledger_id": l["ledger_id"], "side": l["side"], "amount": f"{l['amount_paise'] / 100:.2f}",
              "cc_id": l["cc_id"]} for l in v["lines"]]
    nxt = None
    if every:
        nxt = parse_iso(d.get("next_due"), "Next due date")
    payload = json.dumps({"narration": v["narration"], "ref": "", "lines": lines})
    with dbm.write_tx(conn):
        if conn.execute("SELECT 1 FROM vtemplates WHERE name=?", (name,)).fetchone():
            raise UserError(f"A template named '{name}' already exists.")
        tid = conn.execute("INSERT INTO vtemplates(name, vtype, payload, repeat_every, next_due, created_at) VALUES (?,?,?,?,?,?)",
                           (name, v["vtype"], payload, every, nxt, dbm.now_iso())).lastrowid
        dbm.audit(conn, "create", "template", tid, name)
    return {"id": tid}


def set_repeat(conn, d: dict) -> dict:
    every = d.get("repeat_every") or ""
    if every not in EVERY:
        raise UserError("Choose how often it repeats.")
    nxt = parse_iso(d.get("next_due"), "Next due date") if every else None
    with dbm.write_tx(conn):
        n = conn.execute("UPDATE vtemplates SET repeat_every=?, next_due=? WHERE id=?", (every, nxt, int(d.get("id") or 0))).rowcount
        if not n:
            raise UserError("That template no longer exists.")
    return {"ok": True}


def delete(conn, tid: int) -> None:
    with dbm.write_tx(conn):
        conn.execute("DELETE FROM vtemplates WHERE id=?", (tid,))
        dbm.audit(conn, "delete", "template", tid, "")


def get(conn, tid: int) -> dict:
    r = conn.execute("SELECT * FROM vtemplates WHERE id=?", (tid,)).fetchone()
    if not r:
        raise UserError("That template no longer exists.")
    return _row(r)


def due(conn, today: str) -> list:
    """Every occurrence that is due on or before today (a template missed for 3 months shows 3 lines)."""
    out = []
    for r in conn.execute("SELECT * FROM vtemplates WHERE repeat_every<>'' AND next_due IS NOT NULL ORDER BY next_due, name"):
        x, d, n = _row(r), r["next_due"], 0
        while d <= today and n < 24:
            out.append({"template_id": x["id"], "name": x["name"], "vtype": x["vtype"], "date": d,
                        "total_paise": x["total_paise"], "narration": x["narration"]})
            d, n = _next(d, r["repeat_every"]), n + 1
    return out


def run_due(conn, d: dict, today: str) -> dict:
    """Post the ticked occurrences: d['items'] = [{template_id, date}]. Each becomes a normal voucher; next_due moves on."""
    items = d.get("items") or []
    if not items:
        raise UserError("Tick at least one entry.")
    made, ids = 0, []
    for it in sorted(items, key=lambda i: (i["template_id"], i["date"])):
        t = conn.execute("SELECT * FROM vtemplates WHERE id=?", (int(it["template_id"]),)).fetchone()
        if not t or not t["repeat_every"] or not t["next_due"]:
            continue
        if it["date"] != t["next_due"]:      # must go in order, one by one
            raise UserError(f"'{t['name']}' must be entered in date order; start with {t['next_due']}.")
        if it["date"] > today:
            raise UserError("That entry is not due yet.")
        p = json.loads(t["payload"])
        try:
            v = sv.save_voucher(conn, {"vtype": t["vtype"], "date": it["date"], "narration": p.get("narration", ""),
                                       "ref": "", "lines": p["lines"]})
        except UserError as e:
            raise UserError(f"{made} entered; '{t['name']}' on {it['date']} could not be entered: {e}")
        with dbm.write_tx(conn):
            conn.execute("UPDATE vtemplates SET next_due=? WHERE id=?", (_next(t["next_due"], t["repeat_every"]), t["id"]))
        made += 1
        ids.append(v["id"])
    return {"made": made, "ids": ids}


def as_voucher(conn, tid: int, today: str) -> dict:
    """A template shaped like get_voucher() output, so the voucher form can start from it as a new entry."""
    t = get(conn, tid)
    names = {r["id"]: r for r in conn.execute("SELECT id, name, nature, cb_kind FROM ledgers")}
    lines = []
    for l in t["lines"]:
        r = names.get(l["ledger_id"])
        if not r:
            raise UserError("A ledger used by this template no longer exists.")
        lines.append({"id": None, "ledger_id": l["ledger_id"], "ledger_name": r["name"], "nature": r["nature"], "cb_kind": r["cb_kind"],
                      "side": l["side"], "amount_paise": round(float(l["amount"]) * 100), "cc_id": l.get("cc_id"), "cc_name": None,
                      "item": "", "qty_milli": 0, "unit": ""})
    return {"id": None, "vtype": t["vtype"], "fy": "", "number": "", "date": today, "narration": t["narration"], "ref": "",
            "date_approx": False, "status": "posted", "lines": lines, "total_paise": t["total_paise"], "meta": {}, "bills": [],
            "items": [], "gst": None, "tds": None}
