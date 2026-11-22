"""TDS (stage 1): payer side. Natures of payment with rate and limits, deduction on vouchers, deductee statement,
deposit (challan) register with due dates.

Rates and limits are STARTING VALUES that the user can edit (Masters > TDS Setup). They were taken from published
FY 2026-27 charts (Income-tax Act, 2025, section 393; payment codes shown) and must be confirmed by an accountant.
NOT covered: salary (needs payroll), TCS, non-resident payments (195), lower-deduction certificates other than
typing a different rate, purchase of goods, return filing (Form 26Q/138), TAN, interest on late deposit.
"""
import datetime as dt
import re

from . import db as dbm
from .errors import UserError
from .money import fy_label, parse_iso

PAN_RE = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")
NO_PAN_RATE_BP = 2000          # higher of 20% or twice the rate is charged when PAN is missing


def ledger_id(conn) -> int:
    v = dbm.get_setting(conn, "tds_ledger", "")
    if v and conn.execute("SELECT 1 FROM ledgers WHERE id=?", (int(v),)).fetchone():
        return int(v)
    grp = conn.execute("SELECT id FROM acct_groups WHERE code='DUTIES'").fetchone()
    r = conn.execute("SELECT id FROM ledgers WHERE name='TDS Payable' COLLATE NOCASE").fetchone()
    lid = r["id"] if r else conn.execute(
        "INSERT INTO ledgers(name, group_id, nature, opening_paise, opening_type, created_at) VALUES ('TDS Payable', ?, 'liability', 0, 'Cr', ?)",
        (grp["id"], dbm.now_iso())).lastrowid
    dbm.set_setting(conn, "tds_ledger", str(lid))
    return lid


def setup(conn) -> dict:
    with dbm.write_tx(conn):
        lid = ledger_id(conn)
    return {"ledger_id": lid, "natures": natures(conn),
            "pan": {r["ledger_id"]: r["pan"] for r in conn.execute("SELECT * FROM tds_party")}}


def natures(conn) -> list:
    return [dict(r) for r in conn.execute("SELECT * FROM tds_nature ORDER BY is_active DESC, section, name")]


def save_nature(conn, d: dict) -> dict:
    name = (d.get("name") or "").strip()
    if not name:
        raise UserError("Please type the name of the nature of payment.")

    def money(k):
        try:
            return round(float(str(d.get(k) or 0).replace(",", "")) * 100)
        except ValueError:
            raise UserError("Please type the limits as numbers.")
    try:
        rate = round(float(str(d.get("rate") or "").replace("%", "")) * 100)
    except ValueError:
        raise UserError("Please type the rate as a number, like 10.")
    if not 0 <= rate <= 10000:
        raise UserError("The rate must be between 0 and 100.")
    vals = (name, (d.get("section") or "").strip(), (d.get("code") or "").strip(), rate, money("single"), money("annual"), 1 if d.get("is_active", True) else 0)
    with dbm.write_tx(conn):
        try:
            if d.get("id"):
                conn.execute("UPDATE tds_nature SET name=?, section=?, code=?, rate_bp=?, single_paise=?, annual_paise=?, is_active=? WHERE id=?", vals + (int(d["id"]),))
                nid = int(d["id"])
            else:
                nid = conn.execute("INSERT INTO tds_nature(name, section, code, rate_bp, single_paise, annual_paise, is_active) VALUES (?,?,?,?,?,?,?)", vals).lastrowid
        except Exception as e:
            if "UNIQUE" in str(e):
                raise UserError("A nature of payment with this name already exists.")
            raise
        dbm.audit(conn, "alter", "tds_nature", nid, f"{name} {rate / 100}%")
    return {"id": nid}


def save_pan(conn, d: dict) -> dict:
    lid = int(d.get("ledger_id") or 0)
    pan = (d.get("pan") or "").strip().upper()
    if pan and not PAN_RE.match(pan):
        raise UserError("A PAN has 10 characters: 5 letters, 4 digits, 1 letter (like ABCDE1234F).")
    with dbm.write_tx(conn):
        if pan:
            conn.execute("INSERT INTO tds_party(ledger_id, pan) VALUES (?,?) ON CONFLICT(ledger_id) DO UPDATE SET pan=excluded.pan", (lid, pan))
        else:
            conn.execute("DELETE FROM tds_party WHERE ledger_id=?", (lid,))
    return {"ok": True}


def compute(conn, nature_id, party_id, base_paise: int, on: str, exclude_voucher=None, rate_override=None) -> dict:
    n = conn.execute("SELECT * FROM tds_nature WHERE id=?", (int(nature_id or 0),)).fetchone()
    if not n:
        raise UserError("Please choose the nature of payment.")
    if base_paise <= 0:
        raise UserError("The amount to deduct tax on must be above zero.")
    fy = fy_label(parse_iso(on), dbm.get_company(conn)["fy_start_month"])
    ex = int(exclude_voucher or 0)
    prior = conn.execute(
        """SELECT COALESCE(SUM(t.base_paise),0) b, COALESCE(SUM(t.taxed_base_paise),0) tb, COALESCE(SUM(t.tax_paise),0) tx
           FROM tds_lines t JOIN vouchers v ON v.id=t.voucher_id
           WHERE v.status='posted' AND v.fy=? AND t.party_ledger_id=? AND t.nature_id=? AND v.id<>? AND v.vdate<=?""",
        (fy, int(party_id or 0), n["id"], ex, on)).fetchone()
    pan = conn.execute("SELECT pan FROM tds_party WHERE ledger_id=?", (int(party_id or 0),)).fetchone()
    rate = n["rate_bp"]
    notes = []
    if rate_override not in (None, ""):
        rate = round(float(rate_override) * 100)
        notes.append("Rate typed by you (for example under a lower-deduction certificate).")
    elif not (pan and pan["pan"]):
        rate = max(NO_PAN_RATE_BP, rate * 2)
        notes.append("No PAN is recorded for this party, so the higher rate is used (the higher of 20% or twice the rate).")
    single, annual = n["single_paise"], n["annual_paise"]
    by_single = bool(single) and base_paise > single
    by_annual = bool(annual) and prior["b"] + base_paise > annual
    if not single and not annual:
        liable, taxed_base = True, base_paise
    elif by_single:
        liable, taxed_base = True, base_paise
    elif by_annual:
        liable, taxed_base = True, prior["b"] - prior["tb"] + base_paise          # catch up on earlier untaxed payments
        if prior["b"] > prior["tb"]:
            notes.append("The yearly limit is crossed now, so tax is also taken on the earlier payments that were below the limit.")
    else:
        liable, taxed_base = False, 0
        notes.append("Below the limit: no tax needs to be deducted on this payment.")
    tax = round(taxed_base * rate / 10000) if liable else 0
    return {"nature": dict(n), "rate_bp": rate, "taxable_base_paise": taxed_base, "tax_paise": tax, "liable": liable,
            "prior_base_paise": prior["b"], "ledger_id": ledger_id(conn), "notes": notes, "has_pan": bool(pan and pan["pan"])}


def save_voucher_tds(conn, vid: int, vdate: str, tds: dict | None) -> None:
    """Keep the TDS record of a voucher; it must match the credit on the TDS Payable ledger of that voucher."""
    conn.execute("DELETE FROM tds_lines WHERE voucher_id=?", (vid,))
    if not tds or not int(tds.get("tax_paise") or 0):
        return
    lid = ledger_id(conn)
    cr = conn.execute("SELECT COALESCE(SUM(credit_paise),0) FROM entries WHERE voucher_id=? AND ledger_id=?", (vid, lid)).fetchone()[0]
    if cr != int(tds["tax_paise"]):
        raise UserError("The TDS amount does not match the 'TDS Payable' line of this voucher. Press 'Add TDS' again so the lines are rebuilt, then save.")
    if not conn.execute("SELECT 1 FROM tds_nature WHERE id=?", (int(tds["nature_id"]),)).fetchone():
        raise UserError("That nature of payment no longer exists.")
    conn.execute("INSERT INTO tds_lines(voucher_id, party_ledger_id, nature_id, base_paise, taxed_base_paise, rate_bp, tax_paise) VALUES (?,?,?,?,?,?,?)",
                 (vid, int(tds["party"]), int(tds["nature_id"]), int(tds["base_paise"]), int(tds["taxed_base_paise"]), int(tds["rate_bp"]), int(tds["tax_paise"])))


def get_voucher_tds(conn, vid: int):
    r = conn.execute("SELECT * FROM tds_lines WHERE voucher_id=?", (vid,)).fetchone()
    return None if not r else {"nature_id": r["nature_id"], "party": r["party_ledger_id"], "base_paise": r["base_paise"],
                               "taxed_base_paise": r["taxed_base_paise"], "rate_bp": r["rate_bp"], "tax_paise": r["tax_paise"]}


# ---------------------------------------------------------------------------
def statement(conn, frm: str, to: str) -> dict:
    """Deductee-wise list (the data of Form 26Q) and a total by nature."""
    rows = [dict(r) for r in conn.execute(
        """SELECT v.vdate, v.vtype, v.number, v.fy, l.name AS party, COALESCE(p.pan,'') AS pan, n.section, n.code, n.name AS nature,
                  t.base_paise, t.taxed_base_paise, t.rate_bp, t.tax_paise
           FROM tds_lines t JOIN vouchers v ON v.id=t.voucher_id JOIN ledgers l ON l.id=t.party_ledger_id
           JOIN tds_nature n ON n.id=t.nature_id LEFT JOIN tds_party p ON p.ledger_id=t.party_ledger_id
           WHERE v.status='posted' AND v.vdate>=? AND v.vdate<=? ORDER BY v.vdate, v.id""", (frm, to))]
    by = {}
    for r in rows:
        d = by.setdefault(r["nature"], {"nature": r["nature"], "section": r["section"], "base": 0, "tax": 0, "count": 0})
        d["base"] += r["base_paise"]; d["tax"] += r["tax_paise"]; d["count"] += 1
    return {"rows": rows, "by_nature": list(by.values()), "total_tax": sum(r["tax_paise"] for r in rows),
            "missing_pan": sorted({r["party"] for r in rows if not r["pan"]})}


def save_challan(conn, d: dict) -> dict:
    from .money import parse_iso, parse_amount
    paid = parse_iso(d.get("paid_on"), "Date of deposit")
    fm = str(d.get("for_month") or "")
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", fm):
        raise UserError("Please choose the month the tax was deducted in.")
    amt = parse_amount(d.get("amount"), "Amount deposited")
    with dbm.write_tx(conn):
        cid = conn.execute("INSERT INTO tds_challans(paid_on, for_month, bsr, serial, amount_paise, interest_paise, note) VALUES (?,?,?,?,?,?,?)",
                           (paid, fm, str(d.get("bsr") or "").strip(), str(d.get("serial") or "").strip(), amt,
                            parse_amount(d.get("interest"), "Interest") if str(d.get("interest") or "").strip() not in ("", "0", "0.00") else 0,
                            str(d.get("note") or "").strip())).lastrowid
        dbm.audit(conn, "create", "tds_challan", cid, f"{paid} for {fm} amount {amt}")
    return {"id": cid}


def delete_challan(conn, cid: int) -> dict:
    with dbm.write_tx(conn):
        conn.execute("DELETE FROM tds_challans WHERE id=?", (int(cid),))
        dbm.audit(conn, "delete", "tds_challan", int(cid), "")
    return {"ok": True}


def _due(month: str) -> str:
    y, m = int(month[:4]), int(month[5:])
    if m == 3:
        return f"{y}-04-30"
    y2, m2 = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{y2}-{m2:02d}-07"


def deposits(conn, today: str) -> dict:
    """Month by month: tax deducted, tax deposited, balance and the due date (7th of next month; 30 April for March)."""
    ded = {r["m"]: r["t"] for r in conn.execute(
        "SELECT substr(v.vdate,1,7) m, SUM(t.tax_paise) t FROM tds_lines t JOIN vouchers v ON v.id=t.voucher_id WHERE v.status='posted' GROUP BY m")}
    dep = {r["m"]: (r["a"], r["last"]) for r in conn.execute("SELECT for_month m, SUM(amount_paise) a, MAX(paid_on) last FROM tds_challans GROUP BY for_month")}
    months = sorted(set(ded) | set(dep))
    out = []
    for m in months:
        d, (p, last) = ded.get(m, 0), dep.get(m, (0, None))
        due = _due(m)
        bal = d - p
        status = "Paid" if bal <= 0 and d else ("Overdue" if bal > 0 and today > due else ("Due" if bal > 0 else ""))
        if status == "Paid" and last and last > due:
            status = "Paid late"
        out.append({"month": m, "deducted_paise": d, "deposited_paise": p, "balance_paise": bal, "due": due, "last_paid": last, "status": status})
    challans = [dict(r) for r in conn.execute("SELECT * FROM tds_challans ORDER BY paid_on DESC, id DESC")]
    return {"months": out, "challans": challans, "balance_total": sum(x["balance_paise"] for x in out)}
