"""Unit tests for :class:`bretzel.components.inputs.date_picker.DatePicker`."""

from __future__ import annotations

import datetime as dt

from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.date_picker import DatePicker
from bretzel.core.serialize import serialize


def _render(*args, **kwargs) -> str:
    with render_isolated():
        return serialize(DatePicker(*args, **kwargs).render())


def _focus_handler() -> None: ...


class TestStructure:
    def test_root_is_bz_date_picker_wrapper(self) -> None:
        html = _render()
        assert "bz-date-picker" in html
        # V3 scope carries the popover open flag AND the field val.
        assert "bz-data=" in html
        assert "open: false" in html
        assert "value:" in html

    def test_hidden_input_reactively_binds_val(self) -> None:
        html = _render(value=dt.date(2026, 6, 15))
        # Hidden form-data carrier uses a reactive bz-attr:value (plus
        # a static SSR value) so re-renders + scope mutations stay in
        # sync with the SSR'd initial.
        assert '<input type="hidden"' in html
        assert 'bz-attr:value="value"' in html
        # The initial ISO is seeded into the wrapper's scope ``val``.
        assert "2026-06-15" in html

    def test_visible_input_is_editable_and_model_bound(self) -> None:
        html = _render(value=dt.date(2026, 6, 15))
        # Typing is allowed (no readonly), bound to wrapper ``val``.
        # It shows the value and writes it only once normalised — never
        # ``bz-model``, which sent every keystroke to on_change.
        assert "bz-model=" not in html
        assert "value = $el.value" in html
        assert 'readonly' not in html

    def test_default_placeholder_is_the_typed_form(self) -> None:
        html = _render()
        # The hint is the form the field reads, in the page's order —
        # built in the browser (``$bz.dates.pattern``) from the
        # framework's letters. It said « YYYY-MM-DD » until 2026-11-02.
        assert 'bz-attr:placeholder="$bz.dates.pattern(&quot;DD&quot;, &quot;MM&quot;, &quot;YYYY&quot;)"' in html
        assert "YYYY-MM-DD" not in html

    def test_the_field_is_named_not_hinted(self) -> None:
        # A screen reader announced the hint, « YYYY-MM-DD ».
        assert 'aria-label="Date"' in _render()
        assert 'aria-label="Date"' in _render(placeholder="Pick a deadline")

    def test_custom_placeholder(self) -> None:
        html = _render(placeholder="Pick a deadline")
        assert "Pick a deadline" in html

    def test_blur_normalises_free_form_to_iso(self) -> None:
        html = _render()
        # The bz-on:blur handler hands the text to the ONE reader of a
        # typed date, ``$bz.dates.typed`` (locale.js), since 2026-10-27
        # — it is no longer recopied into the field. The behaviour itself
        # is gated in a browser:
        # tests/runtime_js/test_a_typed_date_follows_the_language.py.
        assert "bz-on:blur=" in html
        assert "$bz.dates.typed($el.value)" in html
        assert "Intl.DateTimeFormat" not in html, "the reader is recopied into the field again"

    def test_calendar_inside_popover_panel(self) -> None:
        html = _render()
        assert "<bz-calendar" in html
        # The panel is anchored + floating (best-fit, flip / clamp to the
        # viewport) via the shared overlay wiring — same as Select / Combobox
        # / Popover. NOT the old static ``absolute top-full left-0`` + bare
        # ``bz-show`` panel that clipped at the edge : the field frame carries
        # ``bz-ref="bztrigger"`` and the panel ``bz-ref="bzpanel"`` +
        # ``$bz.helpers.floating``.
        assert 'bz-ref="bztrigger"' in html
        assert 'bz-ref="bzpanel"' in html
        assert "helpers.floating" in html
        # (``top-full`` / ``bz-show="open"`` still appear — but from the nested
        # bz-calendar's OWN month/year quick-pick menu, a separate internal
        # overlay, not the date_picker panel we just re-anchored.)

    def test_calendar_value_synced_via_bz_effect(self) -> None:
        html = _render()
        # The calendar's value observed attribute is synced from
        # ``val`` through a ``bz-effect`` on the wrapper that calls
        # ``cal.setAttribute('value', …)`` — V3's ``bz-attr:value`` on
        # a custom element writes the JS property and skips the
        # element's attributeChangedCallback. Living on the wrapper
        # (not the bz-calendar) keeps val in direct scope without
        # going through bz-calendar's nested bz-data.
        assert "bz-effect=" in html
        assert "querySelector('bz-calendar')" in html or \
               "querySelector('bz-calendar')" in html
        assert "cal.setAttribute('value'" in html or \
               "cal.setAttribute('value'" in html
        # The value expression is captured once into ``_val`` (so a
        # bound store path is read a single time per tick) then ISO-
        # tested against that capture.
        assert ".test(_val)" in html

    def test_click_outside_closes_popover(self) -> None:
        html = _render()
        # V3 : no ``@click.outside`` modifier ; the bz-init dismiss
        # registers ``$bz.helpers.clickOutside`` on the wrapper.
        assert "bz-init=" in html
        assert "clickOutside" in html

    def test_icon_button_lives_inside_input_frame(self) -> None:
        html = _render()
        # The trigger button sits as a sibling of the typing input
        # inside the same focus-within frame — opens the popover.
        assert 'aria-label="Open date picker"' in html
        assert "focus-within:border-(--bz-solid)" in html
        assert "bz-c-primary" in html


class TestCloseOnPick:
    def test_default_close_on_pick_true(self) -> None:
        html = _render()
        # Calendar change writes the picked value AND closes the
        # popover when close_on_pick=True (the default).
        assert "value = $event.detail.value" in html or \
               "value = $event.detail.value" in html
        assert "open = false" in html or "open = false" in html

    def test_close_on_pick_false_keeps_popover_open(self) -> None:
        html = _render(close_on_pick=False)
        # The change handler still writes the value back but does not
        # toggle ``open``. The picked-date write is unconditional.
        # ``open = false`` from the *wrapper* dismiss may still appear
        # elsewhere ; what matters is the calendar's own change handler
        # (relocated to its hidden input as ``bz-on:change``).
        import re
        # Pull the inner calendar's hidden input opening tag and verify
        # its bz-on:change handler (V3 relocates a string on_change to
        # the bz-calendar's hidden form-data input).
        m = re.search(r'bz-on:change="([^"]+)"', html)
        assert m is not None
        change_handler = m.group(1)
        assert "open = false" not in change_handler
        assert "open = false" not in change_handler


class TestBindableContract:
    def test_bindable_props_listed(self) -> None:
        assert DatePicker.BINDABLE_PROPS == (
            "value", "min", "max", "disabled",
        )

    def test_autoname_from_value(self) -> None:
        assert DatePicker.AUTONAME_FROM == "value"

    def test_autoname_from_server_state_field(self) -> None:
        # ``ui.date_picker(value=state.appointment)`` → the hidden
        # form-data input derives ``name="appointment"`` from the stamped
        # ``date`` field (regression guard : dates used to fall through
        # ``_stamp``, so the name hardcoded back to "value").
        from bretzel.state import ServerState, field
        from bretzel.state.scopes.client import rendering_scope

        class _S(ServerState):
            appointment: dt.date = field(default=dt.date(2026, 6, 15))

        with rendering_scope(), render_isolated():
            out = serialize(DatePicker(value=_S().appointment).render())
        assert 'name="_S.appointment"' in out
        # …and it does NOT leak onto the wrapper <div> root (released).
        assert out.count('name="_S.appointment"') == 1

    def test_events_listed(self) -> None:
        assert DatePicker.EVENTS == ("change", "focus", "blur")

    def test_value_binding_addresses_store_directly(self) -> None:
        from bretzel.state import ClientState, field
        from bretzel.state.scopes.client import rendering_scope

        class _DP(ClientState, persist="memory"):
            picked: str = field(default="")

        with render_isolated(), rendering_scope():
            state = _DP()
            html = serialize(DatePicker(value=state.picked).render())
        # V3 : no ``$watch`` sync. The scope holds only ``open`` ; the
        # input / hidden / calendar all address the store path
        # directly (bz-model / bz-attr:value / bz-on:change).
        assert "$bz.state._DP.default.picked" in html
        assert "$bz.state._DP.default.picked = $el.value" in html
        assert "bz-data=\"{open: false}\"" in html
        # No local ``val`` seed in bound mode.
        assert "value:" not in html
        # Form-data name still autonamed from the bound field.
        assert 'name="_DP.picked"' in html


class TestForwardingToCalendar:
    def test_min_max_forwarded_to_calendar(self) -> None:
        html = _render(
            min=dt.date(2026, 1, 1),
            max=dt.date(2026, 12, 31),
        )
        assert 'min="2026-01-01"' in html
        assert 'max="2026-12-31"' in html

    def test_weekstart_forwarded(self) -> None:
        html = _render(week_start=0)
        assert 'weekstart="0"' in html

    def test_disabled_dates_forwarded(self) -> None:
        html = _render(disabled_dates=[dt.date(2026, 6, 10)])
        assert "2026-06-10" in html
        assert "disabled-dates" in html


class TestClearable:
    def test_clear_button_emitted_when_clearable_true(self) -> None:
        html = _render(value=dt.date(2026, 6, 15))
        assert 'aria-label="Clear date"' in html

    def test_no_clear_button_when_clearable_false(self) -> None:
        html = _render(value=dt.date(2026, 6, 15), clearable=False)
        assert 'aria-label="Clear date"' not in html


class TestFocusBlurRelocatedToField:
    """Regression : ``on_focus=``/``on_blur=`` used to stay on
    ``root_attrs``, applied to the wrapper ``<div>``. Native
    focus/blur don't bubble, so the handler could structurally never
    fire (unlike ``on_change=``, which correctly bubbles from the
    field input to the root). Fixed by relocating both handler
    flavours onto the actual focusable text field, combined with its
    own internal ISO-normalise blur wiring instead of colliding with
    it."""

    def test_string_focus_lands_on_field_not_root(self) -> None:
        html = _render(on_focus="console.log(2)")
        root_opening = html[: html.index(">")]
        assert "bz-on:focus" not in root_opening
        i = html.index('type="text"')
        field_opening = html[i - 10: html.index(">", i)]
        assert 'bz-on:focus="console.log(2)"' in field_opening

    def test_string_blur_combines_with_internal_normalise(self) -> None:
        html = _render(on_blur="console.log(1)")
        root_opening = html[: html.index(">")]
        assert "bz-on:blur" not in root_opening
        i = html.index('type="text"')
        field_opening = html[i - 10: html.index(">", i)]
        assert "console.log(1)" in field_opening
        # Internal ISO-normalise logic still present and runs first.
        marker = "$bz.dates.typed($el.value)"
        assert marker in field_opening
        assert field_opening.index(marker) < field_opening.index(
            "console.log(1)"
        )

    def test_no_handler_field_still_has_internal_blur_only(self) -> None:
        html = _render()
        i = html.index('type="text"')
        field_opening = html[i - 10: html.index(">", i)]
        assert "$bz.dates.typed($el.value)" in field_opening

    def test_callable_focus_relocates_to_field_not_root(self) -> None:
        html = _render(on_focus=_focus_handler)
        root_opening = html[: html.index(">")]
        assert "hx-post" not in root_opening
        i = html.index('type="text"')
        field_opening = html[i - 10: html.index(">", i)]
        assert "hx-post=" in field_opening
        assert 'hx-trigger="focus"' in field_opening
        assert html.count("hx-post=") == 1

    def test_a_client_change_rides_the_value_carrier(self) -> None:
        """On the root it would also hear the visible field's own
        ``change``, and run twice for one entry."""
        html = _render(on_change="console.log(9)")
        root_opening = html[: html.index(">")]
        assert 'bz-on:change="console.log(9)"' not in root_opening
        assert 'bz-on:change="console.log(9)"' in html
