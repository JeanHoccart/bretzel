"""Default :class:`Resizable` / :class:`ResizablePanel` theme.

Le groupe est un conteneur **flex** dont chaque panneau porte
``flex-grow: <poids>`` en style inline, écrit par le runtime. Trois
détails du slot ``panel`` ne sont pas cosmétiques :

- ``basis-0`` est ce qui rend le partage proportionnel. Sans lui, la base
  d'un panneau est son contenu, donc deux panneaux à poids égal
  s'affichent inégaux dès que l'un est plus rempli que l'autre.
- ``min-w-0 min-h-0`` désactive le plancher automatique de flexbox
  (``min-width: auto`` sur un item flex). Sans eux, un panneau REFUSE de
  descendre sous la largeur de son contenu — une table large, et la
  poignée se bloque bien avant le minimum déclaré, sans que rien
  n'échoue.
- ``overflow-hidden`` garde le contenu dans sa boîte quand on rétrécit.
  C'est la contrepartie de ``min-w-0`` : ensemble, ils font qu'un
  panneau se réduit vraiment au lieu de déborder sur son voisin.

La poignée est une barre fine avec une zone de saisie PLUS LARGE qu'elle,
étendue par un pseudo-élément (``before:-inset-x-1``). Une barre de 1 px
serait conforme au dessin et impossible à attraper ; une barre épaisse
serait attrapable et laide. Les deux moitiés du problème n'ont pas la
même réponse, d'où la séparation visuel / zone de saisie.

``touch-none`` (``touch-action: none``) est OBLIGATOIRE et pas un
raffinement : sans lui, le navigateur interprète le glissement d'un doigt
sur la poignée comme un défilement de la page et n'envoie jamais les
``pointermove`` — le composant est alors inutilisable au tactile, en
silence, alors qu'il marche à la souris.

**L'état verrouillé est une BRANCHE, pas un variant négatif.** Les tokens
interactifs vivent dans ``handle_active``, que le composant n'ajoute que
si ``disabled`` est faux. Écrire ``not-aria-disabled:hover:…`` aurait
tenu en une chaîne, mais aurait fait reposer l'affordance sur une
composition de variants non vérifiée dans ce dépôt — et une classe qui
ne compile pas échoue en SILENCE, avec un HTML identique des deux côtés
(memory ``project_assembled_tailwind_class_dev_only``). Deux chaînes
statiques ne peuvent pas mentir.

Slots :
- ``root``           : le groupe flex — porte le scope ``bz-data``
- ``horizontal`` / ``vertical`` : la direction du groupe, un slot par axe
- ``panel``          : un panneau (``ui.resizable_panel``)
- ``handle``         : la poignée entre deux panneaux, au repos
- ``handle_active``  : ce que la poignée gagne quand elle est pilotable
- ``handle_locked``  : ce qu'elle gagne quand ``disabled=True``
- ``handle_h`` / ``handle_v`` : ce qui dépend de l'axe (curseur, sens de
  la zone de saisie)
- ``grip``           : la marque centrale, révélée au survol et au focus
"""

from __future__ import annotations

from typing import Any

RESIZABLE_THEME: dict[str, Any] = {
    "slots": {
        # ``w-full`` et pas ``w-fit`` : un splitter partage une place
        # donnée, il ne se dimensionne pas à son contenu — la règle
        # « root w-fit » des clusters sélecteurs (traps.md) vise les
        # contrôles enveloppables par un tooltip, pas les conteneurs de
        # mise en page.
        "root": "flex w-full",
        "horizontal": "flex-row",
        "vertical": "flex-col",
        "panel": "basis-0 min-w-0 min-h-0 overflow-hidden",
        "handle": (
            # ``group/rz`` nomme le groupe que le grip observe. Nommé et
            # pas nu : un Resizable IMBRIQUÉ ferait sinon réagir le grip
            # du parent au survol de l'enfant.
            "group/rz relative shrink-0 touch-none select-none "
            "bg-text/10 transition-colors duration-150 ease-out "
            "flex items-center justify-center "
            # La zone de saisie déborde la barre — pseudo-élément, donc
            # aucun nœud de plus dans le DOM et aucune boîte qui
            # participerait au flex.
            "before:absolute before:content-[''] "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-inset focus-visible:ring-(--bz-focus)"
        ),
        "handle_active": (
            "cursor-grab active:cursor-grabbing "
            "hover:bg-(--bz-solid)/40 active:bg-(--bz-solid)"
        ),
        # Pas de ``pointer-events-none`` à côté du curseur : un élément
        # qui ne reçoit aucun événement de pointeur ne peint jamais son
        # curseur, donc la classe serait présente et invisible. C'est le
        # bug que ``test_disabled_affordance`` verrouille, payé par Tree.
        "handle_locked": "cursor-not-allowed",
        "handle_h": "cursor-col-resize before:-inset-x-1 before:inset-y-0",
        "handle_v": "cursor-row-resize before:-inset-y-1 before:inset-x-0",
        # Le grip est TOUJOURS visible, et le survol ne fait que
        # l'appuyer. Le réflexe inverse (``opacity-0`` puis
        # ``group-hover:opacity-100``) est ce que fait la moitié de
        # l'écosystème et c'est un piège à deux détentes : un doigt ne
        # survole pas, donc au tactile la poignée n'annonce plus qu'elle
        # s'attrape — et le navigateur de l'utilisateur rapporte
        # justement ``any-hover: false`` (memory
        # ``project_user_browser_has_no_fine_pointer``). Gaté par
        # ``test_hover_only_controls_reachable``, qui a refusé la
        # première version de ce slot.
        "grip": (
            "pointer-events-none rounded-full bg-text/25 "
            "transition-colors duration-150 ease-out "
            "group-hover/rz:bg-text/60 group-focus-within/rz:bg-text/60"
        ),
    },
    # ``bar_*`` = l'ÉPAISSEUR de la barre, ``grip_*`` = la marque centrale.
    # Le suffixe dit l'axe du GROUPE : ``_h`` = panneaux côte à côte, donc
    # une barre verticale dont c'est la largeur qui varie.
    #: L'espace entre un panneau et la poignee — la GOUTTIERE. Meme
    #: echelle a six crans que ``ui.flex`` / ``ui.hstack`` / ``ui.vstack``
    #: / ``ui.grid`` / ``ui.carousel``, parce que c'est le meme espace :
    #: un conteneur flex qui separe ses enfants.
    #:
    #: ⚠️ **Recopiee, pas importee de ``FLEX_THEME``**, et c'est la
    #: convention du depot : un theme reste self-contained, on harmonise
    #: sans factoriser. L'accord des deux tables est tenu par
    #: ``tests/consistency/test_a_flex_container_spaces_its_children.py``,
    #: qui les compare cran par cran.
    #:
    #: Pourquoi c'est le GROUPE qui la porte, et pas le panneau : le
    #: padding d'un ancetre ne peut jamais creer d'espace A L'INTERIEUR
    #: du groupe. Mesure du 2026-08-23 sur la coque du CRM (parent en
    #: ``p-8``) : le panneau commencait bien a x=32, donc le padding
    #: l'atteignait — mais son contenu courait jusqu'a 384, ou la
    #: poignee commence. Zero. Seul le parent des panneaux sait ou est
    #: la poignee.
    "gaps": {
        "none": "gap-0",
        "xs": "gap-1",
        "sm": "gap-2",
        "md": "gap-4",
        "lg": "gap-6",
        "xl": "gap-8",
    },
    "sizes": {
        "xs": {
            "bar_h": "w-px",
            "bar_v": "h-px",
            "grip_h": "w-0.5 h-3",
            "grip_v": "h-0.5 w-3",
        },
        "sm": {
            "bar_h": "w-px",
            "bar_v": "h-px",
            "grip_h": "w-0.5 h-4",
            "grip_v": "h-0.5 w-4",
        },
        "md": {
            "bar_h": "w-0.5",
            "bar_v": "h-0.5",
            "grip_h": "w-1 h-6",
            "grip_v": "h-1 w-6",
        },
        "lg": {
            "bar_h": "w-1",
            "bar_v": "h-1",
            "grip_h": "w-1.5 h-8",
            "grip_v": "h-1.5 w-8",
        },
        "xl": {
            "bar_h": "w-1.5",
            "bar_v": "h-1.5",
            "grip_h": "w-2 h-10",
            "grip_v": "h-2 w-10",
        },
    },
}

RESIZABLE_PANEL_THEME: dict[str, Any] = {
    # Le panneau ne porte AUCUNE classe à lui : sa boîte est composée par
    # le groupe (slot ``panel``), qui est le seul à savoir s'il est en
    # ligne ou en colonne et quel poids lui revient. Un thème propre au
    # panneau donnerait deux auteurs à la même boîte.
    #
    # Le dict existe quand même — ``THEME`` est lu par ``_resolved_theme``
    # et par l'override utilisateur ``Theme(components={…})``, donc un
    # composant sans table de slots déclare la table VIDE plutôt que de
    # laisser le sentinel hérité.
    "slots": {
        "root": "",
    },
}
