"""Bills and receipts kept inside the database (photos / PDFs), linked to vouchers or waiting in the Bill Inbox."""
import base64
import hashlib

from . import db as dbm
from .errors import UserError

MAX_BYTES = 6 * 1024 * 1024


def _kind(b: bytes):
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    if b[:5] == b"%PDF-":
        return "application/pdf"
    return None


def add(conn, d: dict) -> dict:
    try:
        raw = base64.b64decode(d.get("data") or "", validate=False)
    except Exception:
        raise UserError("The file could not be read.")
    if not raw:
        raise UserError("The file is empty.")
    if len(raw) > MAX_BYTES:
        raise UserError("This file is larger than 6 MB. Photos are shrunk automatically; for a PDF please use a smaller file.")
    mime = _kind(raw)
    if not mime:
        raise UserError("Only photos (JPG, PNG, WEBP, GIF) and PDF files can be kept.")
    sha = hashlib.sha256(raw).hexdigest()
    dup = conn.execute("SELECT id, voucher_id FROM attachments WHERE sha256=?", (sha,)).fetchone()
    if dup:
        raise UserError("This exact file is already stored" + (" and linked to a voucher." if dup["voucher_id"] else " in the Bill Inbox."))
    vid = int(d["voucher_id"]) if d.get("voucher_id") else None
    if vid and not conn.execute("SELECT 1 FROM vouchers WHERE id=?", (vid,)).fetchone():
        raise UserError("That voucher no longer exists.")
    name = (d.get("filename") or "bill").replace("\\", "/").split("/")[-1][:120]
    with dbm.write_tx(conn):
        aid = conn.execute("INSERT INTO attachments(voucher_id, filename, mime, size, sha256, note, data, created_at) VALUES (?,?,?,?,?,?,?,?)",
                           (vid, name, mime, len(raw), sha, (d.get("note") or "").strip()[:300], raw, dbm.now_iso())).lastrowid
        dbm.audit(conn, "create", "attachment", aid, name)
    return {"id": aid}


def listing(conn, voucher_id=None, inbox=False) -> list:
    q = "SELECT id, voucher_id, filename, mime, size, note, created_at FROM attachments"
    if voucher_id:
        rows = conn.execute(q + " WHERE voucher_id=? ORDER BY id", (int(voucher_id),))
    elif inbox:
        rows = conn.execute(q + " WHERE voucher_id IS NULL ORDER BY id")
    else:
        rows = conn.execute(q + " ORDER BY id DESC LIMIT 500")
    return [dict(r) for r in rows]


def get_file(conn, aid: int):
    r = conn.execute("SELECT filename, mime, data FROM attachments WHERE id=?", (int(aid),)).fetchone()
    if not r:
        raise UserError("That file no longer exists.")
    return ("bin", r["filename"], bytes(r["data"]), r["mime"])


def link(conn, aid: int, voucher_id) -> dict:
    with dbm.write_tx(conn):
        if voucher_id and not conn.execute("SELECT 1 FROM vouchers WHERE id=?", (int(voucher_id),)).fetchone():
            raise UserError("That voucher no longer exists.")
        conn.execute("UPDATE attachments SET voucher_id=? WHERE id=?", (int(voucher_id) if voucher_id else None, int(aid)))
    return {"ok": True}


def delete(conn, aid: int) -> dict:
    with dbm.write_tx(conn):
        r = conn.execute("SELECT filename FROM attachments WHERE id=?", (int(aid),)).fetchone()
        if r:
            conn.execute("DELETE FROM attachments WHERE id=?", (int(aid),))
            dbm.audit(conn, "delete", "attachment", int(aid), r["filename"])
    return {"ok": True}


def counts(conn) -> dict:
    return {r["voucher_id"]: r["n"] for r in conn.execute("SELECT voucher_id, COUNT(*) n FROM attachments WHERE voucher_id IS NOT NULL GROUP BY voucher_id")}
