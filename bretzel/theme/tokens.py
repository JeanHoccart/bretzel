"""Semantic / palette name catalogue + type literals.

Pure constants — no class, no I/O. Imported by every other theme
module that needs to validate a color name or list the slots.

Two distinct concepts (cf. ``.claude/bretzel/theme.md`` § *Mental model*) :

- **Semantic** : 11 fixed slots known to every component. The values
  change ; the names are part of the framework grammar.
- **Palette** : an open list of named hex colors. The user can add,
  remove or override entries — no framework-level meaning attached.
"""

from __future__ import annotations

from typing import Final, Literal

# ───────────────────────────────────────────────────────────────────────────
# Breakpoints — l'échelle Tailwind, source unique
# ───────────────────────────────────────────────────────────────────────────
#
# Elle vit ICI et non dans ``components/base/responsive.py`` (qui la
# ré-exporte) parce que la SAFELIST en a besoin : ``responsive_classes``
# peut préfixer n'importe quelle classe graduée par n'importe lequel de
# ces breakpoints, donc la clôture de la safelist porte sur les deux
# axes. Or ``theme`` n'a pas le droit d'importer ``components`` — c'est
# le sens du DAG, vérifié par ``import-linter``. Deux tuples parallèles
# auraient dérivé : un breakpoint ajouté d'un côté aurait produit des
# classes que le compilateur ne connaît pas, sans erreur.

BREAKPOINTS: Final[tuple[str, ...]] = ("sm", "md", "lg", "xl", "2xl")


# ───────────────────────────────────────────────────────────────────────────
# Semantic slots — 11, fixed, framework-known
# ───────────────────────────────────────────────────────────────────────────


SEMANTIC_COLOR_NAMES: Final[tuple[str, ...]] = (
    "primary",
    "secondary",
    "success",
    "error",
    "warning",
    "info",
    "background",
    "surface",
    "interface",
    "text",
    "muted",
)


SemanticColors = Literal[
    "primary",
    "secondary",
    "success",
    "error",
    "warning",
    "info",
    "background",
    "surface",
    "interface",
    "text",
    "muted",
]


# ───────────────────────────────────────────────────────────────────────────
# Font slots — 3, fixed, and deliberately Tailwind's own three
# ───────────────────────────────────────────────────────────────────────────
#
# Ce ne sont pas des noms inventés : ``--font-sans`` / ``--font-serif`` /
# ``--font-mono`` sont les tokens que Tailwind v4 définit lui-même, et
# ``--default-font-family: var(--font-sans)`` de son préréglage fait que
# redéfinir ``sans`` change la fonte de la page ENTIÈRE via le preflight
# (``html { font-family: var(--default-font-family, …) }``, vérifié dans le
# CSS compilé). Les utilitaires ``font-sans`` / ``font-serif`` / ``font-mono``
# suivent gratuitement — et ``Heading`` écrit déjà ``font-sans`` en dur dans
# son thème, donc les titres suivent sans qu'un composant bouge.
#
# **Pas de quatrième slot** (``display``, ``heading``…) : il faudrait
# l'inventer côté Tailwind ET réécrire le thème de Heading, alors qu'une
# fonte de titre distincte s'obtient déjà par
# ``Theme(components={"heading": {"slots": {...}}})``. Arbitré le
# 2026-08-16.
#
# **Aucun défaut n'est recopié ici.** Une section ``fonts`` vide n'émet
# rien et les piles de Tailwind tiennent. Recopier ``ui-sans-serif,
# system-ui, …`` dans ce fichier créerait un doublon dont la seule
# évolution possible est de diverger de l'amont, en silence.

FONT_SLOT_NAMES: Final[tuple[str, ...]] = ("sans", "serif", "mono")


# ───────────────────────────────────────────────────────────────────────────
# L'échelle — sa BASE, pas un multiplicateur
# ───────────────────────────────────────────────────────────────────────────
#
# Deux jetons, et ce sont ceux de Tailwind v4 : ``--spacing``, l'unité dont
# toute utilitaire d'espacement dérive (``h-10`` vaut
# ``calc(var(--spacing) * 10)``, comme ``p-4``, ``gap-2`` et ``w-6``), et
# ``--text-<palier>``, que les utilitaires ``text-*`` lisent.
#
# ⚠️ **Bretzel pose ses propres valeurs, et c'est le sujet.** Ce n'est pas le
# doublon d'amont que les fontes évitent : une valeur recopiée ne peut que
# diverger, une valeur CHOISIE dit quelque chose. Tailwind vise des pages —
# contrôle à 40 px, texte médian à 16 px — et Bretzel sert à faire des
# OUTILS, qui montrent beaucoup dans peu de place. Hériter de l'échelle
# d'un document était un défaut par omission, pas une décision (2026-09-13).
#
# Le repère : les défauts d'Ant Design sont ``controlHeight`` 32 et
# ``fontSize`` 14, à peu près où ceux-ci atterrissent, et son préréglage
# « compact » descend ENCORE en dessous. C'était donc le défaut de Bretzel
# qui était l'exception.
#
# **Pourquoi la base et non un curseur.** Cette place a dit « la densité n'est
# PAS ouverte » jusqu'au 2026-09-13, au motif que chaque composant a déjà son
# ``size=`` et qu'un multiplicateur global serait une seconde manière de faire
# la même chose. Le motif tient toujours — et sa propre clause de sortie
# disait quoi ouvrir le jour où le besoin remonterait : *la BASE de cette
# échelle, pas un axe neuf*. C'est ce qui est ici. ``size=`` continue de
# choisir un palier ; le thème décide de quelle échelle.
#
# Une app qui veut l'échelle d'un DOCUMENT la reprend par la même porte :
# ``Theme(spacing="0.25rem", text={"base": "16px", …})``. Il n'y a pas de
# préréglage pour ça — ce serait un second nom pour les valeurs de Tailwind,
# donc le doublon d'amont qu'on vient d'écarter.
#
# Le besoin est remonté deux fois, mesuré : ``examples/kanban`` puis
# ``examples/ecole`` ont chacun réécrit la même correction — la première en
# retaillant onze composants un par un, ce qui en a laissé onze autres au
# défaut et mis quatre hauteurs de champ sur un même écran. Une liste écrite
# à la main est une liste de composants qu'on a pensé à citer.
#
# **Le marché est unanime sur le mécanisme, pas sur le nom.** Ant Design
# livre un préréglage entier (``compactAlgorithm``) piloté par des jetons de
# graine — ``sizeUnit`` 4, ``sizeStep``, ``controlHeight`` 32, ``fontSize``
# 14 ; Radix Themes et Reflex exposent un pourcentage (``scaling``) ; Mantine
# un ``scale`` plus ses dicts ``fontSizes``/``spacing``. Tous déplacent une
# base, aucun ne retaille composant par composant. Les noms retenus ici sont
# ceux de Tailwind parce que ce sont les jetons RÉELLEMENT lus — même raison
# que les trois slots de fonte, et même bénéfice : rien à traduire.

#: Le pas d'espacement livré, et **3 px pile** — le chiffre rond est le
#: sujet. À ``0.205rem``, ``h-10`` valait 32,8 px : un palier entre deux
#: pixels, que les navigateurs arrondissent différemment selon la structure
#: du contrôle (hauteur sur l'élément bordé, ou sur son enfant). Mesuré sur
#: ``examples/ecole`` : 31 px d'un côté, 33 de l'autre, pour des champs que
#: rien ne distingue dans le code. À 3 px, chaque cran tombe sur un entier.
DEFAULT_SPACING: Final[str] = "0.1875rem"

#: Le même pas en PIXELS, pour les apps qui doivent CALCULER — la hauteur
#: d'un bloc de N heures dans une grille se compose d'un nombre de crans, et
#: une classe Tailwind ne sait pas additionner (cf.
#: ``examples/ecole/features/emploi_du_temps.py``). Deux autorités sur une
#: même grandeur ne se composent pas : l'accord des deux est gaté.
DEFAULT_SPACING_PX: Final[int] = 3

#: Les paliers de texte livrés — un cran sous ceux de Tailwind
#: (12/14/16/18/20/24), qui est la mesure que deux apps avaient trouvée
#: séparément avant que le framework tranche.
#:
#: ⚠️ **Les paliers d'affiche EN FONT PARTIE, et ça a été mesuré.** Cette
#: place a dit « ``3xl`` et au-delà ne sont pas posés : aucun chrome ne les
#: écrit ». C'était faux, et le prix a été un défaut : l'échelle de taille
#: d'``ui.icon`` monte jusqu'à ``text-6xl`` (``xl`` vaut ``text-4xl``,
#: ``2xl`` vaut ``text-6xl``), et ``ui.file_upload`` écrit ``text-5xl``.
#: Un chevron resté à 36 px dans un bouton descendu à 33 sortait de
#: **1,5 px** — invisible à toute lecture de classes, trouvé par
#: ``probe_calendar_width`` en français ET en anglais.
#:
#: C'est la forme générale du piège, et elle vaut au-delà d'ici : laisser
#: une moitié d'une grandeur sur l'échelle d'amont et déplacer l'autre,
#: ce sont deux autorités qui ne se composent pas. Une BOÎTE mesurée en
#: crans et un GLYPHE mesuré en paliers de texte doivent bouger ensemble.
DEFAULT_TEXT: Final[dict[str, str]] = {
    "xs": "11px",
    "sm": "13px",
    "base": "14px",
    "lg": "16px",
    "xl": "18px",
    "2xl": "22px",
    "3xl": "27px",
    "4xl": "32px",
    "5xl": "43px",
    "6xl": "54px",
}

#: Les paliers de ``--text-*``, c'est-à-dire ceux que Tailwind v4 définit.
#: Fermé comme les fontes : ``Theme(text={"md": …})`` n'est pas une extension
#: mais un jeton que rien ne lira — l'échelle de Tailwind dit ``base`` là où
#: un ``size=`` de composant dit ``md``, et c'est le composant qui traduit.
#:
#: ⚠️ La ligne d'en dessous du palier reste hors de portée : 39 chaînes de
#: thème écrivent une taille littérale (``text-[10px]``, ``h-[1.75rem]``).
#: Déplacer la base ne les bouge pas — c'est la dette « ``size=`` n'atteint
#: pas tous les slots » de ``todo.md``, pas un trou de ce paramètre-ci.
TEXT_SLOT_NAMES: Final[tuple[str, ...]] = (
    "xs",
    "sm",
    "base",
    "lg",
    "xl",
    "2xl",
    "3xl",
    "4xl",
    "5xl",
    "6xl",
    "7xl",
    "8xl",
    "9xl",
)


# ───────────────────────────────────────────────────────────────────────────
# Shape — les trois familles de rayon
# ───────────────────────────────────────────────────────────────────────────
#
# Émises dans ``@theme`` comme ``--radius-<famille>``, donc Tailwind v4 en
# fabrique de vraies utilitaires : ``rounded-box``, ``rounded-field``,
# ``rounded-selector``, avec leurs variantes de coin (``rounded-l-field``).
# Vérifié au binaire de prod le 2026-08-30.
#
# **Pourquoi trois familles et pas une échelle.** Le dépôt en avait six
# (xl 46×, full 31×, md 28×, lg 12×, sm 7×, 2xl 3×) et rien n'écrivait
# pourquoi un composant prenait l'un plutôt que l'autre. Un curseur
# unique posé sur six jetons sans logique ne règle rien de décidable ;
# trois familles NOMMÉES rendent la question décidable au call-site.
#
# La coupe est celle de daisyUI 5 (``--radius-box`` / ``--radius-field``
# / ``--radius-selector``), seul système du marché à cloisonner par
# famille — Radix, Material 3, Ant Design, Fluent, Bootstrap et Mantine
# utilisent tous une échelle globale plus une assignation par composant.
#
# ⚠️ **``rounded-full`` n'entre dans aucune famille, et c'est la règle la
# plus importante ici.** Le rond d'un switch, d'un radio, d'un spinner ou
# d'une barre de progression est leur FORME, pas leur style : les
# équarrir ferait lire le switch comme une case à cocher. Radix Themes
# arrive à la même conclusion et l'écrit — chez eux « full » rend un
# bouton en pilule mais ne rendra jamais une checkbox ronde, « to prevent
# any confusion between it and a Radio ». 32 slots restent donc en dur.

#: Les trois familles, et ce qu'elles veulent dire :
#:
#: - ``box`` — l'élément CONTIENT d'autres éléments (carte, panneau,
#:   dialogue, surface).
#: - ``field`` — un contrôle qu'on vise, avec son propre cadre (bouton,
#:   champ, déclencheur de picker).
#: - ``selector`` — une petite marque, ou un contrôle IMBRIQUÉ dans un
#:   autre (case à cocher, badge, croix d'effacement, pastille).
SHAPE_SLOT_NAMES: Final[tuple[str, ...]] = ("box", "field", "selector")

#: Les valeurs de départ. Choisies pour être celles que la majorité des
#: slots portait déjà : 12 px, c'est ``rounded-xl``, que 46 slots
#: écrivaient ; 6 px, c'est ``rounded-md``, celui de la case à cocher et
#: du badge. Le regroupement déplace 26 slots sur 96, tous de 6 px au
#: plus — le recensement est dans le message de commit.
#: La largeur de trait, et ses deux crans dérivés.
#:
#: **Un seul réglage**, contrairement au rayon : le marché est unanime là
#: où il diverge sur la forme. daisyUI (``--border``), Ant Design
#: (``lineWidth``) et Bootstrap (``--bs-border-width``) exposent une
#: largeur globale ; Radix, Mantine, Material 3 et shadcn n'en exposent
#: aucune. Personne ne cloisonne, et le dépôt donne la raison : son
#: vocabulaire de bordure est DÉJÀ décidable — 1 px partout, 2 px pour
#: l'emphase (le bouton `outline`, l'onglet actif), 4 px pour un accent
#: latéral (le bandeau, la citation), 0 pour retirer.
#:
#: D'où les deux crans DÉRIVÉS plutôt que réglés : si l'emphase était un
#: nombre fixe, pousser la base à 2 px la ferait disparaître — le bouton
#: `outline` cesserait de se distinguer du bouton plein. Ici le rapport
#: tient à toutes les valeurs.
#:
#: ⚠️ ``--bz-stroke`` et pas ``--bz-border`` : ce dernier est DÉJÀ un
#: palier de couleur des ponts (:mod:`bretzel.theme.bridges`), et
#: ``border-(--bz-border)`` compile en ``border-color``. La collision
#: aurait été silencieuse dans un sens (une largeur lue comme couleur) et
#: destructrice dans l'autre. Le nom vient de Fluent 2, qui appelle ses
#: jetons de largeur ``strokeWidth*``.
DEFAULT_STROKE: Final[str] = "1px"

DEFAULT_SHAPE: Final[dict[str, str]] = {
    "box": "0.75rem",
    "field": "0.75rem",
    "selector": "0.375rem",
}


# ───────────────────────────────────────────────────────────────────────────
# Default palette — 31 named hex shipped with Bretzel
# ───────────────────────────────────────────────────────────────────────────


DEFAULT_PALETTE_NAMES: Final[tuple[str, ...]] = (
    # Neutrals.
    "gray",
    "mauve",
    "slate",
    "sage",
    "olive",
    "sand",
    # Reds & pinks.
    "tomato",
    "red",
    "ruby",
    "crimson",
    "pink",
    "plum",
    # Purples & blues.
    "purple",
    "violet",
    "iris",
    "indigo",
    "blue",
    "cyan",
    "sky",
    # Greens.
    "teal",
    "jade",
    "green",
    "grass",
    # Warms.
    "yellow",
    "amber",
    "orange",
    "gold",
    "bronze",
    "brown",
    # Extremes.
    "black",
    "white",
)


PaletteColors = Literal[
    "gray", "mauve", "slate", "sage", "olive", "sand",
    "tomato", "red", "ruby", "crimson", "pink", "plum",
    "purple", "violet", "iris", "indigo", "blue", "cyan", "sky",
    "teal", "jade", "green", "grass",
    "yellow", "amber", "orange", "gold", "bronze", "brown",
    "black", "white",
]  # fmt: skip


# ───────────────────────────────────────────────────────────────────────────
# Convenience union — every color the resolver can recognise
# ───────────────────────────────────────────────────────────────────────────


# In practice users pass plain ``str`` — the literal types are
# documentation hints for IDEs / mypy. The runtime checks the value
# against the actual palette at render time.
AnyColor = SemanticColors | PaletteColors | str


# ───────────────────────────────────────────────────────────────────────────
# Internal CSS prefix for palette colors
# ───────────────────────────────────────────────────────────────────────────


# Palette names share a global CSS namespace with Tailwind's stock
# utilities (``bg-red-500``, …). Prefixing our colors with ``ui-``
# avoids any clash without leaking the prefix to the user — the
# framework rewrites ``color="red"`` to ``bg-ui-red`` at render time.
PALETTE_CLASS_PREFIX: Final[str] = "ui-"


# Foreground class is derived by appending this suffix to the class
# stem (``primary`` → ``primary-foreground``).
FOREGROUND_SUFFIX: Final[str] = "-foreground"
