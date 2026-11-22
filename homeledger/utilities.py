"""Data repair and Tally-format (XML) import / export."""
import datetime as dt
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from . import db as dbm, service as sv
from .errors import UserError

DEBIT_SIDE_TYPES = ("Payment", "Receipt", "Contra", "Journal", "Sales", "Purchase", "Credit Note", "Debit Note")


# ---------------------------------------------------------------------------
# repair
# ---------------------------------------------------------------------------
def repair(conn) -> dict:
    """Check everything, rebuild the indexes, compact the file. Never deletes or changes an entry."""
    steps = []

    def add(name, ok, detail=""):
        steps.append({"name": name, "ok": bool(ok), "detail": detail})
    rows = [r[0] for r in conn.execute("PRAGMA integrity_check")]
    add("File integrity", rows == ["ok"], "No damage found." if rows == ["ok"] else "; ".join(rows[:3]))
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    add("Links between records", not fk, "All links are intact." if not fk else f"{len(fk)} broken link(s) found.")
    bad = conn.execute(
        """SELECT v.vtype, v.fy, v.number FROM vouchers v JOIN entries e ON e.voucher_id=v.id
           WHERE v.status<>'cancelled' GROUP BY v.id HAVING SUM(e.debit_paise)<>SUM(e.credit_paise)""").fetchall()
    add("Every entry balances (debit = credit)", not bad,
        "All balanced." if not bad else "Unbalanced: " + ", ".join(f"{r[0]} {r[2]} ({r[1]})" for r in bad[:5]))
    dup = conn.execute("SELECT COUNT(*) FROM (SELECT 1 FROM vouchers GROUP BY vtype, fy, number HAVING COUNT(*)>1)").fetchone()[0]
    add("Voucher numbers are unique", dup == 0, "No duplicates." if not dup else f"{dup} duplicate number(s).")
    if rows == ["ok"]:
        try:
            conn.execute("REINDEX")
            add("Indexes rebuilt", True, "Search and reports tables were rebuilt.")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("VACUUM")
            conn.execute("ANALYZE")
            add("File compacted", True, "Free space was reclaimed.")
        except Exception as e:                      # e.g. disk full: nothing is lost
            add("Rebuild", False, str(e))
    ok = all(s["ok"] for s in steps)
    return {"ok": ok, "steps": steps,
            "message": "Your data is in good order." if ok else
            "Something needs attention. A safety copy was taken before checking; use Backup & Restore to go back if needed."}


# ---------------------------------------------------------------------------
# Tally XML
# ---------------------------------------------------------------------------
def _tdate(iso):
    return iso.replace("-", "")


def _amt(p):
    return f"{p / 100:.2f}"


def export_xml(conn, frm: str, to: str) -> bytes:
    co = dbm.get_company(conn)
    out = ['<?xml version="1.0" encoding="UTF-8"?>', "<ENVELOPE>", "<HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>",
           "<BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>All Masters</REPORTNAME><STATICVARIABLES>",
           f"<SVCURRENTCOMPANY>{escape(co['name'])}</SVCURRENTCOMPANY></STATICVARIABLES></REQUESTDESC><REQUESTDATA>"]
    groups = {r["id"]: r for r in conn.execute("SELECT * FROM acct_groups")}
    std = {x[1].lower() for x in dbm.GROUPS}
    for g in groups.values():
        if g["name"].lower() not in std:
            par = groups[g["parent_id"]]["name"] if g["parent_id"] else "Primary"
            out.append(f'<TALLYMESSAGE xmlns:UDF="TallyUDF"><GROUP NAME="{escape(g["name"], {chr(34): "&quot;"})}" ACTION="Create">'
                       f"<NAME>{escape(g['name'])}</NAME><PARENT>{escape(par)}</PARENT><NATURE>{g['nature']}</NATURE></GROUP></TALLYMESSAGE>")
    for l in conn.execute("SELECT * FROM ledgers ORDER BY name"):
        op = 0
        if l["opening_paise"]:
            op = l["opening_paise"] * (-1 if l["opening_type"] == "Dr" else 1)
        out.append(f'<TALLYMESSAGE xmlns:UDF="TallyUDF"><LEDGER NAME="{escape(l["name"], {chr(34): "&quot;"})}" ACTION="Create">'
                   f"<NAME>{escape(l['name'])}</NAME><PARENT>{escape(groups[l['group_id']]['name'])}</PARENT>"
                   f"<OPENINGBALANCE>{_amt(op)}</OPENINGBALANCE></LEDGER></TALLYMESSAGE>")
    led = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM ledgers")}
    n = 0
    for v in conn.execute("SELECT * FROM vouchers WHERE vdate>=? AND vdate<=? AND status='posted' ORDER BY vdate, id", (frm, to)):
        n += 1
        out.append('<TALLYMESSAGE xmlns:UDF="TallyUDF">'
                   f'<VOUCHER VCHTYPE="{escape(v["vtype"])}" ACTION="Create">'
                   f"<DATE>{_tdate(v['vdate'])}</DATE><VOUCHERTYPENAME>{escape(v['vtype'])}</VOUCHERTYPENAME>"
                   f"<VOUCHERNUMBER>{v['number']}</VOUCHERNUMBER><NARRATION>{escape(v['narration'] or '')}</NARRATION>")
        for e in conn.execute("SELECT * FROM entries WHERE voucher_id=? ORDER BY line_no", (v["id"],)):
            dr = e["debit_paise"] > 0
            amount = -e["debit_paise"] if dr else e["credit_paise"]     # Tally: debit is negative
            out.append(f"<ALLLEDGERENTRIES.LIST><LEDGERNAME>{escape(led[e['ledger_id']])}</LEDGERNAME>"
                       f"<ISDEEMEDPOSITIVE>{'Yes' if dr else 'No'}</ISDEEMEDPOSITIVE><AMOUNT>{_amt(amount)}</AMOUNT></ALLLEDGERENTRIES.LIST>")
        out.append("</VOUCHER></TALLYMESSAGE>")
    out.append("</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>")
    return "\n".join(out).encode("utf-8")


def _find_all(el, tag):
    return [x for x in el.iter() if x.tag == tag]


def _text(el, tag, default=""):
    for x in el.iter():
        if x.tag == tag and x.text:
            return x.text.strip()
    return default


def import_xml(conn, raw: bytes) -> dict:
    head = raw[:4000].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in raw[:20000].upper():
        raise UserError("This file contains features HomeLedger does not accept for safety, so it was not imported.")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raise UserError("This is not a valid Tally XML file.")
    res = {"groups": 0, "ledgers": 0, "vouchers": 0, "skipped": [], "errors": []}
    gid = {r["name"].lower(): r["id"] for r in conn.execute("SELECT id, name FROM acct_groups")}
    # groups (parents may be listed after children, so retry a few passes)
    pending = [((g.findtext("NAME") or g.get("NAME") or ""), (g.findtext("PARENT") or "").strip(), (g.findtext("NATURE") or "").strip())
               for g in _find_all(root, "GROUP")]
    for _ in range(4):
        left = []
        for name, parent, nature in pending:
            name = name.strip()
            if not name or name.lower() in gid:
                continue
            if parent and parent.lower() not in gid and parent != "Primary":
                left.append((name, parent, nature)); continue
            try:
                if parent == "Primary" or not parent:         # a top-level group needs its nature
                    if nature not in sv.NATURES:
                        res["skipped"].append(f"Group {name}: top-level group without a nature"); continue
                    with dbm.write_tx(conn):
                        conn.execute("INSERT INTO acct_groups(name, parent_id, nature, is_system, sort) VALUES (?,NULL,?,0,1000)", (name, nature))
                    gid[name.lower()] = conn.execute("SELECT id FROM acct_groups WHERE name=?", (name,)).fetchone()[0]
                    res["groups"] += 1
                    continue
                r = sv.save_group(conn, {"name": name, "parent_id": gid.get(parent.lower())})
                gid[name.lower()] = r["id"] if isinstance(r, dict) and "id" in r else conn.execute("SELECT id FROM acct_groups WHERE name=?", (name,)).fetchone()[0]
                res["groups"] += 1
            except UserError as e:
                res["errors"].append(f"Group {name}: {e}")
        pending = left
    lid = {r["name"].lower(): r["id"] for r in conn.execute("SELECT id, name FROM ledgers")}
    for l in _find_all(root, "LEDGER"):
        name = (l.findtext("NAME") or l.get("NAME") or "").strip()
        if not name or name.lower() in lid:
            continue
        parent = (l.findtext("PARENT") or "").strip().lower()
        if parent not in gid:
            res["skipped"].append(f"Ledger {name}: group '{parent}' not found")
            continue
        try:
            ob = float(l.findtext("OPENINGBALANCE") or 0)
        except ValueError:
            ob = 0
        grp = conn.execute("SELECT nature FROM acct_groups WHERE id=?", (gid[parent],)).fetchone()
        d = {"name": name, "group_id": gid[parent]}
        if ob and grp["nature"] in sv.REAL:
            d["opening"] = f"{abs(ob):.2f}"
            d["opening_type"] = "Dr" if ob < 0 else "Cr"
        try:
            r = sv.save_ledger(conn, d)
            lid[name.lower()] = r["id"] if isinstance(r, dict) and "id" in r else conn.execute("SELECT id FROM ledgers WHERE name=?", (name,)).fetchone()[0]
            res["ledgers"] += 1
        except UserError as e:
            res["errors"].append(f"Ledger {name}: {e}")
    for v in _find_all(root, "VOUCHER"):
        vt = (_text(v, "VOUCHERTYPENAME") or v.get("VCHTYPE") or "").strip()
        ds = _text(v, "DATE")
        tag = f"{vt} {_text(v, 'VOUCHERNUMBER')} {ds}"
        if vt not in sv.VTYPES:
            res["skipped"].append(f"{tag}: voucher type '{vt}' is not supported"); continue
        try:
            date = dt.datetime.strptime(ds, "%Y%m%d").date().isoformat()
        except ValueError:
            res["skipped"].append(f"{tag}: bad date"); continue
        lines, ok = [], True
        for e in v:
            if not e.tag.endswith("LEDGERENTRIES.LIST"):
                continue
            nm = (e.findtext("LEDGERNAME") or "").strip().lower()
            try:
                amount = float(e.findtext("AMOUNT") or 0)
            except ValueError:
                amount = 0
            if nm not in lid or amount == 0:
                ok = False; res["skipped"].append(f"{tag}: ledger '{nm}' missing or zero amount"); break
            lines.append({"ledger_id": lid[nm], "side": "Dr" if amount < 0 else "Cr", "amount": f"{abs(amount):.2f}"})
        if not ok:
            continue
        try:
            sv.save_voucher(conn, {"vtype": vt, "date": date, "narration": _text(v, "NARRATION"), "lines": lines})
            res["vouchers"] += 1
        except UserError as e:
            res["skipped"].append(f"{tag}: {e}")
    res["skipped"] = res["skipped"][:60]
    return res
