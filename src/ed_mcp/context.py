"""Application context container."""

from dataclasses import dataclass

from ed_mcp.client import EdClient
from ed_mcp.config import Settings


@dataclass
class AppContext:
    settings: Settings
    client: EdClient
