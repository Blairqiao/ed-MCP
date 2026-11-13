import json

import httpx
import pytest
from conftest import make_client

from ed_mcp.client import EdAuthError, EdClient, EdError, EdNotFoundError, EdRateLimitError


def test_pagination_and_limits():
    offsets = []

    def handler(req):
        assert req.headers["accept"] == "application/json"
        assert req.headers["authorization"] == "Bearer test-token"
        assert req.url.params["limit"] == "100"
        offset = int(req.url.params["offset"])
        offsets.append(offset)
        count = min(100, 237 - offset)
        return httpx.Response(
            200,
            json={
                "threads": [{"id": i, "user_id": 1} for i in range(offset, offset + count)],
                "users": [{"id": 1, "name": "A"}],
            },
        )

    client = make_client(handler)
    assert len(client.list_threads(1, limit=500)["threads"]) == 100
    offsets.clear()
    threads = list(client.iter_threads(1))
    assert len(threads) == 237
    assert offsets == [0, 100, 200]
    assert all(t["user"]["name"] == "A" for t in threads)
    offsets.clear()
    assert len(list(client.iter_threads(1, max_threads=3))) == 3
    assert offsets == [0]
    client.close()


def test_thread_and_comment_writes():
    calls = []

    def handler(req):
        body = json.loads(req.content) if req.content else None
        calls.append((req.method, req.url.path, body))
        if req.method == "GET":
            return httpx.Response(
                200,
                json={
                    "thread": {"id": 5, "title": "old", "answers": [], "comments": [], "user": {}}
                },
            )
        if req.method == "PUT":
            return httpx.Response(200, json={"thread": body["thread"]})
        return httpx.Response(200, json={"thread": {"id": 5}, "comment": {"id": 8}})

    client = make_client(handler)
    client.post_thread(1, title="T", content_xml="xml")
    assert len(calls[-1][2]["thread"]) == 11
    assert client.edit_thread(5, title="new", category=None) == {"id": 5, "title": "new"}
    with pytest.raises(ValueError):
        client.edit_thread(5, mystery=1)
    client.post_comment(5, "xml", type="answer")
    assert calls[-1][1:] == (
        "/api/threads/5/comments",
        {
            "comment": {
                "type": "answer",
                "content": "xml",
                "is_private": False,
                "is_anonymous": False,
            }
        },
    )
    client.reply_to_comment(8, "xml")
    assert calls[-1][1] == "/api/comments/8/comments"
    assert calls[-1][2]["comment"]["type"] == "comment"
    client.thread_action(5, "pin")
    assert calls[-1][:2] == ("POST", "/api/threads/5/pin")
    with pytest.raises(ValueError):
        client.thread_action(5, "explode")
    with pytest.raises(ValueError):
        client.comment_action(5, "explode")


def test_retries_and_errors():
    sleeps = []
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(429),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    client = EdClient(
        "secret", transport=httpx.MockTransport(lambda req: next(responses)), sleep=sleeps.append
    )
    assert client.get_user() == {"ok": True}
    assert sleeps == [7, 2]
    attempts = []
    client = EdClient(
        "secret",
        transport=httpx.MockTransport(
            lambda req: (attempts.append(1), httpx.Response(503, json={"message": "secret"}))[1]
        ),
        max_retries=2,
        sleep=lambda _: None,
    )
    with pytest.raises(EdError) as caught:
        client.get_user()
    assert len(attempts) == 3
    assert "secret" not in str(caught.value) and "secret" not in repr(caught.value)
    for status, body, error in [
        (401, {}, EdAuthError),
        (400, {"code": "bad_token", "message": "secret"}, EdAuthError),
        (200, {"code": "bad_token", "message": "secret"}, EdAuthError),
        (404, {}, EdNotFoundError),
        (429, {}, EdRateLimitError),
    ]:
        client = EdClient(
            "secret",
            transport=httpx.MockTransport(
                lambda req, status=status, body=body: httpx.Response(status, json=body)
            ),
            max_retries=0,
        )
        with pytest.raises(error) as caught:
            client.get_user()
        assert "secret" not in str(caught.value) and "secret" not in repr(caught.value)
        assert caught.value.status == status


def test_fallback_upload_and_empty():
    calls = []

    def handler(req):
        calls.append(req.url.path)
        if req.url.path.endswith("/users") and "analytics" not in req.url.path:
            return httpx.Response(403)
        if "analytics" in req.url.path:
            return httpx.Response(200, json={"users": [{"id": 1}]})
        if req.url.path == "/api/files":
            assert b"attachment" in req.content and b"hello" in req.content
            return httpx.Response(200, json={"file": {"id": "abc"}})
        return httpx.Response(200)

    client = make_client(handler)
    assert client.list_course_users(1) == [{"id": 1}]
    assert calls[:2] == ["/api/courses/1/users", "/api/courses/1/analytics/users"]
    assert (
        client.upload_file("x.txt", b"hello", "text/plain")
        == "https://static.us.edusercontent.com/files/abc"
    )
    assert client._request("GET", "empty") is None


def test_read_endpoints_and_remaining_writes():
    calls = []

    def handler(req):
        calls.append(
            (
                req.method,
                req.url.path,
                dict(req.url.params),
                json.loads(req.content) if req.content else None,
            )
        )
        return httpx.Response(
            200,
            json={
                "course": {"id": 1},
                "courses": [{"course": {"status": "active"}}, {"course": {"status": "archived"}}],
                "items": [1],
                "threads": [],
                "users": [],
                "lesson": {"id": 2},
                "slide": {"id": 3},
                "resources": [4],
                "comment": {"id": 5},
            },
        )

    client = make_client(handler)
    assert len(client.list_courses()) == 1
    assert len(client.list_courses(True)) == 2
    assert client.get_course(1) == {"id": 1}
    assert client.get_user_activity(2, 1, limit=100) == [1]
    assert calls[-1][2]["limit"] == "50"
    client.get_course_thread(1, 7)
    assert calls[-1][1] == "/api/courses/1/threads/7"
    client.search_threads(1, "query")
    assert calls[-1][2]["query"] == "query"
    client.list_lessons(1)
    assert client.get_lesson(2) == {"id": 2}
    assert client.get_slide(3) == {"id": 3}
    assert client.list_resources(1) == [4]
    assert client.edit_comment(5, "xml") == {"id": 5}
    assert calls[-1][3] == {"comment": {"content": "xml"}}
    client.delete_comment(5)
    assert calls[-1][:2] == ("DELETE", "/api/comments/5")
    client.comment_action(5, "endorse")
    assert calls[-1][:2] == ("POST", "/api/comments/5/endorse")
    client.accept_answer(1, 5)
    assert calls[-1][:2] == ("POST", "/api/threads/1/accept/5")
    client.delete_thread(1)
    assert calls[-1][:2] == ("DELETE", "/api/threads/1")
