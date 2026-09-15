"""Unit tests for ``bretzel.render.pipeline``."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from bretzel.core.tree import Element, TextNode
from bretzel.render.context import RenderContext, current_context
from bretzel.render.decorators.page import page
from bretzel.render.pipeline import render_page
from bretzel.runtime.protocol import (
    ENVELOPE_TAG_NAME,
    PROTOCOL_VERSION,
)
from bretzel.state import field
from bretzel.state.persistence.memory import MemoryBackend
from bretzel.state.registry import StateRegistry, use_registry
from bretzel.state.scopes.client import ClientState


def run[T](coro: Awaitable[T]) -> T:
    return asyncio.new_event_loop().run_until_complete(coro)


# ───────────────────────────────────────────────────────────────────────────
# Stub app + theme
# ───────────────────────────────────────────────────────────────────────────


class _StubTheme:
    """Minimal stand-in matching :meth:`Theme.generate_envelope_dict`."""

    def generate_envelope_dict(self) -> dict[str, object]:
        return {
            "palette": {
                "primary": {"bg": "primary", "fg": "primary-foreground"},
                "brand": {"bg": "amber-500", "fg": "white"},
            },
            "icons": {},
        }


class _StubApp:
    def __init__(self) -> None:
        self._pages: list[Callable[..., Any]] = []
        self._realtime: dict[str, Any] = {}
        self._error_handlers: dict[int, Callable[..., Any]] = {}
        self._theme = _StubTheme()

    @property
    def theme(self) -> object:
        return self._theme

    @property
    def state_backend(self) -> Any:
        return None

    @property
    def debug(self) -> bool:
        return True


def _ctx(app: _StubApp, registry: StateRegistry | None = None) -> RenderContext:
    return RenderContext(app=app, request=object(), state_registry=registry)


# ───────────────────────────────────────────────────────────────────────────
# Basic renders
# ───────────────────────────────────────────────────────────────────────────


class TestBasicRender:
    def test_node_returning_function(self) -> None:
        app = _StubApp()

        def home() -> Element:
            return Element("h1", {}, (TextNode("Hello"),))

        ctx = _ctx(app)
        result = run(render_page(app, home, ctx=ctx))

        assert "<!doctype html>" in result.body
        assert "<h1>Hello</h1>" in result.body
        # V3 : the bootstrap envelope rides as a semantic HTML tag.
        assert f"<{ENVELOPE_TAG_NAME}>" in result.body
        assert f"</{ENVELOPE_TAG_NAME}>" in result.body

    def test_root_children_drained(self) -> None:
        app = _StubApp()

        def home() -> None:
            ctx = current_context()
            ctx.root_children.append(Element("section", {"class": "a"}))
            ctx.root_children.append(Element("section", {"class": "b"}))

        ctx = _ctx(app)
        result = run(render_page(app, home, ctx=ctx))

        assert 'class="a"' in result.body
        assert 'class="b"' in result.body

    def test_async_page_function(self) -> None:
        app = _StubApp()

        async def home() -> Element:
            await asyncio.sleep(0)
            return Element("p", {}, (TextNode("async!"),))

        ctx = _ctx(app)
        result = run(render_page(app, home, ctx=ctx))
        assert "<p>async!</p>" in result.body


# ───────────────────────────────────────────────────────────────────────────
# Page meta — title / description
# ───────────────────────────────────────────────────────────────────────────


class TestPageMeta:
    def test_title_propagates(self) -> None:
        app = _StubApp()

        @page("/x", title="My Page", description="A demo")
        def home() -> Element:
            return Element("p")

        ctx = _ctx(app)
        result = run(render_page(app, home, ctx=ctx))
        assert "<title>My Page</title>" in result.body
        assert 'name="description" content="A demo"' in result.body

    def test_default_title(self) -> None:
        app = _StubApp()

        def home() -> Element:
            return Element("p")

        ctx = _ctx(app)
        result = run(render_page(app, home, ctx=ctx))
        assert "<title>Bretzel</title>" in result.body


# ───────────────────────────────────────────────────────────────────────────
# Path params injection
# ───────────────────────────────────────────────────────────────────────────


class TestPathParams:
    def test_path_params_flow_into_signature(self) -> None:
        app = _StubApp()
        observed: dict[str, Any] = {}

        @page("/users/{id}")
        def user_page(id: int) -> Element:
            observed["id"] = id
            return Element("p", {}, (TextNode(str(id)),))

        ctx = _ctx(app)
        result = run(
            render_page(app, user_page, ctx=ctx, path_params={"id": 42})
        )
        assert observed["id"] == 42
        assert "<p>42</p>" in result.body

    def test_signature_without_match_calls_with_no_args(self) -> None:
        app = _StubApp()

        @page("/")
        def home() -> Element:
            return Element("p")

        ctx = _ctx(app)
        # Path params not relevant — should not raise.
        result = run(render_page(app, home, ctx=ctx, path_params={"junk": 1}))
        assert result.status_code == 200


# ───────────────────────────────────────────────────────────────────────────
# Envelope content — palette + client state + version
# ───────────────────────────────────────────────────────────────────────────


class TestEnvelopeContent:
    def test_envelope_carries_protocol_version(self) -> None:
        app = _StubApp()

        def home() -> Element:
            return Element("p")

        result = run(render_page(app, home, ctx=_ctx(app)))
        assert f'"version":"{PROTOCOL_VERSION}"' in result.body

    # ``test_envelope_carries_palette_from_theme`` a été retiré le
    # 2026-08-01 avec le champ lui-même : la palette ne part plus dans
    # l'envelope (rien ne la lisait côté client). En contrepartie :

    def test_envelope_carries_no_palette(self) -> None:
        """Le pendant négatif — le payload mort ne revient pas."""
        app = _StubApp()

        def home() -> Element:
            return Element("p")

        result = run(render_page(app, home, ctx=_ctx(app)))
        assert '"palette"' not in result.body

    def test_envelope_carries_clientstate(self) -> None:
        app = _StubApp()
        registry = StateRegistry(MemoryBackend())

        class FilterState(ClientState):
            sort_by: str = field(default='date')

        def home() -> Element:
            with use_registry(registry):
                f = FilterState()
                f.sort_by = "name"
            return Element("p")

        ctx = _ctx(app, registry=registry)
        result = run(render_page(app, home, ctx=ctx))
        # The envelope is on a single line ; just check the
        # FilterState entry is in there.
        assert '"FilterState.default"' in result.body
        assert '"persist":"memory"' in result.body


# ───────────────────────────────────────────────────────────────────────────
# Server-state commit happens after render
# ───────────────────────────────────────────────────────────────────────────


class TestCommit:
    def test_dirty_serverstate_persisted(self) -> None:
        from bretzel.state.scopes.server import ServerState

        app = _StubApp()
        backend = MemoryBackend()
        registry = StateRegistry(backend, session_id="sid_42")

        class CartState(ServerState, scope="session"):
            coupon: str = field(default='')

        def home() -> Element:
            cart = CartState()
            cart.coupon = "SUMMER"
            return Element("p")

        ctx = _ctx(app, registry=registry)
        run(render_page(app, home, ctx=ctx))

        stored = run(backend.load("session", "sid_42:CartState:default"))
        assert stored == {"coupon": "SUMMER"}


# ───────────────────────────────────────────────────────────────────────────
# Headers / cookies pass through
# ───────────────────────────────────────────────────────────────────────────


class TestHeadersCookies:
    def test_response_headers_forwarded(self) -> None:
        app = _StubApp()

        def home() -> Element:
            ctx = current_context()
            ctx.set_header("HX-Trigger", "refresh-cart")
            return Element("p")

        ctx = _ctx(app)
        result = run(render_page(app, home, ctx=ctx))
        assert result.headers == {"HX-Trigger": "refresh-cart"}

    def test_cookies_forwarded(self) -> None:
        app = _StubApp()

        def home() -> Element:
            ctx = current_context()
            ctx.set_cookie("session", "abc123", max_age=3600)
            return Element("p")

        ctx = _ctx(app)
        result = run(render_page(app, home, ctx=ctx))
        assert "session" in result.new_cookies
        assert result.new_cookies["session"]["value"] == "abc123"


# ───────────────────────────────────────────────────────────────────────────
# Page-uuid wrapper
# ───────────────────────────────────────────────────────────────────────────


class TestPageWrapper:
    def test_uuid_present_in_body(self) -> None:
        app = _StubApp()

        def home() -> Element:
            return Element("p")

        ctx = _ctx(app)
        result = run(render_page(app, home, ctx=ctx))
        assert f"bz-page-{ctx.page_uuid}" in result.body

    def test_two_renders_have_distinct_uuids(self) -> None:
        app = _StubApp()

        def home() -> Element:
            return Element("p")

        a = run(render_page(app, home, ctx=_ctx(app)))
        b = run(render_page(app, home, ctx=_ctx(app)))
        # Distinct UUIDs → idiomorph treats successive page renders
        # as fresh elements (CR-3 from the spec review).
        assert a.body != b.body


# ───────────────────────────────────────────────────────────────────────────
# Custom shell override
# ───────────────────────────────────────────────────────────────────────────


class TestShellOverride:
    def test_custom_shell_invoked(self) -> None:
        app = _StubApp()
        observed: dict[str, Any] = {}

        def custom_shell(
            body_html: str,
            envelope_json: str,
            *,
            page_uuid: str,
            **kw: Any,
        ) -> str:
            observed["body"] = body_html
            observed["uuid"] = page_uuid
            return f"<custom>{body_html}</custom>"

        @page("/", shell=custom_shell)
        def home() -> Element:
            return Element("p", {}, (TextNode("hi"),))

        ctx = _ctx(app)
        result = run(render_page(app, home, ctx=ctx))
        assert result.body.startswith("<custom>")
        assert "<p>hi</p>" in observed["body"]
        assert observed["uuid"] == ctx.page_uuid


# ───────────────────────────────────────────────────────────────────────────
# Layout + outlet wrapping
# ───────────────────────────────────────────────────────────────────────────


class TestLayoutWrapping:
    """``@page(layout=foo)`` runs the layout function, finds its
    ``ui.outlet()``, and lets the page's components attach inside.

    Imports are deferred to keep the test module importable without
    the full ``bretzel`` namespace at parse time.
    """

    def test_page_lands_inside_outlet(self) -> None:
        from bretzel.components.layout.stack import HStack
        from bretzel.components.meta.outlet import Outlet
        from bretzel.components.primitives.heading import Heading
        from bretzel.components.primitives.text import Text as TextComponent
        from bretzel.render.decorators.layout import layout as layout_decorator

        app = _StubApp()

        def app_layout() -> None:
            with HStack():
                Heading("Brand", level=1)
                Outlet()

        layout_decorator(app_layout)

        @page("/", layout=app_layout)
        def home() -> None:
            TextComponent("Hello inside outlet")

        ctx = _ctx(app)
        result = run(render_page(app, home, ctx=ctx))
        # Both pieces appear : the layout frame *and* the page body
        # inside the outlet's <main>.
        assert "Brand" in result.body
        # Outlet id derived from the layout function's name.
        assert 'id="outlet_app_layout"' in result.body
        # Page content lives inside the outlet element.
        outlet_open = result.body.index('id="outlet_app_layout"')
        outlet_close = result.body.index("</main>", outlet_open)
        outlet_body = result.body[outlet_open:outlet_close]
        assert "Hello inside outlet" in outlet_body

    def test_nested_layouts_chain_outer_to_inner(self) -> None:
        from bretzel.components.layout.stack import HStack
        from bretzel.components.meta.outlet import Outlet
        from bretzel.components.primitives.heading import Heading
        from bretzel.components.primitives.text import Text as TextComponent
        from bretzel.render.decorators.layout import layout as layout_decorator

        app = _StubApp()

        def app_layout() -> None:
            with HStack():
                Heading("App", level=1)
                Outlet()

        def admin_layout() -> None:
            with HStack():
                Heading("Admin sidebar", level=2)
                Outlet()

        layout_decorator(app_layout)
        admin_layout = layout_decorator(parent=app_layout)(admin_layout)

        @page("/admin", layout=admin_layout)
        def admin_home() -> None:
            TextComponent("Admin body")

        ctx = _ctx(app)
        result = run(render_page(app, admin_home, ctx=ctx))
        assert "App" in result.body
        assert "Admin sidebar" in result.body
        # Innermost outlet id reflects the deepest layout name.
        assert 'id="outlet_admin_layout"' in result.body
        # Outer outlet wraps the inner one.
        assert 'id="outlet_app_layout"' in result.body
        outer_pos = result.body.index('id="outlet_app_layout"')
        inner_pos = result.body.index('id="outlet_admin_layout"')
        assert outer_pos < inner_pos


# ───────────────────────────────────────────────────────────────────────────
# Partial nav — ctx.is_partial skips layout + shell
# ───────────────────────────────────────────────────────────────────────────


class TestPartialNav:
    def test_is_partial_returns_bare_inner_html(self) -> None:
        from bretzel.components.layout.stack import HStack
        from bretzel.components.meta.outlet import Outlet
        from bretzel.components.primitives.heading import Heading
        from bretzel.components.primitives.text import Text as TextComponent
        from bretzel.render.decorators.layout import layout as layout_decorator

        app = _StubApp()

        def app_layout() -> None:
            with HStack():
                Heading("Brand", level=1)
                Outlet()

        layout_decorator(app_layout)

        @page("/", layout=app_layout)
        def home() -> None:
            TextComponent("Just the page")

        ctx = _ctx(app)
        ctx.is_partial = True
        ctx.partial_target = "outlet_app_layout"
        result = run(render_page(app, home, ctx=ctx))
        # No shell — no doctype, no envelope, no <main> outlet either
        # (the existing one in the browser stays put).
        assert "<!doctype html>" not in result.body
        assert "bz-envelope" not in result.body
        assert "<main" not in result.body
        # Just the page body.
        assert "Just the page" in result.body
        # ``Brand`` heading lives in the layout — should NOT appear.
        assert "Brand" not in result.body

    def test_partial_response_carries_hx_trigger_title(self) -> None:
        from bretzel.components.layout.stack import HStack
        from bretzel.components.meta.outlet import Outlet
        from bretzel.components.primitives.text import Text as TextComponent
        from bretzel.render.decorators.layout import layout as layout_decorator

        app = _StubApp()

        def app_layout() -> None:
            with HStack():
                Outlet()

        layout_decorator(app_layout)

        @page("/dashboard", layout=app_layout, title="Dashboard")
        def dashboard() -> None:
            TextComponent("d")

        ctx = _ctx(app)
        ctx.is_partial = True
        result = run(render_page(app, dashboard, ctx=ctx))
        # The pipeline pushes ``HX-Trigger`` so the browser can swap
        # the document title on a partial nav.
        trigger = result.headers.get("HX-Trigger", "")
        assert "bretzel:title" in trigger
        assert "Dashboard" in trigger


# ───────────────────────────────────────────────────────────────────────────
# Cross-layout partial nav — sidebar in outer layout jumping between
# sibling sub-layouts (the case the prior binary is_partial flow missed)
# ───────────────────────────────────────────────────────────────────────────


class TestCrossLayoutPartialNav:
    def test_partial_target_on_outer_layout_renders_inner_subchain(self) -> None:
        from bretzel.components.layout.stack import HStack
        from bretzel.components.meta.outlet import Outlet
        from bretzel.components.primitives.heading import Heading
        from bretzel.components.primitives.text import Text as TextComponent
        from bretzel.render.decorators.layout import layout as layout_decorator

        app = _StubApp()

        # shell  ← outer (where the sidebar lives ; targeted by HX-Target)
        # └─ billing_shell  ← inner sub-layout for the billing section
        #    └─ /billing/invoices  ← page
        def shell() -> None:
            with HStack():
                Heading("App shell", level=1)
                Outlet()

        def billing_shell() -> None:
            with HStack():
                Heading("Billing nav", level=2)
                Outlet()

        layout_decorator(shell)
        billing_shell = layout_decorator(parent=shell)(billing_shell)

        @page("/billing/invoices", layout=billing_shell)
        def invoices() -> None:
            TextComponent("Invoice list")

        ctx = _ctx(app)
        # Sidebar in ``shell`` would emit ``hx-target=#outlet_shell``
        # when the user clicks a link to /billing/invoices.
        ctx.is_partial = True
        ctx.partial_target = "outlet_shell"
        result = run(render_page(app, invoices, ctx=ctx))

        # Shell content is OUTSIDE the matched outlet — must NOT appear.
        assert "App shell" not in result.body
        # billing_shell content is INSIDE the matched outlet — MUST appear
        # (this is the whole point of the cross-section fix : the inner
        # sub-layout re-renders fresh, the outer one stays untouched).
        assert "Billing nav" in result.body
        # Page content lands at the deepest layer.
        assert "Invoice list" in result.body
        # No shell wrapper / envelope — it's a partial response.
        assert "<!doctype html>" not in result.body
        assert "bz-envelope" not in result.body

    def test_intra_section_partial_still_page_only(self) -> None:
        # Existing intra-section behaviour must keep working :
        # HX-Target = innermost layout outlet → slice returns [] →
        # page-only render, same as before the fix.
        from bretzel.components.layout.stack import HStack
        from bretzel.components.meta.outlet import Outlet
        from bretzel.components.primitives.heading import Heading
        from bretzel.components.primitives.text import Text as TextComponent
        from bretzel.render.decorators.layout import layout as layout_decorator

        app = _StubApp()

        def shell() -> None:
            with HStack():
                Heading("App shell", level=1)
                Outlet()

        def admin_shell() -> None:
            with HStack():
                Heading("Admin nav", level=2)
                Outlet()

        layout_decorator(shell)
        admin_shell = layout_decorator(parent=shell)(admin_shell)

        @page("/admin/audit", layout=admin_shell)
        def audit() -> None:
            TextComponent("Audit log")

        ctx = _ctx(app)
        ctx.is_partial = True
        ctx.partial_target = "outlet_admin_shell"  # innermost
        result = run(render_page(app, audit, ctx=ctx))

        # Neither layout's chrome appears — pure page body.
        assert "App shell" not in result.body
        assert "Admin nav" not in result.body
        assert "Audit log" in result.body

    def test_unmatched_target_falls_back_to_page_only(self) -> None:
        # If the inbound HX-Target doesn't match any layout in the
        # chain (stale client, layout renamed, etc.), we still don't
        # render shell/envelope — but the layout chain slice returns
        # empty so the response is just the page body. The browser's
        # mounted outlet receives content it doesn't know what to do
        # with, but it's not a 500.
        from bretzel.components.layout.stack import HStack
        from bretzel.components.meta.outlet import Outlet
        from bretzel.components.primitives.text import Text as TextComponent
        from bretzel.render.decorators.layout import layout as layout_decorator

        app = _StubApp()

        def shell() -> None:
            with HStack():
                Outlet()

        layout_decorator(shell)

        @page("/page", layout=shell)
        def my_page() -> None:
            TextComponent("Body")

        ctx = _ctx(app)
        ctx.is_partial = True
        ctx.partial_target = "outlet_does_not_exist"
        result = run(render_page(app, my_page, ctx=ctx))
        # Page renders bare ; no shell, no envelope.
        assert "Body" in result.body
        assert "<!doctype html>" not in result.body


# ───────────────────────────────────────────────────────────────────────────
# Slice helper — pure-function test of the chain truncation logic
# ───────────────────────────────────────────────────────────────────────────


class TestSliceChainForPartial:
    def test_empty_target_returns_empty(self) -> None:
        from bretzel.render.pipeline import _slice_chain_for_partial

        def a() -> None: ...
        def b() -> None: ...

        assert _slice_chain_for_partial([a, b], "") == []
        assert _slice_chain_for_partial([a, b], None) == []

    def test_target_matches_outer_returns_inner(self) -> None:
        from bretzel.render.pipeline import _slice_chain_for_partial

        def outer() -> None: ...
        def inner() -> None: ...

        result = _slice_chain_for_partial([outer, inner], "outlet_outer")
        assert result == [inner]

    def test_target_matches_innermost_returns_empty(self) -> None:
        from bretzel.render.pipeline import _slice_chain_for_partial

        def outer() -> None: ...
        def inner() -> None: ...

        result = _slice_chain_for_partial([outer, inner], "outlet_inner")
        assert result == []

    def test_unmatched_target_returns_empty(self) -> None:
        from bretzel.render.pipeline import _slice_chain_for_partial

        def outer() -> None: ...
        def inner() -> None: ...

        result = _slice_chain_for_partial([outer, inner], "outlet_other")
        assert result == []

    def test_three_level_chain_matches_middle(self) -> None:
        from bretzel.render.pipeline import _slice_chain_for_partial

        def a() -> None: ...
        def b() -> None: ...
        def c() -> None: ...

        result = _slice_chain_for_partial([a, b, c], "outlet_b")
        assert result == [c]
