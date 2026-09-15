"""Unit tests for :class:`bretzel.components.inputs.switch.Switch`.

Focused on the imperative write-only API (``.toggle() / .set(bool)``).
``.check()`` / ``.uncheck()`` aliases were dropped after v2-A as
redundant semantic sugar. Switch is a visual variant of Checkbox —
same contract, same tests.
"""

from __future__ import annotations

from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.switch.switch import Switch
from bretzel.state import field


def _root_attrs(s: Switch) -> dict:
    return s.render().attrs


def _input_attrs(s: Switch) -> dict:
    # Render structure : label > div(container) > input + visuals
    container = s.render().children[0]
    return container.children[0].attrs


class TestImperativeAPI:
    """``.check/.uncheck/.toggle/.set`` write-only methods —
    write-through binding if any, else DOM dispatch on the input by id."""

    # ── No-binding path : DOM dispatch ─────────────────────────────────

    def test_toggle_without_binding_returns_dispatch(self) -> None:
        with render_isolated():
            s = Switch()
            out = s.toggle()
        assert "bz-toggle" in out
        assert "detail" not in out

    def test_set_with_explicit_bool(self) -> None:
        with render_isolated():
            s = Switch()
            assert "value: true"  in s.set(True)
            assert "value: false" in s.set(False)

    # ── Binding path : write-through ──────────────────────────────────

    def test_toggle_with_binding_writes_through(self) -> None:
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class UI(ClientState, persist="memory"):
            flag: bool = field(default=False)

        with render_isolated():
            with rendering_scope():
                ui_state = UI()
                s = Switch(checked=ui_state.flag)
                out = s.toggle()
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
                s = Switch(checked=ui_state.flag)
                out = s.set(True)
        assert "$bz.state.UI.default.flag" in out
        assert "= true" in out
        assert "dispatchEvent" not in out

    # ── Render-time wiring : input listeners (V3) ─────────────────────

    def test_root_carries_no_scope_residue(self) -> None:
        # V3 : ``bz-on:`` listeners resolve against the runtime's
        # root scope — no ``x-data`` / ``bz-data`` on the root.
        with render_isolated():
            s = Switch()
            attrs = _root_attrs(s)
        assert "x-data" not in attrs
        assert "bz-data" not in attrs

    def test_input_carries_bz_toggle_and_bz_set_listeners(self) -> None:
        with render_isolated():
            s = Switch()
            attrs = _input_attrs(s)
        assert "bz-on:bz-toggle" in attrs
        assert "bz-on:bz-set" in attrs
        # V2 Alpine forms and dropped aliases must not appear.
        assert "@bz-toggle" not in attrs
        assert "@bz-set" not in attrs
        assert "bz-on:bz-check" not in attrs
        assert "bz-on:bz-uncheck" not in attrs

    def test_listeners_fire_change_event(self) -> None:
        with render_isolated():
            s = Switch()
            attrs = _input_attrs(s)
        for k in ("bz-on:bz-toggle", "bz-on:bz-set"):
            assert "new Event('change'" in attrs[k]

    def test_root_always_carries_id_for_external_dispatch(self) -> None:
        with render_isolated():
            s = Switch()
            attrs = _input_attrs(s)
        assert attrs.get("id") == s.id
        assert s.id in s.set(True)
        assert s.id in s.toggle()

    def test_methods_return_str(self) -> None:
        with render_isolated():
            s = Switch()
            assert isinstance(s.toggle(),  str)
            assert isinstance(s.set(True), str)
