"""La migration vers les paliers ne peut que PROGRESSER, et son
vocabulaire est fermé.

Deux invariants, une seule raison d'être : la coexistence entre les
gabarits ``{bg_color}`` et les paliers ``(--bz-…)`` est voulue — 100
composants à surface visuelle ne se migrent pas d'un bloc — mais son
mode de défaillance connu est qu'**elle ne finit jamais**.

Le compteur
------------

Le nombre de gabarits restants est écrit ici. Il ne peut que baisser.
Une migration qui stagne reste visible ; une qui recule rougit. La phase
5 du chantier le mettra à zéro et transformera le compteur en
interdiction pure.

C'est la décision du 2026-08-30 (`.claude/work/chantier-jetons-couleur-2026-08-30.md`,
§ *Les décisions*, point 2), et elle vient de ce que la coexistence est
**gratuite** : ``resolve_slot`` laisse passer une chaîne sans trou, donc
les deux formes vivent côte à côte sans une ligne de compatibilité. Ce
qui est gratuit ne se termine pas tout seul.

Le vocabulaire
---------------

Un thème n'écrit que des paliers qui existent. ``bg-(--bz-bg-hovr)`` est
une classe parfaitement valide pour Tailwind, qui la compile sans un
mot ; à l'écran la propriété est invalide et le composant reste
transparent. Ni erreur, ni trace — le mode d'échec le plus cher du
chantier, et le seul qu'une relecture ne rattrape pas.

⚠️ ``--bz-text`` (variable CSS) et ``bz-text`` (directive du runtime)
sont deux choses différentes qui partagent une sous-chaîne. Un ``grep``
naïf les mélange, et deux tests unitaires ont rougi pour ça le
2026-08-30. Les assertions doivent nommer ce qu'elles cherchent :
``bz-text=`` pour la directive, ``(--bz-text)`` pour le palier.
"""

from __future__ import annotations

import re

from bretzel.theme.bridges import STEP_NAMES
from tests.consistency._discovery import theme_slot_strings, theme_sources

#: Un gabarit de couleur, la forme qu'on retire.
_PLACEHOLDER = re.compile(r"\{(?:bg|fg)_color\}")

#: Un palier lu dans une classe Tailwind à propriété arbitraire.
_STEP_USE = re.compile(r"\(\s*(--bz-[a-z0-9-]+)\s*\)")

#: **Zéro**, depuis la phase 3 (2026-08-30) : les 47 thèmes restants sont
#: passés aux paliers dans la foulée d'``Icon`` et de ``Badge``.
#:
#: Le compteur reste un compteur et ne devient PAS une interdiction pure :
#: c'est la phase 5 qui supprimera le mécanisme. Tant qu'il existe, un
#: thème peut le réécrire — et ce fichier le verra.
_PLACEHOLDERS_LEFT = 0


def placeholders() -> list[str]:
    """Les gabarits restants, un par occurrence."""
    out: list[str] = []
    for source in theme_sources():
        for slot, classes in theme_slot_strings(source.text):
            for _match in _PLACEHOLDER.findall(classes):
                out.append(f"{source.path.parent.name}:{slot}")
    return out


def step_uses() -> list[tuple[str, str]]:
    """Les paliers écrits par les thèmes — ``(composant:slot, palier)``."""
    out: list[tuple[str, str]] = []
    for source in theme_sources():
        for slot, classes in theme_slot_strings(source.text):
            for step in _STEP_USE.findall(classes):
                out.append((f"{source.path.parent.name}:{slot}", step))
    return out


def test_the_sweep_is_not_vacuous() -> None:
    """Le plancher lit la découverte des DEUX balayages.

    Si ``theme_slot_strings`` cessait d'extraire, les deux listes
    tomberaient à zéro : le compteur passerait au vert en ayant l'air
    d'une migration finie, et le vocabulaire n'aurait plus rien à
    vérifier. Mesuré le 2026-08-30 : 230 gabarits, 16 paliers.
    """
    assert len(placeholders()) + len(step_uses()) >= 100, (
        f"Le balayage ne voit plus que {len(placeholders())} gabarit(s) et "
        f"{len(step_uses())} palier(s). L'extracteur de slots a cessé de "
        "rendre ce qu'on croit — les deux tests ci-dessous ne vérifient "
        "plus rien."
    )


def test_the_placeholder_count_only_shrinks() -> None:
    seen = len(placeholders())
    assert seen <= _PLACEHOLDERS_LEFT, (
        f"{seen} gabarits ``{{bg_color}}`` / ``{{fg_color}}`` dans les "
        f"thèmes, contre {_PLACEHOLDERS_LEFT} déclarés ici.\n"
        "La coexistence avec les paliers est voulue, mais elle doit "
        "FINIR : un thème neuf s'écrit en paliers, pas en gabarits.\n"
        "  Un palier est une classe COMPLÈTE que le compilateur voit ; un "
        "gabarit est une demi-classe qu'il faut clôturer couleur par "
        "couleur, et c'est cette clôture qui pèse 80 % de la feuille."
    )


def test_the_counter_is_not_left_behind() -> None:
    """L'autre sens : un compteur qui garde du mou ne compte plus.

    Sans lui, migrer dix thèmes sans toucher au nombre laisserait la
    place pour en dé-migrer dix — et la gate resterait verte.
    """
    seen = len(placeholders())
    assert seen == _PLACEHOLDERS_LEFT, (
        f"Il ne reste que {seen} gabarits, le compteur en déclare "
        f"{_PLACEHOLDERS_LEFT}. Descends-le à {seen} dans le même commit "
        "que la migration."
    )


#: Les propriétés ``--bz-*`` d'un thème qui ne sont PAS des couleurs.
#:
#: La règle au-dessus lit tout ``(--bz-…)`` d'une classe de thème comme un
#: palier de couleur, parce que c'est ce que 100 % d'entre eux étaient. Le
#: 2026-09-09 en a introduit un qui ne l'est pas : la flèche d'un
#: ``ui.tooltip`` doit viser son déclencheur et non le milieu de sa bulle,
#: donc ``$bz.helpers.floating`` publie la position de l'ancre DANS le
#: panneau et le thème la lit en ``start-(--bz-arrow)``.
#:
#: ⚠️ Une liste, pas une exception au motif. La protection que cette règle
#: apporte — une faute de frappe dans un nom de propriété ne lève nulle
#: part, Tailwind compile la classe et l'écran rend un composant
#: transparent — vaut exactement autant pour une géométrie que pour une
#: couleur. ``--bz-arow`` doit rougir ici comme ``--bz-bg-hovr``.
_GEOMETRY_STEPS = frozenset({"--bz-arrow"})


def test_a_theme_only_writes_steps_that_exist() -> None:
    known = set(STEP_NAMES) | _GEOMETRY_STEPS
    unknown = sorted({
        f"{where} → {step}" for where, step in step_uses() if step not in known
    })
    assert not unknown, (
        "Ces thèmes écrivent un palier qui n'existe pas :\n  "
        + "\n  ".join(unknown)
        + f"\n\nLes paliers sont {sorted(known)}.\n"
        "  Une faute de frappe ne lève nulle part : Tailwind compile la "
        "classe sans un mot, et à l'écran la propriété est invalide — le "
        "composant reste transparent."
    )


def test_the_detectors_still_bite() -> None:
    """Mutation, dans les deux sens, sur les deux détecteurs."""
    # ── ils mordent ────────────────────────────────────────────────
    assert _PLACEHOLDER.findall("bg-{bg_color}/15 text-{fg_color}")
    assert _STEP_USE.findall("bg-(--bz-bg) text-(--bz-text)") == [
        "--bz-bg", "--bz-text"
    ]
    assert _STEP_USE.findall("hover:bg-(--bz-bg-hover)") == ["--bz-bg-hover"]
    # une variante empilée ne cache pas le palier
    assert _STEP_USE.findall(
        "peer-focus-visible:ring-(--bz-focus)"
    ) == ["--bz-focus"]

    # ── ils épargnent ──────────────────────────────────────────────
    # une classe Tailwind ordinaire ne contient pas de gabarit
    assert not _PLACEHOLDER.findall("rounded-md px-2 text-sm")
    # une variable qui n'est PAS un palier de couleur
    assert not _STEP_USE.findall("w-(--sidebar-width)")
    # la DIRECTIVE ``bz-text``, qui n'est pas le palier ``--bz-text``
    assert not _STEP_USE.findall('bz-text="$bz.state.x"')
    # un token de thème, écrit sans les parenthèses de propriété arbitraire
    assert not _STEP_USE.findall("bg-surface text-text/80")
