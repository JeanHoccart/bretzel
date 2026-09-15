"""Les ponts de couleur — douze paliers dérivés d'une seule teinte source.

Un **pont** est une classe CSS qui, posée sur un élément, y installe les
douze variables dont les thèmes composants se servent pour se peindre ::

    <span class="bz-c-error bg-(--bz-bg) text-(--bz-text)">

Le pont fait la traduction ; le thème ne parle plus que le vocabulaire
des paliers. C'est ce qui remplace les gabarits ``bg-{bg_color}``, dont
le défaut est structurel : ``bg-{bg_color}`` n'est pas une classe mais
une **demi-classe**, invisible au compilateur Tailwind, qu'il fallait
donc clôturer à la main — chaque forme × chaque couleur. Mesuré le
2026-08-30 : 72 formes × 42 couleurs = 3 791 classes en safelist, soit
576 Ko sur 717, **80 % de la feuille**. Douze ponts pèsent 156 lignes.

Douze **paliers**, 43 **ponts** : les onze couleurs sémantiques, plus
``current`` (cf. :data:`CURRENT_COLOR_NAME`), dont la source est la
couleur héritée et non un nom de thème.

Ce que les paliers rendent possible, et qui était impossible
------------------------------------------------------------

1. **Teindre une zone entière.** ``bz-c-error`` sur un conteneur teinte
   tout ce qu'il contient, sans qu'aucun enfant ne le sache. Aujourd'hui
   il faut passer ``color="error"`` à chacun.
2. **Repeindre UNE instance.** ``style="--bz-solid: #b91c1c"`` change les
   onze paliers de ce composant-là. Aucun ``classes=`` ne sait faire ça :
   il faudrait réécrire chaque état, survol et focus compris.
3. **Un composant TIERS qui se teinte.** Il écrit ``bg-(--bz-bg)``, une
   classe complète et littérale, donc le compilateur la voit. Rien à
   déclarer, rien à clôturer.

Pourquoi onze noms et pas des numéros
--------------------------------------

Les noms disent l'**intention**, pas la propriété CSS ni un rang :
c'est la convention que le dépôt suit déjà pour ses foregrounds
(``--color-primary-foreground``), et celle de shadcn. On écrit
``bg-(--bz-bg-hover)`` parce qu'on veut le survol d'un fond, pas parce
qu'on veut « le cran 4 ».

L'échelle elle-même est celle de Radix, dont les douze crans sont
définis par leur RÔLE. Le dépôt l'avait déjà réinventée, mal : ses 302
gabarits se réduisaient à 6 propriétés et 22 couples (propriété,
opacité), dont quinze utilisés trois fois ou moins. La leçon mesurée
est que **l'opacité n'est pas une valeur absolue, c'est un cran relatif
au substrat** — un survol posé sur un fond à ``/15`` et un survol posé
sur un aplat plein ne peuvent pas porter la même opacité. Des paliers
absolus font disparaître le problème.

Le sombre est gratuit
----------------------

Aucune règle ``.dark`` ici, et ce n'est pas un oubli. Les formules
partent de ``--color-<nom>``, ``--color-surface`` et ``--color-text``,
qui sont **déjà** redéfinis dans le bloc ``.dark`` du thème. Un pont
écrit une fois se réévalue donc tout seul de l'autre côté : mesuré, la
rampe s'inverse (``--bz-bg`` passe de L* 0.951 à 0.186) sans une seule
classe ``dark:``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from functools import lru_cache
from typing import Final

from bretzel.theme.palette import Palette, ThemeError
from bretzel.theme.tokens import (
    PALETTE_CLASS_PREFIX,
    SEMANTIC_COLOR_NAMES,
)

#: Le préfixe d'une classe-pont. ``bz-c-primary``, ``bz-c-error``…
BRIDGE_CLASS_PREFIX = "bz-c-"

#: Les deux variables INTERNES au pont : la teinte source et son
#: foreground. Elles n'apparaissent dans aucun thème de composant — un
#: thème lit les paliers, jamais la source. Les exposer serait rouvrir
#: la porte qu'on ferme : ``bg-(--bz-src)/15`` réinventerait l'opacité
#: comme façon de fabriquer un palier.
SOURCE_VAR = "--bz-src"
SOURCE_FOREGROUND_VAR = "--bz-src-foreground"

#: Les douze paliers, dans l'ordre de l'échelle. La valeur est la formule,
#: écrite avec ``{src}``, ``{fg}``, ``{surface}`` et ``{text}``.
#:
#: ``--bz-text`` et ``--bz-text-muted`` MÉLANGENT VERS LE TEXTE, et c'est
#: le seul changement visuel délibéré du chantier. Ils valaient la
#: couleur brute (le cran 9 de Radix) et son délavé vers la surface
#: jusqu'au 2026-08-30 : mesuré, **sept couleurs sur onze passaient sous
#: WCAG AA** sur leur propre fond, et ``warning`` en clair descendait à
#: **1,88**. Ce n'était pas une régression des paliers — un badge ``soft``
#: rendait déjà exactement cette paire — mais il n'existait aucune façon
#: d'écrire « la version TEXTE de cette couleur » : il n'y avait que la
#: couleur.
#:
#: Les deux pourcentages sont RÉSOLUS, pas choisis. Sur 8 couleurs × 2
#: modes × 2 fonds :
#:
#:   --bz-text        55 %  le plus de teinte possible en tenant 4,5:1
#:                          (à 60 % le pire tombe à 4,26). Pire mesuré :
#:                          4,82, contre 1,88 avant.
#:   --bz-text-muted  70 %  visiblement plus clair que le précédent, et
#:                          il tient 3,41 — la barre des AFFORDANCES
#:                          (WCAG 1.4.11 : 3:1 pour un composant d'UI).
#:                          Ses cinq sites sont des icônes et des boutons
#:                          de fermeture, qui passent au plein au survol.
#:
#: ⚠️ **Il n'y a pas de place pour deux crans de texte tous deux à
#: 4,5:1** avec cette palette : aucun pourcentage entre 70 et 100 ne
#: clôt AA pour le second, parce que les teintes sources sont trop
#: claires (le jaune surtout). Radix s'en sort avec douze crans réglés à
#: la main par teinte ; ici on nomme la contrainte au lieu de la
#: masquer.
#:
#: ``in srgb`` — et le cadrage disait ``in oklab``. C'est une mesure qui
#: a tranché, pas un goût.
#:
#: Mélanger vers ``--color-surface`` en sRGB **est** l'opération qu'une
#: opacité fait déjà : ``bg-error/50`` composite en sRGB. Les deux
#: écritures sont donc algébriquement la même chose, et la migration ne
#: déplace aucune couleur. En oklab, non : mesuré le 2026-08-30 sur les
#: 8 couleurs × 2 modes, **aucun pourcentage ne reproduit une opacité** —
#: le meilleur ajustement de ``/50`` est 54 %, et il laisse encore ΔE 3,9
#: en moyenne et 11,5 au pire. L'écart dépend de la TEINTE, donc il ne se
#: règle pas avec un nombre.
#:
#: Ça se voyait : à 50 % en oklab la bordure du badge ``outline`` rendait
#: plus pâle que son texte dans les deux modes — exactement le défaut que
#: la phase 0 avait corrigé à l'œil douze heures plus tôt.
#:
#: La raison écrite au cadrage — « un mélange en sRGB traverse le gris et
#: fait boueux au milieu de l'échelle » — est vraie de deux couleurs
#: CHROMATIQUES qu'on mélange. Ces formules-ci mélangent vers la surface,
#: c'est-à-dire vers du blanc ou du presque-noir : il n'y a pas de gris à
#: traverser.
#:
#: ⚠️ Une échelle perceptivement uniforme reste un meilleur objectif de
#: DESIGN, et c'est ce qui rendra les crans réguliers. Mais c'est un
#: changement visuel, donc il se décide et se montre — comme les trois
#: opacités de la phase 0 — pas en passant pendant une migration dont le
#: contrat est l'égalité.
#:
#: La dépendance à ``color-mix`` est déjà prise en production —
#: ``feedback/notification/theme.py`` l'écrit littéralement depuis des
#: mois.
COLOR_STEPS: tuple[tuple[str, str, str], ...] = (
    # (nom du palier, formule, ce à quoi il sert)
    (
        "--bz-bg",
        "color-mix(in srgb, var({src}) 10%, var({surface}))",
        "fond d'un composant teinté (Radix 3)",
    ),
    (
        "--bz-bg-hover",
        "color-mix(in srgb, var({src}) 20%, var({surface}))",
        "son survol (Radix 4)",
    ),
    (
        "--bz-bg-active",
        "color-mix(in srgb, var({src}) 30%, var({surface}))",
        "son état sélectionné / actif (Radix 5)",
    ),
    (
        "--bz-border",
        "color-mix(in srgb, var({src}) 35%, var({surface}))",
        "bordure au repos (Radix 6-7)",
    ),
    (
        "--bz-border-hover",
        "color-mix(in srgb, var({src}) 50%, var({surface}))",
        "bordure au survol / au focus (Radix 7)",
    ),
    (
        "--bz-focus",
        "color-mix(in srgb, var({src}) 40%, transparent)",
        "anneau de focus (Radix 8)",
    ),
    (
        "--bz-focus-soft",
        "color-mix(in srgb, var({src}) 30%, transparent)",
        "anneau de focus SOUTENU — celui d'un champ, allumé pendant "
        "toute la frappe, donc plus discret",
    ),
    (
        "--bz-solid",
        "var({src})",
        "aplat plein (Radix 9)",
    ),
    (
        "--bz-solid-hover",
        "color-mix(in srgb, var({src}) 88%, var({text}))",
        "son survol (Radix 10)",
    ),
    (
        "--bz-on-solid",
        "var({fg})",
        "ce qui s'écrit SUR l'aplat",
    ),
    (
        "--bz-text-muted",
        "color-mix(in srgb, var({src}) {pct_muted}%, var({text}))",
        "texte accentué atténué (Radix 11) — une AFFORDANCE, pas du "
        "corps de texte : la barre est 3:1 (WCAG 1.4.11), tenue à 3,41",
    ),
    (
        "--bz-text",
        "color-mix(in srgb, var({src}) {pct_text}%, var({text}))",
        "texte accentué (Radix 12) — lisible, la barre est 4,5:1, "
        "tenue à 4,82 au pire",
    ),
)

#: Les noms de paliers seuls — ce qu'un thème de composant a le droit
#: d'écrire.
STEP_NAMES: tuple[str, ...] = tuple(name for name, _f, _r in COLOR_STEPS)


#: Le douzième pont, dont la source n'est pas une couleur NOMMÉE.
#:
#: ``color="current"`` est le défaut de ``ui.icon``, ``ui.spinner`` et
#: ``ui.breadcrumb``, et il pilote toute la barre du datatable : c'est la
#: valeur de ``color=`` la plus répandue du framework, et sans elle la
#: phase 3 buterait sur son composant le plus utilisé. ``currentColor``
#: est une vraie valeur CSS, donc les onze formules marchent dessus sans
#: rien changer.
#:
#: ⚠️ ``--bz-on-solid`` est le seul choix MOU des douze ponts :
#: ``current`` n'a pas de compagnon ``-foreground``, donc on prend le
#: fond de page — ce qu'on écrit sur un aplat fait de la couleur héritée.
#: C'est un choix inerte aujourd'hui : les quatre composants qui
#: défaillent sur ``current`` n'écrivent **aucun** ``{fg_color}``
#: (vérifié), donc rien ne le lit.
CURRENT_COLOR_NAME = "current"
CURRENT_COLOR_SOURCE = "currentColor"
CURRENT_COLOR_FOREGROUND = "var(--color-background)"

#: Les paliers que le pont ``current`` ne DÉRIVE pas — il les rend tels
#: quels.
#:
#: ⚠️ Sans cette exception, ``current`` traverse les onze formules comme
#: une couleur ordinaire, et ``--bz-text`` vaut
#: ``color-mix(in srgb, currentColor 55%, var(--color-text))``. Autrement
#: dit : **une icône par défaut ne prend PAS la couleur de son parent,
#: elle en prend 55 % tirés vers le texte de page.** Sur un fond neutre
#: la couleur héritée EST celle du texte de page, donc le mélange est
#: l'identité et personne ne voit rien. Sur un aplat — un bouton
#: ``solid``, un badge, une alerte — les deux divergent, et l'icône sort
#: d'une autre couleur que le mot qu'elle accompagne.
#:
#: Mesuré le 2026-09-09 sur un bouton primaire d'``examples/kanban`` :
#: libellé ``rgb(19 22 22)``, icône ``rgb(17 22 31)``. C'est aussi ce que
#: la docstring d'``icon/theme.py`` promettait depuis toujours — « the
#: icon inherits its parent's text colour » — sans que le CSS le tienne.
#:
#: Seul ``--bz-text`` est concerné : c'est le seul palier qu'un composant
#: à ``color="current"`` écrit sur du texte. ``--bz-bg`` &co restent des
#: dérivés, et ils ont un sens sur ``currentColor`` comme sur le reste.
CURRENT_COLOR_IDENTITY_STEPS: frozenset[str] = frozenset({"--bz-text"})


def bridge_class(color: str) -> str:
    """Le nom de la classe-pont d'une couleur. ``primary`` → ``bz-c-primary``."""
    return f"{BRIDGE_CLASS_PREFIX}{color}"


def _color_var(name: str, *, semantic: bool) -> str:
    """La variable Tailwind qui porte cette couleur.

    Les slots sémantiques sont émis sans préfixe (``--color-primary``),
    les couleurs nommées avec celui de la palette (``--color-ui-tomato``)
    — c'est la convention de ``tailwind._emit_block``, pas un choix
    refait ici.
    """
    stem = name if semantic else f"{PALETTE_CLASS_PREFIX}{name}"
    return f"--color-{stem}"


@lru_cache(maxsize=8)
def bridged_color_names(palette: Palette) -> tuple[str, ...]:
    """Les couleurs qui reçoivent un pont.

    **Exactement ce que ``color=`` accepte** : les onze slots
    sémantiques, ``current``, et toute la palette — celle que le
    framework livre comme celle que l'app ajoute.

    La règle n'est pas « douze », c'est **la couverture**. Un pont
    manquant n'est pas une économie, c'est un composant qui rend sans
    couleur : ses paliers sont indéfinis, donc ses propriétés invalides.
    Mesuré le 2026-08-30 en migrant le Badge — ``ui.badge(color="tomato")``
    perdait tout son style, et 21 composants faisaient rougir
    ``test_palette_color_is_prefixed``.

    Le compte de **douze** de la décision du 2026-08-30 reste vrai, et il
    arrive tout seul : il découle de la taille de la PALETTE, pas d'une
    liste tenue ici. Le jour où les 31 couleurs par défaut seront
    retirées (phase 5 du chantier), cette fonction rendra douze noms sans
    qu'on touche une ligne — et une app qui déclare ``brand`` aura son
    pont, exactement comme aujourd'hui.

    Le coût de la couverture est petit devant ce qu'elle remplace :
    43 ponts pèsent ~33 Ko contre les 576 Ko de la clôture forme ×
    couleur.

    Pourquoi elle est mémoïsée
    ---------------------------

    Le corps balaie toute la palette — ``envelope_dict()`` recalcule un
    ``bg_class`` et un ``fg_class`` pour chacune de ses ~42 couleurs.
    C'est bon marché une fois, et cette fonction est appelée par
    :func:`bretzel.components.base._wiring._refuse_unknown_color`, donc
    **une fois par composant coloré**. Mesuré le 2026-09-05 sur un
    chargement dur du playground : 135 660 appels à ``bg_class`` pour
    cinq rendus de ``/tabs``, et 19 % du temps de la requête passé à
    répondre 1 615 fois à la même question.

    Le pari est sûr, contrairement à celui d'``escape_attr`` : une
    :class:`~bretzel.theme.palette.Palette` est construite une fois au
    démarrage, ses tables ne sont écrites que dans son ``__init__``, et
    ``Theme.get_palette`` rend toujours la même instance. Le taux de
    réutilisation n'est donc pas « élevé », il est **total** — et
    ``test_the_color_bridge_memo_still_pays`` le vérifie, parce que le
    jour où une palette serait rebâtie par requête, rien ne casserait :
    la page resterait juste, elle serait juste redevenue lente.

    A/B alterné dans le même process, min de 14 : ``/tabs``
    86,4 → 68,2 ms (−21 %), ``/datatable`` 330,1 → 198,3 ms (−40 %).
    """
    names = list(SEMANTIC_COLOR_NAMES) + [CURRENT_COLOR_NAME]
    names += sorted(set(palette.envelope_dict()) - set(SEMANTIC_COLOR_NAMES))
    return tuple(names)


#: Les deux paliers de TEXTE et la barre que chacun doit franchir.
#:
#: ``--bz-text`` est du corps de texte accentué : WCAG AA, 4,5:1.
#: ``--bz-text-muted`` est une AFFORDANCE et pas du corps de texte, donc
#: sa barre est celle des composants (WCAG 1.4.11), 3:1.
_TEXT_STEP_TARGETS: Final[dict[str, tuple[str, float]]] = {
    "pct_text": ("--bz-text", 4.5),
    "pct_muted": ("--bz-text-muted", 3.0),
}

#: Les pourcentages de DÉPART — la rampe qu'on veut, quand elle est
#: lisible. Ce sont les valeurs qui étaient écrites en dur dans les
#: formules jusqu'au 2026-09-02.
_TEXT_STEP_BASE: Final[dict[str, int]] = {"pct_text": 55, "pct_muted": 70}

#: De combien on recule à chaque cran, et jusqu'où. Reculer, c'est mettre
#: MOINS de teinte et plus de texte — donc plus de contraste, dans les
#: deux modes (mesuré : le sombre a 14 à 17 de marge, il n'y a rien à y
#: casser).
_TEXT_STEP_DOWN: Final[int] = 5
_TEXT_STEP_FLOOR: Final[int] = 25

#: Les slots de SURFACE, écartés de la dérivation.
#:
#: ⚠️ **Ils échouent la même barre, et c'est une découverte du
#: 2026-09-02 — pas une exemption de confort.** Mesurés, ils
#: reculeraient eux aussi : ``surface`` et ``white`` de 55 à 35 %,
#: ``background`` et ``interface`` à 40 %, ``black`` à 50 %.
#:
#: Ils sont écartés parce que **la gate ne les juge pas** —
#: ``test_the_colour_steps_stay_readable`` tient 37 couleurs, et aucune
#: de ces cinq n'en fait partie. Les faire bouger changerait
#: l'apparence de composants sur une barre à laquelle personne ne les a
#: jamais tenus, et sans qu'aucune mesure ne dise si c'est un progrès :
#: un ``color="white"`` sert un badge blanc sur une bannière sombre, pas
#: du texte sur la page, donc le fond contre lequel il faut mesurer
#: n'est pas celui que cette dérivation suppose.
#:
#: C'est donc une question ouverte, pas un oubli — consignée dans
#: ``.claude/work/todo.md``. L'élargir demande d'abord de décider
#: CONTRE QUOI un slot de surface se mesure.
_SURFACE_SLOTS: Final[frozenset[str]] = frozenset({
    "background", "surface", "interface", "white", "black",
})


def readable_step_pct(palette: Palette, color: str, champ: str) -> int:
    """Le pourcentage de teinte du palier ``champ``, reculé s'il le faut.

    Pourquoi ça existe (2026-09-02)
    --------------------------------
    Une formule unique sert les 43 couleurs : le cran 12 vaut « 55 % de
    la teinte + 45 % du texte ». Sur une teinte très claire ça ne clôt
    pas 4,5:1 — mesuré, ``yellow`` en clair rendait **3,76**, et son
    ``--bz-text-muted`` **2,58** contre une barre à 3.

    La décision annoncée était « une formule OU une table par teinte ».
    C'est une troisième voie, et c'est la même que
    ``palette._readable_fg`` : on garde la formule, et on la RECULE vers
    le texte jusqu'à ce que la barre soit franchie, en s'arrêtant au
    premier cran qui suffit. Ce n'est donc pas une table réglée à la
    main — c'est une dérivation, qui sert une couleur ajoutée demain
    sans qu'on y touche.

    Reculer augmente le contraste dans les DEUX modes, ce qui est ce qui
    permet à une règle CSS unique de servir les deux : le texte est par
    construction la couleur qui contraste le plus avec le fond, donc en
    mettre plus ne peut pas rapprocher. Vérifié en sombre, où la marge
    est de 14 à 17.

    ⚠️ La mesure se fait sur le thème COURANT. Un thème qui change son
    ``text`` ou son ``background`` change le résultat — c'est voulu, et
    c'est mieux que le pourcentage figé d'avant, qui ne s'y adaptait
    pas du tout.
    """
    base = _TEXT_STEP_BASE[champ]
    _nom, cible = _TEXT_STEP_TARGETS[champ]
    if color == CURRENT_COLOR_NAME or color in _SURFACE_SLOTS:
        # ``currentColor`` n'a pas de valeur résoluble : rien à mesurer,
        # donc rien à reculer. Les slots de SURFACE, eux, sont écartés
        # pour une autre raison — cf. ``_SURFACE_SLOTS``.
        return base
    for pct in range(base, _TEXT_STEP_FLOOR - 1, -_TEXT_STEP_DOWN):
        if all(
            _step_ratio(palette, color, mode, pct) >= cible
            for mode in ("light", "dark")
        ):
            return pct
    return _TEXT_STEP_FLOOR


def _step_ratio(palette: Palette, color: str, mode: str, pct: int) -> float:
    """Le contraste du palier contre le FOND de page, à ce pourcentage."""
    from bretzel.theme.palette import _contrast_ratio, _parse_hex

    try:
        src = _parse_hex(palette.resolve(color, mode).bg_hex)
    except ThemeError:
        return 21.0          # couleur inconnue ici : le juge, c'est ailleurs
    text = _parse_hex(palette.resolve("text", mode).bg_hex)
    fond = _parse_hex(palette.resolve("background", mode).bg_hex)
    part = pct / 100
    melange = tuple(
        round(part * a + (1 - part) * b)
        for a, b in zip(src, text, strict=True)
    )
    return _contrast_ratio(melange, fond)  # type: ignore[arg-type]


def generate_color_bridges(
    palette: Palette, *, names: Sequence[str] | None = None
) -> str:
    """Le bloc CSS des ponts — une règle par couleur.

    ``names`` force la liste (les tests s'en servent) ; par défaut c'est
    :func:`bridged_color_names`.
    """
    colors = tuple(names) if names is not None else bridged_color_names(palette)
    semantics = set(SEMANTIC_COLOR_NAMES) | {CURRENT_COLOR_NAME}
    lines: list[str] = [
        "/* --- Les ponts de couleur — cf. bretzel/theme/bridges.py --- */"
    ]
    for color in colors:
        lines.extend(
            _bridge_rule(color, semantic=color in semantics, palette=palette)
        )
    return "\n".join(lines) + "\n"


def _bridge_rule(
    color: str, *, semantic: bool, palette: Palette
) -> Iterable[str]:
    if color == CURRENT_COLOR_NAME:
        source, foreground = CURRENT_COLOR_SOURCE, CURRENT_COLOR_FOREGROUND
    else:
        var = _color_var(color, semantic=semantic)
        source, foreground = f"var({var})", f"var({var}-foreground)"
    yield f".{bridge_class(color)} {{"
    yield f"  {SOURCE_VAR}: {source};"
    yield f"  {SOURCE_FOREGROUND_VAR}: {foreground};"
    for name, formula, _role in COLOR_STEPS:
        if color == CURRENT_COLOR_NAME and name in CURRENT_COLOR_IDENTITY_STEPS:
            # La couleur héritée, telle quelle. Cf.
            # ``CURRENT_COLOR_IDENTITY_STEPS`` pour la mesure.
            yield f"  {name}: var({SOURCE_VAR});"
            continue
        value = formula.format(
            src=SOURCE_VAR,
            fg=SOURCE_FOREGROUND_VAR,
            surface="--color-surface",
            text="--color-text",
            pct_text=readable_step_pct(palette, color, "pct_text"),
            pct_muted=readable_step_pct(palette, color, "pct_muted"),
        )
        yield f"  {name}: {value};"
    yield "}"
