"""Compact Ed API responses for tools."""

from ed_mcp.content import ed_xml_to_text, extract_links

STAFF_ROLES = frozenset({"admin", "staff", "mentor", "tutor", "instructor", "ta"})


def users_index(users: list[dict] | None) -> dict[int, dict]:
    return {user["id"]: user for user in users or [] if "id" in user}


def thread_url(course_id: int, thread_id: int, region: str) -> str:
    return f"https://edstem.org/{region}/courses/{course_id}/discussion/{thread_id}"


def _author(obj: dict, users_by_id: dict[int, dict]) -> dict:
    return users_by_id.get(obj.get("user_id")) or obj.get("user") or {}


def author_name(obj: dict, users_by_id: dict[int, dict]) -> str:
    if obj.get("is_anonymous"):
        return "Anonymous"
    return (
        users_by_id.get(obj.get("user_id"), {}).get("name")
        or (obj.get("user") or {}).get("name")
        or f"user {obj.get('user_id')}"
    )


def author_role(obj: dict, users_by_id: dict[int, dict]) -> str | None:
    return None if obj.get("is_anonymous") else _author(obj, users_by_id).get("course_role")


def truncate(text: str, limit: int | None) -> str:
    return text if limit is None or len(text) <= limit else text[:limit] + "…"


def compact_thread(
    thread: dict, users_by_id: dict[int, dict], region: str, *, body_chars: int | None = 500
) -> dict:
    keys = (
        "id",
        "number",
        "course_id",
        "title",
        "type",
        "category",
        "subcategory",
        "created_at",
        "updated_at",
        "is_pinned",
        "is_private",
        "is_answered",
        "is_staff_answered",
        "is_endorsed",
        "reply_count",
        "vote_count",
        "view_count",
    )
    result = {key: thread.get(key) for key in keys}
    result.update(
        author=author_name(thread, users_by_id),
        author_role=author_role(thread, users_by_id),
        url=thread_url(thread.get("course_id"), thread.get("id"), region),
        body=truncate(ed_xml_to_text(thread.get("content")), body_chars),
    )
    return result


def compact_comment(
    comment: dict, users_by_id: dict[int, dict], *, body_chars: int | None = None
) -> dict:
    keys = ("id", "type", "created_at", "is_endorsed", "is_private", "vote_count")
    result = {key: comment.get(key) for key in keys}
    result.update(
        author=author_name(comment, users_by_id),
        author_role=author_role(comment, users_by_id),
        body=truncate(ed_xml_to_text(comment.get("content")), body_chars),
        replies=[
            compact_comment(reply, users_by_id, body_chars=body_chars)
            for reply in comment.get("comments", []) or []
        ],
    )
    return result


def compact_thread_detail(payload: dict, region: str, *, body_chars: int | None = None) -> dict:
    thread = payload["thread"]
    users = users_index(payload.get("users"))
    result = compact_thread(thread, users, region, body_chars=body_chars)
    result["answers"] = [
        compact_comment(item, users, body_chars=body_chars)
        for item in thread.get("answers", []) or []
    ]
    result["comments"] = [
        compact_comment(item, users, body_chars=body_chars)
        for item in thread.get("comments", []) or []
    ]
    links = []
    seen = set()

    def collect(item):
        for link in extract_links(item.get("content")):
            if link["url"] not in seen:
                links.append(link)
                seen.add(link["url"])
        for reply in item.get("comments", []) or []:
            collect(reply)

    collect(thread)
    for answer in thread.get("answers", []) or []:
        collect(answer)
    result["links"] = links
    return result
