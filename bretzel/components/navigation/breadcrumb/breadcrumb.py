"""``Breadcrumb`` — page-location trail.

A flat row of links separated by a marker (chevron by default), with
the final entry rendered as plain text (the current location).

Two tiers, and it is **the author who owns the loop**
(``COLLECTION_OWNER = "author"``, cf. ``Component``):

**Tier 1 — the shortcut**, when the trail is only text ::

    ui.breadcrumb([
        {"label": "Home", "href": "/"},
        {"label": "Projects", "href": "/projects"},
        {"label": "Tracker"},   # last item — no href, current page
    ])

Items can be plain dicts, ``(label, href)`` tuples, or bare strings ;
the last item becomes the ``current`` segment whether or not it has an
``href`` — the trail's last node is by definition where the user is.

**Tier 2 — the children**, as soon as a segment wants markup ::

    with ui.breadcrumb():
        ui.breadcrumb_item("Home", href="/")
        with ui.breadcrumb_item(href="/projects"):
            ui.icon("folder", size="xs")
            ui.text("Projects")
        ui.breadcrumb_item("Tracker")

It is :class:`~bretzel.components.inputs.ToggleGroup`'s shape, and the
idiom of ten of the catalogue's eleven collections. The component knows
by itself which segment is the last — the author does not have to tell
it.

To customise a segment's markup, use :class:`BreadcrumbItem` rather than
a render callback: its parameters are typed, autocompleted and visible
in ``bretzel describe``.

The separator is a string (interpreted as an Icon name or a literal
text) by default — pass ``separator="/"`` for a slash, or any
:class:`Component` / Element for a custom glyph.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from bretzel.components.base import Component, ComponentUsageError, reactive_prop
from bretzel.components.base.composition import unwrap_transparent
from bretzel.components.base.theme_values import theme_context
from bretzel.components.base.universals import finish_render
from bretzel.components.navigation.breadcrumb.theme import BREADCRUMB_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as TextNode
from bretzel.render import text
from bretzel.state.scopes.client import ClientBinding


class Breadcrumb(Component):
    """Page-location trail with chevron-separated parents."""

    THEME: ClassVar[dict[str, Any]] = BREADCRUMB_THEME
    THEME_KEY: ClassVar[str] = "breadcrumb"
    #: Draws its children itself: a zone among them is refused
    #: (``base/composition.unwrap_transparent``).
    _COMPOSES_CHILDREN: ClassVar[bool] = True
    DEFAULT_TAG: ClassVar[str] = "nav"
    # Container — it is the base layer's default, so not redeclared
    # here: the author writes their ``for``, they need somewhere to put
    # their markup. ``items=`` stays the text case's shortcut, and
    # materialises the same children.
    COLLECTION_OWNER: ClassVar[str | None] = "author"
    # Pure structural display — items are a list rendered at server
    # time, no reactive props expected. Empty tuple = strict mode +
    # nothing bindable.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    # most apps don't want a colored accent baked in. Inherits the
    # parent text colour via Tailwind's ``text-current``. Callers opt
    # in to a semantic palette (``color="primary"`` etc.) when they
    # want the trail to emphasise.
    color: str = reactive_prop(default="current", emit_attr=False)
    size: str = reactive_prop(default="sm", emit_attr=False)

    def __init__(
        self,
        items: Sequence[Any] = (),
        *,
        separator: str | Component = "chevron-right",
        color: str | None = None,
        size: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(color=color, size=size, **kwargs)
        # The ``items=`` shortcut materialises the SAME children as the
        # container form — a single render path afterwards. (Mixing the
        # two in one trail is not supported: it is ``ToggleGroup``'s
        # rule, for the same reason.)
        if items:
            with self:
                for entry in items:
                    label, href, icon = _normalise_item(entry)
                    BreadcrumbItem(label, href=href, icon=icon)
        # A string separator may be a literal "/" as much as an icon
        # name: ``_render_separator`` decides.
        self._separator: str | Component = separator

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        _theme, slots, sizes, size_key, _color = theme_context(self, size_default="sm", color_default="current")
        size_class = sizes.get(size_key, sizes.get("sm", ""))

        item_class = " ".join(
            p
            for p in (
                slots.get("item", ""),
                size_class,
            )
            if p
        )
        current_class = " ".join(
            p
            for p in (
                slots.get("current", ""),
                size_class,
            )
            if p
        )
        separator_class = slots.get("separator", "")

        # ``unwrap_transparent``: a WRAPPED segment — a
        # ``@refreshable`` zone, a ``ui.fragment`` — is not an instance
        # of ``BreadcrumbItem``, so without this it would DISAPPEAR from
        # the breadcrumb, with no error.
        segments = [
            (child, rewrap)
            for child, rewrap in (unwrap_transparent(c, self) for c in self._children)
            if isinstance(child, BreadcrumbItem)
        ]
        children: list[Element] = []
        for index, (seg, rewrap) in enumerate(segments):
            if children:
                children.append(
                    _render_separator(self._separator, separator_class, self)
                )
            # ``finish_render`` here, at the call, and not in
            # ``_render_segment``: the segment's own ``render()`` reuses
            # that method and already goes through the metaclass wrap.
            children.append(
                rewrap(finish_render(seg, seg._render_segment(
                    is_last=index == len(segments) - 1,
                    item_class=item_class,
                    current_class=current_class,
                )))
            )

        root_attrs = self.emit_attrs()
        root_attrs["class"] = " ".join(p for p in (self.compose_class(
            "root", apply_variant_size_modifiers=False
        ), size_class) if p)
        root_attrs.setdefault("aria-label", text("breadcrumb.label"))
        return Element(
            tag=self._tag, attrs=root_attrs, children=tuple(children)
        )


class BreadcrumbItem(Component):
    """Render one breadcrumb segment with an optional icon and link."""

    THEME_KEY: ClassVar[str] = "breadcrumb"
    DEFAULT_TAG: ClassVar[str] = "a"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    NAMED_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    #: ``icon="book"`` rather than ``icon=ui.icon("book")`` — the string
    #: shortcut the ten peers also offer.
    ICON_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)

    def __init__(
        self,
        label: str | Component | None = None,
        *,
        icon: str | Component | None = None,
        href: str | None = None,
        **kwargs: Any,
    ) -> None:
        # ⚠️ An ``icon="book"`` is NOT handed to ``ICON_SLOTS``: the
        # base layer would wrap it as ``ui.icon(name)`` at the default
        # size (``md`` = 18 px), calibrated for 16 px body text. A
        # breadcrumb's label is 12 px, so the icon would dwarf its text.
        # We keep the NAME and build the Icon at render,
        # when the label's size is finally known.
        #
        # A Component passed by hand keeps ITS size: the author chose it,
        # it is not the component's business to correct it.
        self._icon_name = icon if isinstance(icon, str) else None
        super().__init__(icon=None if self._icon_name else icon, **kwargs)
        self._label = label
        self._href = href

    # ── Internal render — called by Breadcrumb ────────────────────────

    def _render_segment(
        self, *, is_last: bool, item_class: str, current_class: str
    ) -> Element:
        """The wrapper belongs to the component, the content to the author.

        The last segment is a ``<span aria-current="page">`` and not a
        link: it is the page you ARE on, making it clickable would
        announce a navigation that does not happen.
        """
        body: list[Node] = []
        icon = self._slot_components.get("icon")
        if icon is None and self._icon_name:
            from bretzel.components.base.sizes import icon_size_for
            from bretzel.components.primitives.icon import Icon

            # The segment's class carries the label's size; the icon
            # takes the step just above. Fallback ``sm`` when the segment
            # is rendered outside a trail (no class received).
            size = icon_size_for(current_class if is_last else item_class)
            icon = Icon(self._icon_name, size=size or "sm")
        if icon is not None:
            body.append(Component.render_detached(icon))
        label_node = self.emit_text_slot(self._label)
        if label_node is not None:
            body.append(label_node)

        if is_last:
            return Element(
                tag="span",
                attrs={"class": current_class, "aria-current": "page"},
                children=tuple(body),
            )
        attrs: dict[str, Any] = {"class": item_class}
        if self._href:
            attrs["href"] = str(self._href)
        return Element(
            tag="a" if self._href else "span",
            attrs=attrs,
            children=tuple(body),
        )

    def render(self) -> Element:
        """Outside a ``Breadcrumb``, a segment renders its content
        WITHOUT the parent's classes, rather than raising: it is its
        peers' contract (``Tab``, ``Step``, ``TreeNode`` render empty
        outside their parent), and raising at render would break a page
        for a composition mistake no unit test sees."""
        return self._render_segment(
            is_last=False, item_class="", current_class=""
        )


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────


def _normalise_item(item: Any) -> tuple[Any, str | None, Any]:
    """Coerce a breadcrumb entry into ``(label, href, icon)``.

    Accepts dicts (``{"label", "href", "icon"}``), tuples
    (``(label, href)`` or ``(label,)``), or a bare string (label only,
    with no link).

    ``icon`` only exists on the dict form: it is what lets the ``items=``
    shortcut express EVERYTHING the children express. Without it, the
    API's two tiers would diverge as soon as you want an icon — and
    ``test_items_shortcut_materialises_the_same_children`` would have
    nothing left to compare.
    """
    if isinstance(item, dict):
        return item.get("label", ""), item.get("href"), item.get("icon")
    if isinstance(item, tuple):
        if len(item) >= 2:
            return item[0], item[1], None
        if len(item) == 1:
            return item[0], None, None
    if isinstance(item, str):
        return item, None, None
    raise ComponentUsageError(
        f"Unsupported breadcrumb item shape : {type(item).__name__}"
    )


def _render_separator(
    separator: str | Component, separator_class: str, owner: Component
) -> Element:
    """Render a single separator node between two items.

    Strings shorter than 3 chars (``"/"``, ``"›"``, ``">"``) are
    treated as literal text ; longer strings are assumed to be
    Iconify names and wrapped in an :class:`Icon`. Caller can also
    pass a pre-built :class:`Component` for full control.
    """
    if isinstance(separator, Component):
        Component._detach_from_parent(separator)
        node = separator.render()
        if isinstance(node, Element):
            return Component.with_slot_class(
                node, separator_class, **{"aria-hidden": "true"}
            )
        return Element(
            tag="span",
            attrs={"class": separator_class, "aria-hidden": "true"},
            children=(node,),
        )

    # A bound separator follows the client value; its SERVER value
    # decides text vs icon, as for a plain string.
    bound = separator if isinstance(separator, ClientBinding) else None
    text = str(bound.value if bound is not None else separator)
    if len(text) <= 2:
        return Element(
            tag="span",
            attrs={"class": separator_class, "aria-hidden": "true"},
            children=(
                owner.emit_text_slot(bound) if bound is not None
                else TextNode(text),
            ),
        )

    # Iconify name — wrap in an Icon, render, stamp the slot class. A
    # binding goes to the Icon as is: it emits the live ``bz-attr:icon``.
    icon = Icon(bound if bound is not None else text, size="xs")
    Component._detach_from_parent(icon)
    rendered = icon.render()
    existing = rendered.attrs.get("class", "")
    return Element(
        tag=rendered.tag,
        attrs={
            **rendered.attrs,
            "class": (
                f"{separator_class} {existing}".strip()
                if existing
                else separator_class
            ),
            "aria-hidden": "true",
        },
        children=rendered.children,
    )


__all__ = ["Breadcrumb"]


