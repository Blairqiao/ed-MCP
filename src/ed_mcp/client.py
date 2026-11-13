"""Synchronous Ed Discussion HTTP client."""

import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Literal, get_args

import httpx


class EdError(Exception):
    def __init__(self, message: str, *, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


class EdAuthError(EdError):
    pass


class EdNotFoundError(EdError):
    pass


class EdRateLimitError(EdError):
    pass


ThreadAction = Literal[
    "lock", "unlock", "pin", "unpin", "endorse", "unendorse", "star", "unstar", "watch", "unwatch"
]
CommentAction = Literal["endorse", "unendorse"]


class EdClient:
    def __init__(
        self,
        token: str,
        base_url: str = "https://us.edstem.org/api/",
        *,
        static_base_url: str = "https://static.us.edusercontent.com/files/",
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._token = token
        self.base_url = base_url.rstrip("/") + "/"
        self.static_base_url = static_base_url.rstrip("/") + "/"
        self.max_retries = max_retries
        self._sleep = sleep
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _redact(self, value: str) -> str:
        return value.replace(self._token, "[REDACTED]") if self._token else value

    def _request(self, method: str, path: str, *, params=None, json=None, files=None) -> Any:
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.request(
                    method, self.base_url + path, params=params, json=json, files=files
                )
            except httpx.RequestError as exc:
                raise EdError(self._redact(f"{method} {path}: {exc}")) from None
            try:
                payload = response.json() if response.content else None
            except ValueError:
                if response.is_success:
                    raise
                payload = None
            error_payload = payload if isinstance(payload, dict) else {}
            code = error_payload.get("code")
            if (
                code != "bad_token"
                and (response.status_code == 429 or response.status_code >= 500)
                and attempt < self.max_retries
            ):
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after is not None else float(2**attempt)
                except ValueError:
                    try:
                        date = parsedate_to_datetime(retry_after)
                        if date.tzinfo is None:
                            date = date.replace(tzinfo=UTC)
                        delay = (date - datetime.now(UTC)).total_seconds()
                    except (TypeError, ValueError, OverflowError):
                        delay = float(2**attempt)
                self._sleep(max(0.0, delay))
                continue
            if not response.is_success or code == "bad_token":
                message = self._redact(
                    f"{method} {path}: {response.status_code} {error_payload.get('message', '')}"
                )
                safe_code = self._redact(str(code)) if code is not None else None
                error = (
                    EdAuthError
                    if response.status_code == 401 or code == "bad_token"
                    else EdNotFoundError
                    if response.status_code == 404
                    else EdRateLimitError
                    if response.status_code == 429
                    else EdError
                )
                raise error(message, status=response.status_code, code=safe_code)
            return payload
        raise AssertionError("unreachable")

    def get_user(self) -> dict:
        return self._request("GET", "user")

    def list_courses(self, include_archived: bool = False) -> list[dict]:
        courses = self.get_user().get("courses", [])
        return (
            courses
            if include_archived
            else [c for c in courses if c.get("course", {}).get("status") == "active"]
        )

    def get_course(self, course_id: int) -> dict:
        payload = self._request("GET", f"courses/{course_id}")
        return payload.get("course", payload)

    def list_course_users(self, course_id: int) -> list[dict]:
        try:
            payload = self._request("GET", f"courses/{course_id}/users")
        except EdError as exc:
            if exc.status not in (403, 404):
                raise
            payload = self._request("GET", f"courses/{course_id}/analytics/users")
        return payload.get("users", [])

    def get_user_activity(
        self, user_id: int, course_id: int, *, limit: int = 30, offset: int = 0, filter: str = "all"
    ) -> list[dict]:
        payload = self._request(
            "GET",
            f"users/{user_id}/profile/activity",
            params={
                "courseID": course_id,
                "limit": min(50, max(1, limit)),
                "offset": offset,
                "filter": filter,
            },
        )
        return payload.get("items", [])

    def list_threads(
        self, course_id: int, *, limit: int = 30, offset: int = 0, sort: str = "new"
    ) -> dict:
        return self._request(
            "GET",
            f"courses/{course_id}/threads",
            params={"limit": min(100, max(1, limit)), "offset": offset, "sort": sort},
        )

    def iter_threads(
        self,
        course_id: int,
        *,
        page_size: int = 100,
        sort: str = "new",
        max_threads: int | None = None,
    ) -> Iterator[dict]:
        page_size = min(100, max(1, page_size))
        offset = 0
        while max_threads is None or offset < max_threads:
            payload = self.list_threads(course_id, limit=page_size, offset=offset, sort=sort)
            threads = payload.get("threads", [])
            users = {user.get("id"): user for user in payload.get("users", [])}
            for thread in threads:
                if max_threads is not None and offset >= max_threads:
                    return
                yield {
                    **thread,
                    "user": thread["user"]
                    if "user" in thread
                    else users.get(thread.get("user_id")),
                }
                offset += 1
            if len(threads) < page_size:
                return

    def get_thread(self, thread_id: int) -> dict:
        return self._request("GET", f"threads/{thread_id}")

    def get_course_thread(self, course_id: int, number: int) -> dict:
        return self._request("GET", f"courses/{course_id}/threads/{number}")

    def search_threads(self, course_id: int, query: str, *, limit: int = 30) -> dict:
        return self._request(
            "GET", f"courses/{course_id}/threads/search", params={"query": query, "limit": limit}
        )

    def post_thread(
        self,
        course_id: int,
        *,
        title: str,
        content_xml: str,
        type: str = "post",
        category: str = "",
        subcategory: str = "",
        subsubcategory: str = "",
        is_private: bool = False,
        is_anonymous: bool = False,
        is_pinned: bool = False,
        is_megathread: bool = False,
        anonymous_comments: bool = False,
    ) -> dict:
        thread = {
            "title": title,
            "content": content_xml,
            "type": type,
            "category": category,
            "subcategory": subcategory,
            "subsubcategory": subsubcategory,
            "is_private": is_private,
            "is_anonymous": is_anonymous,
            "is_pinned": is_pinned,
            "is_megathread": is_megathread,
            "anonymous_comments": anonymous_comments,
        }
        return self._request("POST", f"courses/{course_id}/threads", json={"thread": thread})[
            "thread"
        ]

    def edit_thread(self, thread_id: int, **fields: Any) -> dict:
        allowed = {
            "title",
            "content",
            "type",
            "category",
            "subcategory",
            "subsubcategory",
            "is_private",
            "is_anonymous",
            "is_pinned",
            "is_megathread",
            "anonymous_comments",
        }
        unknown = fields.keys() - allowed
        if unknown:
            raise ValueError(f"Unknown thread fields: {', '.join(sorted(unknown))}")
        thread = {
            k: v
            for k, v in self.get_thread(thread_id)["thread"].items()
            if k not in {"answers", "comments", "user"}
        }
        thread.update({k: v for k, v in fields.items() if v is not None})
        return self._request("PUT", f"threads/{thread_id}", json={"thread": thread})["thread"]

    def delete_thread(self, thread_id: int) -> None:
        self._request("DELETE", f"threads/{thread_id}")

    def thread_action(self, thread_id: int, action: ThreadAction) -> None:
        if action not in get_args(ThreadAction):
            raise ValueError(f"Unknown thread action: {action}")
        self._request("POST", f"threads/{thread_id}/{action}")

    def post_comment(
        self,
        thread_id: int,
        content_xml: str,
        *,
        type: Literal["comment", "answer"] = "comment",
        is_private: bool = False,
        is_anonymous: bool = False,
    ) -> dict:
        return self._request(
            "POST",
            f"threads/{thread_id}/comments",
            json={
                "comment": {
                    "type": type,
                    "content": content_xml,
                    "is_private": is_private,
                    "is_anonymous": is_anonymous,
                }
            },
        )["comment"]

    def reply_to_comment(
        self,
        comment_id: int,
        content_xml: str,
        *,
        is_private: bool = False,
        is_anonymous: bool = False,
    ) -> dict:
        return self._request(
            "POST",
            f"comments/{comment_id}/comments",
            json={
                "comment": {
                    "type": "comment",
                    "content": content_xml,
                    "is_private": is_private,
                    "is_anonymous": is_anonymous,
                }
            },
        )["comment"]

    def edit_comment(self, comment_id: int, content_xml: str) -> dict:
        payload = self._request(
            "PUT", f"comments/{comment_id}", json={"comment": {"content": content_xml}}
        )
        return payload.get("comment", payload)

    def delete_comment(self, comment_id: int) -> None:
        self._request("DELETE", f"comments/{comment_id}")

    def comment_action(self, comment_id: int, action: CommentAction) -> None:
        if action not in get_args(CommentAction):
            raise ValueError(f"Unknown comment action: {action}")
        self._request("POST", f"comments/{comment_id}/{action}")

    def accept_answer(self, thread_id: int, comment_id: int) -> None:
        self._request("POST", f"threads/{thread_id}/accept/{comment_id}")

    def list_lessons(self, course_id: int) -> dict:
        return self._request("GET", f"courses/{course_id}/lessons")

    def get_lesson(self, lesson_id: int) -> dict:
        return self._request("GET", f"lessons/{lesson_id}")["lesson"]

    def get_slide(self, slide_id: int) -> dict:
        return self._request("GET", f"lessons/slides/{slide_id}")["slide"]

    def list_resources(self, course_id: int) -> list[dict]:
        return self._request("GET", f"courses/{course_id}/resources").get("resources", [])

    def upload_file(self, filename: str, data: bytes, content_type: str) -> str:
        payload = self._request(
            "POST", "files", files={"attachment": (filename, data, content_type)}
        )
        return self.static_base_url + str(payload["file"]["id"])
