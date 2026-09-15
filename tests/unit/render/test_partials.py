"""Unit tests for ``bretzel.render.partials``."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from bretzel.core.tree import Element, TextNode
from bretzel.render.context import RenderContext
from bretzel.render.decorators.refreshable import refreshable
from bretzel.render.partials import (
    RenderResult,
    drain_refresh_queue,
    render_partial,
)
from bretzel.runtime.protocol import (
    BZ_ID_ATTR,
    PATCH_TAG_NAME,
)
from bretzel.state import field
from bretzel.state.persistence.memory import MemoryBackend
from bretzel.state.registry import StateRegistry, use_registry
from bretzel.state.scopes.client import ClientState


def run[T](coro: Awaitable[T]) -> T:
    return asyncio.new_event_loop().run_until_complete(coro)


# ───────────────────────────────────────────────────────────────────────────
# Stub app + ctx helper
# ───────────────────────────────────────────────────────────────────────────


class _StubApp:
    def __init__(self) -> None:
        self._pages: list[Callable[..., Any]] = []
        self._realtime: dict[str, Any] = {}
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


def _build_ctx(app: _StubApp, registry: StateRegistry | None = None) -> RenderContext:
    return RenderContext(
        app=app,
        request=object(),
        state_registry=registry,
    )


# ───────────────────────────────────────────────────────────────────────────
# Single-section render
# ───────────────────────────────────────────────────────────────────────────


class TestSingleSection:
    def test_renders_returned_node(self) -> None:
        app = _StubApp()

        def section() -> Element:
            return Element("div", {"class": "card"}, (TextNode("hi"),))

        handle = refreshable(section)
        ctx = _build_ctx(app)

        result = run(render_partial(app, handle, ctx=ctx))
        assert isinstance(result, RenderResult)
        # Section produced one Element root → fusion splices framework
        # attrs onto it (no extra <div>).
        assert "<div" in result.body
        assert f'{BZ_ID_ATTR}="{handle.id}"' in result.body
        assert f'id="{handle.id}"' in result.body
        # V3 : no bz-version stamp — scope state survives morphs via
        # the runtime's bz-id-keyed Map, no version guard needed.
        assert "bz-version" not in result.body
        assert ">hi<" in result.body

    def test_renders_multiple_root_children(self) -> None:
        # Multiple Nodes accumulated in ctx.root_children → wrapper div.
        app = _StubApp()

        def section() -> None:
            from bretzel.render.context import current_context

            ctx = current_context()
            ctx.root_children.append(Element("a"))
            ctx.root_children.append(Element("b"))

        handle = refreshable(section)
        ctx = _build_ctx(app)
        result = run(render_partial(app, handle, ctx=ctx))
        assert "<div" in result.body
        assert "<a></a><b></b>" in result.body

    def test_isolates_root_children(self) -> None:
        # The render must NOT contaminate a caller's existing
        # ctx.root_children (the test populates the outer scope and
        # checks it survives untouched).
        app = _StubApp()

        def section() -> Element:
            return Element("p", {}, (TextNode("inner"),))

        handle = refreshable(section)
        ctx = _build_ctx(app)
        ctx.root_children.append(Element("nav"))
        ctx.parent_stack.append("sentinel")

        run(render_partial(app, handle, ctx=ctx))

        # Caller scope intact.
        assert ctx.root_children == [Element("nav")]
        assert ctx.parent_stack == ["sentinel"]

    def test_marks_is_partial(self) -> None:
        app = _StubApp()

        def section() -> Element:
            return Element("p")

        handle = refreshable(section)
        ctx = _build_ctx(app)
        run(render_partial(app, handle, ctx=ctx))
        assert ctx.is_partial is True


# ───────────────────────────────────────────────────────────────────────────
# Multi-section (out-of-band fragments)
# ───────────────────────────────────────────────────────────────────────────


class TestOob:
    def test_every_section_carries_oob_attribute(self) -> None:
        # The dispatcher fires the action POST with ``swap: 'none'`` —
        # only ``hx-swap-oob`` fragments find their target by id. Every
        # refreshable (primary AND extras) has to ride as OOB or it gets
        # silently dropped by HTMX.
        app = _StubApp()

        def primary() -> Element:
            return Element("section", {"class": "p"}, ())

        def extra() -> Element:
            return Element("section", {"class": "e"}, ())

        h_primary = refreshable(primary)
        h_extra = refreshable(extra)
        ctx = _build_ctx(app)

        result = run(
            render_partial(app, h_primary, ctx=ctx, extra_handles=[h_extra])
        )

        primary_segment = result.body.split("\n")[0]
        extra_segment = result.body.split("\n")[1]
        assert 'hx-swap-oob="morph"' in primary_segment
        assert 'hx-swap-oob="morph"' in extra_segment

    def test_extras_dedupe_against_primary(self) -> None:
        app = _StubApp()

        def section() -> Element:
            return Element("section")

        handle = refreshable(section)
        ctx = _build_ctx(app)
        # Same handle in extras must be ignored (dedupe).
        result = run(
            render_partial(app, handle, ctx=ctx, extra_handles=[handle])
        )
        # Body contains exactly ONE rendering of the section.
        assert result.body.count(handle.id) <= 2  # bz-id + id duplication only


# ───────────────────────────────────────────────────────────────────────────
# Client-state delta
# ───────────────────────────────────────────────────────────────────────────


class TestDelta:
    def test_no_delta_when_clean(self) -> None:
        app = _StubApp()
        registry = StateRegistry(MemoryBackend())

        def section() -> Element:
            return Element("p")

        handle = refreshable(section)
        ctx = _build_ctx(app, registry=registry)

        result = run(render_partial(app, handle, ctx=ctx))
        assert f"<{PATCH_TAG_NAME}>" not in result.body

    def test_delta_appended_when_clientstate_dirty(self) -> None:
        app = _StubApp()
        registry = StateRegistry(MemoryBackend())

        class FilterState(ClientState):
            sort_by: str = field(default='date')

        def section() -> Element:
            return Element("p")

        handle = refreshable(section)
        ctx = _build_ctx(app, registry=registry)

        with use_registry(registry):
            f = FilterState()
            f.sort_by = "name"  # dirty

        result = run(render_partial(app, handle, ctx=ctx))
        # The delta rides as a semantic <bz-patch> tag (V3 wire format).
        assert f"<{PATCH_TAG_NAME}>" in result.body
        assert f"</{PATCH_TAG_NAME}>" in result.body
        assert '"FilterState.default"' in result.body
        assert '"sort_by":"name"' in result.body


# ───────────────────────────────────────────────────────────────────────────
# Refresh-queue draining
# ───────────────────────────────────────────────────────────────────────────


class TestDrain:
    def test_empty_queue_no_clientstate_returns_none(self) -> None:
        app = _StubApp()
        registry = StateRegistry(MemoryBackend())
        ctx = _build_ctx(app, registry=registry)
        assert run(drain_refresh_queue(app, ctx)) is None

    def test_empty_queue_with_dirty_state_returns_delta_only(self) -> None:
        app = _StubApp()
        registry = StateRegistry(MemoryBackend())

        class FilterState(ClientState):
            sort_by: str = field(default='date')

        ctx = _build_ctx(app, registry=registry)
        with use_registry(registry):
            f = FilterState()
            f.sort_by = "name"

        result = run(drain_refresh_queue(app, ctx))
        assert result is not None
        # The body is just the <bz-patch> tag, no rendered section.
        assert f"<{PATCH_TAG_NAME}>" in result.body
        assert "<section" not in result.body

    def test_queue_renders_primary_plus_oob(self) -> None:
        app = _StubApp()
        registry = StateRegistry(MemoryBackend())
        ctx = _build_ctx(app, registry=registry)

        def a() -> Element:
            return Element("section", {"class": "a"})

        def b() -> Element:
            return Element("section", {"class": "b"})

        ha = refreshable(a)
        hb = refreshable(b)

        ctx.refresh_queue = [ha, hb]

        result = run(drain_refresh_queue(app, ctx))
        assert result is not None
        # Primary first, OOB second.
        assert result.body.index("class=\"a\"") < result.body.index("class=\"b\"")
        assert 'hx-swap-oob="morph"' in result.body
