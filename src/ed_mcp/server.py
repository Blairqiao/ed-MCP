"""FastMCP server factory for Ed Discussion."""

from mcp.server.fastmcp import FastMCP

from ed_mcp.client import EdClient
from ed_mcp.config import Settings
from ed_mcp.context import AppContext
from ed_mcp.tools.core import register_core_tools
from ed_mcp.tools.digest_tools import register_digest_tools
from ed_mcp.tools.monitor_tools import register_monitor_tools
from ed_mcp.tools.write import register_write_tools

SERVER_INSTRUCTIONS = (
    "Tools for reading and writing Ed Discussion (edstem.org). "
    "Start with list_courses to find course IDs, use get_posts_in_range to summarise a period, "
    "check_new_posts / get_recent_alerts for alerts, and content accepts markdown."
)


def build_server(settings: Settings, client: EdClient | None = None) -> FastMCP:
    mcp = FastMCP("ed-discussion", instructions=SERVER_INSTRUCTIONS)
    ctx = AppContext(
        settings=settings,
        client=client
        or EdClient(
            settings.api_token,
            settings.base_url,
            static_base_url=settings.static_base_url,
        ),
    )
    register_core_tools(mcp, ctx)
    if not settings.read_only:
        register_write_tools(mcp, ctx)
    register_digest_tools(mcp, ctx)
    register_monitor_tools(mcp, ctx)
    return mcp
