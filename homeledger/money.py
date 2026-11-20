"""Exact money / quantity handling. Money is stored as integer paise, quantities as integer thousandths."""
from __future__ import annotations

import datetime as _dt
from decimal import Decimal, InvalidOperation

import re

from .errors import UserError

_PLAIN = re.compile(r"^\d+(\.\d+)?$|^\.\d+$")   # digits with an optional decimal part; no exponents, signs or words


def _plain(s: str, label: str):
    if not _PLAIN.match(s):
        raise UserError(f"{label} '{s}' is not a valid number.")

MAX_PAISE = 10 ** 13  # 100 billion rupees: far beyond any real entry, catches typos


def parse_amount(value, field: str = "Amount") -> int:
    """Rupees (str/int) -> positive integer paise. Never uses floating point."""
    if value is None or isinstance(value, bool):
        raise UserError(f"{field} is missing.")
    if isinstance(value, float):
        value = repr(value)
    s = str(value).strip().replace(",", "").replace("₹", "").replace(" ", "")
    if not s:
        raise UserError(f"{field} is missing.")
    if s.startswith("-"):
        raise UserError(f"{field} must be more than zero.")
    _plain(s, field)
    d = Decimal(s)
    paise = d * 100
    if paise != paise.to_integral_value():
        raise UserError(f"{field} can have at most 2 digits after the decimal point.")
    paise = int(paise)
    if paise <= 0:
        raise UserError(f"{field} must be more than zero.")
    if paise > MAX_PAISE:
        raise UserError(f"{field} is too large. Please check the number.")
    return paise


def parse_opening(value) -> int:
    """Opening balance: zero allowed."""
    if value is None or str(value).strip() == "":
        return 0
    s = str(value).strip().replace(",", "").replace("₹", "").replace(" ", "")
    _plain(s, "Opening balance")
    d = Decimal(s)
    paise = d * 100
    if paise != paise.to_integral_value() or paise < 0 or paise > MAX_PAISE:
        raise UserError("Opening balance must be a positive number with at most 2 decimals.")
    return int(paise)


def parse_qty(value):
    """Quantity -> integer thousandths, or None when blank."""
    if value is None or str(value).strip() == "":
        return None
    s = str(value).strip().replace(",", "")
    _plain(s, "Quantity")
    d = Decimal(s)
    milli = d * 1000
    if milli != milli.to_integral_value():
        raise UserError("Quantity can have at most 3 digits after the decimal point.")
    milli = int(milli)
    if milli <= 0:
        raise UserError("Quantity must be more than zero.")
    if milli > 10 ** 12:
        raise UserError("Quantity is too large. Please check the number.")
    return milli


def parse_iso(value, field: str = "Date") -> str:
    """Validate YYYY-MM-DD and return it."""
    try:
        d = _dt.date.fromisoformat(str(value))
    except (ValueError, TypeError):
        raise UserError(f"{field} is not valid.")
    if not (1990 <= d.year <= 2100):
        raise UserError(f"{field} {d.isoformat()} looks wrong (year must be between 1990 and 2100).")
    return d.isoformat()


def fmt_inr(paise: int, decimals: int = 2) -> str:
    """Indian digit grouping, e.g. 1,23,456.00"""
    neg = paise < 0
    paise = abs(int(paise))
    rupees, ps = divmod(paise, 100)
    s = str(rupees)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    out = s + (f".{ps:02d}" if decimals else "")
    return ("-" if neg else "") + out


def fy_label(iso_date: str, fy_start_month: int) -> str:
    d = _dt.date.fromisoformat(iso_date)
    start = d.year if d.month >= fy_start_month else d.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def month_start(iso_date: str) -> str:
    return iso_date[:7] + "-01"


def add_months(year: int, month: int, n: int):
    idx = year * 12 + (month - 1) + n
    return idx // 12, idx % 12 + 1
