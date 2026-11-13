from datetime import UTC, datetime, timedelta

import pytest

from ed_mcp.timeutil import parse_ed_time, parse_time, to_iso


def test_relative():
    now = datetime(2026, 11, 13, tzinfo=UTC)
    for value, delta in [
        ("7d", timedelta(days=7)),
        ("24h", timedelta(hours=24)),
        ("90m", timedelta(minutes=90)),
        ("2w", timedelta(weeks=2)),
    ]:
        assert parse_time(value, now=now) == now - delta
    assert parse_time("now", now=now) == now


def test_iso():
    assert parse_time("2026-11-01").hour == 0
    assert parse_time("2026-11-01").tzinfo is not None
    assert parse_time("2026-11-01T12:00:00").tzinfo is not None
    assert parse_time("2026-11-01T12:00:00+11:00").utcoffset() == timedelta(hours=11)
    assert parse_ed_time("2026-11-10T09:15:02.123456+11:00").utcoffset() == timedelta(hours=11)
    assert parse_ed_time("2026-11-10T09:15:02").tzinfo == UTC
    assert to_iso(datetime(2026, 1, 1, microsecond=12, tzinfo=UTC)) == "2026-01-01T00:00:00+00:00"
    with pytest.raises(ValueError, match="ISO"):
        parse_time("yesterday-ish")
