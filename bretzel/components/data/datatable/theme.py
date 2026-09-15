"""Default :class:`Datatable` theme.

The Datatable owns almost no visual identity of its own : the table is a
composed :class:`~bretzel.components.data.table.Table`, the search box a
composed ``ui.input``, the pager a composed ``ui.pagination``, the sort
control a composed ``ui.button``. Each of those already carries its own
look, and re-styling them here would fork the design system.

What is left for this theme is the **chrome around them** — the toolbar
strip, the footer strip, and the scroll frame — plus the two things the
composed pieces cannot express on their own : the sticky header and the
sort-direction affordance on the active column.

Slots :
- ``root``        : the vertical stack (toolbar / table / footer)
- ``toolbar``     : the strip above the table (search box, filter triggers)
- ``search``      : width constraint on the composed search input
- ``export``      : pushes the CSV control to the far end of the toolbar
- ``footer``      : the strip below the table (result count + pager)
- ``footer_info`` : the "N results" text
- ``head_button`` : layout override for the composed sort button, so a
  ``ui.button`` sits in a ``<th>`` like a header label rather than like a
  button (full width, inherited type scale, no padding of its own)
- ``head_static`` : the same metrics for a NON-sortable header, so the two
  kinds of column align on the same baseline

The per-column filter has NO slot here : it is a ``ui.combobox``
(``multiple``, ``bulk_actions``, custom ``trigger=``), so its panel, its
tick-list, its search field and its header bar are the combobox's own
theme. Everything that used to live here — ``filter_panel``,
``filter_option``, ``filter_rule``, ``filter_search``, ``filter_trigger``,
``head_group`` — was a second copy of it.

Modifiers :
- ``sticky``      : pins the ``<thead>`` while the body scrolls. Only ever
  applied together with a ``max_height``, because a sticky header with
  nothing to scroll under it does nothing at all.
"""

from __future__ import annotations

from typing import Any

DATATABLE_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            "bz-datatable "  # audit marker — cf. tests/audit/checklist.py
            "flex flex-col gap-3 w-full"
        ),
        "toolbar": "flex items-center gap-2 flex-wrap",
        # The search box shouldn't span the table — a full-width text
        # field reads as "type a lot here", which is the wrong promise
        # for a filter. D'où le plafond à `max-w-xs` (320 px).
        #
        # `flex-1` et PAS `w-full`, et c'est la moitié qui compte. Sous
        # `flex-wrap`, un débordement fait RETOURNER À LA LIGNE, il ne
        # compresse pas : la recherche restait donc à 320 px à toutes les
        # largeurs (mesuré de 1400 à 700 px — pas un pixel cédé) et
        # c'est l'export qui se payait une rangée entière dès ~1000 px.
        # `flex-1` (base 0) la fait tenir sur la ligne quoi qu'il arrive
        # puis grandir dans la place restante, donc c'est ELLE qui absorbe
        # l'étroitesse — c'est le contrôle le plus élastique de la barre,
        # les autres ont une largeur que leur texte impose.
        #
        # Le plancher vit dans `sizes[<size>]["search"]` : sous ~190 px
        # (à `md`) le placeholder se tronque et le champ ne dit plus ce
        # qu'il cherche, et un élastique SANS plancher rend un champ de
        # 40 px avant de consentir à passer à la ligne. Il se met à
        # l'échelle parce qu'un tableau `lg` écrit plus gros : le même
        # nombre de pixels n'y tient pas le même nombre de caractères.
        "search": "flex-1 max-w-xs",
        # ``ml-auto`` : l'export part au bout de la barre. Ce n'est pas
        # de la mise en page décorative — c'est ce qui sépare les deux
        # natures de contrôle qui la peuplent. À gauche on RESTREINT
        # (recherche, filtres, remise à zéro) ; à droite on SORT les
        # données. Collé aux filtres, l'export se lisait comme l'un
        # d'eux. C'est LA place à documenter : les call-sites lisent ce
        # slot par son nom et n'ont rien à redire.
        #
        # ``ml-auto`` et PAS le ``justify-between`` que ``footer`` emploie
        # deux lignes plus bas, alors que c'est le même travail. La
        # différence est ``flex-wrap`` : le footer a exactement deux
        # enfants, la toolbar en a un nombre variable qui doit rester
        # groupé. Sous ``justify-between`` la barre écarterait la
        # recherche et les filtres à chaque bout dès qu'il reste de la
        # place. ``ml-auto`` sur le dernier enfant pousse à droite de LA
        # LIGNE OÙ IL ATTERRIT — mesuré de 1280 à 390 px : au large il
        # termine la rangée des filtres, à l'étroit il occupe seule la
        # sienne, toujours à ras du bord droit. La lecture « deux
        # moitiés » vaut donc tant que la barre tient sur une ligne, et
        # dégénère proprement — pas en désordre — quand elle passe à la
        # ligne.
        "export": "ms-auto",
        "footer": "flex items-center justify-between gap-3 flex-wrap",
        # Type scale lives in ``sizes[<size>]["info"]`` — a ``text-xs``
        # baked here would be a size the ``size=`` prop could never move.
        "footer_info": "text-muted tabular-nums",
        # A ``ui.button`` in a ``<th>`` has to stop looking like a button
        # and start looking like a header : the cell already owns the
        # padding and the type scale, so the button contributes only the
        # hit area and the affordances (hover, focus ring, keyboard) a
        # bare ``<th>`` has none of.
        #
        # ``px-1 -mx-1`` on purpose : the horizontal padding gives the
        # hover wash some body around the text, and the negative margin
        # cancels it for alignment — so a sortable header still starts on
        # the same pixel as the plain header above it in the column.
        # ``hover:!text-text`` is the affordance that says clickable ; the
        # colour at REST comes from the parent (``color="current"``).
        # ⚠️ La casse suit ``Table.head_cell`` — les deux DOIVENT rester
        # d'accord, sinon une colonne triable et sa voisine statique ne se
        # lisent plus comme la même ligne d'en-tête. L'uppercase en 10-12 px
        # a été retiré des deux le 2026-08-06 : illisible, et c'est
        # exactement ce que le spec V1 demandait de remplacer par de la
        # casse normale. Ce qui distingue un en-tête d'une donnée est
        # désormais le POIDS et la couleur, pas la taille ni les capitales
        # — la convention des bibliothèques actuelles.
        # Ni ``flex-1`` ni ``min-w-0`` : ils servaient le ``head_group``
        # qui partageait la cellule entre le titre et un déclencheur de
        # filtre. Le filtre est parti dans la barre d'outils, le parent
        # est redevenu un ``<th>`` nu (``table/theme.py`` § head_cell,
        # sans ``display:flex``), et les deux tokens n'agissaient plus
        # sur rien.
        "head_button": (
            "!justify-start !h-auto !px-1 !py-0.5 -mx-1 "
            "!rounded !text-sm !font-semibold !normal-case !tracking-normal "
            "not-disabled:hover:!text-text gap-1"
        ),
        # Non-sortable headers keep the same box so a sortable and a
        # static column don't sit two pixels apart.
        "head_static": "inline-flex items-center py-0.5",
    },
    # The composed children's own size tokens, derived from the
    # Datatable's — a literal ``Pagination(size="sm")`` would leave the
    # pager the same height on a ``size="lg"`` table. Every row carries
    # the same keys on purpose : a missing one falls back silently,
    # which is how the frozen-child bug started.
    #
    # ⚠️ The sort BUTTON is deliberately absent from this table, and its
    # ``size="xs"`` at the call site is a baselined constant. Table fixes
    # the header type scale (``text-xs uppercase`` in ``head_cell``, the
    # same at every density), so a sortable header that grew with ``size``
    # would no longer match the NON-sortable header beside it. Measured
    # before deciding : with the layout overrides below in place, deriving
    # the button's size changed nothing at all in the browser — one
    # rendered value across sm/md/lg. A derivation that moves nothing is
    # worse than an honest constant, because the test that "proves" it
    # only sees the class string.
    "sizes": {
        # Un SEUL token `toolbar` alimente TOUS les contrôles de la barre
        # — recherche, filtres, export — et il descend tel quel dans le
        # `size=` du combobox de filtre, dont la propre table `sizes`
        # met à l'échelle son panneau, ses options et sa recherche. Avant :
        # la recherche prenait `size`, la pastille `toolbar_button` et la
        # recherche interne `filter_check`, donc trois échelles côte à
        # côte sur un tableau `lg`.
        "sm": {"pager": "sm", "info": "text-xs", "toolbar": "sm",
               "search": "min-w-44"},
        "md": {"pager": "sm", "info": "text-xs", "toolbar": "sm",
               "search": "min-w-48"},
        "lg": {"pager": "md", "info": "text-sm", "toolbar": "md",
               "search": "min-w-56"},
    },
    "modifiers": {
        # ``sticky`` rides on the composed Table via ``classes=`` — the
        # ``<thead>`` is inside it, so the selector reaches down. ``z-10``
        # keeps it above the scrolling rows ; the background is opaque so
        # rows don't show through as they pass under.
        "sticky": (
            "overflow-y-auto "
            "[&_thead]:sticky [&_thead]:top-0 [&_thead]:z-10 "
            "[&_thead]:bg-surface"
        ),
    },
    # The sort arrow's three positions. Kept as icon NAMES (not classes)
    # because the affordance is an icon swap, not a style swap.
    "sort_icons": {
        "asc": "arrow-up",
        "desc": "arrow-down",
        # Neutral : a dimmed both-ways arrow that says "this is sortable"
        # without claiming a direction.
        "": "chevrons-up-down",
    },
}
