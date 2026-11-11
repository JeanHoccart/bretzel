"""``Topic`` — ce qui n'est pas un état, une base ou un fichier, se suit par un sujet.

Une fonction qui lit se rattache au sujet par ``@reads``, une fonction qui
écrit par ``@writes``. Bretzel ne regarde pas le stockage : il ne connaît que
ces déclarations.
"""

from __future__ import annotations

import asyncio

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.render.decorators.refreshable import (
    enqueue_readers,
    refresh,
    refreshable,
    state_qualname,
)
from bretzel.runtime.protocol import DATA_SUBSCRIBE_STATE
from bretzel.server.feature import _classify_provide
from bretzel.state import AppState, Topic, field, reads, writes
from bretzel.state.persistence.memory import MemoryBackend
from bretzel.state.registry import StateRegistry, use_registry

calendar = Topic("calendar")
grades = Topic("grades")


@reads(calendar)
def read_calendar() -> str:
    return "calendar"


@reads(calendar, grades)
def read_both() -> str:
    return "both"


@writes(calendar)
def write_calendar(fail: bool = False) -> str:
    if fail:
        raise ValueError("nothing written")
    return "written"


@writes(grades)
def write_grades() -> None:
    return None


def _changed_by(action) -> set:  # type: ignore[no-untyped-def]
    registry = StateRegistry(MemoryBackend())
    with use_registry(registry):
        action()
        return set(registry.diff_and_notify())


class TestReads:
    def test_a_zone_calling_a_reader_follows_the_topic(self) -> None:
        @refreshable
        def zone() -> None:
            read_calendar()

        with render_isolated() as ctx:
            zone()
            assert set(zone.reads) == {calendar._revision}
            enqueue_readers(ctx, {calendar._revision: set()})
            assert zone in ctx.refresh_queue

    def test_a_zone_that_reads_something_else_is_left_alone(self) -> None:
        @refreshable
        def zone() -> None:
            read_both()

        @refreshable
        def other() -> None:
            pass

        with render_isolated() as ctx:
            zone()
            other()
            assert set(zone.reads) == {calendar._revision, grades._revision}
            enqueue_readers(ctx, {grades._revision: set()})
            assert zone in ctx.refresh_queue
            assert other not in ctx.refresh_queue

    def test_a_zone_can_read_a_topic_itself(self) -> None:
        @refreshable
        @reads(calendar)
        def zone() -> None:
            pass

        with render_isolated():
            zone()
        assert set(zone.reads) == {calendar._revision}

    def test_a_reader_stays_callable_outside_a_zone(self) -> None:
        assert read_calendar() == "calendar"

    def test_an_async_reader_is_awaited_and_followed(self) -> None:
        @reads(calendar)
        async def read() -> int:
            return 7

        assert asyncio.run(read()) == 7


class TestWrites:
    def test_a_write_rings_the_topic(self) -> None:
        assert calendar._revision in _changed_by(write_calendar)

    def test_it_rings_only_its_own_topic(self) -> None:
        assert grades._revision not in _changed_by(write_calendar)
        assert calendar._revision not in _changed_by(write_grades)

    def test_a_failed_write_rings_nothing(self) -> None:
        def attempt() -> None:
            with pytest.raises(ValueError):
                write_calendar(fail=True)

        assert calendar._revision not in _changed_by(attempt)

    def test_an_async_write_rings_after_it_finished(self) -> None:
        @writes(calendar)
        async def write() -> int:
            return 7

        def run() -> None:
            assert asyncio.run(write()) == 7

        assert calendar._revision in _changed_by(run)

    def test_a_generator_is_refused(self) -> None:
        """Its body runs after the call has returned: it would ring too soon."""
        with pytest.raises(TypeError, match="generator"):
            @writes(calendar)
            def write():  # type: ignore[no-untyped-def]
                yield 1


class TestRefresh:
    def test_refresh_rings_without_a_write(self) -> None:
        with render_isolated():
            assert calendar._revision in _changed_by(lambda: refresh(calendar))

    def test_refresh_outside_a_request_says_it_reaches_no_screen(self) -> None:
        with pytest.warns(RuntimeWarning, match="reaches no screen"):
            refresh(calendar)


class TestDeclaration:
    @pytest.mark.parametrize("decorator", [reads, writes])
    def test_nothing_but_a_topic_is_accepted(self, decorator) -> None:  # type: ignore[no-untyped-def]
        class NotATopic(AppState):
            rev: int = field(default=0)

        for wrong in ("calendar", NotATopic, 3):
            with pytest.raises(TypeError, match="Topic"):
                decorator(wrong)

    @pytest.mark.parametrize("decorator", [reads, writes])
    def test_a_topic_is_required(self, decorator) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(TypeError, match="at least one"):
            decorator()

    @pytest.mark.parametrize("decorator", [reads, writes])
    def test_the_function_keeps_its_identity(self, decorator) -> None:  # type: ignore[no-untyped-def]
        def my_function() -> None:
            """Its documentation."""

        wrapped = decorator(calendar)(my_function)
        assert wrapped.__name__ == "my_function"
        assert wrapped.__doc__ == "Its documentation."

    def test_a_name_that_cannot_name_a_class_is_refused(self) -> None:
        with pytest.raises(ValueError, match="identifier"):
            Topic("two words")

    def test_a_feature_lists_it_as_a_state(self) -> None:
        info = _classify_provide(calendar)
        assert (info.label, info.kind, info.module) == ("calendar", "state", __name__)

    def test_a_zone_reading_a_topic_listens_to_the_other_tabs(self) -> None:
        @refreshable
        @reads(calendar)
        def zone() -> None:
            pass

        with render_isolated():
            zone()
        attrs = zone.subscription(zone.reads)
        assert attrs[DATA_SUBSCRIBE_STATE] == state_qualname(calendar._revision)
