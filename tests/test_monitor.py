import httpx
from conftest import call_tool, make_client, make_ctx
from mcp.server.fastmcp import FastMCP

from ed_mcp.monitor import check_new_posts
from ed_mcp.state import StateStore
from ed_mcp.tools.monitor_tools import register_monitor_tools


def thread(tid, **kwargs):
    return {
        "id": tid,
        "number": tid,
        "user_id": 3,
        "title": "Hello",
        "type": "post",
        "content": "<document><paragraph>Body</paragraph></document>",
        "created_at": f"2026-11-{tid:02d}T00:00:00+00:00",
        **kwargs,
    }


def router(data):
    def handler(req):
        if req.url.path == "/api/user":
            return httpx.Response(
                200,
                json={
                    "courses": [
                        {"course": {"id": i, "code": f"C{i}", "status": "active"}} for i in (1, 2)
                    ]
                },
            )
        cid = int(req.url.path.split("/")[3])
        if data.get(cid) == 500:
            return httpx.Response(500, json={"message": "failure"})
        return httpx.Response(
            200,
            json={
                "threads": data.get(cid, []),
                "users": [{"id": 3, "name": "A", "course_role": "staff"}],
            },
        )

    return handler


def test_baseline_backfill_new_and_dedupe(tmp_path):
    data = {1: [thread(3), thread(2), thread(1)]}
    client = make_client(router(data))
    store = StateStore(tmp_path / "s.db")
    result = check_new_posts(client, store, region="us", course_ids=[1])
    assert result.alerts == [] and store.get_cursor(1) == 3
    data[1] = [thread(3, is_pinned=True), thread(5), thread(4), thread(2)]
    result = check_new_posts(client, store, region="us", course_ids=[1])
    assert [a["thread_id"] for a in result.alerts] == [4, 5]
    assert result.alerts[0]["score"] == 3
    assert result.alerts[0]["snippet"] == "Body"
    assert result.alerts[0]["url"].endswith("/courses/1/discussion/4")
    assert not check_new_posts(client, store, region="us", course_ids=[1]).alerts
    store.reset_cursor(1)
    store2 = StateStore(tmp_path / "backfill.db")
    result = check_new_posts(client, store2, region="us", course_ids=[1], backfill=2)
    assert [a["thread_id"] for a in result.alerts] == [4, 5]


def test_errors_filter_and_unknown_course(tmp_path):
    data = {1: 500, 2: [thread(1)], 3: [thread(2)]}
    client = make_client(router(data))
    store = StateStore(tmp_path / "s.db")
    result = check_new_posts(client, store, region="us", backfill=1)
    assert result.errors[0]["course_id"] == 1
    assert [a["course_id"] for a in result.alerts] == [2]
    result = check_new_posts(client, store, region="us", course_ids=[3], backfill=1)
    assert result.alerts[0]["course_code"] is None


def test_tools(tmp_path):
    data = {1: [thread(1)]}
    ctx = make_ctx(router(data), tmp_path)
    mcp = FastMCP("test")
    register_monitor_tools(mcp, ctx)
    assert call_tool(mcp, "check_new_posts", course_id=1)["note"]
    data[1].insert(0, thread(2, is_anonymous=True))
    result = call_tool(mcp, "check_new_posts", course_id=1)
    assert result["new_post_count"] == 1 and result["alerts"] == []
    assert len(call_tool(mcp, "get_recent_alerts", since="1000d", important_only=False)) == 1
    rules = call_tool(mcp, "update_alert_rules", add_keywords=["lab"], remove_keywords=["EXAM"])
    assert "lab" in rules["keywords"] and "exam" not in rules["keywords"]
    assert call_tool(mcp, "reset_alert_cursor", course_id=1) == {"reset": 1}


def test_pinned_old_does_not_end_scan_and_auth_is_reported(tmp_path):
    data = {1: [thread(1, is_pinned=True), thread(6), *[thread(2) for _ in range(19)], thread(7)]}
    store = StateStore(tmp_path / "s.db")
    store.set_cursor(1, 5)
    result = check_new_posts(make_client(router(data)), store, region="us", course_ids=[1])
    assert [a["thread_id"] for a in result.alerts] == [6, 7]

    def handler(req):
        if req.url.path == "/api/user":
            return httpx.Response(
                200, json={"courses": [{"course": {"id": 1, "status": "active"}}]}
            )
        return httpx.Response(401, json={"code": "bad_token", "message": "bad token"})

    result = check_new_posts(make_client(handler), store, region="us")
    assert result.auth_failed and result.errors[0]["course_id"] == 1
    assert store.get_cursor(1) == 7


def test_pagination_failure_keeps_cursor(tmp_path):
    def handler(req):
        if req.url.path == "/api/user":
            return httpx.Response(
                200, json={"courses": [{"course": {"id": 1, "status": "active"}}]}
            )
        if req.url.params.get("offset") == "0":
            return httpx.Response(200, json={"threads": [thread(8) for _ in range(100)]})
        return httpx.Response(500, json={"message": "page failed"})

    store = StateStore(tmp_path / "s.db")
    store.set_cursor(1, 5)
    result = check_new_posts(make_client(handler), store, region="us")
    assert result.errors and not result.alerts and store.get_cursor(1) == 5
