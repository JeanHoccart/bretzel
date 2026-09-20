"""``ColorPicker`` — colour field with a swatch panel.

Usage ::

    ui.color_picker(value=state.brand)

**The value is a hexadecimal string** — ``"#2f5fd0"``. It is what a
``Theme(semantic=…)`` expects, what a form data carries as is, and what
reads back in the field. An empty string means "no colour", as
everywhere else in the input family.

Why not ``<input type="color">``
---------------------------------

``ui.input`` REFUSES it, and this component is what its message
recommends. A native picker is not themable and changes look between
Chrome, Safari and Android — it is the same lesson as the Carousel's
scrollbar and ``<input type="time">``. Here there is an added reason
specific to Bretzel: the native one cannot offer **the theme's
palette**, which is precisely what one wants to choose nine times out of
ten.

What the panel offers
----------------------

The active theme's NAMED colours, resolved to hexadecimal (the 31 of the
palette shipped by default). Not the eleven semantic slots: those are
the structure being edited, offering them as a value would be circular.

⚠️ **There is no ``swatches=``**, and it is deliberate. An app that
wants its brand declares it once — ``Theme(palette={"brand": "#..."})``
— and ALL its pickers offer it. A per-instance parameter would be a
second way of doing the same thing, and it would make two pickers of the
same app diverge with nothing saying so. It would also make this
component "owner of a collection" without having markup to delegate,
which is none of ``COLLECTION_OWNER``'s three cases.

The field stays free: any hexadecimal can be typed by hand, and that is
what stops a grid of swatches becoming a prison.

Form integration : ``names_field=True`` on ``value`` derives the HTML
``name``; an ``<input type="hidden">`` carries the colour in the form
data. Idiom shared with DatePicker / TimePicker / Calendar.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import (
    anchored_dismiss_init,
    bool_attr,
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
from bretzel.components.inputs.color_picker.theme import COLOR_PICKER_THEME
from bretzel.core.escape import RawAttrValue
from bretzel.core.tree import Element, Node
from bretzel.render import text

#: The fallback when no render context is active (a bench, a unit
#: test): we cannot read the app's palette, and an empty panel would be
#: worse than a short list.
_FALLBACK_SWATCHES: tuple[str, ...] = (
    "#8b8d98", "#e54d2e", "#e5484d", "#e93d82", "#d6409f",
    "#8e4ec6", "#6e56cf", "#3e63dd", "#0090ff", "#00a2c7",
    "#12a594", "#30a46c", "#46a758", "#ffe629", "#ffc53d",
    "#f76b15", "#ad7f58", "#8d8d8d",
)


def hex_or_empty(value: Any, *, owner: str = "ColorPicker") -> str:
    """Coerce a colour value to ``"#rrggbb"`` or ``""``.

    ``None`` → ``""`` (empty field); a string passes. Everything else is
    a usage error, raised with ``owner`` in the message so the author
    sees WHO refused — **same contract as ``time_to_hhmm`` and
    ``date_to_iso``**, deliberately.

    ⚠️ A non-hexadecimal string is NOT refused, and it is a choice. The
    field is editable: the user necessarily types intermediate states
    (``"#2f"``), and a caller's SSR seed can be anything. Refusing at
    construction would move the error to the wrong place — it is the
    render that shows an empty swatch, and that reads. The three date
    pickers reason alike.
    """
    from bretzel.components.base.attrs import ComponentDefinitionError

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    raise ComponentDefinitionError(
        f"{owner}(value={value!r}): type {type(value).__name__} not "
        "supported. Expected a hexadecimal string or None."
    )


class ColorPicker(Component):
    """Render a color field with a swatch selection panel."""

    THEME: ClassVar[dict[str, Any]] = COLOR_PICKER_THEME
    THEME_KEY: ClassVar[str] = "color_picker"
    IS_CONTAINER: ClassVar[bool] = False
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
    # ``emit_attr=False``: the root is a wrapper ``<div>``, where
    # ``disabled`` does NOTHING. The binding is forwarded by hand onto
    # the three real carriers (field, ×, trigger) — same reason and same
    # gate as TimePicker (``test_binding_lands_on_carrier``).
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    required: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)

    def __init__(
        self,
        value: Any = None,
        *,
        name: str | None = None,
        placeholder: str | None = None,
        clearable: bool = False,
        disabled: bool | None = None,
        required: bool | None = None,
        color: str | None = None,
        size: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        self._placeholder = placeholder or "#rrggbb"
        self._clearable = clearable
        super().__init__(
            value=value, name=name, disabled=disabled, required=required,
            color=color, size=size,
            on_change=on_change, on_focus=on_focus, on_blur=on_blur,
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

    # ── The two shapes of the value expression ───────────────────────

    def _palette_swatches(self) -> tuple[str, ...]:
        """The offered colours — the THEME's, and nothing else.

        Outside a render context we cannot read the palette: we return
        the fallback rather than an empty panel. A bench that builds the
        component bare therefore still sees swatches.
        """
        from bretzel.render.context import maybe_current_context
        from bretzel.theme.tokens import SEMANTIC_COLOR_NAMES

        ctx = maybe_current_context()
        theme = getattr(getattr(ctx, "app", None), "theme", None)
        getter = getattr(theme, "get_palette", None)
        if not callable(getter):
            return _FALLBACK_SWATCHES
        palette = getter()
        semantic = set(SEMANTIC_COLOR_NAMES)
        return tuple(
            palette.resolve(name, "light").bg_hex
            for name in palette.envelope_dict()
            if name not in semantic
        )

    def render(self) -> Element:
        theme = self._resolved_theme()
        sizes = theme.get("sizes", {})
        size_key = self._reactive_values.get("size") or "md"

        size_cfg = sizes.get(size_key, sizes.get("md", {}))

        def sized(slot: str) -> str:
            return self.slot_class(slot, size_cfg.get(slot, ""))

        disabled = bool(self._reactive_values.get("disabled"))
        required = bool(self._reactive_values.get("required"))
        initial = hex_or_empty(self._reactive_values.get("value"))
        val = value_expr(self)

        # ── Racine : attrs, relocations, scope ───────────────────────
        root_attrs = self.emit_attrs()
        hidden_extra: dict[str, Any] = {}
        relocated: dict[str, Any] = {}
        relocate_field_events(
            root_attrs, value_carrier=hidden_extra, focusable=relocated
        )
        name = detach_wrapper_carriers(self, root_attrs)
        root_attrs["class"] = self.compose_class("root")
        # ``_serverSync``: without it, a server mutation followed by a
        # refresh would change NOTHING on screen — idiomorph preserves
        # the client signal, so the old value wins. The marker tells the
        # runtime to re-adopt the rendered value.
        # ⚠️ ``server_sync_marker`` returns a fragment that starts with a
        # SPACE and ends with a COMMA: it is made to slip BETWEEN two
        # fields, so the comma before it is the caller's responsibility.
        # Forgetting it produces ``val: "#2f5fd0" _serverSync: [...]`` —
        # a syntax error that kills the runtime's SCAN for the whole page
        # (28 scopes, 0 initialised) with not a word in the console.
        # Measured right here.
        local = ""
        if self._binding_metadata.get("value") is None:
            (key,) = self._scope_keys("value")
            sync = server_sync_marker(
                key, enabled=self._value_server_backed("value")
            )
            local = f",{key}: {json.dumps(initial)},{sync}"
        root_attrs["bz-data"] = "{open: false" + local + "}"
        # ── The receivers of the imperative API ──────────────────
        #
        # In BOUND mode, `.open()` / `.set()` write straight into the
        # store and these listeners never fire; we set them anyway so the
        # contract is the same in both modes — the choice already made by
        # Sidebar, Dialog and Select.
        for _ev, _handler in imperative_listeners("open").items():
            root_attrs.setdefault(_ev, _handler)
        root_attrs.setdefault(
            "bz-on:bz-set", f"{val} = $event.detail.value"
        )
        root_attrs["bz-init"] = anchored_dismiss_init("open")

        hidden_input = hidden_carrier(
            value_expr=val, initial=initial, name=name,
            required=required, extra=hidden_extra,
        )

        # ── The head swatch ──────────────────────────────────────────
        # The theme's checkerboard shows through when the value is empty:
        # a white swatch and a swatch WITH NO colour would look alike.
        swatch = Element(
            tag="span",
            attrs={
                "class": sized("swatch"),
                "aria-hidden": "true",
                # ``background-color`` and not ``background``: the
                # class sets the resting grey, and a ``background``
                # shorthand would erase it even when empty. Here, absent
                # value = no inline style = the grey shows.
                "bz-attr:style": RawAttrValue(
                    f"{val} ? 'background-color:' + {val} : ''"
                ),
                **({"style": f"background-color:{initial}"} if initial else {}),
            },
            children=(),
        )

        field_attrs: dict[str, Any] = {
            "type": "text",
            "placeholder": self._placeholder,
            "class": sized("input_field"),
            "value": initial,
            "bz-model": val,
            "autocomplete": "off",
            "spellcheck": "false",
            "aria-label": self._placeholder,
        }
        if disabled:
            field_attrs["disabled"] = True
        if required:
            field_attrs["aria-required"] = "true"
        field_attrs.update(relocated)
        self.forward_binding("disabled", field_attrs)

        frame_children: list[Node] = [
            swatch,
            Element(tag="input", attrs=field_attrs, children=()),
        ]

        if self._clearable:
            cross = clear_button(
                css=sized("clear_button"),
                icon_css=self.slot_class(
                    "button_icon", size_cfg.get("button_icon", "")
                ),
                aria_label=text("color_picker.clear"),
                clear_js=f"{val} = ''",
                show_when=val,
                has_value_at_ssr=bool(initial),
                disabled=disabled,
            )
            self.forward_binding("disabled", cross.attrs)
            frame_children.append(cross)

        opener = trigger_button(
            icon="palette",
            css=sized("trigger_button"),
            icon_css=self.slot_class(
                "button_icon", size_cfg.get("button_icon", "")
            ),
            aria_label=text("color_picker.open"),
            disabled=disabled,
        )
        self.forward_binding("disabled", opener.attrs)
        frame_children.append(opener)

        frame = Element(
            tag="div",
            attrs={"class": sized("input_frame"), "bz-ref": "bztrigger"},
            children=tuple(frame_children),
        )

        panel = anchored_panel(
            css=self.slot_class("panel"),
            children=(
                Element(
                    tag="div",
                    attrs={"class": self.slot_class("panel_label")},
                    children=(Element(
                        tag="span", attrs={}, children=()),),
                ),
                Element(
                    tag="div",
                    attrs={"class": self.slot_class("grid")},
                    children=tuple(
                        self._cell(hexa, val, initial, disabled)
                        for hexa in self._palette_swatches()
                    ),
                ),
            ),
        )

        return Element(
            tag=self._tag,
            attrs=root_attrs,
            children=(hidden_input, frame, panel),
        )

    def _cell(
        self, hexa: str, val: str, initial: str, disabled: bool
    ) -> Element:
        """One swatch of the panel.

        The click writes the value AND closes: unlike the TimePicker,
        where the hour precedes the minute, there is nothing to choose
        after a colour.
        """
        attrs: dict[str, Any] = {
            "type": "button",
            "class": self.slot_class("swatch_cell"),
            "style": f"background:{hexa}",
            "title": hexa,
            "aria-label": hexa,
            # ``bool_attr`` and not a hand-written ternary: ``bz-attr``
            # treats a boolean the way HTML wants (empty attribute, or
            # removed), yet ``data-[selected=true]:`` matches the
            # LITERAL. Forgetting the ternary breaks nothing visible —
            # the style does not apply, in silence.
            "data-selected": (
                "true" if initial.lower() == hexa.lower() else "false"
            ),
            "bz-attr:data-selected": RawAttrValue(
                bool_attr(f"({val} || '').toLowerCase() === '{hexa.lower()}'")
            ),
            # ⚠️ ``value`` and ``open`` BARE, not ``this.value``: a
            # ``bz-on:`` is a DIRECTIVE, evaluated in a ``with($scope)``
            # — the bare identifier resolves there, ``this`` does not.
            # It is ``this`` that is needed in a METHOD BODY of the
            # ``bz-data``, the exact opposite. Written the wrong way
            # round here, the raise killed the runtime's scan for the
            # WHOLE PAGE: no scope initialised any more, and no visible
            # error.
            "bz-on:click": RawAttrValue(
                f"{val} = '{hexa}'; open = false"
            ),
        }
        if disabled:
            attrs["disabled"] = True
        self.forward_binding("disabled", attrs)
        return Element(tag="button", attrs=attrs, children=())
