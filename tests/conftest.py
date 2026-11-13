"""Shared test fixtures and helpers."""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

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
    """Call an MCP tool and return its Python return value.

    Runs the tool through FastMCP's argument validation, checks that FastMCP can convert the
    result, and checks the result is JSON-serialisable (round-tripped through json). Reading the
    raw return value avoids the content-list ambiguity for tools without a return annotation,
    where FastMCP splits a list into one content block per item ([] -> no blocks, [x] -> x).
    Tool errors surface as ToolError.
    """

    async def run() -> Any:
        tool = mcp._tool_manager.get_tool(name)
        if tool is None:
            raise ToolError(f"Unknown tool: {name}")
        result = await tool.run(args, context=mcp.get_context())
        tool.fn_metadata.convert_result(result)
        return result

    return json.loads(json.dumps(asyncio.run(run())))
