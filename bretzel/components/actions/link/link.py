"""``Link`` — anchor with three visual variants and a11y disabled state.

External links get ``target="_blank"`` + the ``rel="noopener noreferrer"``
safety pair. Disabled links suppress the ``href``, set ``aria-disabled``
and ``tabindex="-1"`` so keyboard users can't navigate.

The ``group`` class on the root carries ``group-hover:`` /
``group-focus-visible:`` reactivity to children (e.g. trailing chevrons
that should follow the link's state).
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from bretzel.components.actions.link.theme import LINK_THEME
from bretzel.components.base import Component, reactive_prop
from bretzel.core.tree import Element
from bretzel.state.scopes.client import ClientBinding


class Link(Component):
    """Anchor element with semantic colour, three variants
    (``hover`` / ``underline`` / ``text``), and a11y-correct disabled
    state."""

    THEME: ClassVar[dict[str, Any]] = LINK_THEME
    # ``autofocus=`` only: ``.focus()`` would put an id on every
    # button of every page (cf. ``components/base/focus.py``).
    FOCUS_TARGET: ClassVar[tuple[str, ...] | None] = ()
    THEME_KEY: ClassVar[str] = "link"
    DEFAULT_TAG: ClassVar[str] = "a"
    # with status (counter, dynamic string). href changes when the
    # target depends on state. variant/color are design-time.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("href", "disabled")

    variant: str = reactive_prop(default="hover", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    #: The steps of ``ui.text`` (``"xs"`` … ``"6xl"``); ``None`` keeps
    #: the parent's size — a link in a sentence reads as the sentence.
    size: str | None = reactive_prop(default=None, emit_attr=False)
    href: str | None = reactive_prop(default=None)
    disabled: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        label: str | Component | ClientBinding | None = None,
        *,
        href: str | ClientBinding | None = None,
        variant: str | None = None,
        color: str | None = None,
        size: str | None = None,
        external: bool = False,
        disabled: Any = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive ``None`` kwargs.
        # ``external`` is a design-time boolean → handled separately.
        super().__init__(href=href, variant=variant, color=color, size=size, disabled=disabled,
                         **kwargs)
        self._label = label
        self._external = external

    def render(self) -> Element:
        # ``compose_class`` reads slots + variant. We add the text's
        # colour here so as not to pollute the variant templates — and it
        # is the STEP we write, not a colour name: the bridge the base
        # layer sets on that same root says which one.
        cls_string = f'{self.compose_class("root")} text-(--bz-text)'.strip()

        attrs = self.emit_attrs()
        attrs["class"] = cls_string

        # External : open in a new tab + neuter the opener for security.
        if self._external:
            attrs.setdefault("target", "_blank")
            attrs.setdefault("rel", "noopener noreferrer")

        # Disabled : suppress ``href`` so keyboard nav can't follow it, mark
        # ``aria-disabled`` (screen readers + the theme's ``aria-disabled:*``
        # CSS) and ``tabindex="-1"`` to skip it in keyboard order.
        # Bound, the same three follow the client value.
        bound = self._binding_metadata.get("disabled")
        if bound is not None:
            path = self.path_of(bound)
            target = attrs.get("bz-attr:href") or json.dumps(attrs.get("href") or "")
            attrs["bz-attr:href"] = f"({path}) ? null : {target}"
            self.forward_binding("disabled", attrs, as_attr="aria-disabled")
            attrs["bz-attr:tabindex"] = f"({path}) ? '-1' : null"
        if self._reactive_values.get("disabled"):
            if bound is None:
                self.release_root_attr("href", attrs)
            attrs.pop("href", None)
            attrs["aria-disabled"] = "true"
            attrs["tabindex"] = "-1"

        children = list(self._render_children())
        # Inline-text shortcut takes precedence over child nodes if the
        # user passed both — same as Button.label. ``emit_text_slot``
        # handles the static-vs-ClientBinding split (raw text node vs
        # ``<span bz-text="...">``).
        label_node = self.emit_text_slot(self._label)
        if label_node is not None:
            children = [label_node, *children]

        return Element(tag=self._tag, attrs=attrs, children=tuple(children))
