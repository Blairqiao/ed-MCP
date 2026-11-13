"""Tools for posting and moderating Ed Discussion content."""

import mimetypes
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

from ed_mcp.content import ensure_ed_xml
from ed_mcp.context import AppContext
from ed_mcp.format import compact_comment, compact_thread
from ed_mcp.tools._common import handle_ed_errors


def register_write_tools(mcp: FastMCP, ctx: AppContext) -> None:
    """Register tools that modify content under the user's Ed account."""
    region = ctx.settings.region

    @mcp.tool()
    @handle_ed_errors
    def create_thread(
        course_id: int,
        title: str,
        content: str,
        thread_type: Literal["post", "question", "announcement"] = "post",
        category: str = "",
        subcategory: str = "",
        is_private: bool = False,
        is_anonymous: bool = False,
        is_pinned: bool = False,
    ) -> dict:
        """Create a thread under your Ed account, publicly unless private; return the thread.

        Content accepts Markdown or Ed XML.
        """
        result = ctx.client.post_thread(
            course_id,
            title=title,
            content_xml=ensure_ed_xml(content),
            type=thread_type,
            category=category,
            subcategory=subcategory,
            is_private=is_private,
            is_anonymous=is_anonymous,
            is_pinned=is_pinned,
        )
        return compact_thread(result, {}, region, body_chars=None)

    @mcp.tool()
    @handle_ed_errors
    def edit_thread(
        thread_id: int,
        title: str | None = None,
        content: str | None = None,
        category: str | None = None,
        subcategory: str | None = None,
        thread_type: str | None = None,
        is_private: bool | None = None,
    ) -> dict:
        """Edit a thread under your Ed account; changes may be public. Return the thread.

        Content accepts Markdown or Ed XML.
        """
        fields = {
            "title": title,
            "content": content,
            "category": category,
            "subcategory": subcategory,
            "type": thread_type,
            "is_private": is_private,
        }
        if all(value is None for value in fields.values()):
            raise ValueError("At least one field is required")
        if content is not None:
            fields["content"] = ensure_ed_xml(content)
        return compact_thread(
            ctx.client.edit_thread(thread_id, **fields), {}, region, body_chars=None
        )

    @mcp.tool()
    @handle_ed_errors
    def delete_thread(thread_id: int) -> dict:
        """Delete a thread under your Ed account and return its ID; the change is public."""
        ctx.client.delete_thread(thread_id)
        return {"deleted": thread_id}

    @mcp.tool()
    @handle_ed_errors
    def post_comment(
        thread_id: int,
        content: str,
        as_answer: bool = False,
        is_private: bool = False,
        is_anonymous: bool = False,
    ) -> dict:
        """Post a comment or answer under your Ed account, publicly unless private; return it.

        Content accepts Markdown or Ed XML.
        """
        result = ctx.client.post_comment(
            thread_id,
            ensure_ed_xml(content),
            type="answer" if as_answer else "comment",
            is_private=is_private,
            is_anonymous=is_anonymous,
        )
        return compact_comment(result, {})

    @mcp.tool()
    @handle_ed_errors
    def reply_to_comment(
        comment_id: int,
        content: str,
        is_private: bool = False,
        is_anonymous: bool = False,
    ) -> dict:
        """Reply under your Ed account, publicly unless private; return the comment.

        Content accepts Markdown or Ed XML.
        """
        result = ctx.client.reply_to_comment(
            comment_id,
            ensure_ed_xml(content),
            is_private=is_private,
            is_anonymous=is_anonymous,
        )
        return compact_comment(result, {})

    @mcp.tool()
    @handle_ed_errors
    def edit_comment(comment_id: int, content: str) -> dict:
        """Edit a comment under your Ed account; changes may be public. Return the comment.

        Content accepts Markdown or Ed XML.
        """
        return compact_comment(ctx.client.edit_comment(comment_id, ensure_ed_xml(content)), {})

    @mcp.tool()
    @handle_ed_errors
    def delete_comment(comment_id: int) -> dict:
        """Delete a comment under your Ed account and return its ID; the change is public."""
        ctx.client.delete_comment(comment_id)
        return {"deleted": comment_id}

    @mcp.tool()
    @handle_ed_errors
    def thread_action(
        thread_id: int,
        action: Literal[
            "lock",
            "unlock",
            "pin",
            "unpin",
            "endorse",
            "unendorse",
            "star",
            "unstar",
            "watch",
            "unwatch",
        ],
    ) -> dict:
        """Moderate or follow a thread under your Ed account; return the change.

        Changes may be public.
        """
        ctx.client.thread_action(thread_id, action)
        return {"thread_id": thread_id, "action": action, "ok": True}

    @mcp.tool()
    @handle_ed_errors
    def comment_action(comment_id: int, action: Literal["endorse", "unendorse"]) -> dict:
        """Endorse or unendorse a comment under your Ed account; return the public change."""
        ctx.client.comment_action(comment_id, action)
        return {"comment_id": comment_id, "action": action, "ok": True}

    @mcp.tool()
    @handle_ed_errors
    def accept_answer(thread_id: int, comment_id: int) -> dict:
        """Accept an answer under your Ed account and return the public change."""
        ctx.client.accept_answer(thread_id, comment_id)
        return {"thread_id": thread_id, "comment_id": comment_id, "accepted": True}

    @mcp.tool()
    @handle_ed_errors
    def upload_file(path: str) -> dict:
        """Upload a file under your Ed account; return a URL and Markdown for a public post."""
        file = Path(path).expanduser()
        if not file.is_file():
            raise ValueError("Path must be an existing regular file")
        if file.stat().st_size >= 20 * 1024 * 1024:
            raise ValueError("File must be under 20 MB")
        content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        url = ctx.client.upload_file(file.name, file.read_bytes(), content_type)
        prefix = "!" if content_type.startswith("image/") else ""
        return {"url": url, "markdown": f"{prefix}[{file.name}]({url})"}
