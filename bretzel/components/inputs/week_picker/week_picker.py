"""``WeekPicker`` — a WEEK field, selected by row.

Usage ::

    ui.week_picker(value=state.week)               # "2026-08-03"
    ui.week_picker(value=state.week, week_start=0)  # Sunday weeks

**The value is the ISO date of the week's FIRST day.** A week IS its
first day — it is what most back ends store, and it stays an ordinary
date: comparable, filterable, displayable, and compatible with anything
that already eats ISO. Whoever wants the end adds six days.

The starting day follows ``week_start`` (default Monday). It is not a
cosmetic detail: the same date does not belong to the same week
depending on the setting, so returning the Monday when the user asked
for Sunday weeks would be a lie about the value.

**The snapping applies to TYPING too.** Typing any date into the field
does not leave that date: it is brought back to the start of its week on
blur, exactly like a click. Without that, the field and the grid would
say two different things — and the posted value would depend on how the
user entered it.

The component is thin: frame, popover, hidden input and routing come
from ``_picker_field``; the grid and the row highlighting come from
``ui.calendar(mode="week")``. What is left here is the codec and the
normaliser.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base.arguments import reject_attribute_component
from bretzel.components.base.commands import ValueCommands
from bretzel.components.base.focus import FocusCommands
from bretzel.components.base.overlay_wiring import install_open_close_toggle
from bretzel.components.inputs._picker_field import render_calendar_field, value_expr
from bretzel.components.inputs._wiring import date_to_iso
from bretzel.components.inputs.week_picker.theme import WEEK_PICKER_THEME
from bretzel.core.tree import Element
from bretzel.render import text

#: Free input → ISO date, THEN snapped to the start of the week.
#:
#: The second step is what sets this normaliser apart from DatePicker's:
#: without it, typing "2026-08-06" would leave the Thursday in the field
#: while the grid highlights the week of Monday the 3rd — two truths for
#: one value.
#:
#: ``{V}`` is the value expression, ``{WS}`` the starting day. The modulo
#: is doubled for the same reason as in the custom element: JS returns a
#: NEGATIVE remainder for a negative dividend.
NORMALISE_TO_WEEK_TEMPLATE = "{V} = $bz.dates.typedWeek({V}, {WS})"
"""A typed date, as the first day of its week — read by ``$bz.dates``,
the ONE reader of a typed date (``locale.js``). A ``new Date(raw)`` here
would read ``MM/DD/YYYY`` whatever the language: « 02/07/2027 » would give
the week of 7 February in French, and « 13/07/2027 » would empty the
field."""


def normalise_to_week_js(value_expr: str, weekstart: int) -> str:
    """The free-input → start-of-week ISO normaliser."""
    return NORMALISE_TO_WEEK_TEMPLATE.format(
        V=value_expr, WS=int(weekstart) % 7
    )


def _week_to_iso(value: Any) -> str:
    """``WeekPicker``'s date coercion — the shared one, bound to this
    component's name for the error message (same contract as its
    neighbours)."""
    return date_to_iso(value, owner="WeekPicker")


class WeekPicker(ValueCommands, FocusCommands, Component):
    """Render a week field with row-based day selection."""

    THEME: ClassVar[dict[str, Any]] = WEEK_PICKER_THEME
    THEME_KEY: ClassVar[str] = "week_picker"
    #: Retired names, refused with the new one (``attrs.split_kwargs``).
    RENAMED_PROPS: ClassVar[dict[str, str]] = {"weekstart": "write ``week_start=``."}
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value", "disabled")
    #: A picker is BOTH natures at once: an anchored panel (like
    #: `dialog`) and a field carrying a value (like `input`). Its surface
    #: is therefore the union of the two vocabularies already fixed by
    #: its neighbours — nothing invented here.
    IMPERATIVE: ClassVar[tuple[str, ...]] = (
        "open", "close", "toggle", "set", "clear", "focus", "blur",
    )
    # Where ``autofocus=`` / ``.focus()`` land. NOT ``"input"``: the first
    # ``<input>`` is the HIDDEN carrier, where ``.focus()`` does nothing.
    FOCUS_TARGET: ClassVar[tuple[str, ...] | None] = ("input:not([type=hidden])",)
    _command_value = staticmethod(_week_to_iso)
    EVENTS: ClassVar[tuple[str, ...]] = ("change", "focus", "blur")

    name: str | None = reactive_prop(default=None, emit_attr=False)
    value: Any = reactive_prop(
        default=None, writes=True, names_field=True
    )
    min: Any = reactive_prop(default=None, emit_attr=False)
    max: Any = reactive_prop(default=None, emit_attr=False)
    # ``emit_attr=False``: the root is a ``<div>``, where ``disabled``
    # does nothing. Forwarded by hand onto the three real carriers.
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    required: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)

    def __init__(
        self,
        *,
        value: Any = None,
        placeholder: str | None = None,
        min: Any = None,
        max: Any = None,
        week_start: int = 1,
        marks: Any = None,
        weekday_names: list[str] | None = None,
        month_names: list[str] | None = None,
        color: str | None = None,
        size: str | None = None,
        disabled: bool | None = None,
        required: bool | None = None,
        clearable: bool = True,
        close_on_pick: bool = True,
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        reject_attribute_component(placeholder, owner="WeekPicker", prop="placeholder")
        self._placeholder = placeholder
        # Passed on as is: the same day grid as ``ui.calendar``, so a
        # mark has a cell to land in. ``ui.month_picker`` does not have
        # it: its grid is made of MONTHS.
        self._marks = marks
        self._weekstart = int(week_start) % 7
        self._weekday_names = list(weekday_names) if weekday_names else None
        self._month_names = list(month_names) if month_names else None
        self._clearable = clearable
        self._close_on_pick = close_on_pick
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            name=name, value=value, min=min, max=max,
            color=color, size=size, disabled=disabled, required=required,
            on_change=on_change, on_focus=on_focus, on_blur=on_blur,
            **kwargs,
        )
        # AFTER `super().__init__`: the installer reads
        # `_binding_metadata`, which is only populated at that point.
        install_open_close_toggle(self)


    def render(self) -> Element:
        # The calendar in the panel is drawn at the field's step.
        size_key = self._size_key() or "md"
        color = self._reactive_values.get("color") or "primary"

        raw = self._reactive_values.get("value")
        initial = _week_to_iso(raw) if raw else ""
        val = value_expr(self)

        cal_kwargs: dict[str, Any] = {
            "mode": "week", "color": color, "size": size_key,
            "week_start": self._weekstart,
            "marks": self._marks,
        }
        if self._weekday_names:
            cal_kwargs["weekday_names"] = list(self._weekday_names)
        if self._month_names:
            cal_kwargs["month_names"] = list(self._month_names)
        for bound in ("min", "max"):
            if self._reactive_values.get(bound):
                cal_kwargs[bound] = self._reactive_values.get(bound)
        picked = [f"{val} = $event.detail.value"]
        if self._close_on_pick:
            picked.append("open = false")
        cal_kwargs["on_change"] = "; ".join(picked)

        # A week's value is a scalar ISO date, so the mirror is EXACTLY
        # DatePicker's — default granularity, including its "only write
        # if it is a complete ISO" guard that avoids erasing the
        # selection mid-typing.
        return render_calendar_field(
            self,
            initial=initial,
            value_expr=val,
            normalise=lambda v: normalise_to_week_js(v, self._weekstart),
            shown=lambda v: f"$bz.dates.shownWeek({v}, {self._weekstart})",
            mirror_granularity=None,
            clearable=self._clearable,
            clear_label=text("week_picker.clear"),
            trigger_icon="calendar-range",
            trigger_label=text("week_picker.open"),
            field_label=text("week_picker.label"),
            calendar_kwargs=cal_kwargs,
            root_css=self.compose_class(
                "root", apply_variant_size_modifiers=False),
            # The step's height lives on the FRAME, which carries the
            # border (cf. the theme's note) — otherwise the control
            # renders 2 px too many.
            frame_css=self.compose_class("input_frame"),
            panel_css=self.compose_class("panel"),
            field_css=self.compose_class("input_field"),
            clear_css=self.compose_class("clear_button"),
            trigger_css=self.compose_class("trigger_button"),
            icon_css=self.compose_class("button_icon"),
        )


__all__ = ["WeekPicker", "normalise_to_week_js"]
