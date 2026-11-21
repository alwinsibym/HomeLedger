import datetime as dt, os, random, sqlite3, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from homeledger import db as dbm, service as sv, reports as rp, backup as bk, money
from homeledger.errors import UserError, CorruptDatabase
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.path = Path(self.tmp.name) / "t.db"
        dbm._create_fresh(self.path, dt.date(2026, 11, 19))
        self.c = dbm.connect(self.path)
        fixtures.install(self.c)
        self.L = {l["name"]: l["id"] for l in sv.list_masters(self.c, "2026-11-19")["ledgers"]}

    def tearDown(self):
        self.c.close(); self.tmp.cleanup()

    def pay(self, date, ledger, amt, acct="Cash", **kw):
        return sv.save_voucher(self.c, {"vtype": "Payment", "date": date, "lines": [
            {"ledger_id": self.L[ledger], "side": "Dr", "amount": str(amt), **kw},
            {"ledger_id": self.L[acct], "side": "Cr", "amount": str(amt)}]})

    def rec(self, date, ledger, amt, acct="Bank Account"):
        return sv.save_voucher(self.c, {"vtype": "Receipt", "date": date, "lines": [
            {"ledger_id": self.L[ledger], "side": "Cr", "amount": str(amt)},
            {"ledger_id": self.L[acct], "side": "Dr", "amount": str(amt)}]})


class TestYearEnd(Base):
    """Books run across financial years (April-March): balances and profit carry forward by themselves."""
    def test_carry_forward_across_years(self):
        self.rec("2025-06-10", "Rubber Sales", 100000, "Cash")       # FY 2025-26: earned 1,00,000
        self.pay("2025-09-01", "Groceries & Provisions", 30000)      # spent 30,000 -> profit 70,000
        self.pay("2026-05-05", "Groceries & Provisions", 10000)      # FY 2026-27: spent 10,000
        bs1 = rp.balance_sheet(self.c, "2025-04-01", "2026-03-31")
        bs2 = rp.balance_sheet(self.c, "2026-04-01", "2027-03-31")
        self.assertTrue(bs1["balanced"]); self.assertTrue(bs2["balanced"])
        names = {e["name"]: e["amount"] for e in bs2["extra"]}
        self.assertEqual(names["Profit & Loss A/c (brought forward)"], 7000000)   # last year's profit (paise)
        self.assertEqual(names["Profit & Loss A/c (this period)"], 1000000 * -1)  # this year's 10,000 spending
        self.assertEqual(sum(a["amount"] for a in bs2["assets"]), 6000000)       # cash left: 60,000
        tb = rp.trial_balance(self.c, "2026-04-01", "2027-03-31")
        self.assertTrue(tb["balanced"] if "balanced" in tb else True)


class TestTallyChart(unittest.TestCase):
    def test_new_book_starts_like_tally(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            f = Path(d) / "t.db"; dbm.init_database(f); c = dbm.connect(f)
            groups = [r["name"] for r in c.execute("SELECT name FROM acct_groups")]
            for g in ("Branch / Divisions", "Capital Account", "Reserves & Surplus", "Current Assets", "Bank Accounts", "Cash-in-Hand", "Deposits (Asset)",
                      "Loans & Advances (Asset)", "Stock-in-Hand", "Sundry Debtors", "Current Liabilities", "Duties & Taxes", "Provisions", "Sundry Creditors",
                      "Direct Expenses", "Direct Incomes", "Fixed Assets", "Indirect Expenses", "Indirect Incomes", "Investments", "Loans (Liability)",
                      "Bank OD A/c", "Secured Loans", "Unsecured Loans", "Misc. Expenses (ASSET)", "Purchase Accounts", "Sales Accounts", "Suspense A/c"):
                self.assertIn(g, groups)
            self.assertEqual(len(groups), 28)
            self.assertEqual([r["name"] for r in c.execute("SELECT name FROM ledgers")], ["Cash"])
            self.assertEqual(c.execute("SELECT COUNT(*) FROM cost_centres").fetchone()[0], 0)
            self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], dbm.SCHEMA_VERSION)
            c.close()


class TestCreditDebitNotes(Base):
    def test_notes_number_separately_and_reject_cash(self):
        mk = lambda vt, dr, cr, d="2026-11-10": sv.save_voucher(self.c, {"vtype": vt, "date": d, "lines": [
            {"ledger_id": self.L[dr], "side": "Dr", "amount": "500"}, {"ledger_id": self.L[cr], "side": "Cr", "amount": "500"}]})
        a = mk("Credit Note", "Rubber Sales", "Advances Paid"); b = mk("Debit Note", "Advances Paid", "Rubber Sales"); c2 = mk("Credit Note", "Rubber Sales", "Advances Paid")
        self.assertEqual((a["number"], b["number"], c2["number"]), (1, 1, 2))
        with self.assertRaises(UserError): mk("Credit Note", "Rubber Sales", "Cash")


class TestUpgradeFromOldBook(unittest.TestCase):
    def test_v1_farm_book_is_upgraded_without_losing_entries(self):
        import legacy_v1_db as old
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            f = Path(d) / "old.db"; old._create_fresh(f, dt.date(2026, 11, 19))
            c = old.connect(f)
            L = {r["name"]: r["id"] for r in c.execute("SELECT id, name FROM ledgers")}
            c.execute("BEGIN IMMEDIATE")
            c.execute("INSERT INTO vouchers(vtype, fy, number, vdate, narration, ref, date_approx, status, created_at, updated_at) VALUES ('Payment','2026-27',1,'2026-11-10','rice','',0,'posted','t','t')")
            vid = c.execute("SELECT id FROM vouchers").fetchone()[0]
            c.execute("INSERT INTO entries(voucher_id, line_no, ledger_id, debit_paise, credit_paise) VALUES (?,1,?,50000,0)", (vid, L["Groceries & Provisions"]))
            c.execute("INSERT INTO entries(voucher_id, line_no, ledger_id, debit_paise, credit_paise) VALUES (?,2,?,0,50000)", (vid, L["Cash"]))
            c.execute("UPDATE ledgers SET opening_paise=100000 WHERE name='Farm Land'")
            c.execute("COMMIT"); c.close()
            dbm.init_database(f)                                           # upgrade
            c = dbm.connect(f)
            self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], dbm.SCHEMA_VERSION)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM vouchers").fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM entries").fetchone()[0], 2)
            names = {r["name"] for r in c.execute("SELECT name FROM ledgers")}
            self.assertIn("Groceries & Provisions", names)                 # used: kept
            self.assertIn("Farm Land", names)                              # has an opening balance: kept
            self.assertNotIn("Goat Sales", names)                          # unused starter: tidied away
            self.assertIn("Stock-in-Hand", {r["name"] for r in c.execute("SELECT name FROM acct_groups")})
            self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertTrue(list(Path(d).glob("homeledger-before-upgrade-*.db")))    # safety copy was made
            v = sv.save_voucher(c, {"vtype": "Credit Note", "date": "2026-11-11", "lines": [
                {"ledger_id": {r["name"]: r["id"] for r in c.execute("SELECT id, name FROM ledgers")}["Groceries & Provisions"], "side": "Dr", "amount": "5"},
                {"ledger_id": {r["name"]: r["id"] for r in c.execute("SELECT id, name FROM ledgers")}["Farm Land"], "side": "Cr", "amount": "5"}]})
            self.assertEqual(v["number"], 1)
            c.close()


class TestMoney(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(money.parse_amount("3,000"), 300000)
        self.assertEqual(money.parse_amount("0.10"), 10)
        self.assertEqual(money.parse_amount("₹ 1,23,456.78"), 12345678)
        self.assertEqual(money.parse_amount(0.1), 10)      # float input never drifts
        for bad in ["", "abc", "-5", "0", "1.234", "1e3", "NaN", "inf", None, "9" * 20]:
            with self.assertRaises(UserError, msg=str(bad)):
                money.parse_amount(bad)

    def test_inr(self):
        self.assertEqual(money.fmt_inr(12345678), "1,23,456.78")
        self.assertEqual(money.fmt_inr(-100), "-1.00")
        self.assertEqual(money.fmt_inr(99), "0.99")

    def test_qty_and_dates(self):
        self.assertEqual(money.parse_qty("2.5"), 2500)
        self.assertIsNone(money.parse_qty(""))
        with self.assertRaises(UserError): money.parse_qty("1.2345")
        with self.assertRaises(UserError): money.parse_iso("2026-02-30")
        with self.assertRaises(UserError): money.parse_iso("1850-01-01")
        self.assertEqual(money.fy_label("2026-03-31", 4), "2025-26")
        self.assertEqual(money.fy_label("2026-04-01", 4), "2026-27")


class TestVouchers(Base):
    def test_balanced_and_saved(self):
        v = self.pay("2026-11-10", "Groceries & Provisions", "1250.50")
        self.assertEqual(v["total_paise"], 125050)
        self.assertEqual(v["number"], 1)
        self.assertEqual(v["fy"], "2026-27")

    def test_unbalanced_rejected_and_nothing_saved(self):
        with self.assertRaises(UserError):
            sv.save_voucher(self.c, {"vtype": "Journal", "date": "2026-11-10", "lines": [
                {"ledger_id": self.L["Groceries & Provisions"], "side": "Dr", "amount": "100"},
                {"ledger_id": self.L["Money Borrowed"], "side": "Cr", "amount": "99.99"}]})
        self.assertEqual(self.c.execute("select count(*) from vouchers").fetchone()[0], 0)
        self.assertEqual(self.c.execute("select count(*) from entries").fetchone()[0], 0)

    def test_type_rules(self):
        g, cash, bank = self.L["Groceries & Provisions"], self.L["Cash"], self.L["Bank Account"]
        bad = [
            {"vtype": "Payment", "lines": [{"ledger_id": g, "side": "Dr", "amount": "5"}, {"ledger_id": self.L["Money Borrowed"], "side": "Cr", "amount": "5"}]},
            {"vtype": "Receipt", "lines": [{"ledger_id": self.L["Rubber Sales"], "side": "Cr", "amount": "5"}, {"ledger_id": g, "side": "Dr", "amount": "5"}]},
            {"vtype": "Contra", "lines": [{"ledger_id": cash, "side": "Dr", "amount": "5"}, {"ledger_id": g, "side": "Cr", "amount": "5"}]},
            {"vtype": "Journal", "lines": [{"ledger_id": cash, "side": "Dr", "amount": "5"}, {"ledger_id": self.L["Money Borrowed"], "side": "Cr", "amount": "5"}]},
            {"vtype": "Payment", "lines": [{"ledger_id": cash, "side": "Dr", "amount": "5"}, {"ledger_id": bank, "side": "Cr", "amount": "5"}]},
        ]
        for b in bad:
            with self.assertRaises(UserError, msg=b["vtype"]):
                sv.save_voucher(self.c, {"date": "2026-11-10", **b})

    def test_needs_both_sides_and_amount(self):
        for lines in ([], [{"ledger_id": self.L["Cash"], "side": "Cr", "amount": "0"}],
                      [{"ledger_id": 999999, "side": "Dr", "amount": "5"}]):
            with self.assertRaises(UserError):
                sv.save_voucher(self.c, {"vtype": "Payment", "date": "2026-11-10", "lines": lines})

    def test_numbering_per_type_and_year(self):
        self.pay("2026-11-10", "Water Bill", 10); self.pay("2026-11-11", "Water Bill", 10)
        v3 = self.pay("2027-04-02", "Water Bill", 10)
        r = self.rec("2026-11-12", "Other Income", 10)
        self.assertEqual(v3["number"], 1); self.assertEqual(v3["fy"], "2027-28")
        self.assertEqual(r["number"], 1)
        self.assertEqual(sv.next_number(self.c, "Payment", "2026-11-20"), 3)

    def test_before_books_begin_rejected(self):
        with self.assertRaises(UserError):
            self.pay("2019-01-01", "Water Bill", 10)

    def test_edit_and_cancel(self):
        v = self.pay("2026-11-10", "Water Bill", 100)
        edited = sv.save_voucher(self.c, {"id": v["id"], "vtype": "Payment", "date": "2026-11-12", "lines": [
            {"ledger_id": self.L["Water Bill"], "side": "Dr", "amount": "250"}, {"ledger_id": self.L["Cash"], "side": "Cr", "amount": "250"}]})
        self.assertEqual(edited["total_paise"], 25000); self.assertEqual(edited["number"], v["number"])
        tb = rp.trial_balance(self.c, "2026-04-01", "2027-03-31")
        self.assertEqual(tb["total_dr"], 25000)
        sv.set_voucher_status(self.c, v["id"], "cancelled")
        tb = rp.trial_balance(self.c, "2026-04-01", "2027-03-31")
        self.assertEqual(tb["total_dr"], 0)
        with self.assertRaises(UserError):
            sv.save_voucher(self.c, {"id": v["id"], "vtype": "Payment", "date": "2026-11-12", "lines": edited and [
                {"ledger_id": self.L["Water Bill"], "side": "Dr", "amount": "1"}, {"ledger_id": self.L["Cash"], "side": "Cr", "amount": "1"}]})
        sv.set_voucher_status(self.c, v["id"], "posted")
        self.assertEqual(rp.trial_balance(self.c, "2026-04-01", "2027-03-31")["total_dr"], 25000)
        log = [r["action"] for r in self.c.execute("select action from audit_log where entity='voucher' order by id")]
        self.assertEqual(log, ["create", "alter", "cancel", "restore"])

    def test_optional_and_delete(self):
        v = self.pay("2026-11-10", "Water Bill", 100, )
        v = sv.save_voucher(self.c, {"id": v["id"], "vtype": "Payment", "date": "2026-11-10", "status": "optional", "lines": [
            {"ledger_id": self.L["Water Bill"], "side": "Dr", "amount": "100"}, {"ledger_id": self.L["Cash"], "side": "Cr", "amount": "100"}]})
        self.assertEqual(v["status"], "optional")
        self.assertEqual(rp.trial_balance(self.c, "2026-04-01", "2027-03-31")["total_dr"], 0)
        sv.set_voucher_status(self.c, v["id"], "posted")
        self.assertEqual(rp.trial_balance(self.c, "2026-04-01", "2027-03-31")["total_dr"], 10000)
        sv.delete_voucher(self.c, v["id"])
        self.assertEqual(rp.trial_balance(self.c, "2026-04-01", "2027-03-31")["total_dr"], 0)
        self.assertEqual(self.c.execute("select count(*) from entries").fetchone()[0], 0)
        self.assertEqual(self.c.execute("select action from audit_log order by id desc limit 1").fetchone()[0], "delete")

    def test_database_refuses_bad_rows_directly(self):
        v = self.pay("2026-11-10", "Water Bill", 100)
        with self.assertRaises(sqlite3.IntegrityError):   # both sides on one line
            self.c.execute("insert into entries(voucher_id,line_no,ledger_id,debit_paise,credit_paise) values (?,9,?,5,5)", (v["id"], self.L["Cash"]))
        with self.assertRaises(sqlite3.IntegrityError):   # unknown ledger
            self.c.execute("insert into entries(voucher_id,line_no,ledger_id,debit_paise,credit_paise) values (?,9,424242,5,0)", (v["id"],))

    def test_items_reuse_spelling(self):
        self.pay("2026-11-10", "Fertilizer & Manure", 100, item="Urea", qty="10", unit="kg")
        v = self.pay("2026-11-11", "Fertilizer & Manure", 100, item="UREA", qty="10", unit="KG")
        self.assertEqual({l["item"] for l in v["lines"] if l["item"]}, {"Urea"})
        self.assertEqual({l["unit"] for l in v["lines"] if l["unit"]}, {"kg"})
        with self.assertRaises(UserError):
            self.pay("2026-11-11", "Fertilizer & Manure", 100, qty="5", unit="kg")      # quantity without an item
        with self.assertRaises(UserError):
            self.pay("2026-11-11", "Fertilizer & Manure", 100, item="Urea", qty="5")    # quantity without a unit


class TestLedgers(Base):
    def test_rules(self):
        r = sv.save_ledger(self.c, {"name": "Poultry Feed", "group_id": self.c.execute("select id from acct_groups where code='FARM_EXP'").fetchone()[0]})
        with self.assertRaises(UserError):
            sv.save_ledger(self.c, {"name": "poultry feed", "group_id": self.c.execute("select id from acct_groups where code='FARM_EXP'").fetchone()[0]})
        with self.assertRaises(UserError):   # expense ledgers cannot carry an opening balance
            sv.save_ledger(self.c, {"name": "X", "group_id": self.c.execute("select id from acct_groups where code='FARM_EXP'").fetchone()[0], "opening": "10"})
        sv.delete_ledger(self.c, r["id"])
        self.pay("2026-11-10", "Water Bill", 10)
        with self.assertRaises(UserError):
            sv.delete_ledger(self.c, self.L["Water Bill"])
        with self.assertRaises(UserError):   # cannot turn a used expense ledger into an asset
            sv.save_ledger(self.c, {"id": self.L["Water Bill"], "name": "Water Bill", "group_id": self.c.execute("select id from acct_groups where code='FIXED'").fetchone()[0]})


class TestReports(Base):
    def test_random_books_always_balance(self):
        rnd = random.Random(11)
        sv.set_openings(self.c, [{"ledger_id": self.L["Cash"], "amount": "5000", "type": "Dr"}, {"ledger_id": self.L["Bank Account"], "amount": "100000", "type": "Dr"},
                                 {"ledger_id": self.L["Bank Loan"], "amount": "30000", "type": "Cr"}, {"ledger_id": self.L["Capital Account"], "amount": "75000", "type": "Cr"}])
        exp = [n for n, l in self.L.items() if n in ("Groceries & Provisions", "Labour Wages", "Cattle Feed", "Water Bill")]
        d = dt.date(2025, 5, 1)
        for i in range(300):
            d += dt.timedelta(days=rnd.randint(0, 2))
            k = rnd.random()
            if k < .5: self.pay(d.isoformat(), rnd.choice(exp), f"{rnd.randint(1, 5000) / 100 + rnd.randint(0, 3000):.2f}", acct=rnd.choice(["Cash", "Bank Account"]))
            elif k < .8: self.rec(d.isoformat(), rnd.choice(["Rubber Sales", "Milk Sales", "Salary / Pension"]), rnd.randint(100, 20000), acct=rnd.choice(["Cash", "Bank Account"]))
            elif k < .9: sv.save_voucher(self.c, {"vtype": "Contra", "date": d.isoformat(), "lines": [{"ledger_id": self.L["Cash"], "side": "Dr", "amount": "500"}, {"ledger_id": self.L["Bank Account"], "side": "Cr", "amount": "500"}]})
            else: sv.save_voucher(self.c, {"vtype": "Journal", "date": d.isoformat(), "lines": [{"ledger_id": self.L["Water Bill"], "side": "Dr", "amount": "77.77"}, {"ledger_id": self.L["Money Borrowed"], "side": "Cr", "amount": "77.77"}]})
        for frm, to in (("2025-04-01", "2026-03-31"), ("2026-04-01", "2027-03-31"), ("2025-06-10", "2025-09-02")):
            tb = rp.trial_balance(self.c, frm, to)
            self.assertEqual(tb["closing_dr"], tb["closing_cr"], (frm, to))
            self.assertEqual(tb["opening_dr"], tb["opening_cr"], (frm, to))
            self.assertEqual(tb["total_dr"], tb["total_cr"], (frm, to))
            bs = rp.balance_sheet(self.c, frm, to)
            self.assertTrue(bs["balanced"], (frm, to))
            pl = rp.profit_and_loss(self.c, frm, to)
            self.assertEqual(pl["net"], pl["total_income"] - pl["total_expense"])
        # ledger statement closing == trial balance closing
        st = rp.ledger_statement(self.c, "2025-04-01", "2026-03-31", ledger_id=self.L["Cash"])
        tb = rp.trial_balance(self.c, "2025-04-01", "2026-03-31")
        cash = next(c for g in tb["tree"] for c in _walk(g) if c.get("id") == self.L["Cash"] and c["type"] == "ledger")
        self.assertEqual(st["closing"], cash["closing"])

    def test_dashboard_net_worth_excludes_capital(self):
        sv.set_openings(self.c, [{"ledger_id": self.L["Cash"], "amount": "1000", "type": "Dr"}, {"ledger_id": self.L["Capital Account"], "amount": "1000", "type": "Cr"}])
        d = rp.dashboard(self.c, "2026-04-01", "2027-03-31", "2026-11-19")
        self.assertEqual(d["cards"]["net_worth"], 100000)
        self.assertEqual(d["months"][-1]["net_worth"], 100000)

    def test_search_and_commodities(self):
        self.pay("2026-11-10", "Fertilizer & Manure", 3000, item="Urea", qty="50", unit="kg")
        self.pay("2026-11-12", "Fertilizer & Manure", 3300, item="Urea", qty="50", unit="kg")
        self.pay("2026-11-13", "Water Bill", 700)
        self.assertEqual(rp.search(self.c, {"q": "urea"})["count"], 2)
        self.assertEqual(rp.search(self.c, {"q": "3000"})["count"], 1)
        self.assertEqual(rp.search(self.c, {"q": "100%"})["count"], 0)            # wildcard characters are literal
        self.assertEqual(rp.search(self.c, {"item": "ure", "from": "2026-11-11"})["count"], 1)
        cm = rp.commodity_summary(self.c, "2026-04-01", "2027-03-31")["rows"][0]
        self.assertEqual((cm["paid"], cm["avg_buy"]), (630000, 6300))             # 63 rupees per kg
        act = rp.activity_summary(self.c, "2026-04-01", "2027-03-31")
        farm = next(r for r in act["rows"] if r["name"] == "Farm")
        self.assertEqual(farm["expense"], 630000)                                 # fertilizer is tagged to Farm by default
        self.assertEqual(sum(r["expense"] for r in act["rows"]), 630000 + 70000)


def _walk(n):
    yield n
    for c in n.get("children", []):
        yield from _walk(c)


class TestBackup(Base):
    def test_snapshot_restore_roundtrip(self):
        self.pay("2026-11-10", "Water Bill", 100)
        bdir = Path(self.tmp.name) / "b"
        snap = bk.make_snapshot(self.path, bdir, "manual")
        bk.validate_backup(snap)
        self.pay("2026-11-11", "Water Bill", 200)
        self.c.close()
        bk.restore_into(self.path, snap)
        c = dbm.connect(self.path)
        self.assertEqual(c.execute("select count(*) from vouchers").fetchone()[0], 1)
        self.assertEqual(dbm.quick_check(self.path), [])
        c.close(); self.c = dbm.connect(self.path)

    def test_bad_backup_refused(self):
        junk = Path(self.tmp.name) / "junk.db"; junk.write_bytes(b"not a database" * 50)
        with self.assertRaises(UserError): bk.validate_backup(junk)
        other = Path(self.tmp.name) / "other.db"
        c = sqlite3.connect(other); c.execute("create table x(a)"); c.commit(); c.close()
        with self.assertRaises(UserError): bk.validate_backup(other)

    def test_rotation_keeps_recent_and_thins_old(self):
        d = Path(self.tmp.name) / "r"; d.mkdir()
        now = dt.datetime(2026, 11, 19, 12, 0, 0)
        names = []
        for days in range(0, 120):
            for hr in (8, 20):
                t = now - dt.timedelta(days=days, hours=12 - hr)
                n = f"homeledger-{t:%Y%m%d-%H%M%S}-auto.db"; (d / n).write_bytes(b"x"); names.append(n)
        (d / "homeledger-20200101-000000-manual.db").write_bytes(b"x")
        bk.rotate(d, now)
        left = bk.list_backups(d)
        self.assertTrue(any(b["reason"] == "manual" for b in left))
        self.assertGreaterEqual(len([b for b in left if b["when"] >= "2026-11-18"]), 2)   # recent ones all kept
        self.assertLess(len(left), 70)


class TestStartup(unittest.TestCase):
    def test_corrupt_file_detected(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "x.db"; dbm._create_fresh(p)
            data = bytearray(p.read_bytes()); data[len(data) // 2: len(data) // 2 + 4000] = os.urandom(4000); p.write_bytes(bytes(data))
            with self.assertRaises((CorruptDatabase, sqlite3.DatabaseError)):
                dbm.init_database(p)

    def test_newer_version_refused(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "x.db"; dbm._create_fresh(p)
            c = sqlite3.connect(p); c.execute("pragma user_version=99"); c.commit(); c.close()
            with self.assertRaises(UserError): dbm.init_database(p)


if __name__ == "__main__":
    unittest.main(verbosity=1)
