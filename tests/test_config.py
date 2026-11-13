"""Tests for configuration parsing."""

from pathlib import Path

import pytest

from ed_mcp.config import ConfigError, load_settings


def test_region_urls(tmp_path: Path) -> None:
    s_us = load_settings(
        env={
            "ED_API_TOKEN": "tok",
            "ED_REGION": "us",
            "ED_STATE_DIR": str(tmp_path / "us"),
        }
    )
    assert s_us.base_url == "https://us.edstem.org/api/"
    assert s_us.static_base_url == "https://static.us.edusercontent.com/files/"

    s_au = load_settings(
        env={
            "ED_API_TOKEN": "tok",
            "ED_REGION": "au",
            "ED_STATE_DIR": str(tmp_path / "au"),
        }
    )
    assert s_au.base_url == "https://edstem.org/api/"
    assert s_au.static_base_url == "https://static.edusercontent.com/files/"

    s_ca = load_settings(
        env={
            "ED_API_TOKEN": "tok",
            "ED_REGION": "ca",
            "ED_STATE_DIR": str(tmp_path / "ca"),
        }
    )
    assert s_ca.base_url == "https://ca.edstem.org/api/"
    assert s_ca.static_base_url == "https://static.ca.edusercontent.com/files/"


def test_base_url_override(tmp_path: Path) -> None:
    s = load_settings(
        env={
            "ED_API_TOKEN": "tok",
            "ED_API_BASE_URL": "https://custom.edstem.org/api",
            "ED_STATE_DIR": str(tmp_path),
        }
    )
    assert s.base_url == "https://custom.edstem.org/api/"

    s2 = load_settings(
        env={
            "ED_API_TOKEN": "tok",
            "ED_API_BASE_URL": "https://custom.edstem.org/api/",
            "ED_STATE_DIR": str(tmp_path),
        }
    )
    assert s2.base_url == "https://custom.edstem.org/api/"


def test_bad_region(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_settings(
            env={
                "ED_API_TOKEN": "tok",
                "ED_REGION": "u s",
                "ED_STATE_DIR": str(tmp_path),
            }
        )

    with pytest.raises(ConfigError):
        load_settings(
            env={
                "ED_API_TOKEN": "tok",
                "ED_REGION": "toolongregion",
                "ED_STATE_DIR": str(tmp_path),
            }
        )


def test_missing_token(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"https://edstem\.org/us/settings/api-tokens"):
        load_settings(env={"ED_STATE_DIR": str(tmp_path)})

    s = load_settings(
        env={"ED_STATE_DIR": str(tmp_path)},
        require_token=False,
    )
    assert s.api_token == ""


def test_read_only_truthy(tmp_path: Path) -> None:
    for val in ("1", "true", "yes", "TRUE", "Yes", "True"):
        s = load_settings(
            env={
                "ED_API_TOKEN": "tok",
                "ED_STATE_DIR": str(tmp_path),
                "ED_READ_ONLY": val,
            }
        )
        assert s.read_only is True

    for val in ("0", "false", "no", "", "off"):
        s = load_settings(
            env={
                "ED_API_TOKEN": "tok",
                "ED_STATE_DIR": str(tmp_path),
                "ED_READ_ONLY": val,
            }
        )
        assert s.read_only is False
