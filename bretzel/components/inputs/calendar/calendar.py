"""``Calendar`` — month-grid date picker, single or range.

Standalone primitive used directly OR wrapped by
``ui.date_picker`` / ``ui.date_range_picker``. Renders as a
**`<bz-calendar>` custom element** (cf. ``bretzel/runtime/_src/07_calendar.js``)
which owns its internal day-grid state ; configuration lives in
observed HTML attributes that idiomorph can morph freely on every
server refresh. Each attribute change triggers
``attributeChangedCallback`` in JS, which re-renders the internal
day grid.

This is the Web Component escape hatch documented in
``02_morph_hook.js`` philosophy : stateful widgets where the
"scope init-once" friction with idiomorph is intractable get to be
custom elements with their own attribute observers. Iconify-icon
already follows this pattern.

DatePicker and DateRangePicker are not custom elements: their root is a
``<div>`` that hosts a ``<bz-calendar>`` and syncs with it through
``bz-effect`` + ``setAttribute``.

Two modes :

- ``picker`` (default) : single date pick. ``value: date`` (or ``None``).
- ``range`` : start + end pick. ``value: tuple[date, date]`` (or ``None``).
  First click sets start ; second click closes the range. Hovering
  between the two highlights the preview.

Form integration : ``AUTONAME_FROM = "value"`` derives the HTML
``name`` from the bound field. A hidden ``<input type="hidden">``
child of ``<bz-calendar>`` serialises the value (ISO ``YYYY-MM-DD``
for single, JSON-stringified ISO pair for range) and the relocated
change handler rides onto it.

Runtime notes :

- Only the Python plumbing AROUND ``<bz-calendar>`` is framework-wired ;
  the custom element itself (day grid, range preview, dispatch,
  ``bz-set`` / ``bz-prev-month`` / ``bz-next-month`` listeners,
  ``$bz.state`` write-back) is untouched.
- The root's header coordination state is ``bz-data="{year, month}"``.
  ``bz-attr:month`` propagates a header dropdown / prev-next click onto
  the observed ``month`` attribute, firing ``attributeChangedCallback`` ;
  ``bz-on:month-change`` syncs the element's internal nav back into
  ``year`` / ``month``.
- The inline month / year dropdowns use their own ``bz-data="{open:
  false}"`` + ``bz-init`` clickOutside/escapeKey dismiss.
- A server-callable ``on_change`` is relocated to the hidden input
  (which fires a bubbling synthetic ``change``) ; a string ``on_change``
  rides ``bz-on:change`` on the root (the synthetic ``change`` bubbles).

Imperative API (cf. ``imperative-api.md``) :

- ``.set(value)`` — write-through binding if any, else dispatches
  ``bz-set`` CustomEvent on the element (the custom element listens
  for it and updates its state).
- ``.clear()`` — write ``None`` / empty pair.
- ``.focus()`` / ``.blur()`` — focus the first focusable day cell.
- ``.next_month()`` / ``.prev_month()`` — dispatch ``bz-next-month`` /
  ``bz-prev-month`` CustomEvent on the element.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    ComponentDefinitionError,
    reactive_prop,
    stamp_display_none,
)
from bretzel.components.base._wiring import (
    SERVER_ACTION_ATTRS,
    anchored_dismiss_init,
    bool_attr,
    retrigger,
    server_sync_marker,
    theme_context,
    trigger_event,
)
from bretzel.components.inputs._wiring import date_to_iso
from bretzel.components.inputs.calendar.theme import CALENDAR_THEME
from bretzel.core.tree import Element, HtmlNode, Node
from bretzel.render import template, text

# ───────────────────────────────────────────────────────────────────────────
# Public defaults — English month/weekday names (Sunday-canonical order)
# ───────────────────────────────────────────────────────────────────────────


DEFAULT_WEEKDAY_NAMES_SUN_FIRST: tuple[str, ...] = (
    "Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat",
)
"""Weekday names indexed by ``Date.getDay()`` (0 = Sunday, … 6 = Saturday).

``weekstart=`` rotates this tuple at render time. Override per call site
via ``weekday_names=`` (still in Sunday-first order, the rotation is the
component's job)."""

DEFAULT_MONTH_NAMES: tuple[str, ...] = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
"""Month names indexed 0..11 — matches ``Date.getMonth()``."""


# ───────────────────────────────────────────────────────────────────────────
# Pure helpers — exposed for tests, SSR, and custom date pickers
# ───────────────────────────────────────────────────────────────────────────


def compute_month_grid(
    year: int,
    month: int,
    weekstart: int = 1,
    today: _dt.date | None = None,
) -> list[list[dict[str, Any]]]:
    """Return 6 rows × 7 cells covering the displayed month.

    Mirror of the JS computation inside ``<bz-calendar>`` — used for
    SSR-rendered initial DOM and for tests."""
    weekstart = weekstart % 7
    today = today or _dt.date.today()
    first = _dt.date(year, month, 1)
    first_dow_sun = (first.weekday() + 1) % 7
    offset = (first_dow_sun - weekstart) % 7
    grid: list[list[dict[str, Any]]] = []
    for week in range(6):
        row: list[dict[str, Any]] = []
        for col in range(7):
            cell_date = first + _dt.timedelta(days=week * 7 + col - offset)
            row.append({
                "date": cell_date,
                "in_current_month": cell_date.month == month,
                "is_today": cell_date == today,
            })
        grid.append(row)
    return grid


def format_month_label(
    year: int,
    month: int,
    month_names: tuple[str, ...] | list[str] | None = None,
) -> str:
    """``"<MonthName> <Year>"`` (e.g. ``"March 2026"``)."""
    names = month_names or DEFAULT_MONTH_NAMES
    return f"{names[month - 1]} {year}"


def rotate_weekday_names(
    weekday_names: tuple[str, ...] | list[str] | None = None,
    weekstart: int = 1,
) -> list[str]:
    """Return the 7 weekday names rotated so ``weekstart`` comes first."""
    names = list(weekday_names or DEFAULT_WEEKDAY_NAMES_SUN_FIRST)
    weekstart = weekstart % 7
    return names[weekstart:] + names[:weekstart]


def _date_to_iso(value: Any) -> str:
    """``Calendar``'s date coercion — the shared one, bound to this
    component's name for the error message (audit F50: the three
    components of the date family each carried an identical copy)."""
    return date_to_iso(value, owner="Calendar")


#: The format the grid compares: ``YYYY-MM-DD``, exactly.
_ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def normalise_marks(marks: Any) -> dict[str, int]:
    """``marks=`` → ``{"2026-08-14": 3}``, in both of its call shapes.

    Two shapes because both needs exist, and the simpler one must not
    pay for the other:

    - an ITERABLE of dates — "those days have something";
    - a DICTIONARY date → integer — "that day has three".

    The integer covers the boolean, so a single prop is enough: that is
    the decision taken with the user on 2026-08-25. It is not drawn (a
    dot stays a dot, at a 24 px cell one more digit would be
    illegible) but it is ANNOUNCED — the cell's accessible name carries
    it, and a hover shows it.

    A zero count removes the mark rather than setting an empty one: a
    dictionary built by a ``Counter`` contains some, and raising on them
    would force every caller to filter it.
    """
    if not marks:
        return {}
    pairs = (
        marks.items() if hasattr(marks, "items")
        else ((day, 1) for day in marks)
    )
    out: dict[str, int] = {}
    for day, count in pairs:
        iso = _date_to_iso(day)
        # ⚠️ ``date_to_iso`` returns a string AS IS — that is what lets
        # a client binding through, and it is intended over there. Here
        # the key ends up in a dictionary indexed by date: a free string
        # would match no cell there, in silence. So we check the SHAPE.
        if not _ISO_DAY.fullmatch(iso or ""):
            raise ComponentDefinitionError(
                f"marks: {day!r} is not a date. Expected a "
                f"``datetime.date`` or an ISO ``YYYY-MM-DD`` string."
            )
        if not isinstance(count, int) or isinstance(count, bool):
            # ``bool`` is an ``int`` in Python, and ``{day: True}`` is a
            # credible typo for ``[day]``. Letting it through would put
            # "1" on screen without anybody wanting it.
            raise ComponentDefinitionError(
                f"marks[{day!r}] must be an integer, got {count!r}. "
                f"For a plain \"something happens here\", pass a list of "
                f"dates rather than a dictionary."
            )
        if count < 0:
            raise ComponentDefinitionError(
                f"marks[{day!r}] = {count}: a negative count has no "
                f"possible render."
            )
        if count:
            out[iso] = count
    return dict(sorted(out.items()))


def _disabled_dates_to_iso(
    disabled_dates: list[_dt.date] | None,
) -> list[str]:
    return [_date_to_iso(d) for d in (disabled_dates or [])]


# ───────────────────────────────────────────────────────────────────────────
# Component
# ───────────────────────────────────────────────────────────────────────────


# ``week`` (August 2026) returns a SCALAR DATE like ``picker`` — the
# first day of the clicked week, according to ``weekstart``. It
# therefore borrows the same serialisation branch, and differs only in
# what the custom element does with the click (snapping to the start of
# the week) and in its highlighting (the whole row, rendered with the
# band vocabulary ALREADY written for ``range`` — a week IS a closed
# range of seven days).
#
# ``month`` (August 2026) is the only mode that does NOT render days: a
# 12-cell year grid, and a value in ``"YYYY-MM"``. The header's arrows
# move by a YEAR there, and the month selector is removed — it would
# duplicate the grid itself.
#: Ceiling of the year-jump menu. The default, with no ``min`` and no
#: ``max``, is today ± 10 years — that is 21 entries. 200 lets through
#: ALL real uses (a birth date goes back ~120 years, a historical
#: register a few centuries) and cuts the pathological case, which is
#: not a use: a 1,900-year span comes from a malformed ``min``, not from
#: somebody who wants those years.
#:
#: Guarded by ``tests/consistency/test_a_year_dropdown_stays_bounded.py``.
MAX_YEARS_IN_DROPDOWN = 200

_VALID_MODES = ("picker", "range", "week", "month")

# Native HTMX action attrs a server-callable ``on_change`` lands on the
# root via ``emit_attrs`` ; relocated wholesale onto the hidden input
# that carries name+value (the dispatcher reads form-data from there).
# The custom element fires a bubbling synthetic ``change`` on the hidden
# input whenever the value mutates, so ``hx-trigger="change"`` fires.
_ACTION_ATTRS = SERVER_ACTION_ATTRS


class Calendar(Component):
    """Month-grid date picker, single or range. Web Component-backed."""

    THEME: ClassVar[dict[str, Any]] = CALENDAR_THEME
    THEME_KEY: ClassVar[str] = "calendar"
    DEFAULT_TAG: ClassVar[str] = "bz-calendar"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = (
        "value", "month", "min", "max", "disabled",
    )
    # ``next_month`` / ``prev_month`` were shipped and wired but not
    # declared — so absent from the documentation's ``ui.*`` catalogue,
    # which enumerates this ClassVar (audit F20/F21). Same idiom as
    # NumberInput's ``increment`` / ``decrement``.
    IMPERATIVE: ClassVar[tuple[str, ...]] = (
        "set", "clear", "focus", "blur", "next_month", "prev_month",
    )
    EVENTS: ClassVar[tuple[str, ...]] = (
        "change", "month_change", "focus", "blur",
    )

    name: str | None = reactive_prop(default=None, emit_attr=False)
    # BINDABLE props ride emit_attr=True so a ``value=binding`` /
    # ``month=binding`` / etc. registers as ``bz-attr:<attr>="$bz.state.…"``
    # — the directive mutates the HTML attribute when the bound state
    # changes, which fires the custom element's ``attributeChangedCallback``
    # and re-renders. Final attribute values for non-trivial shapes (range
    # JSON, ISO dates) are overridden manually below ``emit_attrs()``.
    value: Any = reactive_prop(default=None, writes=True, names_field=True)
    month: Any = reactive_prop(default=None, writes=True, scope_keys=("year", "month"))
    min: Any = reactive_prop(default=None)
    max: Any = reactive_prop(default=None)
    disabled: bool = reactive_prop(default=False)
    # Non-bindable / design-time props : ``emit_attr=False``
    # because they're either irrelevant to the custom element
    # (color/size — encoded in the data-bz-theme blob) or carried
    # via dedicated attributes set explicitly in ``render()``
    # (mode/weekstart/required which never bind).
    mode: str = reactive_prop(default="picker", emit_attr=False)
    weekstart: int = reactive_prop(default=1, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    required: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        value: Any = None,
        *,
        mode: str | None = None,
        min: Any = None,
        max: Any = None,
        disabled_dates: list[_dt.date] | None = None,
        marks: Any = None,
        month: Any = None,
        weekstart: int | None = None,
        weekday_names: list[str] | None = None,
        month_names: list[str] | None = None,
        color: str | None = None,
        size: str | None = None,
        disabled: bool | None = None,
        required: bool | None = None,
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_month_change: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        if mode is not None and mode not in _VALID_MODES:
            raise ComponentDefinitionError(
                f"Calendar mode={mode!r} not in {_VALID_MODES}"
            )
        # ``None`` when the caller said nothing — and most certainly
        # NOT the English table. That default rendered "August / MON TUE
        # WED" to every app whatever its language, and the only handle
        # was to pass the 19 strings AT EVERY MOUNT (three times on a
        # single CRM screen). With no explicit list, it is the browser
        # that names, from ``<html lang>`` — cf. ``06_locale.js``.
        self._weekday_names = list(weekday_names) if weekday_names else None
        self._month_names = list(month_names) if month_names else None
        if self._weekday_names is not None and len(self._weekday_names) != 7:
            raise ComponentDefinitionError(
                f"weekday_names must have 7 entries, got "
                f"{len(self._weekday_names)}"
            )
        if self._month_names is not None and len(self._month_names) != 12:
            raise ComponentDefinitionError(
                f"month_names must have 12 entries, got "
                f"{len(self._month_names)}"
            )
        self._disabled_dates = list(disabled_dates or [])
        self._marks = normalise_marks(marks)

        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            name=name, value=value, month=month,
            mode=mode, min=min, max=max,
            weekstart=weekstart,
            color=color, size=size,
            disabled=disabled, required=required,
            on_change=on_change,
            on_month_change=on_month_change,
            on_focus=on_focus,
            on_blur=on_blur,
            **kwargs,
        )

    # ── Imperative write-only API ─────────────────────────────────────

    def set(self, value: Any) -> str:
        if isinstance(value, _dt.date):
            value = value.isoformat()
        elif isinstance(value, (list, tuple)):
            value = [
                v.isoformat() if isinstance(v, _dt.date) else v
                for v in value
            ]
        return self._value_command(value)

    def clear(self) -> str:
        return self.set(None)

    def focus(self) -> str:
        return f"document.getElementById('{self.id}').focus()"

    def blur(self) -> str:
        return f"document.getElementById('{self.id}').blur()"

    def next_month(self) -> str:
        binding = self._binding_metadata.get("month")
        if binding is not None:
            return (
                f"(() => {{"
                f"const d = new Date({binding.binding_path()} || new Date());"
                f"d.setMonth(d.getMonth() + 1);"
                f"d.setDate(1);"
                f"{binding.binding_path()} = "
                f"d.getFullYear() + '-' + "
                f"String(d.getMonth() + 1).padStart(2, '0') + '-01';"
                f"}})()"
            )
        return self._dispatch_command("bz-next-month")

    def prev_month(self) -> str:
        binding = self._binding_metadata.get("month")
        if binding is not None:
            return (
                f"(() => {{"
                f"const d = new Date({binding.binding_path()} || new Date());"
                f"d.setMonth(d.getMonth() - 1);"
                f"d.setDate(1);"
                f"{binding.binding_path()} = "
                f"d.getFullYear() + '-' + "
                f"String(d.getMonth() + 1).padStart(2, '0') + '-01';"
                f"}})()"
            )
        return self._dispatch_command("bz-prev-month")


    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        _theme, slots, sizes, size_key, color = theme_context(self)
        size_map = sizes.get(size_key, sizes.get("md", {}))
        mode = self._reactive_values.get("mode") or "picker"
        is_range = mode == "range"
        is_month_mode = mode == "month"
        ws_raw = self._reactive_values.get("weekstart")
        weekstart = (
            int(ws_raw) if ws_raw not in (None, "") else 1
        ) % 7
        disabled = bool(self._reactive_values.get("disabled"))
        required = bool(self._reactive_values.get("required"))
        # When ``disabled`` rides a ClientBinding, the header controls
        # (nav arrows + month/year dropdowns) are rendered ONCE at SSR —
        # a frozen literal ``disabled=False`` would leave them live while
        # the binding flips True (the exact Client-playground bug). Pass
        # the binding through so IconButton / the dropdown triggers emit
        # ``bz-attr:disabled`` and toggle reactively ; fall back to the
        # resolved bool for the literal / design-time case.
        disabled_binding = self._binding_metadata.get("disabled")
        disabled_prop: Any = (
            disabled_binding if disabled_binding is not None else disabled
        )
        # The dropdown triggers are raw ``<button>`` (not a Component) so
        # they can't take ``disabled_prop`` directly — spread this instead :
        # a reactive ``bz-attr:disabled`` when bound, a static ``disabled``
        # for the literal case. ``disabled:`` (Tailwind) applies natively
        # on a ``<button>`` so the cursor/opacity feedback follows.
        if disabled_binding is not None:
            _header_disable_attrs: dict[str, Any] = {
                "bz-attr:disabled": self.path_of(disabled_binding)
            }
        elif disabled:
            _header_disable_attrs = {"disabled": True}
        else:
            _header_disable_attrs = {}

        def _resolve(template: str) -> str:
            return template

        # ── Compose theme classes once ────────────────────────────
        cell_class = " ".join(p for p in (
            _resolve(slots.get("day_cell", "")),
            size_map.get("day_cell", ""),
        ) if p)
        mark_class = " ".join(p for p in (
            _resolve(slots.get("day_mark", "")),
            size_map.get("day_mark", ""),
        ) if p)
        nav_class = " ".join(p for p in (
            slots.get("nav_button", ""),
            size_map.get("nav_button", ""),
        ) if p)
        label_class = " ".join(p for p in (
            slots.get("month_label", ""),
            size_map.get("month_label", ""),
        ) if p)
        weekday_class = " ".join(p for p in (
            slots.get("weekday", ""),
            size_map.get("weekday", ""),
        ) if p)
        chevron_class = (
            "inline-flex shrink-0 justify-center items-center "
            f"align-middle text-current {size_map.get('chevron', 'text-sm')}"
        )

        # Hand the full slot map to the custom element so its JS
        # re-render uses the SAME classes Python composed here. Single
        # source of truth — Python computes, JS executes.
        theme_blob = {
            "header": slots.get("header", ""),
            "month_label": label_class,
            "nav_button": nav_class,
            "weekday_row": slots.get("weekday_row", ""),
            "weekday": weekday_class,
            "week_row": slots.get("week_row", ""),
            "day_cell": cell_class,
            "day_mark": mark_class,
            "chevron_class": chevron_class,
            # ``month`` mode's year grid. Composed here like the
            # others — Python composes, JS executes — so that the same
            # source of truth serves both kinds of grid.
            "month_grid": slots.get("month_grid", ""),
            "month_cell": " ".join(p for p in (
                _resolve(slots.get("month_cell", "")),
                size_map.get("month_cell", ""),
            ) if p),
        }

        # ── Determine initial displayed month ─────────────────────
        # Priority : explicit ``month=`` → the SELECTED value's month →
        # today. Opening on the value's month (not today's) is what every
        # date picker does — otherwise a calendar built with a value in
        # another month paints today's grid and the selection is invisible
        # (the "value in June, grid shows July" bug that false-FAILed the
        # clear / focus function tests). A bound value (client/server) is
        # not a literal here, so it correctly falls through to today.
        month_raw = self._reactive_values.get("month")
        if isinstance(month_raw, _dt.date):
            initial_displayed = month_raw.replace(day=1)
        elif isinstance(month_raw, str) and month_raw:
            initial_displayed = _dt.date.fromisoformat(month_raw).replace(day=1)
        else:
            seed = self._reactive_values.get("value")
            if isinstance(seed, (list, tuple)):        # range → open on start
                seed = seed[0] if seed else None
            if isinstance(seed, str) and seed:
                try:
                    seed = _dt.date.fromisoformat(seed)
                except ValueError:
                    seed = None
            seed = seed if isinstance(seed, _dt.date) else None
            initial_displayed = (seed or _dt.date.today()).replace(day=1)

        # ── Initial value (ISO string for picker, JSON pair for range) ─
        raw_value = self._reactive_values.get("value")
        if is_range:
            if isinstance(raw_value, (list, tuple)) and len(raw_value) == 2:
                initial_range_start = _date_to_iso(raw_value[0])
                initial_range_end = _date_to_iso(raw_value[1])
                initial_value_attr = json.dumps(
                    [initial_range_start, initial_range_end]
                )
            else:
                initial_range_start = ""
                initial_range_end = ""
                initial_value_attr = ""
            initial_picker = ""
        elif mode == "month":
            # Value in ``"YYYY-MM"``. A ``date`` is accepted and
            # TRUNCATED — the developer who passes ``date(2026, 8, 14)``
            # visibly wants "August 2026", and refusing would cost them
            # a ``.strftime`` for nothing. The string, on the other hand,
            # passes as is: it is the canonical form.
            if isinstance(raw_value, _dt.date):
                initial_picker = f"{raw_value.year:04d}-{raw_value.month:02d}"
            else:
                initial_picker = str(raw_value or "")[:7]
            initial_value_attr = initial_picker
            initial_range_start = ""
            initial_range_end = ""
        else:
            initial_picker = _date_to_iso(raw_value) if raw_value else ""
            initial_value_attr = initial_picker
            initial_range_start = ""
            initial_range_end = ""

        value_binding = self._binding_metadata.get("value")
        month_binding = self._binding_metadata.get("month")

        # ── Event handling ─────────────────────────────────────────
        # A **server-callable** ``on_change`` lands its native HTMX
        # action bundle (``hx-post`` + ``hx-trigger`` + …) on the root
        # via ``emit_attrs`` ; relocate the whole bundle to the hidden
        # input — the dispatcher reads ``name`` + ``value`` from the
        # source element to build form data, and those live on the
        # hidden input. The custom element fires a bubbling synthetic
        # ``change`` on the hidden input whenever the value mutates, so
        # ``hx-trigger="change"`` fires there. (Mirror of Select's
        # change relocation.)
        #
        # A **string** ``on_change`` rides ``bz-on:change`` ; it stays
        # on the ``<bz-calendar>`` root because the synthetic ``change``
        # bubbles up to the root where the listener catches it (no
        # name/value read needed for a client string handler).
        #
        # ``month_change`` is dispatched as a CustomEvent on the root.
        # ``emit_attrs`` already produced ``bz-on:month_change`` (string)
        # or the HTMX bundle keyed on ``month_change`` ; rename to the
        # kebab event name ``month-change`` the custom element actually
        # dispatches.
        root_attrs = self.emit_attrs()
        # Autoname (base ``emit_attrs``) injects ``name`` onto the root,
        # but the form-data carrier is the hidden ``<input>`` below
        # (``name`` is derived independently a few lines down). Release it
        # from the ``<bz-calendar>`` root so the name lives in one place.
        self.release_root_attr("name", root_attrs)
        relocated_to_hidden: dict[str, Any] = {}
        # Server-callable bundle — route by the event it fires on. The
        # base emits ONE ``hx-post`` keyed to its event's ``hx-trigger`` :
        #   ``change``       → the hidden input (the value carrier, which
        #                      dispatches a synthetic ``change``) ;
        #   ``month_change`` → stays on the <bz-calendar> root, renamed to
        #                      the kebab ``month-change`` CustomEvent ;
        #   ``focus`` / ``blur`` → stay on the root with their native
        #                      trigger.
        # The EVENT, not the string: ``hx-trigger`` carries the modifiers
        # of a ``debounce=`` / ``throttle=``. Both named branches below
        # used to overwrite them by rewriting the whole trigger.
        server_trigger = root_attrs.get("hx-trigger", "")
        server_event = trigger_event(root_attrs)
        if "hx-post" in root_attrs:
            bundle = {a: root_attrs.pop(a)
                      for a in _ACTION_ATTRS if a in root_attrs}
            if server_event == "change":
                relocated_to_hidden.update(bundle)
            elif server_event == "month_change":
                bundle["hx-trigger"] = retrigger(server_trigger, "month-change")
                root_attrs.update(bundle)
            else:
                # focus / blur — keep the base's native trigger on the root.
                root_attrs.update(bundle)
        # ``month_change`` STRING form (``bz-on:month_change``) → kebab.
        for ev_attr in list(root_attrs.keys()):
            if ev_attr == "bz-on:month_change":
                root_attrs["bz-on:month-change"] = root_attrs.pop(ev_attr)

        # ── Form-data name (autoname) ─────────────────────────────
        fallback = "value" if relocated_to_hidden else None
        name = self._reactive_values.get("name") or self._derive_field_name() or fallback

        # ── Hidden input (form-data carrier) ──────────────────────
        hidden_nodes: list[Node] = []
        if name or relocated_to_hidden:
            hidden_attrs: dict[str, Any] = {
                "type": "hidden",
                "value": initial_value_attr,
            }
            if name:
                hidden_attrs["name"] = str(name)
            if required:
                hidden_attrs["required"] = True
            hidden_attrs.update(relocated_to_hidden)
            hidden_nodes.append(
                Element(tag="input", attrs=hidden_attrs, children=())
            )

        # ── SSR initial DOM : header + weekday row + EMPTY grid ─────
        # Day cells are NOT pre-rendered in HTML — the custom element
        # fills them on ``connectedCallback`` via the same code path
        # as subsequent ``attributeChangedCallback`` re-renders.
        # Single render path (JS) means : no drift between SSR layout
        # and runtime layout, smaller HTML payload (1700 cells × ~700
        # chars on the playground = ~1 MB saved), and the Tailwind
        # safelist already covers the day-cell classes from the
        # Reference card's color/size demos. Visual : the calendar
        # outline paints immediately, the grid cells appear ~50 ms later
        # when the runtime script runs.
        #
        # ⚠️ The WEEKDAY row changed sides on 2026-08-24: with no
        # explicit ``weekday_names=``, it leaves as seven EMPTY ``<div>``
        # carrying a ``bz-text`` — their names come from ``Intl``, which
        # only the browser has. It therefore appears with the grid, not
        # before. That is the price of a calendar that speaks the app's
        # language, and it is only paid on the default path: an explicit
        # list is always rendered server-side.
        min_raw = self._reactive_values.get("min")
        max_raw = self._reactive_values.get("max")
        min_iso = _date_to_iso(min_raw)
        max_iso = _date_to_iso(max_raw)
        disabled_iso_set = set(
            _disabled_dates_to_iso(self._disabled_dates)
        )

        # ── Python-rendered header : prev IconButton, month dropdown,
        #    year dropdown, next IconButton. We build the dropdowns
        #    inline as Elements (not via ui.dropdown) because :
        #    1. ui.dropdown re-renders the trigger Component internally,
        #       wiping any ``bz-text`` patch we apply to the trigger
        #       Element — labels would never become reactive ;
        #    2. we want a guaranteed ``max-h-64 overflow-y-auto`` on
        #       the panel so 21 year items + tall calendars scroll
        #       cleanly instead of running off the page.
        #    The state still lives in the ``<bz-calendar>`` root's
        #    ``bz-data="{year, month}"`` (see below) ; each inline
        #    dropdown adds its own ``open`` flag.
        from bretzel.components.actions.icon_button import (
            IconButton as _IconButton,
        )
        from bretzel.core.tree import TextNode as _TextNode

        today_year_for_range = _dt.date.today().year
        if isinstance(min_raw, _dt.date):
            year_min_hd = min_raw.year
        elif min_iso:
            year_min_hd = int(min_iso.split("-")[0])
        else:
            year_min_hd = today_year_for_range - 10
        if isinstance(max_raw, _dt.date):
            year_max_hd = max_raw.year
        elif max_iso:
            year_max_hd = int(max_iso.split("-")[0])
        else:
            year_max_hd = today_year_for_range + 10
        year_min_hd = min(year_min_hd, initial_displayed.year)
        year_max_hd = max(year_max_hd, initial_displayed.year)

        # ── The year grid is BOUNDED ────────────────────────────────
        #
        # The menu below renders one ``<button>`` per year, hard in the
        # DOM. With no ceiling, the span comes as is from ``min`` /
        # ``max`` — and ``int("137".split("-")[0])`` is the year 137.
        #
        # Measured on 2026-08-27:
        #
        #     ui.date_picker(min="2026-01-01")  ->  17,622 B,    29 <button>
        #     ui.date_picker(min="137")         -> 463,581 B, 1,918 <button>
        #
        # The server render stays instant (0.01 s) — it is the BROWSER
        # that takes ~114 s to swallow the result, which made
        # ``pytest -m audit`` hang on this component.
        #
        # ⚠️ Bounding changes NOTHING about the constraint: ``min`` /
        # ``max`` still decide which dates are selectable. This menu is a
        # JUMP affordance, and a jump is not chosen from a list of 1,900
        # buttons — beyond that, you type the date.
        #
        # The window is CENTRED on the displayed year, not truncated at
        # one end: truncating the end would make the menu useless for
        # somebody who has just opened the calendar on 1912.
        span = year_max_hd - year_min_hd + 1
        if span > MAX_YEARS_IN_DROPDOWN:
            half = MAX_YEARS_IN_DROPDOWN // 2
            anchor = initial_displayed.year
            lo = max(year_min_hd, anchor - half)
            hi = min(year_max_hd, lo + MAX_YEARS_IN_DROPDOWN - 1)
            # If the anchor is near the top of the span, ``hi`` has
            # been clipped by ``year_max_hd``: we take the room back at
            # the bottom.
            lo = max(year_min_hd, hi - MAX_YEARS_IN_DROPDOWN + 1)
            year_min_hd, year_max_hd = lo, hi

        # In ``month`` mode the grid shows a whole YEAR, so the arrows
        # move by a year — otherwise they would change nothing visible,
        # the grid not depending on the displayed month.
        prev_step = "year -= 1" if is_month_mode else (
            "month === 0 ? (year -= 1, month = 11) : (month -= 1)"
        )
        next_step = "year += 1" if is_month_mode else (
            "month === 11 ? (year += 1, month = 0) : (month += 1)"
        )
        prev_btn = _IconButton(
            "chevron-left",
            variant="ghost",
            size=size_key,
            color=color,
            disabled=disabled_prop,
            # ``shrink-0``: without it the arrow SHRINKS when the
            # month's label is long — measured on 2026-08-25, 40 px on
            # "août" against 31.6 px on "septembre". Its right edge is
            # fixed, so it was its LEFT edge that moved by 8.4 px: you
            # click, the target slips away. It is the label that must
            # give (it has ``truncate``), never the command.
            # The size comes from the CALENDAR's theme, not from
            # IconButton's: its ``md`` step is 40 px where this theme
            # declares 32 (``nav_button: w-8``). The token was therefore
            # honoured by the JS render and ignored by the Python one,
            # and those 2 × 8 px too many made the header overflow — the
            # 16.8 px measured. The ``!`` are necessary: at equal
            # specificity, Tailwind decides by its sheet's order, so
            # without them the winner is unpredictable.
            classes="shrink-0 " + size_map.get("nav_button", ""),
            **{
                "bz-on:click": prev_step,
                "aria-label": text(
                    "calendar.previous_year" if is_month_mode
                    else "calendar.previous_month"
                ),
            },
        )
        Component._detach_from_parent(prev_btn)
        next_btn = _IconButton(
            "chevron-right",
            variant="ghost",
            size=size_key,
            color=color,
            disabled=disabled_prop,
            # ``shrink-0``: without it the arrow SHRINKS when the
            # month's label is long — measured on 2026-08-25, 40 px on
            # "août" against 31.6 px on "septembre". Its right edge is
            # fixed, so it was its LEFT edge that moved by 8.4 px: you
            # click, the target slips away. It is the label that must
            # give (it has ``truncate``), never the command.
            # The size comes from the CALENDAR's theme, not from
            # IconButton's: its ``md`` step is 40 px where this theme
            # declares 32 (``nav_button: w-8``). The token was therefore
            # honoured by the JS render and ignored by the Python one,
            # and those 2 × 8 px too many made the header overflow — the
            # 16.8 px measured. The ``!`` are necessary: at equal
            # specificity, Tailwind decides by its sheet's order, so
            # without them the winner is unpredictable.
            classes="shrink-0 " + size_map.get("nav_button", ""),
            **{
                "bz-on:click": next_step,
                "aria-label": text(
                    "calendar.next_year" if is_month_mode
                    else "calendar.next_month"
                ),
            },
        )
        Component._detach_from_parent(next_btn)

        # Trigger button classes : ghost button look, small label,
        # gap before the chevron, focus ring. ``{bg_color}`` so the ring
        # follows ``color=`` (resolved via the local ``_resolve`` closure,
        # like the other slots), matching the prev/next IconButtons and
        # the wrapping date_picker's frame.
        trigger_cls = _resolve(
            "inline-flex items-center gap-1 px-2 py-1 "
            "rounded-selector text-sm font-medium text-text "
            "not-disabled:hover:bg-text/5 transition-colors "
            "disabled:opacity-40 disabled:cursor-not-allowed "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus)"
        )
        # Panel : absolute under the trigger, scrollable.
        #
        # ⚠️ This comment announced "with a transition on open/close"
        # and there was NONE — not even the dead class the six other
        # panels carried. Corrected by setting it for real on
        # 2026-09-04.
        #
        # FIELD cadence (75 ms): these two menus open INSIDE an already
        # open panel, so at the menu cadence (150) they would look
        # heavier than the surface carrying them.
        # Mechanism of the three classes: a single copy, in
        # ``overlay/dropdown/theme.py``.
        panel_cls = (
            "absolute top-full left-0 mt-1 z-10 min-w-[120px] "
            "max-h-64 overflow-y-auto "
            "rounded-box border border-text/10 bg-interface shadow-lg "
            "py-1 "
            "transition-[opacity,display] transition-discrete duration-75 starting:opacity-0"
        )
        item_cls = (
            "flex items-center w-full px-3 py-1.5 text-sm cursor-pointer "
            "text-text not-disabled:hover:bg-text/5 transition-colors "
            "outline-none focus-visible:bg-text/5"
        )
        chevron_dropdown_cls = (
            "inline-flex shrink-0 text-current text-xs"
        )

        def _build_dropdown(
            label_expr: str,
            items: list[tuple[str, str]],
            aria_label: str,
            item_labels_are_expressions: bool = False,
        ) -> Element:
            """Build a self-contained dropdown :
            <div bz-data={open}><trigger><panel/items></div>.

            ``label_expr`` is a client expression for the trigger's
            ``bz-text`` (e.g. ``"(['Jan',...,'Dec'])[month]"`` or
            ``"year"``). ``items`` is a list of
            ``(label, on_click_expression)`` pairs.

            The panel starts hidden with a FOUC pre-stamp ; ``.stop`` is
            inlined as ``$event.stopPropagation()`` (no modifier grammar) ;
            dismiss (click-outside + Escape) rides the shared
            ``anchored_dismiss_init`` on ``$el``.
            """
            trigger = Element(
                tag="button",
                attrs={
                    "type": "button",
                    # ``min-w-0`` on the TRIGGER, not only on its
                    # wrapper: ``truncate`` on the label does nothing as
                    # long as the box containing it keeps its content
                    # size. Measured at ``xs`` in French, the label was
                    # 67.7 px in a 61.2 px button — it OVERFLOWED onto
                    # the year selector, which ended up squeezed to
                    # 38.8 px: "septembre2026" stuck together, month
                    # chevron swallowed.
                    "class": trigger_cls + " min-w-0",
                    "aria-label": aria_label,
                    "bz-on:click": "$event.stopPropagation(); open = !open",
                    **_header_disable_attrs,
                },
                children=(
                    Element(
                        tag="span",
                        attrs={"bz-text": label_expr},
                        children=(),
                    ),
                    Element(
                        tag="iconify-icon",
                        attrs={
                            "icon": "lucide:chevron-down",
                            "class": chevron_dropdown_cls,
                        },
                        children=(),
                    ),
                ),
            )
            item_nodes: list[Node] = []
            for lbl, on_click in items:
                item_attrs: dict[str, Any] = {
                    "type": "button",
                    "class": item_cls,
                    "bz-on:click": f"{on_click}; open = false",
                }
                # A FLAG rather than a label type: discriminating on
                # ``isinstance`` here looked, to the letter, like the
                # sorting of children by class that
                # ``test_a_parent_that_sorts_children_unwraps_them``
                # forbids — and it was right to say so, the pattern is
                # the same to within a hair.
                if item_labels_are_expressions:
                    item_attrs["bz-text"] = lbl
                    item_children: tuple[Node, ...] = ()
                else:
                    item_children = (_TextNode(lbl),)
                item_nodes.append(Element(
                    tag="button", attrs=item_attrs, children=item_children,
                ))
            panel_attrs: dict[str, Any] = {
                "class": panel_cls,
                "bz-show": "open",
                "role": "menu",
                # ``anchored_dismiss_init``'s contract: every overlay
                # that calls it MUST name its panel ``bzpanel``,
                # otherwise ``$refs.bzpanel`` walks up the scope's
                # prototype chain and resolves an ANCESTOR's panel.
                #
                # Bug reproduced in the browser on 2026-07-29: these
                # dropdowns live in a ``<bz-calendar>`` which itself
                # lives in a ``date_picker``'s panel. Without this ref,
                # the month dropdown's ``clickOutside`` considered THE
                # PICKER's panel as "inside" → a click on the calendar's
                # header did not close it. Control: a click on
                # ``<body>``, on an ``<h1>`` or Escape did close it — so
                # the dismiss was wired, it aimed at the wrong target.
                "bz-ref": "bzpanel",
            }
            # FOUC pre-stamp : the dropdown starts closed at SSR.
            stamp_display_none(panel_attrs)
            panel = Element(
                tag="div",
                attrs=panel_attrs,
                children=tuple(item_nodes),
            )
            return Element(
                tag="div",
                attrs={
                    # ``min-w-0``: that is what allows the label to
                    # give. Without it, a remainder of 0.8 px was enough
                    # to push the arrow away — the guarantee must be
                    # STRUCTURAL (the command never moves), not "it just
                    # about fits in this language".
                    "class": "relative inline-block min-w-0",
                    "bz-data": "{open: false}",
                    "bz-init": anchored_dismiss_init("open"),
                },
                children=(trigger, panel),
            )

        # With no explicit list, the twelve names are COMPUTED by the
        # client: the server cannot produce them (Python's ``locale``
        # module is process-global state, and Babel would be a
        # dependency). The panel stays invisible until ``.bz-ready``, so
        # no flicker — it is the same guarantee that already covers the
        # grid, filled in JS.
        client_months = self._month_names is None
        if client_months:
            month_expr = "$bz.locale.monthName(month)"
            month_labels = [f"$bz.locale.monthName({mi})" for mi in range(12)]
        else:
            month_expr = f"({json.dumps(self._month_names)})[month]"
            month_labels = list(self._month_names)
        month_drop_el = _build_dropdown(
            label_expr=month_expr,
            items=[
                (label, f"month = {mi}")
                for mi, label in enumerate(month_labels)
            ],
            aria_label=text("calendar.month"),
            item_labels_are_expressions=client_months,
        )
        year_drop_el = _build_dropdown(
            label_expr="year",
            items=[
                (str(y), f"year = {y}")
                for y in range(year_min_hd, year_max_hd + 1)
            ],
            aria_label=text("calendar.year"),
        )

        header_el = Element(
            tag="div",
            attrs={
                "data-bz-cal-header": "",
                "class": slots.get("header", ""),
            },
            # In ``month`` mode, the MONTH selector disappears: the
            # grid IS the month selector. Keeping it would make two
            # paths for the same gesture, one of which would have no
            # visible effect on the displayed grid.
            children=tuple(
                el for el in (
                    prev_btn.render(),
                    None if is_month_mode else month_drop_el,
                    year_drop_el,
                    next_btn.render(),
                ) if el is not None
            ),
        )

        # Same split as the months: named by the client for want of an
        # explicit list. The index is ``Date.getDay()``'s (Sunday = 0),
        # rotated here for ``weekstart`` — it is the component that
        # rotates, never the list (trap [14]).
        if self._weekday_names is None:
            # The INDICES rotate, exactly as the names rotate on the
            # other branch — same helper, so a single implementation of
            # the Sunday-first contract (trap [14]).
            weekday_html_parts = [
                f'<div class="{weekday_class}" '
                f'bz-text="$bz.locale.weekdayNames()[{i}]">'
                f'</div>'
                for i in rotate_weekday_names(list(range(7)), weekstart)
            ]
        else:
            weekday_html_parts = [
                f'<div class="{weekday_class}">{n}</div>'
                for n in rotate_weekday_names(self._weekday_names, weekstart)
            ]
        weekdays_html = (
            f'<div data-bz-cal-weekdays class="{slots.get("weekday_row", "")}">'
            f'{"".join(weekday_html_parts)}'
            f'</div>'
        )
        # Empty grid container — JS fills via insertAdjacentHTML at
        # connectedCallback. A morph RE-EMPTIES it (the children go back
        # to the server version) without waking any callback of the
        # custom element: it is the ``bz-init`` set further down on the
        # root that catches up, by calling ``rehydrate()`` after each
        # rescan.
        grid_html = (
            f'<div data-bz-cal-grid class="{slots.get("week_row", "")}"></div>'
        )

        # ``month`` mode: neither a weekday row nor a day grid.
        # Emitting the weekday row anyway would make it FLICKER — it
        # would be painted at the first render then removed by the
        # custom element's first ``_replaceBody``.
        ssr_html = HtmlNode(
            f'<div data-bz-cal-months class="{slots.get("month_grid", "")}">'
            f"</div>"
            if is_month_mode
            else weekdays_html + grid_html
        )

        # ── Root attributes on <bz-calendar> ──────────────────────
        # The WIDTH comes from the sizes table, not from the slot: it
        # depends on the step (7 cells + the two edges), and putting it
        # in the slot would stack it with the table on the same element
        # — the collision ``traps.md`` § "size=: slot ↔ table collision"
        # describes, whose outcome Tailwind decides by its sheet's
        # order.
        root_attrs["class"] = " ".join(filter(None, (
            slots.get("root", ""),
            size_map.get("root", ""),
        )))
        # The root's whole-grid fade + cursor ride ``aria-disabled`` (the
        # ``disabled`` attr does nothing on a custom element — ``:disabled``
        # only matches real form controls). ``emit_attrs`` already put a
        # reactive ``bz-attr:disabled`` on the root for the JS to observe ;
        # mirror it onto ``aria-disabled`` so the CSS feedback toggles too.
        if disabled_binding is not None:
            # A ternary, not the bare path : ``bz-attr`` on a boolean sets
            # ``aria-disabled=""`` (empty), but Tailwind's ``aria-disabled:``
            # variant matches ``[aria-disabled="true"]`` (the string). Same
            # idiom as the header's ``bz-attr:aria-expanded`` ternary.
            root_attrs["bz-attr:aria-disabled"] = (
                bool_attr(self.path_of(disabled_binding))
            )
        elif disabled:
            root_attrs["aria-disabled"] = "true"
        # The framework's "after EVERY rescan" hook, and it is
        # ``bz-effect``, NOT ``bz-init``: that one is one-shot per NODE
        # (``el._bzInitDone``, which survives a rebind), yet idiomorph
        # morphs in place — the node survives, so a ``bz-init`` would
        # never run again. A ``bz-effect`` is disposed then redone at
        # every ``bindEl``, so its body runs again on every swap. Same
        # choice and same reason as SignaturePad's ``_observe()``.
        #
        # What it catches up: a refresh of the zone containing the
        # calendar puts its children back to the server version — that
        # is to say the EMPTY grid (measured on 2026-08-21: 42 cells at
        # the first render, 0 after a refresh, and for good).
        # ``rehydrate()`` only repaints if the body was really wiped, so
        # an unrelated swap costs only a ``querySelector``.
        root_attrs["bz-effect"] = "$el.rehydrate && $el.rehydrate()"
        root_attrs["mode"] = mode
        root_attrs["weekstart"] = str(weekstart)
        root_attrs["month"] = initial_displayed.isoformat()
        if initial_value_attr:
            root_attrs["value"] = initial_value_attr
        if min_iso:
            root_attrs["min"] = min_iso
        if max_iso:
            root_attrs["max"] = max_iso
        if disabled:
            root_attrs["disabled"] = True
        if disabled_iso_set:
            root_attrs["disabled-dates"] = json.dumps(
                sorted(disabled_iso_set)
            )
        if self._marks:
            root_attrs["marks"] = json.dumps(self._marks)
            # The accessible name's template leaves from here,
            # RESOLVED server-side: the grid is built in JavaScript, and
            # the framework's word table exists only in Python. Without
            # this hand-off, a marked cell would announce itself in
            # English whatever the app's language.
            root_attrs["data-bz-mark-label"] = template("calendar.marked")
        if self._weekday_names is not None:
            root_attrs["weekday-names"] = json.dumps(self._weekday_names)
        if self._month_names is not None:
            root_attrs["month-names"] = json.dumps(self._month_names)
        root_attrs["data-bz-theme"] = json.dumps(theme_blob)
        # bz-data for the Python-rendered header. ``year`` and
        # ``month`` (0-indexed) drive the dropdown trigger labels and
        # the prev/next handlers. ``bz-attr:month`` (reactive attribute
        # binding below) propagates user changes to the bz-calendar's
        # observed ``month`` attribute, which fires the custom
        # element's ``attributeChangedCallback`` and re-renders the
        # grid. ``bz-on:month-change`` syncs back from the custom
        # element to the scope for nav driven from the imperative API
        # (``.prev_month()`` / ``.next_month()``) or internal grid nav.
        #
        # No getters here — ``year`` / ``month`` are flat signals, so the
        # ``scope.absorb`` getter-freeze trap doesn't apply. absorb also
        # preserves those signals across a morph — so a SERVER change to a
        # bound ``month=state.field`` is ignored on refresh unless the keys
        # opt into ``_serverSync``. Gate on server-backed (a ClientBinding
        # lives in the store; a literal keeps its client nav through an
        # unrelated refresh).
        month_sync = server_sync_marker(
            "year", "month", enabled=self._value_server_backed("month"))
        root_attrs["bz-data"] = (
            f"{{year: {initial_displayed.year}, "
            f"month: {initial_displayed.month - 1}"
            + (f",{month_sync}" if month_sync else "") + "}"
        )
        root_attrs["bz-attr:month"] = (
            "year + '-' + String(month + 1).padStart(2, '0') + '-01'"
        )
        # Inline sync handler stays present alongside any user-supplied
        # ``bz-on:month-change`` (string) so the wrapper state never
        # drifts. A server-callable ``on_change``/``on_month_change``
        # rides ``hx-*`` (not ``bz-on:``), so it never collides here.
        existing_mc = root_attrs.get("bz-on:month-change", "")
        sync_expr = (
            "year = $event.detail.year; "
            "month = $event.detail.month - 1"
        )
        root_attrs["bz-on:month-change"] = (
            f"{sync_expr}; {existing_mc}" if existing_mc else sync_expr
        )
        # Year range for the header year-select. Auto-derived from
        # ``min`` / ``max`` if set, otherwise default ±10 years from
        # ``today``. The custom element widens the range live if the
        # displayed year sits outside (e.g. ``month=date(1850, …)``
        # without bounds) so the select always shows the live year.
        today_year = _dt.date.today().year
        if isinstance(min_raw, _dt.date):
            year_min = min_raw.year
        elif min_iso:
            year_min = int(min_iso.split("-")[0])
        else:
            year_min = today_year - 10
        if isinstance(max_raw, _dt.date):
            year_max = max_raw.year
        elif max_iso:
            year_max = int(max_iso.split("-")[0])
        else:
            year_max = today_year + 10
        root_attrs["data-bz-year-min"] = str(year_min)
        root_attrs["data-bz-year-max"] = str(year_max)
        # Hand the bound state path(s) to the custom element so it can
        # write back on internal mutations (user pick, prev/next nav).
        # Without these the Client playground / Client events stay
        # silent — the framework's ``bz-attr:<attr>`` only flows state →
        # attribute, this closes the round-trip.
        # ⚠️ Both paths are ASSIGNABLE: ``07_calendar.js::_writeBinding``
        # splits them on ``.`` then walks to the leaf to write there. A
        # ClientExpression is structurally invalid there (it is not a
        # dotted path) — hence ``value``/``month`` in ``TWO_WAY_PROPS``,
        # which rejects it at construction. ``path_of`` stays correct for
        # the plain binding.
        if value_binding is not None:
            root_attrs["data-bz-value-path"] = self.path_of(value_binding)
        if month_binding is not None:
            root_attrs["data-bz-month-path"] = self.path_of(month_binding)

        return Element(
            tag=self._tag,
            attrs=root_attrs,
            children=(*hidden_nodes, header_el, ssr_html),
        )
