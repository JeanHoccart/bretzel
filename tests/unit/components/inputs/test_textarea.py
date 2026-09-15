"""Unit tests for :class:`bretzel.components.inputs.textarea.Textarea`."""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.textarea import Textarea
from bretzel.core.serialize import serialize
from bretzel.state import field


class TestStructure:
    def test_renders_textarea_tag(self) -> None:
        with render_isolated():
            ta = Textarea(name="bio")
            out = serialize(ta.render())
        assert "<textarea" in out
        assert "</textarea>" in out

    def test_no_value_attr_on_textarea(self) -> None:
        # ``<textarea>``'s value lives in its text content, not in a
        # ``value="…"`` attribute.
        with render_isolated():
            ta = Textarea(name="bio", value="hello world")
            out = serialize(ta.render())
        assert 'value="' not in out
        assert ">hello world<" in out

    def test_initial_text_as_child(self) -> None:
        with render_isolated():
            ta = Textarea(value="seed")
            out = serialize(ta.render())
        assert ">seed<" in out

    def test_empty_value_no_text_child(self) -> None:
        with render_isolated():
            ta = Textarea()
            out = serialize(ta.render())
        # Self-closes with no children when there's nothing to seed.
        assert "<textarea" in out
        # No stray text node between the tags.
        body = out[out.index("<textarea"):]
        assert body.split(">", 1)[1].startswith("</textarea>")


class TestAttrs:
    def test_name_passes_through(self) -> None:
        with render_isolated():
            ta = Textarea(name="bio")
            assert 'name="bio"' in serialize(ta.render())

    def test_placeholder_passes_through(self) -> None:
        with render_isolated():
            ta = Textarea(placeholder="Tell us…")
            assert 'placeholder="Tell us…"' in serialize(ta.render())

    def test_rows_passes_through(self) -> None:
        with render_isolated():
            ta = Textarea(rows=8)
            assert 'rows="8"' in serialize(ta.render())

    def test_required_attr(self) -> None:
        with render_isolated():
            ta = Textarea(required=True)
            out = serialize(ta.render())
        assert "required" in out

    def test_disabled_attr(self) -> None:
        with render_isolated():
            ta = Textarea(disabled=True)
            out = serialize(ta.render())
        assert "disabled" in out

    def test_minmax_length(self) -> None:
        with render_isolated():
            ta = Textarea(minlength=5, maxlength=200)
            out = serialize(ta.render())
        assert 'minlength="5"' in out
        assert 'maxlength="200"' in out


class TestTheme:
    @pytest.mark.parametrize(
        ("size", "expected"),
        [("sm", "text-xs"), ("md", "text-sm"), ("lg", "text-base")],
    )
    def test_size_classes(self, size: str, expected: str) -> None:
        with render_isolated():
            ta = Textarea(size=size)
            assert expected in serialize(ta.render())

    def test_color_substitutes(self) -> None:
        with render_isolated():
            ta = Textarea(color="success")
            out = serialize(ta.render())
        assert "focus:border-(--bz-solid)" in out
        assert "bz-c-success" in out
        assert "{bg_color}" not in out

    def test_root_visual_identity(self) -> None:
        with render_isolated():
            ta = Textarea()
            out = serialize(ta.render())
        # V1 identity: same radius / border / resize-none as Input.
        assert "rounded-field" in out
        assert "resize-none" in out
        assert "border-text/10" in out


def _textarea_attrs(ta: Textarea) -> dict:
    """Return the attrs of the ``<textarea>`` element.

    Textarea has a single render path : the root IS the ``<textarea>``."""
    node = ta.render()
    if node.tag == "textarea":
        return node.attrs
    raise AssertionError("No <textarea> element found in rendered tree")


class TestImperativeAPI:
    """``.set/.clear/.focus/.blur`` write-only methods.

    Branches at call time on whether ``value=`` carries a binding :
    binding → write-through ; literal → DOM dispatch caught by the
    textarea's own ``bz-on:bz-*`` listener. ``.focus()`` / ``.blur()``
    are pure DOM commands, no dispatch indirection."""

    # ── No-binding path : DOM dispatch ─────────────────────────────────

    def test_set_without_binding_returns_dispatch_with_payload(self) -> None:
        with render_isolated():
            ta = Textarea()
            out = ta.set("hello world")
        assert "dispatchEvent" in out
        assert "bz-set" in out
        assert '"hello world"' in out  # _to_js wraps str in quotes
        assert ta.id in out

    def test_clear_without_binding_dispatches_empty_string(self) -> None:
        with render_isolated():
            ta = Textarea()
            out = ta.clear()
        # .clear() is sugar over .set("") — same dispatch shape.
        assert "dispatchEvent" in out
        assert "bz-set" in out
        assert '""' in out

    def test_set_with_int_value(self) -> None:
        # value= can be any JSON-serialisable type. Numbers ride
        # naked (no quotes).
        with render_isolated():
            ta = Textarea()
            out = ta.set(42)
        assert "value: 42" in out

    # ── Focus / blur : direct DOM, no dispatch ─────────────────────────

    def test_focus_returns_direct_dom_call(self) -> None:
        with render_isolated():
            ta = Textarea()
            out = ta.focus()
        assert out == f"document.getElementById('{ta.id}').focus()"
        assert "dispatchEvent" not in out

    def test_blur_returns_direct_dom_call(self) -> None:
        with render_isolated():
            ta = Textarea()
            out = ta.blur()
        assert out == f"document.getElementById('{ta.id}').blur()"
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
                ta = Textarea(value=draft.name)
                out = ta.set("Ada")
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
                ta = Textarea(value=draft.name)
                out = ta.clear()
        assert "$bz.state.Form.default.name" in out
        assert '""' in out
        assert "dispatchEvent" not in out

    # ── Render-time wiring : listeners (V3) ───────────────────────────

    def test_textarea_carries_no_scope_residue(self) -> None:
        # V3 : ``bz-on:`` listeners resolve against the runtime's
        # root scope — no ``x-data`` / ``bz-data`` on the textarea.
        with render_isolated():
            ta = Textarea()
            attrs = _textarea_attrs(ta)
        assert "x-data" not in attrs
        assert "bz-data" not in attrs

    def test_textarea_carries_bz_set_listener_and_clear_is_set_sugar(self) -> None:
        with render_isolated():
            ta = Textarea()
            attrs = _textarea_attrs(ta)
        assert "bz-on:bz-set" in attrs
        # ``.clear()`` is sugar for ``.set("")`` — it dispatches ``bz-set``
        # with an empty value, so there is NO dedicated ``bz-clear`` listener.
        assert "bz-on:bz-clear" not in attrs
        assert "bz-set" in ta.clear()
        assert "bz-clear" not in ta.clear()
        # V2 Alpine forms gone.
        assert "@bz-set" not in attrs

    def test_listeners_fire_input_and_change_events(self) -> None:
        # Synthetic input + change events are what make bz-model
        # (binding case) sync to the bound state and what makes
        # user on_input= / on_change= handlers run.
        with render_isolated():
            ta = Textarea()
            attrs = _textarea_attrs(ta)
        assert "new Event('input'"  in attrs["bz-on:bz-set"]
        assert "new Event('change'" in attrs["bz-on:bz-set"]

    def test_root_always_carries_id_for_external_dispatch(self) -> None:
        # External callers .set() / .focus() target the textarea via
        # getElementById. The id MUST always be emitted, even on a
        # bare unbound textarea.
        with render_isolated():
            ta = Textarea()
            attrs = _textarea_attrs(ta)
        assert attrs.get("id") == ta.id
        assert ta.id in ta.set("x")
        assert ta.id in ta.focus()

    # ── Layout coverage : seeded content + bound flags still work ─────

    def test_imperative_listeners_attach_with_initial_text(self) -> None:
        with render_isolated():
            ta = Textarea(value="seeded content")
            attrs = _textarea_attrs(ta)
        assert "bz-on:bz-set" in attrs
        assert "x-data" not in attrs

    def test_imperative_listeners_attach_with_size_and_color(self) -> None:
        with render_isolated():
            ta = Textarea(size="lg", color="success", rows=6)
            attrs = _textarea_attrs(ta)
        assert "bz-on:bz-set" in attrs
        assert "x-data" not in attrs

    def test_methods_return_str(self) -> None:
        with render_isolated():
            ta = Textarea()
            assert isinstance(ta.set("x"), str)
            assert isinstance(ta.clear(),  str)
            assert isinstance(ta.focus(),  str)
            assert isinstance(ta.blur(),   str)
