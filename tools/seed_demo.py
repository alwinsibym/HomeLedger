"""Fill a database with realistic sample entries (for testing and screenshots only)."""
import datetime as dt, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from homeledger import db, service as sv, config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tests'))
import fixtures

def main():
    db.init_database(config.db_path())
    c = db.connect(config.db_path())
    fixtures.install(c)
    m = sv.list_masters(c, "2026-11-19")
    L = {l["name"]: l["id"] for l in m["ledgers"]}
    sv.set_openings(c, [
        {"ledger_id": L["Cash"], "amount": "25000", "type": "Dr"},
        {"ledger_id": L["Bank Account"], "amount": "180000", "type": "Dr"},
        {"ledger_id": L["Farm Land"], "amount": "2500000", "type": "Dr"},
        {"ledger_id": L["House & Property"], "amount": "3500000", "type": "Dr"},
        {"ledger_id": L["Bank Loan"], "amount": "400000", "type": "Cr"},
        {"ledger_id": L["Capital Account"], "amount": "5805000", "type": "Cr"}])
    rnd = random.Random(7)
    def pay(date, ledger, amt, item=None, qty=None, unit=None, acct="Cash", note=""):
        sv.save_voucher(c, {"vtype": "Payment", "date": date, "narration": note, "lines": [
            {"ledger_id": L[ledger], "side": "Dr", "amount": str(amt), "item": item or "", "qty": qty or "", "unit": unit or ""},
            {"ledger_id": L[acct], "side": "Cr", "amount": str(amt)}]})
    def rec(date, ledger, amt, item=None, qty=None, unit=None, acct="Bank Account", note=""):
        sv.save_voucher(c, {"vtype": "Receipt", "date": date, "narration": note, "lines": [
            {"ledger_id": L[ledger], "side": "Cr", "amount": str(amt), "item": item or "", "qty": qty or "", "unit": unit or ""},
            {"ledger_id": L[acct], "side": "Dr", "amount": str(amt)}]})
    d0 = dt.date(2025, 12, 1)
    end = dt.date(2026, 11, 18)
    d = d0
    while d <= end:
        iso = d.isoformat()
        if d.day in (1, 15): pay(iso, "Groceries & Provisions", rnd.randint(2500, 4200), "Rice", rnd.choice(["25","30"]), "kg")
        if d.day % 3 == 0: pay(iso, "Vegetables & Fruits", rnd.randint(180, 520))
        if d.day == 5: pay(iso, "Electricity Bill (House)", rnd.randint(900, 1900), acct="Bank Account")
        if d.day == 9: pay(iso, "Phone & Internet", 799, acct="Bank Account")
        if d.day == 12: pay(iso, "Gas Cylinder (LPG)", 1050)
        if d.day == 20: pay(iso, "Medical & Medicines", rnd.randint(300, 2600))
        if d.day in (7, 21): pay(iso, "Cattle Feed", rnd.randint(1400, 2100), "Cattle feed", rnd.choice(["2","3"]), "bag")
        if d.day in (10,): pay(iso, "Goat Feed", rnd.randint(600, 900), "Goat feed", "1", "bag")
        if d.day in (4, 18, 26): pay(iso, "Labour Wages", rnd.choice([1800, 2400, 3000]), note="Weeding / tapping labour")
        if d.day == 14 and d.month in (1, 5, 8, 11): pay(iso, "Fertilizer & Manure", rnd.randint(2800, 5200), "Urea", rnd.choice(["25","50"]), "kg")
        if d.day == 22 and d.month in (3, 6, 9): pay(iso, "Pesticides & Crop Protection", rnd.randint(900, 2200))
        if d.day == 28: pay(iso, "Rubber Tapping & Processing", rnd.randint(1500, 2600))
        if d.day == 11 and d.month in (4, 10): pay(iso, "Veterinary & Medicines", rnd.randint(800, 2500))
        if d.day == 2: pay(iso, "Vehicle Fuel (Household)", rnd.randint(1500, 2500))
        if d.day == 3 and d.month in (6, 7): pay(iso, "Education & Fees", rnd.randint(8000, 15000), acct="Bank Account")
        if d.day == 24 and d.month in (4, 12): pay(iso, "Festivals & Functions", rnd.randint(6000, 14000))
        if d.day == 16: pay(iso, "Dog Expenses", rnd.randint(500, 1100), "Dog food", "5", "kg")
        if d.day in (1, 16):
            sv.save_voucher(c, {"vtype": "Contra", "date": iso, "narration": "Cash withdrawn", "lines": [
                {"ledger_id": L["Cash"], "side": "Dr", "amount": "22000"}, {"ledger_id": L["Bank Account"], "side": "Cr", "amount": "22000"}]})
        # income
        if d.day == 1: rec(iso, "Salary / Pension", 22000, note="Monthly pension")
        if d.day == 25 and d.month not in (6,7): rec(iso, "Rubber Sales", rnd.randint(18000, 34000), "Rubber sheet", str(rnd.randint(110, 190)), "kg", note="Sold to dealer")
        if d.day == 13: rec(iso, "Milk Sales", rnd.randint(4000, 6500), "Milk", str(rnd.randint(180, 260)), "litre")
        if d.day == 8 and d.month in (1, 2, 3, 12): rec(iso, "Pepper Sales", rnd.randint(6000, 14000), "Black pepper", str(rnd.randint(12, 25)), "kg")
        if d.day == 17 and d.month in (5, 6, 7): rec(iso, "Fruit Sales", rnd.randint(2000, 5000), "Mango", str(rnd.randint(40, 90)), "kg")
        d += dt.timedelta(days=1)
    # loan EMI split, cash withdrawal, a sale of a goat, borrowed money
    sv.save_voucher(c, {"vtype": "Contra", "date": "2026-11-02", "narration": "Cash withdrawn", "lines": [
        {"ledger_id": L["Cash"], "side": "Dr", "amount": "20000"}, {"ledger_id": L["Bank Account"], "side": "Cr", "amount": "20000"}]})
    sv.save_voucher(c, {"vtype": "Payment", "date": "2026-11-05", "narration": "Loan EMI", "lines": [
        {"ledger_id": L["Bank Loan"], "side": "Dr", "amount": "8000"}, {"ledger_id": L["Loan Interest Paid"], "side": "Dr", "amount": "1500"},
        {"ledger_id": L["Bank Account"], "side": "Cr", "amount": "9500"}]})
    rec("2026-10-09", "Goat Sales", 14000, "Goat (GOAT-004)", "1", "nos", note="Sold male goat")
    print("seeded", c.execute("select count(*) from vouchers").fetchone()[0], "vouchers")
main()
