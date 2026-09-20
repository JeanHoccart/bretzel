"""``IconButton`` — square button whose only content is an icon.

Same visual identity as :class:`Button` but the size axis controls
``h × w`` together (``size="md"`` → ``h-10 w-10``). The icon is positional
(``ui.icon_button("trash-2", on_click=…)``) and accepts a string Iconify
name (auto-wrapped in :class:`Icon`). The visible content being an icon
with no fallback text, the button needs an **accessible name** —
``aria_label="…"`` gives it, and failing that the ``tooltip=`` supplies
it (cf. :meth:`IconButton.render`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.actions._wiring import (
    apply_loading_disabled,
    build_loading_spinner,
    loading_leading_children,
)
from bretzel.components.actions.icon_button.theme import ICON_BUTTON_THEME
from bretzel.components.base import Component, reactive_prop
from bretzel.components.primitives.spinner import Spinner
from bretzel.core.tree import Element, Node


class IconButton(Component):
    """Icon-only button. Pass the icon name positionally + an
    ``aria_label`` for screen readers."""

    THEME: ClassVar[dict[str, Any]] = ICON_BUTTON_THEME
    THEME_KEY: ClassVar[str] = "icon_button"
    DEFAULT_TAG: ClassVar[str] = "button"
    IS_CONTAINER: ClassVar[bool] = False
    EVENTS: ClassVar[tuple[str, ...]] = (
        "click", "focus", "blur", "mouseenter", "mouseleave",
    )
    # Same shape as Button — disabled / loading change during async ;
    # icon is design-time. (No ``label``-equivalent — IconButton's icon
    # IS the content, and icon changes via conditional render.)
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("disabled", "loading")

    variant: str = reactive_prop(default="ghost", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    type: str = reactive_prop(default="button")
    disabled: bool = reactive_prop(default=False)
    loading: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        icon: str | Component | None = None,
        *,
        variant: str | None = None,
        size: str | None = None,
        color: str | None = None,
        type: str | None = None,
        disabled: Any = None,
        loading: Any = None,
        on_click: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        on_mouseenter: Callable[..., Any] | str | None = None,
        on_mouseleave: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive ``None`` kwargs
        # (keeps the default).
        super().__init__(
            variant=variant,
            size=size,
            color=color,
            type=type,
            disabled=disabled,
            loading=loading,
            on_click=on_click,
            on_focus=on_focus,
            on_blur=on_blur,
            on_mouseenter=on_mouseenter,
            on_mouseleave=on_mouseleave,
            **kwargs,
        )
        # ``adopt_slot`` does the string→Icon conversion + detaches the icon
        # from the active parent if it auto-registered there. Pre-wrap string
        # shortcuts with the button's size so the inner glyph scales with the
        # button (Icon's ``text-{size}`` sets the glyph font-size). A fully-
        # built Component flows through untouched — its explicit size wins.
        if isinstance(icon, str):
            from bretzel.components.primitives.icon import Icon

            icon = Icon(icon, size=self._reactive_values.get("size") or "md")
        self._icon: Component | None = Component.adopt_slot(
            icon, icon_shortcut=True
        )

        self._loading_spinner: Spinner | None = build_loading_spinner(self)

    def render(self) -> Element:
        attrs = self.emit_attrs()
        self.apply_class_attrs(attrs)

        # An icon button with no text has NO accessible name: a screen
        # reader announces "button", and a test cannot find it by
        # role+name. The ``tooltip=`` already says in full what the
        # button is for — it wraps the component in a :class:`Tooltip`,
        # which is a hover, not a label. So we copy it into
        # ``aria-label`` when the caller has not set one.
        #
        # Measured on 2026-08-19: the CRM's hamburger carried a
        # ``tooltip`` and stayed anonymous. The framework's datatable,
        # for its part, writes both by hand (``tooltip=`` AND
        # ``aria_label=`` on its "Clear filters") — the knowledge
        # existed, it was not shared.
        #
        # Only a string: a ``tooltip=ui.text(...)`` is rich content, and
        # flattening a tree into a label would produce a sentence nobody
        # wrote.
        if "aria-label" not in attrs and isinstance(self._tooltip, str):
            label = self._tooltip.strip()
            if label:
                attrs["aria-label"] = label

        loading_binding = self._binding_metadata.get("loading")
        loading = bool(self._reactive_values.get("loading"))
        if loading:
            attrs["disabled"] = True

        children: list[Node] = []
        icon_comp = self._icon

        # Reactive: ``disabled`` follows ``(loading || disabled)`` so
        # the button stays unclickable during the async window.
        if loading_binding is not None:
            apply_loading_disabled(
                self, attrs, self.path_of(loading_binding),
            )
        children.extend(loading_leading_children(
            self,
            loading=loading,
            loading_path=(
                self.path_of(loading_binding)
                if loading_binding is not None else None
            ),
            spinner=self._loading_spinner,
            icon=icon_comp,
        ))

        return Element(tag=self._tag, attrs=attrs, children=tuple(children))


__all__ = ["IconButton"]
