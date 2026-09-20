"""``Link`` — anchor with three visual variants and a11y disabled state.

External links get ``target="_blank"`` + the ``rel="noopener noreferrer"``
safety pair. Disabled links suppress the ``href``, set ``aria-disabled``
and ``tabindex="-1"`` so keyboard users can't navigate.

The ``group`` class on the root carries ``group-hover:`` /
``group-focus-visible:`` reactivity to children (e.g. trailing chevrons
that should follow the link's state).
"""

from __future__ import annotations

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
    THEME_KEY: ClassVar[str] = "link"
    DEFAULT_TAG: ClassVar[str] = "a"
    # with status (counter, dynamic string). href changes when the
    # target depends on state. variant/color are design-time.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("label", "href")

    variant: str = reactive_prop(default="hover", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    href: str | None = reactive_prop(default=None, never_code=True)

    def __init__(
        self,
        label: str | ClientBinding | None = None,
        *,
        href: str | ClientBinding | None = None,
        variant: str | None = None,
        color: str | None = None,
        external: bool = False,
        download: bool = False,
        disabled: bool = False,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive ``None`` kwargs.
        # ``external`` / ``download`` / ``disabled`` are design-time
        # booleans → handled separately.
        super().__init__(href=href, variant=variant, color=color, **kwargs)
        # ``adopt_slot`` detaches a Component passed as a slot
        # (otherwise it renders twice); string / ClientBinding pass
        # through intact. Cf. traps.md § "A Component slot stored without
        # adopt_slot".
        self._label = Component.adopt_slot(label)
        self._external = external
        self._download = download
        self._disabled = disabled

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

        # ── Download: this link carries a FILE, not a navigation ─────
        #
        # ⚠️ ``hx-boost="false"`` is not an option: the shell sets
        # ``hx-boost`` on the page, so htmx intercepts EVERY ``<a>``,
        # fetches the target by XHR and injects it into the document. On
        # a CSV, that downloads nothing and replaces the page with plain
        # text — with no error, no failed request, nothing to see on the
        # server side.
        #
        # Measured on 2026-09-02 on the playground's `/meta`, before this
        # fix: ``resource_type: 'xhr'`` and the URL switched to
        # ``/meta-demo.csv``. It is the mechanism the datatable's export
        # already neutralised by hand (`datatable.py:745`); this makes it
        # available to everybody rather than leaving it to be
        # rediscovered.
        #
        # The HTML ``download`` attribute in addition: it tells the
        # browser NOT to display the file even if it knows how to render
        # it (an SVG, a PDF), and it lets the server name it through
        # ``Content-Disposition``.
        if self._download:
            attrs.setdefault("hx-boost", "false")
            attrs.setdefault("download", True)

        # Disabled : suppress ``href`` so keyboard nav can't follow it, mark
        # ``aria-disabled`` (screen readers + the theme's ``aria-disabled:*``
        # CSS) and ``tabindex="-1"`` to skip it in keyboard order.
        if self._disabled:
            self.release_root_attr("href", attrs)
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
