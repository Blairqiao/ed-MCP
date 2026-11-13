import json
from types import SimpleNamespace

import httpx
from conftest import make_settings

from ed_mcp import watch
from ed_mcp.client import EdAuthError
from ed_mcp.config import TOKEN_HELP, ConfigError
from ed_mcp.monitor import CheckResult


def test_watch_delivery(monkeypatch, tmp_path, capsys):
    alerts = [
        {
            "important": important,
            "course_code": "C",
            "course_id": 1,
            "number": n,
            "title": "Title",
            "reasons": ["pinned"],
        }
        for n, important in [(1, True), (2, False)]
    ]
    closed = []
    monkeypatch.setattr(watch, "load_settings", lambda: make_settings(tmp_path))
    monkeypatch.setattr(
        watch, "EdClient", lambda *a, **kw: SimpleNamespace(close=lambda: closed.append("client"))
    )
    monkeypatch.setattr(
        watch, "default_store", lambda s: SimpleNamespace(close=lambda: closed.append("store"))
    )
    monkeypatch.setattr(watch, "check_new_posts", lambda *a, **kw: CheckResult(alerts, []))
    monkeypatch.setattr(watch.sys, "platform", "darwin")
    notifications, posts = [], []
    monkeypatch.setattr(watch, "notify", lambda *a: notifications.append(a))

    def post(url, **kwargs):
        posts.append((url, kwargs))
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(watch.httpx, "post", post)
    assert watch.main(["--once", "--webhook", "https://h.example"]) == 0
    assert [json.loads(line) for line in capsys.readouterr().out.splitlines()] == alerts[:1]
    assert len(notifications) == len(posts) == 1 and len(closed) == 2
    assert watch.main(["--once", "--all", "--no-notify"]) == 0
    assert len(capsys.readouterr().out.splitlines()) == 2 and len(notifications) == 1


def test_watch_errors(monkeypatch, capsys):
    def fail():
        raise ConfigError("bad config")

    monkeypatch.setattr(watch, "load_settings", fail)
    assert watch.main(["--once"]) == 1
    assert "bad config" in capsys.readouterr().err
    assert watch._as('say "hi"\\n') == '"say \\"hi\\"\\\\n"'


def test_auth_from_course(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(watch, "load_settings", lambda: make_settings(tmp_path))
    monkeypatch.setattr(watch, "EdClient", lambda *a, **k: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(watch, "default_store", lambda s: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(watch, "check_new_posts", lambda *a, **k: CheckResult([], [], True))
    assert watch.main(["--once"]) == 1
    assert TOKEN_HELP in capsys.readouterr().err
    assert issubclass(EdAuthError, Exception)
