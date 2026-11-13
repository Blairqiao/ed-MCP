"""Shared test fixtures and helpers."""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from ed_mcp.client import EdClient
from ed_mcp.config import Settings, load_settings
from ed_mcp.context import AppContext


def make_client(handler: Callable[[httpx.Request], httpx.Response]) -> EdClient:
    """Create an EdClient wired to MockTransport."""
    return EdClient(
        "test-token",
        "https://us.edstem.org/api/",
        transport=httpx.MockTransport(handler),
        sleep=lambda s: None,
    )


def make_settings(tmp_path: Path, *, read_only: bool = False, region: str = "us") -> Settings:
    """Create a test Settings instance with state_dir in tmp_path."""
    return load_settings(
        env={
            "ED_API_TOKEN": "test-token",
            "ED_REGION": region,
            "ED_STATE_DIR": str(tmp_path),
            "ED_READ_ONLY": "1" if read_only else "0",
        }
    )


def make_ctx(
    handler: Callable[[httpx.Request], httpx.Response],
    tmp_path: Path,
    *,
    read_only: bool = False,
) -> AppContext:
    """Create an AppContext wired to MockTransport."""
    settings = make_settings(tmp_path, read_only=read_only)
    client = make_client(handler)
    return AppContext(settings=settings, client=client)


def call_tool(mcp: FastMCP, name: str, **args: Any) -> Any:
    """Call an MCP tool and normalise result to Python return value."""
    res = asyncio.run(mcp.call_tool(name, args))

    if isinstance(res, tuple):
        content, structured = res
        if structured is not None:
            if isinstance(structured, dict) and "result" in structured:
                return structured["result"]
            return structured
        res = content

    if isinstance(res, list):
        if not res:
            return None
        if len(res) == 1:
            item = res[0]
            text = getattr(item, "text", str(item))
            try:
                return json.loads(text)
            except Exception:
                return text
        else:
            parsed = []
            for item in res:
                text = getattr(item, "text", str(item))
                try:
                    parsed.append(json.loads(text))
                except Exception:
                    parsed.append(text)
            return parsed

    if isinstance(res, dict) and "result" in res:
        return res["result"]
    return res
