"""Unit tests for :class:`bretzel.components.inputs.form_field.FormField`."""

from __future__ import annotations

from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.form_field import FormField
from bretzel.components.inputs.textarea import Textarea
from bretzel.core.serialize import serialize


class TestStructure:
    def test_root_div(self) -> None:
        with render_isolated():
            ff = FormField()
            out = serialize(ff.render())
        assert out.startswith("<div")

    def test_label_when_provided(self) -> None:
        with render_isolated():
            ff = FormField(label="Email")
            out = serialize(ff.render())
        assert "<label" in out
        assert ">Email<" in out

    def test_no_label_when_omitted(self) -> None:
        with render_isolated():
            ff = FormField()
            assert "<label" not in serialize(ff.render())

    def test_label_for_attr_when_name_given(self) -> None:
        with render_isolated():
            ff = FormField(label="Email", name="email")
            assert 'for="email"' in serialize(ff.render())

    def test_label_no_for_attr_when_name_missing(self) -> None:
        with render_isolated():
            ff = FormField(label="Email")
            out = serialize(ff.render())
        # The <label> is present but ``for=`` is not set.
        assert "<label" in out
        assert "for=" not in out


class TestRequired:
    def test_required_marker_in_label(self) -> None:
        with render_isolated():
            ff = FormField(label="Email", required=True)
            out = serialize(ff.render())
        assert ">*<" in out
        # a11y : the marker is decorative — the real semantic is the
        # ``required`` attr on the inner input.
        assert 'aria-hidden="true"' in out

    def test_no_required_marker_when_not_required(self) -> None:
        with render_isolated():
            ff = FormField(label="Email")
            out = serialize(ff.render())
        assert ">*<" not in out


class TestHintAndError:
    def test_hint_renders_when_no_error(self) -> None:
        with render_isolated():
            ff = FormField(hint="No spam ever.")
            out = serialize(ff.render())
        assert ">No spam ever.<" in out
        assert 'role="alert"' not in out

    def test_error_renders_with_alert_role(self) -> None:
        with render_isolated():
            ff = FormField(error="Required field")
            out = serialize(ff.render())
        assert ">Required field<" in out
        assert 'role="alert"' in out

    def test_error_takes_precedence_over_hint(self) -> None:
        # Spec : error wins, hint is not shown alongside.
        with render_isolated():
            ff = FormField(hint="optional hint", error="bad input")
            out = serialize(ff.render())
        assert ">bad input<" in out
        assert ">optional hint<" not in out


class TestChildrenIntegration:
    def test_wraps_inner_input(self) -> None:
        with render_isolated():
            with FormField(label="Bio", name="bio") as ff:
                Textarea(name="bio", placeholder="…")
            out = serialize(ff.render())
        # Label, then textarea, both inside the wrapper div.
        assert "<label" in out
        assert "<textarea" in out
        assert out.index("<label") < out.index("<textarea")

    def test_label_then_input_then_hint_order(self) -> None:
        with render_isolated():
            with FormField(label="Bio", name="bio", hint="max 500 chars") as ff:
                Textarea(name="bio")
            out = serialize(ff.render())
        # Strict top-to-bottom order.
        i_label = out.index("<label")
        i_input = out.index("<textarea")
        i_hint = out.rindex("<span")
        assert i_label < i_input < i_hint


class TestRequiredPropagation:
    """``FormField(required=True)`` propagates the HTML5 ``required``
    attribute to its child form-control. Without this, the asterisk
    is purely cosmetic and the browser never blocks an empty submit."""

    def test_required_propagates_to_input(self) -> None:
        from bretzel.components.inputs.input import Input

        with render_isolated():
            with FormField(label="Email", required=True) as ff:
                Input(name="email", type="email")
            out = serialize(ff.render())
        assert "<input" in out
        # The bare ``required`` attribute (HTML5 boolean) lands on
        # the input tag, separate from the visual ``*`` span.
        # Check on the opening of the <input ... > tag specifically.
        input_tag = out[out.index("<input"):out.index("/>", out.index("<input"))]
        assert " required" in input_tag

    def test_required_propagates_to_textarea(self) -> None:
        with render_isolated():
            with FormField(label="Bio", required=True) as ff:
                Textarea(name="bio")
            out = serialize(ff.render())
        textarea_tag = out[out.index("<textarea"):out.index(">", out.index("<textarea"))]
        assert " required" in textarea_tag

    def test_no_required_when_form_field_not_required(self) -> None:
        from bretzel.components.inputs.input import Input

        with render_isolated():
            with FormField(label="Optional") as ff:
                Input(name="x")
            out = serialize(ff.render())
        input_tag = out[out.index("<input"):out.index("/>", out.index("<input"))]
        assert " required" not in input_tag


class TestReactiveErrorBinding:
    """When ``error=`` is a ``ClientBinding``, FormField emits an
    always-present ``<span>`` with ``bz-show`` + ``bz-text`` so the
    runtime can flip visibility AND text content reactively without a
    full refreshable round-trip — the native form error pattern."""

    def test_binding_emits_bz_show_and_bz_text(self) -> None:
        from bretzel.state import ClientState, field as state_field
        from bretzel.state.scopes.client import rendering_scope

        class _E(ClientState, persist="memory"):
            email_err: str = state_field(default="")

        with render_isolated(), rendering_scope():
            e = _E()
            with FormField(label="Email", error=e.email_err) as ff:
                from bretzel.components.inputs.input import Input
                Input(name="email")
            out = serialize(ff.render())

        # Span exists in DOM even though initial value is empty.
        assert 'role="alert"' in out
        assert 'bz-show="$bz.state._E.default.email_err"' in out
        assert 'bz-text="$bz.state._E.default.email_err"' in out
        # V3 FOUC strategy : x-cloak is gone — the initially-falsy
        # branch is pre-stamped display:none instead.
        assert "x-cloak" not in out
        assert "display:none" in out

    def test_binding_truthy_ssr_value_not_prestamped_hidden(self) -> None:
        # When the binding's SSR value is truthy the error span must
        # be visible before the runtime boots — no display:none stamp.
        from bretzel.state import ClientState, field as state_field
        from bretzel.state.scopes.client import rendering_scope

        class _F(ClientState, persist="memory"):
            email_err: str = state_field(default="Already taken")

        with render_isolated(), rendering_scope():
            f = _F()
            with FormField(label="Email", error=f.email_err) as ff:
                from bretzel.components.inputs.input import Input
                Input(name="email")
            out = serialize(ff.render())

        assert 'bz-show="$bz.state._F.default.email_err"' in out
        assert ">Already taken<" in out
        assert "display:none" not in out

    def test_literal_error_keeps_static_span(self) -> None:
        # Backwards-compat : a literal string ``error="…"`` still
        # renders as a plain static span (no bz-show / bz-text bloat).
        with render_isolated():
            with FormField(label="X", error="Already taken") as ff:
                from bretzel.components.inputs.input import Input
                Input(name="x")
            out = serialize(ff.render())
        assert "Already taken" in out
        assert "bz-text" not in out
        assert "bz-show" not in out


class TestStaleErrorAutoClear:
    """When ``error=`` is a ``ClientBinding``, FormField stamps a
    ``bz-on:input`` directive on its root that resets the bound
    path to ``""`` on any input event bubbling from the child
    form-control. Standard 2026 UX : the user starts editing → the
    stale server-side error verdict disappears instantly, no
    round-trip needed. (V2 used Alpine's ``@input.capture`` ; V3 has
    no ``.capture`` modifier — bubble phase is equivalent here.)"""

    def test_binding_emits_input_listener_directive(self) -> None:
        from bretzel.state import ClientState, field as state_field
        from bretzel.state.scopes.client import rendering_scope

        class _E(ClientState, persist="memory"):
            email_err: str = state_field(default="Already taken")

        with render_isolated(), rendering_scope():
            e = _E()
            with FormField(label="Email", error=e.email_err) as ff:
                from bretzel.components.inputs.input import Input
                Input(name="email")
            out = serialize(ff.render())

        # The directive sits on the FormField root div ; input events
        # bubbling from the child form-control are caught there. The
        # expression writes the empty string back to the bound
        # ClientState path, which flips bz-show via the runtime's
        # reactivity.
        assert "bz-on:input" in out
        assert "@input.capture" not in out  # V2 Alpine form gone
        # Path matches the binding's serialize_path.
        assert "$bz.state._E.default.email_err" in out
        # Reset value is the empty string (ClientState fields are
        # typed ``str`` here so "" is the natural empty value).
        # The serialiser entity-encodes both ``=`` (=) and ``'``
        # (') — accept either raw or encoded form.
        assert (
            "bz-on:input=\"$bz.state._E.default.email_err = ''\""
            in out
            or "= ''" in out
        )

    def test_literal_error_no_auto_clear(self) -> None:
        # When the caller passes a static string for ``error=``, they
        # explicitly asked for a frozen message — no auto-clear logic
        # should be stamped on the DOM.
        with render_isolated():
            with FormField(label="X", error="Frozen") as ff:
                from bretzel.components.inputs.input import Input
                Input(name="x")
            out = serialize(ff.render())
        assert "bz-on:input" not in out

    def test_no_error_no_auto_clear(self) -> None:
        # FormField without ``error=`` at all — nothing to clear.
        with render_isolated():
            with FormField(label="X") as ff:
                from bretzel.components.inputs.input import Input
                Input(name="x")
            out = serialize(ff.render())
        assert "bz-on:input" not in out
