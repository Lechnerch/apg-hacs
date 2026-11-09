"""Interpretation of the APG Powermonitor data envelope.

The Powermonitor (Infografics) API returns a dataset as a list of flat row
dicts, e.g. for "renewable generation":

    {"Datum Lokalzeit": "08.11.2026", "Erzeugungstyp": "Wind",
     "Energieverbrauch [GWh]": 18.625, "KW": 45, "Energy Type": "Wind"}

Every dataset has the same anatomy:
  * a *date* column ("Datum Lokalzeit", dd.mm.yyyy),
  * a *week* column ("KW") that must be ignored — it is the calendar week,
    not a measurement,
  * exactly one *value* column whose header carries the unit
    ("... [GWh]", "... [%]", "Prozent", "MW", ...),
  * optionally one or more *category* columns (Erzeugungstyp/Typ/Land, plus an
    English duplicate like "Energy Type"/"Country").

This module finds those columns heuristically and derives a single headline
value for the sensor state, while keeping the full table in ``series``.
"""

from __future__ import annotations

from datetime import date
import re
from typing import Any

# Numeric columns that are dimensions, never measurements. Matched on a
# normalised (lower-cased, unit-stripped) header.
_DIMENSION_COLUMNS = {
    "kw",
    "woche",
    "week",
    "jahr",
    "year",
    "monat",
    "month",
    "tag",
    "day",
    "quartal",
    "quarter",
    "id",
}

_DATE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
_UNIT_BRACKET_RE = re.compile(r"\[([^\]]+)\]")
# Headers that are themselves a unit, or clearly a percentage.
_BARE_UNITS = {"mw", "gwh", "mwh", "kwh", "gw", "kw_leistung"}
_PERCENT_HEADERS = {"prozent", "percent", "anteil"}


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    match = _DATE_RE.match(value.strip())
    if not match:
        return None
    day, month, year = (int(g) for g in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _normalise(header: str) -> str:
    # Drop the bracketed unit and whitespace for name comparisons.
    return _UNIT_BRACKET_RE.sub("", header).strip().lower()


def _unit_from_header(header: str) -> str | None:
    bracket = _UNIT_BRACKET_RE.search(header)
    if bracket:
        return bracket.group(1).strip()
    norm = _normalise(header)
    if norm in _PERCENT_HEADERS:
        return "%"
    if norm in _BARE_UNITS:
        return header.strip()
    return None


def _columns(rows: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            for key in row:
                if key not in seen:
                    seen.append(key)
    return seen


def _is_numeric_column(rows: list[dict[str, Any]], column: str) -> bool:
    values = [row.get(column) for row in rows if isinstance(row, dict) and column in row]
    numbers = [v for v in values if _to_number(v) is not None]
    # A column is numeric if it has values and at least 60% parse as numbers.
    return bool(values) and len(numbers) >= max(1, int(0.6 * len(values)))


def _pick_value_column(rows: list[dict[str, Any]], columns: list[str]) -> str | None:
    candidates = [
        c
        for c in columns
        if _normalise(c) not in _DIMENSION_COLUMNS and _is_numeric_column(rows, c)
    ]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    # Prefer a column that declares a unit, then the one with the widest spread
    # (dimension-like counters tend to be near-constant).
    unit_cols = [c for c in candidates if _unit_from_header(c)]
    pool = unit_cols or candidates

    def spread(column: str) -> float:
        nums = [
            _to_number(row.get(column))
            for row in rows
            if isinstance(row, dict) and _to_number(row.get(column)) is not None
        ]
        return (max(nums) - min(nums)) if nums else 0.0

    return max(pool, key=spread)


def _pick_date_column(rows: list[dict[str, Any]], columns: list[str]) -> str | None:
    for column in columns:
        parsed = [
            _parse_date(row.get(column))
            for row in rows
            if isinstance(row, dict) and column in row
        ]
        if parsed and sum(p is not None for p in parsed) >= max(1, int(0.6 * len(parsed))):
            return column
    return None


def _pick_category_column(
    columns: list[str], value_column: str | None, date_column: str | None
) -> str | None:
    for column in columns:
        if column == value_column or column == date_column:
            continue
        if _normalise(column) in _DIMENSION_COLUMNS:
            continue
        # The first remaining (non-numeric) column is the primary dimension;
        # English duplicates such as "Energy Type"/"Country" come later.
        return column
    return None


def summarize(payload: Any) -> dict[str, Any]:
    """Derive the headline value and metadata from a Powermonitor dataset.

    Returns keys: value, unit, date, value_column, primary_category, mode,
    breakdown, point_count, series.
    """
    rows = payload if isinstance(payload, list) else _find_rows(payload)
    rows = [r for r in (rows or []) if isinstance(r, dict)]

    empty = {
        "value": None,
        "unit": None,
        "date": None,
        "value_column": None,
        "primary_category": None,
        "mode": None,
        "breakdown": None,
        "point_count": len(rows),
        "series": rows[-64:],
    }
    if not rows:
        return empty

    columns = _columns(rows)
    value_column = _pick_value_column(rows, columns)
    if value_column is None:
        return empty
    date_column = _pick_date_column(rows, columns)
    category_column = _pick_category_column(columns, value_column, date_column)
    unit = _unit_from_header(value_column)

    # Restrict to the most recent date present (if any).
    latest_date: date | None = None
    latest_label: str | None = None
    if date_column is not None:
        dated = [
            (_parse_date(r.get(date_column)), r)
            for r in rows
            if _parse_date(r.get(date_column)) is not None
        ]
        if dated:
            latest_date = max(d for d, _ in dated)
            latest_rows = [r for d, r in dated if d == latest_date]
            latest_label = next(
                (r.get(date_column) for r in latest_rows), None
            )
        else:
            latest_rows = rows
    else:
        latest_rows = rows

    values = [
        _to_number(r.get(value_column))
        for r in latest_rows
        if _to_number(r.get(value_column)) is not None
    ]
    if not values:
        return {**empty, "value_column": value_column, "unit": unit}

    # Percentage shares across several categories sum to 100, so the headline
    # is the primary (first) slice. Everything else is a total for the day.
    is_share = unit == "%" and len(latest_rows) > 1
    if is_share:
        value = values[0]
        mode = "share"
    else:
        value = sum(values)
        mode = "sum" if len(values) > 1 else "single"

    breakdown: dict[str, Any] | None = None
    primary_category: str | None = None
    if category_column is not None:
        breakdown = {}
        for row in latest_rows:
            number = _to_number(row.get(value_column))
            if number is None:
                continue
            key = str(row.get(category_column))
            breakdown[key] = round(number, 3)
        if breakdown:
            primary_category = next(iter(breakdown))

    return {
        "value": round(value, 2),
        "unit": unit,
        "date": latest_label,
        "value_column": value_column,
        "primary_category": primary_category,
        "mode": mode,
        "breakdown": breakdown,
        "point_count": len(rows),
        "series": rows[-64:],
    }


def _find_rows(payload: Any, depth: int = 0) -> list[Any] | None:
    """Locate the row list inside an envelope that wraps it in a dict."""
    if depth > 6:
        return None
    if isinstance(payload, list):
        return payload if payload and isinstance(payload[0], dict) else None
    if isinstance(payload, dict):
        for key in ("data", "rows", "values", "items", "records", "result"):
            if key in payload:
                found = _find_rows(payload[key], depth + 1)
                if found:
                    return found
        for value in payload.values():
            found = _find_rows(value, depth + 1)
            if found:
                return found
    return None
