"""Best-effort interpretation of the APG Powermonitor data envelope.

The Powermonitor (Infografics) API returns tabular data in a "standard
envelope". Its exact shape is not documented in the public Swagger spec, so
this module stays deliberately defensive: it walks the payload, finds the most
likely data rows, and derives a latest numeric value plus the raw series. If it
cannot make sense of the payload, it degrades gracefully and keeps the raw
structure available as attributes so users can refine templates themselves.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# Keys that commonly hold the row collection in tabular envelopes.
_ROW_CONTAINER_KEYS = ("rows", "data", "values", "series", "items", "records")
# Keys that commonly hold a numeric measurement inside a row.
_VALUE_KEYS = ("value", "y", "val", "amount", "v", "count")
# Keys that commonly hold a timestamp/label inside a row.
_TIME_KEYS = ("timestamp", "time", "date", "datetime", "utc", "x", "label", "t")
# Keys that commonly hold a unit of measurement.
_UNIT_KEYS = ("unit", "uom", "units", "measure")


def _find_rows(payload: Any, depth: int = 0) -> list[Any] | None:
    """Return the most promising list of rows found within *payload*."""
    if depth > 6:
        return None
    if isinstance(payload, list):
        # A list of dicts or list of lists is very likely the data itself.
        if payload and isinstance(payload[0], (dict, list)):
            return payload
        return None
    if isinstance(payload, dict):
        # Prefer the well-known container keys, in order.
        for key in _ROW_CONTAINER_KEYS:
            if key in payload:
                found = _find_rows(payload[key], depth + 1)
                if found:
                    return found
        # Fall back to scanning every value.
        for value in payload.values():
            found = _find_rows(value, depth + 1)
            if found:
                return found
    return None


def _first_key(row: dict[str, Any], candidates: tuple[str, ...]) -> str | None:
    lowered = {k.lower(): k for k in row}
    for cand in candidates:
        if cand in lowered:
            return lowered[cand]
    return None


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _row_value(row: Any) -> float | None:
    """Extract a numeric value from a single row (dict or list)."""
    if isinstance(row, dict):
        key = _first_key(row, _VALUE_KEYS)
        if key is not None:
            return _to_number(row[key])
        # No obvious value key: take the last numeric field.
        numbers = [n for n in (_to_number(v) for v in row.values()) if n is not None]
        return numbers[-1] if numbers else None
    if isinstance(row, (list, tuple)):
        numbers = [n for n in (_to_number(v) for v in row) if n is not None]
        return numbers[-1] if numbers else None
    return _to_number(row)


def _row_time(row: Any) -> str | None:
    if isinstance(row, dict):
        key = _first_key(row, _TIME_KEYS)
        if key is not None and row[key] is not None:
            return str(row[key])
    return None


def _find_unit(payload: Any, depth: int = 0) -> str | None:
    if depth > 4 or not isinstance(payload, dict):
        return None
    key = _first_key(payload, _UNIT_KEYS)
    if key is not None and isinstance(payload[key], str):
        return payload[key]
    for value in payload.values():
        unit = _find_unit(value, depth + 1)
        if unit:
            return unit
    return None


def summarize(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a summary dict used by the Powermonitor sensors.

    Keys:
        latest_value: last numeric value in the series, or ``None``
        latest_label: label/timestamp of that last point, or ``None``
        unit: detected unit of measurement, or ``None``
        point_count: number of rows found
        series: the raw rows (capped) for use as an attribute
    """
    rows = _find_rows(payload) or []
    latest_value: float | None = None
    latest_label: str | None = None
    for row in rows:
        value = _row_value(row)
        if value is not None:
            latest_value = value
            latest_label = _row_time(row)

    return {
        "latest_value": latest_value,
        "latest_label": latest_label,
        "unit": _find_unit(payload),
        "point_count": len(rows),
        "series": rows[-48:],  # cap to keep the attribute reasonable
    }


def default_label(payload: dict[str, Any]) -> str | None:
    """Try to read a human readable title from the envelope."""
    for key in ("title", "name", "label", "slug"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    meta = payload.get("meta")
    if isinstance(meta, dict):
        return default_label(meta)
    return None
