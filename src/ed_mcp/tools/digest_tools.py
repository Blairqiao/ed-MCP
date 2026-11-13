"""Digest tools registration."""

from typing import Literal

from mcp.server.fastmcp import FastMCP

from ed_mcp.client import EdError
from ed_mcp.context import AppContext
from ed_mcp.digest import collect_posts, format_digest
from ed_mcp.timeutil import parse_time
from ed_mcp.tools._common import handle_ed_errors


def _label(course: dict) -> str:
    return f"{course.get('code', '')} {course.get('name', '')}".strip()


def register_digest_tools(mcp: FastMCP, ctx: AppContext) -> None:
    @mcp.tool()
    @handle_ed_errors
    def get_posts_in_range(
        course_id: int,
        start: str,
        end: str = "now",
        include_comments: bool = True,
        max_threads: int = 200,
        output: Literal["text", "json"] = "text",
    ) -> str | dict:
        """Return threads created in a time window for the agent to summarise.

        Times accept 7d, 24h, 2026-11-01, or an ISO datetime. Comments on threads
        created before the window are not included. Summarise the returned text.
        """
        start_time, end_time = parse_time(start), parse_time(end)
        if start_time >= end_time:
            raise ValueError("start must be before end")
        result = collect_posts(
            ctx.client,
            course_id,
            start_time,
            end_time,
            region=ctx.settings.region,
            include_comments=include_comments,
            max_threads=max_threads,
        )
        if output == "json":
            return result
        label = next(
            (
                _label(entry["course"])
                for entry in ctx.client.list_courses(True)
                if entry.get("course", {}).get("id") == course_id
            ),
            f"course {course_id}",
        )
        return format_digest(result, course_label=label)

    @mcp.tool()
    @handle_ed_errors
    def digest_all_courses(
        start: str,
        end: str = "now",
        include_comments: bool = False,
        max_threads_per_course: int = 100,
    ) -> str:
        """Return a text digest of threads created in the window across active courses."""
        start_time, end_time = parse_time(start), parse_time(end)
        if start_time >= end_time:
            raise ValueError("start must be before end")
        courses = ctx.client.list_courses()
        digests = []
        for entry in courses:
            course = entry["course"]
            label = _label(course)
            try:
                result = collect_posts(
                    ctx.client,
                    course["id"],
                    start_time,
                    end_time,
                    region=ctx.settings.region,
                    include_comments=include_comments,
                    max_threads=max_threads_per_course,
                )
                digests.append(
                    format_digest(
                        result, course_label=label, max_chars=max(8000, 60000 // len(courses))
                    )
                )
            except EdError as exc:
                digests.append(f"# {label}: error: {exc.message}")
        return "\n\n---\n\n".join(digests)

    @mcp.prompt()
    def summarize_period(course_id: str, start: str, end: str = "now") -> str:
        """Guide a summary of a course's discussion in a period."""
        return (
            f"Call get_posts_in_range with course_id={course_id}, start={start}, end={end}. "
            "Then write a summary grouped into Announcements and deadlines, Common questions "
            "and their answers, Unresolved questions, Links and resources shared, and Anything "
            "that needs the user's action. Cite thread numbers and URLs."
        )
