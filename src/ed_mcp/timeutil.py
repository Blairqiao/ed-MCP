"""Parse user and Ed timestamps."""

import re
from datetime import UTC, datetime, timedelta


def parse_time(value: str, *, now: datetime | None = None) -> datetime:
    now = now if now is not None else datetime.now().astimezone()
    if now.tzinfo is None:
        now = now.astimezone()
    if value == "now":
        return now
    if match := re.fullmatch(r"(\d+)([mhdw])", value):
        amount = int(match.group(1))
        seconds = {"m": 60, "h": 3600, "d": 86400, "w": 604800}[match.group(2)]
        return now - timedelta(seconds=amount * seconds)
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(
            "Expected now, a relative time like 7d or 24h, or an ISO date/datetime"
        ) from None
    return result if result.tzinfo is not None else result.astimezone()


def parse_ed_time(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    return result if result.tzinfo is not None else result.replace(tzinfo=UTC)


def to_iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")
