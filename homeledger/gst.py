"""GST (stage 1): registration details, tax ledgers, tax calculation on invoices, and GSTR-1 / GSTR-3B style summaries.

Scope: regular intra-state (CGST + SGST) and inter-state (IGST) supplies of goods or services with a rate per item.
NOT covered: reverse charge, composition scheme, cess, TCS/TDS under GST, input-credit eligibility rules, e-invoicing,
e-way bills, exports and SEZ supplies, and return filing. Figures are for checking and for the accountant, not for filing.
"""
import re

from . import db as dbm
from .errors import UserError
from .money import parse_iso

STATES = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh", "05": "Uttarakhand",
    "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura", "17": "Meghalaya",
    "18": "Assam", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
    "24": "Gujarat", "26": "Dadra & Nagar Haveli and Daman & Diu", "27": "Maharashtra", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry", "35": "Andaman & Nicobar Islands",
    "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh", "97": "Other Territory",
}
_CH = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
RATES_BP = (0, 25, 300, 500, 1200, 1800, 2800)       # the usual slabs, as a hint for the screen only


def gstin_ok(g: str) -> bool:
    g = (g or "").strip().upper()
    if not _RE.match(g) or g[:2] not in STATES:
        return False
    total = 0
    for i, ch in enumerate(g[:14]):
        v = _CH.index(ch) * (1 if i % 2 == 0 else 2)
        total += v // 36 + v % 36
    return _CH[(36 - total % 36) % 36] == g[14]


# ---------------------------------------------------------------------------
# settings and masters
# ---------------------------------------------------------------------------
def get_config(conn) -> dict:
    return {"on": dbm.get_setting(conn, "gst_on", "0") == "1", "gstin": dbm.get_setting(conn, "gst_gstin", ""),
            "state": dbm.get_setting(conn, "gst_state", ""), "states": STATES,
            "tax_ledgers": {r["kind"]: r["ledger_id"] for r in conn.execute("SELECT * FROM gst_taxledger")}}


def save_config(conn, d: dict) -> dict:
    on = bool(d.get("on"))
    gstin = (d.get("gstin") or "").strip().upper()
    state = (d.get("state") or "").strip()
    if gstin:
        if not gstin_ok(gstin):
            raise UserError("This GSTIN does not look right (15 characters, with a valid check letter). Please check it.")
        state = gstin[:2]
    if on and state not in STATES:
        raise UserError("Please choose the state of your business (needed to decide CGST/SGST or IGST).")
    with dbm.write_tx(conn):
        dbm.set_setting(conn, "gst_on", "1" if on else "0")
        dbm.set_setting(conn, "gst_gstin", gstin)
        dbm.set_setting(conn, "gst_state", state)
        if on:
            _ensure_tax_ledgers(conn)
        dbm.audit(conn, "alter", "gst", None, f"GST {'on' if on else 'off'}, state {state}, GSTIN {gstin}")
    return get_config(conn)


def _ensure_tax_ledgers(conn):
    grp = conn.execute("SELECT id FROM acct_groups WHERE code='DUTIES'").fetchone()
    if not grp:
        raise UserError("The Duties & Taxes group is missing.")
    have = {r["kind"] for r in conn.execute("SELECT kind FROM gst_taxledger")}
    for kind, name in (("cgst", "CGST"), ("sgst", "SGST"), ("igst", "IGST")):
        if kind in have:
            continue
        r = conn.execute("SELECT id FROM ledgers WHERE name=? COLLATE NOCASE", (name,)).fetchone()
        lid = r["id"] if r else conn.execute(
            "INSERT INTO ledgers(name, group_id, nature, opening_paise, opening_type, created_at) VALUES (?,?,'liability',0,'Cr',?)",
            (name, grp["id"], dbm.now_iso())).lastrowid
        conn.execute("INSERT OR REPLACE INTO gst_taxledger(ledger_id, kind) VALUES (?,?)", (lid, kind))


def masters(conn) -> dict:
    return {"party": {r["ledger_id"]: {"gstin": r["gstin"], "state": r["state_code"], "reg": r["reg_type"]}
                      for r in conn.execute("SELECT * FROM gst_party")},
            "item": {r["item_id"]: {"hsn": r["hsn"], "rate_bp": r["rate_bp"]} for r in conn.execute("SELECT * FROM gst_item")}}


def save_party(conn, d: dict) -> dict:
    lid = int(d.get("ledger_id") or 0)
    if not conn.execute("SELECT 1 FROM ledgers WHERE id=?", (lid,)).fetchone():
        raise UserError("That ledger no longer exists.")
    gstin = (d.get("gstin") or "").strip().upper()
    state = (d.get("state") or "").strip()
    reg = d.get("reg") if d.get("reg") in ("regular", "composition", "unregistered", "consumer") else ("regular" if gstin else "unregistered")
    if gstin:
        if not gstin_ok(gstin):
            raise UserError("This GSTIN does not look right (15 characters, with a valid check letter). Please check it.")
        state = gstin[:2]
    if state and state not in STATES:
        raise UserError("Unknown state.")
    with dbm.write_tx(conn):
        if not (gstin or state) and reg in ("unregistered", "consumer"):
            conn.execute("DELETE FROM gst_party WHERE ledger_id=?", (lid,))
        else:
            conn.execute("INSERT INTO gst_party(ledger_id, gstin, state_code, reg_type) VALUES (?,?,?,?) "
                         "ON CONFLICT(ledger_id) DO UPDATE SET gstin=excluded.gstin, state_code=excluded.state_code, reg_type=excluded.reg_type",
                         (lid, gstin, state, reg))
        dbm.audit(conn, "alter", "gst_party", lid, f"{gstin} {state} {reg}")
    return {"ok": True}


def save_item(conn, d: dict) -> dict:
    iid = int(d.get("item_id") or 0)
    if not conn.execute("SELECT 1 FROM stock_items WHERE id=?", (iid,)).fetchone():
        raise UserError("That stock item no longer exists.")
    hsn = re.sub(r"\s", "", str(d.get("hsn") or ""))
    if hsn and not re.fullmatch(r"\d{4,8}", hsn):
        raise UserError("The HSN / SAC code should be 4 to 8 digits.")
    try:
        rate = round(float(str(d.get("rate") or 0).replace("%", "")) * 100)
    except ValueError:
        raise UserError("Please type the GST rate as a number, like 5 or 18.")
    if not 0 <= rate <= 10000:
        raise UserError("The GST rate must be between 0 and 100.")
    with dbm.write_tx(conn):
        conn.execute("INSERT INTO gst_item(item_id, hsn, rate_bp) VALUES (?,?,?) "
                     "ON CONFLICT(item_id) DO UPDATE SET hsn=excluded.hsn, rate_bp=excluded.rate_bp", (iid, hsn, rate))
        dbm.audit(conn, "alter", "gst_item", iid, f"HSN {hsn} rate {rate / 100}%")
    return {"ok": True}


# ---------------------------------------------------------------------------
# calculation
# ---------------------------------------------------------------------------
TAX_SIDE = {"Sales": "Cr", "Purchase": "Dr", "Credit Note": "Dr", "Debit Note": "Cr"}   # credit note = sales return here
GST_VTYPES = tuple(TAX_SIDE)


def compute(conn, vtype: str, party_ledger_id, pos_state: str, items: list) -> dict:
    cfg = get_config(conn)
    if not cfg["on"]:
        raise UserError("GST is not switched on. Turn it on in Masters > GST Setup.")
    if vtype not in GST_VTYPES:
        raise UserError("GST applies to Sales, Purchase, Credit Note and Debit Note.")
    party = conn.execute("SELECT * FROM gst_party WHERE ledger_id=?", (int(party_ledger_id or 0),)).fetchone()
    pos = (pos_state or (party["state_code"] if party else "") or cfg["state"]).strip()
    if pos not in STATES:
        raise UserError("Please choose the place of supply (state).")
    intra = pos == cfg["state"]
    groups, warnings = {}, []
    for x in items or []:
        amt = int(x.get("amount_paise") or 0)
        if amt <= 0:
            continue
        g = conn.execute("SELECT g.hsn, g.rate_bp, i.name FROM stock_items i LEFT JOIN gst_item g ON g.item_id=i.id WHERE i.id=?",
                         (int(x.get("item_id") or 0),)).fetchone()
        if not g:
            raise UserError("A stock item in the list no longer exists.")
        if g["rate_bp"] is None:
            warnings.append(f"'{g['name']}' has no GST rate set, so it is taxed at 0%. Set it in Masters > Stock Items > GST.")
        k = (g["hsn"] or "", g["rate_bp"] or 0)
        groups[k] = groups.get(k, 0) + amt
    rows = []
    for (hsn, rate), taxable in sorted(groups.items()):
        tax = round(taxable * rate / 10000)
        if intra:
            c = tax // 2
            rows.append({"hsn": hsn, "rate_bp": rate, "taxable_paise": taxable, "cgst_paise": c, "sgst_paise": tax - c, "igst_paise": 0})
        else:
            rows.append({"hsn": hsn, "rate_bp": rate, "taxable_paise": taxable, "cgst_paise": 0, "sgst_paise": 0, "igst_paise": tax})
    tot = {k: sum(r[k + "_paise"] for r in rows) for k in ("taxable", "cgst", "sgst", "igst")}
    return {"rows": rows, "totals": tot, "intra": intra, "pos": pos, "side": TAX_SIDE[vtype],
            "ledgers": cfg["tax_ledgers"], "warnings": warnings}


def save_voucher_gst(conn, vid: int, vtype: str, party_ledger_id, gst: dict | None) -> None:
    """Keep the tax breakup of an invoice. Refuses a breakup that does not match the tax ledger lines of the voucher."""
    conn.execute("DELETE FROM gst_lines WHERE voucher_id=?", (vid,))
    if not gst or not gst.get("rows") or vtype not in GST_VTYPES:
        return
    cfg = get_config(conn)
    if not cfg["on"]:
        return
    want = {"cgst": 0, "sgst": 0, "igst": 0}
    for r in gst["rows"]:
        for k in want:
            want[k] += int(r.get(k + "_paise") or 0)
    side = TAX_SIDE[vtype]
    have = {"cgst": 0, "sgst": 0, "igst": 0}
    for e in conn.execute("SELECT t.kind, e.debit_paise, e.credit_paise FROM entries e JOIN gst_taxledger t ON t.ledger_id=e.ledger_id WHERE e.voucher_id=?", (vid,)):
        if e["kind"] in have:
            have[e["kind"]] += e["debit_paise"] if side == "Dr" else e["credit_paise"]
    if want != have:
        raise UserError("The GST amounts in the tax breakup do not match the tax lines of this voucher. "
                        "Press 'Add GST' again so the tax lines are rebuilt, then save.")
    pos = str(gst.get("pos") or "")
    for r in gst["rows"]:
        conn.execute("INSERT INTO gst_lines(voucher_id, party_ledger_id, hsn, rate_bp, taxable_paise, cgst_paise, sgst_paise, igst_paise, pos_state) "
                     "VALUES (?,?,?,?,?,?,?,?,?)",
                     (vid, party_ledger_id, str(r.get("hsn") or ""), int(r.get("rate_bp") or 0), int(r.get("taxable_paise") or 0),
                      int(r.get("cgst_paise") or 0), int(r.get("sgst_paise") or 0), int(r.get("igst_paise") or 0), pos))


def get_voucher_gst(conn, vid: int) -> dict | None:
    rows = [dict(r) for r in conn.execute("SELECT hsn, rate_bp, taxable_paise, cgst_paise, sgst_paise, igst_paise, pos_state FROM gst_lines WHERE voucher_id=?", (vid,))]
    return {"rows": rows, "pos": rows[0]["pos_state"]} if rows else None


# ---------------------------------------------------------------------------
# reports
# ---------------------------------------------------------------------------
def _lines(conn, frm, to):
    return conn.execute(
        """SELECT v.id AS vid, v.vtype, v.number, v.fy, v.vdate, v.ref, g.hsn, g.rate_bp, g.taxable_paise, g.cgst_paise, g.sgst_paise,
                  g.igst_paise, g.pos_state, l.name AS party, p.gstin, p.state_code
           FROM gst_lines g JOIN vouchers v ON v.id=g.voucher_id LEFT JOIN ledgers l ON l.id=g.party_ledger_id
           LEFT JOIN gst_party p ON p.ledger_id=g.party_ledger_id
           WHERE v.status='posted' AND v.vdate>=? AND v.vdate<=? ORDER BY v.vdate, v.id""", (frm, to)).fetchall()


def summary(conn, frm, to) -> dict:
    """GSTR-3B style: outward supplies, inward supplies (input tax credit) and the net tax to pay."""
    out = {k: 0 for k in ("taxable", "cgst", "sgst", "igst")}
    inn = dict(out)
    for r in _lines(conn, frm, to):
        sign = 1 if r["vtype"] in ("Sales", "Purchase") else -1
        tgt = out if r["vtype"] in ("Sales", "Credit Note") else inn
        for k in out:
            tgt[k] += sign * r[k + "_paise"]
    net = {k: out[k] - inn[k] for k in ("cgst", "sgst", "igst")}
    return {"from": frm, "to": to, "outward": out, "inward": inn, "net": net, "net_total": sum(net.values())}


def gstr1(conn, frm, to) -> dict:
    rows = _lines(conn, frm, to)
    b2b, b2c, cdn, hsn = [], {}, [], {}
    inv = {}
    for r in rows:
        if r["vtype"] not in ("Sales", "Credit Note"):
            continue
        sign = 1 if r["vtype"] == "Sales" else -1
        tax = r["cgst_paise"] + r["sgst_paise"] + r["igst_paise"]
        item = {"date": r["vdate"], "number": f"{r['vtype']} {r['number']}", "fy": r["fy"], "party": r["party"] or "", "gstin": r["gstin"] or "",
                "pos": r["pos_state"], "rate_bp": r["rate_bp"], "taxable": r["taxable_paise"], "cgst": r["cgst_paise"], "sgst": r["sgst_paise"],
                "igst": r["igst_paise"], "value": r["taxable_paise"] + tax}
        if r["vtype"] == "Credit Note":
            cdn.append(item)
        elif r["gstin"]:
            b2b.append(item)
        else:
            k = (r["pos_state"], r["rate_bp"])
            d = b2c.setdefault(k, {"pos": r["pos_state"], "rate_bp": r["rate_bp"], "taxable": 0, "cgst": 0, "sgst": 0, "igst": 0})
            d["taxable"] += r["taxable_paise"]; d["cgst"] += r["cgst_paise"]; d["sgst"] += r["sgst_paise"]; d["igst"] += r["igst_paise"]
        h = hsn.setdefault((r["hsn"], r["rate_bp"]), {"hsn": r["hsn"], "rate_bp": r["rate_bp"], "taxable": 0, "cgst": 0, "sgst": 0, "igst": 0})
        h["taxable"] += sign * r["taxable_paise"]; h["cgst"] += sign * r["cgst_paise"]; h["sgst"] += sign * r["sgst_paise"]; h["igst"] += sign * r["igst_paise"]
    return {"from": frm, "to": to, "b2b": b2b, "b2c": sorted(b2c.values(), key=lambda x: (x["pos"], x["rate_bp"])),
            "cdn": cdn, "hsn": sorted(hsn.values(), key=lambda x: (x["hsn"], x["rate_bp"]))}


def missing_details(conn) -> dict:
    """Things that make GST figures wrong: items without a rate, registered parties without GSTIN."""
    return {"items_without_rate": [r["name"] for r in conn.execute(
        "SELECT i.name FROM stock_items i LEFT JOIN gst_item g ON g.item_id=i.id WHERE g.item_id IS NULL ORDER BY i.name")]}
