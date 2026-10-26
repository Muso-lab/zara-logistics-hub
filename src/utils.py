"""
Utility functions for European/Italian localization and operational cycle dates.
"""

from datetime import date, datetime, timedelta
from typing import Any, Tuple, Optional
import pandas as pd
import numpy as np


def get_cycle_date_range(cycle_type: str, ref_date: Optional[date] = None) -> Tuple[date, date]:
    """
    Computes default operational Extranet date range based on Zara logistics cycle:
    - 'LUN-MER': Consegna Mercoledì -> Spedizioni da Lunedì a Mercoledì della settimana.
    - 'GIOV-DOM': Consegna Sabato   -> Spedizioni da Giovedì a Domenica della settimana.
    """
    if ref_date is None:
        ref_date = date.today()
    elif isinstance(ref_date, datetime):
        ref_date = ref_date.date()

    # Monday of the current week (weekday() returns 0 for Monday, 6 for Sunday)
    monday = ref_date - timedelta(days=ref_date.weekday())

    if cycle_type == "LUN-MER":
        desde = monday
        hasta = monday + timedelta(days=2)  # Wednesday
    else:  # "GIOV-DOM"
        desde = monday + timedelta(days=3)  # Thursday
        hasta = monday + timedelta(days=6)  # Sunday

    return desde, hasta


def format_number_it(val: Any, decimals: int = 2, default: str = "-") -> str:
    """
    Formats numbers according to European / Italian convention:
    - Thousands separator: '.'
    - Decimal separator: ','
    Examples:
      10080 -> "10.080"
      1041.5 -> "1.041,50"
      0 -> "0"
    """
    if val is None or pd.isna(val) or val == "":
        return default

    try:
        fval = float(val)
    except (ValueError, TypeError):
        return str(val)

    if fval == 0.0:
        return "0" if decimals == 0 else f"0,{ '0' * decimals }"

    if decimals == 0 or (fval.is_integer() and decimals <= 0):
        return f"{int(round(fval)):,d}".replace(",", ".")
    else:
        formatted = f"{fval:,.{decimals}f}"
        return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def format_currency_it(val: Any) -> str:
    s = format_number_it(val, decimals=2)
    return f"{s} €" if s != "-" else "-"


def format_date_it(dt: Any) -> str:
    """
    Formats dates into Italian format DD/MM/YYYY.
    """
    if dt is None or pd.isna(dt):
        return ""
    if isinstance(dt, str):
        try:
            dt = datetime.strptime(dt[:10], "%Y-%m-%d").date()
        except Exception:
            return dt
    if isinstance(dt, (datetime, date)):
        return dt.strftime("%d/%m/%Y")
    return str(dt)


def parse_date_obj(val: Any, default: Optional[date] = None) -> date:
    """
    Safely parses strings, datetimes or dates into a datetime.date object.
    Supports YYYY-MM-DD, timestamps (YYYY-MM-DD HH:MM:SS), DD/MM/YYYY, etc.
    """
    fallback = default or (date.today() + timedelta(days=1))
    if val is None or pd.isna(val):
        return fallback
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if not s:
        return fallback
    if len(s) >= 10 and s[4] == '-' and s[7] == '-':
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except Exception:
            pass
    if len(s) >= 10 and s[2] == '/' and s[5] == '/':
        try:
            return datetime.strptime(s[:10], "%d/%m/%Y").date()
        except Exception:
            pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return fallback
