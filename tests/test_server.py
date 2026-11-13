"""Tests for server factory and tool call helpers."""

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from conftest import call_tool, make_client, make_settings
from mcp.server.fastmcp import FastMCP

from ed_mcp.cli import main as cli_main
from ed_mcp.client import EdNotFoundError
from ed_mcp.config import TOKEN_HELP
from ed_mcp.server import SERVER_INSTRUCTIONS, build_server
from ed_mcp.tools._common import handle_ed_errors, json_safe


def test_call_tool_and_error_handling() -> None:
    mcp = FastMCP("test-server")

    @mcp.tool()
    def return_dict() -> dict:
        return {"a": 1}

    @mcp.tool()
    def return_list() -> list[int]:
        return [1, 2]

    @mcp.tool()
    def return_str() -> str:
        return "hi"

    @mcp.tool()
    @handle_ed_errors
    def raise_error() -> str:
        raise EdNotFoundError("gone", status=404)

    @mcp.tool()
    @handle_ed_errors
    def raise_value_error() -> str:
        raise ValueError("invalid parameter")

    assert call_tool(mcp, "return_dict") == {"a": 1}
    assert call_tool(mcp, "return_list") == [1, 2]
    assert call_tool(mcp, "return_str") == "hi"

    with pytest.raises(Exception, match=r"Ed API error \(404\)"):
        call_tool(mcp, "raise_error")

    with pytest.raises(Exception, match="invalid parameter"):
        call_tool(mcp, "raise_value_error")


def test_build_server(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, read_only=False)
    server = build_server(settings)
    assert server.name == "ed-discussion"
    assert server.instructions == SERVER_INSTRUCTIONS

    settings_ro = make_settings(tmp_path, read_only=True)
    server_ro = build_server(settings_ro)
    assert server_ro.name == "ed-discussion"


def test_json_safe() -> None:
    obj = {"k": 1}
    assert json_safe(obj) is obj


def test_cli_watch(capsys: pytest.CaptureFixture[str]) -> None:
    ret = cli_main(["watch"])
    assert ret == 2
    captured = capsys.readouterr()
    assert "watch is not implemented yet" in captured.err


def test_cli_check_auth_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ED_API_TOKEN", "bad-token")
    monkeypatch.setenv("ED_STATE_DIR", str(tmp_path))

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/user"
        return httpx.Response(401, json={"message": "auth failed"})

    with patch("ed_mcp.cli.EdClient", return_value=make_client(handler)):
        ret = cli_main(["check"])
        assert ret == 1
        captured = capsys.readouterr()
        assert TOKEN_HELP in captured.err


def test_cli_check_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ED_API_TOKEN", "good-token")
    monkeypatch.setenv("ED_STATE_DIR", str(tmp_path))

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/user"
        return httpx.Response(
            200,
            json={
                "user": {"name": "Alice"},
                "courses": [
                    {
                        "course": {
                            "id": 101,
                            "code": "CS101",
                            "name": "Intro CS",
                            "status": "active",
                        }
                    },
                    {
                        "course": {
                            "id": 999,
                            "code": "OLD",
                            "name": "Archived CS",
                            "status": "archived",
                        }
                    },
                ],
            },
        )

    with patch("ed_mcp.cli.EdClient", return_value=make_client(handler)):
        ret = cli_main(["check"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "Alice" in captured.out
        assert "101  CS101  Intro CS" in captured.out
        assert "OLD" not in captured.out


def test_call_tool_unannotated_lists() -> None:
    mcp = FastMCP("test-server")

    @mcp.tool()
    def one():
        return [{"a": 1}]

    @mcp.tool()
    def none():
        return []

    assert call_tool(mcp, "one") == [{"a": 1}]
    assert call_tool(mcp, "none") == []


def test_cli_check_missing_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ED_API_TOKEN", "")
    monkeypatch.setenv("ED_STATE_DIR", str(tmp_path))
    assert cli_main(["check"]) == 1
    assert TOKEN_HELP in capsys.readouterr().err


def test_cli_check_network_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ED_API_TOKEN", "good-token")
    monkeypatch.setenv("ED_STATE_DIR", str(tmp_path))

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    with patch("ed_mcp.cli.EdClient", return_value=make_client(handler)):
        assert cli_main(["check"]) == 1
    err = capsys.readouterr().err
    assert "offline" in err and "good-token" not in err
