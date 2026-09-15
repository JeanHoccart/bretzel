"""``ui.grid(min_col=…)`` — la grille compte ses colonnes elle-même.

Le manque que la prop ferme
-----------------------------
``cols={"base": 1, "md": 2, "xl": 4}`` déclare un nombre de colonnes par
palier de **fenêtre**. Or un préfixe ``xl:`` lit la largeur du viewport,
pas celle que la grille a vraiment : sous une coque à barre latérale, les
deux divergent de la largeur de la barre.

Mesuré le 2026-08-25 sur la rangée « Affichage » du CRM, dans un
conteneur de 1024 px — la largeur de contenu réelle ::

    cols={"base":1,"md":2,"xl":4}   4 colonnes, cellules de 244 px,
                                    le ui.toggle_group (256) dehors de 11,9
    min_col="16rem"                 3 colonnes de 331 px, rien dehors

Et la moitié qu'on ne voit pas en regardant l'écran large : rétrécir la
**fenêtre** à 700 px transformait la grille en UNE colonne de 1024 px. Le
conteneur n'avait pas bougé d'un pixel.

``repeat(auto-fit, minmax(X, 1fr))`` est l'idiome CSS canonique de la
grille responsive sans media query, et le ``minChildWidth`` de Chakra s'y
traduit exactement.

Ce qui se juge ici : la table, les refus, et ce qui part sur le fil. Le
versant navigateur — que la grille se replie VRAIMENT au bon moment — est
dans ``tests/probes/probe_grid_min_col.py`` : ces classes ne produisent
aucune différence de HTML mesurable, seulement des pixels.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.layout.grid import Grid
from bretzel.components.layout.grid.theme import GRID_THEME
from bretzel.core.serialize import serialize


def classes(build) -> str:
    """Le composant est bâti DANS le contexte, jamais avant —
    ``Component.__init__`` appelle ``current_context()``."""
    with render_isolated():
        return serialize(build().render())


# ── Ce qui part sur le fil ────────────────────────────────────────────

def test_nothing_asked_keeps_the_old_behaviour() -> None:
    out = classes(lambda: Grid(cols=3))
    assert "grid-cols-3" in out
    assert "auto-fit" not in out


def test_absent_by_default() -> None:
    """Une grille qui ne demande rien n'émet aucune colonne — c'est le
    comportement d'avant, et il ne doit pas bouger."""
    out = classes(lambda: Grid())
    assert "grid-cols" not in out


@pytest.mark.parametrize("width", sorted(GRID_THEME["min_cols"]))
def test_each_width_reaches_its_class(width: str) -> None:
    out = classes(lambda: Grid(min_col=width))
    assert f"minmax({width},1fr)" in out
    assert "auto-fit" in out


def test_the_class_is_whole_never_assembled() -> None:
    """Chaque valeur est une classe ENTIÈRE. Une largeur assemblée en
    f-string rendrait un HTML identique en dev et sans aucune règle en
    prod — le compilateur ne scanne que des littéraux."""
    for value in GRID_THEME["min_cols"].values():
        assert value.startswith("grid-cols-[repeat(auto-fit,minmax(")
        assert "{" not in value


def test_auto_fit_and_not_auto_fill() -> None:
    """``auto-fit`` effondre les pistes vides, donc les colonnes présentes
    se partagent toute la place. Avec ``auto-fill``, deux champs dans un
    conteneur large resteraient collés à gauche avec du vide à droite."""
    for value in GRID_THEME["min_cols"].values():
        assert "auto-fit" in value and "auto-fill" not in value


# ── Les refus ─────────────────────────────────────────────────────────

def test_cols_and_min_col_together_raise() -> None:
    """Les deux posent ``grid-template-columns``. Les accepter ensemble
    laisserait l'ordre de la feuille trancher — donc un résultat qui ne se
    lit dans aucun des deux appels."""
    with pytest.raises(ComponentUsageError, match="min_col"):
        classes(lambda: Grid(cols=3, min_col="16rem"))


def test_a_width_outside_the_table_raises() -> None:
    """Une largeur inconnue rendrait la chaîne vide : la grille
    retomberait sur une seule colonne, sans erreur et sans rien dire."""
    with pytest.raises(ComponentUsageError, match="16rem"):
        classes(lambda: Grid(min_col="15rem"))


def test_the_refusal_names_the_escape_hatch() -> None:
    with pytest.raises(ComponentUsageError) as caught:
        classes(lambda: Grid(min_col="1000px"))
    assert "cols=" in str(caught.value)


def test_the_refusal_happens_at_construction() -> None:
    """Pas au rendu : une levée depuis ``render`` remonte une pile sans
    aucune frame de l'appelant, donc elle nomme les valeurs acceptées sans
    dire lequel des N ``ui.grid`` de la page est fautif."""
    with render_isolated(), pytest.raises(ComponentUsageError):
        Grid(min_col="15rem")  # jamais rendu
