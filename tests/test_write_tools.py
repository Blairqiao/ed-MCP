"""Exercise write tools against a mock Ed API."""

import asyncio
import json

import httpx
import pytest
from conftest import call_tool, make_client, make_ctx, make_settings
from mcp.server.fastmcp import FastMCP

from ed_mcp.server import build_server
from ed_mcp.tools.write import register_write_tools


@pytest.fixture
def write_tools(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        path = request.url.path
        if path == "/api/files":
            return httpx.Response(200, json={"file": {"id": "abc"}})
        if request.method == "GET":
            return httpx.Response(
                200, json={"thread": {"id": 9, "course_id": 1, "title": "old", "answers": []}}
            )
        if path.endswith("/comments"):
            return httpx.Response(
                200, json={"comment": {"id": 3, **json.loads(request.content)["comment"]}}
            )
        if path.endswith("/threads") or request.method == "PUT":
            return httpx.Response(
                200,
                json={"thread": {"id": 9, "course_id": 1, **json.loads(request.content)["thread"]}},
            )
        return httpx.Response(200)

    mcp = FastMCP("t")
    register_write_tools(mcp, make_ctx(handler, tmp_path))
    return mcp, requests


def test_all_write_tools_register(write_tools):
    mcp, _ = write_tools
    assert {tool.name for tool in asyncio.run(mcp.list_tools())} == {
        "create_thread",
        "edit_thread",
        "delete_thread",
        "post_comment",
        "reply_to_comment",
        "edit_comment",
        "delete_comment",
        "thread_action",
        "comment_action",
        "accept_answer",
        "upload_file",
    }


def test_create_thread_converts_markdown_and_sets_type(write_tools):
    mcp, requests = write_tools
    result = call_tool(
        mcp, "create_thread", course_id=1, title="Hi", content="**hi**", thread_type="announcement"
    )
    body = json.loads(requests[-1].content)["thread"]
    assert body["content"].startswith("<document") and "<bold>hi</bold>" in body["content"]
    assert body["type"] == "announcement" and result["body"] == "hi"


def test_edit_thread_requires_a_field(write_tools):
    mcp, requests = write_tools
    with pytest.raises(Exception, match="At least one field"):
        call_tool(mcp, "edit_thread", thread_id=9)
    assert not requests


def test_edit_thread_fetches_then_updates(write_tools):
    mcp, requests = write_tools
    call_tool(mcp, "edit_thread", thread_id=9, title="new")
    assert [(r.method, r.url.path) for r in requests] == [
        ("GET", "/api/threads/9"),
        ("PUT", "/api/threads/9"),
    ]
    assert json.loads(requests[-1].content)["thread"]["title"] == "new"


def test_post_comment_as_answer(write_tools):
    mcp, requests = write_tools
    call_tool(mcp, "post_comment", thread_id=9, content="answer", as_answer=True)
    assert json.loads(requests[-1].content)["comment"]["type"] == "answer"


def test_pin_thread(write_tools):
    mcp, requests = write_tools
    assert call_tool(mcp, "thread_action", thread_id=9, action="pin")["ok"]
    assert requests[-1].url.path == "/api/threads/9/pin"


def test_upload_image_multipart_and_markdown(write_tools, tmp_path):
    mcp, requests = write_tools
    image = tmp_path / "image.png"
    image.write_bytes(b"png")
    result = call_tool(mcp, "upload_file", path=str(image))
    assert result["markdown"] == f"![image.png]({result['url']})"
    request = requests[-1]
    assert request.url.path == "/api/files"
    assert (
        b'Content-Disposition: form-data; name="attachment"; filename="image.png"'
        in request.content
    )
    assert b"Content-Type: image/png" in request.content


def test_upload_missing_file_rejected(write_tools, tmp_path):
    mcp, requests = write_tools
    with pytest.raises(Exception, match="existing regular file"):
        call_tool(mcp, "upload_file", path=str(tmp_path / "missing"))
    assert not requests


def test_upload_size_limit_rejected(write_tools, tmp_path):
    mcp, requests = write_tools
    large = tmp_path / "large.bin"
    with large.open("wb") as file:
        file.truncate(20 * 1024 * 1024)
    with pytest.raises(Exception, match="under 20 MB"):
        call_tool(mcp, "upload_file", path=str(large))
    assert not requests


def test_read_only_server_excludes_write_tools(tmp_path):
    def handler(request):
        raise AssertionError("No API request expected")

    server = build_server(make_settings(tmp_path, read_only=True), make_client(handler))
    assert "create_thread" not in {tool.name for tool in asyncio.run(server.list_tools())}
