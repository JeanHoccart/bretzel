"""``MonthPicker`` — a MONTH field with a year grid in a popover.

Usage ::

    ui.month_picker(value=state.period)              # "2026-08"
    ui.month_picker(value=state.period, min="2026-03", max="2026-12")

**The value is a ``"YYYY-MM"`` string** — the third member of the same
family of formats as the dates' ISO and the times' ``"HH:MM"``, and for
the same reason: zero-padded, it **sorts lexicographically as it sorts
chronologically**, so bounding is a string comparison. Python also
accepts a ``datetime.date``, TRUNCATED to the month — somebody passing
``date(2026, 8, 14)`` visibly wants "August 2026", and refusing would
cost them a ``strftime`` for nothing.

The component is thin by design: the frame, the popover, the hidden
input and the handler routing come from ``_picker_field``; the grid
comes from ``ui.calendar(mode="month")``. What is left here is the
**value codec** and the input normaliser — that is to say everything
proper to it, and nothing else.

``min`` / ``max`` accept a ``"YYYY-MM"`` or a ``date``, and are
truncated to the month: a ``min`` on 15 March does NOT forbid March,
since part of the month is still allowed. They are **not** bindable,
same reasoning as TimePicker — the rule only admits them one-way for the
cross constraint of a date range.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base.arguments import reject_attribute_component
from bretzel.components.base.commands import ValueCommands
from bretzel.components.base.focus import FocusCommands
from bretzel.components.base.overlay_wiring import install_open_close_toggle
from bretzel.components.inputs._picker_field import render_calendar_field, value_expr
from bretzel.components.inputs.month_picker.theme import MONTH_PICKER_THEME
from bretzel.core.tree import Element
from bretzel.render import text


def month_to_ym(value: Any, *, owner: str = "MonthPicker") -> str:
    """Coerce a month value to ``"YYYY-MM"``.

    ``None`` → ``""``; a ``date`` → its month (TRUNCATED, cf. the
    module's docstring); a string passes and is cut to 7 characters,
    which accepts ``"2026-08"`` as well as ``"2026-08-14"``. Everything
    else is a usage error, raised with ``owner`` so the author sees WHO
    refused — same contract as ``date_to_iso`` and ``time_to_hhmm``.
    """
    from bretzel.components.base.attrs import ComponentUsageError

    if value is None:
        return ""
    if isinstance(value, _dt.date):
        return f"{value.year:04d}-{value.month:02d}"
    if isinstance(value, str):
        return value[:7]
    raise ComponentUsageError(
        f"{owner} value must be str / date / None, "
        f"got {type(value).__name__}: {value!r}"
    )


#: Blur normalisation: free input becomes ``YYYY-MM``, or empties —
#: digits (``2026-08``, ``08/2026``) or the month's name in the page's
#: language (« novembre 2026 », what the field shows). The reader is
#: ``$bz.dates.typedMonth`` (``locale.js``), once, not recopied into
#: every field. Templated on ``{V}`` so that bound and literal modes
#: share it.
NORMALISE_TO_YM_TEMPLATE = "{V} = $bz.dates.typedMonth({V})"


def normalise_to_ym_js(value_expr: str) -> str:
    """The free-input → ``YYYY-MM`` normaliser for ``value_expr``."""
    return NORMALISE_TO_YM_TEMPLATE.format(V=value_expr)


class MonthPicker(ValueCommands, FocusCommands, Component):
    """Render a month field with a year-grid popover."""

    THEME: ClassVar[dict[str, Any]] = MONTH_PICKER_THEME
    THEME_KEY: ClassVar[str] = "month_picker"
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
    _command_value = staticmethod(month_to_ym)
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
        reject_attribute_component(placeholder, owner="MonthPicker", prop="placeholder")
        self._placeholder = placeholder
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

        initial = month_to_ym(self._reactive_values.get("value"))
        val = value_expr(self)

        cal_kwargs: dict[str, Any] = {
            "mode": "month", "color": color, "size": size_key,
        }
        if self._month_names:
            cal_kwargs["month_names"] = list(self._month_names)
        for bound in ("min", "max"):
            raw = self._reactive_values.get(bound)
            if raw:
                # The calendar expects a DATE for its bounds and
                # truncates them itself; we give it the 1st of the
                # month.
                cal_kwargs[bound] = f"{month_to_ym(raw)}-01"
        picked = [f"{val} = $event.detail.value"]
        if self._close_on_pick:
            picked.append("open = false")
        cal_kwargs["on_change"] = "; ".join(picked)

        return render_calendar_field(
            self,
            initial=initial,
            value_expr=val,
            normalise=normalise_to_ym_js,
            shown=lambda v: f"$bz.dates.shownMonth({v})",
            mirror_granularity="month",
            clearable=self._clearable,
            clear_label=text("month_picker.clear"),
            trigger_icon="calendar",
            trigger_label=text("month_picker.open"),
            field_label=text("month_picker.label"),
            month_hint=True,
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


__all__ = ["MonthPicker", "month_to_ym", "normalise_to_ym_js"]
