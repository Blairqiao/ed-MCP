import asyncio

import httpx
import pytest
from conftest import call_tool, make_ctx
from mcp.server.fastmcp import FastMCP

from ed_mcp.tools.core import register_core_tools


def setup(tmp_path, routes):
    requests = []

    def handler(req):
        requests.append(req)
        value = routes.get(req.url.path)
        if value is None:
            return httpx.Response(404, json={"message": "missing"})
        return httpx.Response(200, json=value)

    mcp = FastMCP("t")
    register_core_tools(mcp, make_ctx(handler, tmp_path))
    return mcp, requests


def test_registration_and_threads(tmp_path):
    threads = [
        {"id": 1, "course_id": 1, "category": "General", "type": "question", "is_answered": False},
        {"id": 2, "course_id": 1, "category": "General", "type": "question", "is_answered": True},
        {"id": 3, "course_id": 1, "category": "Other", "type": "post"},
    ]
    mcp, _ = setup(tmp_path, {"/api/courses/1/threads": {"threads": threads}})
    assert len(asyncio.run(mcp.list_tools())) == 13
    result = call_tool(
        mcp,
        "list_threads",
        course_id=1,
        limit=3,
        category="general",
        thread_type="question",
        unanswered_only=True,
    )
    assert [t["id"] for t in result["threads"]] == [1]
    assert result["next_offset"] == 3
    assert call_tool(mcp, "list_threads", course_id=1, limit=4)["next_offset"] is None


def test_thread_number_and_errors(tmp_path):
    mcp, requests = setup(
        tmp_path, {"/api/courses/1/threads/7": {"thread": {"id": 10, "course_id": 1}}}
    )
    assert call_tool(mcp, "get_thread", course_id=1, number=7)["id"] == 10
    assert requests[-1].url.path == "/api/courses/1/threads/7"
    with pytest.raises(Exception, match="thread_id"):
        call_tool(mcp, "get_thread")
    with pytest.raises(Exception, match="404"):
        call_tool(mcp, "get_thread", thread_id=999)


def test_course_categories_and_fallback(tmp_path):
    mcp, _ = setup(
        tmp_path,
        {
            "/api/courses/1": {
                "course": {
                    "id": 1,
                    "settings": {
                        "discussion": {
                            "categories": [{"name": "A", "subcategories": [{"name": "B"}]}]
                        }
                    },
                }
            },
            "/api/courses/2": {"course": {"id": 2}},
            "/api/user": {"courses": [{"course": {"id": 2}}]},
        },
    )
    assert call_tool(mcp, "get_course_info", course_id=1)["categories"] == [
        {"name": "A", "subcategories": ["B"]}
    ]
    assert call_tool(mcp, "get_course_info", course_id=2)["categories"] == []


def test_announcements_and_links(tmp_path):
    threads = [
        {
            "id": 1,
            "course_id": 1,
            "title": "Old",
            "type": "post",
            "created_at": "2020-01-01T00:00:00+00:00",
            "content": "https://old.test",
        },
        {
            "id": 2,
            "course_id": 1,
            "title": "New",
            "type": "announcement",
            "created_at": "2026-01-01T00:00:00+00:00",
            "content": '<link href="https://new.test">new</link>',
        },
        {"id": 3, "course_id": 1, "title": "More", "type": "announcement"},
    ]
    mcp, _ = setup(tmp_path, {"/api/courses/1/threads": {"threads": threads}})
    assert [t["id"] for t in call_tool(mcp, "list_announcements", course_id=1, limit=1)] == [2]
    links = call_tool(mcp, "get_links", course_id=1, since="2025-01-01T00:00:00+00:00")
    assert len(links) == 1
    assert links[0]["thread_title"] == "New"
    assert links[0]["thread_url"] == "https://edstem.org/us/courses/1/discussion/2"


def test_lessons(tmp_path):
    mcp, _ = setup(
        tmp_path,
        {
            "/api/courses/1/lessons": {
                "modules": [{"id": 3, "name": "Week 1"}],
                "lessons": [{"id": 5, "module_id": 3}, {"id": 6}],
            },
            "/api/lessons/5": {
                "lesson": {
                    "id": 5,
                    "slides": [
                        {
                            "id": 8,
                            "content": '<document><paragraph>See <link href="https://example.com">this</link></paragraph></document>',
                        }
                    ],
                }
            },
        },
    )
    lessons = call_tool(mcp, "list_lessons", course_id=1)
    assert lessons == [{"id": 5, "module_id": 3, "module": "Week 1"}, {"id": 6, "module": None}]
    lesson = call_tool(mcp, "get_lesson", lesson_id=5)
    assert lesson["slides"][0]["content"] == "See this (https://example.com)"
    assert lesson["links"][0]["url"] == "https://example.com"
