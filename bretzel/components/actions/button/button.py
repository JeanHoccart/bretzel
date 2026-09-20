"""``Button`` — Archetype 3 action component.

A callable ``on_click`` becomes an HMAC-stamped ``hx-post`` action route ;
a string is emitted as a ``bz-on:click`` expression evaluated client-side.

``href=`` turns the button into an **anchor** — same dressing, different
semantics. It is a functional distinction, not a decorative one: an
``<a>`` opens on a middle click, is copied by "open in a new tab", and
says "link" to a screen reader. A call to action that NAVIGATES should
therefore use ``href=`` rather than a manual tag change.
:class:`~bretzel.components.layout.card.Card` follows the same contract.

``loading=True`` swaps the ``icon_left`` slot for a :class:`Spinner`,
suppresses ``icon_right``, and forces the rendered ``<button>`` into the
disabled state (50 % opacity, ``cursor-not-allowed`` via the root slot's
``disabled:`` variant) so the click is blocked while in flight. No separate
``loading`` modifier — that would reintroduce a source-order race against
``disabled:cursor-not-allowed``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.actions._wiring import (
    apply_loading_disabled,
    build_loading_spinner,
    loading_leading_children,
)
from bretzel.components.actions.button.theme import BUTTON_THEME
from bretzel.components.base import Component, reactive_prop
from bretzel.components.primitives.spinner import Spinner
from bretzel.core.tree import Element, Node
from bretzel.state.scopes.client import ClientBinding


class Button(Component):
    """Action button with variant / size / color theming + named slots."""

    THEME: ClassVar[dict[str, Any]] = BUTTON_THEME
    THEME_KEY: ClassVar[str] = "button"
    DEFAULT_TAG: ClassVar[str] = "button"
    IS_CONTAINER: ClassVar[bool] = False
    NAMED_SLOTS: ClassVar[tuple[str, ...]] = ("icon_left", "icon_right")
    ICON_SLOTS: ClassVar[tuple[str, ...]] = ("icon_left", "icon_right")
    EVENTS: ClassVar[tuple[str, ...]] = (
        "click",
        "focus",
        "blur",
        "mouseenter",
        "mouseleave",
    )
    # Reactive surface : props that change during the button's lifecycle
    # (label, disabled, loading). variant / size / color / type / icons are
    # design-time — conditional render covers the rest.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = (
        "label", "disabled", "loading", "href",
    )

    # Cosmetic props (consumed by ``_compose_classes`` only — kept off
    # the DOM via ``emit_attr=False``). ``type`` and ``disabled`` are
    # real HTML attributes so they ride through.
    variant: str = reactive_prop(default="solid", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    loading: bool = reactive_prop(default=False, emit_attr=False)
    type: str = reactive_prop(default="button")
    disabled: bool = reactive_prop(default=False)
    href: str | None = reactive_prop(default=None, never_code=True)

    def __init__(
        self,
        label: str | ClientBinding | None = None,
        *,
        variant: str | None = None,
        size: str | None = None,
        color: str | None = None,
        type: str | None = None,
        href: str | ClientBinding | None = None,
        external: bool = False,
        disabled: Any = None,
        loading: Any = None,
        icon_left: Component | str | None = None,
        icon_right: Component | str | None = None,
        on_click: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        on_mouseenter: Callable[..., Any] | str | None = None,
        on_mouseleave: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive ``None`` kwargs
        # (keeps the descriptor's default); a ``None`` slot reads as
        # ``.get()``→None.
        super().__init__(
            variant=variant,
            size=size,
            color=color,
            type=type,
            href=href,
            disabled=disabled,
            loading=loading,
            icon_left=icon_left,
            icon_right=icon_right,
            on_click=on_click,
            on_focus=on_focus,
            on_blur=on_blur,
            on_mouseenter=on_mouseenter,
            on_mouseleave=on_mouseleave,
            **kwargs,
        )
        # ``adopt_slot`` detaches a Component passed as label from the parent
        # its own ``__init__`` auto-registered into — else it renders twice
        # (standalone in the parent flow AND inside this Button). Strings /
        # ClientBindings / None flow through unchanged.
        self._label = Component.adopt_slot(label)
        self._external = external

        # ── An href makes this button an ANCHOR ───────────────────────
        # The tag switches here and not in ``render``: ``self._tag`` is
        # read by introspection and by the gates, and a component whose
        # tag only knows itself at render lies to whoever asks it.
        # An explicit ``tag=`` wins — it is the tier-2 escape hatch, and
        # the caller who writes it knows what they are doing.
        if href is not None and "tag" not in kwargs:
            self._tag = "a"
        if href is not None and on_click is not None:
            raise TypeError(
                "ui.button does not take `href=` AND `on_click=`: they "
                "are two jobs (navigate / act) on one target, and nothing "
                "would announce which applies. Choose — or place two "
                "controls."
            )
        if href is not None and type is not None:
            raise TypeError(
                "ui.button(href=…) renders an `<a>`, where `type=` names "
                "the target's MIME type and not a button's nature. Remove "
                "`type=`."
            )

        # Build the spinner eagerly here (not in render()) : Spinner's ctor
        # needs a live render context for ID allocation, and render() may run
        # after the context is torn down (notably in unit tests). Spinner's
        # default ``color="current"`` inherits the button's text colour. Build
        # it whenever loading is truthy OR carries a binding — the reactive
        # case needs the DOM node ready even if loading defaults False at SSR,
        # since the mutex emits both branches for the runtime to bz-show.
        self._loading_spinner: Spinner | None = build_loading_spinner(self)

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        attrs = self.emit_attrs()
        self.apply_class_attrs(attrs)

        # ── What no longer makes sense once the tag has changed ───────
        # ``type`` is declared with ``default="button"``, so it comes out
        # of ``emit_attrs`` even when nobody asked for it. On an ``<a>``
        # it names the target's MIME type: leaving it produced
        # `<a type="button">`, HTML that means nothing and that the
        # `tag="a"` instructions shipped as is.
        if self._tag != "button":
            attrs.pop("type", None)

        # Loading forces the rendered ``<button>`` disabled to block double-
        # submits during the async window ; the reactive ``disabled`` prop
        # itself stays untouched so toggling loading off restores it.
        loading_binding = self._binding_metadata.get("loading")
        loading = bool(self._reactive_values.get("loading"))
        if loading:
            attrs["disabled"] = True

        # Reactive ``loading || disabled`` : OR-combine both bindings so the
        # HTML disabled attr stays true while EITHER side is. ``path_of``
        # resolves a ClientBinding or ClientExpression to its JS source.
        if loading_binding is not None:
            path = self.path_of(loading_binding)
            apply_loading_disabled(self, attrs, path)

        icon_left = self._slot_components.get("icon_left")
        icon_right = self._slot_components.get("icon_right")

        children: list[Node] = []

        children.extend(loading_leading_children(
            self,
            loading=loading,
            loading_path=path if loading_binding is not None else None,
            spinner=self._loading_spinner,
            icon=icon_left,
        ))

        label_node = self.emit_text_slot(self._label)
        if label_node is not None:
            children.append(label_node)

        if loading_binding is not None:
            if icon_right is not None:
                children.append(
                    self._cloak_show(
                        icon_right.render(), f"!{path}", initial=not loading
                    )
                )
        elif not loading and icon_right is not None:
            children.append(icon_right.render())

        if self._tag == "a":
            # External: a new tab + a neutralised opener. Same writing
            # as ``ui.link`` — the ``rel`` pair is not cosmetic, it stops
            # the opened page reaching ``window.opener``.
            if self._external:
                attrs.setdefault("target", "_blank")
                attrs.setdefault("rel", "noopener noreferrer")
            # Disabled: an ``<a>`` has no ``disabled`` attribute, and
            # setting it blocks NOTHING. We remove the destination, take
            # it out of the tab order and say so out loud — exactly what
            # ``ui.link`` does, whose theme and this one share the
            # ``aria-disabled:`` selector.
            if attrs.pop("disabled", None):
                attrs.pop("href", None)
                attrs["aria-disabled"] = "true"
                attrs["tabindex"] = "-1"

        return Element(tag=self._tag, attrs=attrs, children=tuple(children))
