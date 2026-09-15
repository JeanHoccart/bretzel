"""Le rendu commun des deux contrôles cochables — ``Checkbox`` et ``Switch``.

Ce que la mesure a montré
--------------------------
Le 2026-08-19 : ``Checkbox.render`` = 137 lignes, ``Switch.render`` =
113, **86 identiques (62 %)**. Les deux fichiers importaient exactement
les trois mêmes helpers de ``inputs/_wiring``, dans le même ordre.

Ce qui les sépare vraiment est **visuel, et lui seul** : la case a une
boîte plus un SVG de coche, l'interrupteur a un rail plus un pouce. Tout
le reste — l'``<input type=checkbox>`` réel qui porte les attributs du
framework, le ``bz-model`` bidirectionnel, le scope local qui fait
survivre une bascule à un morph, le forçage du booléen dans la form
data, les écouteurs de l'API impérative, le ``<label>`` racine — est le
même mot pour mot.

⚠️ Et comme pour les overlays, une bonne part de l'écart restant
n'était pas du code mais des **commentaires** : le piège du booléen non
soumis (une case décochée n'envoie RIEN, donc le ``false`` n'atteint
jamais le serveur et le refresh la re-coche) y était expliqué deux fois,
à deux niveaux de détail.

Ce qui reste chez l'appelant
-----------------------------
Les nœuds visuels, construits avec ses propres classes composées — elles
restent par composant (`feedback_no_shared_style_tokens`). Ce module ne
lit jamais un thème : il reçoit des nœuds et les pose sous le
``<label>``.
"""

from __future__ import annotations

from typing import Any

from bretzel.components.inputs._wiring import (
    add_local_value_scope,
    checked_command_listeners,
    false_companion_input,
    force_boolean_form_vals,
)
from bretzel.core.tree import Element, Node


def render_checkable(
    component: Any,
    *,
    size_map: dict[str, str],
    visuals: tuple[Node, ...],
) -> Element:
    """``<label>`` : l'``<input>`` réel, les faux visuels, puis le libellé.

    ``visuals`` sont les nœuds décoratifs qui suivent l'input dans le
    conteneur — boîte + coche pour une case, rail + pouce pour un
    interrupteur. Ils sont purement décoratifs : c'est l'``<input>``
    caché qui porte l'interaction, le focus et l'accessibilité.
    """
    # L'input réel — caché mais interactif. Il porte TOUS les attributs
    # du framework (id / bz-id / events / bz-model) ; les faux visuels
    # sont des descendants décoratifs sous le même ``<label>``.
    input_attrs: dict[str, Any] = {
        "type": "checkbox",
        "class": component.compose_class(
            "input", apply_variant_size_modifiers=False
        ),
    }
    input_attrs.update(component.emit_attrs())

    # ``bz-model`` écrit dans les deux sens ; il retire au passage le
    # ``bz-attr:checked`` en lecture seule que ``emit_attrs`` avait posé
    # pour un binding. Un ``checked=True`` littéral, lui, est déjà arrivé
    # en attribut HTML statique par ``emit_attrs``.
    component._bind_x_model(input_attrs, prop="checked")

    # Local + interactif : un signal de scope ``checked`` sur l'``<input>``
    # pour qu'une bascule de l'utilisateur survive au morph d'un
    # ``@refreshable`` englobant — sans lui, idiomorph remet le
    # ``.checked`` natif à la valeur SSR. Sans effet en mode binding, ni
    # sans handler.
    add_local_value_scope(
        component, input_attrs, prop="checked",
        ssr_value=bool(component._reactive_values.get("checked")),
    )

    # Bascule liée au serveur : une case DÉCOCHÉE ne soumet rien, donc le
    # ``false`` n'atteindrait jamais le serveur et le refresh la
    # re-cocherait. Sauté pour un ClientBinding (le bridge expédie déjà le
    # store) et pour un ``value=`` explicite (sémantique de liste de
    # valeurs, où « décoché = absent » est le bon HTML). Cf. traps.md.
    #
    # DEUX mécanismes, parce qu'il y a DEUX requêtes possibles, et qu'aucun
    # des deux ne couvre l'autre :
    #
    # - ``hx-vals`` couvre la requête que la CASE tire elle-même (son
    #   ``on_change``) : htmx l'évalue à l'envoi et écrase la valeur native.
    #   Il n'existe que s'il y a un ``hx-post`` sur l'input ;
    # - le compagnon caché couvre la soumission du FORMULAIRE parent, où
    #   l'événement ne vient pas de la case et où ``event.target.checked``
    #   ne veut rien dire. Il porte le même ``name`` et la valeur
    #   ``"false"``, et il est placé AVANT la case : les deux partent quand
    #   elle est cochée, et le serveur garde la dernière (``FormData`` comme
    #   ``parse_qsl`` : le dernier gagne).
    #
    # Mesuré le 2026-08-19 sur l'écran Paramètres du CRM : un ``ui.switch``
    # sans ``on_change`` se décochait à l'écran et revenait coché après
    # « Enregistrer » — un réglage booléen coincé sur ``True`` pour toujours.
    server_bound_boolean = (
        component._binding_metadata.get("checked") is None
        and component._reactive_values.get("value") is None
        and bool(input_attrs.get("name"))
    )
    if server_bound_boolean:
        force_boolean_form_vals(input_attrs, name=input_attrs.get("name"))

    # Écouteurs de l'API impérative — ils attrapent les commandes DOM que
    # ``.toggle()`` / ``.set(bool)`` dispatchent sur cet input par son id.
    # L'écouteur bascule ``$el.checked`` puis tire un ``change`` de
    # synthèse, pour que ``bz-model`` (cas binding) se synchronise ET que
    # le ``on_change=`` de l'utilisateur tourne. En mode binding, les
    # méthodes impératives écrivent directement par le binding et ces
    # événements ne partent jamais — on garde la forme uniforme pour le
    # cas sans binding. Cf. `imperative-api.md` / ``inputs/_wiring.py``.
    input_attrs.update(checked_command_listeners())

    # Le compagnon caché — l'autre moitié du même mécanisme, d'où sa place
    # dans ``inputs/_wiring.py`` juste à côté de ``force_boolean_form_vals``.
    companion: tuple[Node, ...] = (
        (false_companion_input(
            input_attrs["name"],
            # Le même sort que la case : un contrôle désactivé ne soumet
            # rien, et un compagnon resté actif serait le seul à partir.
            disabled=bool(input_attrs.get("disabled")),
        ),)
        if server_bound_boolean else ()
    )

    container = Element(
        tag="div",
        attrs={
            "class": component.compose_class(
                "container", apply_variant_size_modifiers=False
            )
        },
        children=(
            *companion,
            Element(tag="input", attrs=input_attrs, children=()),
            *visuals,
        ),
    )

    children: list[Node] = [container]
    if component._label:
        label_class = " ".join(
            p
            for p in (
                component.compose_class(
                    "label", apply_variant_size_modifiers=False
                ),
                size_map.get("label", ""),
            )
            if p
        )
        children.append(
            Element(
                tag="span",
                attrs={"class": label_class},
                children=(component.emit_text_slot(component._label),),
            )
        )

    # Pas de scope sur la racine — les ``bz-on:`` posés sur l'input se
    # résolvent contre le scope racine du runtime.
    return Element(
        tag=component._tag,
        attrs={"class": component.compose_class("root")},
        children=tuple(children),
    )


def sized_slot(component: Any, slot: str, size_map: dict[str, str]) -> str:
    """La classe composée d'un slot visuel, plus son entrée de taille.

    Les deux composants écrivaient cette jointure deux fois chacun (boîte
    + icône, rail + pouce), à l'identique. ``compose_class`` résout le
    ``{bg_color}`` et n'ajoute rien d'autre : ni variante ni taille sur
    un slot non-racine.
    """
    return " ".join(
        p
        for p in (
            component.compose_class(slot, apply_variant_size_modifiers=False),
            size_map.get(slot, ""),
        )
        if p
    )


__all__ = ["render_checkable", "sized_slot"]
