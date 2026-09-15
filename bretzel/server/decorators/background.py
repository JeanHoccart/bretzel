"""``@background`` — fire-and-forget after-response work.

Wraps Starlette's :class:`BackgroundTasks` with a tiny typed handle. A
handler calls ``my_task.schedule(**kwargs)`` and the task runs **after**
the current request's HTTP response has shipped. Starlette awaits async
functions and runs synchronous functions in its threadpool.

The current request's :class:`BackgroundTasks` is exposed through a
request-scoped :class:`~contextvars.ContextVar` that the action route
binds for the duration of handler dispatch (:func:`bind_background_tasks`)
— no global mutable state, the queue is per-request like the state
registry. Out-of-context ``schedule`` raises
:class:`BackgroundContextError`, pointing at the direct-await escape for
contexts with no live request (cron, startup hooks, external workers).

What this is **not** (``.claude/bretzel/handlers.md`` § *background*) : not a job
queue with retries / persistence, not scheduled / periodic by itself,
not a substitute for ``@refreshable(..., broadcast=[State])``. It is best-effort
after-response work (emails, analytics, cache warmup, a one-shot SSE
animation loop). A raising task is logged by Starlette but never crashes
the worker — the response already shipped.

"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from starlette.background import BackgroundTasks

# Per-request background queue. ``None`` outside a request → ``schedule``
# raises rather than silently dropping the task.
_CURRENT: ContextVar[BackgroundTasks | None] = ContextVar(
    "bretzel_current_background", default=None
)


class BackgroundContextError(RuntimeError):
    """Raised when ``.schedule()`` runs with no live request bound."""


@contextmanager
def bind_background_tasks(tasks: BackgroundTasks) -> Iterator[None]:
    """Bind ``tasks`` as the current request's background queue.

    Called by the action route around handler dispatch ; the bound
    queue is attached to the response so Starlette drains it after the
    body is sent.
    """
    token = _CURRENT.set(tasks)
    try:
        yield
    finally:
        _CURRENT.reset(token)


class BackgroundHandle:
    """Returned by :func:`background`. ``.schedule(**kwargs)`` enqueues the
    wrapped function onto the current request's background queue ; calling
    the handle directly (``await handle(**kwargs)``) just runs the
    function — the escape for contexts with no request."""

    def __init__(self, fn: Callable[..., Any]) -> None:
        self.fn = fn
        self.__name__ = getattr(fn, "__name__", "background_task")
        self.__qualname__ = getattr(fn, "__qualname__", self.__name__)
        self.__doc__ = fn.__doc__

    def schedule(self, **kwargs: Any) -> None:
        """Enqueue this task on the current request.

        Must run inside a request (an ``on_click`` handler). Out of
        context raises :class:`BackgroundContextError`.
        """
        tasks = _CURRENT.get()
        if tasks is None:
            raise BackgroundContextError(
                f"{self.__qualname__}.schedule() needs a live request — "
                "call it from inside an action / on_click handler. Outside "
                "a request (cron, startup, external worker) await the "
                f"function directly: await {self.__qualname__}(**kwargs)."
            )
        tasks.add_task(self.fn, **kwargs)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Direct invocation — runs the wrapped function as-is."""
        return self.fn(*args, **kwargs)


def background(fn: Callable[..., Any]) -> BackgroundHandle:
    """Mark ``fn`` as an after-response background task.

    Usage ::

        from bretzel import background

        @background
        async def send_welcome_email(user_id: str):
            await email_client.send(...)

        def signup_handler():
            user = save_to_db(...)
            send_welcome_email.schedule(user_id=user.id)
            # returns immediately ; the email runs after the response ships.
    """
    return BackgroundHandle(fn)
