"""One date format, validated once, for every route.

Five routes called `datetime.strptime(date, "%Y-%m-%d")` directly. A request with
`date=13-09-2026` or `date=garbage` raised ValueError inside the handler, which
surfaced as an unhandled 500 with a traceback in the server log -- a client
mistake reported as a server fault.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import HTTPException

DATE_FORMAT = "%Y-%m-%d"


def parse_iso_date(value: str) -> date:
    """Parse YYYY-MM-DD, rejecting anything else -- including impossible dates such
    as 2026-02-30, which match the pattern but are not on any calendar."""
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except (TypeError, ValueError):
        raise ValueError(f"date must be a real calendar date in YYYY-MM-DD format; got {value!r}") from None


def validate_iso_date(value: str | None) -> str | None:
    """Pydantic field validator: return the original string if it is a valid date."""
    if value is None:
        return value
    parse_iso_date(value)
    return value


def query_date_or_422(value: str) -> date:
    """For query parameters, where a raised ValueError would not become a 422."""
    try:
        return parse_iso_date(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
