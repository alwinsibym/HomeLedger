"""Bulk entry: read a CSV / Excel file (a typed-up notebook, a bank statement), suggest where each line belongs,
and enter the reviewed lines as Payment / Receipt vouchers. Also serves the Quick Entry screen."""
import base64
import csv
import datetime as dt
import io
import re
import zipfile
import xml.etree.ElementTree as ET

from . import db as dbm, service as sv
from .errors import UserError
from .money import parse_iso

MAX_ROWS = 5000
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


# ------------------------------------------------------------------ reading files
def _xlsx_rows(raw: bytes) -> list:
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise UserError("This does not look like an Excel (.xlsx) file.")
    if sum(i.file_size for i in z.infolist()) > 80_000_000:
        raise UserError("This Excel file is too large to read safely.")

    def xml(name):
        data = z.read(name)
        if b"<!DOCTYPE" in data[:2000].upper() or b"<!ENTITY" in data[:20000].upper():
            raise UserError("This Excel file contains features that are not accepted.")
        return ET.fromstring(data)
    strings = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in xml("xl/sharedStrings.xml").findall("m:si", _NS):
            strings.append("".join(t.text or "" for t in si.iter("{%s}t" % _NS["m"])))
    sheet = next((n for n in sorted(z.namelist()) if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")), None)
    if not sheet:
        raise UserError("No sheet found in this Excel file.")
    rows = []
    for r in xml(sheet).iter("{%s}row" % _NS["m"]):
        cells = {}
        for c in r.findall("m:c", _NS):
            ref = re.match(r"([A-Z]+)", c.get("r") or "")
            if not ref:
                continue
            col = 0
            for ch in ref.group(1):
                col = col * 26 + ord(ch) - 64
            t, v = c.get("t"), c.find("m:v", _NS)
            if t == "s" and v is not None:
                val = strings[int(v.text)] if int(v.text) < len(strings) else ""
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter("{%s}t" % _NS["m"]))
            else:
                val = v.text if v is not None and v.text is not None else ""
            cells[col - 1] = val
        if cells:
            n = max(cells) + 1
            rows.append([cells.get(i, "") for i in range(n)])
        if len(rows) > MAX_ROWS + 1:
            break
    return rows


def parse_file(filename: str, b64: str) -> dict:
    try:
        raw = base64.b64decode(b64 or "")
    except Exception:
        raise UserError("The file could not be read.")
    if not raw:
        raise UserError("The file is empty.")
    if raw[:2] == b"PK":
        rows = _xlsx_rows(raw)
    else:
        text = None
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc); break
            except UnicodeDecodeError:
                continue
        try:
            dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = [r for r in csv.reader(io.StringIO(text), dialect)][:MAX_ROWS + 1]
    rows = [[str(c).strip() for c in r] for r in rows if any(str(c).strip() for c in r)]
    if len(rows) < 2:
        raise UserError("The file needs a heading row and at least one line of data.")
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    return {"headers": rows[0], "rows": rows[1:MAX_ROWS + 1], "truncated": len(rows) - 1 > MAX_ROWS}


# ------------------------------------------------------------------ cleaning values
_FORMATS = ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%d-%b-%Y", "%d-%b-%y", "%d %b %Y", "%d-%m-%y", "%d/%m/%y", "%d-%B-%Y", "%b %d, %Y")


def clean_date(s: str):
    s = (s or "").strip()
    if not s:
        return None
    if re.fullmatch(r"\d{5}(\.\d+)?", s) and 20000 < float(s) < 80000:          # Excel serial date
        return (dt.date(1899, 12, 30) + dt.timedelta(days=int(float(s)))).isoformat()
    s = s.split(" ")[0] if re.match(r"\d{4}-\d{2}-\d{2} \d", s) else s
    for f in _FORMATS:
        try:
            return dt.datetime.strptime(s, f).date().isoformat()
        except ValueError:
            continue
    return None


def clean_amount(s: str):
    """paise (positive) and whether it was marked as credit / negative; None when it is not a number."""
    t = (s or "").strip().replace("₹", "").replace("Rs.", "").replace("Rs", "").replace(",", "").replace(" ", "")
    if not t:
        return None
    neg = t.startswith("(") and t.endswith(")") or t.startswith("-")
    cr = bool(re.search(r"cr$", t, re.I))
    t = re.sub(r"(dr|cr)$", "", t.strip("()-"), flags=re.I)
    if not re.fullmatch(r"\d+(\.\d{1,2})?", t):
        return None
    return round(float(t) * 100), (neg or cr)


# ------------------------------------------------------------------ categorising
def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", (text or "").lower())).strip()


def suggest(conn, text: str):
    """(ledger_id, source) for a description: saved rule first, then what earlier entries with the same words used."""
    n = _norm(text)
    if not n:
        return None, ""
    best = None
    for r in conn.execute("SELECT keyword, ledger_id FROM cat_rules"):
        k = _norm(r["keyword"])
        if k and k in n and (not best or len(k) > len(best[0])):
            best = (k, r["ledger_id"])
    if best:
        return best[1], "rule"
    words = [w for w in n.split() if len(w) >= 3][:3]
    for w in words:
        row = conn.execute(
            """SELECT e.ledger_id, COUNT(*) c FROM vouchers v JOIN entries e ON e.voucher_id=v.id JOIN ledgers l ON l.id=e.ledger_id
               WHERE v.status='posted' AND v.vtype IN ('Payment','Receipt') AND lower(v.narration) LIKE ? AND l.cb_kind IS NULL
               GROUP BY e.ledger_id ORDER BY c DESC LIMIT 1""", (f"%{w}%",)).fetchone()
        if row:
            return row["ledger_id"], "history"
    return None, ""


def preview(conn, d: dict) -> dict:
    """Turn mapped columns into proposed entries. d: rows, map{date,desc,amount,debit,credit,type,ref}, out_words."""
    m = d.get("map") or {}
    rows = d.get("rows") or []

    def col(r, k):
        i = m.get(k)
        return r[int(i)] if i not in (None, "") and int(i) < len(r) else ""
    if m.get("date") in (None, "") or (m.get("amount") in (None, "") and m.get("debit") in (None, "") and m.get("credit") in (None, "")):
        raise UserError("Please choose which column holds the date and which holds the amount.")
    out, bad = [], 0
    for ix, r in enumerate(rows):
        date = clean_date(col(r, "date"))
        amt = None
        direction = None
        if m.get("amount") not in (None, ""):
            a = clean_amount(col(r, "amount"))
            if a:
                amt = a[0]
                tcol = col(r, "type").lower()
                if tcol:
                    direction = "in" if re.search(r"\b(cr|credit|in|receipt|received|income)\b", tcol) else "out"
                else:
                    direction = "in" if a[1] else "out"
        else:
            dr, cr = clean_amount(col(r, "debit")), clean_amount(col(r, "credit"))
            if dr and dr[0]:
                amt, direction = dr[0], "out"
            elif cr and cr[0]:
                amt, direction = cr[0], "in"
        if d.get("flip") and direction:
            direction = "in" if direction == "out" else "out"
        desc = col(r, "desc")
        problem = ""
        if not date:
            problem = "date not understood"
        elif not amt:
            problem = "amount not understood"
        lid, src = suggest(conn, desc) if not problem else (None, "")
        dup = False
        if not problem:
            dup = bool(conn.execute(
                "SELECT 1 FROM vouchers v JOIN entries e ON e.voucher_id=v.id WHERE v.vdate=? AND v.vtype IN ('Payment','Receipt') AND v.status<>'cancelled' "
                "AND (e.debit_paise=? OR e.credit_paise=?) AND lower(v.narration)=lower(?) LIMIT 1", (date, amt, amt, desc.strip())).fetchone())
        bad += 1 if problem else 0
        out.append({"row": ix, "date": date, "desc": desc, "amount_paise": amt, "dir": direction, "ref": col(r, "ref"), "ledger_id": lid, "source": src, "problem": problem, "duplicate": dup})
    return {"rows": out, "problems": bad}


def commit(conn, d: dict) -> dict:
    """Enter reviewed lines. d: bank_ledger_id, rows [{date, dir in|out, amount_paise, ledger_id, desc, ref, att_id?}], remember."""
    bank = int(d.get("bank_ledger_id") or 0)
    b = conn.execute("SELECT l.id FROM ledgers l WHERE l.id=? AND l.cb_kind IS NOT NULL", (bank,)).fetchone()
    if not b:
        raise UserError("Please choose the Cash or Bank ledger that the money moved through.")
    rows = d.get("rows") or []
    if not rows:
        raise UserError("There is nothing to enter.")
    todo = []
    for i, r in enumerate(rows, 1):
        try:
            date = parse_iso(r.get("date"), "Date")
        except UserError:
            raise UserError(f"Line {i}: the date is not valid.")
        amt = int(r.get("amount_paise") or 0)
        if amt <= 0:
            raise UserError(f"Line {i}: the amount must be above zero.")
        lid = int(r.get("ledger_id") or 0)
        if not lid or lid == bank or not conn.execute("SELECT 1 FROM ledgers WHERE id=?", (lid,)).fetchone():
            raise UserError(f"Line {i}: please choose the account (ledger) it belongs to.")
        if r.get("dir") not in ("in", "out"):
            raise UserError(f"Line {i}: please say whether money came in or went out.")
        todo.append((date, r["dir"], amt, lid, (r.get("desc") or "").strip(), (r.get("ref") or "").strip(), r.get("att_id")))
    from . import attach
    made, ids = 0, []
    try:
        for date, direction, amt, lid, desc, ref, att in todo:
            amount = f"{amt / 100:.2f}"
            lines = ([{"ledger_id": lid, "side": "Dr", "amount": amount}, {"ledger_id": bank, "side": "Cr", "amount": amount}] if direction == "out"
                     else [{"ledger_id": bank, "side": "Dr", "amount": amount}, {"ledger_id": lid, "side": "Cr", "amount": amount}])
            v = sv.save_voucher(conn, {"vtype": "Payment" if direction == "out" else "Receipt", "date": date, "narration": desc, "ref": ref, "lines": lines})
            made += 1
            ids.append(v["id"])
            if att:
                attach.link(conn, int(att), v["id"])
    except UserError as e:
        raise UserError(f"{made} of {len(todo)} lines were entered before a problem stopped the rest: {e}")
    if d.get("remember"):
        with dbm.write_tx(conn):
            for date, direction, amt, lid, desc, ref, att in todo:
                key = " ".join(w for w in _norm(desc).split() if len(w) >= 3)[:40]
                if len(key) >= 4 and not conn.execute("SELECT 1 FROM cat_rules WHERE keyword=?", (key,)).fetchone():
                    conn.execute("INSERT INTO cat_rules(keyword, ledger_id) VALUES (?,?)", (key, lid))
    return {"entered": made, "ids": ids}


def rules(conn) -> list:
    return [dict(r) for r in conn.execute("SELECT r.id, r.keyword, r.ledger_id, l.name AS ledger FROM cat_rules r JOIN ledgers l ON l.id=r.ledger_id ORDER BY r.keyword")]


def save_rule(conn, d: dict) -> dict:
    kw = (d.get("keyword") or "").strip()
    if len(kw) < 3:
        raise UserError("The keyword needs at least 3 letters.")
    lid = int(d.get("ledger_id") or 0)
    if not conn.execute("SELECT 1 FROM ledgers WHERE id=?", (lid,)).fetchone():
        raise UserError("Please choose the ledger.")
    with dbm.write_tx(conn):
        conn.execute("INSERT INTO cat_rules(keyword, ledger_id) VALUES (?,?) ON CONFLICT(keyword) DO UPDATE SET ledger_id=excluded.ledger_id", (kw, lid))
    return {"ok": True}


def delete_rule(conn, rid) -> dict:
    with dbm.write_tx(conn):
        conn.execute("DELETE FROM cat_rules WHERE id=?", (int(rid),))
    return {"ok": True}
