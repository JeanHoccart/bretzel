"""Unit tests for :class:`bretzel.components.inputs.input.Input`.

Focused on the imperative write-only API
(``.set(value) / .clear() / .focus() / .blur()``) added in v2-B.
"""

from __future__ import annotations

from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.input.input import Input
from bretzel.state import field


def _input_attrs(i: Input) -> dict:
    """Return the attrs of the ``<input>`` element.

    Layout depends on whether prefix/suffix/icons are set ; the bare
    case returns the input directly, while wrapped cases nest it.
    """
    node = i.render()
    if node.tag == "input":
        return node.attrs
    # Find the <input> child in a wrapper.
    for child in node.children:
        if getattr(child, "tag", None) == "input":
            return child.attrs
    raise AssertionError("No <input> element found in rendered tree")


class TestImperativeAPI:
    """``.set/.clear/.focus/.blur`` write-only methods.

    Branches at call time on whether ``value=`` carries a binding :
    binding → write-through ; literal → DOM dispatch caught by the
    input's own ``bz-on:bz-*`` listener. ``.focus()`` / ``.blur()``
    are pure DOM commands, no dispatch indirection."""

    # ── No-binding path : DOM dispatch ─────────────────────────────────

    def test_set_without_binding_returns_dispatch_with_payload(self) -> None:
        with render_isolated():
            i = Input()
            out = i.set("hello world")
        assert "dispatchEvent" in out
        assert "bz-set" in out
        assert '"hello world"' in out  # _to_js wraps str in quotes
        assert i.id in out

    def test_clear_without_binding_dispatches_empty_string(self) -> None:
        with render_isolated():
            i = Input()
            out = i.clear()
        # .clear() is sugar over .set("") — same dispatch shape.
        assert "dispatchEvent" in out
        assert "bz-set" in out
        assert '""' in out

    def test_set_with_int_value(self) -> None:
        # value= can be any JSON-serialisable type. Numbers ride
        # naked (no quotes).
        with render_isolated():
            i = Input()
            out = i.set(42)
        assert "value: 42" in out

    # ── Focus / blur : direct DOM, no dispatch ─────────────────────────

    def test_focus_returns_direct_dom_call(self) -> None:
        with render_isolated():
            i = Input()
            out = i.focus()
        assert out == f"document.getElementById('{i.id}').focus()"
        assert "dispatchEvent" not in out

    def test_blur_returns_direct_dom_call(self) -> None:
        with render_isolated():
            i = Input()
            out = i.blur()
        assert out == f"document.getElementById('{i.id}').blur()"
        assert "dispatchEvent" not in out

    # ── Binding path : write-through ──────────────────────────────────

    def test_set_with_binding_writes_through(self) -> None:
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class Form(ClientState, persist="memory"):
            name: str = field(default='')

        with render_isolated():
            with rendering_scope():
                draft = Form()
                i = Input(value=draft.name)
                out = i.set("Ada")
        assert "$bz.state.Form.default.name" in out
        assert '"Ada"' in out
        assert "dispatchEvent" not in out

    def test_clear_with_binding_writes_empty_string(self) -> None:
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class Form(ClientState, persist="memory"):
            name: str = field(default='preset')

        with render_isolated():
            with rendering_scope():
                draft = Form()
                i = Input(value=draft.name)
                out = i.clear()
        assert "$bz.state.Form.default.name" in out
        assert '""' in out
        assert "dispatchEvent" not in out

    # ── Render-time wiring : listeners (V3) ───────────────────────────

    def test_input_carries_no_scope_residue(self) -> None:
        # V3 : ``bz-on:`` listeners resolve against the runtime's
        # root scope — no ``x-data`` / ``bz-data`` on the input.
        with render_isolated():
            i = Input()
            attrs = _input_attrs(i)
        assert "x-data" not in attrs
        assert "bz-data" not in attrs

    def test_input_carries_bz_set_listener_and_clear_is_set_sugar(self) -> None:
        with render_isolated():
            i = Input()
            attrs = _input_attrs(i)
        assert "bz-on:bz-set" in attrs
        # ``.clear()`` is sugar for ``.set("")`` — it dispatches ``bz-set``
        # with an empty value, so there is NO dedicated ``bz-clear`` listener.
        assert "bz-on:bz-clear" not in attrs
        assert "bz-set" in i.clear()
        assert "bz-clear" not in i.clear()
        # V2 Alpine forms gone.
        assert "@bz-set" not in attrs

    def test_listeners_fire_input_and_change_events(self) -> None:
        # Synthetic input + change events are what make bz-model
        # (binding case) sync to the bound state and what makes
        # user on_input= / on_change= handlers run.
        with render_isolated():
            i = Input()
            attrs = _input_attrs(i)
        assert "new Event('input'"  in attrs["bz-on:bz-set"]
        assert "new Event('change'" in attrs["bz-on:bz-set"]

    def test_root_always_carries_id_for_external_dispatch(self) -> None:
        # External callers .set() / .focus() target the input via
        # getElementById. The id MUST always be emitted, even on a
        # bare unbound input.
        with render_isolated():
            i = Input()
            attrs = _input_attrs(i)
        assert attrs.get("id") == i.id
        assert i.id in i.set("x")
        assert i.id in i.focus()

    # ── Layout coverage : affixes + icons still work ──────────────────

    def test_imperative_listeners_attach_on_input_with_icon(self) -> None:
        from bretzel.components.primitives.icon import Icon

        with render_isolated():
            i = Input(icon_left=Icon("search"))
            attrs = _input_attrs(i)
        assert "bz-on:bz-set" in attrs
        assert "x-data" not in attrs

    def test_imperative_listeners_attach_on_input_with_affix(self) -> None:
        with render_isolated():
            i = Input(prefix="$", suffix=".com")
            attrs = _input_attrs(i)
        assert "bz-on:bz-set" in attrs
        assert "x-data" not in attrs

    def test_methods_return_str(self) -> None:
        with render_isolated():
            i = Input()
            assert isinstance(i.set("x"), str)
            assert isinstance(i.clear(),  str)
            assert isinstance(i.focus(),  str)
            assert isinstance(i.blur(),   str)
