"""Collect and render time-range discussion digests."""

from collections import Counter
from datetime import datetime

from ed_mcp import format as fmt
from ed_mcp.client import EdClient
from ed_mcp.timeutil import parse_ed_time, to_iso

OLDER_STREAK_STOP = 10


def collect_posts(
    client: EdClient,
    course_id: int,
    start: datetime,
    end: datetime,
    *,
    region: str,
    include_comments: bool = True,
    max_threads: int = 200,
    thread_chars: int = 800,
    comment_chars: int = 400,
) -> dict:
    """Collect threads created in the half-open interval [start, end)."""
    if max_threads < 1:
        raise ValueError("max_threads must be at least 1")
    records = []
    streak = scanned = 0
    truncated = False

    def truncate_comments(items: list[dict]) -> None:
        for item in items:
            item["body"] = fmt.truncate(item["body"], comment_chars)
            truncate_comments(item.get("replies", []))

    for thread in client.iter_threads(course_id, sort="new", max_threads=max_threads * 3 + 100):
        scanned += 1
        if not thread.get("created_at"):
            continue
        created = parse_ed_time(thread["created_at"])
        if created >= end:
            continue
        if created < start:
            if not thread.get("is_pinned"):
                streak += 1
                if streak >= OLDER_STREAK_STOP:
                    break
            continue
        streak = 0
        user = thread.get("user")
        users = {user["id"]: user} if user and "id" in user else {}
        record = fmt.compact_thread(thread, users, region, body_chars=thread_chars)
        if include_comments and (thread.get("reply_count") or 0) > 0:
            # Detail compaction applies body_chars to comments too, so use the larger
            # limit initially and then apply each limit independently.
            record = fmt.compact_thread_detail(client.get_thread(thread["id"]), region)
            record["body"] = fmt.truncate(record["body"], thread_chars)
            truncate_comments(record["answers"])
            truncate_comments(record["comments"])
        records.append(record)
        if len(records) >= max_threads:
            truncated = True
            break
    records.sort(key=lambda record: parse_ed_time(record["created_at"]))
    return {
        "course_id": course_id,
        "start": to_iso(start),
        "end": to_iso(end),
        "threads": records,
        "truncated": truncated,
        "scanned": scanned,
    }


def format_digest(result: dict, *, course_label: str, max_chars: int = 60000) -> str:
    """Render a digest within the character budget, including any footers."""
    threads = result["threads"]
    header = f"# {course_label}: posts from {result['start']} to {result['end']}"
    counts = Counter(t.get("type") or "unknown" for t in threads)
    categories = Counter(t["category"] for t in threads if t.get("category"))
    if threads:
        types = ", ".join(f"{count} {kind}" for kind, count in counts.most_common())
        cats = ", ".join(f"{name} ({count})" for name, count in categories.most_common(5)) or "none"
        header += f"\n{len(threads)} threads ({types}); categories: {cats}"
    else:
        header += "\nNo posts in this period."

    def comment_lines(item: dict, depth: int, answer: bool = False) -> list[str]:
        prefix = "  " * depth + "> "
        mark = "[answer] " if answer else ""
        endorsed = " ✓" if item.get("is_endorsed") else ""
        line = (
            f"{prefix}{mark}{item.get('author')} ({item.get('author_role') or 'unknown role'})"
            f": {item.get('body') or ''}{endorsed}"
        )
        return [line] + [
            line for child in item.get("replies", []) for line in comment_lines(child, depth + 1)
        ]

    blocks = []
    for thread in threads:
        flags = (" · PINNED" if thread.get("is_pinned") else "") + (
            " · answered" if thread.get("is_answered") else ""
        )
        lines = [
            f"## #{thread.get('number')} [{thread.get('type')}] {thread.get('title')}",
            f"{thread.get('author')} ({thread.get('author_role') or 'unknown role'}) · "
            f"{thread.get('created_at')} · {thread.get('reply_count')} replies · "
            f"{thread.get('vote_count')} votes{flags}",
            thread.get("url") or "",
            thread.get("body") or "",
        ]
        for answer in thread.get("answers", []):
            lines.extend(comment_lines(answer, 1, True))
        for comment in thread.get("comments", []):
            lines.extend(comment_lines(comment, 1))
        if thread.get("links"):
            lines.append("Links: " + ", ".join(link["url"] for link in thread["links"]))
        blocks.append("\n".join(lines))

    def render(n: int) -> str:
        parts = [header, *blocks[:n]]
        if n < len(blocks):
            parts.append(
                f"[{len(blocks) - n} more threads omitted; narrow the time range "
                "or set include_comments=false]"
            )
        if result.get("truncated"):
            parts.append(f"[stopped at max_threads={len(threads)}; more posts exist in this range]")
        return "\n\n".join(parts)

    for n in range(len(blocks), -1, -1):
        text = render(n)
        if len(text) <= max_chars:
            return text
    return render(0)[: max(0, max_chars)]
