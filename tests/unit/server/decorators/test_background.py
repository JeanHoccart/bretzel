"""Unit tests for ``@background`` semantics (no HTTP).

The end-to-end "runs after the response ships" path is covered in
``tests/integration/server/test_background.py`` ; here we pin the pure
contract : out-of-context ``schedule`` raises, in-context ``schedule``
enqueues onto the bound queue, direct call still runs the function.
"""

from __future__ import annotations

import asyncio

import pytest
from starlette.background import BackgroundTasks

from bretzel.server.decorators.background import (
    BackgroundContextError,
    BackgroundHandle,
    background,
    bind_background_tasks,
)


def test_background_returns_handle() -> None:
    @background
    def task() -> None:
        pass

    assert isinstance(task, BackgroundHandle)
    assert task.__name__ == "task"


def test_schedule_out_of_context_raises() -> None:
    @background
    def task(x: int) -> None:
        pass

    with pytest.raises(BackgroundContextError) as exc:
        task.schedule(x=1)
    # The hint points at the direct-await escape.
    assert "await" in str(exc.value)


def test_schedule_in_context_enqueues() -> None:
    @background
    def task(x: int) -> None:
        pass

    bg = BackgroundTasks()
    with bind_background_tasks(bg):
        task.schedule(x=42)
    assert len(bg.tasks) == 1
    assert bg.tasks[0].kwargs == {"x": 42}


def test_binding_is_scoped_and_resets() -> None:
    @background
    def task() -> None:
        pass

    bg = BackgroundTasks()
    with bind_background_tasks(bg):
        pass
    # After the with-block the queue is unbound again.
    with pytest.raises(BackgroundContextError):
        task.schedule()


def test_direct_call_runs_the_function() -> None:
    ran: list[int] = []

    @background
    async def task(x: int) -> None:
        ran.append(x)

    asyncio.run(task(7))
    assert ran == [7]
