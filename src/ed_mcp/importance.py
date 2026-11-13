"""Transparent rules for scoring new threads."""

from dataclasses import asdict, dataclass, field

from ed_mcp.content import ed_xml_to_text
from ed_mcp.format import STAFF_ROLES

DEFAULT_KEYWORDS = [
    "exam",
    "midterm",
    "final",
    "deadline",
    "due",
    "extension",
    "quiz",
    "assignment",
    "homework",
    "project",
    "cancel",
    "reschedul",
    "postpone",
    "grade",
    "regrade",
    "important",
    "urgent",
    "required",
    "mandatory",
    "room change",
    "office hours",
]
DEFAULT_WEIGHTS = {
    "announcement": 5,
    "pinned": 3,
    "staff_author": 3,
    "keyword": 2,
    "category": 2,
    "watched_user": 3,
    "popular": 1,
}


@dataclass
class AlertRules:
    keywords: list[str] = field(default_factory=lambda: list(DEFAULT_KEYWORDS))
    categories: list[str] = field(default_factory=list)
    watch_user_ids: list[int] = field(default_factory=list)
    threshold: int = 3
    popular_votes: int = 5
    weights: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AlertRules":
        values = {key: value for key, value in d.items() if key in cls.__dataclass_fields__}
        values["weights"] = {**DEFAULT_WEIGHTS, **values.get("weights", {})}
        return cls(**values)


@dataclass
class Score:
    score: int
    reasons: list[str]
    important: bool


def score_thread(thread: dict, author_role: str | None, rules: AlertRules) -> Score:
    score = 0
    reasons = []

    def add(weight: str, reason: str) -> None:
        nonlocal score
        score += rules.weights[weight]
        reasons.append(reason)

    if thread.get("type") == "announcement":
        add("announcement", "announcement")
    if thread.get("is_pinned"):
        add("pinned", "pinned")
    role = author_role.lower() if author_role else None
    if role in STAFF_ROLES:
        add("staff_author", f"posted by {role}")
    text = f"{thread.get('title') or ''} {ed_xml_to_text(thread.get('content'))}".lower()
    matched = [keyword for keyword in rules.keywords if keyword.lower() in text][:3]
    if matched:
        score += rules.weights["keyword"] * len(matched)
        reasons.append(f"keywords: {', '.join(matched)}")
    categories = {category.lower() for category in rules.categories}
    for cat in (thread.get("category"), thread.get("subcategory")):
        if cat and cat.lower() in categories:
            add("category", f"category: {cat}")
            break
    if not thread.get("is_anonymous") and thread.get("user_id") in rules.watch_user_ids:
        add("watched_user", "watched user")
    votes = thread.get("vote_count") or 0
    if votes >= rules.popular_votes:
        add("popular", f"{votes} votes")
    return Score(score, reasons, score >= rules.threshold)
