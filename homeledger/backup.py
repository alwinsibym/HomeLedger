"""Backups: consistent snapshots, rotation, second-copy folder, restore."""
from __future__ import annotations

import datetime as dt
import re
import shutil
import sqlite3
import time
from pathlib import Path

from . import db as dbm
from .errors import UserError

NAME_RE = re.compile(r"^homeledger-(\d{8})-(\d{6})-([a-z\-]+)\.db$")


def _stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def make_snapshot(db_file: Path, dest_dir: Path, reason: str = "auto") -> Path:
    """Consistent copy of the live database (safe while the app is running), verified before it is kept."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    reason = re.sub(r"[^a-z\-]", "", reason.lower()) or "auto"
    dest = dest_dir / f"homeledger-{_stamp()}-{reason}.db"
    while dest.exists():  # two backups in the same second: wait for the clock to move on
        time.sleep(1.05)
        dest = dest_dir / f"homeledger-{_stamp()}-{reason}.db"
    tmp = dest.with_suffix(".tmp")
    src = sqlite3.connect(str(db_file), timeout=30)
    try:
        out = sqlite3.connect(str(tmp))
        try:
            src.backup(out)
        finally:
            out.close()
    finally:
        src.close()
    problems = dbm.quick_check(tmp)
    if problems:
        tmp.unlink(missing_ok=True)
        raise UserError("The backup could not be verified, so it was not kept: " + "; ".join(problems))
    tmp.replace(dest)
    return dest


def list_backups(dest_dir: Path) -> list:
    out = []
    for p in sorted(dest_dir.glob("homeledger-*.db"), reverse=True):
        m = NAME_RE.match(p.name)
        if not m:
            continue
        when = dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        out.append({"name": p.name, "when": when.isoformat(sep=" "), "reason": m.group(3),
                    "size": p.stat().st_size})
    out.sort(key=lambda x: x["when"], reverse=True)
    return out


def rotate(dest_dir: Path, now: dt.datetime | None = None) -> int:
    """Thin out automatic backups: keep everything for 2 days, then one per day for 35 days,
    then one per month for 24 months. Manual / pre-restore copies are kept (newest 80)."""
    now = now or dt.datetime.now()
    items = list_backups(dest_dir)
    removed = 0
    keep = set()
    autos = [i for i in items if i["reason"] == "auto"]
    others = [i for i in items if i["reason"] != "auto"]
    seen_day, seen_month = set(), set()
    for i in autos:  # newest first
        w = dt.datetime.fromisoformat(i["when"])
        age = (now - w).days
        if age < 2:
            keep.add(i["name"])
        elif age <= 35:
            d = w.date()
            if d not in seen_day:
                seen_day.add(d)
                keep.add(i["name"])
        elif age <= 730:
            ym = (w.year, w.month)
            if ym not in seen_month:
                seen_month.add(ym)
                keep.add(i["name"])
    for i in others[:80]:
        keep.add(i["name"])
    for i in items:
        if i["name"] not in keep:
            try:
                (dest_dir / i["name"]).unlink()
                removed += 1
            except OSError:
                pass
    return removed


def copy_to(src_file: Path, folder: str) -> None:
    """Second copy (e.g. a pen drive). Raises on failure so the caller can warn the person."""
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_file, target / src_file.name)
    # keep that folder tidy too: newest 60 copies
    files = sorted(target.glob("homeledger-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[60:]:
        try:
            old.unlink()
        except OSError:
            pass


def validate_backup(path: Path) -> None:
    if not path.exists():
        raise UserError("That backup file was not found.")
    problems = dbm.quick_check(path)
    if problems:
        raise UserError("This backup file is damaged and cannot be used: " + "; ".join(problems))
    c = sqlite3.connect(str(path))
    try:
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        ver = c.execute("PRAGMA user_version").fetchone()[0]
    finally:
        c.close()
    if not {"company", "ledgers", "vouchers", "entries"} <= names:
        raise UserError("This file is not a HomeLedger backup.")
    if ver > dbm.SCHEMA_VERSION:
        raise UserError("This backup was made by a newer version of HomeLedger.")


def restore_into(live_db: Path, backup_file: Path) -> None:
    """Replace the live database contents with the backup (page-level copy, safe with WAL)."""
    validate_backup(backup_file)
    src = sqlite3.connect(str(backup_file))
    try:
        dst = sqlite3.connect(str(live_db), timeout=30)
        try:
            src.backup(dst)
            dst.execute("PRAGMA journal_mode = WAL")
        finally:
            dst.close()
    finally:
        src.close()


# ---------------------------------------------------------------------------
# password-protected copies (for a cloud-synced folder such as Google Drive)
# ---------------------------------------------------------------------------
# File layout: b"HLBK1" | salt(16) | nonce(16) | ciphertext | MAC(32)
# Key from the password with PBKDF2-SHA256; stream cipher = HMAC-SHA256 in counter mode; encrypt-then-MAC.
# (Built only from Python's standard library so no extra software is needed.)
import hashlib
import hmac
import os

_MAGIC = b"HLBK1"
_KDF_ITERS = 200_000
ENC_SUFFIX = ".hlbk"
ENC_RE = re.compile(r"^homeledger-(\d{8})-(\d{6})-([a-z\-]+)\.db\.hlbk$")


def _keys(password: str, salt: bytes):
    k = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _KDF_ITERS, dklen=64)
    return k[:32], k[32:]


def _xor_stream(data: bytes, enc_key: bytes, nonce: bytes, start_block: int) -> bytes:
    out = bytearray()
    block = start_block
    for i in range(0, len(data), 32):
        ks = hmac.new(enc_key, nonce + block.to_bytes(8, "big"), hashlib.sha256).digest()
        chunk = data[i:i + 32]
        out += (int.from_bytes(chunk, "big") ^ int.from_bytes(ks[:len(chunk)], "big")).to_bytes(len(chunk), "big")
        block += 1
    return bytes(out)


def encrypt_file(src: Path, dst: Path, password: str) -> None:
    if not password:
        raise UserError("A password is needed to protect the copy.")
    salt, nonce = os.urandom(16), os.urandom(16)
    ek, mk = _keys(password, salt)
    mac = hmac.new(mk, _MAGIC + salt + nonce, hashlib.sha256)
    tmp = dst.with_name(dst.name + ".tmp")
    with open(src, "rb") as f, open(tmp, "wb") as o:
        o.write(_MAGIC + salt + nonce)
        block = 0
        while True:
            data = f.read(32 * 32768)             # 1 MB at a time
            if not data:
                break
            ct = _xor_stream(data, ek, nonce, block)
            block += len(data) // 32 + (1 if len(data) % 32 else 0)
            mac.update(ct)
            o.write(ct)
        o.write(mac.digest())
        o.flush()
        os.fsync(o.fileno())
    tmp.replace(dst)


def decrypt_file(src: Path, dst: Path, password: str) -> None:
    size = src.stat().st_size
    if size < len(_MAGIC) + 32 + 32:
        raise UserError("That file is not a protected HomeLedger copy.")
    with open(src, "rb") as f:
        head = f.read(len(_MAGIC) + 32)
        if head[:len(_MAGIC)] != _MAGIC:
            raise UserError("That file is not a protected HomeLedger copy.")
        salt, nonce = head[len(_MAGIC):len(_MAGIC) + 16], head[len(_MAGIC) + 16:]
        ek, mk = _keys(password or "", salt)
        mac = hmac.new(mk, head, hashlib.sha256)
        remaining = size - len(head) - 32
        pos = len(head)
        while remaining > 0:                      # first pass: check the whole file before decrypting anything
            chunk = f.read(min(1 << 20, remaining))
            mac.update(chunk)
            remaining -= len(chunk)
        tag = f.read(32)
        if not hmac.compare_digest(mac.digest(), tag):
            raise UserError("The password is not correct, or the file is damaged.")
        f.seek(pos)
        remaining = size - len(head) - 32
        block = 0
        tmp = dst.with_name(dst.name + ".tmp")
        with open(tmp, "wb") as o:
            while remaining > 0:
                chunk = f.read(min(32 * 32768, remaining))
                o.write(_xor_stream(chunk, ek, nonce, block))
                block += len(chunk) // 32 + (1 if len(chunk) % 32 else 0)
                remaining -= len(chunk)
        tmp.replace(dst)


def copy_protected(src_file: Path, folder: str, password: str) -> None:
    """Second copy, password-protected, then proven readable by opening it again before it is trusted."""
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)
    dst = target / (src_file.name + ENC_SUFFIX)
    encrypt_file(src_file, dst, password)
    check = target / ".homeledger-verify.tmp"
    try:
        decrypt_file(dst, check, password)
        if hashlib.sha256(check.read_bytes()).digest() != hashlib.sha256(src_file.read_bytes()).digest():
            raise UserError("The protected copy could not be verified.")
    except Exception:
        dst.unlink(missing_ok=True)
        raise
    finally:
        check.unlink(missing_ok=True)
    files = sorted(target.glob("homeledger-*.db.hlbk"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[60:]:
        try:
            old.unlink()
        except OSError:
            pass
