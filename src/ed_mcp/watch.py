"""Poll for new posts and deliver alerts."""

import argparse
import json
import subprocess
import sys
import time

import httpx

from ed_mcp.client import EdAuthError, EdClient
from ed_mcp.config import TOKEN_HELP, ConfigError, load_settings
from ed_mcp.monitor import check_new_posts, default_store


def _as(s: str) -> str:
    s = s.replace("\n", " ").replace("\r", " ")[:200]
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def notify(title: str, message: str) -> None:
    subprocess.run(
        ["osascript", "-e", f"display notification {_as(message)} with title {_as(title)}"],
        check=False,
        timeout=10,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ed-mcp watch")
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--course", type=int, action="append")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument("--webhook")
    parser.add_argument("--backfill", type=int, default=0)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    if args.interval < 60:
        print("Interval raised to 60 seconds.", file=sys.stderr)
        args.interval = 60
    client = store = None
    try:
        settings = load_settings()
        client = EdClient(
            settings.api_token, settings.base_url, static_base_url=settings.static_base_url
        )
        store = default_store(settings)
        while True:
            result = check_new_posts(
                client,
                store,
                region=settings.region,
                course_ids=args.course,
                backfill=args.backfill,
            )
            if getattr(result, "auth_failed", False):
                print(TOKEN_HELP, file=sys.stderr)
                return 1
            for error in result.errors:
                print(f"Course {error['course_id']}: {error['error']}", file=sys.stderr)
            for alert in result.alerts:
                if not args.all and not alert["important"]:
                    continue
                print(json.dumps(alert), flush=True)
                if not args.no_notify and sys.platform == "darwin":
                    try:
                        notify(
                            f"Ed: {alert['course_code'] or alert['course_id']} #{alert['number']}",
                            f"{alert['title']} ({', '.join(alert['reasons'])})",
                        )
                    except (OSError, subprocess.SubprocessError) as exc:
                        print(f"Notification failed: {exc}", file=sys.stderr)
                if args.webhook:
                    try:
                        response = httpx.post(args.webhook, json=alert, timeout=10)
                        response.raise_for_status()
                    except httpx.HTTPError as exc:
                        print(f"Webhook failed: {exc}", file=sys.stderr)
            if args.once:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    except EdAuthError:
        print(TOKEN_HELP, file=sys.stderr)
        return 1
    finally:
        if store is not None:
            store.close()
        if client is not None:
            client.close()
