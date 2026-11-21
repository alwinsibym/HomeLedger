"""Inventory: stock masters, item lines inside vouchers, godowns, batches, price lists, bills of material and
stock valuation (weighted average, FIFO, LIFO, last purchase cost, standard cost)."""
from __future__ import annotations

import datetime as dt
import json

from . import db as dbm
from .errors import UserError
from .money import parse_amount, parse_iso, parse_qty

VALUATIONS = {"avg": "Average cost", "fifo": "FIFO (first in, first out)", "lifo": "LIFO (last in, first out)",
              "last": "Last purchase cost", "std": "Standard cost"}
# what each voucher type does to stock by default: (direction, kind)
DEFAULT_FLOW = {"Purchase": ("in", "normal"), "Receipt Note": ("in", "normal"), "Credit Note": ("in", "normal"),
                "Sales": ("out", "normal"), "Delivery Note": ("out", "normal"), "Debit Note": ("out", "normal"),
                "Sales Order": ("out", "order"), "Purchase Order": ("in", "order")}
ITEM_VTYPES = tuple(DEFAULT_FLOW) + ("Stock Journal", "Payment", "Receipt", "Journal")


def _txt(v, n, field):
    from .service import _txt as t
    return t(v, n, field)


# ----------------------------------------------------------------------------------------------- masters
def _simple_master(conn, table, d, label):
    name = _txt(d.get("name"), 60, label + " name")
    if not name:
        raise UserError(f"Please enter the {label.lower()} name.")
    parent = int(d.get("parent_id") or 0) or None
    mid = d.get("id")
    with dbm.write_tx(conn):
        dup = conn.execute(f"SELECT id FROM {table} WHERE name=? COLLATE NOCASE", (name,)).fetchone()
        if dup and dup["id"] != mid:
            raise UserError(f"A {label.lower()} named '{name}' already exists.")
        if parent and parent == mid:
            raise UserError("A group cannot be inside itself.")
        if mid:
            conn.execute(f"UPDATE {table} SET name=?, parent_id=? WHERE id=?", (name, parent, mid))
        else:
            mid = conn.execute(f"INSERT INTO {table}(name, parent_id) VALUES (?,?)", (name, parent)).lastrowid
        dbm.audit(conn, "save", table, mid, name)
    return {"id": mid}


def save_stock_group(conn, d): return _simple_master(conn, "stock_groups", d, "Stock group")
def save_category(conn, d): return _simple_master(conn, "stock_categories", d, "Stock category")
def save_godown(conn, d): return _simple_master(conn, "godowns", d, "Godown")


def delete_master(conn, table, mid):
    if table not in ("stock_groups", "stock_categories", "godowns"):
        raise UserError("Unknown list.")
    mid = int(mid or 0)
    with dbm.write_tx(conn):
        if table == "godowns":
            if mid == 1:
                raise UserError("The Main Location cannot be removed.")
            if conn.execute("SELECT 1 FROM voucher_items WHERE godown_id=? LIMIT 1", (mid,)).fetchone():
                raise UserError("This godown is used in vouchers, so it cannot be deleted.")
        if conn.execute(f"SELECT 1 FROM {table} WHERE parent_id=?", (mid,)).fetchone():
            raise UserError("It has others inside it. Move or delete those first.")
        col = {"stock_groups": "group_id", "stock_categories": "category_id"}.get(table)
        if col and conn.execute(f"SELECT 1 FROM stock_items WHERE {col}=? LIMIT 1", (mid,)).fetchone():
            raise UserError("Stock items still use it. Change those items first.")
        conn.execute(f"DELETE FROM {table} WHERE id=?", (mid,))
        dbm.audit(conn, "delete", table, mid, "")


def lists(conn) -> dict:
    q = lambda t: [dict(r) for r in conn.execute(f"SELECT id, name, parent_id FROM {t} ORDER BY name COLLATE NOCASE")]
    return {"groups": q("stock_groups"), "categories": q("stock_categories"), "godowns": q("godowns"), "valuations": VALUATIONS}


def list_items(conn) -> list:
    return [dict(r) for r in conn.execute(
        """SELECT id, name, unit, opening_qty_milli, opening_value_paise, group_id, category_id, valuation, std_rate_paise, track_batches
           FROM stock_items ORDER BY name COLLATE NOCASE""")]


def save_item(conn, d: dict) -> dict:
    sid = d.get("id")
    name = _txt(d.get("name"), 60, "Item name")
    if not name:
        raise UserError("Please enter the item name.")
    unit = _txt(d.get("unit"), 12, "Unit")
    qty = parse_qty(d.get("opening_qty")) if str(d.get("opening_qty") or "").strip() else 0
    val = parse_amount(d.get("opening_value")) if str(d.get("opening_value") or "").strip() else 0
    std = parse_amount(d.get("std_rate")) if str(d.get("std_rate") or "").strip() else 0
    if qty < 0 or val < 0:
        raise UserError("Opening quantity and value cannot be negative.")
    if val and not qty:
        raise UserError("An opening value needs an opening quantity.")
    valuation = d.get("valuation") or "avg"
    if valuation not in VALUATIONS:
        raise UserError("Choose a valuation method.")
    if valuation == "std" and not std:
        raise UserError("Standard cost valuation needs a standard rate.")
    gid = int(d.get("group_id") or 0) or None
    cid = int(d.get("category_id") or 0) or None
    for tbl, v in (("stock_groups", gid), ("stock_categories", cid)):
        if v and not conn.execute(f"SELECT 1 FROM {tbl} WHERE id=?", (v,)).fetchone():
            raise UserError("The chosen stock group or category no longer exists.")
    tb = 1 if d.get("track_batches") else 0
    with dbm.write_tx(conn):
        dup = conn.execute("SELECT id FROM stock_items WHERE name=? COLLATE NOCASE", (name,)).fetchone()
        if dup and dup["id"] != sid:
            raise UserError(f"A stock item named '{name}' already exists.")
        if sid:
            if not conn.execute("SELECT 1 FROM stock_items WHERE id=?", (sid,)).fetchone():
                raise UserError("That stock item no longer exists.")
            conn.execute("""UPDATE stock_items SET name=?, unit=?, opening_qty_milli=?, opening_value_paise=?, group_id=?, category_id=?,
                            valuation=?, std_rate_paise=?, track_batches=? WHERE id=?""",
                         (name, unit, qty, val, gid, cid, valuation, std, tb, sid))
            dbm.audit(conn, "alter", "stock_item", sid, name)
        else:
            sid = conn.execute("""INSERT INTO stock_items(name, unit, opening_qty_milli, opening_value_paise, group_id, category_id, valuation,
                                  std_rate_paise, track_batches, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                               (name, unit, qty, val, gid, cid, valuation, std, tb, dbm.now_iso())).lastrowid
            dbm.audit(conn, "create", "stock_item", sid, name)
    return {"id": sid}


# ----------------------------------------------------------------------------------------------- voucher lines
def get_voucher_items(conn, vid: int) -> list:
    return [dict(r) for r in conn.execute(
        """SELECT vi.id, vi.item_id, i.name AS item, i.unit, vi.godown_id, g.name AS godown, vi.dir, vi.kind, vi.batch, vi.expiry,
                  vi.qty_milli, vi.rate_paise, vi.amount_paise, vi.order_ref
           FROM voucher_items vi JOIN stock_items i ON i.id=vi.item_id JOIN godowns g ON g.id=vi.godown_id
           WHERE vi.voucher_id=? ORDER BY vi.line_no""", (vid,))]


def save_voucher_items(conn, vid: int, vtype: str, vdate: str, items) -> None:
    conn.execute("DELETE FROM voucher_items WHERE voucher_id=?", (vid,))
    if not items:
        if vtype in ("Stock Journal",):
            raise UserError("A Stock Journal needs at least one stock line.")
        return
    if vtype not in ITEM_VTYPES:
        raise UserError(f"Stock lines cannot be used in a {vtype}.")
    flow = DEFAULT_FLOW.get(vtype)
    for n, x in enumerate(items, 1):
        iid = int(x.get("item_id") or 0)
        it = conn.execute("SELECT id, name, track_batches FROM stock_items WHERE id=?", (iid,)).fetchone()
        if not it:
            raise UserError(f"Stock line {n}: please choose a stock item.")
        qty = parse_qty(x.get("qty"))
        if qty <= 0:
            raise UserError(f"Stock line {n}: please enter the quantity of {it['name']}.")
        rate = parse_amount(x.get("rate")) if str(x.get("rate") or "").strip() else 0
        amount = parse_amount(x.get("amount")) if str(x.get("amount") or "").strip() else round(qty * rate / 1000)
        gid = int(x.get("godown_id") or 1)
        if not conn.execute("SELECT 1 FROM godowns WHERE id=?", (gid,)).fetchone():
            raise UserError(f"Stock line {n}: the godown no longer exists.")
        batch = _txt(x.get("batch"), 30, "Batch")
        exp = parse_iso(x["expiry"], "Expiry date") if x.get("expiry") else None
        if it["track_batches"] and not batch and (flow or ("in", ""))[0] and vtype != "Stock Journal":
            raise UserError(f"Stock line {n}: {it['name']} is tracked by batch. Please enter the batch.")
        order_ref = _txt(x.get("order_ref"), 30, "Order reference")
        if vtype == "Stock Journal":
            kind = x.get("kind")
            if kind not in ("transfer", "consume", "produce"):
                raise UserError(f"Stock line {n}: choose Transfer, Consumed or Produced.")
            if kind == "transfer":
                to = int(x.get("godown_to_id") or 0)
                if not to or not conn.execute("SELECT 1 FROM godowns WHERE id=?", (to,)).fetchone():
                    raise UserError(f"Stock line {n}: choose the godown it moves to.")
                if to == gid:
                    raise UserError(f"Stock line {n}: the two godowns are the same.")
                for gd, di in ((gid, "out"), (to, "in")):
                    conn.execute("""INSERT INTO voucher_items(voucher_id, line_no, item_id, godown_id, dir, kind, batch, expiry, qty_milli, rate_paise, amount_paise, order_ref)
                                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (vid, n, iid, gd, di, "transfer", batch, exp, qty, rate, amount, ""))
                continue
            d = "out" if kind == "consume" else "in"
        else:
            d, kind = flow
        conn.execute("""INSERT INTO voucher_items(voucher_id, line_no, item_id, godown_id, dir, kind, batch, expiry, qty_milli, rate_paise, amount_paise, order_ref)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (vid, n, iid, gid, d, kind, batch, exp, qty, rate, amount, order_ref))


# ----------------------------------------------------------------------------------------------- price lists and BOM
def set_price(conn, d: dict) -> dict:
    level = _txt(d.get("level"), 30, "Price level") or "Standard"
    iid = int(d.get("item_id") or 0)
    if not conn.execute("SELECT 1 FROM stock_items WHERE id=?", (iid,)).fetchone():
        raise UserError("Choose a stock item.")
    frm = parse_iso(d.get("from_date"), "From date")
    rate = parse_amount(d.get("rate"), "Rate")
    with dbm.write_tx(conn):
        if rate == 0:
            conn.execute("DELETE FROM price_lists WHERE level=? AND item_id=? AND from_date=?", (level, iid, frm))
        else:
            conn.execute("INSERT INTO price_lists(level, item_id, from_date, rate_paise) VALUES (?,?,?,?) "
                         "ON CONFLICT(level, item_id, from_date) DO UPDATE SET rate_paise=excluded.rate_paise", (level, iid, frm, rate))
        dbm.audit(conn, "price", "stock_item", iid, f"{level} {frm} {rate}")
    return {"ok": True}


def list_prices(conn) -> list:
    return [dict(r) for r in conn.execute(
        """SELECT p.id, p.level, p.item_id, i.name AS item, i.unit, p.from_date, p.rate_paise FROM price_lists p JOIN stock_items i ON i.id=p.item_id
           ORDER BY p.level, i.name COLLATE NOCASE, p.from_date DESC""")]


def price_for(conn, item_id: int, level: str, on: str):
    r = conn.execute("SELECT rate_paise FROM price_lists WHERE item_id=? AND level=? AND from_date<=? ORDER BY from_date DESC LIMIT 1",
                     (item_id, level or "Standard", on)).fetchone()
    if r:
        return {"rate_paise": r[0], "source": "price list"}
    r = conn.execute("""SELECT vi.rate_paise FROM voucher_items vi JOIN vouchers v ON v.id=vi.voucher_id
                        WHERE vi.item_id=? AND vi.rate_paise>0 AND v.status<>'cancelled' ORDER BY v.vdate DESC, v.id DESC LIMIT 1""", (item_id,)).fetchone()
    return {"rate_paise": r[0] if r else 0, "source": "last used" if r else ""}


def save_bom(conn, d: dict) -> dict:
    pid = int(d.get("product_id") or 0)
    if not conn.execute("SELECT 1 FROM stock_items WHERE id=?", (pid,)).fetchone():
        raise UserError("Choose the finished product.")
    name = _txt(d.get("name"), 40, "BOM name") or "Standard"
    out_q = parse_qty(d.get("out_qty") or "1")
    if out_q <= 0:
        raise UserError("Enter how much one batch produces.")
    lines = d.get("lines") or []
    if not lines:
        raise UserError("Add at least one component.")
    with dbm.write_tx(conn):
        row = conn.execute("SELECT id FROM boms WHERE product_id=? AND name=? COLLATE NOCASE", (pid, name)).fetchone()
        if row:
            bid = row["id"]
            conn.execute("UPDATE boms SET out_qty_milli=? WHERE id=?", (out_q, bid))
            conn.execute("DELETE FROM bom_lines WHERE bom_id=?", (bid,))
        else:
            bid = conn.execute("INSERT INTO boms(product_id, name, out_qty_milli) VALUES (?,?,?)", (pid, name, out_q)).lastrowid
        for l in lines:
            iid = int(l.get("item_id") or 0)
            q = parse_qty(l.get("qty"))
            if not conn.execute("SELECT 1 FROM stock_items WHERE id=?", (iid,)).fetchone() or q <= 0:
                raise UserError("Each component needs an item and a quantity.")
            if iid == pid:
                raise UserError("The product cannot be made from itself.")
            conn.execute("INSERT INTO bom_lines(bom_id, item_id, qty_milli) VALUES (?,?,?)", (bid, iid, q))
        dbm.audit(conn, "save", "bom", bid, name)
    return {"id": bid}


def delete_bom(conn, bid: int) -> None:
    with dbm.write_tx(conn):
        conn.execute("DELETE FROM boms WHERE id=?", (int(bid or 0),))


def list_boms(conn) -> list:
    out = []
    for b in conn.execute("SELECT b.id, b.product_id, b.name, b.out_qty_milli, i.name AS product, i.unit FROM boms b JOIN stock_items i ON i.id=b.product_id ORDER BY i.name"):
        d = dict(b)
        d["lines"] = [dict(r) for r in conn.execute(
            "SELECT bl.item_id, bl.qty_milli, i.name AS item, i.unit FROM bom_lines bl JOIN stock_items i ON i.id=bl.item_id WHERE bl.bom_id=? ORDER BY bl.id", (b["id"],))]
        out.append(d)
    return out


# ----------------------------------------------------------------------------------------------- valuation engine
def _movements(conn, to: str) -> list:
    """Every stock movement up to 'to', oldest first. Each: dict(date, vid, order, key, dir, kind, qty, value, godown, batch, expiry)."""
    items = {}
    for r in conn.execute("SELECT id, name, unit, opening_qty_milli, opening_value_paise, valuation, std_rate_paise, group_id, category_id FROM stock_items"):
        items[r["name"].strip().lower()] = dict(r, master=True)
    movs = []

    def key_for(name, unit):
        k = name.strip().lower()
        if k not in items:
            items[k] = {"id": None, "name": name.strip(), "unit": unit or "", "opening_qty_milli": 0, "opening_value_paise": 0,
                        "valuation": "avg", "std_rate_paise": 0, "group_id": None, "category_id": None, "master": False}
        return k
    for k, it in list(items.items()):
        if it["opening_qty_milli"]:
            movs.append({"date": "0000-00-00", "vid": 0, "order": 0, "key": k, "dir": "in", "kind": "normal", "qty": it["opening_qty_milli"],
                         "value": it["opening_value_paise"], "godown": 1, "batch": "", "expiry": None})
    for r in conn.execute(
            """SELECT trim(e.item) AS item, COALESCE(e.unit,'') AS unit, v.vdate, v.id AS vid, e.debit_paise AS dr, e.credit_paise AS cr, e.qty_milli AS q
               FROM entries e JOIN vouchers v ON v.id=e.voucher_id AND v.status='posted' JOIN ledgers l ON l.id=e.ledger_id
               WHERE e.item IS NOT NULL AND trim(e.item)<>'' AND e.qty_milli>0 AND l.cb_kind IS NULL AND v.vdate<=?""", (to,)):
        k = key_for(r["item"], r["unit"])
        movs.append({"date": r["vdate"], "vid": r["vid"], "order": 1, "key": k, "dir": "in" if r["dr"] else "out", "kind": "normal", "qty": r["q"],
                     "value": r["dr"] if r["dr"] else r["cr"], "godown": 1, "batch": "", "expiry": None})
    for r in conn.execute(
            """SELECT i.name, i.unit, v.vdate, v.id AS vid, vi.dir, vi.kind, vi.qty_milli, vi.amount_paise, vi.godown_id, vi.batch, vi.expiry
               FROM voucher_items vi JOIN vouchers v ON v.id=vi.voucher_id AND v.status='posted' JOIN stock_items i ON i.id=vi.item_id
               WHERE vi.kind<>'order' AND v.vdate<=? ORDER BY v.vdate, v.id, vi.line_no""", (to,)):
        k = key_for(r["name"], r["unit"])
        movs.append({"date": r["vdate"], "vid": r["vid"], "order": {"consume": 0, "normal": 1, "transfer": 1, "produce": 2}[r["kind"]], "key": k,
                     "dir": r["dir"], "kind": r["kind"], "qty": r["qty_milli"], "value": r["amount_paise"], "godown": r["godown_id"],
                     "batch": r["batch"], "expiry": r["expiry"]})
    movs.sort(key=lambda m: (m["date"], m["vid"], m["order"]))
    return items, movs


def _simulate(items, movs, frm: str, made_out_q):
    st = {}
    for k, it in items.items():
        st[k] = {"it": it, "layers": [], "qty": 0, "val": 0, "last": 0, "op_q": 0, "op_v": 0, "in_q": 0, "in_v": 0, "out_q": 0, "out_v": 0, "snap": False}
    made = {}                                  # voucher id -> cost of what it consumed (spread over what it produced)

    def avg_rate(s):
        return s["val"] / s["qty"] if s["qty"] > 0 else 0

    def take(s, qty):
        """Cost of issuing qty under the item's valuation method; updates the running state."""
        m = s["it"]["valuation"]
        have = max(s["qty"], 0)
        real = min(qty, have)
        if m == "avg":
            cost = round(avg_rate(s) * real)
        elif m in ("fifo", "lifo"):
            cost, need = 0, real
            while need > 0 and s["layers"]:
                lay = s["layers"][0] if m == "fifo" else s["layers"][-1]
                use = min(need, lay[0])
                cost += round(lay[1] * use / lay[0]) if lay[0] else 0
                lay[1] -= round(lay[1] * use / lay[0]) if lay[0] else 0
                lay[0] -= use
                need -= use
                if lay[0] <= 0:
                    s["layers"].pop(0 if m == "fifo" else -1)
        elif m == "last":
            cost = round(s["last"] * real / 1000) if s["last"] else round(avg_rate(s) * real)
        else:
            cost = round(s["it"]["std_rate_paise"] * real / 1000)
        if m in ("avg", "last", "std"):
            s["val"] -= round(avg_rate(s) * real)
        else:
            s["val"] = sum(l[1] for l in s["layers"])
        s["qty"] -= qty
        if s["qty"] < 0:
            s["val"] = 0
        return cost

    def give(s, qty, value):
        s["qty"] += qty
        s["val"] += value
        s["layers"].append([qty, value])
        if qty:
            s["last"] = round(value * 1000 / qty)

    for m in movs:
        s = st[m["key"]]
        if m["kind"] == "transfer":
            continue
        before = m["date"] < frm
        if m["dir"] == "in":
            value = m["value"]
            if m["kind"] == "produce" and not value:
                tot = made.get(m["vid"], 0)
                value = round(tot * m["qty"] / made_out_q[m["vid"]]) if made_out_q.get(m["vid"]) else 0
            give(s, m["qty"], value)
            if before:
                s["op_q"] += m["qty"]; s["op_v"] += value
            else:
                s["in_q"] += m["qty"]; s["in_v"] += value
        else:
            cost = take(s, m["qty"])
            if m["kind"] == "consume":
                made[m["vid"]] = made.get(m["vid"], 0) + cost
            if before:
                s["op_q"] -= m["qty"]; s["op_v"] -= cost
            else:
                s["out_q"] += m["qty"]; s["out_v"] += cost
    return st


def summary(conn, frm: str, to: str) -> dict:
    items, movs = _movements(conn, to)
    made_out_q = {}
    for m in movs:
        if m["kind"] == "produce":
            made_out_q[m["vid"]] = made_out_q.get(m["vid"], 0) + m["qty"]
    # _simulate needs the produced totals before it starts
    st = _simulate(items, movs, frm, made_out_q)
    rows = []
    for k, s in st.items():
        it = s["it"]
        if not (s["op_q"] or s["in_q"] or s["out_q"] or s["qty"] or it["master"]):
            continue
        close_q = s["qty"]
        meth = it["valuation"]
        if close_q <= 0:
            close_v = 0
        elif meth == "avg":
            close_v = s["val"]
        elif meth in ("fifo", "lifo"):
            close_v = sum(l[1] for l in s["layers"])
        elif meth == "last":
            close_v = round(s["last"] * close_q / 1000) if s["last"] else s["val"]
        else:
            close_v = round(it["std_rate_paise"] * close_q / 1000)
        rows.append({"item_id": it["id"], "name": it["name"], "unit": it["unit"], "valuation": meth, "master": it["master"],
                     "group_id": it["group_id"], "category_id": it["category_id"],
                     "op_q": s["op_q"], "op_v": max(s["op_v"], 0) if s["op_q"] > 0 else 0, "in_q": s["in_q"], "in_v": s["in_v"],
                     "out_q": s["out_q"], "out_v": s["out_v"], "close_q": close_q, "close_v": close_v})
    rows.sort(key=lambda x: x["name"].lower())
    return rows


def godown_summary(conn, to: str) -> list:
    """Quantity of each item in each godown (transfers included), valued at the item's closing rate."""
    items, movs = _movements(conn, to)
    names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM godowns")}
    q = {}
    for m in movs:
        k = (m["key"], m["godown"])
        q[k] = q.get(k, 0) + (m["qty"] if m["dir"] == "in" else -m["qty"])
    rate = {r["name"].strip().lower(): (r["close_v"] / r["close_q"] if r["close_q"] > 0 else 0) for r in summary(conn, "0000-00-00", to)}
    out = []
    for (k, g), qty in q.items():
        if qty == 0:
            continue
        out.append({"item": items[k]["name"], "unit": items[k]["unit"], "godown_id": g, "godown": names.get(g, "?"), "qty": qty,
                    "value": round(rate.get(k, 0) * qty) if qty > 0 else 0})
    out.sort(key=lambda x: (x["godown"].lower(), x["item"].lower()))
    return out


def batch_summary(conn, to: str, today: str) -> list:
    """Stock by batch with expiry, soonest expiry first."""
    t = dt.date.fromisoformat(today)
    b = {}
    for r in conn.execute(
            """SELECT i.name, i.unit, vi.batch, vi.dir, vi.kind, vi.qty_milli, vi.expiry, vi.godown_id
               FROM voucher_items vi JOIN vouchers v ON v.id=vi.voucher_id AND v.status='posted' JOIN stock_items i ON i.id=vi.item_id
               WHERE vi.batch<>'' AND vi.kind<>'order' AND v.vdate<=?""", (to,)):
        x = b.setdefault((r["name"], r["batch"]), {"item": r["name"], "unit": r["unit"], "batch": r["batch"], "qty": 0, "expiry": None})
        x["qty"] += r["qty_milli"] if r["dir"] == "in" else -r["qty_milli"]
        if r["expiry"] and (not x["expiry"] or r["expiry"] < x["expiry"]):
            x["expiry"] = r["expiry"]
    out = []
    for x in b.values():
        if x["qty"] == 0:
            continue
        x["days_left"] = (dt.date.fromisoformat(x["expiry"]) - t).days if x["expiry"] else None
        out.append(x)
    out.sort(key=lambda x: (x["expiry"] is None, x["expiry"] or "", x["item"].lower()))
    return out


def pending_orders(conn) -> list:
    """Orders (sales and purchase) with what is still to be delivered or received."""
    out = []
    for o in conn.execute(
            """SELECT v.id, v.vtype, v.number, v.vdate, v.status, vi.item_id, i.name AS item, i.unit, vi.qty_milli, vi.dir, vi.rate_paise
               FROM voucher_items vi JOIN vouchers v ON v.id=vi.voucher_id JOIN stock_items i ON i.id=vi.item_id
               WHERE vi.kind='order' AND v.status<>'cancelled' ORDER BY v.vdate, v.id, vi.line_no"""):
        done = conn.execute(
            """SELECT COALESCE(SUM(vi.qty_milli),0) FROM voucher_items vi JOIN vouchers v ON v.id=vi.voucher_id AND v.status='posted'
               WHERE vi.kind='normal' AND vi.item_id=? AND vi.dir=? AND lower(vi.order_ref)=lower(?)""", (o["item_id"], o["dir"], str(o["number"]))).fetchone()[0]
        pend = o["qty_milli"] - done
        if pend > 0:
            out.append({"voucher_id": o["id"], "vtype": o["vtype"], "order_no": str(o["number"]), "date": o["vdate"], "item": o["item"], "unit": o["unit"],
                        "ordered": o["qty_milli"], "done": done, "pending": pend})
    return out
