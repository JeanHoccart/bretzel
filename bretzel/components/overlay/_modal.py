"""Le rendu commun des deux overlays modaux — ``Dialog`` et ``Drawer``.

Ce que la mesure a montré
--------------------------
Le 2026-08-19 : ``Dialog.render`` = 181 lignes, ``Drawer.render`` = 176,
**139 identiques (76 %)**. Ce ne sont pas deux composants qui se
ressemblent, c'est un composant rendu deux fois, dont toute la
différence tient en trois valeurs de style : la classe de largeur (le
drawer la choisit sur DEUX axes selon le côté), ce que le côté ajoute au
panneau, ce qu'il ajoute au conteneur.

⚠️ **Le reste de l'écart n'était pas du code, c'étaient les
commentaires.** Les deux fichiers expliquaient la même mécanique — la
résolution de l'état ouvert, pourquoi le backdrop porte le clic et pas
le conteneur, pourquoi le scope local doit se resynchroniser quand
``open=`` est backé serveur — avec des mots différents, à des niveaux de
détail différents. Un lecteur ne pouvait donc pas savoir si les deux se
comportent pareil sans relire les deux. C'est le coût que la duplication
fait payer AVANT même de produire un bug.

Ce qui reste chez l'appelant
-----------------------------
Les chaînes de style. Elles restent par composant
(`feedback_no_shared_style_tokens`) et arrivent ici **déjà composées** :
ce module ne lit jamais un thème, il assemble des nœuds.

⚠️ La classe de translation fermée du drawer
(``data-[open=false]:translate-x-full``) est déjà COMPLÈTE dans son
thème et ne peut pas être assemblée ici — une classe Tailwind assemblée
à l'exécution n'existe qu'en dev
(`project_assembled_tailwind_class_dev_only`).
"""

from __future__ import annotations

from typing import Any

from bretzel.components.actions.icon_button import IconButton
from bretzel.components.base import Component
from bretzel.components.base._wiring import (
    escape_init,
    focus_trap_effect,
    imperative_listeners,
    modal_root_effect,
    server_sync_marker,
    show_attrs,
)
from bretzel.core.tree import Element, Node
from bretzel.render import text


def render_modal_overlay(
    component: Any,
    *,
    slots: dict[str, str],
    panel_extra: tuple[str, ...] = (),
    container_extra: tuple[str, ...] = (),
) -> Element:
    """Backdrop + conteneur + panneau (en-tête, corps) + racine câblée.

    ``panel_extra`` est ce qui suit ``slots["panel"]`` sur le panneau —
    la classe de largeur pour un dialog, plus les deux classes de côté
    pour un drawer. **L'ordre appartient à l'appelant** : deux
    utilitaires de même famille et même spécificité sont départagés par
    l'ordre de la FEUILLE, pas par celui du ``class=``, mais l'ordre
    reste ce que le composant a écrit et une gate le surveille
    (``test_no_same_specificity_conflict``).
    """
    title = component._reactive_values.get("title")
    dismissible = bool(component._reactive_values.get("dismissible"))
    persistent = bool(component._reactive_values.get("persistent"))

    # ── L'état ouvert : ClientBinding ou booléen littéral ─────────────
    # Quand l'utilisateur passe un ClientBinding, le socle l'a rangé dans
    # ``_binding_metadata`` et a laissé le bool brut dans
    # ``_reactive_values`` pour le SSR. On branche ici.
    open_binding = component._binding_metadata.get("open")
    bound_open = open_binding is not None
    # ``$bz.state.<Classe>.<clé>.<champ>`` — le chemin exact où le
    # ``.set()`` / ``.toggle()`` du binding écrit. Sinon, un drapeau
    # local au scope de cet overlay.
    open_expr = open_binding.binding_path() if bound_open else "open"
    initial_open = bool(component._reactive_values.get("open"))

    title_id = f"{component.id}_title" if component.id and title else None

    # ── Backdrop ─────────────────────────────────────────────────────
    # Un overlay persistant AVALE le clic de fond ; un dismissible ferme.
    # Dans les deux cas le clic n'atteint jamais un descendant du
    # panneau : le panneau vit dans un élément FRÈRE.
    backdrop_attrs: dict[str, Any] = {
        "class": slots.get("backdrop", ""),
        **show_attrs(open_expr, initial_open),
        "aria-hidden": "true",
    }
    if dismissible and not persistent:
        backdrop_attrs["bz-on:click"] = f"{open_expr} = false"
    backdrop = Element(tag="div", attrs=backdrop_attrs, children=())

    # ── Panneau ──────────────────────────────────────────────────────
    panel_attrs: dict[str, Any] = {
        "class": " ".join(
            p for p in (slots.get("panel", ""), *panel_extra) if p
        ),
        "role": "dialog",
        "aria-modal": "true",
        **show_attrs(open_expr, initial_open),
        # Piège à focus tant que c'est ouvert : Tab/Shift+Tab tournent
        # dans le panneau, le premier enfant focalisable reçoit le focus,
        # et l'élément précédemment focalisé est restauré à la fermeture
        # (``$bz.helpers.focusTrap`` rend son propre dispose).
        "bz-effect": focus_trap_effect(open_expr),
    }
    if title_id:
        panel_attrs["aria-labelledby"] = title_id

    panel_children: list[Node] = []

    # En-tête (titre + bouton de fermeture) — seulement s'il y a un titre
    # OU de quoi fermer, pour qu'un overlay de confirmation persistant
    # puisse s'en passer entièrement avec ``title=None``.
    if title or dismissible:
        header_children: list[Node] = []
        if title:
            title_attrs: dict[str, Any] = {"class": slots.get("title", "")}
            if title_id:
                title_attrs["id"] = title_id
            header_children.append(
                Element(
                    tag="h2",
                    attrs=title_attrs,
                    children=(component.emit_text_slot(title),),
                )
            )
        if dismissible:
            close_btn = IconButton(
                "x",
                variant="ghost",
                size="sm",
                color="muted",
                aria_label=text("modal.close"),
                on_click=f"{open_expr} = false",
            )
            Component._detach_from_parent(close_btn)
            header_children.append(
                Element(
                    tag="div",
                    attrs={"class": slots.get("close", "")},
                    children=(close_btn.render(),),
                )
            )
        panel_children.append(
            Element(
                tag="div",
                attrs={"class": slots.get("header", "")},
                children=tuple(header_children),
            )
        )

    # Corps — tous les enfants capturés dans le ``with``.
    body_nodes = list(component._render_children())
    if body_nodes:
        panel_children.append(
            Element(
                tag="div",
                attrs={"class": slots.get("body", "")},
                children=tuple(body_nodes),
            )
        )

    panel = Element(tag="div", attrs=panel_attrs, children=tuple(panel_children))

    # ── Conteneur ────────────────────────────────────────────────────
    # Il place le panneau et fournit la surface de clic-dehors. On n'y
    # met PAS ``bz-on:click`` : le panneau est son enfant, le clic
    # remonterait — c'est le backdrop qui porte la fermeture.
    container = Element(
        tag="div",
        attrs={
            "class": " ".join(
                p for p in (slots.get("container", ""), *container_extra) if p
            ),
            **show_attrs(open_expr, initial_open),
        },
        children=(panel,),
    )

    # ── Racine ───────────────────────────────────────────────────────
    attrs = component.emit_attrs()
    # ``contents`` retire le wrapper du flux de mise en page, pour que
    # les enfants ``fixed`` s'ancrent sur le viewport et non sur sa boîte.
    attrs["class"] = "contents"
    if not bound_open:
        # ``open`` vit dans le scope local, qu'``absorb`` PRÉSERVE à
        # travers un morph — donc un ``open=state.champ`` piloté par le
        # SERVEUR serait ignoré au refresh si la clé ne demande pas
        # ``_serverSync``. On garde sur « backé serveur » : un
        # ``open=True`` littéral doit, lui, garder son état client à
        # travers un refresh sans rapport.
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
    # Verrou de scroll + dispatch open/close (bz-effect de racine),
    # récepteurs de l'API impérative, Échap pour fermer : le câblage
    # d'overlay partagé (cf. ``base/_wiring.py``).
    attrs["bz-effect"] = modal_root_effect(open_expr)
    attrs.update(imperative_listeners(open_expr))
    if dismissible and not persistent:
        attrs["bz-init"] = escape_init(open_expr)

    return Element(
        tag=component._tag,
        attrs=attrs,
        children=(backdrop, container, *component._event_carrier_nodes()),
    )


__all__ = ["render_modal_overlay"]
