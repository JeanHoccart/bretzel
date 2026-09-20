"""``TimePicker`` — time field with a two-column panel.

Usage ::

    ui.time_picker(value=state.start)                 # :00 :15 :30 :45
    ui.time_picker(value=state.start, step=30)        # half hours
    ui.time_picker(value=state.start, min="09:00", max="18:00")

**The value is an ``"HH:MM"`` string** — the same shape as the date
pickers' ISO: sortable, comparable, serialisable as is in a form data,
and readable in the editable field. Python also accepts a
``datetime.time``, converted at render.

Identical silhouette to :class:`DatePicker` (editable field + icon button
in the same focus ring, anchored popover), but the panel is not a grid:
**two snapping columns**, hours and minutes.

Why home-made columns and not ``<input type="time">``: a native widget
is not themable and changes look between Chrome, Safari and Android. It
is the lesson paid on the Carousel's scrollbar, more visibly so — and
here there is the added fact that a native ``min``/``max`` applies
without any way of SHOWING the allowed slots.

``step`` (default 15) is **business data**, not taste: an appointment
slot. It decides which minutes exist — ``step=15`` → :00 :15 :30 :45,
``step=1`` → all sixty. The default avoids the 60-row column nobody wants
to scroll.

``min`` / ``max`` bound the OFFERED cells (an out-of-range hour is
rendered ``disabled``). They are **not** bindable, unlike the date
family: the rule (`client-reactive-surface.md`) only admits them there
for the client-side cross constraint of a range (``end.min = start``),
which does not exist here. Cf. `kwarg-routing.md`.

Clicking a MINUTE closes the panel, clicking an hour does not: the
reading order is hour then minute, so closing on the hour would cut the
user's hand off mid-gesture.

Form integration : ``names_field=True`` on ``value`` derives the HTML
``name`` from the bound field; an ``<input type="hidden">`` carries the
time in the form data. Idiom shared with DatePicker / Calendar.
"""

from __future__ import annotations

import datetime as _dt
import json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop, reject_component
from bretzel.components.base._wiring import (
    anchored_dismiss_init,
    imperative_listeners,
    install_open_close_toggle,
    install_value_commands,
    server_sync_marker,
)
from bretzel.components.inputs._picker_field import (
    anchored_panel,
    clear_button,
    detach_wrapper_carriers,
    hidden_carrier,
    relocate_field_events,
    trigger_button,
    value_expr,
)
from bretzel.components.inputs.time_picker.theme import TIME_PICKER_THEME
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as TextNode
from bretzel.render import text

#: The two parts, in the order you read them. The indices are those of
#: the tuple returned by ``_parts()`` in ``$bz.time.scope`` — a single
#: place names them on each side.
HOUR, MINUTE = 0, 1


def time_to_hhmm(value: Any, *, owner: str = "TimePicker") -> str:
    """Coerce a time value to ``"HH:MM"``.

    ``None`` → ``""`` (empty field); a ``datetime.time`` → its ``HH:MM``
    form; a string passes (already normalised, or the caller's SSR seed).
    Everything else is a usage error, raised with ``owner`` in the
    message so the author sees WHO refused.

    Same contract as ``inputs/_wiring.date_to_iso`` for the date family —
    deliberately, the two families read alike.
    """
    from bretzel.components.base.attrs import ComponentDefinitionError

    if value is None:
        return ""
    if isinstance(value, _dt.time):
        return f"{value.hour:02d}:{value.minute:02d}"
    if isinstance(value, str):
        return value
    raise ComponentDefinitionError(
        f"{owner} value must be time / None / str, "
        f"got {type(value).__name__}: {value!r}"
    )


#: Blur normalisation: free input becomes ``HH:MM``, or empties. Templated
#: on ``{V}`` (the value expression) so that bound mode
#: (``$bz.state.X.y``) and literal mode (``value``) share the SAME parser
#: — exactly like ``NORMALISE_TO_ISO_TEMPLATE`` at DatePicker.
NORMALISE_TO_HHMM_TEMPLATE = (
    "(() => {{ const raw = String({V} || '').trim(); "
    "if (!raw) {{ {V} = ''; return; }} "
    # ``9h30`` / ``9:30`` / ``9.30`` / ``930`` / ``9`` — a single
    # pattern covers the five ways people type a time.
    "const m = raw.match(/^(\\d{{1,2}})[^\\d]?(\\d{{2}})?$/); "
    "if (!m) {{ {V} = ''; return; }} "
    "const h = Number(m[1]), mi = Number(m[2] || 0); "
    "if (h > 23 || mi > 59) {{ {V} = ''; return; }} "
    "const pad = n => String(n).padStart(2, '0'); "
    "{V} = pad(h) + ':' + pad(mi); }})()"
)


def normalise_to_hhmm_js(value_expr: str) -> str:
    """The free-input → ``HH:MM`` normaliser for ``value_expr``."""
    return NORMALISE_TO_HHMM_TEMPLATE.format(V=value_expr)


def _in_bounds(candidate: str, low: str, high: str) -> bool:
    """Does ``candidate`` fit in ``[low, high]``?

    A STRING comparison, and it is correct: zero-padded ``"HH:MM"`` sorts
    lexicographically as it sorts chronologically. It is the format's
    reason to be, the same one that makes ISO the choice for dates.
    """
    if low and candidate < low:
        return False
    return not (high and candidate > high)


class TimePicker(Component):
    """Render a time field with hour and minute panels."""

    THEME: ClassVar[dict[str, Any]] = TIME_PICKER_THEME
    THEME_KEY: ClassVar[str] = "time_picker"
    IS_CONTAINER: ClassVar[bool] = False
    # ``min`` / ``max`` stay static: the rule admits them one-way only
    # for the cross constraint of a date range, which does not exist here
    # (cf. client-reactive-surface.md § The rule).
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value", "disabled")
    #: A picker is BOTH natures at once: an anchored panel (like
    #: `dialog`) and a field carrying a value (like `input`). Its surface
    #: is therefore the union of the two vocabularies already fixed by
    #: its neighbours — nothing invented here.
    IMPERATIVE: ClassVar[tuple[str, ...]] = (
        "open", "close", "toggle", "set", "clear", "focus", "blur",
    )
    EVENTS: ClassVar[tuple[str, ...]] = ("change", "focus", "blur")

    name: str | None = reactive_prop(default=None, emit_attr=False)
    value: Any = reactive_prop(
        default=None, writes=True, names_field=True
    )
    min: Any = reactive_prop(default=None, emit_attr=False)
    max: Any = reactive_prop(default=None, emit_attr=False)
    # ``emit_attr=False``: the root is a wrapper ``<div>``, where
    # ``disabled`` does NOTHING. The binding is forwarded by hand onto
    # the three real carriers (field, ×, trigger) — same reason and same
    # gate as DatePicker (``test_binding_lands_on_carrier``).
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    required: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)

    def __init__(
        self,
        value: Any = None,
        *,
        placeholder: str = "HH:MM",
        step: int = 15,
        min: Any = None,
        max: Any = None,
        color: str | None = None,
        size: str | None = None,
        disabled: bool | None = None,
        required: bool | None = None,
        clearable: bool = True,
        close_on_pick: bool = True,
        hour_label: str = "H",
        minute_label: str = "M",
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        if not 1 <= int(step) <= 60:
            from bretzel.components.base.attrs import ComponentUsageError

            raise ComponentUsageError(
                f"TimePicker(step={step!r}) — a minute step must fit in "
                f"1..60. Without this guard, step=0 loops forever and "
                f"step=90 renders an empty column, both in silence."
            )
        self._placeholder = placeholder
        self._step = int(step)
        self._clearable = clearable
        self._close_on_pick = close_on_pick
        for _prop, _value in (("hour_label", hour_label),
                              ("minute_label", minute_label)):
            reject_component(
                _value,
                owner="TimePicker",
                prop=_prop,
                because=(
                    "the column header ALSO serves as an accessible name — "
                    "it goes into the column's ``aria-label`` AND into that of "
                    "each of its 24 (or 60) cells (``f\"{label} {v}\"``), "
                    "and an HTML attribute can only carry a string."
                ),
                instead=(
                    "Expected: a one- or two-character abbreviation, "
                    "``hour_label=\"H\"`` / ``minute_label=\"Min\"``."
                ),
            )
        self._hour_label = hour_label
        self._minute_label = minute_label
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            name=name,
            value=value,
            min=min,
            max=max,
            color=color,
            size=size,
            disabled=disabled,
            required=required,
            on_change=on_change,
            on_focus=on_focus,
            on_blur=on_blur,
            **kwargs,
        )
        # AFTER `super().__init__`: both installers read
        # `_binding_metadata`, which is only populated at that point.
        install_open_close_toggle(self)
        # ⚠️ NOT `"input"`: a picker's first `<input>` is the HIDDEN
        # carrier (`hidden_carrier`), which does not take focus.
        # Measured — `.focus()` did nothing on all six.
        install_value_commands(
            self, focus_selector="input:not([type=hidden])"
        )


    def _value_target(self) -> str:
        """The same value, as a METHOD BODY must address it.

        A method body is NOT wrapped in ``with($scope)``: the bare
        identifier ``value`` raises ``value is not defined`` there, and
        the whole panel becomes inert — the clicks write nothing,
        silently on the server side. It takes ``this.value``.

        The store path, for its part, is global: it is written the same
        on both sides. That is what makes the bug INVISIBLE in binding
        mode and present only in literal mode — so absent from half the
        tests if one is not careful.

        (The trap has been documented since Pagination: "in a method
        body, a bare identifier does not see the scope". I brought it
        back by copying DatePicker's expression, which only uses it in
        directives.)
        """
        binding = self._binding_metadata.get("value")
        if binding is not None:
            return self.path_of(binding)
        # The key comes from the DECLARATION, never from a literal. It
        # was hard-coded ``"this.val"`` here until 2026-09-07, and it is
        # the only site the normalisation of scope keys missed: the whole
        # panel went inert in literal mode, with no JS error and no red
        # test — only ``probe_time_picker_cells`` said so. Exactly the
        # failure mode this helper documents above, applied to itself.
        return f"this.{self._scope_keys('value')[0]}"

    def render(self) -> Element:
        theme = self._resolved_theme()
        sizes = theme.get("sizes", {})
        size_key = self._reactive_values.get("size") or "md"
        size_cfg = sizes.get(size_key, sizes.get("md", {}))
        disabled = bool(self._reactive_values.get("disabled"))
        required = bool(self._reactive_values.get("required"))

        initial = time_to_hhmm(self._reactive_values.get("value"))
        low = time_to_hhmm(self._reactive_values.get("min"))
        high = time_to_hhmm(self._reactive_values.get("max"))
        val = value_expr(self)

        # ── Root: attrs, relocations, scope ───────────────────────────
        # The two calls below are the mechanics shared by the three
        # pickers (``inputs/_picker_field.py``): empty the root of what
        # it cannot carry, and route each handler to the carrier able to
        # fire it.
        root_attrs = self.emit_attrs()
        hidden_extra: dict[str, Any] = {}
        relocated: dict[str, Any] = {}
        relocate_field_events(
            root_attrs, value_carrier=hidden_extra, focusable=relocated
        )
        name = detach_wrapper_carriers(self, root_attrs)
        root_attrs["class"] = self.slot_class("root")
        root_attrs["bz-data"] = self._scope_literal(
            initial, self._value_target()
        )
        # ── The receivers of the imperative API ──────────────────
        #
        # In BOUND mode, `.open()` / `.set()` write straight into the
        # store and these listeners never fire; we set them anyway so the
        # contract is the same in both modes — the choice already made by
        # Sidebar, Dialog and Select.
        for _ev, _handler in imperative_listeners("open").items():
            root_attrs.setdefault(_ev, _handler)
        # ⚠️ `value_expr()` and NOT `_value_target()`. A `bz-on:` is a
        # DIRECTIVE, so evaluated in a `with($scope)` where the bare
        # identifier `value` resolves; `this.value` designates nothing
        # there. It is the exact mirror of the trap `_value_target`
        # documents, and it only shows in LITERAL mode: in bound mode
        # both render the same store path. Measured — `.set()` set
        # nothing on the time_picker, and on it alone.
        root_attrs.setdefault(
            "bz-on:bz-set", f"{value_expr(self)} = $event.detail.value"
        )
        # Escape + click-outside: the shared helper registers both on
        # ``$el`` (``bz-on`` has neither ``.outside`` nor ``.escape`` —
        # it has NO modifier at all, cf. traps.md).
        root_attrs["bz-init"] = anchored_dismiss_init("open")

        hidden_input = hidden_carrier(
            value_expr=val,
            initial=initial,
            name=name,
            required=required,
            extra=hidden_extra,
        )

        # ── Editable field ───────────────────────────────────────────
        field_attrs: dict[str, Any] = {
            "type": "text",
            "placeholder": self._placeholder,
            "class": self.slot_class("input_field", size_cfg.get("input_field", "")),
            "value": initial,
            "bz-model": val,
            "bz-on:blur": normalise_to_hhmm_js(val),
            "autocomplete": "off",
            "inputmode": "numeric",
            "spellcheck": "false",
            "aria-label": self._placeholder,
        }
        if disabled:
            field_attrs["disabled"] = True
        if required:
            # A visual marker only — the real ``required`` of the
            # validation lives on the hidden input.
            field_attrs["aria-required"] = "true"
        if "bz-on:blur" in relocated:
            # Chain rather than overwrite: the internal normalisation
            # and the user's ``on_blur=`` must both run.
            relocated["bz-on:blur"] = (
                f"{field_attrs['bz-on:blur']}; {relocated['bz-on:blur']}"
            )
        field_attrs.update(relocated)
        self.forward_binding("disabled", field_attrs)

        frame_children: list[Node] = [
            Element(tag="input", attrs=field_attrs, children=())
        ]

        if self._clearable:
            cross = clear_button(
                css=self.slot_class("clear_button", size_cfg.get("clear_button", "")),
                icon_css=self.slot_class("button_icon", size_cfg.get("button_icon", "")),
                aria_label=text("time_picker.clear"),
                clear_js=f"{val} = ''",
                show_when=val,
                has_value_at_ssr=bool(initial),
                disabled=disabled,
            )
            self.forward_binding("disabled", cross.attrs)
            frame_children.append(cross)

        opener = trigger_button(
            icon="clock",
            css=self.slot_class("trigger_button", size_cfg.get("trigger_button", "")),
            icon_css=self.slot_class("button_icon", size_cfg.get("button_icon", "")),
            aria_label=text("time_picker.open"),
            disabled=disabled,
        )
        self.forward_binding("disabled", opener.attrs)
        frame_children.append(opener)

        # ``bz-ref="bztrigger"``: the anchor the panel positions itself
        # against (same idiom as Select / Combobox / DatePicker).
        frame = Element(
            tag="div",
            # The step's height is on the FRAME, which carries the
            # border (cf. the theme's note) — otherwise 2 px too many.
            attrs={
                "class": self.slot_class(
                    "input_frame", size_cfg.get("input_frame", "")),
                "bz-ref": "bztrigger",
            },
            children=tuple(frame_children),
        )

        # A cell's class travels ONCE, on the container. Before
        # 2026-09-01 it was copied onto each of the 28 or 84 cells: 452
        # characters × 84 = 38 kB of a single identical string, in a page
        # that weighed 54.
        cell_base = " ".join(
            p
            for p in (
                self.compose_class("cell", apply_variant_size_modifiers=False),
                size_cfg.get("cell", ""),
            )
            if p
        )

        # ── Panel: two snapping columns ──────────────────────────────
        panel = anchored_panel(
            css=self.slot_class("panel"),
            # On opening, bring the current value under your eyes: over
            # 24 hours, opening at 14:00 while showing 00-06 would force
            # you to search. It is an ACTION triggered by the ``open``
            # signal, not a computed value — so immune to the "a
            # measurement is not a signal" trap that bit the Carousel.
            extra_effect=(
                "if (open) $el.querySelectorAll('[data-selected=true]')"
                ".forEach(c => c.scrollIntoView({block: 'center'}))"
            ),
            children=(
                Element(
                    tag="div",
                    attrs={
                        "class": self.slot_class("columns"),
                        # ── The cells are born HERE, on the client ──
                        # ``bz-effect`` and NOT ``bz-init``: the latter
                        # is one-shot per NODE and survives a rebind, yet
                        # idiomorph morphs IN PLACE — so a ``bz-init``
                        # would never run again after a swap. Same choice
                        # and same reason as ``<bz-calendar>``, which
                        # paid the lesson.
                        #
                        # The effect does TWO things, and the second is
                        # the one that justifies its being an effect:
                        # paint the cells once, then re-mark the
                        # selection at EVERY change of the value. That
                        # is what replaces the former 84
                        # ``bz-attr:data-selected`` — one effect per
                        # instance instead of one per cell.
                        # ``_parts()`` is READ here, and that is what
                        # subscribes the effect: without that read it
                        # would never run again and the selection would
                        # stay the first paint's. The ``pick`` travels
                        # as an arrow — a method passed by its name
                        # would lose its ``this``, and the scope is NOT
                        # ``this`` in a directive expression (measured:
                        # "scope._parts is not a function", the runtime
                        # no longer started at all).
                        "bz-effect": (
                            "$bz.time.fill($el, _parts(), (p, v) => pick(p, v))"
                        ),
                        "data-bz-cell-class": cell_base,
                        **({"data-bz-cells-disabled": "true"}
                           if disabled else {}),
                    },
                    children=(
                        self._column(
                            HOUR, self._hour_label,
                            [f"{h:02d}" for h in range(24)],
                            low, high, size_cfg, disabled, part_is_hour=True,
                        ),
                        self._column(
                            MINUTE, self._minute_label,
                            [f"{m:02d}" for m in range(0, 60, self._step)],
                            low, high, size_cfg, disabled, part_is_hour=False,
                        ),
                    ),
                ),
            ),
        )

        return Element(
            tag=self._tag,
            attrs=root_attrs,
            children=(
                hidden_input,
                frame,
                panel,
            ),
        )

    # ── Piece factory ───────────────────────────────────────────────

    def _scope_literal(self, initial: str, target: str) -> str:
        """The instance's ``bz-data``: **data, not code**.

        The methods (``_parts`` / ``_is`` / ``pick``) live once in
        ``$bz.time.scope`` — a panel has 28 buttons, writing the pick out
        in full on each would serialise the same algorithm 28 times per
        instance.

        ``_read`` / ``_write`` cover both value modes with the same
        methods. It is not an elegance: a bound expression MUST live in a
        method body, the only place re-read on every call hence tracked.
        As a field, it would be frozen at mount (cf. traps.md § "a
        bz-data field is not reactive").

        ⚠️ ``target`` comes from :meth:`_value_target`, NOT from
        :func:`~bretzel.components.inputs._picker_field.value_expr`: here
        we are in a method body, where the bare identifier does not
        resolve. Paid once — the whole panel was inert in literal mode,
        and only the browser said so ("val is not defined").
        """
        local = ""
        if self._binding_metadata.get("value") is None:
            (key,) = self._scope_keys("value")
            sync = server_sync_marker(
                key, enabled=self._value_server_backed("value")
            )
            local = f"{key}: {json.dumps(initial)},{sync} "
        return (
            "{...$bz.time.scope,open: false,"
            + local
            + f"_closeOnPick: {'true' if self._close_on_pick else 'false'},"
            + f"_read() {{ return {target}; }},"
            + f"_write(v) {{ {target} = v; }}"
            + "}"
        )

    def _icon(self, name: str, size_cfg: dict[str, Any]) -> Element:
        return Element(
            tag="iconify-icon",
            attrs={
                "icon": f"lucide:{name}",
                "class": " ".join(
                    p
                    for p in (
                        self.compose_class(
                            "button_icon", apply_variant_size_modifiers=False
                        ),
                        size_cfg.get("button_icon", ""),
                    )
                    if p
                ),
            },
            children=(),
        )

    def _column(
        self,
        part: int,
        label: str,
        values: list[str],
        low: str,
        high: str,
        size_cfg: dict[str, Any],
        disabled: bool,
        *,
        part_is_hour: bool,
    ) -> Element:
        """A snapping column — its cells, and which are out of range.

        Bounding an HOUR looks at the end of the hour (``09:59``) for the
        floor and at its start (``09:00``) for the ceiling: an hour is
        excluded only if NONE of its minutes fits in ``[min, max]``.
        Without that nuance, ``min="09:30"`` would grey out the whole
        hour 09 and 09:45 would become unreachable.
        """
        off = [
            v
            for v in values
            # A minute is only bounded if there is a single possible
            # hour; otherwise ``:45`` would be greyed out because it
            # falls outside at the last hour, while it is valid at all
            # the others. So we let it through, keyboard entry being the
            # precise door in anyway.
            if part_is_hour
            and not (
                _in_bounds(f"{v}:59", low, "")
                and _in_bounds(f"{v}:00", "", high)
            )
        ]

        header = Element(
            tag="div",
            attrs={
                "class": " ".join(
                    p
                    for p in (
                        self.compose_class(
                            "column_label", apply_variant_size_modifiers=False
                        ),
                        size_cfg.get("column_label", ""),
                    )
                    if p
                )
            },
            children=(TextNode(label),),
        )
        return Element(
            tag="div",
            attrs={
                "class": " ".join(
                    p
                    for p in (
                        self.compose_class(
                            "column", apply_variant_size_modifiers=False
                        ),
                        size_cfg.get("column", ""),
                    )
                    if p
                ),
                "role": "listbox",
                "aria-label": label,
                # ── The column DESCRIBES itself, it does not write
                # itself ────────────────────────────────────────────
                # Its cells are painted by ``$bz.time.fill``. What
                # travels here is the data it is made of: the values,
                # those that are out of range, and the word that
                # prefixes each one's ``aria-label``.
                "data-bz-part": str(part),
                "data-bz-values": ",".join(values),
                "data-bz-off": ",".join(off),
                "data-bz-cell-label": label,
            },
            children=(header,),
        )


__all__ = ["TimePicker", "normalise_to_hhmm_js", "time_to_hhmm"]
