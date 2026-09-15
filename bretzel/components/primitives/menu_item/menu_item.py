"""``MenuItem`` — shared base for clickable menu rows.

One clickable row : ``icon_left`` + ``label`` + ``icon_right`` + optional
right-aligned ``shortcut``, colour-tinted via ``color``, rendered as
``<button>`` (default) or ``<a>`` (when ``href`` given). On click it
dispatches a bubbling ``bz-dropdown-pick`` CustomEvent so the enclosing
menu closes itself.

Concrete subclasses set ``THEME`` + ``THEME_KEY`` and nothing else —
:class:`~bretzel.components.overlay.dropdown.DropdownItem` and
:class:`~bretzel.components.navigation.sidebar.SidebarFooterItem` are thin
shells so the row logic lives in ONE place (primitives/, importable by any
group — no cross-group cycle, anti-règle 5).

Theme contract — the subclass theme must expose slots ``root`` /
``icon_left`` / ``label`` / ``icon_right`` / ``shortcut`` and a ``colors``
map (semantic → tint classes).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import bool_attr
from bretzel.core.tree import Element, Node

# The bubbling event every menu row fires on click ; the enclosing menu panel
# listens (``bz-on:bz-dropdown-pick``) and flips its open flag. Generic despite
# the Dropdown-flavoured name.
MENU_PICK_EVENT = "bz-dropdown-pick"


class MenuItem(Component):
    """Base clickable menu row. Subclasses provide ``THEME``/``THEME_KEY``."""

    DEFAULT_TAG: ClassVar[str] = "button"
    IS_CONTAINER: ClassVar[bool] = False
    EVENTS: ClassVar[tuple[str, ...]] = ("click",)
    # Curated reactive surface — disabled (item locked). color is design-time.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("disabled",)

    color: str | None = reactive_prop(default=None, emit_attr=False)
    disabled: bool = reactive_prop(default=False)

    def __init__(
        self,
        *,
        label: str | Component | None = None,
        icon_left: str | Component | None = None,
        icon_right: str | Component | None = None,
        shortcut: str | None = None,
        href: str | None = None,
        color: str | None = None,
        disabled: bool | None = None,
        on_click: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            color=color, disabled=disabled, on_click=on_click, **kwargs
        )
        # ``label=`` et ``shortcut=`` sont des slots textuels : ils
        # acceptent ``str | ClientBinding | Component``. ``adopt_slot``
        # détache un Component pour qu'il ne rende pas AUSSI tout seul
        # dans la portée environnante.
        self._label = Component.adopt_slot(label)
        self._href = href
        self._shortcut = Component.adopt_slot(shortcut)
        # String icon shortcuts (``icon_left="pencil"`` → ``Icon("pencil")``)
        # ; adopt_slot wraps + detaches from the active parent.
        self._icon_left: Component | None = Component.adopt_slot(
            icon_left, icon_shortcut=True
        )
        self._icon_right: Component | None = Component.adopt_slot(
            icon_right, icon_shortcut=True
        )

    @staticmethod
    def _slotted_icon(icon: Component, slot_class: str) -> Element:
        """Render an icon component and prepend the slot class to it."""
        ic = icon.render()
        return Element(
            tag=ic.tag,
            attrs={
                **ic.attrs,
                "class": f"{slot_class} {ic.attrs.get('class', '')}".strip(),
            },
            children=ic.children,
        )

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        colors = theme.get("colors", {})

        # Always tint — a plain row uses the ``neutral`` entry, a coloured one
        # its semantic tint. Keeping bg states in ``colors`` (not ``root``)
        # means a coloured item's hover wins cleanly, no same-layer clash.
        color = self._reactive_values.get("color")
        color_cls = colors.get(color or "neutral", "")

        children: list[Node] = []
        if self._icon_left is not None:
            children.append(
                self._slotted_icon(self._icon_left, slots.get("icon_left", ""))
            )
        if isinstance(self._label, Component):
            # Un Component garde sa propre racine — l'envelopper dans le
            # span du slot ``label`` lui imposerait la typo de la ligne,
            # ce qu'un contenu riche vient justement remplacer.
            children.append(self._label.render())
        else:
            # ``emit_text_slot`` renvoie ``None`` pour ``None`` ET pour la
            # chaîne vide — un seul garde couvre les deux, d'où l'absence
            # de ``if self._label is not None`` autour de ce bloc.
            label_node = self.emit_text_slot(self._label)
            if label_node is not None:
                children.append(
                    Element(
                        tag="span",
                        attrs={"class": slots.get("label", "")},
                        children=(label_node,),
                    )
                )
        if self._icon_right is not None:
            children.append(
                self._slotted_icon(self._icon_right, slots.get("icon_right", ""))
            )
        shortcut_node = self.emit_text_slot(self._shortcut)
        if shortcut_node is not None:
            children.append(
                Element(
                    tag="span",
                    attrs={"class": slots.get("shortcut", "")},
                    children=(shortcut_node,),
                )
            )

        # base row + optional colour tint ; ``classes=`` posé par le wrap
        # métaclasse — pas ici (doublon).
        root_class = " ".join(
            p for p in (slots.get("root", ""), color_cls) if p
        )

        attrs = self.emit_attrs()
        attrs["class"] = root_class
        attrs.setdefault("role", "menuitem")

        disabled = bool(self._reactive_values.get("disabled"))
        disabled_binding = self._binding_metadata.get("disabled")
        if disabled_binding is not None:
            # ⚠️ Le chemin RÉACTIF. Tout ce que fait la branche statique
            # ci-dessous se décide À LA CONSTRUCTION, donc jamais quand
            # ``disabled`` est piloté par une binding : la valeur au rendu
            # vaut ``False``, la branche n'est pas prise, et l'émission
            # automatique posait ``bz-attr:disabled`` sur un ``<a>`` — un
            # attribut qui n'existe pas sur une ancre, donc rien du tout.
            # Mesuré le 2026-08-13 : ``ui.dropdown_item(disabled=binding)``
            # gardait son ``href``, son ``bz-on:click`` et son apparence
            # d'entrée active.
            #
            # La réécriture en ``aria-disabled`` est ce qui répare les
            # TROIS moitiés d'un coup : le thème habille déjà l'état via
            # ses variantes ``aria-disabled:``, un lecteur d'écran
            # l'annonce, et le socle runtime en dérive l'inertie
            # (``$bz._inert``) — clic, navigation et action serveur.
            path = self.path_of(disabled_binding)
            attrs.pop("bz-attr:disabled", None)
            attrs["bz-attr:aria-disabled"] = bool_attr(path)
            attrs["bz-attr:tabindex"] = f"({path}) ? '-1' : null"
        if disabled:
            # A disabled row must announce itself to AT AND show
            # ``cursor-not-allowed`` on hover. Both rule out native
            # ``disabled`` <button> and ``pointer-events-none`` — each drops
            # every pointer event, so the not-allowed cursor never paints. Go
            # aria-only, keep the hit-test LIVE, and strip the interaction
            # wiring here instead. ``tabindex=-1`` pulls it from the tab order.
            attrs["aria-disabled"] = "true"
            attrs["tabindex"] = "-1"
            attrs.pop("disabled", None)  # native disabled would kill the cursor
            # Drop every wired handler (server ``hx-post`` + HMAC stamp AND
            # client ``bz-on:`` expressions) — ``_event_attrs`` is exactly
            # that set — so a live-hit-test row still does nothing on click.
            for key in self._event_attrs:
                attrs.pop(key, None)
        else:
            # Close the enclosing menu on click — append to any client click
            # handler, coexist with a server ``hx-post``.
            existing_click = attrs.get("bz-on:click")
            close_dispatch = f"$dispatch('{MENU_PICK_EVENT}')"
            attrs["bz-on:click"] = (
                f"{existing_click}; {close_dispatch}"
                if existing_click else close_dispatch
            )

        if self._href:
            # ``disabled`` links carry no ``href`` (inert), enabled ones do.
            if not disabled:
                attrs["href"] = self._href
            return Element(tag="a", attrs=attrs, children=tuple(children))
        # Seulement si la balise est encore un bouton. ``type`` posé ici
        # et pas par ``emit_attrs`` — donc hors de portée du garde-fou
        # central — atterrissait tel quel sur un ``tag=`` personnalisé,
        # où il désigne un type MIME. Gaté par
        # ``test_a_changed_tag_drops_what_it_cannot_carry``.
        if self._tag == "button":
            attrs.setdefault("type", "button")
        return Element(tag=self._tag, attrs=attrs, children=tuple(children))
