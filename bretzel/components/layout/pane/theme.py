"""Thème par défaut de :class:`Pane` — la région qui défile.

Le slot ``root`` porte cinq utilitaires, et **deux d'entre eux ne se
devinent pas**. C'est la raison d'être du composant : chacun a coûté une
mesure et une entrée de ``traps.md`` avant d'être écrit ici.

``flex-1`` **et** ``h-full``
    Les deux, parce que le parent peut avoir deux formes et que le
    composant ne sait pas laquelle. Dans un parent ``flex-col``,
    ``flex-basis: 0%`` remplace la taille principale et ``height: 100%``
    est ignoré ; dans un parent bloc à hauteur définie (un
    ``ui.resizable_panel``, par exemple), ``flex-1`` est inerte et c'est
    ``h-full`` qui rend. Mesuré en Chromium sur les trois formes de
    parent — colonne flex, bloc, panneau : la combinaison des deux
    défile dans les trois, ``flex-1`` seul échoue dans deux (600 px de
    haut, aucun défilement), ``h-full`` seul rate la place restante en
    colonne flex.

``min-h-0``
    Load-bearing. Sans lui, la hauteur minimale automatique d'un item
    flex vaut la taille de son contenu : la boîte GRANDIT au lieu de
    défiler, et rien ne le signale. Déjà dans ``traps.md`` § *sidebar
    scroll*.

``[&>*]:shrink-0``
    Load-bearing aussi, et encore moins devinable. La racine de
    ``ui.card`` porte ``overflow-hidden``, donc sa hauteur minimale
    automatique vaut ZÉRO : dès que la liste remplit la colonne, les
    cartes se compriment sous leur contenu. Mesuré sur
    ``examples/crm`` : 73 px libre contre 34 px contraint, **39 px
    coupés** — et invisible sur la dernière page, qui n'a pas assez de
    lignes pour remplir. ``traps.md`` § *Une colonne qui défile ÉCRASE
    ses items*.

Ce qui n'est **pas** ici, et pourquoi
--------------------------------------
``pr-1`` — la gouttière qui écarte le contenu de la barre de défilement.
Trois sites sur dix-sept l'écrivent, et surtout elle se bat avec
``padding=`` : ``p-8`` et ``pr-1`` posent tous deux ``padding-right``, et
le vainqueur dépend de l'ordre de la feuille Tailwind, pas de l'ordre des
classes. Un réglage par instance qui casse une prop reste dans
``classes=``.

Les tables ``directions`` / ``alignments`` / ``justifies`` / ``gaps`` sont
recopiées de :data:`FLEX_THEME` plutôt que partagées : la convention du
dépôt est qu'un thème est auto-suffisant, pour qu'un override n'ait
jamais à deviner d'où vient une valeur.
"""

from __future__ import annotations

from typing import Any

PANE_THEME: dict[str, Any] = {
    "slots": {
        # ``flex`` seul : la direction arrive de la table ci-dessous
        # (``col`` par défaut, scellé — un pane est une colonne).
        "root": "flex flex-1 h-full min-h-0 overflow-y-auto [&>*]:shrink-0",
    },
    "directions": {
        "row": "flex-row",
        "col": "flex-col",
        "row-reverse": "flex-row-reverse",
        "col-reverse": "flex-col-reverse",
    },
    # ⚠️ Les deux CENTRAGES portent le mot-clé CSS ``safe``, et c'est le
    # seul endroit du catalogue où il compte : un pane DÉFILE
    # (``overflow-y-auto``). Centrer un contenu plus haut que le cadre le
    # fait déborder des DEUX côtés, or le défilement ne remonte jamais
    # au-dessus de son origine — la partie haute devient donc
    # **inatteignable**, définitivement. ``safe`` dit au navigateur de
    # retomber sur ``start`` quand ça déborde, ce qui est exactement le
    # cas où le centrage nuit.
    #
    # Mesuré le 2026-08-24 sur la page de connexion d'``auth`` en
    # 1280×600 : contenu de 732 px, cadre de 600, et **108 px coupés en
    # haut** que rien ne permettait d'atteindre. Le symptôme ne désigne
    # rien — la page a l'air simplement tronquée, pas cassée.
    #
    # Forme entre crochets plutôt que ``justify-center-safe`` : cet
    # utilitaire n'existe que depuis Tailwind 4.1, et le compilateur
    # navigateur du mode dev peut être plus ancien. La propriété
    # arbitraire, elle, marche depuis la v3.
    "alignments": {
        "start": "items-start",
        "center": "[align-items:safe_center]",
        "end": "items-end",
        "stretch": "items-stretch",
        "baseline": "items-baseline",
    },
    "justifies": {
        "start": "justify-start",
        "center": "[justify-content:safe_center]",
        "end": "justify-end",
        "between": "justify-between",
        "around": "justify-around",
        "evenly": "justify-evenly",
    },
    "gaps": {
        "none": "gap-0",
        "xs": "gap-1",
        "sm": "gap-2",
        "md": "gap-4",
        "lg": "gap-6",
        "xl": "gap-8",
    },
    # Même échelle que ``ui.card`` — la respiration d'une région de
    # contenu et celle d'une carte se comparent à l'œil dans la même vue,
    # donc deux échelles concurrentes se verraient.
    "paddings": {
        "none": "",
        "xs": "p-2 sm:p-3",
        "sm": "p-3 sm:p-4",
        "md": "p-4 sm:p-6",
        "lg": "p-6 sm:p-8",
        "xl": "p-8 sm:p-10",
    },
    # Pas de clé ``wrap`` : la prop est SCELLÉE sur le composant, donc la
    # table serait du thème mort — et elle ressortait dans
    # ``bretzel describe pane``, ce qui rendait visible une prop refusée
    # à l'appel. Exactement ce que ``SEALED_PROPS`` existe pour éviter.
    # Recopiée de :data:`FLEX_THEME` comme les tables voisines — un thème
    # est auto-suffisant dans ce dépôt. Les trois copies sont tenues
    # identiques par ``test_a_flex_family_declares_every_table``.
    "grows": {
        "equal": "*:grow *:basis-0",
        "12rem": "*:grow *:basis-48",
        "16rem": "*:grow *:basis-64",
        "20rem": "*:grow *:basis-80",
    },
}
