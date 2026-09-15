"""Unit tests for :class:`bretzel.components.meta.outlet.Outlet`."""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.meta.outlet import Outlet
from bretzel.core.serialize import serialize
from bretzel.render.context import current_context


class TestOutletId:
    def test_auto_id_falls_back_when_no_layout_active(self) -> None:
        with render_isolated():
            o = Outlet()
        # No layout pushed onto the stack → bare ``outlet``.
        assert o.id == "outlet"

    def test_auto_id_uses_layout_stack_tail(self) -> None:
        with render_isolated() as ctx:
            ctx.layout_stack.append("app_layout")
            o = Outlet()
        assert o.id == "outlet_app_layout"

    def test_auto_id_picks_innermost_layout_when_nested(self) -> None:
        with render_isolated() as ctx:
            ctx.layout_stack.append("app_layout")
            ctx.layout_stack.append("admin_layout")
            o = Outlet()
        assert o.id == "outlet_admin_layout"

    def test_explicit_id_becomes_suffix(self) -> None:
        with render_isolated() as ctx:
            ctx.layout_stack.append("split_layout")
            left = Outlet(id="left")
            right = Outlet(id="right")
        assert left.id == "outlet_split_layout_left"
        assert right.id == "outlet_split_layout_right"


class TestOutletRender:
    def test_renders_main_tag(self) -> None:
        with render_isolated():
            out = serialize(Outlet().render())
        assert "<main" in out
        assert 'id="outlet"' in out

    def test_no_reveal_cycle(self) -> None:
        """The outlet renders its content directly — NO ``_v`` / ``bz-show``
        gate. The old reveal cycle hid the outlet and only re-revealed it
        when it WAS the swap target (``htmx:after-swap`` + ``$event.target
        === $el``). That blanked the inner outlet of a nested sub-layout on
        partial nav : the swap targets the OUTERMOST outlet, so an inner
        outlet never received the event → it stayed ``display:none``. Cf.
        ``traps.md`` § "Nested partial-nav blanks the inner outlet"."""
        with render_isolated():
            el = Outlet().render()
        assert el.attrs.get("data-bz-outlet") == "1"
        # No hide / reveal machinery — those gated the inner outlet shut.
        assert "bz-show" not in el.attrs
        assert "bz-data" not in el.attrs
        assert "bz-init" not in el.attrs
        assert "bz-on:htmx:after-swap" not in el.attrs

    def test_not_pre_hidden(self) -> None:
        """The outlet is NOT pre-stamped ``display:none`` — its content is
        server-rendered and shows immediately, so a nested partial-nav swap
        can't leave it stuck hidden."""
        with render_isolated():
            el = Outlet().render()
        assert "display:none" not in el.attrs.get("style", "")

    def test_no_alpine_residue(self) -> None:
        """V3 purge — Alpine directives and the inline transition
        classes are gone (enter/leave animations are CSS-only in V3,
        owned by the theme). The ``@htmx:before-request.window``
        instant-hide is NOT portable to ``bz-on:`` (no ``.window``
        modifier) — deferred to the batch-3 window-event primitive,
        cf. the TODO in ``Outlet.render``."""
        with render_isolated():
            out = serialize(Outlet().render())
        assert "x-data" not in out
        assert "x-init" not in out
        assert "x-show" not in out
        assert "x-transition" not in out
        assert "transition-opacity" not in out
        assert "htmx:before-request" not in out

    def test_children_render_inside(self) -> None:
        from bretzel.components.primitives.text import Text

        with render_isolated() as ctx:
            ctx.layout_stack.append("app_layout")
            with Outlet() as o:
                Text("Page body")
            out = serialize(o.render())
        assert "<main" in out
        assert 'id="outlet_app_layout"' in out
        assert "Page body" in out
