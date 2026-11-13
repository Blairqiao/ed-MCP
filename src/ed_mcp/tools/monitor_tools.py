"""MCP tools for checking and configuring alerts."""

from mcp.server.fastmcp import FastMCP

from ed_mcp import monitor
from ed_mcp.context import AppContext
from ed_mcp.timeutil import parse_time
from ed_mcp.tools._common import handle_ed_errors


def register_monitor_tools(mcp: FastMCP, ctx: AppContext) -> None:
    store = None

    def get_store():
        nonlocal store
        if store is None:
            store = monitor.default_store(ctx.settings)
        return store

    @mcp.tool()
    @handle_ed_errors
    def check_new_posts(
        course_id: int | None = None, only_important: bool = True, backfill: int = 0
    ) -> dict:
        """Check for new posts and mark them seen; a second check returns only newer posts.

        The ed-mcp watch process may already have recorded posts; also use get_recent_alerts.
        """
        state = get_store()

        class CursorTracker:
            baseline = False

            def __getattr__(self, name):
                return getattr(state, name)

            def get_cursor(self, cid):
                cursor = state.get_cursor(cid)
                if cursor is None:
                    self.baseline = True
                return cursor

        tracker = CursorTracker()
        result = monitor.check_new_posts(
            ctx.client,
            tracker,
            region=ctx.settings.region,
            course_ids=[course_id] if course_id is not None else None,
            backfill=backfill,
        )
        response = {
            "alerts": [a for a in result.alerts if a["important"] or not only_important],
            "new_post_count": len(result.alerts),
            "errors": result.errors,
        }
        if tracker.baseline:
            response["note"] = "First check of a course only records a baseline."
        return response

    @mcp.tool()
    @handle_ed_errors
    def get_recent_alerts(
        since: str = "7d", important_only: bool = True, limit: int = 50
    ) -> list[dict]:
        """Return recorded alerts since a time; use this to see alerts found by the watcher."""
        return get_store().recent_alerts(
            since=parse_time(since), important_only=important_only, limit=limit
        )

    @mcp.tool()
    @handle_ed_errors
    def get_alert_rules() -> dict:
        """Return the current scoring rules for important posts."""
        return get_store().get_rules().to_dict()

    @mcp.tool()
    @handle_ed_errors
    def update_alert_rules(
        keywords: list[str] | None = None,
        add_keywords: list[str] | None = None,
        remove_keywords: list[str] | None = None,
        categories: list[str] | None = None,
        watch_user_ids: list[int] | None = None,
        threshold: int | None = None,
        popular_votes: int | None = None,
    ) -> dict:
        """Update and return alert scoring rules; use to tune which posts matter."""
        state = get_store()
        rules = state.get_rules()
        if keywords is not None:
            rules.keywords = list(keywords)
        existing = {word.casefold() for word in rules.keywords}
        for word in add_keywords or []:
            if word.casefold() not in existing:
                rules.keywords.append(word)
                existing.add(word.casefold())
        removed = {word.casefold() for word in remove_keywords or []}
        rules.keywords = [word for word in rules.keywords if word.casefold() not in removed]
        for name, value in (
            ("categories", categories),
            ("watch_user_ids", watch_user_ids),
            ("threshold", threshold),
            ("popular_votes", popular_votes),
        ):
            if value is not None:
                setattr(rules, name, value)
        state.save_rules(rules)
        return rules.to_dict()

    @mcp.tool()
    @handle_ed_errors
    def reset_alert_cursor(course_id: int | None = None) -> dict:
        """Reset a course cursor, or all cursors, so the next check establishes a baseline."""
        get_store().reset_cursor(course_id)
        return {"reset": course_id if course_id is not None else "all"}
