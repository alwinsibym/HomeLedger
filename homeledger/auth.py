"""Optional sign-in: usernames and passwords (or a short PIN), owner / view-only roles, auto-lock, lock-out after
repeated wrong tries, and a recovery key for a forgotten password. Everything stays on this computer."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time

from . import db as dbm
from .errors import UserError

ITERS = 240_000
MIN_LEN = 4
IDLE_CHOICES = (5, 10, 15, 30, 60, 0)      # minutes; 0 = never lock automatically
ROLES = ("owner", "viewer")


def _hash(password: str, salt: bytes, iters: int = ITERS) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)


def enabled(conn) -> bool:
    return dbm.get_setting(conn, "auth_enabled", "0") == "1"


def idle_minutes(conn) -> int:
    try:
        v = int(dbm.get_setting(conn, "idle_minutes", "15"))
    except ValueError:
        v = 15
    return v if v in IDLE_CHOICES else 15


def _check_new(username: str, password: str):
    username = (username or "").strip()
    if not (2 <= len(username) <= 30) or not all(ch.isalnum() or ch in "._- " for ch in username):
        raise UserError("Choose a user name of 2 to 30 letters or numbers.")
    if len(password or "") < MIN_LEN:
        raise UserError(f"The password (or PIN) needs at least {MIN_LEN} characters.")
    return username


def _add_user(conn, username, password, role):
    salt = os.urandom(16)
    try:
        conn.execute("INSERT INTO users(username, role, salt, hash, iters, created) VALUES (?,?,?,?,?,?)",
                     (username, role, salt, _hash(password, salt), ITERS, dbm.now_iso()))
    except Exception as e:
        if "UNIQUE" in str(e):
            raise UserError("That user name is already in use.")
        raise


def new_recovery_key() -> str:
    raw = secrets.token_hex(10).upper()          # 20 characters
    return "-".join(raw[i:i + 5] for i in range(0, 20, 5))


def _set_recovery(conn, key: str):
    salt = os.urandom(16)
    dbm.set_setting(conn, "recovery_salt", salt.hex())
    dbm.set_setting(conn, "recovery_hash", _hash(key.replace("-", "").upper(), salt).hex())


def enable(conn, username, password) -> str:
    """Turn sign-in on, create the first (owner) user. Returns the recovery key, shown once."""
    if enabled(conn):
        raise UserError("Sign-in is already turned on.")
    username = _check_new(username, password)
    with dbm.write_tx(conn):
        conn.execute("DELETE FROM users")
        _add_user(conn, username, password, "owner")
        key = new_recovery_key()
        _set_recovery(conn, key)
        dbm.set_setting(conn, "auth_enabled", "1")
        dbm.audit(conn, "security", "sign-in", None, "sign-in turned on")
    return key


def disable(conn):
    with dbm.write_tx(conn):
        dbm.set_setting(conn, "auth_enabled", "0")
        dbm.audit(conn, "security", "sign-in", None, "sign-in turned off")


def users(conn) -> list:
    return [dict(r) for r in conn.execute("SELECT id, username, role, created FROM users ORDER BY id")]


def add_user(conn, username, password, role):
    if role not in ROLES:
        raise UserError("Unknown role.")
    username = _check_new(username, password)
    with dbm.write_tx(conn):
        _add_user(conn, username, password, role)
        dbm.audit(conn, "security", "user", None, f"user {username} added as {role}")


def remove_user(conn, user_id: int):
    r = conn.execute("SELECT username, role FROM users WHERE id=?", (user_id,)).fetchone()
    if not r:
        raise UserError("That user no longer exists.")
    owners = conn.execute("SELECT COUNT(*) FROM users WHERE role='owner'").fetchone()[0]
    if r["role"] == "owner" and owners <= 1:
        raise UserError("The last owner cannot be removed.")
    with dbm.write_tx(conn):
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        dbm.audit(conn, "security", "user", user_id, f"user {r['username']} removed")


def verify(conn, username, password) -> dict:
    """Check a password. Raises UserError with a friendly message; wrong tries slow down and then lock briefly."""
    row = conn.execute("SELECT * FROM users WHERE username=?", ((username or "").strip(),)).fetchone()
    now = time.time()
    if row and row["locked_until"] > now:
        wait = int(row["locked_until"] - now) + 1
        raise UserError(f"Too many wrong tries. Please wait {wait} seconds and try again.")
    ok = False
    if row:
        ok = hmac.compare_digest(_hash(password or "", bytes(row["salt"]), row["iters"]), bytes(row["hash"]))
    else:
        _hash(password or "", b"\0" * 16)            # same time taken whether or not the user exists
    if not ok:
        if row:
            failed = row["failed"] + 1
            lock = 0 if failed < 5 else min(900, 30 * 2 ** (failed - 5))
            with dbm.write_tx(conn):
                conn.execute("UPDATE users SET failed=?, locked_until=? WHERE id=?", (failed, now + lock if lock else 0, row["id"]))
        raise UserError("The user name or password is not correct.")
    with dbm.write_tx(conn):
        conn.execute("UPDATE users SET failed=0, locked_until=0 WHERE id=?", (row["id"],))
    return {"id": row["id"], "username": row["username"], "role": row["role"]}


def change_password(conn, user_id, old, new):
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row or not hmac.compare_digest(_hash(old or "", bytes(row["salt"]), row["iters"]), bytes(row["hash"])):
        raise UserError("The current password is not correct.")
    _check_new(row["username"], new)
    salt = os.urandom(16)
    with dbm.write_tx(conn):
        conn.execute("UPDATE users SET salt=?, hash=?, iters=? WHERE id=?", (salt, _hash(new, salt), ITERS, user_id))
        dbm.audit(conn, "security", "user", user_id, "password changed")


def reset_with_recovery_key(conn, key, new_password) -> str:
    """Forgot the password: the printed recovery key sets a new password for the first owner. Returns a NEW key."""
    salt_hex, want = dbm.get_setting(conn, "recovery_salt", ""), dbm.get_setting(conn, "recovery_hash", "")
    if not (salt_hex and want):
        raise UserError("No recovery key was set up.")
    got = _hash((key or "").replace("-", "").replace(" ", "").upper(), bytes.fromhex(salt_hex)).hex()
    if not hmac.compare_digest(got, want):
        raise UserError("That recovery key is not correct.")
    owner = conn.execute("SELECT * FROM users WHERE role='owner' ORDER BY id LIMIT 1").fetchone()
    if not owner:
        raise UserError("No owner user exists.")
    _check_new(owner["username"], new_password)
    salt = os.urandom(16)
    newkey = new_recovery_key()
    with dbm.write_tx(conn):
        conn.execute("UPDATE users SET salt=?, hash=?, iters=?, failed=0, locked_until=0 WHERE id=?",
                     (salt, _hash(new_password, salt), ITERS, owner["id"]))
        _set_recovery(conn, newkey)
        dbm.audit(conn, "security", "user", owner["id"], "password reset with recovery key")
    return newkey


class Sessions:
    """Who is signed in right now (kept in memory only: closing the program signs everyone out)."""

    def __init__(self):
        self._s = {}
        self._lock = threading.Lock()

    def start(self, user: dict) -> str:
        tok = secrets.token_urlsafe(32)
        with self._lock:
            self._s[tok] = {**user, "last": time.time()}
        return tok

    def get(self, tok, idle_min: int, touch: bool):
        with self._lock:
            s = self._s.get(tok or "")
            if not s:
                return None
            if idle_min and time.time() - s["last"] > idle_min * 60:
                del self._s[tok]
                return "expired"
            if touch:
                s["last"] = time.time()
            return dict(s)

    def end(self, tok):
        with self._lock:
            self._s.pop(tok or "", None)

    def clear(self):
        with self._lock:
            self._s.clear()
