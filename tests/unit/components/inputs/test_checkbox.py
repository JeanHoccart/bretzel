"""Unit tests for :class:`bretzel.components.inputs.checkbox.Checkbox`.

Focused on the imperative write-only API
(``.toggle() / .set(bool)``) — ``.check()`` / ``.uncheck()`` aliases
were dropped after v2-A as redundant semantic sugar over ``.set()``.
"""

from __future__ import annotations

from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.checkbox.checkbox import Checkbox
from bretzel.state import field


def _root_attrs(c: Checkbox) -> dict:
    return c.render().attrs


def _input_attrs(c: Checkbox) -> dict:
    # Render structure : label > div(container) > input + visuals
    container = c.render().children[0]
    return container.children[0].attrs


class TestImperativeAPI:
    """``.check/.uncheck/.toggle/.set`` write-only methods —
    write-through binding if any, else DOM dispatch on the input by id."""

    # ── No-binding path : DOM dispatch ─────────────────────────────────

    def test_toggle_without_binding_returns_dispatch(self) -> None:
        with render_isolated():
            c = Checkbox()
            out = c.toggle()
        assert "dispatchEvent" in out
        assert "bz-toggle" in out
        # No payload — toggle is value-less.
        assert "detail" not in out
        assert c.id in out

    def test_set_true_without_binding_returns_dispatch_with_payload(self) -> None:
        with render_isolated():
            c = Checkbox()
            out = c.set(True)
        assert "dispatchEvent" in out
        assert "bz-set" in out
        assert "value: true" in out

    def test_set_false_without_binding_returns_dispatch_with_payload(self) -> None:
        with render_isolated():
            c = Checkbox()
            out = c.set(False)
        assert "value: false" in out

    # ── Binding path : write-through ──────────────────────────────────

    def test_toggle_with_binding_writes_through(self) -> None:
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class UI(ClientState, persist="memory"):
            flag: bool = field(default=False)

        with render_isolated():
            with rendering_scope():
                ui_state = UI()
                c = Checkbox(checked=ui_state.flag)
                out = c.toggle()
        path = "$bz.state.UI.default.flag"
        assert out == f"{path} = !{path}"
        assert "dispatchEvent" not in out

    def test_set_with_binding_writes_through(self) -> None:
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class UI(ClientState, persist="memory"):
            flag: bool = field(default=False)

        with render_isolated():
            with rendering_scope():
                ui_state = UI()
                c = Checkbox(checked=ui_state.flag)
                out = c.set(True)
        assert "$bz.state.UI.default.flag" in out
        assert "= true" in out
        assert "dispatchEvent" not in out

    # ── Render-time wiring : input listeners (V3) ─────────────────────

    def test_root_carries_no_scope_residue(self) -> None:
        # V3 : ``bz-on:`` listeners resolve against the runtime's
        # root scope — no ``x-data`` (V2 Alpine) and no ``bz-data``
        # needed on the root. Regression guard against the V2 idiom
        # creeping back.
        with render_isolated():
            c = Checkbox()
            attrs = _root_attrs(c)
        assert "x-data" not in attrs
        assert "bz-data" not in attrs

    def test_input_carries_bz_toggle_and_bz_set_listeners(self) -> None:
        with render_isolated():
            c = Checkbox()
            attrs = _input_attrs(c)
        assert "bz-on:bz-toggle" in attrs
        assert "bz-on:bz-set" in attrs
        # The V2 Alpine forms must NOT show up.
        assert "@bz-toggle" not in attrs
        assert "@bz-set" not in attrs
        # The dropped aliases must NOT show up.
        assert "bz-on:bz-check" not in attrs
        assert "bz-on:bz-uncheck" not in attrs

    def test_listeners_fire_change_event(self) -> None:
        # The synthetic ``change`` event is what makes bz-model
        # (binding case) sync to the bound state and what makes user
        # ``on_change=`` handlers run.
        with render_isolated():
            c = Checkbox()
            attrs = _input_attrs(c)
        for k in ("bz-on:bz-toggle", "bz-on:bz-set"):
            assert "new Event('change'" in attrs[k]

    def test_root_always_carries_id_for_external_dispatch(self) -> None:
        # Regression : external callers .set() / .toggle() dispatch on
        # getElementById(self.id). Without _needs_identity = True the
        # id wouldn't render on a plain checkbox and the dispatch
        # would silently fail.
        with render_isolated():
            c = Checkbox()
            attrs = _input_attrs(c)
        # The id rides on the input (the dispatch target), not on the
        # label root — emit_attrs is called on input_attrs.
        assert attrs.get("id") == c.id
        assert c.id in c.set(True)
        assert c.id in c.toggle()

    def test_methods_return_str(self) -> None:
        with render_isolated():
            c = Checkbox()
            assert isinstance(c.toggle(),  str)
            assert isinstance(c.set(True), str)
