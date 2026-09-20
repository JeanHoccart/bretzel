"""``Textarea`` — multi-line text input.

Visually identical to :class:`Input` but renders ``<textarea>``
instead of ``<input>`` and exposes a ``rows`` prop for the initial
height. Two-way bind via ``bz-model`` when ``value`` is a
:class:`ClientBinding` — the user's typing flows back into the
reactive store live.

``autosize`` / ``max_rows`` are Phase-2 features that need a small JS
helper (ResizeObserver-based) to grow the field with content. For now
the user controls height via ``rows=`` and CSS overrides
(``classes="resize-y"`` to opt back in to manual resize).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop, reject_component
from bretzel.components.inputs._wiring import (
    add_local_value_scope,
    value_command_listeners,
)
from bretzel.components.inputs.textarea.theme import TEXTAREA_THEME
from bretzel.core.tree import Element
from bretzel.core.tree import TextNode as TextNode


class Textarea(Component):
    """Multi-line text input."""

    THEME: ClassVar[dict[str, Any]] = TEXTAREA_THEME
    THEME_KEY: ClassVar[str] = "textarea"
    DEFAULT_TAG: ClassVar[str] = "textarea"
    IS_CONTAINER: ClassVar[bool] = False
    # Curated reactive surface — same shape as Input.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = (
        "value", "disabled", "readonly",
    )
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "clear", "focus", "blur")
    EVENTS: ClassVar[tuple[str, ...]] = (
        "change", "input", "focus", "blur", "keydown", "keyup",
    )

    name: str | None = reactive_prop(default=None)
    placeholder: str | None = reactive_prop(default=None)
    value: Any = reactive_prop(default=None, writes=True, names_field=True)
    rows: int = reactive_prop(default=4)
    disabled: bool = reactive_prop(default=False)
    readonly: bool = reactive_prop(default=False)
    required: bool = reactive_prop(default=False)
    minlength: int | None = reactive_prop(default=None)
    maxlength: int | None = reactive_prop(default=None)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)

    def __init__(
        self,
        *,
        name: str | None = None,
        placeholder: str | None = None,
        value: Any = None,
        rows: int | None = None,
        disabled: bool | None = None,
        readonly: bool | None = None,
        required: bool | None = None,
        minlength: int | None = None,
        maxlength: int | None = None,
        color: str | None = None,
        size: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_input: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        on_keydown: Callable[..., Any] | str | None = None,
        on_keyup: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        reject_component(
            value,
            owner="Textarea",
            prop="value",
            because=(
                "``value`` is the field's VALUE — the one the form posts "
                "and the one the runtime writes into the ``<textarea>``'s "
                "``.value`` IDL property, which only knows strings. A "
                "Component was stringified there as its Python repr, so "
                "it is that repr that would have been submitted."
            ),
            instead=(
                "For a value that changes on the client side, pass a "
                "ClientBinding: ``value=state.draft``."
            ),
        )
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            name=name, placeholder=placeholder, value=value,
            rows=rows, disabled=disabled, readonly=readonly,
            required=required, minlength=minlength,
            maxlength=maxlength, color=color, size=size,
            on_change=on_change,
            on_input=on_input,
            on_focus=on_focus,
            on_blur=on_blur,
            on_keydown=on_keydown,
            on_keyup=on_keyup,
            **kwargs,
        )

    # ── Imperative write-only API ─────────────────────────────────────
    #
    # Methods returning client JS for ``on_click=`` (or any ``on_*``).
    # ``.set`` write-throughs the binding if any, else DOM dispatch ;
    # ``.focus`` / ``.blur`` are direct DOM commands. Cf. `imperative-api.md`.

    def set(self, value: Any) -> str:
        return self._value_command(value)

    def clear(self) -> str:
        # ``.clear()`` is sugar for ``.set("")`` — empty string covers
        # the text-input case.
        return self.set("")

    def focus(self) -> str:
        return f"document.getElementById('{self.id}').focus()"

    def blur(self) -> str:
        return f"document.getElementById('{self.id}').blur()"


    def render(self) -> Element:
        cls_string = self.compose_class("root")
        attrs = self.emit_attrs()
        attrs["class"] = cls_string

        # Two-way bind via bz-model when value is a ClientBinding.
        # ``<textarea>``'s value is its TEXT CONTENT, not a ``value``
        # attribute, so the literal-string branch drops the ``value``
        # attr the base would have emitted and pours the text into
        # ``children`` instead.
        binding = self._bind_x_model(attrs)
        if binding is not None:
            initial_text: Any = ""
        else:
            raw = self._reactive_values.get("value")
            if isinstance(raw, str):
                attrs.pop("value", None)
                initial_text = raw
            else:
                initial_text = ""

        # Local + interactive : internal ``value`` scope on the <textarea>
        # so typed text survives a @refreshable morph (same model as
        # Input ; bz-model two-ways via the ``.value`` IDL property, which
        # for a textarea reflects its text content). No-op in binding mode
        # or for a handler-less textarea.
        add_local_value_scope(
            self, attrs, prop="value",
            ssr_value=initial_text,
        )

        # Imperative-API listeners (``.set(value)`` / ``.clear()``) —
        # cf. ``inputs/_wiring.py``.
        attrs.update(value_command_listeners())

        children = (TextNode(initial_text),) if initial_text else ()
        return Element(tag=self._tag, attrs=attrs, children=children)
