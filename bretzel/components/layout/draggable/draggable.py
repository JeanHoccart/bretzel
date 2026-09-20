"""``Draggable`` — one grabbable item inside a :class:`Dropzone`.

    with ui.dropzone(name="todo", on_move=reorder):
        for t in ui.each(store.todo):
            with ui.draggable():
                ui.card(t.title)

``ui.drag_each`` is the sugar for that loop and is what app code normally
writes ; this component is what it wraps each item in.

**``key=`` is optional because ``each`` already provides one.** Every
component holding client state reads ``current_iteration_key()`` when its
own ``key=`` is absent, and this is no different — the key it reports as
``Move.item_key`` is the iteration key by default. Passing ``key=``
explicitly is the escape hatch for a hand-rolled loop, not the norm.

**``disabled=`` means « cannot be PICKED UP », not « cannot be MOVED ».**
The distinction is not pedantry — it is the first question a reader asks,
and the two are different features. A disabled card cannot be grabbed, but
dragging one of its neighbours past it still changes its index : that is
what reordering a list *is*, and no amount of locking one item changes
where it sits once the item above it leaves. Same semantics as
Sortable.js's ``filter`` and dnd-kit's ``disabled``.

If an item must keep its *position* — a header row, a pinned task — that
is a different prop that does not exist yet, and it is not free : list
semantics have no notion of an index that cannot be written, so
« insert at index 1 » would need an answer when index 1 is pinned.
Ask for it before assuming ``disabled`` covers it.

**``handle=True`` is a restriction, not the gesture.** By default the whole
item grabs, with the activation the runtime decides per pointer type
(movement threshold on a mouse, press-and-hold on touch). A handle exists
for the case where the item itself contains something interactive — a link,
a checkbox — that would fight the drag. When it is on, ``touch-action:
none`` moves from the item onto the handle, so the rest of the card stays
scrollable under a finger.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.layout.draggable.theme import DRAGGABLE_THEME
from bretzel.core.tree import Element
from bretzel.render import text
from bretzel.render.iteration import current_iteration_key

#: Six-dot grip. Inline SVG rather than ``ui.icon`` : the handle must
#: render identically whether or not an icon set is configured, and it is
#: the only glyph this component ever draws.
_GRIP_SVG = (
    '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" '
    'fill="currentColor" focusable="false">'
    '<circle cx="6" cy="4" r="1.4"/><circle cx="10" cy="4" r="1.4"/>'
    '<circle cx="6" cy="8" r="1.4"/><circle cx="10" cy="8" r="1.4"/>'
    '<circle cx="6" cy="12" r="1.4"/><circle cx="10" cy="12" r="1.4"/>'
    "</svg>"
)


class Draggable(Component):
    """A grabbable wrapper around one item of a dropzone."""

    THEME: ClassVar[dict[str, Any]] = DRAGGABLE_THEME
    THEME_KEY: ClassVar[str] = "draggable"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    color: str = reactive_prop(default="primary", emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        *,
        key: str | None = None,
        group: str | None = None,
        handle: bool = False,
        disabled: bool | None = None,
        color: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(color=color, disabled=disabled, **kwargs)
        self._key = key
        self._group = group
        self._handle = handle

    def _needs_identity(self) -> bool:
        """Always — and for a reason none of the base triggers cover.

        The inherited rule emits ``id``/``bz-id`` when *the runtime* has to
        find the element again (a binding to patch, a handler to dispatch).
        A draggable has neither : it holds no client state and wires no
        event of its own.

        It needs identity for **idiomorph**. The gesture moves the real
        node, so when the server re-renders the list the morph must PAIR
        the moved node rather than replace it — otherwise every drop
        destroys the card's subtree, and with it any open menu, focus or
        in-flight animation it contained. Idiomorph pairs on ``id``, so an
        anonymous draggable silently degrades to teardown-and-rebuild.
        Measured and gated by
        ``tests/runtime_js/test_morph_preserves_reordered_nodes.py``, whose
        whole premise is that the nodes carry ids.
        """
        return True

    def render(self) -> Element:
        color = self._reactive_values.get("color") or "primary"
        disabled = bool(self._reactive_values.get("disabled"))

        attrs = self.emit_attrs()
        attrs["data-bz-draggable"] = "true"
        # Explicit ``key=`` wins ; otherwise the enclosing ``each`` loop's
        # key ; otherwise the stable component id, so a hand-written item
        # outside any loop still reports something the handler can match.
        attrs["data-bz-key"] = (
            self._key or current_iteration_key() or str(attrs.get("id") or "")
        )
        if self._group:
            attrs["data-bz-group"] = self._group
        if disabled:
            attrs["data-bz-disabled"] = "true"
            # ``data-bz-disabled`` drives the RUNTIME; it says nothing
            # to a screen reader. The root is a ``<div>``, so nothing is
            # announced for free — without this line, a locked card
            # presents itself like any other. It is
            # ``test_disabled_affordance``'s invariant, whose list of
            # cases is written by hand and did not include me.
            attrs["aria-disabled"] = "true"

        # Through the COMPOSER (cf. the twin comment in dropzone.py): a
        # ``theme["slots"][…]`` read by hand silently drops a caller's
        # ``slots=``.
        parts = [
            self.compose_class("root", ),
            self.slot_class("dragging"),
        ]
        if self._handle:
            attrs["data-bz-handle"] = "true"
            parts.append(self.slot_class("with_handle"))
        else:
            # Only the grabbing surface may swallow touch gestures.
            parts.append(self.slot_class("grab_all"))
        if disabled:
            parts.append(self.slot_class("disabled"))
        attrs["class"] = " ".join(p for p in parts if p).strip()

        children = list(self._render_children())
        if self._handle and not disabled:
            # The body is wrapped so the grip stays a fixed-width sibling
            # and the content takes the rest of the row.
            children = [
                self._grip(color),
                Element(
                    tag="div",
                    attrs={"class": self.slot_class("handle_body")},
                    children=children,
                ),
            ]

        return Element(tag=self._tag, attrs=attrs, children=children)

    def _grip(self, color: str) -> Element:
        """The grip, focusable so the affordance is not mouse-only.

        ``tabindex=0`` costs nothing today and is what a future keyboard
        reorder would bind to ; more immediately it is what lets a screen
        reader announce that the row is movable at all.
        """
        from bretzel.core.tree import HtmlNode

        return Element(
            tag="span",
            attrs={
                "data-bz-drag-handle": "true",
                "class": self.slot_class("handle"),
                "role": "button",
                "tabindex": "0",
                "aria-label": text("draggable.reorder"),
            },
            children=(HtmlNode(_GRIP_SVG),),
        )
