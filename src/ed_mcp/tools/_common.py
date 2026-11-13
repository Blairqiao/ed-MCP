"""Common tool utilities and error handling."""

import functools
import inspect
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp.exceptions import ToolError

from ed_mcp.client import EdError


def handle_ed_errors(fn: Callable) -> Callable:
    """Decorator that converts EdError and ValueError into ToolError."""
    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await fn(*args, **kwargs)
            except EdError as e:
                status_part = f" ({e.status})" if e.status is not None else ""
                raise ToolError(f"Ed API error{status_part}: {e.message}") from e
            except ValueError as e:
                raise ToolError(str(e)) from e

        return async_wrapper
    else:

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except EdError as e:
                status_part = f" ({e.status})" if e.status is not None else ""
                raise ToolError(f"Ed API error{status_part}: {e.message}") from e
            except ValueError as e:
                raise ToolError(str(e)) from e

        return sync_wrapper


def json_safe(obj: Any) -> Any:
    """Ensure obj is JSON safe."""
    return obj
