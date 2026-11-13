"""Ed Discussion HTTP client."""

import time
from collections.abc import Callable
from typing import Any, Literal

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
        self.token = token
        self.base_url = base_url if base_url.endswith("/") else f"{base_url}/"
        self.static_base_url = (
            static_base_url if static_base_url.endswith("/") else f"{static_base_url}/"
        )
        self.timeout = timeout
        self.transport = transport
        self.max_retries = max_retries
        self.sleep = sleep

    def close(self) -> None:
        pass

    def get_user(self) -> dict[str, Any]:
        raise NotImplementedError("Placeholder for task 2")
