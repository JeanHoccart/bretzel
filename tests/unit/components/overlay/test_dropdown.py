"""Unit tests for :class:`bretzel.components.overlay.dropdown.Dropdown`."""

from __future__ import annotations

from bretzel.components.base.testing import panel_from_teleport, render_isolated
from bretzel.components.overlay.dropdown import Dropdown, DropdownItem
from bretzel.state import field

_panel = panel_from_teleport  # the dropdown menu panel is teleported to <body>


def _server_handler() -> None:
    """Module-level handler — closures can't be addressed via
    ``sys.modules`` (Mode A constraint), so the server ``on_click=``
    target must live at module scope."""


class TestCloseOnPick:
    """V3 : picking an item closes the parent. The panel listens for
    ``bz-dropdown-pick`` and flips the open flag ; each item dispatches
    that event on click. A server ``on_click=`` rides as a separate
    ``hx-post`` coexisting with the dispatch."""

    def test_panel_listens_for_pick(self) -> None:
        with render_isolated():
            with Dropdown() as d:
                DropdownItem(label="A")
            el = d.render()
        assert _panel(el).attrs.get("bz-on:bz-dropdown-pick") == "open = false"

    def test_panel_pick_listener_uses_binding_path_when_bound(self) -> None:
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class UI(ClientState, persist="memory"):
            flag: bool = field(default=False)

        with render_isolated():
            with rendering_scope():
                ui_state = UI()
                with Dropdown(open=ui_state.flag) as d:
                    DropdownItem(label="A")
                el = d.render()
        path = "$bz.state.UI.default.flag"
        assert _panel(el).attrs.get("bz-on:bz-dropdown-pick") == f"{path} = false"
        # Bound root STILL carries an EMPTY ``bz-data`` : the flag lives in
        # the global store, but the root needs its own scope so the
        # teleported panel's ``bztrigger`` / ``bzpanel`` refs isolate
        # per-instance — else every bound dropdown collides on the shared
        # ``rootScope`` and the menu anchors off-screen (traps.md § "bound
        # overlay ref collision").
        assert el.attrs.get("bz-data") == "{}"

    def test_plain_item_dispatches_pick_on_click(self) -> None:
        with render_isolated():
            with Dropdown() as d:
                DropdownItem(label="A")
            el = d.render()
        item = _panel(el).children[0]
        assert item.attrs.get("bz-on:click") == "$dispatch('bz-dropdown-pick')"

    def test_server_handler_item_coexists_with_pick_dispatch(self) -> None:
        # A server ``on_click=`` callable rides as ``hx-post`` ; the
        # close-dispatch stays a SEPARATE ``bz-on:click`` so both fire.
        with render_isolated():
            with Dropdown() as d:
                DropdownItem(label="B", on_click=_server_handler)
            el = d.render()
        item = _panel(el).children[0]
        assert "hx-post" in item.attrs
        assert item.attrs.get("bz-on:click") == "$dispatch('bz-dropdown-pick')"

    def test_dismiss_treats_teleported_panel_as_inside(self) -> None:
        # The panel teleports to <body>, so it's OUTSIDE the root. Without a
        # panel guard, a click that dispatches no close (a DISABLED item, the
        # panel padding) would trip click-outside and dismiss. The root's
        # dismiss init hands ``() => $refs.bzpanel`` to clickOutside so any
        # click inside the panel counts as inside → stays open. (An enabled
        # item still closes via its own bz-dropdown-pick dispatch.)
        with render_isolated():
            with Dropdown(dismissible=True) as d:
                DropdownItem(label="Locked", disabled=True)
            el = d.render()
        assert "() => $refs.bzpanel" in el.attrs.get("bz-init", "")


class TestItemStyling:
    """Regression : ``enabled:hover:`` killed hover on link rows (``<a>``
    has no ``:enabled``). Plain ``hover:`` + bg-in-colors fixes it."""

    def test_link_item_has_plain_hover_not_enabled(self) -> None:
        from bretzel.core.serialize import serialize

        with render_isolated():
            out = serialize(DropdownItem(label="Profile", href="/me").render())
        assert "<a " in out and 'href="/me"' in out
        assert "hover:bg-text" in out           # neutral hover applies
        assert "enabled:hover" not in out       # the bug

    def test_color_row_hovers_its_own_colour(self) -> None:
        from bretzel.core.serialize import serialize

        with render_isolated():
            out = serialize(
                DropdownItem(label="Delete", color="error", href="/x").render()
            )
        # coloured row tints with its own colour (no bg-text clash)
        assert "hover:bg-error/10" in out
        assert "text-error" in out

    def test_disabled_link_is_inert(self) -> None:
        from bretzel.core.serialize import serialize

        with render_isolated():
            out = serialize(
                DropdownItem(label="Off", href="/x", disabled=True).render()
            )
        assert 'aria-disabled="true"' in out
        assert "href=" not in out               # no navigation
        assert 'tabindex="-1"' in out           # out of tab order

    def test_disabled_button_shows_not_allowed_cursor(self) -> None:
        # A native ``disabled`` <button> AND ``pointer-events-none`` each
        # suppress every pointer event, so ``cursor-not-allowed`` never
        # paints on hover. The disabled row must therefore be aria-only with
        # the hit-test LIVE ; inertness comes from stripping the handlers.
        import re

        from bretzel.core.serialize import serialize

        # matches a real native ``disabled`` attr, not ``aria-disabled`` /
        # the Tailwind ``disabled:`` variant (cf. test_disabled_affordance).
        native_disabled = re.compile(r"(?<![-\w])disabled(?=[\s>=])")

        with render_isolated():
            out = serialize(
                DropdownItem(label="Locked", disabled=True).render()
            )
        assert 'aria-disabled="true"' in out
        assert "aria-disabled:cursor-not-allowed" in out  # the affordance
        assert "pointer-events-none" not in out           # would kill cursor
        assert not native_disabled.search(out)            # would kill cursor
        assert 'tabindex="-1"' in out

    def test_disabled_item_strips_click_wiring(self) -> None:
        # Live hit-test (no pointer-events-none) means the row must NOT act
        # on click : server ``hx-post`` and the close-dispatch are stripped.
        from bretzel.core.serialize import serialize

        with render_isolated():
            out = serialize(
                DropdownItem(
                    label="Locked", disabled=True, on_click=_server_handler
                ).render()
            )
        assert "hx-post" not in out
        assert "bz-on:click" not in out

    def test_colored_row_icon_inherits_tint(self) -> None:
        # The icon must inherit the row's tint (a ``color="error"`` row's
        # icon goes red with the label). A hardcoded ``text-text/70`` on the
        # icon slot beat the inherited ``text-error`` — ``opacity-70`` +
        # the icon's own ``text-current`` lets the tint through instead.
        from bretzel.core.serialize import serialize

        with render_isolated():
            out = serialize(
                DropdownItem(
                    label="Delete", color="error", icon_left="trash-2"
                ).render()
            )
        assert "text-error" in out          # row tint on the root
        assert "opacity-70" in out          # icon dims via opacity, not colour
        assert "text-text/70" not in out    # the hardcoded colour that won
        # L'icône hérite toujours de ``currentColor``, mais par le PONT :
        # ``bz-c-current`` pose ``--bz-text: currentColor``, que le slot
        # lit en ``text-(--bz-text)``. Les deux moitiés sont vérifiées —
        # l'une sans l'autre ne colore rien.
        assert "bz-c-current" in out
        assert "text-(--bz-text)" in out


class TestImperativeAPI:
    """Write-only `.open()` / `.close()` / `.toggle()` methods —
    returns Alpine source compatible with ``on_click=``. Branches on
    construction-time presence of a ClientBinding for ``open``."""

    def test_open_without_binding_returns_dispatch(self) -> None:
        with render_isolated():
            with Dropdown() as d:
                DropdownItem(label="A")
            out = d.open()
        assert "dispatchEvent" in out
        assert "bz-open" in out
        assert d.id in out
        # Must NOT carry a binding write — no binding was passed.
        assert "$bz.state" not in out

    def test_close_without_binding_returns_dispatch(self) -> None:
        with render_isolated():
            with Dropdown() as d:
                DropdownItem(label="A")
            out = d.close()
        assert "dispatchEvent" in out
        assert "bz-close" in out
        assert d.id in out

    def test_toggle_without_binding_returns_dispatch(self) -> None:
        with render_isolated():
            with Dropdown() as d:
                DropdownItem(label="A")
            out = d.toggle()
        assert "dispatchEvent" in out
        assert "bz-toggle" in out
        assert d.id in out

    def test_open_with_binding_writes_through(self) -> None:
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class UI(ClientState, persist="memory"):
            flag: bool = field(default=False)

        with render_isolated():
            with rendering_scope():
                ui_state = UI()
                with Dropdown(open=ui_state.flag) as d:
                    DropdownItem(label="A")
                out = d.open()
        # Write-through : returns the binding setter, no DOM dispatch.
        assert "$bz.state.UI.default.flag" in out
        assert "= true" in out
        assert "dispatchEvent" not in out

    def test_close_with_binding_writes_through(self) -> None:
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class UI(ClientState, persist="memory"):
            flag: bool = field(default=False)

        with render_isolated():
            with rendering_scope():
                ui_state = UI()
                with Dropdown(open=ui_state.flag) as d:
                    DropdownItem(label="A")
                out = d.close()
        assert "$bz.state.UI.default.flag" in out
        assert "= false" in out
        assert "dispatchEvent" not in out

    def test_toggle_with_binding_writes_through(self) -> None:
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class UI(ClientState, persist="memory"):
            flag: bool = field(default=False)

        with render_isolated():
            with rendering_scope():
                ui_state = UI()
                with Dropdown(open=ui_state.flag) as d:
                    DropdownItem(label="A")
                out = d.toggle()
        path = "$bz.state.UI.default.flag"
        # ClientBinding.toggle returns "<path> = !<path>".
        assert out == f"{path} = !{path}"
        assert "dispatchEvent" not in out

    def test_bz_listeners_present_on_root_local(self) -> None:
        # V3 : the imperative receivers are ``bz-on:bz-*`` (was
        # ``@bz-*``). Local case : they flip the local ``open`` flag.
        with render_isolated():
            with Dropdown() as d:
                DropdownItem(label="A")
            el = d.render()
        assert el.attrs.get("bz-on:bz-open") == "open = true"
        assert el.attrs.get("bz-on:bz-close") == "open = false"
        assert el.attrs.get("bz-on:bz-toggle") == "open = !open"

    def test_bz_listeners_present_on_root_bound(self) -> None:
        # Bound case : listeners flip the binding path directly. Both
        # paths (binding setter via .open() AND incoming bz-open
        # dispatch) converge on the same write.
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class UI(ClientState, persist="memory"):
            flag: bool = field(default=False)

        with render_isolated():
            with rendering_scope():
                ui_state = UI()
                with Dropdown(open=ui_state.flag) as d:
                    DropdownItem(label="A")
                el = d.render()
        path = "$bz.state.UI.default.flag"
        assert el.attrs.get("bz-on:bz-open") == f"{path} = true"
        assert el.attrs.get("bz-on:bz-close") == f"{path} = false"
        assert el.attrs.get("bz-on:bz-toggle") == f"{path} = !{path}"

    def test_methods_return_str_consumable_by_on_click(self) -> None:
        # Sanity : the returned values are plain strings (same shape as
        # ClientBinding.set/toggle) so they slot into on_click=
        # transparently.
        with render_isolated():
            with Dropdown() as d:
                DropdownItem(label="A")
            assert isinstance(d.open(),   str)
            assert isinstance(d.close(),  str)
            assert isinstance(d.toggle(), str)

    def test_root_always_carries_id_even_without_binding_or_handler(self) -> None:
        # Regression : external callers `.open()` from a sibling button
        # dispatch via `document.getElementById(self.id)`. If the root
        # doesn't carry `id=` (because the base heuristic
        # `_needs_identity` returns False without bindings or events),
        # the dispatch silently fails. The override in Dropdown must
        # force identity unconditionally.
        with render_isolated():
            with Dropdown() as d:
                DropdownItem(label="A")
            el = d.render()
        assert el.attrs.get("id") == d.id
        # And the id referenced in `.open()` matches.
        assert d.id in d.open()
