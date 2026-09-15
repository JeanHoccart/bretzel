"""Un palier de texte reste lisible sur le palier de fond qui va avec.

C'est la gate que le chantier des jetons de couleur annonçait, et elle
n'était **pas écrivable avant lui** : tant qu'un thème écrivait
``text-{bg_color}``, la seule « version texte » d'une couleur était la
couleur elle-même. Il n'y avait rien à régler.

Ce que la mesure a dit, et ce qui a changé
-------------------------------------------

Avec ``--bz-text`` = la couleur brute (le cran 9 de Radix), **sept
couleurs sur onze passaient sous WCAG AA** sur leur propre fond, et
``warning`` en clair descendait à **1,88**. Ce n'était pas une régression
des paliers : un badge ``soft`` rendait déjà exactement cette paire
depuis toujours. Les paliers ont seulement rendu le défaut **mesurable**,
puis **réparable**.

``--bz-text`` mélange maintenant vers ``--color-text`` à 55 %, et le pire
contraste mesuré est **4,82**.

Pourquoi deux barres, et pas une
---------------------------------

``--bz-text`` porte du TEXTE : la barre est 4,5:1 (WCAG 1.4.3 AA).

``--bz-text-muted`` porte des **affordances** — les cinq sites du
catalogue sont des icônes et des boutons de fermeture, qui passent au
plein ``--bz-text`` au survol. La barre est celle des composants d'UI,
3:1 (WCAG 1.4.11), et il tient 3,41.

⚠️ **Il n'y a pas de place pour deux crans de texte tous deux à 4,5:1**
avec cette palette : aucun pourcentage ne clôt AA pour le second sans le
confondre avec le premier, parce que les teintes sources sont trop
claires — le jaune surtout. Radix s'en sort avec douze crans réglés à la
main **par teinte** ; ici on nomme la contrainte plutôt que de la
masquer, et c'est pourquoi la barre du second est écrite en clair.

Trois couleurs sont DÉGÉNÉRÉES, et c'est correct
-------------------------------------------------

``background``, ``surface`` et ``interface`` sont des fonds : leur
``--bz-text`` est un fond mélangé vers le texte, sur un ``--bz-bg`` qui
est ce même fond. Le rapport tourne autour de 1. Les exclure est exact —
ce ne sont pas des couleurs d'accent, et aucun composant ne s'en sert
pour écrire. Les **nommer** ici plutôt que d'abaisser le seuil est ce qui
empêche l'exclusion de couvrir une vraie faute.

Pourquoi ce calcul n'a pas besoin d'un navigateur
--------------------------------------------------

``color-mix(in srgb, A p%, B)`` est **exactement** l'interpolation
linéaire des trois octets — vérifié contre Chromium le 2026-08-30 sur
``primary`` dans les deux modes, au bit près. La gate peut donc vivre
dans la suite rapide au lieu d'attendre un créneau navigateur.
"""

from __future__ import annotations

import re

import pytest

from bretzel.theme import Theme
from bretzel.theme.bridges import readable_step_pct
from bretzel.theme.bridges import (
    COLOR_STEPS,
    CURRENT_COLOR_NAME,
    bridged_color_names,
)

#: Les fonds qui ne sont pas des couleurs d'ACCENT — cf. le docstring.
#:
#: ``black`` et ``white`` s'y ajoutent pour la même raison, un cran plus
#: loin : mélanger du blanc vers le texte donne du gris, sur un fond qui
#: est ce même blanc. Il n'y a pas de « texte blanc lisible sur du
#: blanc », et ce n'est pas un défaut à réparer.
_STRUCTURAL = frozenset(
    {"background", "surface", "interface", "black", "white"}
)

#: **Ce que la gate juge STRICTEMENT** : les onze slots sémantiques, le
#: vocabulaire du framework. C'est ce que Bretzel promet.
#:
#: Les 31 teintes de la palette livrée sont des hues brutes de Radix dont
#: on ne choisit pas la clarté : ``amber`` est un jaune très clair, donc
#: son cran 12 ne clôt pas AA (mesuré 4,06 en clair, contre un seuil de
#: 4,5). Les nommer ici plutôt que d'abaisser le seuil est ce qui
#: distingue « connu et mesuré » de « personne ne regarde ».

#: ``(couleur, mode, paire)`` → la valeur MESURÉE le 2026-08-30.
#:
#: Égalité stricte : une entrée qui s'améliore doit SORTIR, sinon la
#: table pourrit et masque la suivante. Le suivi est dans
#: ``.claude/work/todo.md``.
_KNOWN_BELOW: dict[tuple[str, str, str], float] = {
    # ⚠️ Les SIX entrées ``amber`` / ``yellow`` qui vivaient ici sont
    # parties le 2026-09-02, RÉPARÉES et non re-seuillées.
    #
    # La cause était la formule du cran 12 — « 55 % de la teinte + 45 %
    # du texte » — qui ne clôt pas 4,5:1 sur une teinte très claire
    # (mesuré : ``yellow`` à 3,76, son ``--bz-text-muted`` à 2,58 contre
    # une barre à 3). La décision annoncée était « une formule OU une
    # table par teinte » ; c'est une troisième voie, la même que
    # ``palette._readable_fg`` : la rampe RECULE vers le texte jusqu'à
    # franchir sa barre, au premier cran qui suffit. Une dérivation,
    # donc, pas une table réglée à la main — une couleur ajoutée demain
    # est servie sans qu'on y touche.
    #
    # ``amber`` sort à 50 % / 65 %, ``yellow`` à 45 % / 60 %. Les 41
    # autres couleurs sont OCTET POUR OCTET identiques.
    # ⚠️ Les CINQ entrées ``--bz-on-solid`` qui vivaient ici sont parties
    # le 2026-09-01, RÉPARÉES et non re-seuillées : ``muted`` 4,36 ·
    # ``pink`` 4,48 (les deux modes) · ``plum`` 4,33 (les deux modes).
    #
    # Elles n'étaient pas des paliers calculés mais le foreground que
    # ``palette.py`` dérive, donc une dette de la PALETTE — antérieure au
    # chantier des jetons, et révélée par lui. La cause n'était pas la
    # direction du foreground (le seuil de 0,179 choisit déjà le meilleur
    # des deux candidats pour les 31 couleurs) mais sa TEINTE, qui coûte
    # entre 0,40 et 0,61 de ratio. ``_readable_fg`` la recule désormais
    # jusqu'à ce que AA soit clos, et s'arrête au premier cran suffisant :
    # 73 des 78 couples sortent à l'octet près, seuls ces cinq bougent.
    #
    # Ne restent donc que les deux hues claires, dont la cause est
    # ailleurs — la formule du cran 12, pas l'algèbre du foreground.
}

#: ``color-mix(in srgb, var(--bz-src) 55%, var(--color-text))``
_MIX = re.compile(
    r"color-mix\(in srgb, var\(\{(\w+)\}\) (\d+)%, "
    r"(?:var\(\{(\w+)\}\)|(transparent))\)"
)
#: ``var({src})``
_PLAIN = re.compile(r"^var\(\{(\w+)\}\)$")


def _rgb(hex_value: str) -> tuple[int, int, int]:
    h = hex_value.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def steps_for(
    color: str, mode: str, *, palette: object | None = None
) -> dict[str, tuple[int, int, int] | None]:
    """Les douze paliers d'une couleur, calculés comme le navigateur.

    ``None`` = un palier translucide (``--bz-focus``), qu'on ne juge pas :
    un anneau n'a pas de texte dessus.

    ``palette`` sert au seul contrôle qui compare le calcul À UNE MESURE
    de navigateur : celle-là doit rejouer les couleurs qui étaient en
    place le jour du relevé, sinon repeindre le thème la rendrait fausse
    sans que le calcul ait bougé d'un iota. Partout ailleurs c'est le
    thème LIVRÉ qu'on juge, donc le défaut.
    """
    palette = palette if palette is not None else Theme().get_palette()
    # ⚠️ Les deux paliers de TEXTE portent un pourcentage DÉRIVÉ depuis
    # le 2026-09-02 (``bridges.readable_step_pct``) : la rampe recule
    # vers le texte jusqu'à franchir sa barre. La gate appelle la MÊME
    # fonction que l'émetteur de CSS — la re-implémenter ici ferait
    # juger une formule que le navigateur ne reçoit pas, ce qui est la
    # pire forme de gate verte.
    pcts = {
        champ: readable_step_pct(palette, color, champ)
        for champ in ("pct_text", "pct_muted")
    }
    named = {
        "src": _rgb(palette.resolve(color, mode).bg_hex),
        "fg": _rgb(palette.resolve(color, mode).fg_hex),
        "surface": _rgb(palette.resolve("surface", mode).bg_hex),
        "text": _rgb(palette.resolve("text", mode).bg_hex),
    }
    out: dict[str, tuple[int, int, int] | None] = {}
    for name, formula, _role in COLOR_STEPS:
        if (m := _PLAIN.match(formula)) is not None:
            out[name] = named[m.group(1)]
            continue
        m = _MIX.match(formula.format(
            src="{src}", fg="{fg}", surface="{surface}", text="{text}",
            **pcts,
        ))
        assert m is not None, f"formule non reconnue : {formula}"
        base, pct, toward, transparent = m.groups()
        if transparent:
            out[name] = None            # translucide : hors jugement
            continue
        p = int(pct) / 100
        a, b = named[base], named[toward]
        out[name] = tuple(round(p * x + (1 - p) * y) for x, y in zip(a, b))
    return out


def _luminance(rgb: tuple[int, int, int]) -> float:
    def channel(v: float) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


#: ``(palier de texte, palier de fond, seuil, pourquoi ce seuil)``
_PAIRS = (
    ("--bz-text", "--bz-bg", 4.5, "du TEXTE (WCAG 1.4.3 AA)"),
    ("--bz-text", "--color-surface", 4.5, "du TEXTE (WCAG 1.4.3 AA)"),
    ("--bz-text-muted", "--bz-bg", 3.0, "une AFFORDANCE (WCAG 1.4.11)"),
    ("--bz-on-solid", "--bz-solid", 4.5, "du TEXTE sur l'aplat"),
)

_COLORS = tuple(
    c for c in bridged_color_names(Theme().get_palette())
    if c not in _STRUCTURAL and c != CURRENT_COLOR_NAME
)


def test_the_sweep_is_not_vacuous() -> None:
    """Le plancher lit la découverte de CETTE gate.

    Si ``bridged_color_names`` cessait de rendre, ou si l'exclusion
    structurelle avalait tout, l'interdiction passerait au vert en ne
    jugeant rien. Mesuré le 2026-08-30 : 39 couleurs d'accent sur 43
    ponts.
    """
    assert len(_COLORS) >= 8, (
        f"seulement {len(_COLORS)} couleur(s) jugée(s) : {_COLORS}. "
        "Le balayage est cassé."
    )
    # Et les paliers doivent se CALCULER : une formule non reconnue ferait
    # lever ``steps_for``, mais un dict vide passerait inaperçu.
    computed = steps_for("primary", "light")
    assert len([v for v in computed.values() if v is not None]) >= 10, (
        f"seulement {len(computed)} paliers calculés — les formules de "
        "``COLOR_STEPS`` ne sont plus reconnues par le lecteur."
    )


def _below_floor(mode: str) -> dict[tuple[str, str, str], float]:
    """Les couples sous leur seuil, mesurés."""
    out: dict[tuple[str, str, str], float] = {}
    palette = Theme().get_palette()
    surface = _rgb(palette.resolve("surface", mode).bg_hex)
    for color in _COLORS:
        steps = steps_for(color, mode)
        for fg, bg, floor, _why in _PAIRS:
            back = surface if bg == "--color-surface" else steps[bg]
            assert steps[fg] is not None and back is not None
            got = contrast(steps[fg], back)
            if got < floor:
                out[(color, mode, f"{fg}/{bg}")] = round(got, 2)
    return out


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_every_text_step_is_readable(mode: str) -> None:
    failures = [
        f"{color}/{mode} : {pair} = {got:.2f} (seuil "
        f"{dict((f'{f}/{b}', fl) for f, b, fl, _ in _PAIRS)[pair]})"
        for (color, _m, pair), got in _below_floor(mode).items()
        if (color, mode, pair) not in _KNOWN_BELOW
    ]
    assert not failures, (
        "Ces paliers de texte ne sont pas lisibles :\n  "
        + "\n  ".join(failures)
        + "\n\nLes pourcentages de ``COLOR_STEPS`` sont RÉSOLUS contre ces "
        "seuils, pas choisis : ``--bz-text`` est le plus de teinte "
        "possible qui tienne 4,5:1. Si tu montes le pourcentage, tu "
        "reprends de la couleur et tu perds la lisibilité — c'est "
        "exactement l'arbitrage, et il est mesuré."
    )


def test_the_known_shortfalls_have_not_moved() -> None:
    """Égalité stricte dans les DEUX sens.

    Une entrée réparée doit sortir de la table, sinon celle-ci pourrit et
    masque la suivante ; une entrée qui EMPIRE doit se voir. C'est la même
    discipline que ``_KNOWN_MISSING`` dans la gate des classes émises.
    """
    measured = {**_below_floor("light"), **_below_floor("dark")}
    healed = {k: v for k, v in _KNOWN_BELOW.items() if k not in measured}
    assert not healed, (
        f"ces couples passent maintenant — retire-les de "
        f"``_KNOWN_BELOW`` : {sorted(healed)}"
    )
    worse = {
        k: (v, measured[k]) for k, v in _KNOWN_BELOW.items()
        if k in measured and measured[k] < v - 0.01
    }
    assert not worse, (
        f"ces couples ont EMPIRÉ (déclaré, mesuré) : {worse}. Une dette "
        "connue peut être payée, pas creusée."
    )


#: Les couleurs EN PLACE le jour du relevé Chromium (2026-08-30), rejouées
#: telles quelles. Les trois qui comptent sont celles que le mélange
#: consomme : la source, la surface et le texte.
#:
#: ⚠️ Sans ce gel, repeindre le thème par défaut rendrait la mesure fausse
#: alors que le CALCUL n'aurait pas bougé — et le réflexe serait alors de
#: recopier la nouvelle sortie Python dans l'attendu, ce qui ferait
#: comparer Python à Python. C'est arrivé le 2026-09-13, quand les neutres
#: sont passés au chaud et l'accent à l'indigo.
_AS_MEASURED_2026_08_30 = {
    "semantic": {"primary": "#2f5fd0", "surface": "#ffffff", "text": "#0f172a"},
    "semantic_dark": {"surface": "#0f172a", "text": "#f8fafc"},
}


def test_the_calculator_matches_the_browser() -> None:
    """Mutation : le calcul PYTHON doit reproduire ``color-mix``.

    Toute la gate repose là-dessus. Les valeurs de référence viennent de
    Chromium, relevées le 2026-08-30 — si l'interpolation dérive, les
    contrastes deviennent une fiction interne cohérente.
    """
    p = Theme(**_AS_MEASURED_2026_08_30).get_palette()
    assert steps_for("primary", "light", palette=p)["--bz-text"] == (33, 63, 133)
    assert steps_for("primary", "dark", palette=p)["--bz-text"] == (137, 165, 228)
    # et le cas sans mélange
    assert steps_for("primary", "light", palette=p)["--bz-solid"] == (47, 95, 208)


def test_the_detector_still_bites() -> None:
    """Mutation, dans les deux sens, sur la mesure de contraste."""
    # il mord : du gris moyen sur du blanc ne passe pas
    assert contrast((150, 150, 150), (255, 255, 255)) < 4.5
    # il épargne : du noir sur du blanc, c'est 21
    assert contrast((0, 0, 0), (255, 255, 255)) > 20
    # symétrique — l'ordre des arguments ne doit rien changer
    assert contrast((33, 63, 133), (255, 255, 255)) == contrast(
        (255, 255, 255), (33, 63, 133)
    )
