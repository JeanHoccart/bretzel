"""``Dropzone`` — a region that receives dragged items.

    with ui.dropzone(name="todo", accepts=["task"], on_move=reorder):
        for t in ui.drag_each(store.todo, group="task"):
            ui.card(t.title)

The component emits a **DOM contract** and nothing else : the gesture
lives in ``runtime/_src/19_dnd.js``, delegated from the document, so a
zone works the moment its attributes are in the page — including after a
morph, which is why no per-zone listener is wired here.

**Two orthogonal doors**, the distinction the framing insists on :

- ``accepts=`` decides what may come IN. **Omitted does not mean
  « anything »** : an undeclared zone receives only its OWN items, so a
  plain list reorders itself and never catches a card from an unrelated
  list on the same page. Receiving from elsewhere is an opt-in. Same
  default as Sortable.js, and the playground bench proved it necessary —
  with « omitted = anything », grabbing a kanban card lit up every
  unrelated zone on the page.
- ``locked=`` decides whether anything may go OUT. A trash zone accepts
  everything and lets nothing leave.

Conflating them into one « locked » boolean would have made the trash
un-expressible, which is exactly the case the framing names.

- ``holds=`` says HOW MANY the zone holds. ``"many"`` is the default and
  is not written: the drop INSERTS, and the gesture slides the card into
  place during the hover. ``holds="one"`` says a single occupant fits —
  a chair in a seating plan, a slot. The gesture then stops dropping the
  card there (the zone would hold two for the duration of the hover, it
  would open, and everything around would shift) and marks the target as
  OVERWRITABLE. The drop still goes to the handler, with ``to_zone`` on
  the target and ``to_index`` at zero: it is the handler that swaps or
  refuses.

  ⚠️ The zone declares its CARDINALITY, never the drop's effect. A
  ``drop="replace"`` would put a second authority beside the handler,
  and nothing would catch the disagreement if one inserts while the
  other announces a replacement.

**What the gesture SHOWS, and where that is set.** By default the card
in flight keeps its size: the landing zone opens by the height of a
card. The other convention — a thin placeholder, à la
react-beautiful-dnd — is obtained by overriding ``draggable``'s
``dragging`` slot, which documents the ``data-bz-drag-axis`` published
for that. It is a taste, so it is in the theme and not in a prop.

**There is no ``can_drop=``.** Refusing is the handler doing nothing :
the runtime restores the position if the drop's marker survives the
response, even when the handler causes no new render.

**Why the handler hangs off a hidden carrier and not the root.** A ``div``
carries neither ``name``/``value`` nor a native ``change``, so the payload
needs a form control — the same reason Tabs, Accordion and Pagination each
post one. Here the carrier's ``name`` is not the caller's business : it is
``Move.WIRE_FIELD``, the field the runtime writes and the injection rule
reads. That is the one case where hard-coding the name is right.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import pop_change_handler as _pop_change_handler
from bretzel.components.layout.dropzone.move import MOVE_WIRE_FIELD
from bretzel.components.layout.dropzone.theme import DROPZONE_THEME
from bretzel.core.tree import Element


class Dropzone(Component):
    """Render a drop target whose ``on_move`` handler receives a typed ``Move``."""

    THEME: ClassVar[dict[str, Any]] = DROPZONE_THEME
    THEME_KEY: ClassVar[str] = "dropzone"
    # Nothing here is a client-bindable value : a zone holds no value, it
    # reports events. ``visible=`` remains available as a universal.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    EVENTS: ClassVar[tuple[str, ...]] = ("move",)

    color: str = reactive_prop(default="primary", emit_attr=False)
    locked: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        *,
        name: str | None = None,
        accepts: Iterable[str] | None = None,
        holds: str | None = None,
        locked: bool | None = None,
        color: str | None = None,
        on_move: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(color=color, locked=locked, on_move=on_move, **kwargs)
        self._name = name
        self._holds = holds
        # Materialised at construction : ``accepts`` may legitimately be a
        # generator from a comprehension, and ``render()`` must stay
        # re-runnable (a refresh re-renders the same instance).
        self._accepts = tuple(accepts) if accepts is not None else None

    def _needs_identity(self) -> bool:
        """Always — a zone must be NAMEABLE, even with no handler.

        ``name=``'s fallback is the stable id. With no rendered identity,
        a zone that has neither ``name=`` nor ``on_move=`` comes out with
        ``data-bz-dropzone=""`` — and it can perfectly well stay a
        SOURCE: dragging an item from it to a named zone posts a ``Move``
        whose ``from_zone`` is ``""``. With two anonymous zones on the
        page, the handler can no longer say where the item comes from, so
        any "remove it from the source" aims at the wrong list.
        """
        return True

    def render(self) -> Element:
        locked = bool(self._reactive_values.get("locked"))

        attrs = self.emit_attrs()

        # The zone's identity as the handler will read it. Falls back to the
        # stable component id so a single-zone reorder — where nobody looks
        # at ``from_zone`` — needs no ``name=`` at all.
        zone_name = self._name or str(attrs.get("id") or "")
        attrs["data-bz-dropzone"] = zone_name
        if self._accepts is not None:
            attrs["data-bz-accepts"] = ",".join(self._accepts)
        if locked:
            attrs["data-bz-locked"] = "true"
        # ⚠️ ``one`` only: ``many`` is the default and has nothing to
        # write. An attribute set to say "as usual" weighs down every
        # zone on the page without any selector reading it.
        if self._holds == "one":
            attrs["data-bz-holds"] = "one"

        # Through the COMPOSER, never through ``theme["slots"][…]``
        # directly: it is the composer that makes a caller's
        # ``slots={"root": …}`` land. A hand-made lookup drops that
        # override IN SILENCE — the defect measured on ToggleGroup,
        # written in ``slot_class``'s docstring. Both my components
        # reproduced it.
        attrs["class"] = " ".join(
            part for part in (
                self.compose_class("root", ),
                self.slot_class("valid"),
                self.slot_class("replace") if self._holds == "one" else "",
            ) if part
        ).strip()

        # The server handler moves from the root onto the carrier : HTMX
        # must post from the element that *carries the payload*, or the
        # blob the runtime just wrote would not be serialised into the
        # request.
        relocated = _pop_change_handler(attrs)

        children = list(self._render_children())
        # ⚠️ **The carrier is unconditional**, even with no server handler.
        # It is what the runtime writes the payload into and what it
        # dispatches ``move`` from ; rendering it only for the server case
        # would make a client-only ``on_move="…"`` a dead letter — the
        # event would have nothing to fire from, and the string shape is
        # part of the declared surface (cf. traps.md § "``EVENTS = (...)``
        # + an ``on_X=`` kwarg ≠ an event that fires"). The event bubbles,
        # so the root's ``bz-on:move`` catches it.
        carrier_attrs: dict[str, Any] = {
            "type": "hidden",
            "data-bz-move-carrier": "true",
            "class": self.slot_class("carrier"),
            **relocated,
        }
        # ``name`` ONLY when a server handler will post it. An unconditional
        # name would inject ``bz_move=`` into every enclosing form — the
        # exact parasitic-field trap ``hidden_carrier_attrs`` documents for
        # Tabs and Accordion.
        if relocated:
            carrier_attrs["name"] = MOVE_WIRE_FIELD
        children.append(Element(tag="input", attrs=carrier_attrs, children=()))

        return Element(tag=self._tag, attrs=attrs, children=children)
