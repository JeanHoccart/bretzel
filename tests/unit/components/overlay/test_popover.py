"""Unit tests for :class:`bretzel.components.overlay.popover.Popover`."""

from __future__ import annotations

import pytest

from bretzel.components.actions.icon_button import IconButton
from bretzel.components.base.testing import panel_from_teleport, render_isolated
from bretzel.components.overlay.popover import Popover
from bretzel.components.primitives.text import Text
from bretzel.core.serialize import serialize
from bretzel.state import field


def _make(*, position="bottom", align="center", dismissible=True):
    """Build a popover with a button trigger and a small body."""
    p = Popover(
        trigger=IconButton("info", size="sm"),
        position=position,
        align=align,
        dismissible=dismissible,
    )
    return p


_panel = panel_from_teleport  # the popover panel is teleported to <body>


def _trigger_wrapper(el):
    """The trigger wrapper is the first child of the root (when present)."""
    return el.children[0]


class TestStructure:
    def test_root_carries_bz_data(self) -> None:
        # V3 : local open flag lives in ``bz-data`` (was ``x-data``).
        with render_isolated():
            with _make() as p:
                Text("body")
            el = p.render()
        assert el.attrs.get("bz-data") == "{open: false}"

    def test_panel_has_role_dialog(self) -> None:
        with render_isolated():
            with _make() as p:
                Text("body")
            out = serialize(p.render())
        assert 'role="dialog"' in out

    def test_trigger_toggles_open(self) -> None:
        # V3 : the trigger wrapper carries ``bz-on:click`` (was
        # ``@click``) that flips the local ``open`` flag.
        with render_isolated():
            with _make() as p:
                Text("body")
            el = p.render()
        wrapper = _trigger_wrapper(el)
        assert wrapper.attrs.get("bz-on:click") == "open = !open"

    def test_trigger_carries_aria_haspopup_and_expanded(self) -> None:
        # V3 : reactive aria-expanded rides ``bz-attr:aria-expanded``
        # (was ``:aria-expanded``).
        with render_isolated():
            with _make() as p:
                Text("body")
            el = p.render()
        wrapper = _trigger_wrapper(el)
        assert wrapper.attrs.get("aria-haspopup") == "dialog"

        # On fige le CONTRAT — « la valeur littérale "true"/"false", dérivée
        # de ``open`` » — et non la forme de la chaîne. Ce test épinglait
        # ``"(open).toString()"`` ; le passage à ``bool_attr`` l'a cassé
        # alors que le comportement était inchangé sur un booléen. Un test
        # qui fige une chaîne rend un refactor correct indistinguable d'une
        # régression.
        from bretzel.components.base._wiring import bool_attr

        assert wrapper.attrs.get("bz-attr:aria-expanded") == bool_attr("open")


class TestDismissibleBehaviour:
    def test_default_wires_click_outside(self) -> None:
        # V3 : dismiss (Escape + click-outside) is registered once at
        # mount via ``bz-init`` calling ``$bz.helpers`` (was the Alpine
        # ``@click.outside`` / ``@keydown.escape.window`` magics).
        with render_isolated():
            with _make() as p:
                Text("body")
            el = p.render()
        init = el.attrs.get("bz-init") or ""
        assert "$bz.helpers.clickOutside(" in init
        assert "$bz.helpers.escapeKey(" in init

    def test_non_dismissible_drops_outside_and_escape(self) -> None:
        with render_isolated():
            with _make(dismissible=False) as p:
                Text("body")
            el = p.render()
        # No dismiss wiring at all when ``dismissible=False``.
        assert "bz-init" not in el.attrs


class TestPositioning:
    """V3 : positioning is 100 % owned by ``$bz.helpers.floating`` —
    the static position classes (``bottom-full``, ``left-0``, …) are
    GONE from the HTML. The only positioning artefact in the markup is
    the ``placement`` string passed to ``floating`` inside the panel's
    ``bz-effect``. ``center`` align is dropped (floating's default), so
    ``position`` alone is the placement ; non-center align appends
    ``-<align>`` (``bottom-start``, ``right-end``, …)."""

    @pytest.mark.parametrize(
        ("position", "expected"),
        [
            ("top", "__p = 'top'"),
            ("bottom", "__p = 'bottom'"),
            ("left", "__p = 'left'"),
            ("right", "__p = 'right'"),
        ],
    )
    def test_placement_in_panel_effect(
        self, position: str, expected: str
    ) -> None:
        with render_isolated():
            with _make(position=position) as p:
                Text("body")
            el = p.render()
        assert expected in _panel(el).attrs["bz-effect"]

    def test_horizontal_alignment_for_top_bottom(self) -> None:
        # ``top``/``bottom`` + non-center align → ``<side>-<align>``.
        with render_isolated():
            with _make(position="bottom", align="start") as p:
                Text("body")
            el = p.render()
        assert "__p = 'bottom-start'" in _panel(el).attrs["bz-effect"]

    def test_vertical_alignment_for_left_right(self) -> None:
        # ``left``/``right`` + non-center align → ``<side>-<align>``.
        with render_isolated():
            with _make(position="right", align="end") as p:
                Text("body")
            el = p.render()
        assert "__p = 'right-end'" in _panel(el).attrs["bz-effect"]


class TestOpenBinding:
    """``open=`` accepts ``bool | ClientBinding`` like every reactive
    prop. When bound, the popover reads/writes the binding path
    instead of a local ``bz-data`` flag."""

    def test_literal_open_uses_local_bz_data(self) -> None:
        with render_isolated():
            with _make() as p:
                Text("body")
            el = p.render()
        assert el.attrs.get("bz-data") == "{open: false}"

    def test_binding_open_reads_binding_path(self) -> None:
        # V3 : a bound open reads/writes the global store, NOT a local
        # ``open`` flag — but the root STILL carries an EMPTY ``bz-data``
        # so it owns a per-instance scope. Without it the teleported panel
        # resolves its ``bztrigger`` / ``bzpanel`` refs against the shared
        # ``rootScope``, where every bound overlay collides (last-write-
        # wins) and the floating helper anchors to the wrong trigger — the
        # panel lands off-screen. Cf. traps.md § "bound overlay ref
        # collision". The Escape arm lives inside ``bz-init``
        # (``anchored_dismiss_init``).
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class UI(ClientState, persist="memory"):
            is_open: bool = field(default=False)

        with render_isolated(), rendering_scope():
            ui_state = UI()
            p = Popover(open=ui_state.is_open)
            el = p.render()
        path = "$bz.state.UI.default.is_open"
        # Empty scope (ref isolation), and crucially NOT the local ``open``
        # flag — the flag lives in the global store.
        assert el.attrs.get("bz-data") == "{}"
        # The dismiss init writes the binding path to false on Escape /
        # click-outside.
        assert f"{path} = false" in (el.attrs.get("bz-init") or "")
        # The dispatch effect reads the binding path, too.
        assert path in el.attrs.get("bz-effect", "")


class TestArrow:
    def test_popover_has_no_arrow(self) -> None:
        # The popover has no arrow at all — the prop was removed.
        with render_isolated():
            with _make() as p:
                Text("body")
            out = serialize(p.render())
        assert "rotate-45" not in out


class TestImperativeAPI:
    """Write-only `.open()` / `.close()` / `.toggle()` methods —
    returns Alpine source compatible with ``on_click=``. Branches on
    construction-time presence of a ClientBinding for ``open``."""

    def test_open_without_binding_returns_dispatch(self) -> None:
        with render_isolated():
            p = Popover()
            out = p.open()
        assert "dispatchEvent" in out
        assert "bz-open" in out
        assert p.id in out
        # Must NOT carry a binding write — no binding was passed.
        assert "$bz.state" not in out

    def test_close_without_binding_returns_dispatch(self) -> None:
        with render_isolated():
            p = Popover()
            out = p.close()
        assert "dispatchEvent" in out
        assert "bz-close" in out
        assert p.id in out

    def test_toggle_without_binding_returns_dispatch(self) -> None:
        with render_isolated():
            p = Popover()
            out = p.toggle()
        assert "dispatchEvent" in out
        assert "bz-toggle" in out
        assert p.id in out

    def test_open_with_binding_writes_through(self) -> None:
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class UI(ClientState, persist="memory"):
            flag: bool = field(default=False)

        with render_isolated(), rendering_scope():
            ui_state = UI()
            p = Popover(open=ui_state.flag)
            out = p.open()
        # Write-through : returns the binding setter, no DOM dispatch.
        assert "$bz.state.UI.default.flag" in out
        assert "= true" in out
        assert "dispatchEvent" not in out

    def test_close_with_binding_writes_through(self) -> None:
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class UI(ClientState, persist="memory"):
            flag: bool = field(default=False)

        with render_isolated(), rendering_scope():
            ui_state = UI()
            p = Popover(open=ui_state.flag)
            out = p.close()
        assert "$bz.state.UI.default.flag" in out
        assert "= false" in out
        assert "dispatchEvent" not in out

    def test_toggle_with_binding_writes_through(self) -> None:
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class UI(ClientState, persist="memory"):
            flag: bool = field(default=False)

        with render_isolated(), rendering_scope():
            ui_state = UI()
            p = Popover(open=ui_state.flag)
            out = p.toggle()
        path = "$bz.state.UI.default.flag"
        # ClientBinding.toggle returns "<path> = !<path>".
        assert out == f"{path} = !{path}"
        assert "dispatchEvent" not in out

    def test_bz_listeners_present_on_root_local(self) -> None:
        # V3 : the imperative receivers are ``bz-on:bz-*`` (was
        # ``@bz-*``). Local case : they flip the local ``open`` flag.
        with render_isolated():
            p = Popover()
            el = p.render()
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

        with render_isolated(), rendering_scope():
            ui_state = UI()
            p = Popover(open=ui_state.flag)
            el = p.render()
        path = "$bz.state.UI.default.flag"
        assert el.attrs.get("bz-on:bz-open") == f"{path} = true"
        assert el.attrs.get("bz-on:bz-close") == f"{path} = false"
        assert el.attrs.get("bz-on:bz-toggle") == f"{path} = !{path}"

    def test_methods_return_str_consumable_by_on_click(self) -> None:
        # Sanity : the returned values are plain strings (same shape as
        # ClientBinding.set/toggle) so they slot into on_click=
        # transparently.
        with render_isolated():
            p = Popover()
            assert isinstance(p.open(),   str)
            assert isinstance(p.close(),  str)
            assert isinstance(p.toggle(), str)

    def test_root_always_carries_id_even_without_binding_or_handler(self) -> None:
        # Regression : external callers `.open()` from a sibling button
        # dispatch via `document.getElementById(self.id)`. If the root
        # doesn't carry `id=` (because the base heuristic
        # `_needs_identity` returns False without bindings or events),
        # the dispatch silently fails. The override in Popover must
        # force identity unconditionally.
        with render_isolated():
            p = Popover()
            el = p.render()
        assert el.attrs.get("id") == p.id
        # And the id referenced in `.open()` matches.
        assert p.id in p.open()
