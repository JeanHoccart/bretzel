"""Default :class:`Grid` theme.

Pure layout primitive — root carries ``grid``, ``cols`` resolves to a
``grid-cols-N`` (or responsive variants) via the inline parser in
:mod:`bretzel.components.layout.grid.grid`, ``gap`` maps onto the
standard 5-palier scale (matching :class:`Flex` / :class:`VStack`).
"""

from __future__ import annotations

from typing import Any

GRID_THEME: dict[str, Any] = {
    "slots": {
        "root": "grid",
    },
    #: ``min_col=`` — la grille compte ses colonnes ELLE-MÊME.
    #:
    #: ``repeat(auto-fit, minmax(X, 1fr))`` est l'idiome CSS canonique de
    #: la grille responsive sans media query : le navigateur met autant de
    #: colonnes qu'il peut en donnant au moins ``X`` à chacune, et replie
    #: le reste. Précédent : le ``minChildWidth`` de Chakra, qui se traduit
    #: exactement en ceci.
    #:
    #: Le défaut qu'il ferme, mesuré le 2026-08-25 sur la rangée
    #: « Affichage » du CRM, dans un conteneur de 1024 px — la largeur de
    #: contenu réelle, barre latérale déduite ::
    #:
    #:     cols={"base":1,"md":2,"xl":4}   4 colonnes, cellules de 244 px,
    #:                                     le toggle_group (256) dehors de 11,9
    #:     min_col="16rem"                 3 colonnes de 331 px, rien dehors
    #:
    #: Et la moitié qu'on ne voit pas : un préfixe ``xl:`` lit la largeur
    #: de la FENÊTRE, pas celle de la grille. Rétrécir la fenêtre à 700 px
    #: transformait la grille en UNE colonne de 1024 — le conteneur n'avait
    #: pas bougé. ``auto-fit`` lit la place réelle, donc il n'a pas ce
    #: décalage.
    #:
    #: Table FERMÉE, comme ``grows`` : chaque valeur est une classe
    #: ENTIÈRE, donc visible au compilateur Tailwind de prod. Une largeur
    #: assemblée en f-string rendrait un HTML identique en dev et sans
    #: aucune règle en prod (memory ``project_assembled_tailwind_class_dev_only``).
    #:
    #: ``auto-fit`` et non ``auto-fill`` : le premier effondre les pistes
    #: vides, donc les colonnes présentes se partagent toute la place. Avec
    #: ``auto-fill``, deux champs dans un conteneur large resteraient
    #: collés à gauche avec du vide à droite.
    "min_cols": {
        "12rem": "grid-cols-[repeat(auto-fit,minmax(12rem,1fr))]",
        "16rem": "grid-cols-[repeat(auto-fit,minmax(16rem,1fr))]",
        "20rem": "grid-cols-[repeat(auto-fit,minmax(20rem,1fr))]",
        "24rem": "grid-cols-[repeat(auto-fit,minmax(24rem,1fr))]",
    },
    # Gap palier — same vocabulary as Flex / VStack so layouts mix and
    # match without surprise.
    "gaps": {
        "none": "gap-0",
        "xs": "gap-1",
        "sm": "gap-2",
        "md": "gap-4",
        "lg": "gap-6",
        "xl": "gap-8",
    },
}
