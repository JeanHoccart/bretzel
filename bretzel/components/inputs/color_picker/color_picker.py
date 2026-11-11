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
from bretzel.components.base.arguments import reject_attribute_component
from bretzel.components.base.commands import ValueCommands
from bretzel.components.base.focus import FocusCommands
from bretzel.components.base.overlay_wiring import (
    anchored_dismiss_init,
    anchored_panel,
    imperative_listeners,
    install_open_close_toggle,
)
from bretzel.components.base.scope_wiring import bool_attr, server_sync_marker
from bretzel.components.inputs._picker_field import (
    clear_button,
    detach_wrapper_carriers,
    hidden_carrier,
    relocate_field_events,
    trigger_button,
    typed_field_attrs,
    value_expr,
)
from bretzel.components.inputs.color_picker.theme import COLOR_PICKER_THEME
from bretzel.core.tree import Element, Node
from bretzel.render import text
from bretzel.render.shared_parts import PART_ATTR, share_part

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
    from bretzel.components.base.attrs import ComponentUsageError

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    raise ComponentUsageError(
        f"{owner}(value={value!r}): type {type(value).__name__} not "
        "supported. Expected a hexadecimal string or None."
    )


def normalise_to_hex_js(field: str) -> str:
    """Rewrite ``field`` as ``#rrggbb`` (or ``#rrggbbaa``), lower case: with
    or without its ``#``, a short form doubled. Empty when it is no colour."""
    return (
        f"{field} = ((s) => {{ "
        "const m = s.trim().match(/^#?([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i); "
        "if (!m) return ''; const h = m[1].toLowerCase(); "
        "return '#' + (h.length < 6 ? h.replace(/./g, '$&$&') : h); "
        f"}})({field})"
    )


class ColorPicker(ValueCommands, FocusCommands, Component):
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
    # Where ``autofocus=`` / ``.focus()`` land. NOT ``"input"``: the first
    # ``<input>`` is the HIDDEN carrier, where ``.focus()`` does nothing.
    FOCUS_TARGET: ClassVar[tuple[str, ...] | None] = ("input:not([type=hidden])",)
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
        *,
        value: Any = None,
        name: str | None = None,
        placeholder: str | None = None,
        clearable: bool = True,
        disabled: bool | None = None,
        required: bool | None = None,
        color: str | None = None,
        size: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        reject_attribute_component(placeholder, owner="ColorPicker", prop="placeholder")
        self._placeholder = placeholder or "#rrggbb"
        # ``True`` like every picker (R5 of the API rules): a picker
        # empties with one click, a text field with the keyboard, and
        # ``""`` is a documented value (« no colour »). A colour that may
        # never be empty says so: ``clearable=False``.
        self._clearable = clearable
        super().__init__(
            value=value, name=name, disabled=disabled, required=required,
            color=color, size=size,
            on_change=on_change, on_focus=on_focus, on_blur=on_blur,
            **kwargs,
        )
        # AFTER `super().__init__`: the installer reads
        # `_binding_metadata`, which is only populated at that point.
        install_open_close_toggle(self)

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
        # with not a word in the console.
        local = ""
        # The value, read and written through the scope — not by its path:
        # the swatches are SHARED by every picker of the page (cf. the
        # panel below), and a bound picker's path
        # (``$bz.state.Studio.default.primary``) would make each palette
        # its own. In a method body the local field is ``this.<key>``.
        target = val
        if self._binding_metadata.get("value") is None:
            (key,) = self._scope_keys("value")
            sync = server_sync_marker(
                key, enabled=self._value_server_backed("value")
            )
            local = f",{key}: {json.dumps(initial)},{sync}"
            target = f"this.{key}"
        # ``local`` ends with a comma (``server_sync_marker``'s fragment
        # does), so the methods come without one: a doubled comma is a
        # syntax error that kills the scan of the whole page.
        # The framework's one-line indirection (``_read`` / ``_write``,
        # as ``scope_literal`` writes them).
        methods = (
            f"_read() {{ return {target}; }},"
            f"_write(v) {{ {target} = v; }}"
        )
        root_attrs["bz-data"] = "{open: false" + (local or ",") + methods + "}"
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
                "class": self.compose_class("swatch"),
                "aria-hidden": "true",
                # ``background-color`` and not ``background``: the
                # class sets the resting grey, and a ``background``
                # shorthand would erase it even when empty. Here, absent
                # value = no inline style = the grey shows.
                "bz-attr:style": f"{val} ? 'background-color:' + {val} : ''",
                **({"style": f"background-color:{initial}"} if initial else {}),
            },
            children=(),
        )

        field_attrs: dict[str, Any] = {
            "type": "text",
            "placeholder": self._placeholder,
            "class": self.compose_class("input_field"),
            "value": initial,
            # The typed text is read once, normalised, then written: a
            # value that leaves for the server is a whole colour.
            **typed_field_attrs(val, normalise_to_hex_js, lambda v: v),
            "autocomplete": "off",
            "spellcheck": "false",
            "aria-label": text("color_picker.label"),
        }
        if disabled:
            field_attrs["disabled"] = True
        if required:
            field_attrs["aria-required"] = "true"
        if "bz-on:blur" in relocated:
            relocated["bz-on:blur"] = (
                f"{field_attrs['bz-on:blur']}; {relocated['bz-on:blur']}"
            )
        field_attrs.update(relocated)
        self.forward_binding("disabled", field_attrs)

        frame_children: list[Node] = [
            swatch,
            Element(tag="input", attrs=field_attrs, children=()),
        ]

        if self._clearable:
            cross = clear_button(
                css=self.compose_class("clear_button"),
                icon_css=self.compose_class("button_icon"),
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
            css=self.compose_class("trigger_button"),
            icon_css=self.compose_class("button_icon"),
            aria_label=text("color_picker.open"),
            disabled=disabled,
        )
        self.forward_binding("disabled", opener.attrs)
        frame_children.append(opener)

        frame = Element(
            tag="div",
            attrs={"class": self.compose_class("input_frame"), "bz-ref": "bztrigger"},
            children=tuple(frame_children),
        )

        # The palette is the same in every colour picker of the page, and
        # closed until opened, so the page carries it
        # ONCE (``render/shared_parts.py``) and the panel clones it the
        # first time it opens. A swatch's selected mark is a
        # directive: the shared copy starts unselected and the scan sets
        # it. Outside a render context, the panel carries its own.
        def palette(selected: str) -> tuple[Element, ...]:
            return (
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
                        self._cell(hexa, val, selected, disabled)
                        for hexa in self._palette_swatches()
                    ),
                ),
            )

        key = share_part(palette(""))
        panel = anchored_panel(
            css=self.slot_class("panel"),
            children=() if key else palette(initial),
            extra_effect="if (open) $bz.parts.fill($el)" if key else "",
        )
        if key:
            panel = Element(tag=panel.tag, attrs={**panel.attrs, PART_ATTR: key},
                            children=panel.children)

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
            # The page's shared tooltip, not the browser's ``title``
            # bubble: it follows the theme, and it shows at once on focus
            # too. The name is the ``aria-label`` — the
            # panel does not repeat it to a screen reader.
            "data-bz-tip-root": "",
            "data-bz-tip": hexa,
            "aria-label": hexa,
            # ``bool_attr`` and not a hand-written ternary: ``bz-attr``
            # treats a boolean the way HTML wants (empty attribute, or
            # removed), yet ``data-[selected=true]:`` matches the
            # LITERAL. Forgetting the ternary breaks nothing visible —
            # the style does not apply, in silence.
            "data-selected": (
                "true" if initial.lower() == hexa.lower() else "false"
            ),
            "bz-attr:data-selected": bool_attr(
                f"(_read() || '').toLowerCase() === '{hexa.lower()}'"
            ),
            # Through the scope's ``_write`` (cf. ``bz-data`` above), the
            # same for every picker: the swatch is shared. ⚠️ In the
            # DIRECTIVE the names are bare (a ``with($scope)``); in the
            # METHOD body it is ``this.<key>`` — written the wrong way
            # round, the raise killed the runtime's scan for the WHOLE
            # PAGE, with no visible error.
            "bz-on:click": f"_write('{hexa}'); open = false",
        }
        if disabled:
            attrs["disabled"] = True
        self.forward_binding("disabled", attrs)
        return Element(tag="button", attrs=attrs, children=())
