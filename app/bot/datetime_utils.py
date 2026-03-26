from __future__ import annotations

from datetime import datetime, timezone


def _parse_canvas_datetime(value: str | None) -> datetime | None:
    """Parse a Canvas ISO8601 datetime string into an aware datetime.

    Returns None if the value is missing or cannot be parsed.
    """

    if not value:
        return None

    try:
        if value.endswith("Z"):
            dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc,
            )
        else:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return None


def _format_canvas_datetime(value: str | None) -> str | None:
    """Format a Canvas ISO8601 datetime into a readable string.

    Example input: "2026-02-23T16:59:59Z"
    Output: "February 23, 2026 04:59 PM" (UTC)
    """

    dt = _parse_canvas_datetime(value)
    if dt is None:
        return value

    # Format in 12-hour clock with AM/PM, e.g. "March 20, 2026 01:30 PM"
    return dt.strftime("%B %-d, %Y %I:%M %p")


def _format_due_with_relative(value: str | None) -> str | None:
    """Format due date with absolute time plus relative day offset.

    Examples:
    - "February 23, 2026 04:59 PM (3 days ago)"
    - "March 1, 2026 11:59 PM (2 days ahead)"
    - "March 5, 2026 09:00 AM (today)"
    """

    dt = _parse_canvas_datetime(value)
    if dt is None:
        return value

    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Phnom_Penh")
    except ImportError:
        # Python <3.9 fallback (not expected in this project)
        tz = timezone.utc

    dt_local = dt.astimezone(tz)
    pretty = dt_local.strftime("%B %-d, %Y %I:%M %p")

    today_local = datetime.now(tz).date()
    due_date = dt_local.date()
    delta_days = (due_date - today_local).days

    if delta_days == 0:
        suffix = "(today)"
    elif delta_days < 0:
        days = abs(delta_days)
        suffix = f"({days} day ago)" if days == 1 else f"({days} days ago)"
    else:
        days = delta_days
        suffix = f"({days} day ahead)" if days == 1 else f"({days} days ahead)"

    return f"{pretty} {suffix}"
