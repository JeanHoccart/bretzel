"""Une FORME se nomme : famille de rayon, ou jeton de trait.

Le dépôt écrivait six jetons de rayon — ``xl`` 46 fois, ``full`` 31,
``md`` 28, ``lg`` 12, ``sm`` 7, ``2xl`` 3 — et rien nulle part ne disait
pourquoi un composant prenait l'un plutôt que l'autre. Ce n'est pas un
défaut de discipline : il n'y avait aucune question à laquelle répondre.
Un thème neuf copiait le voisin, et le voisin avait copié le sien.

Depuis le 2026-08-30 il y a trois familles, et elles posent une question
décidable au moment d'écrire le slot :

- ``rounded-box`` — l'élément CONTIENT d'autres éléments.
- ``rounded-field`` — un contrôle qu'on vise, avec son propre cadre.
- ``rounded-selector`` — une petite marque, ou un contrôle IMBRIQUÉ.

Ce que cette gate refuse
-------------------------

Un ``rounded-<jeton d'échelle>`` dans un thème du framework. Les seules
sorties sont ``rounded-full`` et ``rounded-none``, et elles sont
délibérées : le rond d'un switch, d'un radio, d'un spinner ou d'une barre
de progression est leur FORME. Les équarrir ferait lire le switch comme
une case à cocher — Radix Themes arrive à la même conclusion et l'écrit
noir sur blanc : chez eux ``radius="full"`` rend un bouton en pilule mais
ne rendra **jamais** une checkbox ronde, *« to prevent any confusion
between it and a Radio »*.

⚠️ Elle balaie AUSSI ce qui n'est pas un ``theme.py``. Trois classes
vivantes échappaient au thème le jour de la migration — deux dans
``calendar.py``, une dans le tooltip des charts en JS — et une gate qui
n'aurait lu que les thèmes les aurait laissées dériver là où personne ne
regarde.
"""

from __future__ import annotations

import re

import pytest

from bretzel.theme import Theme
from bretzel.theme.tokens import DEFAULT_STROKE, SHAPE_SLOT_NAMES
from tests.consistency._discovery import (
    PACKAGE_DIR,
    PACKAGE_FLOOR,
    RUNTIME_SRC_DIR,
    parsed_sources,
    theme_slot_strings,
    theme_sources,
)

#: Preuve de morsure : la famille qui ne sert à personne est morte.
MUTATION_PROOF = "test_every_family_is_actually_used"

#: Les jetons d'échelle de Tailwind — ceux qui n'ont pas de sens ici.
_SCALE = ("xs", "sm", "md", "lg", "xl", "2xl", "3xl", "4xl")

#: Ce qui reste licite, et pourquoi.
#:
#: ``full`` : la forme. ``none`` : l'angle vif volontaire (une cellule de
#: calendrier au milieu d'une plage). Aucune des deux ne se règle, donc
#: aucune des deux n'appartient à une famille.
_SHAPES = ("full", "none")

_RAW = re.compile(
    r"\brounded-(?:[trbl]{1,2}-)?(" + "|".join(_SCALE) + r")\b"
)
_FAMILY = re.compile(
    r"\brounded-(?:[trbl]{1,2}-)?(" + "|".join(SHAPE_SLOT_NAMES) + r")\b"
)

#: Plancher de DÉCOUVERTE : combien de fichiers portent réellement une
#: classe de famille. 48 mesurés le 2026-08-30. C'est celui-ci qui compte
#: — débrancher l'expression régulière laisserait 359 fichiers lus et zéro
#: classe vue, et la gate passerait au vert en ne jugeant rien.
_CARRIERS_FLOOR = 40

#: Les fichiers dont la PROSE cite un jeton brut pour une raison
#: historique, sans qu'aucune classe ne le porte. Le balayage lit du
#: texte, donc il faut les nommer.
_PROSE_ONLY = {
    "bretzel/theme/tokens.py",       # explique d'où viennent les valeurs
    "bretzel/theme/sources.py",      # exemple de classe statique
}


def _sources() -> list:
    return parsed_sources(PACKAGE_DIR, floor=PACKAGE_FLOOR)


def _js_sources() -> list[tuple[str, str]]:
    """Le runtime aussi : il écrit des classes, donc il peut dériver."""
    return [
        (p.relative_to(PACKAGE_DIR.parent).as_posix(),
         p.read_text(encoding="utf-8-sig"))
        for p in sorted(RUNTIME_SRC_DIR.glob("*.js"))
    ]


def _corpus() -> list[tuple[str, str]]:
    files = [
        (s.path.relative_to(PACKAGE_DIR.parent).as_posix(), s.text)
        for s in _sources()
    ]
    return files + _js_sources()


_CORPUS = _corpus()


def test_the_sweep_is_not_vacuous() -> None:
    """Le plancher lit la DÉCOUVERTE, pas le nombre de fichiers."""
    carriers = [name for name, text in _CORPUS if _FAMILY.search(text)]
    assert len(carriers) >= _CARRIERS_FLOOR, (
        f"{len(carriers)} fichiers seulement portent une classe de famille "
        f"(plancher {_CARRIERS_FLOOR}) — l'expression régulière ou le "
        f"chemin est cassé, pas le dépôt."
    )
    assert any(name.endswith(".js") for name in carriers), (
        "aucun fichier JS dans le balayage : le runtime écrit pourtant des "
        "classes, et c'est là qu'une dérive se voit le moins."
    )


def test_no_raw_radius_token_in_the_framework() -> None:
    guilty: list[str] = []
    for name, text in _CORPUS:
        if name in _PROSE_ONLY:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if match := _RAW.search(line):
                guilty.append(f"{name}:{line_no} — rounded-{match.group(1)}")
    assert not guilty, (
        "un rayon doit nommer sa FAMILLE, pas un cran d'échelle :\n"
        + "\n".join(f"    {g}" for g in guilty)
        + "\n  Les trois familles sont "
        + ", ".join(f"`rounded-{f}`" for f in SHAPE_SLOT_NAMES)
        + ".\n  Les deux sorties sont `rounded-full` (la forme d'un switch, "
        "d'un radio, d'un spinner) et `rounded-none` (l'angle vif "
        "volontaire)."
    )


@pytest.mark.parametrize("family", SHAPE_SLOT_NAMES)
def test_every_family_is_actually_used(family: str) -> None:
    """Une famille que personne n'écrit est un jeton mort.

    C'est la moitié LICITE de la preuve : refuser les jetons bruts ne dit
    rien si les remplaçants ne sont posés nulle part. Une migration à
    moitié faite passerait l'interdiction et laisserait des composants
    sans rayon du tout.
    """
    pattern = re.compile(rf"\brounded-(?:[trbl]{{1,2}}-)?{family}\b")
    users = sorted(
        {name for name, text in _CORPUS if pattern.search(text)}
    )
    assert len(users) >= 3, (
        f"`rounded-{family}` n'est écrit que dans {users} — une famille "
        f"qui ne sert à (presque) personne ne mérite pas d'être une "
        f"famille."
    )


@pytest.mark.parametrize("shape", _SHAPES)
def test_the_two_exits_are_still_taken(shape: str) -> None:
    """``full`` et ``none`` doivent rester UTILISÉS.

    Sans ce contrôle, l'interdiction ci-dessus resterait verte le jour où
    quelqu'un « harmoniserait » le switch en famille — exactement la
    régression que cette gate existe pour empêcher.
    """
    pattern = re.compile(rf"\brounded-(?:[trbl]{{1,2}}-)?{shape}\b")
    users = [name for name, text in _CORPUS if pattern.search(text)]
    assert users, (
        f"plus personne n'écrit `rounded-{shape}` : soit la sortie a été "
        f"supprimée par erreur, soit le balayage ne voit plus rien."
    )


def test_the_three_variables_reach_the_stylesheet() -> None:
    """Les trois familles n'existent QUE si le thème les émet.

    C'est le mode d'échec silencieux de tout ce dispositif : sans
    ``--radius-box`` dans ``@theme``, Tailwind ne fabrique pas
    l'utilitaire ``rounded-box``. La classe reste dans le HTML, aucune
    règle ne la porte, et les 31 slots qui l'écrivent perdent leur rayon
    d'un coup — sans erreur, sans avertissement.
    """
    css = Theme().generate_css()
    for family in SHAPE_SLOT_NAMES:
        assert f"--radius-{family}:" in css, (
            f"`--radius-{family}` n'est pas émis dans la feuille : "
            f"`rounded-{family}` ne compilera pas, et tout ce qui l'écrit "
            f"perdra son rayon en silence."
        )


def test_a_theme_can_move_a_whole_family() -> None:
    """Ce que le cloisonnement ACHÈTE, vérifié plutôt que promis."""
    css = Theme(shape={"box": "2rem"}).generate_css()
    assert "--radius-box: 2rem;" in css
    assert "--radius-field: 0.75rem;" in css, (
        "bouger `box` a bougé `field` : les familles ne sont pas "
        "indépendantes, donc elles ne cloisonnent rien."
    )


# ───────────────────────────────────────────────────────────────────────
# Le trait — une seule largeur, deux crans dérivés
# ───────────────────────────────────────────────────────────────────────
#
# Pas de famille ici, et le marché est unanime là où il diverge sur le
# rayon : daisyUI, Ant Design et Bootstrap exposent UNE largeur globale,
# Radix / Mantine / Material 3 / shadcn n'en exposent aucune. Personne ne
# cloisonne. Le dépôt dit pourquoi : son vocabulaire de bordure était
# déjà décidable — 1 px partout, 2 px pour l'emphase, 4 px pour l'accent
# latéral, 0 pour retirer.

#: Les largeurs littérales que plus aucun thème ne doit écrire. ``0``
#: n'en fait PAS partie : ``border-0`` retire une bordure, il ne règle
#: pas une largeur, et le dériver d'une variable n'aurait aucun sens.
#:
#: ⚠️ Le garde-fou de tete n'est pas decoratif : sans lui,
#: le motif mordrait dans ``--bz-border-hover`` et ``bz-c-border``,
#: qui sont des COULEURS. Le prefixe de couleur des ponts partage le
#: mot ``border`` avec la largeur -- c'est exactement la collision qui
#: a fait nommer le jeton ``--bz-stroke`` et non ``--bz-border``.
_LITERAL_WIDTH = re.compile(
    r"(?<![-\w])border(?:-[xytrbles])?-(?:1|2|3|4|8)(?![-\w/(])"
)

#: ``border`` nu — la forme la plus discrète, et la plus fréquente : 49
#: slots l'écrivaient. Elle vaut 1 px en dur, donc elle échappe au
#: réglage aussi sûrement qu'un ``border-2``.
_BARE_BORDER = re.compile(r"(?<![-\w])border(?:-[xytrbles])?(?![-\w/(:])")


def test_no_literal_border_width_in_the_framework() -> None:
    """Sur les CHAÎNES DE SLOT, pas sur le texte du fichier.

    C'est la différence avec le rayon juste au-dessus, et elle est
    réelle : ``rounded-xl`` est sans ambiguïté un nom de classe partout
    où il apparaît, alors que « border » est un mot — les docstrings de
    ``card``, ``input``, ``alert`` et huit autres écrivent « soft
    border » ou « bordered frame » en prose. Un balayage textuel
    rougirait sur onze phrases correctes, ce qui est la meilleure façon
    de faire désactiver une gate.

    On lit donc les slots par le lecteur PARTAGÉ de ``_discovery`` : la
    même vue que le migrateur a utilisée, donc rien qui diverge.
    """
    guilty: list[str] = []
    for src in theme_sources():
        name = src.path.parent.name
        for slot, value in theme_slot_strings(src.text):
            for pattern in (_LITERAL_WIDTH, _BARE_BORDER):
                if match := pattern.search(value):
                    guilty.append(f"{name}.{slot} — {match.group(0)}")
                    break
    assert not guilty, (
        "une largeur de trait se lit dans une variable, pas en dur :\n"
        + "\n".join(f"    {g}" for g in guilty)
        + "\n  `border-(length:--bz-stroke)` pour la base, "
        "`--bz-stroke-strong` pour l'emphase (le bouton `outline`, "
        "l'onglet actif), `--bz-stroke-accent` pour l'accent lateral.\n"
        "  `border-0` reste licite : il RETIRE une bordure."
    )


def test_the_stroke_variables_reach_the_stylesheet() -> None:
    """Même silence que pour le rayon, même garde.

    Sans ``--bz-stroke`` dans la feuille, ``border-(length:--bz-stroke)``
    compile en ``border-width: var(--bz-stroke)`` — une variable vide,
    donc une largeur invalide, donc **aucune bordure** sur les 71 slots
    qui l'écrivent. Rien dans la console.
    """
    css = Theme().generate_css()
    for token in ("--bz-stroke", "--bz-stroke-strong", "--bz-stroke-accent"):
        assert f"{token}:" in css, f"`{token}` n'atteint pas la feuille."


def test_the_two_strong_steps_are_derived_not_fixed() -> None:
    """Le rapport doit tenir à TOUTES les valeurs.

    Si l'emphase était un nombre fixe, pousser la base à 2 px la ferait
    disparaître : le bouton ``outline`` cesserait de se distinguer du
    bouton plein, et rien ne le dirait.
    """
    css = Theme(stroke="3px").generate_css()
    assert "--bz-stroke: 3px;" in css
    assert "--bz-stroke-strong: calc(var(--bz-stroke) * 2);" in css, (
        "l'emphase ne dérive plus de la base : elle disparaîtra dès que "
        "quelqu'un épaissira le trait."
    )
    assert DEFAULT_STROKE == "1px", (
        "le défaut a changé : vérifie que les 71 slots le veulent."
    )
