"""Thème par défaut de :class:`Viewport` — le cadre plein écran.

``fixed inset-0 w-full overflow-hidden``, et le ``fixed`` est le seul
utilitaire qui compte vraiment.

Pourquoi ``fixed inset-0`` et surtout PAS ``h-screen``
-------------------------------------------------------
``h-screen`` laisse le cadre DANS le flux du document. Un descendant qui
défile gonfle alors ``html.scrollHeight`` au-delà de ``clientHeight``, et
le navigateur rend une **seconde barre de défilement** au niveau du
viewport. Mesuré deux fois dans ce dépôt : ``html.scrollHeight = 7 657``
pour un ``clientHeight = 800`` sur une page longue. ``position: fixed``
sort le cadre du flux — ``html.scrollHeight`` retombe à
``clientHeight``, et il ne reste que la barre voulue, celle du
:class:`~bretzel.components.layout.pane.Pane`.

⚠️ Le correctif a été **reverté une fois** (2026-07-18) avec un
commentaire affirmant que « ``overflow-hidden`` + ``min-h-0``
suffisent ». C'est faux, et le piège de cette croyance est qu'elle est
vraie sur les pages COURTES : l'inflation vaut zéro tant que le contenu
tient dans l'écran, d'où le sentiment que ``h-screen`` marche. Ne pas
re-reverter. ``traps.md`` § *Shell layout h-screen produit un double
scrollbar viewport*.

Les tables de flex sont recopiées de :data:`FLEX_THEME` plutôt que
partagées — un thème du dépôt est auto-suffisant, pour qu'un override
n'ait jamais à deviner d'où vient une valeur.
"""

from __future__ import annotations

from typing import Any

VIEWPORT_THEME: dict[str, Any] = {
    "slots": {
        # ``flex`` seul : la direction arrive de la table ci-dessous.
        "root": "flex fixed inset-0 w-full overflow-hidden",
    },
    "directions": {
        "row": "flex-row",
        "col": "flex-col",
        "row-reverse": "flex-row-reverse",
        "col-reverse": "flex-col-reverse",
    },
    # ⚠️ Les deux centrages portent ``safe``, comme dans ``ui.pane`` et
    # pour une raison PIRE : le cadre est ``overflow-hidden``, donc un
    # contenu centré plus haut que l'écran est coupé aux deux bouts et
    # **rien ne défile** pour aller le chercher. ``safe`` retombe sur
    # ``start`` quand ça déborde, et ne change rien le reste du temps.
    # Trois call-sites concernés dans tout le dépôt (mesuré le
    # 2026-08-24) : le geste est petit, le mode de panne ne l'est pas.
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
    "wrap": "flex-wrap",
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
