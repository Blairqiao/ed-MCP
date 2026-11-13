"""Read tools for Ed Discussion."""

from mcp.server.fastmcp import FastMCP

from ed_mcp.content import ed_xml_to_text, extract_links
from ed_mcp.context import AppContext
from ed_mcp.format import compact_thread, compact_thread_detail, thread_url, truncate, users_index
from ed_mcp.timeutil import parse_ed_time, parse_time
from ed_mcp.tools._common import handle_ed_errors

COURSE_KEYS = ("id", "code", "name", "year", "session", "status")
LESSON_KEYS = (
    "id",
    "title",
    "type",
    "kind",
    "status",
    "state",
    "module_id",
    "available_at",
    "due_at",
    "locked_at",
    "solutions_at",
    "created_at",
    "slide_count",
    "is_hidden",
    "openable",
)
RESOURCE_KEYS = (
    "id",
    "name",
    "category",
    "session",
    "link",
    "url",
    "created_at",
    "updated_at",
    "release_at",
)


def _courses(items: list[dict]) -> list[dict]:
    result = []
    for item in items:
        course = item.get("course") or {}
        role = item.get("role")
        result.append(
            {
                **{key: course.get(key) for key in COURSE_KEYS},
                "role": role.get("role") if isinstance(role, dict) else role,
            }
        )
    return result


def _categories(course: dict) -> list[dict] | None:
    categories = (course.get("settings") or {}).get("discussion") or {}
    categories = categories.get("categories")
    if categories is None:
        return None
    result = []
    for item in categories:
        entry = {"name": item.get("name")}
        if "subcategories" in item:
            entry["subcategories"] = [
                sub.get("name") if isinstance(sub, dict) else sub
                for sub in item.get("subcategories") or []
            ]
        result.append(entry)
    return result


def register_core_tools(mcp: FastMCP, ctx: AppContext) -> None:
    """Register read-only tools."""
    region = ctx.settings.region

    @mcp.tool()
    @handle_ed_errors
    def list_courses(include_archived: bool = False) -> list[dict]:
        """List courses and roles; start here to find course IDs."""
        return _courses(ctx.client.list_courses(include_archived))

    @mcp.tool()
    @handle_ed_errors
    def whoami() -> dict:
        """Return the current user and active courses."""
        payload = ctx.client.get_user()
        user = payload.get("user") or {}
        courses = [
            c
            for c in payload.get("courses", [])
            if (c.get("course") or {}).get("status") == "active"
        ]
        return {
            "user": {key: user.get(key) for key in ("id", "name", "email", "username")},
            "courses": _courses(courses),
        }

    @mcp.tool()
    @handle_ed_errors
    def get_course_info(course_id: int) -> dict:
        """Return course details and discussion categories."""
        course = ctx.client.get_course(course_id)
        categories = _categories(course)
        if categories is None:
            for item in ctx.client.list_courses(True):
                candidate = item.get("course") or {}
                if candidate.get("id") == course_id:
                    categories = _categories(candidate)
                    break
        return {
            "course": {key: course.get(key) for key in COURSE_KEYS},
            "categories": categories or [],
        }

    @mcp.tool()
    @handle_ed_errors
    def list_threads(
        course_id: int,
        limit: int = 30,
        offset: int = 0,
        category: str | None = None,
        thread_type: str | None = None,
        unanswered_only: bool = False,
        body_chars: int = 300,
    ) -> dict:
        """List a page of threads; filters apply only to the fetched page."""
        payload = ctx.client.list_threads(course_id, limit=limit, offset=offset)
        raw = payload.get("threads", [])
        users = users_index(payload.get("users"))
        selected = [
            t
            for t in raw
            if (category is None or (t.get("category") or "").lower() == category.lower())
            and (thread_type is None or t.get("type") == thread_type)
            and (not unanswered_only or (t.get("type") == "question" and not t.get("is_answered")))
        ]
        return {
            "threads": [compact_thread(t, users, region, body_chars=body_chars) for t in selected],
            "next_offset": offset + len(raw) if len(raw) == min(100, max(1, limit)) else None,
        }

    @mcp.tool()
    @handle_ed_errors
    def get_thread(
        thread_id: int | None = None,
        course_id: int | None = None,
        number: int | None = None,
        body_chars: int | None = None,
    ) -> dict:
        """Return a thread, its comments and links by global ID or course number."""
        if thread_id is not None:
            payload = ctx.client.get_thread(thread_id)
        elif course_id is not None and number is not None:
            payload = ctx.client.get_course_thread(course_id, number)
        else:
            raise ValueError("Provide thread_id or both course_id and number")
        return compact_thread_detail(payload, region, body_chars=body_chars)

    @mcp.tool()
    @handle_ed_errors
    def search_threads(course_id: int, query: str, limit: int = 20) -> list[dict]:
        """Search a course and return compact matching threads."""
        payload = ctx.client.search_threads(course_id, query, limit=limit)
        users = users_index(payload.get("users"))
        return [
            compact_thread(t, users, region, body_chars=300) for t in payload.get("threads", [])
        ]

    @mcp.tool()
    @handle_ed_errors
    def list_announcements(course_id: int, limit: int = 20) -> list[dict]:
        """Return up to limit recent announcements with full text."""
        result = []
        if limit <= 0:
            return result
        for thread in ctx.client.iter_threads(course_id, max_threads=500):
            if thread.get("type") == "announcement":
                result.append(compact_thread(thread, {}, region, body_chars=None))
                if len(result) >= limit:
                    break
        return result

    @mcp.tool()
    @handle_ed_errors
    def get_links(
        course_id: int,
        thread_id: int | None = None,
        since: str | None = None,
        max_threads: int = 100,
    ) -> list[dict]:
        """Find links in thread bodies; provide thread_id to include comments and answers."""
        if thread_id is not None:
            detail = compact_thread_detail(ctx.client.get_thread(thread_id), region)
            return [
                {
                    **link,
                    "thread_id": detail["id"],
                    "thread_title": detail["title"],
                    "thread_url": detail["url"],
                }
                for link in detail["links"]
            ]
        cutoff = parse_time(since) if since is not None else None
        result = []
        for thread in ctx.client.iter_threads(course_id, max_threads=max_threads):
            if (
                cutoff is not None
                and thread.get("created_at")
                and parse_ed_time(thread["created_at"]) < cutoff
            ):
                continue
            result.extend(
                {
                    **link,
                    "thread_id": thread.get("id"),
                    "thread_title": thread.get("title"),
                    "thread_url": thread_url(course_id, thread.get("id"), region),
                }
                for link in extract_links(thread.get("content"))
            )
        return result

    @mcp.tool()
    @handle_ed_errors
    def list_course_users(course_id: int, role: str | None = None) -> list[dict]:
        """List course users, optionally filtered by role."""
        return [
            {key: user.get(key) for key in ("id", "name", "email", "course_role")}
            for user in ctx.client.list_course_users(course_id)
            if role is None or (user.get("course_role") or "").lower() == role.lower()
        ]

    @mcp.tool()
    @handle_ed_errors
    def get_user_activity(course_id: int, user_id: int, limit: int = 30) -> list[dict]:
        """Return a user's course activity with compact plain-text content."""
        items = ctx.client.get_user_activity(user_id, course_id, limit=limit)
        return [
            {
                **item,
                **(
                    {"content": truncate(ed_xml_to_text(item["content"]), 300)}
                    if "content" in item
                    else {}
                ),
            }
            for item in items
        ]

    @mcp.tool()
    @handle_ed_errors
    def list_lessons(course_id: int) -> list[dict]:
        """List lessons to find requirements, readings and due dates."""
        payload = ctx.client.list_lessons(course_id)
        modules = {module.get("id"): module.get("name") for module in payload.get("modules", [])}
        return [
            {
                **{key: lesson[key] for key in LESSON_KEYS if key in lesson},
                "module": modules.get(lesson.get("module_id")),
            }
            for lesson in payload.get("lessons", [])
        ]

    @mcp.tool()
    @handle_ed_errors
    def get_lesson(
        lesson_id: int, include_slide_content: bool = True, content_chars: int | None = 4000
    ) -> dict:
        """Return lesson details, slides and links for reading course material."""
        lesson = ctx.client.get_lesson(lesson_id)
        slides = []
        links = []
        seen = set()
        for slide in lesson.get("slides", []) or []:
            entry = {key: slide.get(key) for key in ("id", "title", "type", "index")}
            if include_slide_content:
                entry["content"] = truncate(ed_xml_to_text(slide.get("content")), content_chars)
            slides.append(entry)
            for link in extract_links(slide.get("content")):
                if link["url"] not in seen:
                    links.append(link)
                    seen.add(link["url"])
        return {
            **{key: lesson[key] for key in LESSON_KEYS if key in lesson},
            "slides": slides,
            "links": links,
        }

    @mcp.tool()
    @handle_ed_errors
    def list_resources(course_id: int) -> list[dict]:
        """List course resources and their URLs."""
        return [
            {key: resource[key] for key in RESOURCE_KEYS if key in resource}
            for resource in ctx.client.list_resources(course_id)
        ]
