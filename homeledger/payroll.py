"""Payroll (stage 1): employees, pay heads, monthly salary run, payslips, and the salary journal voucher.

Simple on purpose: earnings are fixed monthly amounts that are cut in proportion to days present; deductions are
fixed amounts or a percentage of the (pro-rated) basic. Any deduction can be overridden for a month by typing the
amount. NOT covered: statutory PF/ESI/professional-tax slabs and ceilings, salary TDS computed from tax slabs
(type the TDS amount yourself), leave, overtime, arrears, bonus, gratuity, full-and-final settlement, Form 16,
and returns. Have an accountant set the amounts.
"""
import calendar
import re
from decimal import Decimal, ROUND_HALF_UP

from . import db as dbm
from .errors import UserError
from .money import parse_iso

PAN_RE = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")


def _r(x) -> int:
    return int(Decimal(x).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def heads(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM pay_heads ORDER BY is_active DESC, sort, name")]


def save_head(conn, d):
    name = (d.get("name") or "").strip()
    kind = d.get("kind")
    if not name or kind not in ("earning", "deduction"):
        raise UserError("Please type the name and choose earning or deduction.")
    calc = "percent_basic" if d.get("calc") == "percent_basic" and kind == "deduction" else "fixed"
    basic = 1 if d.get("is_basic") and kind == "earning" else 0
    led = int(d["ledger_id"]) if d.get("ledger_id") else None
    with dbm.write_tx(conn):
        if basic:
            conn.execute("UPDATE pay_heads SET is_basic=0 WHERE id<>?", (int(d.get("id") or 0),))
        try:
            if d.get("id"):
                conn.execute("UPDATE pay_heads SET name=?, kind=?, is_basic=?, calc=?, ledger_id=?, sort=?, is_active=? WHERE id=?",
                             (name, kind, basic, calc, led, int(d.get("sort") or 100), 1 if d.get("is_active", True) else 0, int(d["id"])))
                hid = int(d["id"])
            else:
                hid = conn.execute("INSERT INTO pay_heads(name, kind, is_basic, calc, ledger_id, sort) VALUES (?,?,?,?,?,?)",
                                   (name, kind, basic, calc, led, int(d.get("sort") or 100))).lastrowid
        except Exception as e:
            if "UNIQUE" in str(e):
                raise UserError("A pay head with this name already exists.")
            raise
        dbm.audit(conn, "alter", "pay_head", hid, name)
    return {"id": hid}


def employees(conn):
    out = []
    for e in conn.execute("SELECT * FROM pay_employees ORDER BY is_active DESC, name"):
        d = dict(e)
        d["structure"] = {r["head_id"]: {"amount_paise": r["amount_paise"], "rate_bp": r["rate_bp"]}
                          for r in conn.execute("SELECT * FROM pay_structure WHERE employee_id=?", (e["id"],))}
        out.append(d)
    return out


def save_employee(conn, d):
    name = (d.get("name") or "").strip()
    if not name:
        raise UserError("Please type the employee's name.")
    pan = (d.get("pan") or "").strip().upper()
    if pan and not PAN_RE.match(pan):
        raise UserError("A PAN has 10 characters: 5 letters, 4 digits, 1 letter.")
    joined = parse_iso(d["joined"], "Joining date") if d.get("joined") else None
    left = parse_iso(d["left_on"], "Leaving date") if d.get("left_on") else None
    st = d.get("structure") or {}
    with dbm.write_tx(conn):
        try:
            vals = (name, (d.get("designation") or "").strip(), pan, joined, left, 1 if d.get("is_active", True) else 0, (d.get("notes") or "").strip())
            if d.get("id"):
                conn.execute("UPDATE pay_employees SET name=?, designation=?, pan=?, joined=?, left_on=?, is_active=?, notes=? WHERE id=?", vals + (int(d["id"]),))
                eid = int(d["id"])
            else:
                eid = conn.execute("INSERT INTO pay_employees(name, designation, pan, joined, left_on, is_active, notes) VALUES (?,?,?,?,?,?,?)", vals).lastrowid
        except Exception as e:
            if "UNIQUE" in str(e):
                raise UserError("An employee with this name already exists.")
            raise
        conn.execute("DELETE FROM pay_structure WHERE employee_id=?", (eid,))
        for hid, v in st.items():
            amt = int(v.get("amount_paise") or 0)
            rate = int(v.get("rate_bp") or 0)
            if amt < 0 or not 0 <= rate <= 10000:
                raise UserError("Amounts cannot be negative and a percentage must be between 0 and 100.")
            if amt or rate:
                conn.execute("INSERT INTO pay_structure(employee_id, head_id, amount_paise, rate_bp) VALUES (?,?,?,?)", (eid, int(hid), amt, rate))
        dbm.audit(conn, "alter", "pay_employee", eid, name)
    return {"id": eid}


def calc_slip(hds: list, structure: dict, days_present, working_days: int, overrides: dict | None = None) -> dict:
    """Pure calculation. structure: {head_id: {amount_paise, rate_bp}}; overrides: {head_id: amount_paise} for this month."""
    if working_days <= 0:
        raise UserError("Working days must be above zero.")
    days = Decimal(str(days_present))
    if days < 0 or days > working_days:
        raise UserError("Days present must be between 0 and the working days of the month.")
    ratio = days / Decimal(working_days)
    overrides = overrides or {}
    lines, basic = {}, 0
    for h in hds:
        if h["kind"] == "earning" and h["id"] in structure:
            amt = _r(Decimal(structure[h["id"]]["amount_paise"]) * ratio)
            lines[h["id"]] = amt
            if h["is_basic"]:
                basic = amt
    for h in hds:
        if h["kind"] != "deduction" or h["id"] not in structure:
            continue
        s = structure[h["id"]]
        lines[h["id"]] = _r(Decimal(basic) * s["rate_bp"] / 10000) if h["calc"] == "percent_basic" else _r(Decimal(s["amount_paise"]) * (1 if h["calc"] == "fixed" else ratio))
    for hid, amt in overrides.items():
        lines[int(hid)] = int(amt)
    kinds = {h["id"]: h["kind"] for h in hds}
    gross = sum(a for k, a in lines.items() if kinds.get(k) == "earning")
    ded = sum(a for k, a in lines.items() if kinds.get(k) == "deduction")
    if ded > gross:
        raise UserError("Deductions are more than the earnings for this employee.")
    return {"lines": {k: v for k, v in lines.items() if v}, "gross_paise": gross, "deduct_paise": ded, "net_paise": gross - ded}


def _days_in(month: str) -> int:
    return calendar.monthrange(int(month[:4]), int(month[5:]))[1]


def get_run(conn, month: str) -> dict:
    """The saved run of a month, or a fresh unsaved one built from the current salary structures."""
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month or ""):
        raise UserError("Please choose the month.")
    hds = [h for h in heads(conn) if h["is_active"]]
    run = conn.execute("SELECT * FROM pay_runs WHERE month=?", (month,)).fetchone()
    first, last = f"{month}-01", f"{month}-{_days_in(month):02d}"
    slips = []
    if run:
        for s in conn.execute("SELECT s.*, e.name FROM pay_slips s JOIN pay_employees e ON e.id=s.employee_id WHERE s.run_id=? ORDER BY e.name", (run["id"],)):
            ls = {r["head_id"]: r["amount_paise"] for r in conn.execute("SELECT * FROM pay_slip_lines WHERE slip_id=?", (s["id"],))}
            slips.append({"employee_id": s["employee_id"], "name": s["name"], "days_present": s["days_present"], "lines": ls,
                          "gross_paise": s["gross_paise"], "deduct_paise": s["deduct_paise"], "net_paise": s["net_paise"]})
    else:
        for e in employees(conn):
            if not e["is_active"] or (e["joined"] and e["joined"] > last) or (e["left_on"] and e["left_on"] < first) or not e["structure"]:
                continue
            c = calc_slip(hds, e["structure"], _days_in(month), _days_in(month))
            slips.append({"employee_id": e["id"], "name": e["name"], "days_present": _days_in(month), "lines": c["lines"],
                          "gross_paise": c["gross_paise"], "deduct_paise": c["deduct_paise"], "net_paise": c["net_paise"]})
    return {"month": month, "working_days": run["working_days"] if run else _days_in(month), "status": run["status"] if run else "new",
            "voucher_id": run["voucher_id"] if run else None, "heads": hds, "slips": slips}


def calc_run(conn, d: dict) -> dict:
    """Calculate (no saving) from the screen's days / overrides."""
    hds = [h for h in heads(conn) if h["is_active"]]
    emps = {e["id"]: e for e in employees(conn)}
    wd = int(d.get("working_days") or 0)
    out = []
    for x in d.get("slips") or []:
        e = emps.get(int(x["employee_id"]))
        if not e:
            continue
        c = calc_slip(hds, e["structure"], x.get("days_present", wd), wd, {int(k): int(v) for k, v in (x.get("overrides") or {}).items()})
        out.append({"employee_id": e["id"], "name": e["name"], "days_present": x.get("days_present", wd), **c})
    return {"slips": out}


def save_run(conn, d: dict) -> dict:
    month = d.get("month")
    wd = int(d.get("working_days") or 0)
    existing = conn.execute("SELECT * FROM pay_runs WHERE month=?", (month,)).fetchone()
    if existing and existing["status"] == "posted":
        raise UserError("This month is already posted to the books. Cancel its voucher and reopen the month to change it.")
    res = calc_run(conn, d)
    if not res["slips"]:
        raise UserError("There are no employees in this run.")
    with dbm.write_tx(conn):
        if existing:
            rid = existing["id"]
            conn.execute("UPDATE pay_runs SET working_days=? WHERE id=?", (wd, rid))
            conn.execute("DELETE FROM pay_slips WHERE run_id=?", (rid,))
        else:
            rid = conn.execute("INSERT INTO pay_runs(month, working_days, created_at) VALUES (?,?,?)", (month, wd, dbm.now_iso())).lastrowid
        kinds = {h["id"]: h["kind"] for h in heads(conn)}
        for s in res["slips"]:
            sid = conn.execute("INSERT INTO pay_slips(run_id, employee_id, days_present, gross_paise, deduct_paise, net_paise) VALUES (?,?,?,?,?,?)",
                               (rid, s["employee_id"], float(s["days_present"]), s["gross_paise"], s["deduct_paise"], s["net_paise"])).lastrowid
            for hid, amt in s["lines"].items():
                conn.execute("INSERT INTO pay_slip_lines(slip_id, head_id, kind, amount_paise) VALUES (?,?,?,?)", (sid, hid, kinds[hid], amt))
        dbm.audit(conn, "create", "pay_run", rid, f"{month}, {len(res['slips'])} employees")
    return {"id": rid}


def _ledger(conn, name, group_code, nature):
    r = conn.execute("SELECT id FROM ledgers WHERE name=? COLLATE NOCASE", (name,)).fetchone()
    if r:
        return r["id"]
    g = conn.execute("SELECT id FROM acct_groups WHERE code=?", (group_code,)).fetchone()
    return conn.execute("INSERT INTO ledgers(name, group_id, nature, opening_paise, opening_type, created_at) VALUES (?,?,?,0,?,?)",
                        (name, g["id"], nature, "Dr" if nature == "expense" else "Cr", dbm.now_iso())).lastrowid


def post_run(conn, month: str) -> dict:
    """Make the salary Journal: Dr Salaries & Wages (gross); Cr each deduction's ledger; Cr Salary Payable (net)."""
    from . import service as sv
    run = conn.execute("SELECT * FROM pay_runs WHERE month=?", (month,)).fetchone()
    if not run:
        raise UserError("Save the month's payroll first.")
    if run["status"] == "posted":
        raise UserError("This month is already posted.")
    sums = conn.execute("SELECT SUM(gross_paise) g, SUM(deduct_paise) d, SUM(net_paise) n FROM pay_slips WHERE run_id=?", (run["id"],)).fetchone()
    if not sums["g"]:
        raise UserError("Nothing to post.")
    with dbm.write_tx(conn):
        exp = _ledger(conn, "Salaries & Wages", "INDIRECT_EXP", "expense")
        pay = _ledger(conn, "Salary Payable", "CURRENT_LIAB", "liability")
        by_head = {}
        for r in conn.execute("SELECT l.head_id, SUM(l.amount_paise) a, h.name, h.ledger_id FROM pay_slip_lines l JOIN pay_slips s ON s.id=l.slip_id "
                              "JOIN pay_heads h ON h.id=l.head_id WHERE s.run_id=? AND l.kind='deduction' GROUP BY l.head_id", (run["id"],)):
            lid = r["ledger_id"] or _ledger(conn, f"{r['name']} Payable", "DUTIES" if "tds" in r["name"].lower() else "CURRENT_LIAB", "liability")
            by_head[lid] = by_head.get(lid, 0) + r["a"]
    last = f"{month}-{_days_in(month):02d}"
    lines = [{"ledger_id": exp, "side": "Dr", "amount": f"{sums['g'] / 100:.2f}"}]
    for lid, a in by_head.items():
        lines.append({"ledger_id": lid, "side": "Cr", "amount": f"{a / 100:.2f}"})
    lines.append({"ledger_id": pay, "side": "Cr", "amount": f"{sums['n'] / 100:.2f}"})
    v = sv.save_voucher(conn, {"vtype": "Journal", "date": last, "narration": f"Salary for {month}", "lines": lines})
    vid = v["id"]
    with dbm.write_tx(conn):
        conn.execute("UPDATE pay_runs SET status='posted', voucher_id=? WHERE id=?", (vid, run["id"]))
        dbm.audit(conn, "post", "pay_run", run["id"], f"{month} voucher {vid}")
    return {"voucher_id": vid}


def reopen_run(conn, month: str) -> dict:
    run = conn.execute("SELECT * FROM pay_runs WHERE month=?", (month,)).fetchone()
    if not run or run["status"] != "posted":
        raise UserError("This month is not posted.")
    v = conn.execute("SELECT status FROM vouchers WHERE id=?", (run["voucher_id"],)).fetchone()
    if v and v["status"] != "cancelled":
        raise UserError("First cancel the salary Journal voucher (open it and press Alt+X), then reopen the month.")
    with dbm.write_tx(conn):
        conn.execute("UPDATE pay_runs SET status='draft', voucher_id=NULL WHERE id=?", (run["id"],))
    return {"ok": True}


def register(conn, frm: str, to: str) -> dict:
    """Month-wise totals of the saved runs."""
    rows = [dict(r) for r in conn.execute(
        """SELECT r.month, r.status, COUNT(s.id) AS employees, COALESCE(SUM(s.gross_paise),0) AS gross, COALESCE(SUM(s.deduct_paise),0) AS ded,
                  COALESCE(SUM(s.net_paise),0) AS net FROM pay_runs r LEFT JOIN pay_slips s ON s.run_id=r.id
           WHERE r.month>=? AND r.month<=? GROUP BY r.id ORDER BY r.month""", (frm[:7], to[:7]))]
    return {"rows": rows, "gross": sum(r["gross"] for r in rows), "net": sum(r["net"] for r in rows)}
