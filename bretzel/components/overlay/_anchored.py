"""Le rendu commun des overlays ANCRÉS — ``Dropdown`` et ``Popover``.

Le frère de ``_modal`` : même famille de composants, autre mécanique. Un
overlay ancré n'a ni backdrop ni verrou de scroll ; son panneau est
téléporté dans ``<body>`` puis positionné par ``$bz.helpers.floating``
contre le déclencheur.

Ce que la mesure a montré
--------------------------
Le 2026-08-19 : ``Dropdown.render`` = 99 lignes, ``Popover.render`` =
103, **75 identiques (75 %)**. Les deux fichiers importaient exactement
les onze mêmes helpers de ``base/_wiring``, dans le même ordre. La
différence tient en quatre valeurs :

======================  ==============  ==============
                        Dropdown        Popover
======================  ==============  ==============
alignement par défaut   ``start``       ``center``
``role`` du panneau     ``menu``        ``dialog``
``aria-haspopup``       ``menu``        ``dialog``
fermeture au choix      ``bz-dropdown-pick``  —
======================  ==============  ==============

⚠️ Comme pour ``_modal``, le reste de l'écart n'était pas du code mais
des **commentaires** : le piège des refs d'overlay lié (sans scope
propre, le panneau téléporté remonte au ``rootScope`` partagé où tous
les ``bztrigger`` se marchent dessus, et le panneau s'ancre au
déclencheur d'un AUTRE overlay) y était expliqué deux fois, dans deux
formulations. Un piège documenté deux fois est un piège qu'on corrigera
une fois.

Ce qui reste chez l'appelant
-----------------------------
Les chaînes de style : elles arrivent **déjà composées**
(`feedback_no_shared_style_tokens`), ce module ne lit jamais un thème.
"""

from __future__ import annotations

from typing import Any

from bretzel.components.base import stamp_display_none
from bretzel.components.base._wiring import (
    anchored_dismiss_init,
    anchored_panel_effect,
    anchored_trigger_wrapper,
    dispatch_root_effect,
    expand_fit_wrapper,
    floating_placement,
    imperative_listeners,
    server_sync_marker,
    teleport_to_body,
    trigger_is_full_width,
)
from bretzel.core.tree import Element, Node


def render_anchored_overlay(
    component: Any,
    *,
    slots: dict[str, str],
    role: str,
    haspopup: str,
    default_align: str,
    close_on_event: str | None = None,
) -> Element:
    """Déclencheur enveloppé + panneau téléporté + racine câblée.

    ``close_on_event`` sert la seule chose qu'un dropdown a en plus : ses
    items dispatchent ``bz-dropdown-pick`` en se faisant choisir, et
    c'est ce qui referme le menu. L'expression d'ouverture est calculée
    ICI (binding ou drapeau local), donc l'appelant ne peut pas écrire
    l'écouteur lui-même — il nomme l'événement, on le câble.
    """
    position = component._reactive_values.get("position") or "auto"
    align = component._reactive_values.get("align") or default_align
    dismissible = bool(component._reactive_values.get("dismissible"))

    # ── L'état ouvert : ClientBinding ou booléen littéral ─────────────
    # Le binding vit dans ``_binding_metadata`` ; le bool brut reste dans
    # ``_reactive_values`` pour le cas littéral et le SSR.
    open_binding = component._binding_metadata.get("open")
    bound_open = open_binding is not None
    open_expr = open_binding.binding_path() if bound_open else "open"
    initial_open = bool(component._reactive_values.get("open"))

    # ── Panneau ──────────────────────────────────────────────────────
    # Le placement appartient à ``$bz.helpers.floating``, attaché par le
    # ``bz-effect`` du panneau à l'ouverture — aucune classe de position
    # statique.
    panel_attrs: dict[str, Any] = {
        "class": slots.get("panel", ""),
        "role": role,
        "bz-ref": "bzpanel",
        # Bascule d'affichage + attach/detach du flottant, en un effet.
        "bz-effect": anchored_panel_effect(
            open_expr, floating_placement(position, align)
        ),
    }
    if close_on_event:
        panel_attrs[f"bz-on:{close_on_event}"] = f"{open_expr} = false"
    # FOUC : l'effet flottant gère le display, mais on pré-tamponne
    # l'état fermé pour que rien ne peigne en (0,0) avant le boot.
    if not initial_open:
        stamp_display_none(panel_attrs)

    panel = Element(
        tag="div",
        attrs=panel_attrs,
        children=tuple(component._render_children()),
    )

    # ── Déclencheur ──────────────────────────────────────────────────
    trigger_nodes: list[Node] = []
    if component._trigger is not None:
        trigger_nodes.append(
            anchored_trigger_wrapper(
                component._trigger.render(),
                open_expr=open_expr,
                haspopup=haspopup,
            )
        )

    # ── Racine ───────────────────────────────────────────────────────
    # Un déclencheur pleine largeur doit élargir le wrapper ``w-fit``,
    # sinon il se replie sur la largeur du contenu (partagé avec Tooltip).
    attrs = component.emit_attrs()
    root_slot = slots.get("root", "")
    if trigger_is_full_width([component._trigger]):
        root_slot = expand_fit_wrapper(root_slot)
    # ``classes=`` est posé par le wrap métaclasse — pas ici (doublon).
    attrs["class"] = root_slot

    if not bound_open:
        # Un ``open`` backé serveur doit se ré-adopter au refresh
        # (``absorb`` garderait sinon le signal de scope périmé) ; la
        # garde laisse un littéral client tranquille.
        #
        # Le dialecte unique : ``_value_server_backed`` répond « d'où
        # vient ma valeur » (et rend False sur un binding, donc il reste
        # correct même hors de ce ``if``).
        sync = server_sync_marker(
            "open", enabled=component._value_server_backed("open")
        )
        attrs["bz-data"] = (
            "{open: " + ("true" if initial_open else "false")
            + (f",{sync}" if sync else "") + "}"
        )
    else:
        # Lié : le drapeau vit dans le store global, mais la racine a
        # QUAND MÊME besoin de son propre scope (littéral vide) pour que
        # ``bztrigger`` / ``bzpanel`` s'isolent par instance. Sans hôte de
        # scope, ``findScope`` remonte depuis le panneau téléporté
        # jusqu'au ``rootScope`` partagé — où CHAQUE overlay lié
        # enregistre le même ``bztrigger``, dernier arrivé gagne — et le
        # helper flottant ancre le panneau au déclencheur d'un AUTRE
        # overlay, hors écran. Cf. traps.md § « bound overlay ref
        # collision ».
        attrs["bz-data"] = "{}"

    # Dispatch open/close (pas de verrou de scroll pour un panneau
    # ancré), récepteurs de l'API impérative, Échap + clic-dehors : le
    # câblage ancré partagé (``base/_wiring.py``).
    attrs["bz-effect"] = dispatch_root_effect(open_expr)
    attrs.update(imperative_listeners(open_expr))
    if dismissible:
        attrs["bz-init"] = anchored_dismiss_init(open_expr)

    # Le panneau se téléporte dans <body> (cf. ``teleport_to_body``).
    return Element(
        tag=component._tag,
        attrs=attrs,
        children=(
            *trigger_nodes,
            teleport_to_body(panel, component),
            *component._event_carrier_nodes(),
        ),
    )


__all__ = ["render_anchored_overlay"]
