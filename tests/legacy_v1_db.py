# Frozen copy of the version 1.0 database module, used only to test upgrades from an old data file.
"""SQLite schema, starter chart of accounts, connections and start-up checks."""
from __future__ import annotations

import contextlib
import datetime as dt
import shutil
import sqlite3
from pathlib import Path

from homeledger.errors import CorruptDatabase, UserError

SCHEMA_VERSION = 1

SCHEMA_V1 = """
CREATE TABLE company (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL,
    books_begin TEXT NOT NULL,
    fy_start_month INTEGER NOT NULL DEFAULT 4 CHECK (fy_start_month BETWEEN 1 AND 12),
    currency TEXT NOT NULL DEFAULT 'INR',
    created_at TEXT NOT NULL
);

CREATE TABLE acct_groups (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    parent_id INTEGER REFERENCES acct_groups(id),
    nature TEXT NOT NULL CHECK (nature IN ('asset','liability','income','expense')),
    is_system INTEGER NOT NULL DEFAULT 0,
    sort INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE cost_centres (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    parent_id INTEGER REFERENCES cost_centres(id),
    kind TEXT NOT NULL CHECK (kind IN ('household','farm','other')),
    is_active INTEGER NOT NULL DEFAULT 1,
    sort INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE ledgers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    group_id INTEGER NOT NULL REFERENCES acct_groups(id),
    nature TEXT NOT NULL CHECK (nature IN ('asset','liability','income','expense')),
    cb_kind TEXT CHECK (cb_kind IN ('cash','bank')),
    opening_paise INTEGER NOT NULL DEFAULT 0 CHECK (opening_paise >= 0),
    opening_type TEXT NOT NULL DEFAULT 'Dr' CHECK (opening_type IN ('Dr','Cr')),
    default_cc_id INTEGER REFERENCES cost_centres(id),
    is_active INTEGER NOT NULL DEFAULT 1,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE vouchers (
    id INTEGER PRIMARY KEY,
    vtype TEXT NOT NULL CHECK (vtype IN ('Payment','Receipt','Contra','Journal','Sales','Purchase')),
    fy TEXT NOT NULL,
    number INTEGER NOT NULL,
    vdate TEXT NOT NULL,
    narration TEXT NOT NULL DEFAULT '',
    ref TEXT NOT NULL DEFAULT '',
    date_approx INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'posted' CHECK (status IN ('posted','cancelled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (vtype, fy, number)
);

CREATE TABLE entries (
    id INTEGER PRIMARY KEY,
    voucher_id INTEGER NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE,
    line_no INTEGER NOT NULL,
    ledger_id INTEGER NOT NULL REFERENCES ledgers(id),
    debit_paise INTEGER NOT NULL DEFAULT 0 CHECK (debit_paise >= 0),
    credit_paise INTEGER NOT NULL DEFAULT 0 CHECK (credit_paise >= 0),
    cc_id INTEGER REFERENCES cost_centres(id),
    item TEXT,
    qty_milli INTEGER CHECK (qty_milli IS NULL OR qty_milli > 0),
    unit TEXT,
    CHECK ((debit_paise > 0 AND credit_paise = 0) OR (credit_paise > 0 AND debit_paise = 0))
);

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id INTEGER,
    detail TEXT NOT NULL DEFAULT ''
);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX idx_entries_voucher ON entries(voucher_id);
CREATE INDEX idx_entries_ledger ON entries(ledger_id);
CREATE INDEX idx_entries_cc ON entries(cc_id);
CREATE INDEX idx_entries_item ON entries(item COLLATE NOCASE);
CREATE INDEX idx_vouchers_date ON vouchers(vdate);
CREATE INDEX idx_vouchers_status_date ON vouchers(status, vdate);
CREATE INDEX idx_ledgers_group ON ledgers(group_id);
CREATE INDEX idx_audit_entity ON audit_log(entity, entity_id);
"""

# ---- starter chart of accounts ------------------------------------------------
# (code, name, parent_code, nature)
GROUPS = [
    ("CURRENT_ASSETS", "Current Assets", None, "asset"),
    ("CASH", "Cash-in-Hand", "CURRENT_ASSETS", "asset"),
    ("BANK", "Bank Accounts", "CURRENT_ASSETS", "asset"),
    ("DEBTORS", "Sundry Debtors", "CURRENT_ASSETS", "asset"),
    ("LOANS_ADV", "Loans & Advances (Asset)", "CURRENT_ASSETS", "asset"),
    ("DEPOSITS", "Deposits (Asset)", "CURRENT_ASSETS", "asset"),
    ("INVEST", "Investments", None, "asset"),
    ("FIXED", "Fixed Assets", None, "asset"),
    ("LIVESTOCK", "Livestock", "FIXED", "asset"),
    ("CAPITAL", "Capital Account", None, "liability"),
    ("LOANS_LIAB", "Loans (Liability)", None, "liability"),
    ("CURRENT_LIAB", "Current Liabilities", None, "liability"),
    ("CREDITORS", "Sundry Creditors", "CURRENT_LIAB", "liability"),
    ("SALES", "Sales Accounts", None, "income"),
    ("DIRECT_INC", "Direct Incomes", None, "income"),
    ("INDIRECT_INC", "Indirect Incomes", None, "income"),
    ("PURCHASE", "Purchase Accounts", None, "expense"),
    ("DIRECT_EXP", "Direct Expenses", None, "expense"),
    ("FARM_EXP", "Farm Expenses", "DIRECT_EXP", "expense"),
    ("INDIRECT_EXP", "Indirect Expenses", None, "expense"),
    ("HOUSE_EXP", "Household Expenses", "INDIRECT_EXP", "expense"),
]

# Activities (cost centres): (name, parent, kind)
COST_CENTRES = [
    ("Household", None, "household"),
    ("Dog", "Household", "household"),
    ("Farm", None, "farm"),
    ("Rubber", "Farm", "farm"),
    ("Cattle", "Farm", "farm"),
    ("Goats", "Farm", "farm"),
    ("Coffee", "Farm", "farm"),
    ("Cocoa", "Farm", "farm"),
    ("Black Pepper", "Farm", "farm"),
    ("Nutmeg", "Farm", "farm"),
    ("Banana", "Farm", "farm"),
    ("Mango", "Farm", "farm"),
    ("Jackfruit", "Farm", "farm"),
    ("Guava", "Farm", "farm"),
    ("Rambutan", "Farm", "farm"),
    ("Other Fruits", "Farm", "farm"),
    ("Timber Trees", "Farm", "farm"),
]

# Ledgers: (name, group_code, default activity)
LEDGERS = [
    ("Cash", "CASH", None),
    ("Bank Account", "BANK", None),
    # household expenses
    ("Groceries & Provisions", "HOUSE_EXP", "Household"),
    ("Vegetables & Fruits", "HOUSE_EXP", "Household"),
    ("Milk & Dairy", "HOUSE_EXP", "Household"),
    ("Meat & Fish", "HOUSE_EXP", "Household"),
    ("Electricity Bill (House)", "HOUSE_EXP", "Household"),
    ("Water Bill", "HOUSE_EXP", "Household"),
    ("Gas Cylinder (LPG)", "HOUSE_EXP", "Household"),
    ("Phone & Internet", "HOUSE_EXP", "Household"),
    ("Vehicle Fuel (Household)", "HOUSE_EXP", "Household"),
    ("Vehicle Repairs & Service", "HOUSE_EXP", "Household"),
    ("Medical & Medicines", "HOUSE_EXP", "Household"),
    ("Education & Fees", "HOUSE_EXP", "Household"),
    ("Clothing & Footwear", "HOUSE_EXP", "Household"),
    ("House Repairs & Maintenance", "HOUSE_EXP", "Household"),
    ("Festivals & Functions", "HOUSE_EXP", "Household"),
    ("Travel", "HOUSE_EXP", "Household"),
    ("Gifts & Donations", "HOUSE_EXP", "Household"),
    ("Insurance Premiums", "HOUSE_EXP", "Household"),
    ("Entertainment", "HOUSE_EXP", "Household"),
    ("Domestic Help", "HOUSE_EXP", "Household"),
    ("Taxes & Government Fees", "HOUSE_EXP", "Household"),
    ("Loan Interest Paid", "HOUSE_EXP", "Household"),
    ("Dog Expenses", "HOUSE_EXP", "Dog"),
    ("Household Miscellaneous", "HOUSE_EXP", "Household"),
    # farm expenses
    ("Labour Wages", "FARM_EXP", "Farm"),
    ("Fertilizer & Manure", "FARM_EXP", "Farm"),
    ("Pesticides & Crop Protection", "FARM_EXP", "Farm"),
    ("Seeds & Saplings", "FARM_EXP", "Farm"),
    ("Cattle Feed", "FARM_EXP", "Cattle"),
    ("Goat Feed", "FARM_EXP", "Goats"),
    ("Veterinary & Medicines", "FARM_EXP", "Farm"),
    ("Farm Tools (Small)", "FARM_EXP", "Farm"),
    ("Farm Fuel", "FARM_EXP", "Farm"),
    ("Farm Electricity", "FARM_EXP", "Farm"),
    ("Irrigation & Pump Repairs", "FARM_EXP", "Farm"),
    ("Farm Repairs & Maintenance", "FARM_EXP", "Farm"),
    ("Fencing", "FARM_EXP", "Farm"),
    ("Transport & Freight", "FARM_EXP", "Farm"),
    ("Rubber Tapping & Processing", "FARM_EXP", "Rubber"),
    ("Farm Miscellaneous", "FARM_EXP", "Farm"),
    # farm sales / income
    ("Rubber Sales", "SALES", "Rubber"),
    ("Coffee Sales", "SALES", "Coffee"),
    ("Cocoa Sales", "SALES", "Cocoa"),
    ("Pepper Sales", "SALES", "Black Pepper"),
    ("Nutmeg Sales", "SALES", "Nutmeg"),
    ("Fruit Sales", "SALES", "Other Fruits"),
    ("Milk Sales", "SALES", "Cattle"),
    ("Cattle Sales", "SALES", "Cattle"),
    ("Goat Sales", "SALES", "Goats"),
    ("Timber Sales", "SALES", "Timber Trees"),
    ("Other Farm Sales", "SALES", "Farm"),
    # household income
    ("Salary / Pension", "INDIRECT_INC", "Household"),
    ("Interest Received", "INDIRECT_INC", "Household"),
    ("Rent Received", "INDIRECT_INC", "Household"),
    ("Gifts Received", "INDIRECT_INC", "Household"),
    ("Other Income", "INDIRECT_INC", "Household"),
    # assets
    ("House & Property", "FIXED", None),
    ("Farm Land", "FIXED", "Farm"),
    ("Vehicles", "FIXED", None),
    ("Farm Equipment & Machinery", "FIXED", "Farm"),
    ("Cattle Stock", "LIVESTOCK", "Cattle"),
    ("Goat Stock", "LIVESTOCK", "Goats"),
    ("Fixed Deposits", "INVEST", None),
    ("Chit Funds & Savings Schemes", "INVEST", None),
    ("Gold & Jewellery", "INVEST", None),
    ("Advances Paid", "LOANS_ADV", None),
    ("Deposits (Electricity, Gas etc.)", "DEPOSITS", None),
    # liabilities
    ("Capital Account", "CAPITAL", None),
    ("Bank Loan", "LOANS_LIAB", None),
    ("Money Borrowed", "LOANS_LIAB", None),
]


def now_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat(sep=" ")


def connect(path) -> sqlite3.Connection:
    """A short-lived connection. Manual transaction control (we issue BEGIN/COMMIT ourselves)."""
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA synchronous = FULL")  # safe against sudden power cuts
    return conn


@contextlib.contextmanager
def write_tx(conn: sqlite3.Connection):
    """All-or-nothing write block."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def audit(conn, action: str, entity: str, entity_id, detail: str = "") -> None:
    conn.execute(
        "INSERT INTO audit_log(ts, action, entity, entity_id, detail) VALUES (?,?,?,?,?)",
        (now_iso(), action, entity, entity_id, detail[:20000]),
    )


def quick_check(path) -> list:
    """Returns [] when healthy, else a list of problems."""
    try:
        c = sqlite3.connect(str(path), timeout=30)
        try:
            rows = [r[0] for r in c.execute("PRAGMA quick_check").fetchall()]
        finally:
            c.close()
    except sqlite3.DatabaseError as e:
        return [str(e)]
    return [] if rows == ["ok"] else rows[:5]


def _seed(conn: sqlite3.Connection, today: dt.date) -> None:
    ts = now_iso()
    fy_start_year = today.year if today.month >= 4 else today.year - 1
    books_begin = dt.date(fy_start_year - 1, 4, 1).isoformat()
    conn.execute(
        "INSERT INTO company(id, name, books_begin, fy_start_month, currency, created_at) VALUES (1,?,?,?,?,?)",
        ("My Household & Farm", books_begin, 4, "INR", ts),
    )
    ids = {}
    for i, (code, name, parent, nature) in enumerate(GROUPS):
        cur = conn.execute(
            "INSERT INTO acct_groups(code, name, parent_id, nature, is_system, sort) VALUES (?,?,?,?,1,?)",
            (code, name, ids.get(parent), nature, i),
        )
        ids[code] = cur.lastrowid
    cc = {}
    for i, (name, parent, kind) in enumerate(COST_CENTRES):
        cur = conn.execute(
            "INSERT INTO cost_centres(name, parent_id, kind, sort) VALUES (?,?,?,?)",
            (name, cc.get(parent), kind, i),
        )
        cc[name] = cur.lastrowid
    # which groups are under Cash / Bank
    cb_of = {"CASH": "cash", "BANK": "bank"}
    nature_of = {code: nature for code, _n, _p, nature in GROUPS}
    for name, gcode, cc_name in LEDGERS:
        conn.execute(
            "INSERT INTO ledgers(name, group_id, nature, cb_kind, opening_type, default_cc_id, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (name, ids[gcode], nature_of[gcode], cb_of.get(gcode),
             "Cr" if nature_of[gcode] == "liability" else "Dr", cc.get(cc_name), ts),
        )
    audit(conn, "setup", "company", 1, "Starter chart of accounts created")


def _create_fresh(path, today=None) -> None:
    conn = connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        with write_tx(conn):
            for stmt in SCHEMA_V1.split(";"):
                if stmt.strip():
                    conn.execute(stmt)
            _seed(conn, today or dt.date.today())
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    finally:
        conn.close()


def _has_tables(path) -> bool:
    c = sqlite3.connect(str(path))
    try:
        return c.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0] > 0
    finally:
        c.close()


def init_database(path, log=None) -> None:
    """Create the database on first run, verify it on later runs, and upgrade it when needed."""
    path = Path(path)
    if path.exists() and path.stat().st_size > 0:
        try:
            has = _has_tables(path)
        except sqlite3.DatabaseError as e:      # not a database at all (damaged header, wrong file...)
            raise CorruptDatabase(str(e))
    else:
        has = False
    if not has:
        if path.exists():
            path.unlink()
        _create_fresh(path)
        return
    problems = quick_check(path)
    if problems:
        raise CorruptDatabase("; ".join(problems))
    conn = connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        ver = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()
    if ver > SCHEMA_VERSION:
        raise UserError(
            "This data file was made by a newer version of HomeLedger. "
            "Please install the newer version, or restore an older backup."
        )
    if ver < SCHEMA_VERSION:
        # Safety copy before any upgrade
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, path.with_name(f"homeledger-before-upgrade-{stamp}.db"))
        # (future migrations go here: if ver < 2: ...)


def get_company(conn) -> dict:
    r = conn.execute("SELECT * FROM company WHERE id=1").fetchone()
    return dict(r)


def get_setting(conn, key: str, default=None):
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r[0] if r else default


def set_setting(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
