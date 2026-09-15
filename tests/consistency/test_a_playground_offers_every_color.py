"""Gate : une liste ``COLORS`` du playground offre les SEPT couleurs.

Le défaut qu'elle ferme
-----------------------
Le playground est le banc d'essai : un palier qui n'y est pas offert
n'est essayé par personne. Mesuré le 2026-09-06, avant correction :
**9 pages sur 124** proposaient six couleurs sur sept, et chacune des
neuf omissions changeait réellement le rendu —

    bottom_bar, diagram, sidebar, tree           → sans `muted`
    banner, bar_chart, line_chart,
    scatter_chart, sparkline                     → sans `secondary`

Vérifié composant par composant : le HTML de ``color="muted"`` diffère
de celui de ``color="primary"`` sur les quatre premiers, celui de
``color="secondary"`` sur les cinq autres. Ce n'était donc pas une
abstention de conception, c'était une liste recopiée d'une page voisine
et jamais relue — le mode de dérive de tout catalogue écrit à la main.

Ce que la gate NE dit pas
-------------------------
« Ce composant devrait lire `color`. » Elle ne juge que les listes que
la page DÉCLARE : si une page en écrit une, elle l'écrit entière. Une
page qui n'a rien à colorer n'a pas de ``COLORS``, et sort de la
population par définition.

Les EXTRAS restent libres — ``ui.icon`` et ``ui.spinner`` ajoutent
``current`` (hériter du parent), qui n'est pas une couleur du thème.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.consistency._discovery import REPO_ROOT

#: Les sept couleurs du thème, dans l'ordre d'``bretzel describe``.
CANONICAL = (
    "primary", "secondary", "success", "warning", "error", "info", "muted",
)

PLAYGROUND = REPO_ROOT / "examples" / "playground" / "features"


def color_lists() -> list[tuple[str, tuple[str, ...]]]:
    """Chaque affectation ``COLORS = [...]`` littérale du playground."""
    found = []
    for path in sorted(PLAYGROUND.rglob("*.py")):
        source = path.read_text(encoding="utf-8-sig")
        if "COLORS" not in source:
            continue
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Assign):
                continue
            if not any(
                isinstance(t, ast.Name) and t.id == "COLORS"
                for t in node.targets
            ):
                continue
            try:
                values = ast.literal_eval(node.value)
            except ValueError:
                continue  # une liste calculée — pas de littéral à lire
            found.append((
                str(path.relative_to(PLAYGROUND)).replace("\\", "/"),
                tuple(v for v in values if isinstance(v, str)),
            ))
    return found


def missing_from(values: tuple[str, ...]) -> tuple[str, ...]:
    """Les couleurs canoniques absentes — le détecteur, isolé."""
    return tuple(c for c in CANONICAL if c not in values)


# ── Les planchers ─────────────────────────────────────────────────────


def test_the_sweep_finds_the_color_lists() -> None:
    """Sans lui, un `COLORS` renommé viderait le balayage en silence."""
    found = color_lists()
    assert len(found) >= 30, (
        f"seulement {len(found)} liste(s) `COLORS` littérale(s) trouvée(s) "
        f"dans {PLAYGROUND} — il y en avait 33 le 2026-09-06. Le lecteur "
        f"est cassé, ou la convention a changé de nom."
    )


def test_the_lists_are_read_as_colors() -> None:
    """Second plancher : ce sont bien des couleurs qu'on lit.

    Un lecteur qui rendrait des listes vides passerait le plancher
    ci-dessus et rendrait l'assertion verte sur tout le corpus.
    """
    seen = {value for _page, values in color_lists() for value in values}
    assert set(CANONICAL) <= seen, (
        f"les listes lues ne contiennent pas les sept couleurs, même "
        f"réunies : {sorted(seen)}. Ce ne sont pas des `COLORS`."
    )


# ── L'assertion ───────────────────────────────────────────────────────


@pytest.mark.parametrize(("page", "values"), color_lists(), ids=lambda v: v)
def test_a_color_list_offers_all_seven(
    page: str, values: tuple[str, ...]
) -> None:
    missing = missing_from(values)
    assert not missing, (
        f"`{page}` n'offre pas {', '.join(missing)} dans sa liste "
        f"`COLORS`.\n"
        f"  Le playground est le banc d'essai : une couleur qui n'y est "
        f"pas offerte n'est essayée par personne. Les neuf omissions "
        f"mesurées le 2026-09-06 changeaient toutes le rendu — c'étaient "
        f"des listes recopiées d'une page voisine, pas des abstentions.\n"
        f"  Si ce composant ne lit vraiment pas `color`, il n'a pas "
        f"besoin d'une liste `COLORS` du tout."
    )


# ── La morsure ────────────────────────────────────────────────────────


def test_the_detector_catches_a_short_list() -> None:
    """Mutation : le détecteur voit l'omission, et rien sur le cas licite.

    Les deux versants, parce qu'un détecteur qui rougit sur tout est
    aussi inutile qu'un détecteur aveugle.
    """
    assert missing_from(CANONICAL) == ()
    assert missing_from(CANONICAL + ("current",)) == ()
    assert missing_from(tuple(c for c in CANONICAL if c != "muted")) == (
        "muted",
    )
    assert missing_from(()) == CANONICAL
