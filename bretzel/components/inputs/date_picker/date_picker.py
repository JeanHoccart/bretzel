"""``DatePicker`` — single-date input with an inline calendar popover.

UX model — native ``<input type="date">`` shape, themable popover :
the visible field is **editable**. The user can either type a date
(any format ``new Date()`` parses, normalised to ISO on blur) OR
click the calendar icon button — which lives **inside the same focus
ring** as the input — to open a ``<bz-calendar>`` popover and pick.

The single source of truth for the field's value is a **value
expression** (``_value_expr()``) :

- **Bound** (``value=client_state.picked``) : the value expression IS
  the binding path ``$bz.state.X.y``. The scope is just
  ``bz-data="{open: false}"``. The field, the hidden form-data input and
  the inner ``<bz-calendar>`` all address the store directly — zero
  ``$watch`` sync.
- **Literal** (``value=date(...)`` / no value) : the value expression
  is a local scope var ``value``. The scope is
  ``bz-data="{open: false, value: '<initial>'}"``, and the field, the
  hidden input and the calendar change handler all address ``value``.

Wired (both modes, ``V`` = ``_value_expr()``) :

- the editable ``<input>`` shows ``V`` and writes it once normalised, at
  ``change`` and ``blur`` (``typed_field_attrs``) — never at each key ;
- the hidden form-data input uses ``bz-attr:value="V"`` ;
- the clear ``×`` button does ``V = ''`` and is shown only when ``V``
  is non-empty (``bz-show="V"`` + FOUC pre-stamp) ;
- the calendar trigger ``<button>`` toggles ``open`` ;
- the inner ``<bz-calendar>`` receives ``V`` through the wrapper's
  ``bz-effect`` (see the next point) — **not** through
  ``bz-attr:value``, which is explicitly removed from the calendar
  (``release_root_attr``). It writes back on its native ``change``
  (``bz-on:change="V = $event.detail.value; open = false
  [if close_on_pick]"``) ;
- a ``bz-effect`` on the wrapper mirrors ``V`` onto the calendar's
  observed ``value`` ATTRIBUTE via ``setAttribute`` — ``bz-attr:value``
  on a custom element writes the JS property, not the attribute, so it
  would skip ``attributeChangedCallback``.

Form integration : ``AUTONAME_FROM = "value"`` derives the HTML
``name`` from the bound field, same idiom as Calendar / Input.
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
from bretzel.components.base.theme_values import theme_context
from bretzel.components.inputs._picker_field import (
    render_calendar_field,
    value_expr,
)
from bretzel.components.inputs._wiring import date_to_iso
from bretzel.components.inputs.date_picker.theme import DATE_PICKER_THEME
from bretzel.core.tree import Element
from bretzel.render import text


def _date_to_iso(value: Any) -> str:
    """``DatePicker``'s date coercion — the shared one, bound to this
    component's name for the error message."""
    return date_to_iso(value, owner="DatePicker")


# Client expression — typed text → ISO ``YYYY-MM-DD`` on change and blur,
# or empty when it names no day. The reader is ``$bz.dates.typed``
# (``locale.js``), the ONE reader of a typed date: a numeric date is read
# in the order of ``<html lang>`` (« 02/07/2027 » is 2 July in French),
# where ``new Date()`` reads ``MM/DD/YYYY`` whatever the language.
NORMALISE_TO_ISO_TEMPLATE = "{V} = $bz.dates.typed({V})"
"""Templated on ``{V}`` (the value expression) so the bound store path,
the local ``value``, and the range picker's ``vstart`` / ``vend`` all
share one reader. Use :func:`normalise_to_iso_js`."""


def shown_date_js(value_expr: str) -> str:
    """What the field shows of ``value_expr``: the day in the page's
    language, « mar. 3 nov. 2026 » (``$bz.dates.shown``)."""
    return f"$bz.dates.shown({value_expr})"


def normalise_to_iso_js(value_expr: str) -> str:
    """The free-form → ISO blur normaliser for ``value_expr``.

    ``value_expr`` is whatever the field is bound to : a local scope
    var (``value`` / ``vstart`` / ``vend``) or a store path
    (``$bz.state.X.y``). The same body assigns the normalised result
    back into that same expression."""
    return NORMALISE_TO_ISO_TEMPLATE.format(V=value_expr)


class DatePicker(ValueCommands, FocusCommands, Component):
    """Single-date input with an inline calendar popover."""

    THEME: ClassVar[dict[str, Any]] = DATE_PICKER_THEME
    THEME_KEY: ClassVar[str] = "date_picker"
    #: Retired names, refused with the new one (``attrs.split_kwargs``).
    RENAMED_PROPS: ClassVar[dict[str, str]] = {"weekstart": "write ``week_start=``."}
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = (
        "value", "min", "max", "disabled",
    )
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
    _command_value = staticmethod(_date_to_iso)
    EVENTS: ClassVar[tuple[str, ...]] = ("change", "focus", "blur")

    name: str | None = reactive_prop(default=None, emit_attr=False)
    value: Any = reactive_prop(default=None, writes=True, names_field=True)
    min: Any = reactive_prop(default=None, emit_attr=False)
    max: Any = reactive_prop(default=None, emit_attr=False)
    # ``emit_attr=False``: the root is a wrapper ``<div>``, where
    # ``disabled`` does NOTHING. The binding is forwarded by hand in
    # ``render()`` onto the three real carriers (field, ×, trigger) —
    # cf. the ``test_binding_lands_on_carrier`` gate.
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
        disabled_dates: list[_dt.date] | None = None,
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
        reject_attribute_component(placeholder, owner="DatePicker", prop="placeholder")
        self._placeholder = placeholder
        # ``None`` = "let the browser name them", from ``<html lang>``.
        # Freezing English here forced every app to pass the 19 strings
        # again at every mount. Cf. ``ui.calendar``.
        self._weekday_names = list(weekday_names) if weekday_names else None
        self._month_names = list(month_names) if month_names else None
        self._disabled_dates = list(disabled_dates or [])
        # Passed on as is: the day grid is the SAME as
        # ``ui.calendar``'s, so a mark has a cell to land in.
        # ``ui.month_picker`` does not have it: its grid is made of
        # MONTHS, not days.
        self._marks = marks
        self._weekstart = week_start
        self._clearable = clearable
        self._close_on_pick = close_on_pick

        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            name=name, value=value,
            min=min, max=max,
            color=color, size=size,
            disabled=disabled, required=required,
            on_change=on_change,
            on_focus=on_focus,
            on_blur=on_blur,
            **kwargs,
        )
        # AFTER `super().__init__`: the installer reads
        # `_binding_metadata`, which is only populated at that point.
        install_open_close_toggle(self)

    def render(self) -> Element:
        _theme, slots, _sizes, size_key, color = theme_context(self)
        raw_value = self._reactive_values.get("value")
        val = value_expr(self)

        cal_kwargs: dict[str, Any] = {
            "mode": "picker",
            "color": color,
            "size": size_key,
            "week_start": self._weekstart,
            "marks": self._marks,
            "weekday_names": list(self._weekday_names)
            if self._weekday_names else None,
            "month_names": list(self._month_names)
            if self._month_names else None,
        }
        for bound in ("min", "max"):
            binding = self._binding_metadata.get(bound)
            if binding is not None:
                cal_kwargs[bound] = binding
            elif self._reactive_values.get(bound):
                cal_kwargs[bound] = self._reactive_values.get(bound)
        if self._disabled_dates:
            cal_kwargs["disabled_dates"] = self._disabled_dates
        picked = [f"{val} = $event.detail.value"]
        if self._close_on_pick:
            picked.append("open = false")
        cal_kwargs["on_change"] = "; ".join(picked)

        return render_calendar_field(
            self,
            initial=_date_to_iso(raw_value) if raw_value else "",
            value_expr=val,
            normalise=normalise_to_iso_js,
            shown=shown_date_js,
            mirror_granularity=None,
            clearable=self._clearable,
            clear_label=text("date_picker.clear"),
            trigger_icon="calendar",
            trigger_label=text("date_picker.open"),
            field_label=text("date_picker.label"),
            calendar_kwargs=cal_kwargs,
            root_css=slots.get("root", ""),
            frame_css=self.compose_class("input_frame"),
            panel_css=slots.get("panel", ""),
            field_css=self.compose_class("input_field"),
            clear_css=self.compose_class("clear_button"),
            trigger_css=self.compose_class("trigger_button"),
            icon_css=self.compose_class("button_icon"),
        )
