"""Scan courses for newly posted threads."""

from dataclasses import dataclass
from datetime import UTC, datetime

from ed_mcp.client import EdAuthError, EdClient, EdError
from ed_mcp.config import Settings
from ed_mcp.content import ed_xml_to_text
from ed_mcp.format import author_name, author_role, thread_url, truncate, users_index
from ed_mcp.importance import score_thread
from ed_mcp.state import StateStore
from ed_mcp.timeutil import parse_ed_time, to_iso

SCAN_LIMIT = 300
OLD_STREAK_STOP = 20


@dataclass
class CheckResult:
    alerts: list[dict]
    errors: list[dict]
    auth_failed: bool = False


def default_store(settings: Settings) -> StateStore:
    return StateStore(settings.state_dir / "state.db")


def check_new_posts(
    client: EdClient,
    store: StateStore,
    *,
    region: str,
    course_ids: list[int] | None = None,
    backfill: int = 0,
    now: datetime | None = None,
) -> CheckResult:
    courses = {item["course"]["id"]: item["course"].get("code") for item in client.list_courses()}
    if course_ids is not None:
        courses = {cid: courses.get(cid) for cid in dict.fromkeys(course_ids)}
    rules = store.get_rules()
    detected_at = to_iso(now or datetime.now().astimezone())
    result = CheckResult([], [])
    for cid, code in courses.items():
        cursor = store.get_cursor(cid)
        try:
            seen = []
            new = []
            streak = 0
            for thread in client.iter_threads(cid, sort="new", max_threads=SCAN_LIMIT):
                tid = thread["id"]
                seen.append(tid)
                if cursor is None or tid > cursor:
                    new.append(thread)
                    streak = 0
                elif not thread.get("is_pinned"):
                    streak += 1
                    if streak >= OLD_STREAK_STOP:
                        break
            if cursor is None:
                new = sorted(new, key=lambda t: t["id"], reverse=True)[: max(0, backfill)]
            for thread in new:
                users = users_index([thread["user"]] if thread.get("user") else [])
                role = author_role(thread, users)
                score = score_thread(thread, role, rules)
                alert = {
                    "course_id": cid,
                    "course_code": code,
                    "thread_id": thread["id"],
                    "number": thread.get("number"),
                    "title": thread.get("title"),
                    "type": thread.get("type"),
                    "category": thread.get("category"),
                    "author": author_name(thread, users),
                    "author_role": role,
                    "url": thread_url(cid, thread["id"], region),
                    "snippet": truncate(ed_xml_to_text(thread.get("content")), 280),
                    "score": score.score,
                    "reasons": score.reasons,
                    "important": score.important,
                    "thread_created_at": thread.get("created_at"),
                    "detected_at": detected_at,
                }
                if store.record_alert(alert):
                    result.alerts.append(alert)
            if seen:
                store.set_cursor(cid, max(cursor or 0, max(seen)))
        except EdError as exc:
            if isinstance(exc, EdAuthError):
                result.auth_failed = True
            result.errors.append({"course_id": cid, "error": str(exc)})
    result.alerts.sort(
        key=lambda alert: (
            parse_ed_time(alert["thread_created_at"])
            if alert["thread_created_at"]
            else datetime.min.replace(tzinfo=UTC)
        )
    )
    return result
