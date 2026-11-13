"""CLI interface for ed-mcp."""

import argparse
import sys

from ed_mcp.client import EdAuthError, EdClient
from ed_mcp.config import TOKEN_HELP, load_settings
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
            client = EdClient(
                settings.api_token,
                settings.base_url,
                static_base_url=settings.static_base_url,
            )
            data = client.get_user()
            user_info = data.get("user", {})
            user_name = user_info.get("name", "Unknown")
            print(user_name)
            courses = data.get("courses", [])
            for c in courses:
                course = c.get("course", {})
                if course.get("status") == "active":
                    cid = course.get("id")
                    code = course.get("code")
                    name = course.get("name")
                    print(f"{cid}  {code}  {name}")
            return 0
        except EdAuthError:
            print(TOKEN_HELP, file=sys.stderr)
            return 1
    elif args.subcommand == "watch":
        return watch_main(unknown)
    else:
        parser.print_help()
        return 0
