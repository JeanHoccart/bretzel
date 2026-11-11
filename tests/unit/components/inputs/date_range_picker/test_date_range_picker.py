"""Unit tests for ``DateRangePicker``."""

from __future__ import annotations

import datetime as dt

from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.date_range_picker import DateRangePicker
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


def _render(*args, **kwargs) -> str:
    with render_isolated():
        return serialize(DateRangePicker(*args, **kwargs).render())


def _focus_handler() -> None: ...


class TestStructure:
    def test_root_wrapper(self) -> None:
        html = _render()
        assert "bz-date-range-picker" in html
        # V3 scope carries open + the two field vars.
        assert "bz-data=" in html
        assert "open: false" in html
        assert "vstart:" in html and "vend:" in html

    def test_two_editable_inputs_bound_to_vstart_vend(self) -> None:
        html = _render(
            value=(dt.date(2026, 6, 10), dt.date(2026, 6, 20)),
        )
        # Both inputs accept typing; each writes its end once normalised.
        assert "vstart = $el.value" in html
        assert "vend = $el.value" in html
        # No readonly — both fields are typeable.
        assert 'readonly' not in html

    def test_blur_normalises_each_field(self) -> None:
        html = _render()
        # Each field has its own free-form → ISO normaliser on blur.
        # (read in the page's language order — cf. normalise_to_iso_js)
        # It runs on the field's own text, then writes the result once.
        assert html.count("$bz.dates.typed($el.value)") >= 2
        assert "vstart = $el.value" in html
        assert "vend = $el.value" in html

    def test_separator_arrow_present(self) -> None:
        html = _render()
        # Default separator is the right arrow.
        assert "→" in html

    def test_custom_separator(self) -> None:
        html = _render(separator="–")
        assert "–" in html

    def test_calendar_mode_range(self) -> None:
        html = _render()
        assert "<bz-calendar" in html
        assert 'mode="range"' in html

    def test_calendar_value_synced_via_bz_effect(self) -> None:
        html = _render()
        # Same trap as DatePicker — V3 ``bz-attr:value`` on a custom
        # element writes the property, not the attribute. We use a
        # ``bz-effect`` on the wrapper that grabs the bz-calendar via
        # querySelector and calls setAttribute explicitly.
        assert "bz-effect=" in html
        assert "querySelector('bz-calendar')" in html or \
               "querySelector('bz-calendar')" in html
        assert "cal.setAttribute('value'" in html or \
               "cal.setAttribute('value'" in html
        assert "JSON.stringify([vstart, vend])" in html

    def test_hidden_input_json_pair_via_reactive_value(self) -> None:
        html = _render(
            value=(dt.date(2026, 6, 10), dt.date(2026, 6, 20)),
        )
        # Hidden form-data carrier is reactive ; the SSR'd vstart /
        # vend in bz-data should hold the initial ISO pair.
        assert "2026-06-10" in html
        assert "2026-06-20" in html
        assert 'bz-attr:value="JSON.stringify([vstart, vend])"' in html

    def test_click_outside_closes_popover(self) -> None:
        html = _render()
        # V3 : no ``@click.outside`` modifier ; the bz-init dismiss
        # registers ``$bz.helpers.clickOutside`` on the wrapper.
        assert "bz-init=" in html
        assert "clickOutside" in html


class TestBindable:
    def test_bindable_props(self) -> None:
        # What the picker CHOOSES to bind; its displayed contents (the
        # separator) bind by construction since 2026-11-06.
        assert set(DateRangePicker.BINDABLE_PROPS) - set(DateRangePicker.__displayed_props__) == {"value", "min", "max", "disabled"}

    def test_autoname_from_value(self) -> None:
        assert DateRangePicker.AUTONAME_FROM == "value"

    def test_autoname_from_server_state_field(self) -> None:
        # A range round-trips as a 2-element LIST (the store/wire shape) ;
        # ``list`` is stamped with ``field_name`` so a server-bound range
        # autonames its hidden input from the field (regression guard).
        from bretzel.state import ServerState, field
        from bretzel.state.scopes.client import rendering_scope

        class _S(ServerState):
            holiday: dt.date = field(
                default_factory=lambda: [dt.date(2026, 6, 15), dt.date(2026, 6, 22)]
            )

        with rendering_scope(), render_isolated():
            out = serialize(DateRangePicker(value=_S().holiday).render())
        assert 'name="_S.holiday"' in out
        assert out.count('name="_S.holiday"') == 1

    def test_value_binding_seeds_pair_and_pushes_to_store(self) -> None:
        from bretzel.state import ClientState, field
        from bretzel.state.scopes.client import rendering_scope

        class _DRP(ClientState, persist="memory"):
            range_v: list = field(default_factory=list)

        with render_isolated(), rendering_scope():
            state = _DRP()
            html = serialize(DateRangePicker(value=state.range_v).render())
        # V3 : no ``$watch`` pair. vstart / vend seed from the store
        # list, and the wrapper bz-effect pushes ``[vstart, vend]``
        # back into the store on every endpoint change. (``=`` is
        # HTML-attr-escaped to ``=`` inside ``bz-effect``.)
        assert "$bz.state._DRP.default.range_v" in html
        assert "bz-effect=" in html
        assert (
            "$bz.state._DRP.default.range_v = [vstart, vend]" in html
            or "$bz.state._DRP.default.range_v = [vstart, vend]" in html
        )


class TestForwarding:
    def test_min_max_forwarded(self) -> None:
        html = _render(
            min=dt.date(2026, 1, 1),
            max=dt.date(2026, 12, 31),
        )
        assert 'min="2026-01-01"' in html
        assert 'max="2026-12-31"' in html

    def test_weekstart_forwarded(self) -> None:
        html = _render(week_start=0)
        assert 'weekstart="0"' in html


def _field_tags(html: str) -> list[str]:
    import re
    return [m.group() for m in re.finditer(r'<input[^>]*>', html)
            if 'type="text"' in m.group()]


class TestValueCommands:
    """``.set()`` and ``.clear()`` speak the value's shape: a pair."""

    def test_clear_empties_both_ends(self) -> None:
        with render_isolated():
            command = DateRangePicker().clear()
        assert '{value: ["", ""]}' in command

    def test_bz_set_writes_both_ends(self) -> None:
        html = _render()
        handler = html.split('bz-on:bz-set="')[1].split('"')[0]
        assert "vstart = " in handler and "vend = " in handler
        assert "vstart = $event.detail.value" not in handler

    def test_bound_clear_writes_a_pair_to_the_store(self) -> None:
        class S(ClientState, persist="memory"):
            span: list = field(default_factory=list)

        with rendering_scope(), render_isolated():
            command = DateRangePicker(value=S().span).clear()
        assert '["", ""]' in command


class TestFocusBlurRelocatedToFields:
    """Regression : ``on_focus=``/``on_blur=`` used to stay on
    ``root_attrs``, applied to the wrapper ``<div>``. Native
    focus/blur don't bubble, so the handler could structurally never
    fire (unlike ``on_change=``, which correctly bubbles from the
    field inputs to the root). Fixed by relocating both handler
    flavours onto BOTH the start and end fields — unlike Slider's
    handles, start/end are semantically distinct fields a user can
    independently focus, so dropping either would silently miss
    events — combined with each field's own internal ISO-normalise
    blur wiring instead of colliding with it."""

    def test_string_focus_lands_on_both_fields_not_root(self) -> None:
        html = _render(on_focus="console.log(2)")
        root_opening = html[: html.index(">")]
        assert "bz-on:focus" not in root_opening
        fields = _field_tags(html)
        assert len(fields) == 2
        for field in fields:
            assert 'bz-on:focus="console.log(2)"' in field

    def test_string_blur_combines_with_internal_normalise_both_fields(
        self,
    ) -> None:
        html = _render(on_blur="console.log(1)")
        root_opening = html[: html.index(">")]
        assert "bz-on:blur" not in root_opening
        fields = _field_tags(html)
        assert len(fields) == 2
        for field in fields:
            assert "console.log(1)" in field
            marker = "$bz.dates.typed"
            assert marker in field
            assert field.index(marker) < field.index("console.log(1)")

    def test_no_handler_fields_still_have_internal_blur_only(self) -> None:
        html = _render()
        for field in _field_tags(html):
            assert "$bz.dates.typed" in field
            assert "console.log" not in field

    def test_callable_focus_relocates_to_both_fields_not_root(self) -> None:
        html = _render(on_focus=_focus_handler)
        root_opening = html[: html.index(">")]
        assert "hx-post" not in root_opening
        fields = _field_tags(html)
        assert len(fields) == 2
        for field in fields:
            assert "hx-post=" in field
            assert 'hx-trigger="focus"' in field
        assert html.count("hx-post=") == 2

    def test_a_client_change_rides_the_value_carrier(self) -> None:
        """On the root it would also hear the visible field's own
        ``change``, and run twice for one entry."""
        html = _render(on_change="console.log(9)")
        root_opening = html[: html.index(">")]
        assert 'bz-on:change="console.log(9)"' not in root_opening
        assert 'bz-on:change="console.log(9)"' in html
