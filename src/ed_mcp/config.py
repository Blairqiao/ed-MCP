"""Configuration and settings for Ed Discussion MCP server."""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

TOKEN_HELP = "Create a token at https://edstem.org/us/settings/api-tokens and set ED_API_TOKEN."


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""


@dataclass(frozen=True)
class Settings:
    api_token: str = field(repr=False)  # keep the token out of reprs, logs, tracebacks
    region: str  # "us", "au", ...
    base_url: str  # always ends with "/"
    static_base_url: str  # always ends with "/"
    state_dir: Path  # created on load if missing
    read_only: bool


def load_settings(
    env: Mapping[str, str] | None = None,
    *,
    require_token: bool = True,
) -> Settings:
    """Load settings from environment.

    env=None means os.environ after load_dotenv(find_dotenv(usecwd=True)).
    ED_API_TOKEN (required unless require_token=False; then "")
    ED_REGION default "us"; must match ^[a-z]{2,5}$ else ConfigError
    ED_API_BASE_URL optional override of base_url (a trailing "/" is added if missing)
    ED_STATE_DIR default ~/.ed-mcp
    ED_READ_ONLY "1"/"true"/"yes" (case-insensitive) -> True; default False
    """
    if env is None:
        from dotenv import find_dotenv, load_dotenv

        load_dotenv(find_dotenv(usecwd=True))
        source: Mapping[str, str] = os.environ
    else:
        source = env

    api_token = source.get("ED_API_TOKEN", "").strip()
    if not api_token:
        if require_token:
            raise ConfigError(f"Missing ED_API_TOKEN. {TOKEN_HELP}")
        api_token = ""

    region = source.get("ED_REGION", "us").strip()
    if not re.fullmatch(r"[a-z]{2,5}", region):
        raise ConfigError(f"Invalid region: {region!r}. Must match ^[a-z]{{2,5}}$")

    if region == "us":
        default_base_url = "https://us.edstem.org/api/"
        static_base_url = "https://static.us.edusercontent.com/files/"
    elif region == "au":
        default_base_url = "https://edstem.org/api/"
        static_base_url = "https://static.edusercontent.com/files/"
    else:
        default_base_url = f"https://{region}.edstem.org/api/"
        static_base_url = f"https://static.{region}.edusercontent.com/files/"

    base_url_env = source.get("ED_API_BASE_URL")
    if base_url_env:
        base_url = base_url_env if base_url_env.endswith("/") else f"{base_url_env}/"
    else:
        base_url = default_base_url

    if not static_base_url.endswith("/"):
        static_base_url += "/"

    state_dir_env = source.get("ED_STATE_DIR")
    if state_dir_env:
        state_dir = Path(state_dir_env).expanduser()
    else:
        state_dir = Path.home() / ".ed-mcp"
    state_dir.mkdir(parents=True, exist_ok=True)

    read_only_val = source.get("ED_READ_ONLY", "").strip().lower()
    read_only = read_only_val in {"1", "true", "yes"}

    return Settings(
        api_token=api_token,
        region=region,
        base_url=base_url,
        static_base_url=static_base_url,
        state_dir=state_dir,
        read_only=read_only,
    )
