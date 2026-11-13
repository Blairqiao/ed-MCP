from datetime import UTC, datetime

from ed_mcp.importance import AlertRules
from ed_mcp.state import StateStore


def alert(thread_id, detected_at, important=True):
    return {
        "course_id": 1,
        "course_code": "ABC",
        "thread_id": thread_id,
        "number": thread_id,
        "title": "Title",
        "type": "post",
        "category": None,
        "author": "A",
        "author_role": None,
        "url": "url",
        "snippet": "body",
        "score": 3,
        "reasons": ["reason"],
        "important": important,
        "thread_created_at": detected_at,
        "detected_at": detected_at,
    }


def test_cursors_and_rules(tmp_path):
    store = StateStore(tmp_path / "nested" / "state.db")
    assert store.get_cursor(1) is None
    store.set_cursor(1, 42)
    store.set_cursor(2, 99)
    assert store.get_cursor(1) == 42
    store.reset_cursor(1)
    assert store.get_cursor(1) is None and store.get_cursor(2) == 99
    store.reset_cursor(None)
    assert store.get_cursor(2) is None
    rules = AlertRules(keywords=["lab"], threshold=9)
    store.save_rules(rules)
    assert store.get_rules() == rules
    store.close()


def test_alerts_filter_deduplicate_and_share(tmp_path):
    path = tmp_path / "state.db"
    first, second = StateStore(path), StateStore(path)
    old = alert(1, "2026-11-01T12:00:00+00:00")
    assert first.record_alert(old)
    assert not first.record_alert(old)
    assert first.record_alert(alert(2, "2026-11-02T12:00:00+00:00", False))
    assert first.record_alert(alert(3, "2026-11-03T07:00:00-05:00"))
    assert [a["thread_id"] for a in second.recent_alerts()] == [3, 1]
    assert [a["thread_id"] for a in second.recent_alerts(important_only=False, limit=2)] == [3, 2]
    since = datetime.fromisoformat("2026-11-03T13:00:00+01:00")
    found = second.recent_alerts(since=since, important_only=False)
    assert [a["thread_id"] for a in found] == [3]
    assert found[0]["detected_at"] == "2026-11-03T12:00:00+00:00"
    assert found[0]["reasons"] == ["reason"] and found[0]["important"] is True
    assert since.astimezone(UTC).hour == 12
    first.close()
    second.close()
