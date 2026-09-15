"""Unit tests for ``bretzel.render.context``."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest

from bretzel.render.context import (
    RenderContext,
    current_context,
    maybe_current_context,
    use_context,
)

# ───────────────────────────────────────────────────────────────────────────
# Test fixtures — minimal app + request stand-ins
# ───────────────────────────────────────────────────────────────────────────


class _StubApp:
    def __init__(self) -> None:
        self._pages: list[Callable[..., Any]] = []
        self._realtime: dict[str, Callable[..., Any]] = {}
        self._error_handlers: dict[int, Callable[..., Any]] = {}

    @property
    def theme(self) -> object:
        return object()

    @property
    def state_backend(self) -> Any:
        return None

    @property
    def debug(self) -> bool:
        return True


def _ctx() -> RenderContext:
    """Build a minimal RenderContext for tests."""
    return RenderContext(app=_StubApp(), request=object())


# ───────────────────────────────────────────────────────────────────────────
# Defaults
# ───────────────────────────────────────────────────────────────────────────


class TestDefaults:
    def test_page_uuid_unique(self) -> None:
        # Each instance must get a fresh UUID — without this idiomorph
        # would conflate consecutive page renders (CR-3 from the spec).
        a = _ctx().page_uuid
        b = _ctx().page_uuid
        assert a != b
        assert len(a) == 32  # uuid4 hex is 32 chars

    def test_id_generator_isolated(self) -> None:
        ctx = _ctx()
        # Two ctx objects mean two independent counters.
        ctx2 = _ctx()
        ctx.id_generator.next("root", "btn")
        # Other context's generator is untouched.
        assert ctx2.id_generator.next("root", "btn") == "root_btn_0"

    def test_collections_start_empty(self) -> None:
        ctx = _ctx()
        assert ctx.parent_stack == []
        assert ctx.root_children == []
        assert ctx.client_state_payload == {}
        assert ctx.form_data == {}
        assert ctx.new_cookies == {}
        assert ctx.deleted_cookies == set()
        assert ctx.response_headers == {}
        assert ctx.head_extras == []
        assert ctx.cleanup_callbacks == []

    def test_pipeline_flags_default_false(self) -> None:
        ctx = _ctx()
        assert ctx.is_rendering is False
        assert ctx.is_partial is False
        assert ctx.is_action is False
        assert ctx.refreshable_target is None
        assert ctx.layout is None


# ───────────────────────────────────────────────────────────────────────────
# Context-var binding
# ───────────────────────────────────────────────────────────────────────────


class TestBinding:
    def test_outside_scope_raises(self) -> None:
        with pytest.raises(RuntimeError, match="No render context"):
            current_context()

    def test_outside_scope_maybe_returns_none(self) -> None:
        assert maybe_current_context() is None

    def test_inside_scope_returns_ctx(self) -> None:
        ctx = _ctx()
        with use_context(ctx):
            assert current_context() is ctx
            assert maybe_current_context() is ctx
        # Auto-cleared on exit.
        assert maybe_current_context() is None

    def test_nested_scopes_restore_on_exit(self) -> None:
        outer = _ctx()
        inner = _ctx()
        with use_context(outer):
            assert current_context() is outer
            with use_context(inner):
                assert current_context() is inner
            # Inner scope unbinds, outer comes back.
            assert current_context() is outer
        assert maybe_current_context() is None

    def test_concurrent_tasks_isolated(self) -> None:
        # ContextVar guarantees per-task isolation in async code.
        a, b = _ctx(), _ctx()
        results: dict[str, RenderContext] = {}

        async def task_a() -> None:
            with use_context(a):
                await asyncio.sleep(0)  # yield to task_b
                results["a"] = current_context()

        async def task_b() -> None:
            with use_context(b):
                await asyncio.sleep(0)
                results["b"] = current_context()

        async def main() -> None:
            await asyncio.gather(task_a(), task_b())

        asyncio.run(main())
        assert results["a"] is a
        assert results["b"] is b


# ───────────────────────────────────────────────────────────────────────────
# Cookie + header helpers
# ───────────────────────────────────────────────────────────────────────────


class TestCookieHelpers:
    def test_set_cookie(self) -> None:
        ctx = _ctx()
        ctx.set_cookie("auth", "abc", max_age=3600, httponly=True)
        assert ctx.new_cookies["auth"] == {
            "value": "abc",
            "max_age": 3600,
            "httponly": True,
        }

    def test_delete_cookie(self) -> None:
        ctx = _ctx()
        ctx.delete_cookie("auth")
        assert "auth" in ctx.deleted_cookies

    def test_set_then_delete_cancels_set(self) -> None:
        ctx = _ctx()
        ctx.set_cookie("auth", "abc")
        ctx.delete_cookie("auth")
        assert "auth" not in ctx.new_cookies
        assert "auth" in ctx.deleted_cookies

    def test_delete_then_set_cancels_delete(self) -> None:
        # Last write wins in either direction.
        ctx = _ctx()
        ctx.delete_cookie("auth")
        ctx.set_cookie("auth", "xyz")
        assert "auth" in ctx.new_cookies
        assert "auth" not in ctx.deleted_cookies


class TestHeader:
    def test_set_header(self) -> None:
        ctx = _ctx()
        ctx.set_header("HX-Trigger", "refresh")
        assert ctx.response_headers["HX-Trigger"] == "refresh"


# ───────────────────────────────────────────────────────────────────────────
# Cleanup callbacks
# ───────────────────────────────────────────────────────────────────────────


class TestCleanups:
    def test_lifo_order(self) -> None:
        ctx = _ctx()
        log: list[str] = []
        ctx.add_cleanup(lambda: log.append("first"))
        ctx.add_cleanup(lambda: log.append("second"))
        ctx.add_cleanup(lambda: log.append("third"))

        ctx.run_cleanups()
        # Last registered runs first (LIFO).
        assert log == ["third", "second", "first"]

    def test_runs_drains_list(self) -> None:
        ctx = _ctx()
        ctx.add_cleanup(lambda: None)
        ctx.run_cleanups()
        assert ctx.cleanup_callbacks == []

    def test_failing_callback_does_not_poison_rest(self) -> None:
        ctx = _ctx()
        log: list[str] = []
        ctx.add_cleanup(lambda: log.append("a"))

        def boom() -> None:
            raise RuntimeError("boom")

        ctx.add_cleanup(boom)
        ctx.add_cleanup(lambda: log.append("c"))

        ctx.run_cleanups()
        # 'c' (last registered) ran first, then boom raised but was
        # logged & swallowed, then 'a' ran. All callbacks attempted.
        assert log == ["c", "a"]
