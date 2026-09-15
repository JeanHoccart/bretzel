"""``Dropzone`` — a region that receives dragged items.

    with ui.dropzone(name="todo", accepts=["task"], on_move=reorder):
        for t in ui.drag_each(store.todo, group="task"):
            ui.card(t.title)

The component emits a **DOM contract** and nothing else : the gesture
lives in ``runtime/_src/19_dnd.js``, delegated from the document, so a
zone works the moment its attributes are in the page — including after a
morph, which is why no per-zone listener is wired here.

**Two orthogonal doors**, the distinction the cadrage insists on :

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
un-expressible, which is exactly the case the cadrage names.

- ``holds=`` dit COMBIEN la zone tient. ``"many"`` est le défaut et ne
  s'écrit pas : le dépôt INSÈRE, et le geste glisse la carte à sa place
  pendant le survol. ``holds="one"`` dit qu'un seul occupant tient — une
  chaise d'un plan de classe, un créneau. Le geste cesse alors d'y
  déposer la carte (la zone en porterait deux le temps du survol, elle
  s'ouvrirait, et tout autour se décalerait) et marque la cible comme
  ÉCRASABLE. Le dépôt part quand même au handler, avec ``to_zone`` sur la
  cible et ``to_index`` à zéro : c'est lui qui échange ou refuse.

  ⚠️ La zone déclare sa CARDINALITÉ, jamais l'effet du dépôt. Un
  ``drop="replace"`` mettrait une seconde autorité à côté du handler, et
  rien ne rattraperait le désaccord si l'un insère quand l'autre annonce
  un remplacement.

**Ce que le geste MONTRE, et où ça se règle.** Par défaut la carte en vol
garde sa taille : la zone d'arrivée s'ouvre de la hauteur d'une carte.
L'autre convention — un emplacement fin, à la react-beautiful-dnd —
s'obtient en surchargeant le slot ``dragging`` de ``draggable``, qui
documente le ``data-bz-drag-axis`` publié pour ça. C'est un goût, donc
c'est dans le thème et pas dans une prop.

**There is no ``can_drop=``.** Refusing is the handler doing nothing : the
runtime restaure la position si le marqueur du dépôt survit à la réponse,
même quand le handler ne provoque aucun nouveau rendu.

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
    """A region items can be dragged into, out of, and reordered within.

    ``on_move`` reçoit un paramètre typé :class:`Move`, importé depuis
    ``bretzel.components`` : ``def deposer(m: Move) -> None``. Ses clés
    et index décrivent le déplacement ; le handler retrouve l'objet métier.
    """

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
        """Always — une zone doit être NOMMABLE, même sans handler.

        Le fallback de ``name=`` est l'id stable. Sans identité rendue, une
        zone qui n'a ni ``name=`` ni ``on_move=`` sort avec
        ``data-bz-dropzone=""`` — et elle peut parfaitement rester une
        SOURCE : en tirer un item vers une zone nommée poste un ``Move``
        dont ``from_zone`` vaut ``""``. Avec deux zones anonymes sur la
        page, le handler ne peut plus dire d'où l'item vient, donc tout
        « retire-le de la source » vise la mauvaise liste.
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
        # ⚠️ ``one`` seulement : ``many`` est le défaut et n'a rien à
        # écrire. Un attribut posé pour dire « comme d'habitude » alourdit
        # chaque zone de la page sans qu'aucun sélecteur ne le lise.
        if self._holds == "one":
            attrs["data-bz-holds"] = "one"

        # Par le COMPOSEUR, jamais par ``theme["slots"][…]`` en direct :
        # c'est lui qui fait atterrir un ``slots={"root": …}`` de
        # l'appelant. Un lookup à la main droppe cet override EN SILENCE —
        # le défaut mesuré sur ToggleGroup, écrit dans le docstring de
        # ``slot_class``. Mes deux composants le reproduisaient.
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
        # part of the declared surface (cf. traps.md § « ``EVENTS = (...)``
        # + ``on_X=`` kwarg ≠ event qui fire »). The event bubbles, so the
        # root's ``bz-on:move`` catches it.
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
