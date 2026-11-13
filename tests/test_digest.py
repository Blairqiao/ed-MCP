import asyncio
from datetime import UTC, datetime

import httpx
import pytest
from conftest import call_tool, make_client, make_ctx
from mcp.server.fastmcp import FastMCP

from ed_mcp.digest import collect_posts, format_digest
from ed_mcp.tools.digest_tools import register_digest_tools

START = datetime(2026, 11, 1, tzinfo=UTC)
END = datetime(2026, 11, 5, tzinfo=UTC)


def thread(ident, date, **kwargs):
    return {
        "id": ident,
        "number": ident,
        "course_id": 1,
        "created_at": date,
        "title": f"Thread {ident}",
        "type": "question",
        "category": "General",
        "content": "<document><paragraph>Body</paragraph></document>",
        "user_id": 1,
        "reply_count": 1,
        "vote_count": 0,
        **kwargs,
    }


def test_collect_posts():
    requests = []
    items = [
        thread(99, "2026-10-01T00:00:00+00:00", is_pinned=True),
        thread(98, "2026-11-05T00:00:00+00:00"),
        thread(3, "2026-11-04T00:00:00+00:00"),
        thread(2, "2026-11-03T00:00:00+00:00"),
        thread(1, "2026-11-02T00:00:00+00:00"),
    ]
    items += [thread(100 + i, "2026-10-01T00:00:00+00:00") for i in range(110)]

    def handler(req):
        requests.append(req.url.path)
        if req.url.path == "/api/courses/1/threads":
            offset = int(req.url.params["offset"])
            return httpx.Response(
                200,
                json={"threads": items[offset : offset + 100], "users": [{"id": 1, "name": "A"}]},
            )
        ident = int(req.url.path.rsplit("/", 1)[1])
        detail = next(item for item in items if item["id"] == ident)
        return httpx.Response(
            200,
            json={
                "thread": {
                    **detail,
                    "comments": [
                        {"id": 1, "user_id": 1, "content": "<document>abcdefghij</document>"}
                    ],
                },
                "users": [{"id": 1, "name": "A"}],
            },
        )

    client = make_client(handler)
    result = collect_posts(client, 1, START, END, region="us", include_comments=False)
    assert [t["id"] for t in result["threads"]] == [1, 2, 3]
    assert result["scanned"] == 15
    assert requests == ["/api/courses/1/threads"]
    result = collect_posts(client, 1, START, END, region="us", comment_chars=4)
    assert result["threads"][0]["comments"][0]["body"] == "abcd…"
    assert collect_posts(client, 1, START, END, region="us", max_threads=2)["truncated"]


def test_format_digest():
    comment = {
        "author": "B",
        "author_role": None,
        "body": "answer",
        "is_endorsed": True,
        "replies": [{"author": "C", "body": "reply", "replies": []}],
    }
    records = [
        {
            "number": 1,
            "type": "question",
            "title": "Title",
            "author": "A",
            "created_at": "2026-11-02",
            "reply_count": 1,
            "vote_count": 2,
            "body": "Body",
            "url": "https://example.test",
            "category": "General",
            "answers": [comment],
            "links": [{"url": "https://example.test"}],
        }
    ]
    result = {"start": "start", "end": "end", "threads": records, "truncated": False}
    text = format_digest(result, course_label="Course")
    assert "1 question" in text and "General (1)" in text
    assert "  > [answer] B (unknown role): answer ✓" in text
    assert "    > C (unknown role): reply" in text
    assert "Links: https://example.test" in text
    result["threads"] *= 4
    result["truncated"] = True
    text = format_digest(result, course_label="Course", max_chars=300)
    assert (
        len(text) <= 300 and "more threads omitted" in text and "stopped at max_threads=4" in text
    )
    result.update(threads=[], truncated=False)
    assert "No posts in this period." in format_digest(result, course_label="Course")


def test_tools(tmp_path):
    courses = [
        {"course": {"id": i, "code": f"C{i}", "name": "Course", "status": "active"}} for i in (1, 2)
    ]

    def handler(req):
        if req.url.path == "/api/user":
            return httpx.Response(200, json={"courses": courses})
        if req.url.path == "/api/courses/1/threads":
            return httpx.Response(403, json={"message": "denied"})
        return httpx.Response(200, json={"threads": []})

    mcp = FastMCP("test")
    register_digest_tools(mcp, make_ctx(handler, tmp_path))
    assert {"get_posts_in_range", "digest_all_courses"} <= {
        t.name for t in asyncio.run(mcp.list_tools())
    }
    assert "summarize_period" in {p.name for p in asyncio.run(mcp.list_prompts())}
    with pytest.raises(Exception, match="start"):
        call_tool(mcp, "get_posts_in_range", course_id=2, start="2026-11-05", end="2026-11-01")
    result = call_tool(
        mcp, "get_posts_in_range", course_id=2, start="2026-11-01", end="2026-11-05", output="json"
    )
    assert result["threads"] == []
    result = call_tool(mcp, "digest_all_courses", start="2026-11-01", end="2026-11-05")
    assert "C1 Course: error:" in result and "C2 Course: posts" in result


def test_recursive_comment_limits_are_independent_of_thread_limit():
    item = thread(1, "2026-11-02T00:00:00+00:00")
    nested = {
        "user_id": 1,
        "content": "<document>abcdefghij</document>",
        "comments": [{"user_id": 1, "content": "<document>klmnopqrst</document>"}],
    }

    def handler(req):
        if req.url.path == "/api/courses/1/threads":
            return httpx.Response(200, json={"threads": [item]})
        return httpx.Response(
            200, json={"thread": {**item, "answers": [nested], "comments": [nested]}}
        )

    result = collect_posts(
        make_client(handler), 1, START, END, region="us", thread_chars=2, comment_chars=5
    )
    record = result["threads"][0]
    assert record["body"] == "Bo…"
    for key in ("answers", "comments"):
        assert record[key][0]["body"] == "abcde…"
        assert record[key][0]["replies"][0]["body"] == "klmno…"


def test_collection_orders_instants_and_includes_start():
    items = [
        thread(1, "2026-11-03T01:00:00+02:00"),
        thread(2, "2026-11-02T23:30:00+00:00"),
        thread(3, "2026-11-01T00:00:00+00:00"),
        {**thread(4, "2026-11-02T00:00:00+00:00"), "created_at": None},
    ]

    def handler(req):
        return httpx.Response(200, json={"threads": items})

    result = collect_posts(make_client(handler), 1, START, END, region="us", include_comments=False)
    assert [record["id"] for record in result["threads"]] == [3, 1, 2]
    assert result["scanned"] == 4


def test_text_course_label_and_fallback(tmp_path):
    def handler(req):
        if req.url.path == "/api/user":
            return httpx.Response(
                200,
                json={
                    "courses": [
                        {
                            "course": {
                                "id": 1,
                                "code": "CS101",
                                "name": "Computing",
                                "status": "archived",
                            }
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"threads": []})

    mcp = FastMCP("test")
    register_digest_tools(mcp, make_ctx(handler, tmp_path))
    args = {"start": "2026-11-01", "end": "2026-11-05"}
    assert call_tool(mcp, "get_posts_in_range", course_id=1, **args).startswith(
        "# CS101 Computing:"
    )
    assert call_tool(mcp, "get_posts_in_range", course_id=2, **args).startswith("# course 2:")


def test_prompt_instructions(tmp_path):
    mcp = FastMCP("test")
    register_digest_tools(mcp, make_ctx(lambda req: httpx.Response(200, json={}), tmp_path))
    prompt = asyncio.run(
        mcp.get_prompt("summarize_period", {"course_id": "42", "start": "7d", "end": "now"})
    )
    text = str(prompt)
    for expected in (
        "get_posts_in_range",
        "42",
        "7d",
        "now",
        "Announcements and deadlines",
        "Common questions and their answers",
        "Unresolved questions",
        "Links and resources shared",
        "Anything that needs the user's action",
        "thread numbers and URLs",
    ):
        assert expected in text
