"""``Viewport`` — the frame that takes the screen and never scrolls.

A box exactly the size of the window, **outside the document's flow**.
It does not scroll because it never overflows; it is its regions
(:class:`~bretzel.components.layout.pane.Pane`) that scroll.

The model it declares
----------------------
Writing ``ui.viewport()`` is choosing the "frozen document, inner boxes
that scroll" model — the tools' one (VS Code, Slack) — rather than
"fixed chrome, document that scrolls" — the web pages' one (Mantine
``AppShell``, shadcn ``Sidebar``). Bretzel keeps the second by DEFAULT: a
page with no shell scrolls normally, without anybody writing anything.
The first is obtained here, explicitly.

It is Quasar's answer to the same problem: window layout by default,
``container`` mode on request.

What the frozen model gives, and what it costs
------------------------------------------------
It gives N **independently** scrolling regions — a master-detail, kanban
columns, a message thread next to a list — and a side-bar collapse
absorbed by flexbox, with no channel to wire between the bar and the
content.

It costs a continuous chain of heights from the root to the region, and
it is a SILENT cost: a missing link does not raise, it clips or it
grows. Cf. ``Pane``'s docstring.

Where you write it
-------------------
Two shapes, and there is no third: an application shell (eight in
``examples/``), and a full-screen page with no layout —
``examples/crm/features/login.py``, which has neither a bar nor an
outlet because nobody is signed in yet to be entitled to one.

A sign-in page must be able to scroll on a small phone: that asks for NO
prop, it composes — a ``Viewport`` that does not scroll, containing a
``Pane`` that does.

"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import reactive_prop
from bretzel.components.layout.flex.flex import Flex
from bretzel.components.layout.viewport.theme import VIEWPORT_THEME


class Viewport(Flex):
    """Render a full-screen frame whose regions scroll independently."""

    THEME: ClassVar[dict[str, Any]] = VIEWPORT_THEME
    THEME_KEY: ClassVar[str] = "viewport"
    #: "I am a frozen frame." Read by duck typing, like
    #: ``IS_TRANSPARENT_WRAPPER`` right beside it: the reader is
    #: ``base/_wiring.check_sticky_bar_placement``, which judges the
    #: placement of ``sticky`` bars once the tree is built. An
    #: ``isinstance`` would do the same here — the ``base → layout``
    #: import would be acyclic — but a marker remains the repository's
    #: convention for a question asked of a TREE of heterogeneous
    #: objects.
    IS_FROZEN_FRAME: ClassVar[bool] = True

    #: ``row`` — the dominant shape (side bar on the left, content on
    #: the right: eight sites out of nine). ``col`` serves the mobile
    #: shell, top bar then content. The two **co-occur in the same app**:
    #: a demo app since removed had both shells, chosen by
    #: ``if Screen().is_mobile``. That is what earns the prop its place
    #: where ``ui.vstack`` / ``ui.hstack`` lost theirs.
    direction: Any = reactive_prop(default="row", emit_attr=False)
    #: ``stretch`` — a frame's regions fill the cross axis.
    #: ``ui.hstack``'s ``center`` default reduced the right panel to its
    #: content's height and deprived the outlet of any scrolling
    #: container; the shells therefore wrote ``align="stretch"`` by hand,
    #: with the comment explaining why.
    align: str = reactive_prop(default="stretch", emit_attr=False)
    #: ``none`` — a frame juxtaposes regions, it does not space them.
    #: All nine sites wrote ``gap="none"``.
    gap: Any = reactive_prop(default="none", emit_attr=False)

    def __init__(
        self,
        *,
        direction: str | dict | None = None,
        align: str | None = None,
        gap: str | dict | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            direction=direction, align=align, gap=gap, **kwargs
        )
