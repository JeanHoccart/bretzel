"""Surface partagée des pickers à panneau — Select et Combobox.

Les deux composants sont **un miroir l'un de l'autre** par conception :
même trigger ancré, même panneau d'options, mêmes pills en mode multi.
Leurs thèmes promettent explicitement de « se lire comme une famille ».
Ce module est l'endroit où cette promesse est tenue par le code plutôt
que par la discipline.

Avant, deux helpers (``_sized_slot``, ``_badge_pill_classes``) vivaient
dans ``combobox.py`` et ``select.py`` les importait de là — un composant
dépendant d'un frère faute de maison commune. Les quatre autres étaient
recopiés des deux côtés (audit F13, F52), dont le template de pills
entier, dont le docstring de select concédait la copie sans que
l'extraction n'arrive jamais.

Ce qui reste **volontairement** par composant : ``.focus()`` / ``.blur()``
(la surface focusable diffère : un ``<button>`` pour Select, l'``<input>``
de recherche pour Combobox), et le chevron (Select le compose inline,
Combobox le monte en méthode).
"""

from __future__ import annotations

from typing import Any

from bretzel.components.base import (
    Component,
    coerce_children,
    stamp_display_none,
)
from bretzel.components.feedback.badge.theme import BADGE_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as TextNode
from bretzel.render import text


def sized_slot(
    slots: dict[str, str],
    size_map: dict[str, str],
    slot: str,
    resolve_fn: Any,
) -> str:
    """Compose ``slots[slot]`` + ``sizes[<size>][slot]`` en une string.

    L'idiome des composants multi-slots : le composeur de base SKIPPE en
    silence une table ``sizes`` en dict, donc chaque slot sizé se compose
    ici.

    ``resolve_fn`` est appliqué systématiquement : ``_resolve_template``
    court-circuite quand le template n'a pas de ``{``, donc les slots sans
    placeholder ne paient rien.
    """
    return " ".join(p for p in (
        resolve_fn(slots.get(slot, "")), size_map.get(slot, ""),
    ) if p)


def badge_pill_classes(
    resolve_fn: Any,
    *,
    size: str,
    badge_theme: dict[str, Any] | None = None,
    variant: str = "soft",
) -> tuple[str, str]:
    """Compose the ``(pill_class, close_class)`` strings from
    :data:`BADGE_THEME` for use inside a pill-rendering ``bz-for``
    template. Single source of truth for pill styling : Combobox /
    Select multi-pickers both delegate here so a Badge theme tweak
    propagates everywhere automatically.

    ``badge_theme`` DOIT être le thème Badge RÉSOLU du call-site
    (``self._resolved_theme("badge", BADGE_THEME)``) : lire la constante
    ``BADGE_THEME`` ici contournerait un ``Theme(components={"badge":
    …})`` de l'app, et les pills ne suivraient pas la surcharge — alors
    que le docstring ci-dessus promet exactement l'inverse. Le défaut
    ``None`` ne sert qu'aux tests hors contexte de render.

    ``resolve_fn`` is the call site's ``_resolve_template(template,
    color)`` partial so ``{bg_color}`` / ``{fg_color}`` placeholders
    get filled with the picker's chosen color.

    ``size`` est REQUIS — et volontairement sans défaut. Il en avait un
    (``"sm"``), et les quatre call-sites l'avaient tous laissé filer :
    les pills restaient ``sm`` sur un picker ``xl``. Un défaut ici est
    invisible au call-site ; l'absence de défaut force à décider. Passe
    le token depuis ``sizes[<size>]["pill_size"]``.
    """
    theme = badge_theme if badge_theme is not None else BADGE_THEME
    slots = theme["slots"]
    variants = theme["variants"]
    sizes = theme["sizes"]
    variant_cfg = variants.get(variant, variants["soft"])
    size_cfg = sizes.get(size, sizes["sm"])
    pill = " ".join(p for p in (
        resolve_fn(slots.get("root", "")),
        resolve_fn(variant_cfg.get("root", "")),
        size_cfg.get("root", ""),
    ) if p)
    close = " ".join(p for p in (
        resolve_fn(slots.get("close", "")),
        size_cfg.get("close", ""),
    ) if p)
    return pill, close


def normalise_option(opt: Any) -> tuple[Any, Any, bool]:
    """Return ``(value, label, disabled)`` for any of the accepted
    option shapes : str / tuple / dict.

    Le contrat de forme des options DOIT être identique entre les deux
    pickers — un ``options=`` qui marche sur l'un et pas sur l'autre
    serait incompréhensible.
    """
    if isinstance(opt, dict):
        return (
            opt.get("value", opt.get("label", "")),
            opt.get("label", opt.get("value", "")),
            bool(opt.get("disabled", False)),
        )
    if isinstance(opt, tuple) and len(opt) >= 2:
        return opt[0], opt[1], False
    # Plain scalar (string / int) — value == label.
    return opt, opt, False


def option_body(
    render: Any, value: Any, label: Any
) -> tuple[Node, ...]:
    """Le CORPS d'une option — ce que ``render=`` remplace.

    L'enveloppe reste au composant : le ``<button role="option">``, son
    ``data-value``, son ``bz-on:click``, son ``aria-selected`` et — le
    plus important — son ``bz-show="_matches(<haystack>)"``. Le rappel ne
    remplit que l'intérieur.

    Pourquoi un rappel ici et des enfants ailleurs
    ----------------------------------------------

    ``COLLECTION_OWNER = "component"`` : c'est le picker qui itère
    ``options=``, l'auteur n'écrit pas cette boucle — il n'a donc aucun
    endroit où poser son balisage sans ce rappel. Cf.
    ``Component.COLLECTION_OWNER`` et
    ``tests/consistency/test_collection_owner_decides_the_api.py``.

    ⚠️ Signature ``(value, label)``, tous deux **déjà normalisés**, et
    pas l'option brute. C'est délibéré : ``options=`` accepte trois
    formes (str, tuple, dict), donc un rappel écrit
    ``lambda opt: opt["label"]`` planterait sur deux d'entre elles. Le
    même défaut avait été livré puis retiré sur ``breadcrumb`` le
    2026-08-18. ``ui.column(render=lambda value, row)`` a la même
    arité pour la même raison.

    Trois limites à connaître, toutes structurelles :

    1. le **filtre** cherche dans le haystack, bâti côté serveur depuis
       le label TEXTE — un badge rendu ici ne change pas ce qui est
       cherché ;
    2. le **déclencheur** et les **pills** lisent une carte
       valeur→libellé en JS (``bz-text``), donc ils affichent le texte,
       jamais ce balisage — un nœud texte ne porte pas de markup ;
    3. le rappel ne touche ni au ``value``, ni au clic, ni à l'état
       sélectionné.
    """
    if render is None:
        return (TextNode(str(label)),)
    return coerce_children(render(value, label))


def has_picks(initial_value: Any, *, is_multi: bool) -> bool:
    """SSR snapshot : le picker a-t-il une sélection au premier paint ?

    Pilote le pré-stamp FOUC ``stamp_display_none`` — sur le bouton
    clear (Combobox), sur les branches pills / clear / placeholder du
    trigger multi (Select) — pour qu'ils peignent dans le bon état avant
    le boot du runtime.
    """
    if is_multi:
        if isinstance(initial_value, (list, tuple, set)):
            return len(initial_value) > 0
        return bool(initial_value)
    return initial_value not in (None, "")


def render_x_icon(icon_size: str) -> Element:
    """Le glyphe ``×`` du bouton clear, à la taille du picker."""
    return Component.render_detached(Icon("x", size=icon_size))


def option_check(
    *,
    slots: dict[str, str],
    size_map: dict[str, str],
    resolve: Any,
    picked_js: str,
    initially_picked: bool,
) -> Element:
    """La coche d'une option PRISE, en mode multi.

    Sans elle, « pris » ne se lit qu'au gras + accent de
    ``option_selected`` — et sur une liste ouverte avec TOUT pris (ce que
    fait un filtre de colonne : « rien de décoché » = « rien de filtré »)
    l'œil ne voit qu'une liste uniformément bleue, donc aucune sélection.
    Pire, un survol pose ``option_active``, qui est lui aussi accentué :
    survolé-non-pris et pris se ressemblent.

    À DROITE, et pas une case à gauche : la case appartient au
    formulaire, où elle est le contrôle lui-même ; ici le contrôle est la
    rangée entière, et la coche en rapporte l'état. C'est ce que font
    Linear / Notion / GitHub, et ça laisse les libellés alignés sur la
    même colonne qu'en mode simple.

    Mode MULTI seulement : en simple, le déclencheur affiche déjà
    l'étiquette prise, et une coche sur l'unique ligne accentuée
    redirait la même chose deux fois.

    ``picked_js`` est le prédicat du call-site (``_isPicked("x")``) ;
    ``initially_picked`` pré-stampe l'état SSR pour qu'aucune coche ne
    clignote avant le boot du runtime.
    """
    attrs: dict[str, Any] = {
        "class": sized_slot(slots, size_map, "option_check", resolve),
        "bz-show": picked_js,
        "aria-hidden": "true",
    }
    if not initially_picked:
        stamp_display_none(attrs)
    return Element(
        tag="span",
        attrs=attrs,
        children=(Component.render_detached(
            Icon("check", size=size_map.get("check_icon_size", "sm")),
        ),),
    )


def build_pills_template(
    *, pill_class: str, remove_class: str,
) -> Element:
    """Reactive pills via ``<template bz-for>``. Each picked value
    renders as ``<span class="pill">label <button>×</button></span>``.

    Le libellé passe par ``_labelOf(v)``, une méthode du scope. Ce
    gabarit inlinait la carte ``{valeur: libellé}`` ENTIÈRE dans son
    ``bz-text`` jusqu'au 2026-08-28 — un deuxième exemplaire pour Select,
    un TROISIÈME pour Combobox (qui la portait aussi dans ``_options``).
    Chaque picker résout maintenant un libellé à sa façon : Select lit sa
    carte, Combobox balaie ``_options``, qui le porte déjà.

    ``bz-for`` lives on a ``<template>`` with a SINGLE root child ;
    the key rides inside the attribute (``v in _picked() :key=v``)
    per the directive grammar.
    """
    return Element(
        tag="template",
        attrs={"bz-for": "v in _picked() :key=v"},
        children=(
            Element(
                tag="span",
                attrs={"class": pill_class},
                children=(
                    Element(
                        tag="span",
                        attrs={
                            "bz-text": "_labelOf(v) || v",
                        },
                        children=(),
                    ),
                    Element(
                        tag="button",
                        attrs={
                            "type": "button",
                            "class": remove_class,
                            "tabindex": "-1",
                            "aria-label": text("picker.remove"),
                            "bz-on:click": (
                                "$event.stopPropagation(); _removeOne(v)"
                            ),
                        },
                        children=(
                            Element(
                                tag="span",
                                attrs={
                                    "class": (
                                        "inline-block w-3 h-3 "
                                        "leading-none text-center"
                                    ),
                                },
                                children=(TextNode("×"),),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


__all__ = [
    "badge_pill_classes",
    "build_header_bar",
    "build_pills_template",
    "has_picks",
    "normalise_option",
    "option_check",
    "render_x_icon",
    "sized_slot",
]


def build_header_bar(
    *,
    slots: dict[str, str],
    size_map: dict[str, str],
    resolve: Any,
    badge_theme: dict[str, Any],
    is_multi: bool,
    show_bulk: bool,
    total_options: int,
    initial_value: Any,
    select_all_disabled_js: str,
    lead: Element | None = None,
) -> Element:
    """The panel's sticky header — three zones in one flex row.

    - **Compteur** (multi seulement) : ``"N / total"``, le nombre de
      sélections d'un coup d'œil.
    - **Pills** : les picks courants en badges retirables (le ``×``
      enlève sans quitter le panneau).
    - **Actions** (à droite, si ``show_bulk``) : ``Select all`` +
      ``Clear``. Désactivées plutôt que masquées — la mise en page
      reste stable.

    Visibilité : la barre entière se cache via ``bz-show`` quand il n'y
    a ni pick ni action. Un pré-stamp FOUC la garde cachée au SSR quand
    ni l'une ni l'autre condition ne tient.

    ``lead`` est une rangée pleine largeur posée EN TÊTE de la barre —
    le champ de recherche du Combobox quand un ``trigger=`` custom l'a
    délogé du déclencheur. La barre étant ``flex-wrap``, un enfant
    ``w-full`` occupe sa propre ligne et le reste (compteur, actions)
    se range dessous. Une barre qui porte la recherche ne peut plus se
    cacher : ``lead`` force ``bz-show`` à vrai et annule le pré-stamp.

    ``lead`` retire aussi les pills : un filtre s'ouvre avec TOUTES ses
    valeurs cochées, donc les badges seraient un mur au-dessus de la
    liste qu'ils répètent — et le déclencheur, qui appartient à
    l'appelant, dit déjà ce qui est pris. Dérivé plutôt que passé en
    second drapeau : deux booléens qui doivent s'accorder, c'est un
    booléen qui peut se contredire.

    ``select_all_disabled_js`` est la SEULE vraie divergence entre les
    deux pickers (audit F14) : Select compare aux options totales,
    Combobox à ce que la requête laisse visible. Tout le reste — ~100
    lignes — était recopié, pour un contrat visuel que les deux thèmes
    promettent explicitement de tenir en phase (« se lit comme une
    famille »). Un ajustement du header dérivait donc en silence entre
    Select-multi et Combobox-multi.
    """
    bar_class = slots.get("header_bar", "")
    counter_class = sized_slot(slots, size_map, "header_counter", resolve)
    pills_class = slots.get("header_pills", "")
    actions_class = slots.get("header_actions", "")
    # Same Badge-theme delegation as the trigger pills.
    pill_class, remove_class = badge_pill_classes(
        resolve, size=size_map.get("pill_size", "sm"),
        badge_theme=badge_theme,
    )
    btn_primary = sized_slot(slots, size_map, "header_btn_primary", resolve)
    btn_muted = sized_slot(slots, size_map, "header_btn_muted", resolve)

    # Bulk on → la barre reste visible même sans pick (les actions
    # doivent être découvrables). Une recherche en tête la rend
    # inconditionnelle : la cacher emporterait le champ avec elle.
    # UNE variable, lue par le ``bz-show`` runtime ET par le pré-stamp
    # SSR plus bas. Les deux étaient deux expressions indépendantes de
    # polarité inverse : ajouter une zone demandait un terme dans
    # chacune, avec un signe différent, et se tromper sur le pré-stamp
    # est invisible à toute la suite (aucun test SSR n'évalue un
    # ``bz-show``).
    always_visible = show_bulk or lead is not None
    bar_bz_show = "true" if always_visible else "_hasPicked()"

    children: list[Any] = []

    if lead is not None:
        children.append(lead)

    if is_multi:
        children.append(Element(
            tag="span",
            attrs={
                "class": counter_class,
                "bz-text": f"_picked().length + ' / {total_options}'",
            },
            children=(),
        ))

    if lead is None:
        children.append(Element(
            tag="div",
            attrs={"class": pills_class},
            children=(build_pills_template(
                pill_class=pill_class,
                remove_class=remove_class,
            ),),
        ))

    if show_bulk:
        children.append(Element(
            tag="div",
            attrs={"class": actions_class},
            children=(
                Element(
                    tag="button",
                    attrs={
                        "type": "button",
                        "class": btn_primary,
                        "bz-on:click": (
                            "$event.stopPropagation(); _selectAll()"
                        ),
                        "bz-attr:disabled": select_all_disabled_js,
                    },
                    children=(TextNode(text("picker.select_all")),),
                ),
                Element(
                    tag="button",
                    attrs={
                        "type": "button",
                        "class": btn_muted,
                        "bz-on:click": (
                            "$event.stopPropagation(); _clearAll()"
                        ),
                        "bz-attr:disabled": "!_hasPicked()",
                    },
                    children=(TextNode(text("picker.clear")),),
                ),
            ),
        ))

    header_attrs: dict[str, Any] = {
        "class": bar_class,
        "bz-show": bar_bz_show,
    }
    if not always_visible and not has_picks(initial_value, is_multi=is_multi):
        stamp_display_none(header_attrs)
    return Element(tag="div", attrs=header_attrs, children=tuple(children))
