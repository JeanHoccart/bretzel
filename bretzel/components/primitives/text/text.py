"""``Text`` — typographic primitive (Archetype 1, leaf).

Polymorphic over the underlying HTML tag (``span`` by default) so the
same component covers paragraphs, labels, captions, helper text, etc.
without dragging variant-bloat.

"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.primitives.text.theme import TEXT_THEME
from bretzel.core.tree import Element, TextNode
from bretzel.state.scopes.client import ClientBinding


class Text(Component):
    """Inline / block text with typographic modifiers.

    Pure leaf : no children, no `with` block. Pass the text as a
    positional argument or via ``text=``. Tag defaults to ``span``
    so the element drops cleanly inside another flow ; switch to
    ``"p"`` for paragraphs, ``"label"`` for form labels, etc.
    """

    THEME: ClassVar[dict[str, Any]] = TEXT_THEME
    THEME_KEY: ClassVar[str] = "text"
    DEFAULT_TAG: ClassVar[str] = "span"
    IS_CONTAINER: ClassVar[bool] = False
    # Curated reactive surface — only the text text. Visual axes
    # (size / weight / color / align / italic / decoration / truncate)
    # are design-time. ``text`` is the first positional arg.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("text",)

    # All default to ``None`` so a bare ``ui.text("hi")`` carries only the
    # slot's base classes ; modifiers appear only when opted in. All cosmetic
    # (consumed by ``_compose_classes``) → ``emit_attr=False`` keeps them off
    # the DOM.
    size: str | None = reactive_prop(default=None, emit_attr=False)
    weight: str | None = reactive_prop(default=None, emit_attr=False)
    align: str | None = reactive_prop(default=None, emit_attr=False)
    italic: bool | None = reactive_prop(default=None, emit_attr=False)
    decoration: str | None = reactive_prop(default=None, emit_attr=False)
    truncate: bool | None = reactive_prop(default=None, emit_attr=False)
    color: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        text: Any = None,
        *,
        size: str | None = None,
        weight: str | None = None,
        align: str | None = None,
        italic: bool | None = None,
        decoration: str | None = None,
        truncate: bool | None = None,
        color: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            size=size,
            weight=weight,
            align=align,
            italic=italic,
            decoration=decoration,
            truncate=truncate,
            color=color,
            **kwargs,
        )
        # Static strings, ClientBindings, ClientExpressions and Components all
        # pass through verbatim — ``render()`` decides how to emit each shape.
        # ``adopt_slot`` detaches a Component so it doesn't ALSO render as a
        # sibling. We skip ``text or ""`` because ``ClientBinding.__bool__``
        # raises (it would freeze a reactive value at server-render time).
        self._text = "" if text is None else Component.adopt_slot(text)

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        cls_string = self._compose_classes()
        attrs: dict[str, Any] = self.emit_attrs()
        # ``emit_attrs`` already drops ``None`` values so the modifier
        # props don't surface as bare HTML attrs ; only ``class`` needs
        # to be added explicitly.
        if cls_string:
            attrs = {**attrs, "class": cls_string}

        # Reactive text : emit ``bz-text`` (textContent effect), NOT
        # ``bz-attr:textContent``. Browsers lowercase HTML attributes
        # (``textContent`` → ``textcontent``), so setAttribute would create an
        # inert custom attr and leave the span visually empty. ``bz-text``
        # writes the property directly. ``ClientExpression`` IS a
        # ``ClientBinding`` subclass — the check below covers both, and
        # ``path_of`` resolves each to its full JS expression.
        if isinstance(self._text, ClientBinding):
            attrs = {**attrs, "bz-text": self.path_of(self._text)}
            children: tuple[Any, ...] = ()
        elif isinstance(self._text, Component):
            # Universal contract : every text slot accepts a Component too.
            # ``adopt_slot`` (in __init__) already detached it, so rendering
            # it here is the only owner.
            children = (self._text.render(),)
        else:
            children = (TextNode(str(self._text)),)

        return Element(tag=self._tag, attrs=attrs, children=children)

    # ── Class composition ──────────────────────────────────────────────

    def _compose_classes(self) -> str:
        """Text has more axes than the default variant/size/modifiers
        pattern (weight, align, decoration, italic, truncate, color),
        so we don't reuse :py:meth:`Component.compose_class` directly —
        we still pull the theme + template-resolver from the base and
        apply Text's specific lookups on top.
        """
        theme = self._resolved_theme()
        parts: list[str] = []

        root = theme.get("slots", {}).get("root")
        if root:
            parts.append(root)

        for axis, prop in (
            ("sizes", "size"),
            ("weights", "weight"),
            ("alignments", "align"),
            ("decorations", "decoration"),
        ):
            value = self._reactive_values.get(prop)
            if value and value in theme.get(axis, {}):
                parts.append(theme[axis][value])

        # ``text-align`` only shows on a block-level box wider than its
        # text — on the default inline ``<span>`` (or as a flex item
        # that shrinks to text) it's a silent no-op, the text just
        # sits wherever the parent puts it. So when the caller opts into
        # an explicit alignment, promote the element to a full-width
        # block so the alignment is actually observable. ``block w-full``
        # is idempotent on a tag that's already block-level (``tag="p"``).
        align = self._reactive_values.get("align")
        if align and align in theme.get("alignments", {}):
            parts.append("block w-full")

        modifiers = theme.get("modifiers", {})
        if self._reactive_values.get("italic"):
            parts.append(modifiers.get("italic", "italic"))
        if self._reactive_values.get("truncate"):
            parts.append(modifiers.get("truncate", "truncate"))

        color = self._reactive_values.get("color")
        if color:
            template = modifiers.get("color")
            if template:
                parts.append(template)

        # ``classes=`` set by the metaclass wrap — not here (duplicate).
        return " ".join(p for p in parts if p).strip()
