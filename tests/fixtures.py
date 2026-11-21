"""Sample household + farm chart of accounts, used ONLY by the automated tests and the demo-data tool.
HomeLedger itself starts like Tally: just Cash, Tally's standard groups, and no cost centres."""
from homeledger import db as dbm

EXTRA_GROUPS = [('LIVESTOCK', 'Livestock', 'FIXED', 'asset'),
 ('FARM_EXP', 'Farm Expenses', 'DIRECT_EXP', 'expense'),
 ('HOUSE_EXP', 'Household Expenses', 'INDIRECT_EXP', 'expense')]
COST_CENTRES = [('Household', None, 'household'),
 ('Dog', 'Household', 'household'),
 ('Farm', None, 'farm'),
 ('Rubber', 'Farm', 'farm'),
 ('Cattle', 'Farm', 'farm'),
 ('Goats', 'Farm', 'farm'),
 ('Coffee', 'Farm', 'farm'),
 ('Cocoa', 'Farm', 'farm'),
 ('Black Pepper', 'Farm', 'farm'),
 ('Nutmeg', 'Farm', 'farm'),
 ('Banana', 'Farm', 'farm'),
 ('Mango', 'Farm', 'farm'),
 ('Jackfruit', 'Farm', 'farm'),
 ('Guava', 'Farm', 'farm'),
 ('Rambutan', 'Farm', 'farm'),
 ('Other Fruits', 'Farm', 'farm'),
 ('Timber Trees', 'Farm', 'farm')]
LEDGERS = [('Cash', 'CASH', None),
 ('Bank Account', 'BANK', None),
 ('Groceries & Provisions', 'HOUSE_EXP', 'Household'),
 ('Vegetables & Fruits', 'HOUSE_EXP', 'Household'),
 ('Milk & Dairy', 'HOUSE_EXP', 'Household'),
 ('Meat & Fish', 'HOUSE_EXP', 'Household'),
 ('Electricity Bill (House)', 'HOUSE_EXP', 'Household'),
 ('Water Bill', 'HOUSE_EXP', 'Household'),
 ('Gas Cylinder (LPG)', 'HOUSE_EXP', 'Household'),
 ('Phone & Internet', 'HOUSE_EXP', 'Household'),
 ('Vehicle Fuel (Household)', 'HOUSE_EXP', 'Household'),
 ('Vehicle Repairs & Service', 'HOUSE_EXP', 'Household'),
 ('Medical & Medicines', 'HOUSE_EXP', 'Household'),
 ('Education & Fees', 'HOUSE_EXP', 'Household'),
 ('Clothing & Footwear', 'HOUSE_EXP', 'Household'),
 ('House Repairs & Maintenance', 'HOUSE_EXP', 'Household'),
 ('Festivals & Functions', 'HOUSE_EXP', 'Household'),
 ('Travel', 'HOUSE_EXP', 'Household'),
 ('Gifts & Donations', 'HOUSE_EXP', 'Household'),
 ('Insurance Premiums', 'HOUSE_EXP', 'Household'),
 ('Entertainment', 'HOUSE_EXP', 'Household'),
 ('Domestic Help', 'HOUSE_EXP', 'Household'),
 ('Taxes & Government Fees', 'HOUSE_EXP', 'Household'),
 ('Loan Interest Paid', 'HOUSE_EXP', 'Household'),
 ('Dog Expenses', 'HOUSE_EXP', 'Dog'),
 ('Household Miscellaneous', 'HOUSE_EXP', 'Household'),
 ('Labour Wages', 'FARM_EXP', 'Farm'),
 ('Fertilizer & Manure', 'FARM_EXP', 'Farm'),
 ('Pesticides & Crop Protection', 'FARM_EXP', 'Farm'),
 ('Seeds & Saplings', 'FARM_EXP', 'Farm'),
 ('Cattle Feed', 'FARM_EXP', 'Cattle'),
 ('Goat Feed', 'FARM_EXP', 'Goats'),
 ('Veterinary & Medicines', 'FARM_EXP', 'Farm'),
 ('Farm Tools (Small)', 'FARM_EXP', 'Farm'),
 ('Farm Fuel', 'FARM_EXP', 'Farm'),
 ('Farm Electricity', 'FARM_EXP', 'Farm'),
 ('Irrigation & Pump Repairs', 'FARM_EXP', 'Farm'),
 ('Farm Repairs & Maintenance', 'FARM_EXP', 'Farm'),
 ('Fencing', 'FARM_EXP', 'Farm'),
 ('Transport & Freight', 'FARM_EXP', 'Farm'),
 ('Rubber Tapping & Processing', 'FARM_EXP', 'Rubber'),
 ('Farm Miscellaneous', 'FARM_EXP', 'Farm'),
 ('Rubber Sales', 'SALES', 'Rubber'),
 ('Coffee Sales', 'SALES', 'Coffee'),
 ('Cocoa Sales', 'SALES', 'Cocoa'),
 ('Pepper Sales', 'SALES', 'Black Pepper'),
 ('Nutmeg Sales', 'SALES', 'Nutmeg'),
 ('Fruit Sales', 'SALES', 'Other Fruits'),
 ('Milk Sales', 'SALES', 'Cattle'),
 ('Cattle Sales', 'SALES', 'Cattle'),
 ('Goat Sales', 'SALES', 'Goats'),
 ('Timber Sales', 'SALES', 'Timber Trees'),
 ('Other Farm Sales', 'SALES', 'Farm'),
 ('Salary / Pension', 'INDIRECT_INC', 'Household'),
 ('Interest Received', 'INDIRECT_INC', 'Household'),
 ('Rent Received', 'INDIRECT_INC', 'Household'),
 ('Gifts Received', 'INDIRECT_INC', 'Household'),
 ('Other Income', 'INDIRECT_INC', 'Household'),
 ('House & Property', 'FIXED', None),
 ('Farm Land', 'FIXED', 'Farm'),
 ('Vehicles', 'FIXED', None),
 ('Farm Equipment & Machinery', 'FIXED', 'Farm'),
 ('Cattle Stock', 'LIVESTOCK', 'Cattle'),
 ('Goat Stock', 'LIVESTOCK', 'Goats'),
 ('Fixed Deposits', 'INVEST', None),
 ('Chit Funds & Savings Schemes', 'INVEST', None),
 ('Gold & Jewellery', 'INVEST', None),
 ('Advances Paid', 'LOANS_ADV', None),
 ('Deposits (Electricity, Gas etc.)', 'DEPOSITS', None),
 ('Capital Account', 'CAPITAL', None),
 ('Bank Loan', 'LOANS_LIAB', None),
 ('Money Borrowed', 'LOANS_LIAB', None)]


def install(conn):
    """Add the sample groups, cost centres and ledgers to a fresh book."""
    ids = {r["code"]: r["id"] for r in conn.execute("SELECT id, code FROM acct_groups WHERE code IS NOT NULL")}
    nature = {r["code"]: r["nature"] for r in conn.execute("SELECT code, nature FROM acct_groups WHERE code IS NOT NULL")}
    ts = dbm.now_iso()
    conn.execute("BEGIN IMMEDIATE")
    for code, name, parent, nat in EXTRA_GROUPS:
        cur = conn.execute("INSERT INTO acct_groups(code, name, parent_id, nature, is_system, sort) VALUES (?,?,?,?,1,500)", (code, name, ids.get(parent), nat))
        ids[code] = cur.lastrowid; nature[code] = nat
    cc = {}
    for name, parent, kind in COST_CENTRES:
        cur = conn.execute("INSERT INTO cost_centres(name, parent_id, kind, sort) VALUES (?,?,?,0)", (name, cc.get(parent), kind))
        cc[name] = cur.lastrowid
    have = {r[0].lower() for r in conn.execute("SELECT name FROM ledgers")}
    for name, gcode, cname in LEDGERS:
        if name.lower() in have:
            continue
        cb = "cash" if gcode == "CASH" else "bank" if gcode == "BANK" else None
        conn.execute("INSERT INTO ledgers(name, group_id, nature, cb_kind, opening_type, default_cc_id, created_at) VALUES (?,?,?,?,?,?,?)",
                     (name, ids[gcode], nature[gcode], cb, "Cr" if nature[gcode] == "liability" else "Dr", cc.get(cname), ts))
    conn.execute("COMMIT")
