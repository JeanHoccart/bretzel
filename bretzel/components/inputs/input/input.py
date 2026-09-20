"""``Input`` — text input with prefix/suffix/icon slots.

The render path picks one of two layouts depending on whether the
caller passed a prefix / suffix string :

- **Bare** (``ui.input(name="email")``) : a single ``<input>`` styled
  with the ``input`` slot, optionally with absolute-positioned icons
  overlaid via ``icon_left`` / ``icon_right`` slots.
- **With affixes** (``ui.input(prefix="$", suffix=".com", …)``) : a
  ``<div class="prefix_root">`` wraps a transparent ``<input
  class="input_inner">`` flanked by inline ``<span>`` prefix/suffix.
  The frame and the focus ring move to the wrapper so the affix and
  the input share one visual unit.

Two-way binding via ``bz-model`` when ``value`` is a ClientBinding —
the user's typing flows back into the reactive store live.

"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.inputs._picker_field import icon_button
from bretzel.components.inputs._wiring import (
    add_local_value_scope,
    value_command_listeners,
)
from bretzel.components.inputs.input.theme import INPUT_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element
from bretzel.core.tree import TextNode as TextNode
from bretzel.render import text

# HTML5 ``<input>`` types that ship a native browser popup (calendar,
# clock, color wheel, file picker). Native UX is inconsistent across
# browsers AND not themable to match the rest of Bretzel — each kind
# has its own dedicated component instead. Block at construction time
# so the dev sees the right component to use, with a clear pointer.
_NATIVE_PICKER_TYPES: dict[str, str] = {
    "date":           "ui.date_picker (coming soon)",
    "time":           "ui.time_picker (coming soon)",
    "datetime-local": "ui.datetime_picker (coming soon)",
    "month":          "ui.month_picker (coming soon)",
    "color":          "ui.color_picker (coming soon)",
    "file":           "ui.file_upload (coming soon)",
    # Native ``type=number`` has too many cross-browser quirks (leading
    # zeros stripped, ``e`` scientific notation, inconsistent clamp/step,
    # FormData returns a string that may not parse). ``ui.number_input``
    # ships steppers, clamp-on-blur, and float precision instead.
    "number":         "ui.number_input",
}


class Input(Component):
    """Render a text input with distinct input and change events."""

    THEME: ClassVar[dict[str, Any]] = INPUT_THEME
    THEME_KEY: ClassVar[str] = "input"
    DEFAULT_TAG: ClassVar[str] = "input"
    IS_CONTAINER: ClassVar[bool] = False
    EVENTS: ClassVar[tuple[str, ...]] = (
        "change", "input", "focus", "blur", "keydown", "keyup",
    )
    # Reactive surface — only props that change during the input's
    # lifecycle (value: bz-model two-way; disabled: form locks;
    # readonly: edit/view). Everything else is design-time config.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = (
        "value", "disabled", "readonly",
    )
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "clear", "focus", "blur")

    type: str = reactive_prop(default="text")
    name: str | None = reactive_prop(default=None)
    placeholder: str | None = reactive_prop(default=None)
    value: Any = reactive_prop(default=None, writes=True, names_field=True)
    disabled: bool = reactive_prop(default=False)
    readonly: bool = reactive_prop(default=False)
    required: bool = reactive_prop(default=False)
    # HTML5 native validation passthrough — emitted as plain attrs.
    min: Any = reactive_prop(default=None)
    max: Any = reactive_prop(default=None)
    step: Any = reactive_prop(default=None)
    pattern: str | None = reactive_prop(default=None)
    minlength: int | None = reactive_prop(default=None)
    maxlength: int | None = reactive_prop(default=None)
    autocomplete: str | None = reactive_prop(default=None)
    # Visual props — consumed by the slot composer, kept off the DOM.
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)

    # Whitelist of accepted input types. Native UI types (date / time /
    # color / file / number / ...) are blocked at ``__init__`` so the dev
    # gets pointed to the right Bretzel component (cf. _NATIVE_PICKER_TYPES).
    ALLOWED_TYPES: ClassVar[frozenset[str]] = frozenset({
        "text", "email", "password",
        "tel", "url", "search", "hidden",
    })

    def __init__(
        self,
        *,
        type: str | None = None,
        name: str | None = None,
        placeholder: str | None = None,
        value: Any = None,
        disabled: bool | None = None,
        readonly: bool | None = None,
        required: bool | None = None,
        min: Any = None,
        max: Any = None,
        step: Any = None,
        pattern: str | None = None,
        minlength: int | None = None,
        maxlength: int | None = None,
        autocomplete: str | None = None,
        color: str | None = None,
        size: str | None = None,
        # Decorative slots — strings or Component instances.
        prefix: str | Component | None = None,
        suffix: str | Component | None = None,
        icon_left: str | Component | None = None,
        icon_right: str | Component | None = None,
        clearable: bool = False,
        on_change: Callable[..., Any] | str | None = None,
        on_input: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        on_keydown: Callable[..., Any] | str | None = None,
        on_keyup: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Block native-picker types early so the dev sees the right
        # Bretzel component. Only validate literal strings : a binding
        # carries a value we can't statically inspect (``in`` on a
        # binding returns a ClientExpression, not a bool), so reactive
        # ``type=`` is accepted as-is.
        if isinstance(type, str):
            if type in _NATIVE_PICKER_TYPES:
                raise ComponentUsageError(
                    f"Input does not accept type={type!r} — native "
                    f"browser pickers are inconsistent across browsers "
                    f"and don't honour the Bretzel theme. Use "
                    f"{_NATIVE_PICKER_TYPES[type]} instead."
                )
            if type not in self.ALLOWED_TYPES:
                raise ComponentUsageError(
                    f"Input does not accept type={type!r}. Allowed : "
                    f"{sorted(self.ALLOWED_TYPES)!r}."
                )

        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            type=type, name=name, placeholder=placeholder,
            value=value, disabled=disabled, readonly=readonly,
            required=required, min=min, max=max,
            step=step, pattern=pattern, minlength=minlength,
            maxlength=maxlength, autocomplete=autocomplete,
            color=color, size=size,
            on_change=on_change,
            on_input=on_input,
            on_focus=on_focus,
            on_blur=on_blur,
            on_keydown=on_keydown,
            on_keyup=on_keyup,
            **kwargs,
        )
        # ``adopt_slot`` auto-converts string shortcuts
        # (``icon_left="search"`` → ``Icon("search")``) and detaches
        # Component values from the active parent so they don't ALSO
        # render as siblings. ``prefix`` / ``suffix`` are plain text
        # affixes, so no icon shortcut for them.
        self._prefix = Component.adopt_slot(prefix)
        self._suffix = Component.adopt_slot(suffix)
        self._icon_left = Component.adopt_slot(icon_left, icon_shortcut=True)
        self._icon_right = Component.adopt_slot(icon_right, icon_shortcut=True)
        # Design-time, so an instance attribute and not a
        # ``reactive_prop``: nothing on the client side switches a field
        # between clearable and not clearable.
        #
        # Default ``False``, the OPPOSITE of the five pickers, which have
        # it at ``True``. It is not an inconsistency: a picker's value is
        # formatted (``2026-08-07``, ``09:30``) and tedious to clear by
        # hand, whereas a free-text field empties from the keyboard.
        # Putting a cross on EVERY input of every application would be a
        # global change for a gain that only exists on search fields.
        self._clearable = bool(clearable)

    # ── Imperative write-only API ─────────────────────────────────────
    #
    # Methods returning client JS for ``on_click=`` (or any ``on_*``).
    # ``.set`` write-throughs the binding if any, else DOM dispatch ;
    # ``.focus`` / ``.blur`` are direct DOM commands. Cf. `imperative-api.md`.

    def set(self, value: Any) -> str:
        return self._value_command(value)

    def clear(self) -> str:
        # ``.clear()`` is sugar for ``.set("")`` — empty string covers
        # the text-input case. NumberInput / Slider override if they
        # need a different reset value (0, min, etc.).
        return self.set("")

    def focus(self) -> str:
        return f"document.getElementById('{self.id}').focus()"

    def blur(self) -> str:
        return f"document.getElementById('{self.id}').blur()"


    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        size_key = self._reactive_values.get("size") or "md"
        size_map = (
            self._resolved_theme().get("sizes", {}).get(size_key) or {}
        )

        has_affix = self._prefix is not None or self._suffix is not None
        has_icon = (
            self._icon_left is not None
            or self._icon_right is not None
            or self._clearable
        )

        if has_affix:
            return self._render_with_affixes(size_map)
        return self._render_simple(size_map, has_icon)

    def _clear_button(self, size_map: dict[str, str]) -> Element:
        """The ``×`` — visible only when there is something to clear.

        **Its visibility is pure CSS** (``peer-placeholder-shown:hidden``
        in the slot), not a ``bz-show``. It is what allows adding the
        affordance without touching the value scope: that lives on the
        ``<input>`` (cf. ``add_local_value_scope``), where it carries the
        stable ``bz-id`` that makes the typed text survive a morph — and
        a sibling of the ``<input>`` cannot read it anyway.

        **The click goes through the same EVENTS as a human keystroke.**
        Writing ``.value = ''`` is not enough: ``bz-model`` subscribes to
        ``input`` (cf. ``02_directives.js``), so without this dispatch
        the signal would keep the old text and rewrite it at the next
        tick; and a server handler listens for ``change``, which the DOM
        does not emit either for a programmatic write. Both events
        therefore fire, in that order, and everything follows — binding,
        local scope, or bare input.

        The traversal is local (``$el.parentElement``) rather than a
        ``bz-ref``: a ref registers in the nearest scope, and an input
        with no scope would go and pollute the shared ``rootScope`` where
        two fields of the same page would overwrite each other.
        """
        return icon_button(
            icon="x",
            css=" ".join(p for p in (
                self.compose_class(
                    "clear_button", apply_variant_size_modifiers=False,
                ),
            ) if p),
            icon_css=Component.render_detached(
                Icon("x", size=size_map.get("clear_icon_size", "sm")),
            ).attrs.get("class", ""),
            aria_label=text("input.clear"),
            on_click=(
                "$event.stopPropagation(); "
                "const i = $el.parentElement.querySelector('input'); "
                "if (i) { i.value = ''; "
                "i.dispatchEvent(new Event('input', {bubbles: true})); "
                "i.dispatchEvent(new Event('change', {bubbles: true})); "
                "i.focus(); }"
            ),
            disabled=bool(self._reactive_values.get("disabled")),
        )

    # ── Layout : bare or icon-decorated ────────────────────────────────

    def _render_simple(
        self, size_map: dict[str, str], has_icon: bool
    ) -> Element:
        # Compose the input's own classes — frame + ring + size +
        # extra left/right padding when icons overlay.
        input_class = " ".join(
            p
            for p in (
                self.compose_class(
                    "input", apply_variant_size_modifiers=False
                ),
                size_map.get("input", ""),
                size_map.get("icon_pad_left", "")
                if self._icon_left is not None
                else "",
                size_map.get("icon_pad_right", "")
                if (self._icon_right is not None or self._clearable)
                else "",
                # ``peer``: it is IT the ``×`` interrogates through
                # ``peer-placeholder-shown``. Without the marker on the
                # input, the button's selector finds nothing and the
                # cross stays visible on an empty field.
                "peer" if self._clearable else "",
            )
            if p
        )

        input_attrs = self.emit_attrs()
        input_attrs["class"] = input_class
        # ``:placeholder-shown`` only matches if the attribute exists:
        # with no placeholder, the ``×``'s selector never finds anything
        # and the cross would stay shown on an empty field — the exact
        # opposite of what it promises. A single space is enough and
        # paints nothing.
        if self._clearable and not input_attrs.get("placeholder"):
            input_attrs["placeholder"] = " "
        self._bind_x_model(input_attrs)
        # Local + interactive : internal ``value`` scope on the <input> so
        # typed text survives a @refreshable morph (same model as the rich
        # inputs). No-op in binding mode or for a handler-less input.
        add_local_value_scope(
            self, input_attrs, prop="value",
            ssr_value=self._reactive_values.get("value"),
        )
        # Imperative-API listeners (``.set(value)`` / ``.clear()``) —
        # cf. ``inputs/_wiring.py``.
        input_attrs.update(value_command_listeners())
        input_el = Element(tag="input", attrs=input_attrs, children=())

        # No icons → just emit the bare input, no wrapper noise.
        if not has_icon:
            return input_el

        # Icons → wrap in ``root`` with absolute-positioned overlays.
        children: list[Any] = []
        if self._icon_left is not None:
            children.append(self._slot_element("icon_left", self._icon_left))
        children.append(input_el)
        if self._icon_right is not None:
            children.append(self._slot_element("icon_right", self._icon_right))
        # AFTER the input: ``peer-*`` only looks at a PRECEDING sibling.
        if self._clearable:
            children.append(self._clear_button(size_map))

        root_class = self.compose_class(
            "root", apply_variant_size_modifiers=False
        )
        return Element(
            tag="div",
            attrs={"class": root_class},
            children=tuple(children),
        )

    # ── Layout : with prefix / suffix ──────────────────────────────────

    def _render_with_affixes(self, size_map: dict[str, str]) -> Element:
        # The frame + ring move to the wrapper ; the input goes
        # transparent (``input_inner`` slot) and sits between the
        # affix spans.
        wrapper_class = self.compose_class(
            "prefix_root", apply_variant_size_modifiers=False
        )
        input_inner_class = " ".join(
            p
            for p in (
                self.compose_class(
                    "input_inner", apply_variant_size_modifiers=False
                ),
                size_map.get("input", ""),
                "peer" if self._clearable else "",
            )
            if p
        )

        input_attrs = self.emit_attrs()
        input_attrs["class"] = input_inner_class
        # ``:placeholder-shown`` only matches if the attribute exists:
        # with no placeholder, the ``×``'s selector never finds anything
        # and the cross would stay shown on an empty field — the exact
        # opposite of what it promises. A single space is enough and
        # paints nothing.
        if self._clearable and not input_attrs.get("placeholder"):
            input_attrs["placeholder"] = " "
        self._bind_x_model(input_attrs)
        # Local + interactive : internal ``value`` scope (cf. _render_simple).
        add_local_value_scope(
            self, input_attrs, prop="value",
            ssr_value=self._reactive_values.get("value"),
        )
        # Imperative-API listeners (``.set(value)`` / ``.clear()``) —
        # cf. ``inputs/_wiring.py``.
        input_attrs.update(value_command_listeners())
        input_el = Element(tag="input", attrs=input_attrs, children=())

        children: list[Any] = []
        if self._prefix is not None:
            children.append(self._slot_element("prefix", self._prefix))
        children.append(input_el)
        if self._suffix is not None:
            children.append(self._slot_element("suffix", self._suffix))
        # AFTER the input: ``peer-*`` only looks at a PRECEDING sibling.
        # Here the frame lives on the wrapper (not on the input), so the
        # ``×`` positions itself there the same way — ``absolute
        # right-3`` on a parent that is not ``relative`` would fall back
        # on the first positioned ancestor.
        if self._clearable:
            children.append(self._clear_button(size_map))

        return Element(
            tag="div",
            attrs={"class": wrapper_class},
            children=tuple(children),
        )

    # ── helpers ────────────────────────────────────────────────────────

    def _slot_element(self, slot: str, content: Any) -> Element:
        """Build the ``<span>`` (or pre-rendered Component) for a
        decorative slot."""
        slot_class = self.compose_class(
            slot, apply_variant_size_modifiers=False
        )
        if isinstance(content, Component):
            # Component author : render as-is and stamp the slot class
            # on its root attrs.
            node = content.render()
            return Component.with_slot_class(  # type: ignore[return-value]
                node, slot_class
            )
        return Element(
            tag="span",
            attrs={"class": slot_class},
            children=(TextNode(str(content)),),
        )
