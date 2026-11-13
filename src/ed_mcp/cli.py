"""CLI interface for ed-mcp."""

import argparse
import sys

from ed_mcp.client import EdAuthError, EdClient, EdError
from ed_mcp.config import TOKEN_HELP, ConfigError, load_settings
from ed_mcp.server import build_server
from ed_mcp.watch import main as watch_main


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="ed-mcp",
        description="Ed Discussion MCP server CLI",
    )
    subparsers = parser.add_subparsers(dest="subcommand", metavar="{serve,check,watch}")

    subparsers.add_parser("serve", help="Run the MCP server over stdio")
    subparsers.add_parser("check", help="Check token and list active courses")
    subparsers.add_parser("watch", help="Watch for updates")

    # Default to serve when no arguments given
    if not argv:
        settings = load_settings()
        server = build_server(settings)
        server.run()
        return 0

    if argv[0] == "watch":
        return watch_main(argv[1:])

    args, unknown = parser.parse_known_args(argv)

    if args.subcommand == "serve":
        settings = load_settings()
        server = build_server(settings)
        server.run()
        return 0
    elif args.subcommand == "check":
        try:
            settings = load_settings()
        except ConfigError as exc:
            print(exc, file=sys.stderr)
            return 1
        client = EdClient(
            settings.api_token,
            settings.base_url,
            static_base_url=settings.static_base_url,
        )
        try:
            data = client.get_user()
        except EdAuthError:
            print(TOKEN_HELP, file=sys.stderr)
            return 1
        except EdError as exc:
            print(f"Ed API error: {exc.message}", file=sys.stderr)
            return 1
        finally:
            client.close()
        user_info = data.get("user") or {}
        print(user_info.get("name", "Unknown"))
        for c in data.get("courses") or []:
            course = c.get("course") or {}
            if course.get("status") == "active":
                print(f"{course.get('id')}  {course.get('code')}  {course.get('name')}")
        return 0
    elif args.subcommand == "watch":
        return watch_main(unknown)
    else:
        parser.print_help()
        return 0
