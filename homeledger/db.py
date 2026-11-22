"""SQLite schema, starter chart of accounts, connections and start-up checks."""
from __future__ import annotations

import contextlib
import datetime as dt
import shutil
import sqlite3
from pathlib import Path

from .errors import CorruptDatabase, UserError

SCHEMA_VERSION = 13

SCHEMA_V4 = """
CREATE TABLE IF NOT EXISTS bank_clearing (
    voucher_id INTEGER NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE,
    ledger_id INTEGER NOT NULL REFERENCES ledgers(id),
    bank_date TEXT NOT NULL,
    PRIMARY KEY (voucher_id, ledger_id)
)"""

SCHEMA_V5 = """
CREATE TABLE IF NOT EXISTS stock_items (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    unit TEXT NOT NULL DEFAULT '',
    opening_qty_milli INTEGER NOT NULL DEFAULT 0 CHECK (opening_qty_milli >= 0),
    opening_value_paise INTEGER NOT NULL DEFAULT 0 CHECK (opening_value_paise >= 0),
    created_at TEXT
)"""

SCHEMA_V6 = (
    """CREATE TABLE IF NOT EXISTS voucher_meta (
        voucher_id INTEGER PRIMARY KEY REFERENCES vouchers(id) ON DELETE CASCADE,
        post_dated INTEGER NOT NULL DEFAULT 0,
        inst_no TEXT NOT NULL DEFAULT '',
        inst_date TEXT,
        bank_name TEXT NOT NULL DEFAULT '',
        class_name TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS voucher_classes (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        vtype TEXT NOT NULL,
        lines_json TEXT NOT NULL DEFAULT '[]'
    )""",
)


SCHEMA_V7 = (
    """CREATE TABLE IF NOT EXISTS bill_refs (
        id INTEGER PRIMARY KEY,
        voucher_id INTEGER NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE,
        ledger_id INTEGER NOT NULL REFERENCES ledgers(id),
        side TEXT NOT NULL CHECK (side IN ('Dr','Cr')),
        ref_name TEXT NOT NULL,
        kind TEXT NOT NULL CHECK (kind IN ('new','against','advance')),
        amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
        due_date TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS ix_bill_ledger ON bill_refs(ledger_id, ref_name)",
)


SCHEMA_V8 = (
    """CREATE TABLE IF NOT EXISTS budgets (
        id INTEGER PRIMARY KEY,
        kind TEXT NOT NULL CHECK (kind IN ('ledger','group')),
        target_id INTEGER NOT NULL,
        fy TEXT NOT NULL,
        amount_paise INTEGER NOT NULL CHECK (amount_paise >= 0),
        UNIQUE (kind, target_id, fy)
    )""",
)


SCHEMA_V9 = (
    """CREATE TABLE IF NOT EXISTS stock_groups (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, parent_id INTEGER REFERENCES stock_groups(id))""",
    """CREATE TABLE IF NOT EXISTS stock_categories (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, parent_id INTEGER REFERENCES stock_categories(id))""",
    """CREATE TABLE IF NOT EXISTS godowns (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, parent_id INTEGER REFERENCES godowns(id))""",
    "INSERT OR IGNORE INTO godowns(id, name) VALUES (1, 'Main Location')",
    "ALTER TABLE stock_items ADD COLUMN group_id INTEGER REFERENCES stock_groups(id)",
    "ALTER TABLE stock_items ADD COLUMN category_id INTEGER REFERENCES stock_categories(id)",
    "ALTER TABLE stock_items ADD COLUMN valuation TEXT NOT NULL DEFAULT 'avg' CHECK (valuation IN ('avg','fifo','lifo','last','std'))",
    "ALTER TABLE stock_items ADD COLUMN std_rate_paise INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE stock_items ADD COLUMN track_batches INTEGER NOT NULL DEFAULT 0",
    """CREATE TABLE IF NOT EXISTS voucher_items (
        id INTEGER PRIMARY KEY,
        voucher_id INTEGER NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE,
        line_no INTEGER NOT NULL,
        item_id INTEGER NOT NULL REFERENCES stock_items(id),
        godown_id INTEGER NOT NULL DEFAULT 1 REFERENCES godowns(id),
        dir TEXT NOT NULL CHECK (dir IN ('in','out')),
        kind TEXT NOT NULL DEFAULT 'normal' CHECK (kind IN ('normal','transfer','consume','produce','order')),
        batch TEXT NOT NULL DEFAULT '',
        expiry TEXT,
        qty_milli INTEGER NOT NULL CHECK (qty_milli > 0),
        rate_paise INTEGER NOT NULL DEFAULT 0,
        amount_paise INTEGER NOT NULL DEFAULT 0,
        order_ref TEXT NOT NULL DEFAULT ''
    )""",
    "CREATE INDEX IF NOT EXISTS ix_vitems_item ON voucher_items(item_id)",
    "CREATE INDEX IF NOT EXISTS ix_vitems_voucher ON voucher_items(voucher_id)",
    """CREATE TABLE IF NOT EXISTS price_lists (
        id INTEGER PRIMARY KEY,
        level TEXT NOT NULL,
        item_id INTEGER NOT NULL REFERENCES stock_items(id) ON DELETE CASCADE,
        from_date TEXT NOT NULL,
        rate_paise INTEGER NOT NULL CHECK (rate_paise >= 0),
        UNIQUE (level, item_id, from_date)
    )""",
    """CREATE TABLE IF NOT EXISTS boms (
        id INTEGER PRIMARY KEY,
        product_id INTEGER NOT NULL REFERENCES stock_items(id) ON DELETE CASCADE,
        name TEXT NOT NULL DEFAULT 'Standard',
        out_qty_milli INTEGER NOT NULL DEFAULT 1000 CHECK (out_qty_milli > 0),
        UNIQUE (product_id, name)
    )""",
    """CREATE TABLE IF NOT EXISTS bom_lines (
        id INTEGER PRIMARY KEY,
        bom_id INTEGER NOT NULL REFERENCES boms(id) ON DELETE CASCADE,
        item_id INTEGER NOT NULL REFERENCES stock_items(id),
        qty_milli INTEGER NOT NULL CHECK (qty_milli > 0)
    )""",
)


SCHEMA_V11 = (
    """CREATE TABLE IF NOT EXISTS gst_party (
        ledger_id INTEGER PRIMARY KEY REFERENCES ledgers(id) ON DELETE CASCADE,
        gstin TEXT NOT NULL DEFAULT '',
        state_code TEXT NOT NULL DEFAULT '',
        reg_type TEXT NOT NULL DEFAULT 'regular'
    )""",
    """CREATE TABLE IF NOT EXISTS gst_item (
        item_id INTEGER PRIMARY KEY REFERENCES stock_items(id) ON DELETE CASCADE,
        hsn TEXT NOT NULL DEFAULT '',
        rate_bp INTEGER NOT NULL DEFAULT 0 CHECK (rate_bp >= 0 AND rate_bp <= 10000)
    )""",
    """CREATE TABLE IF NOT EXISTS gst_taxledger (
        ledger_id INTEGER PRIMARY KEY REFERENCES ledgers(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK (kind IN ('cgst','sgst','igst','cess'))
    )""",
    """CREATE TABLE IF NOT EXISTS gst_lines (
        id INTEGER PRIMARY KEY,
        voucher_id INTEGER NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE,
        party_ledger_id INTEGER REFERENCES ledgers(id),
        hsn TEXT NOT NULL DEFAULT '',
        rate_bp INTEGER NOT NULL DEFAULT 0,
        taxable_paise INTEGER NOT NULL DEFAULT 0,
        cgst_paise INTEGER NOT NULL DEFAULT 0,
        sgst_paise INTEGER NOT NULL DEFAULT 0,
        igst_paise INTEGER NOT NULL DEFAULT 0,
        pos_state TEXT NOT NULL DEFAULT ''
    )""",
    "CREATE INDEX IF NOT EXISTS ix_gst_lines_voucher ON gst_lines(voucher_id)",
)


SCHEMA_V12 = (
    """CREATE TABLE IF NOT EXISTS tds_nature (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        section TEXT NOT NULL DEFAULT '',
        code TEXT NOT NULL DEFAULT '',
        rate_bp INTEGER NOT NULL CHECK (rate_bp >= 0 AND rate_bp <= 10000),
        single_paise INTEGER NOT NULL DEFAULT 0,
        annual_paise INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS tds_party (
        ledger_id INTEGER PRIMARY KEY REFERENCES ledgers(id) ON DELETE CASCADE,
        pan TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS tds_lines (
        id INTEGER PRIMARY KEY,
        voucher_id INTEGER NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE,
        party_ledger_id INTEGER NOT NULL REFERENCES ledgers(id),
        nature_id INTEGER NOT NULL REFERENCES tds_nature(id),
        base_paise INTEGER NOT NULL,
        taxed_base_paise INTEGER NOT NULL,
        rate_bp INTEGER NOT NULL,
        tax_paise INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS ix_tds_lines_voucher ON tds_lines(voucher_id)",
    """CREATE TABLE IF NOT EXISTS tds_challans (
        id INTEGER PRIMARY KEY,
        paid_on TEXT NOT NULL,
        for_month TEXT NOT NULL,
        bsr TEXT NOT NULL DEFAULT '',
        serial TEXT NOT NULL DEFAULT '',
        amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
        interest_paise INTEGER NOT NULL DEFAULT 0,
        note TEXT NOT NULL DEFAULT ''
    )""",
)
TDS_SEED = (
    ("Contractor: individual / HUF payee", "194C", "1023", 100, 3000000, 10000000),
    ("Contractor: any other payee", "194C", "1024", 200, 3000000, 10000000),
    ("Professional fees", "194J(b)", "1027", 1000, 0, 5000000),
    ("Technical fees", "194J(a)", "1026", 200, 0, 5000000),
    ("Commission / brokerage", "194H", "1006", 200, 0, 2000000),
    ("Rent: land, building, furniture", "194I(b)", "1009", 1000, 5000000, 0),
    ("Rent: plant and machinery", "194I(a)", "1008", 200, 5000000, 0),
    ("Interest other than on securities", "194A", "1022", 1000, 0, 1000000),
)


SCHEMA_V13 = (
    """CREATE TABLE IF NOT EXISTS pay_employees (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        designation TEXT NOT NULL DEFAULT '',
        pan TEXT NOT NULL DEFAULT '',
        joined TEXT,
        left_on TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        notes TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS pay_heads (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        kind TEXT NOT NULL CHECK (kind IN ('earning','deduction')),
        is_basic INTEGER NOT NULL DEFAULT 0,
        calc TEXT NOT NULL DEFAULT 'fixed' CHECK (calc IN ('fixed','percent_basic')),
        ledger_id INTEGER REFERENCES ledgers(id),
        sort INTEGER NOT NULL DEFAULT 100,
        is_active INTEGER NOT NULL DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS pay_structure (
        employee_id INTEGER NOT NULL REFERENCES pay_employees(id) ON DELETE CASCADE,
        head_id INTEGER NOT NULL REFERENCES pay_heads(id),
        amount_paise INTEGER NOT NULL DEFAULT 0,
        rate_bp INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (employee_id, head_id)
    )""",
    """CREATE TABLE IF NOT EXISTS pay_runs (
        id INTEGER PRIMARY KEY,
        month TEXT NOT NULL UNIQUE,
        working_days INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','posted')),
        voucher_id INTEGER REFERENCES vouchers(id),
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS pay_slips (
        id INTEGER PRIMARY KEY,
        run_id INTEGER NOT NULL REFERENCES pay_runs(id) ON DELETE CASCADE,
        employee_id INTEGER NOT NULL REFERENCES pay_employees(id),
        days_present REAL NOT NULL,
        gross_paise INTEGER NOT NULL,
        deduct_paise INTEGER NOT NULL,
        net_paise INTEGER NOT NULL,
        UNIQUE (run_id, employee_id)
    )""",
    """CREATE TABLE IF NOT EXISTS pay_slip_lines (
        slip_id INTEGER NOT NULL REFERENCES pay_slips(id) ON DELETE CASCADE,
        head_id INTEGER NOT NULL REFERENCES pay_heads(id),
        kind TEXT NOT NULL,
        amount_paise INTEGER NOT NULL,
        PRIMARY KEY (slip_id, head_id)
    )""",
)


def apply_v13(conn):
    for stmt in SCHEMA_V13:
        conn.execute(stmt)
    if conn.execute("SELECT COUNT(*) FROM pay_heads").fetchone()[0] == 0:
        conn.executemany("INSERT INTO pay_heads(name, kind, is_basic, calc, sort) VALUES (?,?,?,?,?)",
                         [("Basic Salary", "earning", 1, "fixed", 10), ("Allowances", "earning", 0, "fixed", 20),
                          ("Provident Fund (employee)", "deduction", 0, "percent_basic", 110),
                          ("Advance recovery", "deduction", 0, "fixed", 120)])


def apply_v12(conn):
    for stmt in SCHEMA_V12:
        conn.execute(stmt)
    if conn.execute("SELECT COUNT(*) FROM tds_nature").fetchone()[0] == 0:
        conn.executemany("INSERT INTO tds_nature(name, section, code, rate_bp, single_paise, annual_paise) VALUES (?,?,?,?,?,?)", TDS_SEED)


def apply_v11(conn):
    for stmt in SCHEMA_V11:
        conn.execute(stmt)


def apply_v10(conn):
    """More user roles (accountant, data entry): the users table is rebuilt with a wider CHECK."""
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='users'").fetchone()
    if not sql or "accountant" in sql[0]:
        return
    conn.execute("ALTER TABLE users RENAME TO users_old")
    conn.execute(SCHEMA_V2)
    conn.execute("INSERT INTO users(id, username, role, salt, hash, iters, failed, locked_until, created) "
                 "SELECT id, username, role, salt, hash, iters, failed, locked_until, created FROM users_old")
    conn.execute("DROP TABLE users_old")


def apply_v9(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(stock_items)")}
    for stmt in SCHEMA_V9:
        if stmt.startswith("ALTER TABLE stock_items ADD COLUMN"):
            col = stmt.split("ADD COLUMN")[1].split()[0]
            if col in cols:
                continue
        conn.execute(stmt)


def apply_v8(conn):
    for stmt in SCHEMA_V8:
        conn.execute(stmt)


def apply_v7(conn):
    for stmt in SCHEMA_V7:
        conn.execute(stmt)


def apply_v6(conn):
    for stmt in SCHEMA_V6:
        conn.execute(stmt)


SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    role TEXT NOT NULL CHECK (role IN ('owner','accountant','entry','viewer')),
    salt BLOB NOT NULL,
    hash BLOB NOT NULL,
    iters INTEGER NOT NULL,
    failed INTEGER NOT NULL DEFAULT 0,
    locked_until REAL NOT NULL DEFAULT 0,
    created TEXT NOT NULL
)
"""

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
    vtype TEXT NOT NULL,
    fy TEXT NOT NULL,
    number INTEGER NOT NULL,
    vdate TEXT NOT NULL,
    narration TEXT NOT NULL DEFAULT '',
    ref TEXT NOT NULL DEFAULT '',
    date_approx INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'posted' CHECK (status IN ('posted','cancelled','memo','optional')),
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
# Tally's own starting groups (name, parent, nature). Group codes are used internally.
GROUPS = [
    ("BRANCH", "Branch / Divisions", None, "liability"),
    ("CAPITAL", "Capital Account", None, "liability"),
    ("RESERVES", "Reserves & Surplus", "CAPITAL", "liability"),
    ("CURRENT_ASSETS", "Current Assets", None, "asset"),
    ("BANK", "Bank Accounts", "CURRENT_ASSETS", "asset"),
    ("CASH", "Cash-in-Hand", "CURRENT_ASSETS", "asset"),
    ("DEPOSITS", "Deposits (Asset)", "CURRENT_ASSETS", "asset"),
    ("LOANS_ADV", "Loans & Advances (Asset)", "CURRENT_ASSETS", "asset"),
    ("STOCK", "Stock-in-Hand", "CURRENT_ASSETS", "asset"),
    ("DEBTORS", "Sundry Debtors", "CURRENT_ASSETS", "asset"),
    ("CURRENT_LIAB", "Current Liabilities", None, "liability"),
    ("DUTIES", "Duties & Taxes", "CURRENT_LIAB", "liability"),
    ("PROVISIONS", "Provisions", "CURRENT_LIAB", "liability"),
    ("CREDITORS", "Sundry Creditors", "CURRENT_LIAB", "liability"),
    ("DIRECT_EXP", "Direct Expenses", None, "expense"),
    ("DIRECT_INC", "Direct Incomes", None, "income"),
    ("FIXED", "Fixed Assets", None, "asset"),
    ("INDIRECT_EXP", "Indirect Expenses", None, "expense"),
    ("INDIRECT_INC", "Indirect Incomes", None, "income"),
    ("INVEST", "Investments", None, "asset"),
    ("LOANS_LIAB", "Loans (Liability)", None, "liability"),
    ("BANK_OD", "Bank OD A/c", "LOANS_LIAB", "liability"),
    ("SECURED", "Secured Loans", "LOANS_LIAB", "liability"),
    ("UNSECURED", "Unsecured Loans", "LOANS_LIAB", "liability"),
    ("MISC_EXP", "Misc. Expenses (ASSET)", None, "asset"),
    ("PURCHASE", "Purchase Accounts", None, "expense"),
    ("SALES", "Sales Accounts", None, "income"),
    ("SUSPENSE", "Suspense A/c", None, "liability"),
]

# Like Tally, a new book starts with just Cash and no cost centres. Everything else is created by the user.
COST_CENTRES = []
LEDGERS = [("Cash", "CASH", None)]

# What older versions created for a household + farm book (used only to tidy up unused leftovers when upgrading)
_LEGACY_LEDGERS = ['Bank Account',
 'Groceries & Provisions',
 'Vegetables & Fruits',
 'Milk & Dairy',
 'Meat & Fish',
 'Electricity Bill (House)',
 'Water Bill',
 'Gas Cylinder (LPG)',
 'Phone & Internet',
 'Vehicle Fuel (Household)',
 'Vehicle Repairs & Service',
 'Medical & Medicines',
 'Education & Fees',
 'Clothing & Footwear',
 'House Repairs & Maintenance',
 'Festivals & Functions',
 'Travel',
 'Gifts & Donations',
 'Insurance Premiums',
 'Entertainment',
 'Domestic Help',
 'Taxes & Government Fees',
 'Loan Interest Paid',
 'Dog Expenses',
 'Household Miscellaneous',
 'Labour Wages',
 'Fertilizer & Manure',
 'Pesticides & Crop Protection',
 'Seeds & Saplings',
 'Cattle Feed',
 'Goat Feed',
 'Veterinary & Medicines',
 'Farm Tools (Small)',
 'Farm Fuel',
 'Farm Electricity',
 'Irrigation & Pump Repairs',
 'Farm Repairs & Maintenance',
 'Fencing',
 'Transport & Freight',
 'Rubber Tapping & Processing',
 'Farm Miscellaneous',
 'Rubber Sales',
 'Coffee Sales',
 'Cocoa Sales',
 'Pepper Sales',
 'Nutmeg Sales',
 'Fruit Sales',
 'Milk Sales',
 'Cattle Sales',
 'Goat Sales',
 'Timber Sales',
 'Other Farm Sales',
 'Salary / Pension',
 'Interest Received',
 'Rent Received',
 'Gifts Received',
 'Other Income',
 'House & Property',
 'Farm Land',
 'Vehicles',
 'Farm Equipment & Machinery',
 'Cattle Stock',
 'Goat Stock',
 'Fixed Deposits',
 'Chit Funds & Savings Schemes',
 'Gold & Jewellery',
 'Advances Paid',
 'Deposits (Electricity, Gas etc.)',
 'Capital Account',
 'Bank Loan',
 'Money Borrowed']
_LEGACY_CCS = ['Household',
 'Dog',
 'Farm',
 'Rubber',
 'Cattle',
 'Goats',
 'Coffee',
 'Cocoa',
 'Black Pepper',
 'Nutmeg',
 'Banana',
 'Mango',
 'Jackfruit',
 'Guava',
 'Rambutan',
 'Other Fruits',
 'Timber Trees']
_LEGACY_GROUPS = ['FARM_EXP', 'HOUSE_EXP', 'LIVESTOCK']


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
        ("My Company", books_begin, 4, "INR", ts),
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
            conn.execute(SCHEMA_V2)
            conn.execute(SCHEMA_V4)
            conn.execute(SCHEMA_V5)
            apply_v6(conn)
            apply_v7(conn)
            apply_v8(conn)
            apply_v9(conn)
            apply_v10(conn)
            apply_v11(conn)
            apply_v12(conn)
            apply_v13(conn)
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


_VOUCHERS_V3 = """
CREATE TABLE vouchers_new (
    id INTEGER PRIMARY KEY,
    vtype TEXT NOT NULL,
    fy TEXT NOT NULL,
    number INTEGER NOT NULL,
    vdate TEXT NOT NULL,
    narration TEXT NOT NULL DEFAULT '',
    ref TEXT NOT NULL DEFAULT '',
    date_approx INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'posted' CHECK (status IN ('posted','cancelled','memo','optional')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (vtype, fy, number)
)
"""


def _migrate_v3(conn) -> None:
    """Version 3: any voucher type can be stored (Credit/Debit Note and more); Tally's standard groups are added;
    unused starter accounts made for the old household + farm book are tidied away. Entered data is never touched."""
    conn.execute(_VOUCHERS_V3)
    conn.execute("INSERT INTO vouchers_new SELECT id, vtype, fy, number, vdate, narration, ref, date_approx, status, "
                 "created_at, updated_at FROM vouchers")
    conn.execute("DROP TABLE vouchers")
    conn.execute("ALTER TABLE vouchers_new RENAME TO vouchers")
    conn.execute("CREATE INDEX idx_vouchers_date ON vouchers(vdate)")
    conn.execute("CREATE INDEX idx_vouchers_status_date ON vouchers(status, vdate)")
    # Tally's standard groups that are missing
    ids = {r["code"]: r["id"] for r in conn.execute("SELECT id, code FROM acct_groups WHERE code IS NOT NULL")}
    for i, (code, name, parent, nature) in enumerate(GROUPS):
        if code in ids or conn.execute("SELECT 1 FROM acct_groups WHERE name=?", (name,)).fetchone():
            continue
        cur = conn.execute("INSERT INTO acct_groups(code, name, parent_id, nature, is_system, sort) VALUES (?,?,?,?,1,?)",
                           (code, name, ids.get(parent), nature, i))
        ids[code] = cur.lastrowid
    # unused starter ledgers / cost centres / groups from the old farm-style chart
    removed = 0
    for name in _LEGACY_LEDGERS:
        r = conn.execute("SELECT id, opening_paise FROM ledgers WHERE name=?", (name,)).fetchone()
        if r and r["opening_paise"] == 0 and not conn.execute("SELECT 1 FROM entries WHERE ledger_id=?", (r["id"],)).fetchone():
            conn.execute("DELETE FROM ledgers WHERE id=?", (r["id"],))
            removed += 1
    for name in reversed(_LEGACY_CCS):                       # children before parents
        r = conn.execute("SELECT id FROM cost_centres WHERE name=?", (name,)).fetchone()
        if r and not conn.execute("SELECT 1 FROM entries WHERE cc_id=?", (r["id"],)).fetchone() \
                and not conn.execute("SELECT 1 FROM ledgers WHERE default_cc_id=?", (r["id"],)).fetchone() \
                and not conn.execute("SELECT 1 FROM cost_centres WHERE parent_id=?", (r["id"],)).fetchone():
            conn.execute("DELETE FROM cost_centres WHERE id=?", (r["id"],))
    for code in _LEGACY_GROUPS:
        r = conn.execute("SELECT id FROM acct_groups WHERE code=?", (code,)).fetchone()
        if r and not conn.execute("SELECT 1 FROM ledgers WHERE group_id=?", (r["id"],)).fetchone() \
                and not conn.execute("SELECT 1 FROM acct_groups WHERE parent_id=?", (r["id"],)).fetchone():
            conn.execute("DELETE FROM acct_groups WHERE id=?", (r["id"],))
    audit(conn, "upgrade", "company", 1, f"Tally standard groups added; {removed} unused starter accounts tidied")


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
        conn = connect(path)
        try:
            conn.execute("PRAGMA foreign_keys = OFF")        # needed while a table is rebuilt (turned back on below)
            with write_tx(conn):
                if ver < 2:
                    conn.execute(SCHEMA_V2)
                if ver < 3:
                    _migrate_v3(conn)
                if ver < 4:
                    conn.execute(SCHEMA_V4)
                if ver < 5:
                    conn.execute(SCHEMA_V5)
                if ver < 6:
                    apply_v6(conn)
                if ver < 7:
                    apply_v7(conn)
                if ver < 8:
                    apply_v8(conn)
                if ver < 9:
                    apply_v9(conn)
                if ver < 10:
                    apply_v10(conn)
                if ver < 11:
                    apply_v11(conn)
                if ver < 12:
                    apply_v12(conn)
                if ver < 13:
                    apply_v13(conn)
                bad = conn.execute("PRAGMA foreign_key_check").fetchall()
                if bad:
                    raise sqlite3.IntegrityError("upgrade check failed")
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        finally:
            conn.close()


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
