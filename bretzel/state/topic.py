"""``Topic`` — a subject whose changes redraw the zones that read it.

A database, a file or an API is not a state, so no zone notices when it
changes. The functions that touch the data say so, whatever the storage::

    CALENDAR = Topic("calendar")

    @reads(CALENDAR)
    def calendars() -> list[dict]: ...      # a zone calling this follows the topic

    @writes(CALENDAR)
    def create_calendar(name: str) -> None: ...   # afterwards, those zones redraw

``refresh(CALENDAR)`` redraws them when nothing was written.
"""

from __future__ import annotations

import functools
import inspect
import sys
import types
from collections.abc import Callable
from typing import Any, TypeVar

from bretzel.core.tracking import TRACKER
from bretzel.state.fields.descriptor import field
from bretzel.state.scopes.server import ServerState

F = TypeVar("F", bound=Callable[..., Any])


def _nothing() -> None:
    return None


class Topic:
    """A named subject. Declare it once, at module level.

    It carries no data: under it, one app-wide counter, so that a change
    reaches other tabs and workers by the same road as any ``AppState``.
    """

    #: How a ``Feature`` recognises one without importing this layer.
    _bz_topic = True

    def __init__(self, name: str) -> None:
        if not name.isidentifier():
            raise ValueError(
                f"Topic({name!r}): the name must be a Python identifier, "
                f'such as Topic("calendar").'
            )
        self.__name__ = name
        self.__module__ = sys._getframe(1).f_globals.get("__name__", __name__)
        self._revision = types.new_class(
            f"Topic_{name}",
            (ServerState,),
            {"scope": "app"},
            lambda namespace: namespace.update(
                __module__=self.__module__,
                __qualname__=f"Topic_{name}",
                __doc__=f"The revision of the topic {name!r}.",
                __annotations__={"rev": int},
                rev=field(default=0, merge="add"),
            ),
        )

    def __repr__(self) -> str:
        return f"Topic({self.__name__!r})"

    def _ring(self) -> None:
        self._revision().rev += 1


def _checked(topics: tuple[Any, ...], decorator: str) -> None:
    if not topics:
        raise TypeError(f"@{decorator}() takes at least one Topic.")
    for topic in topics:
        if not isinstance(topic, Topic):
            raise TypeError(
                f"@{decorator}() takes Topic objects, got {topic!r}. "
                f'Declare one once: `CALENDAR = Topic("calendar")`.'
            )


def _around(
    fn: Callable[..., Any],
    before: Callable[[], None] = _nothing,
    after: Callable[[], None] = _nothing,
) -> Any:
    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def awaiting(*args: Any, **kwargs: Any) -> Any:
            before()
            result = await fn(*args, **kwargs)
            after()
            return result

        return awaiting

    @functools.wraps(fn)
    def calling(*args: Any, **kwargs: Any) -> Any:
        before()
        result = fn(*args, **kwargs)
        after()
        return result

    return calling


def reads(*topics: Topic) -> Callable[[F], F]:
    """A zone calling this function follows ``topics``.

    Outside a zone's render it does nothing, so the function stays callable
    from a handler or a script.
    """
    _checked(topics, "reads")

    def follow_them() -> None:
        for topic in topics:
            TRACKER.note_whole(topic._revision)

    def decorate(fn: F) -> F:
        return _around(fn, before=follow_them)

    return decorate


def writes(*topics: Topic) -> Callable[[F], F]:
    """Once this function has returned, the zones reading ``topics`` redraw.

    A function that raises rings nothing: it changed nothing to show.
    """
    _checked(topics, "writes")

    def ring_them() -> None:
        for topic in topics:
            topic._ring()

    def decorate(fn: F) -> F:
        if inspect.isgeneratorfunction(fn) or inspect.isasyncgenfunction(fn):
            raise TypeError(
                f"@writes() on the generator {fn.__qualname__}: its body runs "
                f"after the call has returned, so the topic would ring before "
                f"anything is written. Make it a plain function."
            )
        return _around(fn, after=ring_them)

    return decorate
