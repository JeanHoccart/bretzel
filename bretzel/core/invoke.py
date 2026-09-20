"""Call APPLICATION code without ever blocking the event loop.

An action handler, a page body, the body of a ``@refreshable`` zone, the
``rows=`` of an export, the function behind a ``@download``, the callback
of an ``@auth.door`` gate, a lifecycle hook — all of it is written by the
app author, and the framework calls it. Charter principle 7 says
"async-only", but the product's real idiom is the opposite: measured on
2026-09-04, ``examples/`` holds **1 659 ``def`` against 16 ``async def``**
— because ``state.counter += 1`` has nothing to wait for, and demanding an
``async`` for that would be empty ceremony.

A ``def`` called as-is from a coroutine runs **in the loop thread**. As
long as it only does arithmetic on state, that is the right choice. The
day it calls a synchronous database, ``requests.get`` or ``time.sleep``,
it freezes the worker's event loop: no more HTTP request served, no more
SSE heartbeat, for ALL other users — and nothing raises, nothing shows,
the outage reads as "the server went down".

Hence :func:`call_without_blocking`. An ``async def`` is awaited
directly; **anything else** is offloaded onto the threadpool Starlette
already uses (``anyio.to_thread``), the way FastAPI treats a non-async
route. The developer declares nothing, so there is nothing to FORGET to
declare — that is the point: the failure mode being replaced is invisible
until production.

**What it costs**, measured in-process A/B alternation on 2026-09-04: the
thread hop is worth **0.19 ms** (p95 0.78) against 0.003 ms for the direct
call, on a minimal action round-trip that weighs **2.90** (p95 5.02). A
page render pays one per body — every layout in the chain, the page, then
flattening the tree — so three for a single-layout page; the
``@refreshable`` zones the body calls are free: they run in their caller's
thread.

**Why not ``starlette.concurrency.run_in_threadpool``**, which does
exactly these two lines: because it would mean importing the web framework
into layer 0. So its body is reproduced deliberately — if it changes the
way it enters the pool, this copy must follow. :func:`_is_async_callable`
likewise duplicates ``is_async_callable`` from ``starlette._utils``, whose
module is **private**: that is a choice, not an oversight.

**What it changes for ``ContextVar``**: ``anyio`` COPIES the current
context into the thread, so everything the framework set before the call
(the render context, the state registry, the background task queue) reads
normally. A ``set()`` made INSIDE the thread, however, does not travel
back. None of our ``ContextVar`` are affected: they are all set then
restored by a balanced context manager, and the state that must outlive
the call lives on OBJECTS (``RenderContext``, ``StateRegistry``)
which the thread mutates for good.

⚠️ **What it changes for CONCURRENCY, and this has to be read.** A ``def``
used to be serialised by construction: the loop being single-threaded, two
handlers could not run at the same time. They can now, up to 40 abreast.
The ``state.counter += 1`` used as an example above is a read then a
write: on a shared :class:`~bretzel.state.AppState`, two simultaneous
requests can now lose an increment **inside a single worker**, where it
previously took two workers for that. This is not a regression of the
offload — the same loss already existed between two processes, and the
missing optimistic lock at commit time is tracked separately in
``.claude/work/todo.md`` — but the offload makes it reachable locally, and
therefore reproducible.

**The ceiling becomes the pool**, 40 threads by default in ``anyio``: 41
simultaneous blocking handlers make the 41st wait. That is the standard
trade-off, and it stays out of all proportion with a frozen loop — there,
it is the WHOLE worker that stops, including the requests that asked for
nothing.

``anyio`` ships with starlette: this module adds no dependency (same
reason as in ``server/oauth.py``).
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any

import anyio.to_thread

__all__ = ["call_without_blocking"]


def _is_async_callable(fn: Any) -> bool:
    """``True`` when calling ``fn`` returns a coroutine to await.

    ``iscoroutinefunction`` unwraps ``functools.partial`` on its own (a
    handler with bound arguments is one). The second test covers
    callables that are not functions — an object whose ``__call__`` is
    ``async``; it spares them a needless thread hop, correctness being
    guaranteed anyway by the ``iscoroutine`` check in
    :func:`call_without_blocking`.
    """
    return inspect.iscoroutinefunction(fn) or inspect.iscoroutinefunction(
        getattr(fn, "__call__", None)  # noqa: B004 — the attribute is the point
    )


async def call_without_blocking(
    fn: Callable[..., Any], /, *args: Any, **kwargs: Any
) -> Any:
    """Call ``fn`` without blocking the event loop."""
    if _is_async_callable(fn):
        return await fn(*args, **kwargs)
    result = await anyio.to_thread.run_sync(functools.partial(fn, *args, **kwargs))
    if inspect.iscoroutine(result):
        result = await result
    return result
