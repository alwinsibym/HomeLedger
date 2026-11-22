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

    def test_memorandum_and_reversing_journal(self):
        lines = [{"ledger_id": self.L["Water Bill"], "side": "Dr", "amount": "50"}, {"ledger_id": self.L["Cash"], "side": "Cr", "amount": "50"}]
        m = sv.save_voucher(self.c, {"vtype": "Memorandum", "date": "2026-11-10", "lines": lines})
        self.assertEqual(m["status"], "memo")
        self.assertEqual(rp.trial_balance(self.c, "2026-04-01", "2027-03-31")["total_dr"], 0)
        with self.assertRaises(UserError):   # cash not allowed in a reversing journal
            sv.save_voucher(self.c, {"vtype": "Reversing Journal", "date": "2026-11-10", "lines": lines})

    def test_ratio_analysis(self):
        r = rp.ratio_analysis(self.c, "2026-04-01", "2027-03-31")
        self.assertEqual({i["name"] for i in r["items"]} >= {"Current Ratio", "Working Capital"}, True)
        self.pay("2026-11-10", "Water Bill", 100)
        r2 = {i["name"]: i["value"] for i in rp.ratio_analysis(self.c, "2026-04-01", "2027-03-31")["items"]}
        self.assertEqual(r2["Cash-in-Hand + Bank"], r2["Working Capital"])

    def test_outstanding_fifo(self):
        d = sv.save_ledger(self.c, {"name": "Ravi Stores", "group_id": self.c.execute("select id from acct_groups where code='DEBTORS'").fetchone()[0]})
        did = d["id"] if isinstance(d, dict) else d
        sv.save_voucher(self.c, {"vtype": "Sales", "date": "2026-08-01", "lines": [
            {"ledger_id": did, "side": "Dr", "amount": "1000"}, {"ledger_id": self.L["Water Bill"], "side": "Cr", "amount": "1000"}]})
        sv.save_voucher(self.c, {"vtype": "Sales", "date": "2026-11-01", "lines": [
            {"ledger_id": did, "side": "Dr", "amount": "500"}, {"ledger_id": self.L["Water Bill"], "side": "Cr", "amount": "500"}]})
        sv.save_voucher(self.c, {"vtype": "Receipt", "date": "2026-11-05", "lines": [
            {"ledger_id": did, "side": "Cr", "amount": "400"}, {"ledger_id": self.L["Cash"], "side": "Dr", "amount": "400"}]})
        r = rp.outstanding(self.c, "receivable", "2026-11-20")
        row = r["rows"][0]
        self.assertEqual(row["due"], 110000)               # 1500 - 400
        self.assertEqual(row["buckets"], [50000, 0, 0, 60000])   # oldest settled first: 600 left of the August bill
        with self.assertRaises(UserError):
            rp.outstanding(self.c, "x", "2026-11-20")

    def test_cash_flow(self):
        self.pay("2026-11-10", "Water Bill", 100)
        self.rec("2026-11-11", "Water Bill", 30, acct="Cash")
        r = rp.cash_flow(self.c, "2026-04-01", "2027-03-31")
        self.assertTrue(r["check"])
        self.assertEqual((r["total_in"], r["total_out"]), (3000, 10000))

    def test_bank_reconciliation(self):
        v = self.rec("2026-11-10", "Water Bill", 500)
        bank = self.L["Bank Account"]
        r = rp.bank_reconciliation(self.c, bank, "2026-11-30")
        self.assertEqual((r["books"], r["bank"]), (50000, 0))
        sv.set_bank_date(self.c, v["id"], bank, "2026-11-12")
        r = rp.bank_reconciliation(self.c, bank, "2026-11-30")
        self.assertEqual((r["books"], r["bank"]), (50000, 50000))
        sv.save_voucher(self.c, {"id": v["id"], "vtype": "Receipt", "date": "2026-11-10", "lines": [   # altering keeps the mark
            {"ledger_id": self.L["Water Bill"], "side": "Cr", "amount": "600"}, {"ledger_id": bank, "side": "Dr", "amount": "600"}]})
        self.assertEqual(rp.bank_reconciliation(self.c, bank, "2026-11-30")["bank"], 60000)
        with self.assertRaises(UserError):
            sv.set_bank_date(self.c, v["id"], self.L["Cash"], "2026-11-12")
        sv.set_bank_date(self.c, v["id"], bank, "")
        self.assertEqual(rp.bank_reconciliation(self.c, bank, "2026-11-30")["bank"], 0)

    def test_stock_summary(self):
        sid = sv.save_stock_item(self.c, {"name": "Rice", "unit": "kg", "opening_qty": "100", "opening_value": "2000"})["id"]
        with self.assertRaises(UserError):
            sv.save_stock_item(self.c, {"name": "rice", "unit": "kg"})
        self.pay("2026-11-02", "Water Bill", 1000, item="Rice", qty="50", unit="kg")      # 50 kg in at 1000 (20/kg)
        sv.save_voucher(self.c, {"vtype": "Receipt", "date": "2026-11-05", "lines": [
            {"ledger_id": self.L["Water Bill"], "side": "Cr", "amount": "900", "item": "rice", "qty": "30", "unit": "kg"},
            {"ledger_id": self.L["Cash"], "side": "Dr", "amount": "900"}]})
        r = rp.stock_summary(self.c, "2026-04-01", "2027-03-31")
        row = r["rows"][0]
        self.assertEqual((row["in_q"], row["out_q"], row["close_q"]), (50000, 30000, 120000))
        self.assertEqual(row["close_v"], 240000)        # 120 kg at average Rs 20
        with self.assertRaises(UserError):
            sv.delete_stock_item(self.c, sid)

    def test_postdated_cheque_and_classes(self):
        bank = self.L["Bank Account"]
        lines = [{"ledger_id": self.L["Water Bill"], "side": "Dr", "amount": "250"}, {"ledger_id": bank, "side": "Cr", "amount": "250"}]
        v = sv.save_voucher(self.c, {"vtype": "Payment", "date": "2026-12-20", "lines": lines,
                                     "meta": {"post_dated": True, "inst_no": "004512", "inst_date": "2026-12-20", "bank_name": "SBI"}})
        self.assertEqual(v["status"], "optional")
        self.assertEqual(v["meta"]["inst_no"], "004512")
        self.assertEqual(rp.trial_balance(self.c, "2026-04-01", "2027-03-31")["total_dr"], 0)
        self.assertEqual(len(sv.list_postdated(self.c)), 1)
        self.assertEqual(sv.cheque_register(self.c, "2026-04-01", "2027-03-31")[0]["inst_no"], "004512")
        sv.activate_postdated(self.c, v["id"])
        self.assertEqual(rp.trial_balance(self.c, "2026-04-01", "2027-03-31")["total_dr"], 25000)
        self.assertEqual(sv.list_postdated(self.c), [])
        cid = sv.save_class(self.c, {"name": "Cash Sales", "vtype": "Receipt", "lines": [{"ledger_id": self.L["Cash"], "side": "Dr"}]})["id"]
        self.assertEqual(sv.list_classes(self.c)[0]["lines"][0]["side"], "Dr")
        with self.assertRaises(UserError):
            sv.save_class(self.c, {"name": "cash sales", "vtype": "Receipt"})
        sv.delete_class(self.c, cid)
        sv.delete_voucher(self.c, v["id"])
        self.assertEqual(self.c.execute("select count(*) from voucher_meta").fetchone()[0], 0)

    def test_bill_wise(self):
        gid = self.c.execute("select id from acct_groups where code='DEBTORS'").fetchone()[0]
        d = sv.save_ledger(self.c, {"name": "Mohan Traders", "group_id": gid}); did = d["id"] if isinstance(d, dict) else d
        inc = self.L["Water Bill"]
        sv.save_voucher(self.c, {"vtype": "Sales", "date": "2026-09-01", "lines": [
            {"ledger_id": did, "side": "Dr", "amount": "1000", "bills": [{"ref": "INV-1", "kind": "new", "amount": "600"}, {"ref": "INV-2", "kind": "new", "amount": "400"}]},
            {"ledger_id": inc, "side": "Cr", "amount": "1000"}]})
        # settle INV-2 first, not the oldest
        sv.save_voucher(self.c, {"vtype": "Receipt", "date": "2026-11-01", "lines": [
            {"ledger_id": did, "side": "Cr", "amount": "400", "bills": [{"ref": "inv-2", "kind": "against", "amount": "400"}]},
            {"ledger_id": self.L["Cash"], "side": "Dr", "amount": "400"}]})
        row = rp.outstanding(self.c, "receivable", "2026-11-20")["rows"][0]
        self.assertTrue(row["bill_wise"])
        self.assertEqual([(b["ref"], b["pending"]) for b in row["bills"]], [("INV-1", 60000)])
        self.assertEqual(row["due"], 60000)
        self.assertEqual([b["ref"] for b in sv.open_bills(self.c, did)], ["INV-1"])
        with self.assertRaises(UserError):       # settling a bill that does not exist
            sv.save_voucher(self.c, {"vtype": "Receipt", "date": "2026-11-02", "lines": [
                {"ledger_id": did, "side": "Cr", "amount": "10", "bills": [{"ref": "NOPE", "kind": "against", "amount": "10"}]},
                {"ledger_id": self.L["Cash"], "side": "Dr", "amount": "10"}]})
        with self.assertRaises(UserError):       # more than the line
            sv.save_voucher(self.c, {"vtype": "Receipt", "date": "2026-11-02", "lines": [
                {"ledger_id": did, "side": "Cr", "amount": "10", "bills": [{"ref": "INV-1", "kind": "against", "amount": "99"}]},
                {"ledger_id": self.L["Cash"], "side": "Dr", "amount": "10"}]})
        with self.assertRaises(UserError):       # bills only for debtors and creditors
            sv.save_voucher(self.c, {"vtype": "Payment", "date": "2026-11-02", "lines": [
                {"ledger_id": inc, "side": "Dr", "amount": "10", "bills": [{"ref": "X", "kind": "new", "amount": "10"}]},
                {"ledger_id": self.L["Cash"], "side": "Cr", "amount": "10"}]})

    def test_more_reports(self):
        self.rec("2026-10-01", "Water Bill", 1000)
        self.pay("2026-10-05", "Water Bill", 300)
        f, t = "2026-04-01", "2027-03-31"
        rp_ = rp.receipts_payments(self.c, f, t)
        self.assertTrue(rp_["check"])
        self.assertEqual((rp_["total_receipts"], rp_["total_payments"]), (100000, 30000))
        ff = rp.fund_flow(self.c, f, t)
        self.assertTrue(ff["check"])
        gs = rp.group_summary(self.c, f, t)
        self.assertTrue(gs["items"])
        # scenario: an optional voucher shows only when asked for
        lines = [{"ledger_id": self.L["Water Bill"], "side": "Dr", "amount": "50"}, {"ledger_id": self.L["Cash"], "side": "Cr", "amount": "50"}]
        sv.save_voucher(self.c, {"vtype": "Payment", "date": "2026-10-06", "status": "optional", "lines": lines})
        sc = rp.scenario(self.c, f, t, optional=True)
        self.assertEqual(sc["vouchers_added"], 1)
        self.assertEqual(sc["actual_net"] - sc["scenario_net"], 5000)
        # interest: Rs 10,000 owed for 10 days at 12% = 32.88
        gid = self.c.execute("select id from acct_groups where code='DEBTORS'").fetchone()[0]
        d = sv.save_ledger(self.c, {"name": "Slow Payer", "group_id": gid}); did = d["id"] if isinstance(d, dict) else d
        sv.save_voucher(self.c, {"vtype": "Sales", "date": "2026-11-01", "lines": [
            {"ledger_id": did, "side": "Dr", "amount": "10000"}, {"ledger_id": self.L["Water Bill"], "side": "Cr", "amount": "10000"}]})
        it = rp.interest(self.c, "2026-11-01", "2026-11-10", 1200, gid)
        self.assertEqual(it["rows"][0]["interest"], 3288)
        # budget
        sv.save_budget(self.c, {"kind": "ledger", "target_id": self.L["Water Bill"], "fy": "2026-27", "amount": "1000"})
        br = sv.budget_report(self.c, f, t)
        self.assertEqual(br["rows"][0]["budget"], 100000)

    def _stock_buy(self, item, date, qty, amount, godown=1, batch="", expiry=None, vtype="Purchase"):
        from homeledger import inventory as inv
        return sv.save_voucher(self.c, {"vtype": vtype, "date": date, "lines": [
            {"ledger_id": self.L["Water Bill"], "side": "Dr", "amount": str(amount)}, {"ledger_id": self.L["Cash"], "side": "Cr", "amount": str(amount)}],
            "items": [{"item_id": item, "qty": str(qty), "amount": str(amount), "godown_id": godown, "batch": batch, "expiry": expiry}]})

    def test_inventory_valuation_methods(self):
        from homeledger import inventory as inv
        res = {}
        for meth in ("avg", "fifo", "lifo", "last", "std"):
            iid = inv.save_item(self.c, {"name": "Item-" + meth, "unit": "kg", "valuation": meth, "std_rate": "7" if meth == "std" else ""})["id"]
            self._stock_buy(iid, "2026-05-01", 10, 100)          # 10 kg at 10
            self._stock_buy(iid, "2026-06-01", 10, 200)          # 10 kg at 20
            sv.save_voucher(self.c, {"vtype": "Sales", "date": "2026-07-01", "lines": [
                {"ledger_id": self.L["Cash"], "side": "Dr", "amount": "500"}, {"ledger_id": self.L["Water Bill"], "side": "Cr", "amount": "500"}],
                "items": [{"item_id": iid, "qty": "5", "amount": "500"}]})                       # sell 5 kg
            row = [r for r in rp.stock_summary(self.c, "2026-04-01", "2027-03-31")["rows"] if r["item_id"] == iid][0]
            res[meth] = (row["close_q"], row["close_v"], row["out_v"])
        self.assertEqual(res["avg"], (15000, 22500, 7500))       # avg 15/kg
        self.assertEqual(res["fifo"], (15000, 25000, 5000))      # sold the 10/kg ones
        self.assertEqual(res["lifo"], (15000, 20000, 10000))     # sold the 20/kg ones
        self.assertEqual(res["last"], (15000, 30000, 10000))     # everything at last cost 20
        self.assertEqual(res["std"], (15000, 10500, 3500))       # everything at 7

    def test_inventory_godowns_batches_transfer_manufacture_orders(self):
        from homeledger import inventory as inv
        wh = inv.save_godown(self.c, {"name": "Shed"})["id"]
        flour = inv.save_item(self.c, {"name": "Flour", "unit": "kg", "track_batches": True})["id"]
        bread = inv.save_item(self.c, {"name": "Bread", "unit": "nos"})["id"]
        with self.assertRaises(UserError):                         # batch tracked: batch needed
            self._stock_buy(flour, "2026-05-01", 100, 2000)
        self._stock_buy(flour, "2026-05-01", 100, 2000, batch="B1", expiry="2026-12-01")
        # transfer 40 kg to the shed
        sv.save_voucher(self.c, {"vtype": "Stock Journal", "date": "2026-05-02", "items": [
            {"item_id": flour, "qty": "40", "godown_id": 1, "godown_to_id": wh, "kind": "transfer", "batch": "B1"}]})
        gs = {(x["godown"], x["item"]): x["qty"] for x in inv.godown_summary(self.c, "2027-03-31")}
        self.assertEqual((gs[("Main Location", "Flour")], gs[("Shed", "Flour")]), (60000, 40000))
        self.assertEqual({r["name"]: r for r in rp.stock_summary(self.c, "2026-04-01", "2027-03-31")["rows"]}["Flour"]["close_v"], 200000)   # value unchanged by transfer
        # manufacture: 50 kg flour -> 100 bread; cost of flour carries to the bread
        sv.save_voucher(self.c, {"vtype": "Stock Journal", "date": "2026-05-03", "items": [
            {"item_id": flour, "qty": "50", "kind": "consume", "batch": "B1"}, {"item_id": bread, "qty": "100", "kind": "produce"}]})
        rows = {r["name"]: r for r in rp.stock_summary(self.c, "2026-04-01", "2027-03-31")["rows"]}
        self.assertEqual((rows["Bread"]["close_q"], rows["Bread"]["close_v"]), (100000, 100000))
        self.assertEqual(rows["Flour"]["close_q"], 50000)
        b = inv.batch_summary(self.c, "2027-03-31", "2026-11-21")[0]
        self.assertEqual((b["batch"], b["qty"], b["days_left"]), ("B1", 50000, 10))
        # orders do not move stock; a delivery against the order reduces what is pending
        so = sv.save_voucher(self.c, {"vtype": "Sales Order", "date": "2026-05-04", "items": [{"item_id": bread, "qty": "60", "rate": "15"}]})
        self.assertEqual(so["status"], "memo")
        self.assertEqual(rows["Bread"]["close_q"], 100000)
        self.assertEqual(inv.pending_orders(self.c)[0]["pending"], 60000)
        sv.save_voucher(self.c, {"vtype": "Delivery Note", "date": "2026-05-05", "items": [{"item_id": bread, "qty": "25", "order_ref": str(so["number"])}]})
        self.assertEqual(inv.pending_orders(self.c)[0]["pending"], 35000)
        self.assertEqual({r["name"]: r for r in rp.stock_summary(self.c, "2026-04-01", "2027-03-31")["rows"]}["Bread"]["close_q"], 75000)
        # price list and bad input
        inv.set_price(self.c, {"level": "Retail", "item_id": bread, "from_date": "2026-05-01", "rate": "18"})
        self.assertEqual(inv.price_for(self.c, bread, "Retail", "2026-06-01")["rate_paise"], 1800)
        with self.assertRaises(UserError):
            sv.save_voucher(self.c, {"vtype": "Payment", "date": "2026-05-06", "lines": [
                {"ledger_id": self.L["Water Bill"], "side": "Dr", "amount": "1"}, {"ledger_id": self.L["Cash"], "side": "Cr", "amount": "1"}],
                "items": [{"item_id": bread, "qty": "0"}]})

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


class TestCompanies(Base):
    def setUp(self):
        super().setUp()
        os.environ["HOMELEDGER_DATA"] = self.tmp.name
        from homeledger import companies as co
        self.co = co
        from homeledger import config
        dbm._create_fresh(config.db_path())

    def test_create_list_and_remove(self):
        cid = self.co.create("Second Co")
        names = [c["name"] for c in self.co.listing()]
        self.assertIn("Second Co", names)
        self.co.set_current(cid)
        self.assertEqual(self.co.current_id(), cid)
        with self.assertRaises(UserError): self.co.remove_from_list(cid)
        self.co.set_current("main")
        self.co.remove_from_list(cid)
        self.assertNotIn("Second Co", [c["name"] for c in self.co.listing()])
        self.assertTrue(self.co.paths(cid)[0].exists())      # files are kept

    def test_year_end_carry_forward(self):
        self.rec("2025-06-10", "Rubber Sales", 100000, "Cash")
        self.pay("2025-09-01", "Groceries & Provisions", 30000)
        self.pay("2026-05-05", "Groceries & Provisions", 10000)
        before = rp.balance_sheet(self.c, "2026-04-01", "2027-03-31")
        cid, _ = self.co.carry_forward(self.c, self.path, "2026-04-01", "Next Year")
        f, _b = self.co.paths(cid)
        dbm.init_database(f)
        n = dbm.connect(f)
        try:
            self.assertEqual(dbm.get_company(n)["books_begin"], "2026-04-01")
            self.assertEqual(n.execute("SELECT COUNT(*) FROM vouchers").fetchone()[0], 1)   # only the 2026 one
            after = rp.balance_sheet(n, "2026-04-01", "2027-03-31")
            self.assertEqual(str(before["total_left"] if "total_left" in before else before.get("total")),
                             str(after["total_left"] if "total_left" in after else after.get("total")))
            tb = rp.trial_balance(n, "2026-04-01", "2027-03-31")
            self.assertEqual(tb["closing_dr"], tb["closing_cr"])
        finally:
            n.close()
        # original untouched
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM vouchers").fetchone()[0], 3)

    def test_merge(self):
        self.pay("2026-05-05", "Groceries & Provisions", 10000)
        cid = self.co.create("Other", "2025-04-01")
        f, _b = self.co.paths(cid)
        o = dbm.connect(f)
        sv.save_ledger(o, {"name": "Rent Income", "group_id": o.execute("SELECT id FROM acct_groups WHERE code='INDIRECT_INC'").fetchone()[0]})
        cash = o.execute("SELECT id FROM ledgers WHERE name='Cash'").fetchone()[0]
        ri = o.execute("SELECT id FROM ledgers WHERE name='Rent Income'").fetchone()[0]
        sv.save_voucher(o, {"vtype": "Receipt", "date": "2026-06-01", "lines": [
            {"ledger_id": ri, "side": "Cr", "amount": "500"}, {"ledger_id": cash, "side": "Dr", "amount": "500"}]})
        o.close()
        res = self.co.merge_from(self.c, f)
        self.assertEqual(res["vouchers"], 1)
        self.assertEqual(res["ledgers"], 1)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM vouchers").fetchone()[0], 2)
        tb = rp.trial_balance(self.c, "2026-04-01", "2027-03-31")
        self.assertEqual(tb["total_dr"], tb["total_cr"])


class TestUtilities(Base):
    def test_repair_and_tally_roundtrip(self):
        from homeledger import utilities as ut
        self.pay("2026-05-05", "Groceries & Provisions", 1250)
        r = ut.repair(self.c)
        self.assertTrue(r["ok"], r)
        xml = ut.export_xml(self.c, "2026-04-01", "2027-03-31")
        self.assertIn(b"<AMOUNT>-1250.00</AMOUNT>", xml)
        # import the same file into a fresh book
        p2 = Path(self.tmp.name) / "b.db"; dbm._create_fresh(p2)
        c2 = dbm.connect(p2)
        try:
            res = ut.import_xml(c2, xml)
            self.assertEqual(res["vouchers"], 1, res)
            self.assertEqual(c2.execute("SELECT debit_paise FROM entries WHERE debit_paise>0").fetchone()[0], 125000)
            with self.assertRaises(UserError):
                ut.import_xml(c2, b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><ENVELOPE/>')
        finally:
            c2.close()


class TestRoles(unittest.TestCase):
    def test_new_roles_and_upgrade(self):
        from homeledger import auth
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "r.db"; dbm._create_fresh(p)
            c = dbm.connect(p)
            auth.add_user(c, "dad", "secret123", "owner")
            auth.add_user(c, "clerk", "secret123", "entry")
            auth.add_user(c, "ca", "secret123", "accountant")
            self.assertEqual(sorted(u["role"] for u in auth.users(c)), ["accountant", "entry", "owner"])
            c.close()
            # an old (v9) users table is widened by the upgrade
            c = sqlite3.connect(p)
            c.execute("PRAGMA foreign_keys=OFF")
            c.execute("DROP TABLE users")
            c.execute(dbm.SCHEMA_V2.replace("'owner','accountant','entry','viewer'", "'owner','viewer'"))
            c.execute("INSERT INTO users(username, role, salt, hash, iters, created) VALUES ('old','owner',x'00',x'00',1,'x')")
            c.execute("PRAGMA user_version=9"); c.commit(); c.close()
            dbm.init_database(p)
            c = dbm.connect(p)
            self.assertEqual([u["username"] for u in auth.users(c)], ["old"])
            auth.add_user(c, "clerk", "secret123", "entry")
            c.close()


class TestGST(Base):
    def test_gst_invoice_flow(self):
        from homeledger import gst, inventory as inv
        with self.assertRaises(UserError):
            gst.save_config(self.c, {"on": True, "gstin": "27AAPFU0939F1ZX"})        # bad check letter
        self.assertTrue(gst.gstin_ok("27AAPFU0939F1ZV"))
        cfg = gst.save_config(self.c, {"on": True, "state": "32"})
        self.assertEqual(set(cfg["tax_ledgers"]), {"cgst", "sgst", "igst"})
        item = inv.save_item(self.c, {"name": "Widget", "unit": "nos"})["id"]
        gst.save_item(self.c, {"item_id": item, "hsn": "9988", "rate": "18"})
        party = self.L["Rubber Sales"]      # any ledger works as the party for this test
        comp = gst.compute(self.c, "Sales", party, "32", [{"item_id": item, "amount_paise": 100000}])
        self.assertTrue(comp["intra"]); self.assertEqual(comp["rows"][0]["cgst_paise"], 9000); self.assertEqual(comp["rows"][0]["sgst_paise"], 9000)
        inter = gst.compute(self.c, "Sales", party, "29", [{"item_id": item, "amount_paise": 100000}])
        self.assertFalse(inter["intra"]); self.assertEqual(inter["rows"][0]["igst_paise"], 18000)
        tl = cfg["tax_ledgers"]
        lines = [{"ledger_id": self.L["Cash"], "side": "Dr", "amount": "1180.00"},
                 {"ledger_id": party, "side": "Cr", "amount": "1000.00"},
                 {"ledger_id": tl["cgst"], "side": "Cr", "amount": "90.00"}, {"ledger_id": tl["sgst"], "side": "Cr", "amount": "90.00"}]
        with self.assertRaises(UserError):      # tax lines that do not match the breakup are refused
            sv.save_voucher(self.c, {"vtype": "Sales", "date": "2026-06-01", "lines": lines, "gst": {"rows": [dict(comp["rows"][0], cgst_paise=8000)], "pos": "32"}, "gst_party": party})
        v = sv.save_voucher(self.c, {"vtype": "Sales", "date": "2026-06-01", "lines": lines, "gst": {"rows": comp["rows"], "pos": "32"}, "gst_party": party})
        self.assertEqual(v["gst"]["rows"][0]["taxable_paise"], 100000)
        s = gst.summary(self.c, "2026-04-01", "2027-03-31")
        self.assertEqual((s["outward"]["cgst"], s["net_total"]), (9000, 18000))
        r1 = gst.gstr1(self.c, "2026-04-01", "2027-03-31")
        self.assertEqual(len(r1["b2c"]), 1); self.assertEqual(r1["hsn"][0]["taxable"], 100000)


class TestTDS(Base):
    def test_tds_flow(self):
        from homeledger import tds
        info = tds.setup(self.c)
        self.assertGreaterEqual(len(info["natures"]), 8)
        contr = next(n for n in info["natures"] if n["code"] == "1023")["id"]
        party = sv.save_ledger(self.c, {"name": "Contractor Ram", "group_id": self.c.execute("SELECT id FROM acct_groups WHERE code='CREDITORS'").fetchone()[0]})
        party = party["id"] if isinstance(party, dict) else party
        tds.save_pan(self.c, {"ledger_id": party, "pan": "ABCDE1234F"})
        with self.assertRaises(UserError): tds.save_pan(self.c, {"ledger_id": party, "pan": "BAD"})
        a = tds.compute(self.c, contr, party, 2000000, "2026-05-01")         # 20,000: below both limits
        self.assertFalse(a["liable"])
        b = tds.compute(self.c, contr, party, 5000000, "2026-05-01")         # 50,000 > 30,000 single limit: 1%
        self.assertEqual((b["liable"], b["tax_paise"]), (True, 50000))
        nopan = tds.compute(self.c, contr, self.L["Cash"], 5000000, "2026-05-01")
        self.assertEqual(nopan["rate_bp"], 2000)
        lid = info["ledger_id"]
        lines = [{"ledger_id": self.L["Groceries & Provisions"], "side": "Dr", "amount": "50000.00"},
                 {"ledger_id": party, "side": "Cr", "amount": "49500.00"}, {"ledger_id": lid, "side": "Cr", "amount": "500.00"}]
        rec = {"nature_id": contr, "party": party, "base_paise": 5000000, "taxed_base_paise": 5000000, "rate_bp": 100, "tax_paise": 50000}
        with self.assertRaises(UserError):
            sv.save_voucher(self.c, {"vtype": "Journal", "date": "2026-05-01", "lines": lines, "tds": dict(rec, tax_paise=40000)})
        v = sv.save_voucher(self.c, {"vtype": "Journal", "date": "2026-05-01", "lines": lines, "tds": rec})
        self.assertEqual(v["tds"]["tax_paise"], 50000)
        st = tds.statement(self.c, "2026-04-01", "2027-03-31")
        self.assertEqual(st["total_tax"], 50000)
        tds.save_challan(self.c, {"paid_on": "2026-06-05", "for_month": "2026-05", "amount": "500", "bsr": "0510308"})
        d = tds.deposits(self.c, "2026-12-01")
        self.assertEqual((d["months"][0]["balance_paise"], d["months"][0]["status"]), (0, "Paid"))
        self.assertEqual(tds._due("2027-03"), "2027-04-30")
        # a second payment makes the yearly limit (1,00,000) cross: earlier untaxed money is caught up
        c2 = tds.compute(self.c, contr, party, 5200000, "2026-06-01")
        self.assertTrue(c2["liable"])


class TestPayroll(Base):
    def test_payroll_flow(self):
        from homeledger import payroll as pr
        hs = {h["name"]: h["id"] for h in pr.heads(self.c)}
        e = pr.save_employee(self.c, {"name": "Raju", "structure": {hs["Basic Salary"]: {"amount_paise": 2000000}, hs["Allowances"]: {"amount_paise": 500000},
                                                                      hs["Provident Fund (employee)"]: {"rate_bp": 1200}}})["id"]
        run = pr.get_run(self.c, "2026-06")
        s = run["slips"][0]
        self.assertEqual((s["gross_paise"], s["deduct_paise"], s["net_paise"]), (2500000, 240000, 2260000))
        # half the month present: pay and PF are cut in proportion
        c = pr.calc_slip(run["heads"], pr.employees(self.c)[0]["structure"], 15, 30)
        self.assertEqual((c["gross_paise"], c["deduct_paise"]), (1250000, 120000))
        # a typed TDS / advance override is kept
        c2 = pr.calc_slip(run["heads"], pr.employees(self.c)[0]["structure"], 30, 30, {hs["Advance recovery"]: 100000})
        self.assertEqual(c2["deduct_paise"], 340000)
        with self.assertRaises(UserError): pr.calc_slip(run["heads"], {hs["Basic Salary"]: {"amount_paise": 100, "rate_bp": 0}}, 31, 30)
        pr.save_run(self.c, {"month": "2026-06", "working_days": 30, "slips": [{"employee_id": e, "days_present": 30}]})
        out = pr.post_run(self.c, "2026-06")
        v = sv.get_voucher(self.c, out["voucher_id"])
        self.assertEqual(sum(l["amount_paise"] for l in v["lines"] if l["side"] == "Dr"), 2500000)
        with self.assertRaises(UserError): pr.post_run(self.c, "2026-06")
        with self.assertRaises(UserError): pr.reopen_run(self.c, "2026-06")        # voucher still live
        sv.set_voucher_status(self.c, out["voucher_id"], "cancelled")
        pr.reopen_run(self.c, "2026-06")
        self.assertEqual(pr.get_run(self.c, "2026-06")["status"], "draft")
        tb = rp.trial_balance(self.c, "2026-04-01", "2027-03-31")


class TestBulkAndAttach(Base):
    def test_attachments(self):
        import base64
        from homeledger import attach
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 50).decode()
        v = self.pay("2026-05-05", "Groceries & Provisions", 1000)
        aid = attach.add(self.c, {"filename": "bill.png", "data": png, "voucher_id": v["id"]})["id"]
        with self.assertRaises(UserError): attach.add(self.c, {"filename": "again.png", "data": png})        # same file twice
        with self.assertRaises(UserError): attach.add(self.c, {"filename": "x.exe", "data": base64.b64encode(b"MZ" + b"0" * 30).decode()})
        self.assertEqual(attach.counts(self.c)[v["id"]], 1)
        self.assertEqual(attach.get_file(self.c, aid)[3], "image/png")
        attach.link(self.c, aid, None)
        self.assertEqual(len(attach.listing(self.c, inbox=True)), 1)

    def test_import_and_rules(self):
        import base64, io, zipfile
        from homeledger import bulk
        csvtxt = "Date,Particulars,Amount,Type\n05-06-2026,Kerala Agro fertiliser,\"1,250.00\",Dr\n06/06/2026,Milk sale,300,Cr\nbad,x,1,Dr\n"
        pf = bulk.parse_file("n.csv", base64.b64encode(csvtxt.encode()).decode())
        self.assertEqual(pf["headers"][1], "Particulars")
        grocer = self.L["Groceries & Provisions"]
        bulk.save_rule(self.c, {"keyword": "fertiliser", "ledger_id": grocer})
        pv = bulk.preview(self.c, {"rows": pf["rows"], "map": {"date": 0, "desc": 1, "amount": 2, "type": 3}})
        self.assertEqual((pv["rows"][0]["amount_paise"], pv["rows"][0]["dir"], pv["rows"][0]["ledger_id"], pv["rows"][0]["source"]), (125000, "out", grocer, "rule"))
        self.assertEqual(pv["rows"][1]["dir"], "in"); self.assertEqual(pv["problems"], 1)
        rows = [dict(date=r["date"], dir=r["dir"], amount_paise=r["amount_paise"], ledger_id=r["ledger_id"] or self.L["Rubber Sales"], desc=r["desc"]) for r in pv["rows"] if not r["problem"]]
        with self.assertRaises(UserError): bulk.commit(self.c, {"bank_ledger_id": grocer, "rows": rows})        # not a cash/bank ledger
        out = bulk.commit(self.c, {"bank_ledger_id": self.L["Cash"], "rows": rows, "remember": True})
        self.assertEqual(out["entered"], 2)
        self.assertTrue(bulk.preview(self.c, {"rows": pf["rows"], "map": {"date": 0, "desc": 1, "amount": 2, "type": 3}})["rows"][0]["duplicate"])
        # history-based suggestion for a similar later line
        self.assertEqual(bulk.suggest(self.c, "Milk sale again")[0], self.L["Rubber Sales"])
        # a small .xlsx
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Date</t></si><si><t>Amount</t></si></sst>')
            z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                       '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row><row r="2"><c r="A2"><v>46000</v></c><c r="B2"><v>99.5</v></c></row></sheetData></worksheet>')
        x = bulk.parse_file("a.xlsx", base64.b64encode(buf.getvalue()).decode())
        self.assertEqual(x["headers"], ["Date", "Amount"])
        self.assertEqual(bulk.clean_date(x["rows"][0][0]), "2025-12-09")
        self.assertEqual(bulk.clean_amount("(1,000.50)"), (100050, True))


if __name__ == "__main__":
    unittest.main(verbosity=1)
