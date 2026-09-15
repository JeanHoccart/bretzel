"""Default :class:`Carousel` theme.

La piste est un conteneur **scroll-snap** : `overflow-x-auto snap-x
snap-mandatory`, chaque slide en `snap-start`. Le geste (swipe tactile
avec inertie, molette, clavier) est celui du navigateur — le thème ne
fait que le cadrer.

Deux détails du slot ``track`` ne sont pas cosmétiques :

- ``[scrollbar-width:none] [&::-webkit-scrollbar]:hidden`` masque la
  barre de défilement native. Sans elle, un carousel affiche une barre
  horizontale sous ses slides sur toute plateforme qui en dessine
  (Windows, Linux) — alors que le contrôle existe déjà sous forme de
  flèches et de puces. Les deux formes sont nécessaires, et Tailwind ne
  livre AUCUN utilitaire de scrollbar (c'est un plugin tiers) : d'où les
  variantes arbitraires plutôt qu'un ``scrollbar-none``, qui ne compile
  nulle part.
- ``scroll-smooth`` est ABSENT à dessein : ``goTo`` passe
  ``behavior`` explicitement, et le veut ``auto`` au premier accord
  (un carousel rendu à ``value=2`` doit s'afficher sur la slide 2, pas y
  défiler au chargement). Une déclaration CSS globale gagnerait sur
  l'argument et rendrait ce premier saut animé.

Slots :
- ``root``       : le wrapper — porte le scope ``bz-data`` ; colonne qui
  empile le viewport puis les puces
- ``viewport``   : le conteneur ``relative`` qui ANCRE les flèches. Sans
  lui elles se positionnent sur une hauteur qui COMPREND la rangée de
  puces, et tombent visiblement sous le centre de la piste
- ``track``      : le conteneur scrollable aimanté
- ``slide``      : le wrapper d'un enfant — c'est lui qui porte la
  largeur (donc ``per_view``) et le ``snap-start``
- ``arrow``      : les deux boutons, superposés aux bords
- ``arrow_prev`` / ``arrow_next`` : leur position latérale
- ``dots``       : la rangée de puces
- ``dot``        : une puce — ``data-selected`` pilote son état actif
"""

from __future__ import annotations

from typing import Any

#: La clé de ``THEME["responsive"]`` que ``_dots_hidden_class`` va lire.
#:
#: Une CONSTANTE et pas deux littéraux, pour la même raison que le
#: ``_field()`` du datatable : les deux moitiés doivent s'accorder, et
#: une clé recopiée des deux côtés se désaccorde en silence — le lookup
#: rend ``""``, plus rien n'est masqué, et les puces réapparaissent là où
#: ``per_view`` monte sans que rien n'échoue. Mutation-testé : c'était le
#: seul des cinq scénarios que la gate ne rattrapait pas, et le rendre
#: irreprésentable valait mieux que de l'y ajouter en cas particulier.
DOTS_HIDDEN = "dots_hidden"

CAROUSEL_THEME: dict[str, Any] = {
    "slots": {
        "root": "flex flex-col gap-3 w-full",
        # Le conteneur qui ANCRE les flèches. Elles étaient posées sur la
        # root, donc leur ``top-1/2`` prenait la hauteur de la rangée de
        # puces dans son calcul et elles tombaient sous le centre visuel
        # de la piste. C'est ce que ce slot existe pour corriger.
        "viewport": "relative",
        # ``bz-no-scrollbar`` est un hook du CSS FRAMEWORK, pas un
        # utilitaire Tailwind (cf. ``theme/css.py`` ``_NO_SCROLLBAR``, et
        # le même choix chez Sidebar avec ``bz-rail-scroll``).
        # ⚠️ La raison a changé le 2026-08-29 : les variantes arbitraires
        # équivalentes compilent très bien en PROD (vérifié au binaire) —
        # c'est le compilateur navigateur du mode dev qui ne les gère pas.
        # Le hook reste parce qu'il marche des deux côtés.
        "track": (
            "bz-no-scrollbar flex overflow-x-auto snap-x snap-mandatory"
        ),
        # ``shrink-0`` est ce qui empêche flexbox de compresser les slides
        # pour les faire toutes tenir — sans lui il n'y a rien à faire
        # défiler. La LARGEUR vient de ``per_view``, composée au render.
        "slide": "shrink-0 snap-start",
        "arrow": (
            "absolute top-1/2 -translate-y-1/2 z-10 "
            "flex items-center justify-center rounded-full "
            "bg-surface/90 backdrop-blur-sm text-text "
            "border-(length:--bz-stroke) border-text/10 shadow-md "
            "transition-[opacity,background-color] duration-200 ease-out "
            "not-disabled:cursor-pointer not-disabled:active:scale-95 "
            "not-disabled:hover:bg-surface "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-offset-2 "
            "focus-visible:ring-offset-background "
            "focus-visible:ring-(--bz-focus) "
            # Aux bords la flèche s'efface au lieu de disparaître : un
            # contrôle qui SORT du DOM fait sauter la mise en page et
            # laisse l'utilisateur chercher où il est parti.
            "disabled:opacity-0 disabled:pointer-events-none"
        ),
        "arrow_prev": "left-2",
        "arrow_next": "right-2",
        "dots": "flex items-center justify-center gap-2",
        "dot": (
            "rounded-full cursor-pointer bg-text/20 "
            "transition-[width,background-color] duration-200 ease-out "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-offset-2 "
            "focus-visible:ring-offset-background "
            "focus-visible:ring-(--bz-focus) "
            # La puce active s'ALLONGE en plus de se teinter : sur un
            # écran où la couleur passe mal (luminosité, daltonisme), la
            # forme reste lisible.
            "data-[selected=true]:bg-(--bz-solid)"
        ),
    },
    # Même échelle que Flex / Grid, à dessein : l'espacement entre deux
    # slides est le même geste de design qu'entre deux cellules, et un
    # `gap="md"` doit valoir la même chose partout.
    "gaps": {
        "none": "gap-0",
        "xs": "gap-1",
        "sm": "gap-2",
        "md": "gap-4",
        "lg": "gap-6",
        "xl": "gap-8",
    },
    # Les classes que ``_dots_hidden_class`` ressort PRÉFIXÉES par un
    # breakpoint (``md:hidden``). Dans le thème et pas en dur dans le
    # composant : c'est ce qui les rend visibles à la safelist, qui
    # clôture cette table sur les cinq breakpoints. Écrite en dur, la
    # classe n'existait littéralement nulle part — sauf ``md:hidden``,
    # présent par pur hasard dans une docstring, ce qui suffisait à
    # tromper ``test_emitted_classes_exist_in_source``.
    "responsive": {
        DOTS_HIDDEN: "hidden",
    },
    "sizes": {
        "xs": {
            "arrow": "w-7 h-7",
            "arrow_icon": "xs",
            "dot": "h-1 w-1 data-[selected=true]:w-4",
        },
        "sm": {
            "arrow": "w-8 h-8",
            "arrow_icon": "xs",
            "dot": "h-1.5 w-1.5 data-[selected=true]:w-5",
        },
        "md": {
            "arrow": "w-10 h-10",
            "arrow_icon": "sm",
            "dot": "h-2 w-2 data-[selected=true]:w-6",
        },
        "lg": {
            "arrow": "w-12 h-12",
            "arrow_icon": "md",
            "dot": "h-2.5 w-2.5 data-[selected=true]:w-8",
        },
        "xl": {
            "arrow": "w-14 h-14",
            "arrow_icon": "lg",
            "dot": "h-3 w-3 data-[selected=true]:w-10",
        },
    },
}
