"""Unit tests for :class:`bretzel.components.inputs.calendar.Calendar`."""

from __future__ import annotations

import datetime as dt

import pytest

from bretzel.components.base import ComponentDefinitionError
from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.calendar import (
    DEFAULT_WEEKDAY_NAMES_SUN_FIRST,
    Calendar,
    compute_month_grid,
    format_month_label,
    rotate_weekday_names,
)
from bretzel.core.serialize import serialize

# ───────────────────────────────────────────────────────────────────────────
# Pure helpers
# ───────────────────────────────────────────────────────────────────────────


class TestComputeMonthGrid:
    def test_returns_6_rows_of_7_cells(self) -> None:
        grid = compute_month_grid(2026, 3, weekstart=1)
        assert len(grid) == 6
        for row in grid:
            assert len(row) == 7

    def test_cells_carry_required_fields(self) -> None:
        grid = compute_month_grid(2026, 3, weekstart=1)
        for row in grid:
            for cell in row:
                assert "date" in cell and isinstance(cell["date"], dt.date)
                assert "in_current_month" in cell
                assert "is_today" in cell

    def test_in_current_month_flag_correct(self) -> None:
        grid = compute_month_grid(2026, 3, weekstart=1)
        # March 2026 has 31 days
        in_month = [c for row in grid for c in row if c["in_current_month"]]
        assert len(in_month) == 31
        assert all(c["date"].month == 3 for c in in_month)

    def test_weekstart_monday_first_day_is_monday(self) -> None:
        # March 1 2026 is a Sunday. weekstart=1 (Monday) → first cell in
        # grid is the previous Monday (Feb 23).
        grid = compute_month_grid(2026, 3, weekstart=1)
        first = grid[0][0]["date"]
        assert first == dt.date(2026, 2, 23)
        # Monday.
        assert first.weekday() == 0

    def test_weekstart_sunday_first_day_is_sunday(self) -> None:
        grid = compute_month_grid(2026, 3, weekstart=0)
        first = grid[0][0]["date"]
        # March 1 IS a Sunday — first cell == March 1.
        assert first == dt.date(2026, 3, 1)

    def test_today_flag(self) -> None:
        today = dt.date(2026, 3, 15)
        grid = compute_month_grid(2026, 3, weekstart=1, today=today)
        flagged = [c for row in grid for c in row if c["is_today"]]
        assert len(flagged) == 1
        assert flagged[0]["date"] == today

    def test_february_leap_year(self) -> None:
        # 2024 is leap → 29 days in Feb.
        grid = compute_month_grid(2024, 2, weekstart=1)
        in_month = [c for row in grid for c in row if c["in_current_month"]]
        assert len(in_month) == 29

    def test_february_non_leap_year(self) -> None:
        grid = compute_month_grid(2025, 2, weekstart=1)
        in_month = [c for row in grid for c in row if c["in_current_month"]]
        assert len(in_month) == 28

    def test_weekstart_clamped_mod_7(self) -> None:
        # weekstart=8 ≡ 1 (Monday)
        a = compute_month_grid(2026, 3, weekstart=8)
        b = compute_month_grid(2026, 3, weekstart=1)
        assert a[0][0]["date"] == b[0][0]["date"]

    def test_weekstart_zero_sunday_emitted_as_attribute(self) -> None:
        # Regression : ``int(values.get("weekstart") or 1)`` silently
        # clobbered a legitimate ``0`` (Sunday) back to ``1`` (Monday)
        # because ``0 or 1`` evaluates to ``1`` in Python. The fix uses
        # a ``None / ""`` guard. Verify weekstart=0 emits as the
        # custom-element attribute ``weekstart="0"``.
        with render_isolated():
            html = serialize(Calendar(weekstart=0).render())
        assert 'weekstart="0"' in html
        # Et la ligne des jours commence bien par DIMANCHE. Elle ne
        # contient plus « Sun » : sans liste explicite, les noms sont
        # calculés par le navigateur depuis ``<html lang>`` — le serveur
        # n'émet que l'INDICE, dans l'ordre de ``Date.getDay()``. C'est
        # cet indice qui porte la rotation, et c'est donc lui qu'on
        # mesure.
        first = html.find("$bz.locale.weekdayNames()[0]")
        second = html.find("$bz.locale.weekdayNames()[1]")
        assert first != -1 and second != -1 and first < second


class TestFormatMonthLabel:
    def test_default_english(self) -> None:
        assert format_month_label(2026, 3) == "March 2026"
        assert format_month_label(2025, 12) == "December 2025"

    def test_custom_month_names(self) -> None:
        fr = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
              "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
        assert format_month_label(2026, 3, fr) == "Mars 2026"
        assert format_month_label(2026, 8, fr) == "Août 2026"


class TestRotateWeekdayNames:
    def test_default_english_monday_start(self) -> None:
        assert rotate_weekday_names(weekstart=1) == [
            "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun",
        ]

    def test_sunday_start(self) -> None:
        assert rotate_weekday_names(weekstart=0) == list(
            DEFAULT_WEEKDAY_NAMES_SUN_FIRST
        )

    def test_custom_names_french(self) -> None:
        fr = ["Di", "Lu", "Ma", "Me", "Je", "Ve", "Sa"]
        assert rotate_weekday_names(fr, weekstart=1) == [
            "Lu", "Ma", "Me", "Je", "Ve", "Sa", "Di",
        ]


# ───────────────────────────────────────────────────────────────────────────
# Component validation
# ───────────────────────────────────────────────────────────────────────────


class TestConstructorValidation:
    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ComponentDefinitionError, match="mode"):
            Calendar(mode="invalid")

    def test_view_mode_no_longer_accepted(self) -> None:
        # ``view`` was dropped — half-baked feature (capped at 1 event
        # per day, read-only with no click affordance). A dedicated
        # ``ui.event_calendar`` will land later with proper multi-event
        # + interactive support.
        with pytest.raises(ComponentDefinitionError, match="mode"):
            Calendar(mode="view")

    def test_weekday_names_wrong_length_raises(self) -> None:
        with pytest.raises(ComponentDefinitionError, match="7"):
            Calendar(weekday_names=["only", "five", "days", "here", "nope"])

    def test_month_names_wrong_length_raises(self) -> None:
        with pytest.raises(ComponentDefinitionError, match="12"):
            Calendar(month_names=["one"])


# ───────────────────────────────────────────────────────────────────────────
# Render — structural smoke
# ───────────────────────────────────────────────────────────────────────────


def _render(*args, **kwargs) -> str:
    with render_isolated():
        return serialize(Calendar(*args, **kwargs).render())


def _cal_handler() -> None: ...


class TestEventRelocation:
    """A CALLABLE handler's HTMX bundle is routed by the event it fires on :
    ``change`` → the hidden input (value carrier) ; ``month_change`` → the
    <bz-calendar> root, renamed to the kebab ``month-change`` CustomEvent ;
    ``focus`` / ``blur`` → the root with their native trigger.

    Regression : the whole bundle used to be popped to the hidden input and
    re-keyed to ``change``, so a callable on_month_change / on_focus /
    on_blur silently fired on change instead of its own event."""

    def test_callable_change_pins_change_on_hidden_input(self) -> None:
        html = _render(value=dt.date(2026, 6, 15), on_change=_cal_handler)
        op = html[html.index("<input"):html.index(">", html.index("<input"))]
        assert "hx-post=" in op and 'hx-trigger="change"' in op

    def test_callable_month_change_kebab_on_root(self) -> None:
        html = _render(on_month_change=_cal_handler)
        assert "hx-post=" in html
        assert 'hx-trigger="month-change"' in html
        assert 'hx-trigger="change"' not in html

    def test_callable_focus_blur_keep_native_trigger(self) -> None:
        fh = _render(on_focus=_cal_handler)
        assert "hx-post=" in fh and 'hx-trigger="focus"' in fh
        bh = _render(on_blur=_cal_handler)
        assert "hx-post=" in bh and 'hx-trigger="blur"' in bh


class TestRenderPickerMode:
    def test_root_is_bz_calendar_custom_element(self) -> None:
        html = _render()
        # The root tag is the custom element — idiomorph morphs its
        # attributes freely, the JS side handles re-renders.
        assert "<bz-calendar" in html

    def test_wrapper_has_bz_calendar_theme_classes(self) -> None:
        html = _render()
        assert "bz-calendar" in html
        # ``h-fit`` reste dans le slot : la HAUTEUR se dimensionne au
        # contenu sans risque, la grille complétant toujours ses 6
        # semaines.
        assert "h-fit" in html
        # La LARGEUR, elle, a quitté le slot pour la table de tailles le
        # 2026-08-25. En ``w-fit`` elle valait ``max(en-tête, grille)``,
        # donc le libellé du mois la décidait : « septembre » élargissait
        # le calendrier de 14,8 px et la flèche « mois suivant » se
        # dérobait entre deux clics dessus. Un token par palier, donc,
        # et ``w-fit`` doit avoir DISPARU — les deux cohabiteraient sinon
        # sur le même élément, et Tailwind trancherait par l'ordre de sa
        # feuille.
        assert "w-fit" not in html
        assert " w-69 " in html.replace('"', " "), (
            "le palier md ne déclare plus sa largeur — cf. "
            "tests/consistency/test_a_size_step_declares_the_same_keys.py"
        )

    def test_renders_header_with_nav_buttons(self) -> None:
        html = _render()
        assert 'aria-label="Previous month"' in html
        assert 'aria-label="Next month"' in html

    def test_the_weekday_row_is_named_by_the_browser_by_default(self) -> None:
        """Sans liste explicite, les sept noms viennent de la langue.

        Le test disait « in English by default », et c'était vrai : le
        composant figeait la table anglaise au montage, quelle que soit
        la langue de l'app. Ce qu'il gardait n'était donc pas un
        invariant mais le défaut [11]. Ce qui reste vrai — et ce qui
        compte — c'est la ROTATION : ``weekstart=1`` met lundi en tête,
        et les indices émis sont ceux de ``Date.getDay()``.
        """
        html = _render(weekstart=1)
        emitted = [
            html.find(f"$bz.locale.weekdayNames()[{i}]") for i in range(7)
        ]
        assert all(pos != -1 for pos in emitted), "sept colonnes attendues"
        # Lundi (1) d'abord, dimanche (0) en dernier.
        order = sorted(range(7), key=lambda i: emitted[i])
        assert order == [1, 2, 3, 4, 5, 6, 0], order

    def test_an_explicit_list_still_renders_server_side(self) -> None:
        """L'échappatoire tier 2 : les noms donnés partent dans le HTML."""
        html = _render(weekstart=1, weekday_names=[f"J{i}" for i in range(7)])
        assert "$bz.locale.weekdayNames()" not in html
        for day in ("J1", "J2", "J0"):
            assert f">{day}<" in html

    def test_mode_attribute_emitted(self) -> None:
        html = _render()
        assert 'mode="picker"' in html

    def test_ssr_emits_empty_grid_container(self) -> None:
        # The day cells are NOT pre-rendered in HTML — the custom
        # element fills the grid container on ``connectedCallback``.
        # Single render path (JS only) avoids drift between SSR and
        # runtime layout AND saves ~700 chars × 42 cells = ~30 KB
        # per calendar instance.
        html = _render()
        assert "data-bz-cal-grid" in html
        # No pre-rendered cells.
        assert "data-day-cell" not in html

    def test_data_bz_theme_blob_present(self) -> None:
        # Theme classes (composed by Python's compose_class) are
        # handed over as a single JSON blob the JS reads to re-render
        # cells on attribute mutation. Single source of truth.
        html = _render()
        assert "data-bz-theme=" in html
        assert "&quot;day_cell&quot;" in html

    def test_hidden_input_emitted_when_value_bound(self) -> None:
        # The hidden input is the form-data carrier — child of
        # ``<bz-calendar>``, the framework relocates the
        # ``x-bz-event:change`` listener onto it.
        from bretzel.state import ClientState, field
        from bretzel.state.scopes.client import rendering_scope

        class _CalForm(ClientState, persist="memory"):
            picked: str = field(default="")

        with render_isolated(), rendering_scope():
            state = _CalForm()
            html = serialize(Calendar(state.picked).render())
        assert "<input" in html
        assert 'type="hidden"' in html
        assert 'name="picked"' in html

    def test_no_hidden_input_without_form_binding(self) -> None:
        # A bare ``Calendar()`` (no value binding, no on_change) does
        # not participate in form data → no hidden input.
        html = _render()
        assert 'type="hidden"' not in html


class TestRenderRangeMode:
    def test_mode_range_attribute(self) -> None:
        html = _render(mode="range")
        assert 'mode="range"' in html

    def test_initial_range_values_serialised_to_value_attr(self) -> None:
        # The custom element accepts a JSON-stringified [start, end]
        # in its ``value`` attribute.
        html = _render(
            (dt.date(2026, 3, 10), dt.date(2026, 3, 20)),
            mode="range",
        )
        # The value attribute carries the JSON. HTML-escaped quotes.
        assert "2026-03-10" in html
        assert "2026-03-20" in html

    def test_range_initial_value_passed_to_attribute(self) -> None:
        # The SSR cells are absent ; the JS-side renderer computes
        # ``isRangeStart`` / ``isRangeEnd`` from the ``value`` attribute
        # and stamps ``data-range-start`` / ``data-range-end`` itself.
        # We just verify the JSON pair survives into the attribute.
        html = _render(
            (dt.date(2026, 3, 10), dt.date(2026, 3, 20)),
            mode="range",
            month=dt.date(2026, 3, 1),
        )
        # Attribute value carries the JSON pair (HTML-escaped quotes).
        assert "2026-03-10" in html
        assert "2026-03-20" in html


class TestNoIconLeak:
    def test_calendar_constructed_inside_vstack_does_not_leak_chevrons(
        self,
    ) -> None:
        # Regression : ``Calendar.render()`` used to construct
        # ``Icon("chevron-left")`` / ``Icon("chevron-right")``
        # *inside* its render path. ``Icon.__init__`` auto-attaches
        # to ``ctx.parent_stack[-1]``, so a ``serialize_html(
        # ui.calendar(...))`` call would silently register two
        # orphan chevron icons next to the call site (visible as
        # "two arrows at the bottom" in the playground).
        # Fix : emit ``<iconify-icon>`` elements directly inside
        # ``render()`` — no ``Icon`` Component construction.
        from bretzel import ui
        from bretzel.render import serialize_html

        with render_isolated():
            block = ui.vstack()
            with block:
                # Same call shape as the buggy
                # ``emitted_html_block(... , serialize_html(
                # ui.calendar(...)))`` in the playground.
                _ = serialize_html(Calendar())
            assembled = serialize(block.render())

        # The block must have ZERO chevron icons — the calendar's
        # chevrons live exclusively inside the serialised string,
        # not in the parent stack.
        assert "iconify-icon" not in assembled


class TestSizes:
    def test_five_size_paliers_supported(self) -> None:
        # Matches every other input (Input / Button / Select /
        # NumberInput / Slider / Combobox / Avatar) — 5 paliers.
        from bretzel.components.inputs.calendar.theme import (
            CALENDAR_THEME,
        )

        assert set(CALENDAR_THEME["sizes"].keys()) == {
            "xs", "sm", "md", "lg", "xl",
        }

    def test_xs_and_xl_produce_distinct_day_cell_classes(self) -> None:
        html_xs = _render(size="xs")
        html_xl = _render(size="xl")
        assert "w-6 h-6" in html_xs
        assert "w-13 h-13" in html_xl

    def test_sm_and_md_visually_distinct(self) -> None:
        # ``sm`` overrides the day_cell baseline ; ``md`` stays at
        # the baked baseline (``w-9 h-9``). The user complaint that
        # they were "indistinguishable" pointed at the previous theme
        # where sm was ``w-7`` (28px) only slightly off md ``w-9``
        # (36px). New theme : sm is ``w-8 h-8`` (32px) which is
        # halfway, BUT chevron size + month_label text size also drop
        # in sm so the overall scale shift is unambiguous.
        html_sm = _render(size="sm")
        html_md = _render(size="md")
        assert "w-8 h-8" in html_sm
        assert "w-9 h-9" in html_md

    def test_initial_range_values_serialized(self) -> None:
        html = _render(
            (dt.date(2026, 3, 10), dt.date(2026, 3, 20)),
            mode="range",
        )
        assert "2026-03-10" in html
        assert "2026-03-20" in html


class TestCustomElementIntegration:
    def test_root_tag_is_custom_element(self) -> None:
        # ``DEFAULT_TAG = "bz-calendar"`` so idiomorph morphs the
        # custom element's attributes (mode, value, month, …) directly
        # and ``attributeChangedCallback`` re-renders the interior.
        assert Calendar.DEFAULT_TAG == "bz-calendar"
        html = _render()
        assert "<bz-calendar" in html
        assert "</bz-calendar>" in html

    def test_bz_data_only_coordinates_header_state(self) -> None:
        # The Web Component owns its internal picker / range state.
        # The ``bz-data`` on the root is purely for the Python-rendered
        # header (month / year dropdown triggers + prev / next
        # buttons) coordinating with the custom element via the
        # ``bz-attr:month`` reactive attribute binding. It does NOT
        # carry picker logic.
        html = _render()
        # The wrapper bz-data has just the displayed year/month.
        assert 'bz-data="{year:' in html
        assert "bz-attr:month=" in html
        # No picker logic in the bz-data (no ``picked`` / ``rangeStart``
        # fields).
        assert "picked:" not in html
        assert "rangeStart:" not in html

    def test_no_template_x_for(self) -> None:
        # Day cells are SSR-rendered + JS-regenerated on attr change ;
        # no Alpine template iteration.
        html = _render()
        assert "x-for=" not in html


# ───────────────────────────────────────────────────────────────────────────
# Reactive contract — BINDABLE_PROPS
# ───────────────────────────────────────────────────────────────────────────


class TestBindableProps:
    def test_bindable_props_listed(self) -> None:
        assert Calendar.BINDABLE_PROPS == (
            "value", "month", "min", "max", "disabled",
        )

    def test_autoname_from_value(self) -> None:
        assert Calendar.AUTONAME_FROM == "value"

    def test_autoname_from_server_state_field(self) -> None:
        # ``ui.calendar(value=state.day)`` → the hidden form-data input
        # derives ``name="day"`` from the stamped ``date`` field
        # (regression guard : dates used to fall through ``_stamp``).
        from bretzel.state import ServerState, field
        from bretzel.state.scopes.client import rendering_scope

        class _S(ServerState):
            day: dt.date = field(default=dt.date(2026, 6, 15))

        with rendering_scope(), render_isolated():
            out = serialize(Calendar(value=_S().day).render())
        assert 'name="day"' in out
        # …and it does NOT leak onto the <bz-calendar> root (released).
        assert out.count('name="day"') == 1

    def test_events_listed(self) -> None:
        assert Calendar.EVENTS == (
            "change", "month_change", "focus", "blur",
        )

    def test_color_binding_rejected(self) -> None:
        from bretzel.components.base import ComponentUsageError
        from bretzel.state import ClientState, field
        from bretzel.state.scopes.client import rendering_scope

        class _S(ClientState, persist="memory"):
            color: str = field(default="primary")

        with render_isolated(), rendering_scope():
            state = _S()
            with pytest.raises(ComponentUsageError):
                Calendar(color=state.color)


class TestValueBinding:
    def test_value_binding_emits_bz_attr_value(self) -> None:
        # Bindable ``value=`` rides ``bz-attr:value`` on the custom
        # element root ; the V3 directive mutates the ``value``
        # attribute whenever ``$bz.state.X.y`` changes, the custom
        # element's ``attributeChangedCallback`` reacts and re-renders.
        # The state→DOM round-trip back is closed by the
        # ``data-bz-value-path`` handed to the custom element.
        from bretzel.state import ClientState, field
        from bretzel.state.scopes.client import rendering_scope

        class _Cal(ClientState, persist="memory"):
            pick: str = field(default="")

        with render_isolated(), rendering_scope():
            state = _Cal()
            html = serialize(Calendar(state.pick).render())
        assert "bz-attr:value=" in html
        assert "$bz.state._Cal.default.pick" in html
        # The write-back path for user picks / internal nav.
        assert "data-bz-value-path=" in html

    def test_autoname_derives_field_name(self) -> None:
        from bretzel.state import ClientState, field
        from bretzel.state.scopes.client import rendering_scope

        class _Cal2(ClientState, persist="memory"):
            target_date: str = field(default="")

        with render_isolated(), rendering_scope():
            state = _Cal2()
            html = serialize(Calendar(state.target_date).render())
        assert 'name="target_date"' in html


class TestImperativeAPI:
    def test_set_returns_str(self) -> None:
        with render_isolated():
            result = Calendar().set(dt.date(2026, 3, 15))
        assert isinstance(result, str)

    def test_clear_returns_str(self) -> None:
        with render_isolated():
            result = Calendar().clear()
        assert isinstance(result, str)

    def test_focus_blur_return_str(self) -> None:
        with render_isolated():
            cal = Calendar()
            f = cal.focus()
            b = cal.blur()
        assert isinstance(f, str)
        assert isinstance(b, str)

    def test_next_prev_month_return_str(self) -> None:
        with render_isolated():
            cal = Calendar()
            n = cal.next_month()
            p = cal.prev_month()
        assert isinstance(n, str)
        assert isinstance(p, str)

    def test_root_carries_id(self) -> None:
        # _needs_identity True → id rendered for the imperative API
        # dispatch to target.
        html = _render()
        assert "id=" in html
