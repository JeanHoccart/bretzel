"""Default :class:`Flex` theme.

Shared by :class:`VStack`, :class:`HStack` — the
shortcut classes inherit and only differ on which ``direction`` /
``axis`` defaults are baked in.
"""

from __future__ import annotations

from typing import Any

FLEX_THEME: dict[str, Any] = {
    "slots": {
        "root": "flex",
    },
    "directions": {
        "row": "flex-row",
        "col": "flex-col",
        "row-reverse": "flex-row-reverse",
        "col-reverse": "flex-col-reverse",
    },
    #: ⚠️ ``center`` porte ``safe``, comme dans :data:`PANE_THEME` et
    #: :data:`VIEWPORT_THEME`. Centrer un contenu plus haut que son cadre
    #: le fait déborder des DEUX côtés, et le défilement ne remonte jamais
    #: au-dessus de son origine : le haut devient **inatteignable**, pas
    #: « difficile à voir ». Mesuré le 2026-08-24 sur la page de connexion
    #: d'``examples/auth`` — contenu de 732 px dans 600, et à
    #: ``scrollTop = 0`` le contenu commençait à −108 px.
    #:
    #: Cette table-ci ne déclare aucun débordement, et c'est justement
    #: pourquoi elle en avait besoin : le défilement est posé au CALL-SITE
    #: (``ui.vstack(classes="… overflow-y-auto")``, la recette d'``outlet``
    #: et une zone de dépôt du CRM), donc aucune lecture locale ne pouvait
    #: rapprocher les deux. ``safe`` ne change RIEN quand le contenu tient
    #: — il n'y a donc aucune raison de centrer sans lui.
    #:
    #: Forme entre crochets et pas ``items-center-safe`` : cet utilitaire
    #: n'existe que depuis Tailwind 4.1, et le compilateur navigateur du
    #: mode dev peut être plus ancien.
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
    #: ``grow=`` — comment les enfants directs se partagent l'axe
    #: PRINCIPAL. Absent par défaut : une pile qui ne demande rien
    #: n'émet aucune de ces classes.
    #:
    #: Les clés nomment la BASE, pas un palier de l'échelle ``xs..xl``.
    #: C'est délibéré : ``size="md"`` et ``grow="md"`` auraient nommé deux
    #: choses sans rapport, et le lecteur d'un appel n'aurait eu aucun
    #: moyen de les départager. Ici ``grow="16rem"`` se lit tel qu'il agit.
    #:
    #: Table FERMÉE, et c'est ce qui la rend sûre : chaque valeur est une
    #: classe ENTIÈRE, donc visible au compilateur Tailwind de prod. Une
    #: base assemblée en f-string (``f"*:basis-{n}"``) rendrait un HTML
    #: identique en dev et sans style en prod
    #: (memory ``project_assembled_tailwind_class_dev_only``). Pour une
    #: valeur hors table, c'est ``classes=`` à l'appel — tier 2.
    "grows": {
        # Parts strictement égales : la base vaut zéro, donc le contenu
        # ne pèse pas dans le partage. C'est le ``<Group grow>`` de
        # Mantine, et le seul mode qui ignore ``wrap=``.
        "equal": "*:grow *:basis-0",
        "12rem": "*:grow *:basis-48",
        # La seule valeur que le dépôt utilisait vraiment : les trois
        # ``BAR_FIELD = "basis-64 grow"`` d'examples/ valaient celle-ci.
        "16rem": "*:grow *:basis-64",
        "20rem": "*:grow *:basis-80",
    },
}
