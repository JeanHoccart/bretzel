"""``Pane`` — the region that scrolls.

A column that takes its parent's remaining room and scrolls when its
content exceeds it. That is all it does, and it is deliberately little:
what justifies the component is not the number of classes it saves, it
is that **two of them cannot be guessed** — cf. the theme, which carries
both measurements.

Where you write it
-------------------
Anywhere a zone must scroll while its neighbours stay put. Measured on
the repository as of 2026-08-23: seventeen sites, thirteen apps, and
**four outside a shell** — ``examples/chat``'s message thread,
``examples/crm``'s two master-detail columns (list + record), a pipeline
column. So it is not shell furniture.

What it expects from its parent
--------------------------------
A height. Either because it is a flex column with a defined height
(``ui.viewport``, an ``h-full`` card), or because it has a height itself
(a ``ui.resizable_panel``). With no height anywhere above, ``h-full``
does not resolve, ``flex-1`` has nothing to share, and the pane grows
instead of scrolling — silently. It is the "frozen document" model's
known constraint (Quasar documents it the same way for its ``container``
mode).

In a BLOCK parent, it takes the whole height: it must then be the only
child. A header sibling would overflow, for want of remaining space to
compute — it is a property of the block, not of the component.

Why no ``wrap``
----------------
:class:`VStack` exposes it, it does not. A column that scrolls does not
wrap — and ``wrap`` is very exactly the prop that produced finding [4]
(an item whose basis is 100 % can never share a wrapped line).

"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import reactive_prop
from bretzel.components.layout.pane.theme import PANE_THEME
from bretzel.components.layout.stack import VStack


class Pane(VStack):
    """Render a scrolling column that occupies the remaining space."""

    THEME: ClassVar[dict[str, Any]] = PANE_THEME
    THEME_KEY: ClassVar[str] = "pane"

    #: ``direction`` comes from :class:`VStack` (a pane is a column);
    #: ``wrap`` is sealed here. Declare rather than keep quiet: an
    #: inherited prop refused at the call would be announced as usable by
    #: ``bretzel describe``, and the reader would take a ``TypeError``.
    SEALED_PROPS: ClassVar[tuple[str, ...]] = ("direction", "wrap")
    SEALED_REASONS: ClassVar[dict[str, str]] = {
        "wrap": (
            "ui.pane does not wrap: a column that SCROLLS has no lines "
            "to distribute. It is also the prop that produced finding [4] "
            "— an item whose basis is 100 % can never share a wrapped "
            "line. Put a ui.flex(wrap=True) INSIDE the pane."
        ),
    }

    #: Inner breathing room. ``none`` by default: half the sites do not
    #: want any (a shell puts its padding lower down, around the outlet),
    #: and a non-zero default would be removed more often than set.
    padding: str = reactive_prop(default="none", emit_attr=False)

    def __init__(
        self,
        *,
        gap: str | dict | None = None,
        padding: str | None = None,
        align: str | None = None,
        justify: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            gap=gap, padding=padding, align=align, justify=justify, **kwargs
        )

    def _compose_classes(self) -> str:
        """:class:`Flex`'s classes, plus the ``paddings`` table.

        We extend rather than rewrite: a flex's composition (direction,
        alignment, gap, responsive) is already resolved upstream, and
        duplicating it here would make it diverge at the first change.
        """
        base = super()._compose_classes()
        padding = self._reactive_values.get("padding") or "none"
        extra = self._resolved_theme().get("paddings", {}).get(padding, "")
        return f"{base} {extra}".strip() if extra else base
