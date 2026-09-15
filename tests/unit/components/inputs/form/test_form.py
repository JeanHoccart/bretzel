"""Smoke tests for :class:`Form` — ``<form>`` wrapper + submit wiring."""

from __future__ import annotations

from bretzel.components.actions.button import Button
from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.form.form import Form
from bretzel.components.inputs.input.input import Input
from bretzel.core.serialize import serialize


def _submit_handler() -> None: ...


class TestForm:
    def test_root_tag_is_form(self) -> None:
        with render_isolated():
            rendered = Form().render()
        assert rendered.tag == "form"

    def test_is_container_holds_children(self) -> None:
        """``with form:`` block routes children into the rendered tree."""
        with render_isolated():
            f = Form()
            with f:
                Input(name="email")
                Button("Save", type="submit")
            out = serialize(f.render())
        assert 'name="email"' in out
        assert ">Save<" in out

    def test_on_submit_wires_native_hx_post(self) -> None:
        """``on_submit=fn`` wires the form root as a native ``hx-post``
        action triggered on submit — V3 dropped the ``bz-event:`` dispatcher,
        server actions ride HTMX directly. The bridge adds the HMAC header.
        """
        with render_isolated():
            out = serialize(Form(on_submit=_submit_handler).render())
        # Action target: the handler's wire-id in the POST path.
        assert 'hx-post="/_bretzel/action/' in out
        assert "_submit_handler" in out
        # Fired by the form's native submit, and boosting is off so the
        # dedicated action request (not a page nav) is what goes out.
        assert 'hx-trigger="submit"' in out
        assert 'hx-boost="false"' in out
        # The dropped directive must never reappear.
        assert "bz-event" not in out

    def test_events_declared(self) -> None:
        assert Form.EVENTS == ("submit",)

    def test_no_bindable_props(self) -> None:
        assert Form.BINDABLE_PROPS == ()
