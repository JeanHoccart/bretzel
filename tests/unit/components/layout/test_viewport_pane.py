"""``ui.viewport`` et ``ui.pane`` — le cadre gelé et sa région qui défile.

Ce que ces tests gardent, et pourquoi c'est du rendu Python et pas du
navigateur : les classes qui font marcher ces deux composants sont
**quatre utilitaires précis**, dont deux ont été trouvés à la mesure et
oubliés à chaque recopie. Qu'ils soient là est vérifiable en SSR ; qu'ils
FONCTIONNENT est mesuré en pixels par
``tests/runtime_js/test_a_frozen_screen_scrolls_only_its_panes.py``.
"""

from __future__ import annotations

import pytest

from bretzel import ui
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize


def _classes(build) -> set[str]:
    """Les classes du root. ``build`` est un CALLABLE : un composant se
    construit sous un contexte de rendu, pas avant."""
    with render_isolated():
        html = serialize(build().render())
    inner = html.split('class="', 1)[1].split('"', 1)[0]
    return set(inner.replace("&amp;", "&").replace("&gt;", ">").split())


# ───────────────────────────────────────────────────────────────────────
# Viewport
# ───────────────────────────────────────────────────────────────────────


class TestViewport:
    def test_it_is_out_of_the_document_flow(self) -> None:
        """``fixed``, jamais ``h-screen`` — cf. ``traps.md``.

        En flux, un descendant qui défile gonfle ``html.scrollHeight`` et
        le navigateur rend une SECONDE barre au niveau du viewport. Le
        correctif a déjà été reverté une fois, parce que le défaut ne se
        voit pas sur une page courte.
        """
        classes = _classes(lambda: ui.viewport())
        assert {"fixed", "inset-0", "overflow-hidden"} <= classes
        assert "h-screen" not in classes, (
            "le cadre est revenu en flux : un panneau qui défile va "
            "regonfler `html.scrollHeight` et produire une seconde barre "
            "de défilement, invisible tant que les pages sont courtes."
        )

    def test_the_default_axis_is_a_row(self) -> None:
        assert "flex-row" in _classes(lambda: ui.viewport())

    def test_the_axis_flips(self) -> None:
        """Les deux valeurs co-occurraient dans une app de démo retirée — coque
        desktop en ligne, coque mobile en colonne."""
        assert "flex-col" in _classes(lambda: ui.viewport(direction="col"))

    def test_its_regions_fill_the_cross_axis(self) -> None:
        """``stretch``, pas le ``center`` de ``ui.hstack``.

        Avec ``center``, le panneau droit se réduit à la hauteur de son
        contenu et l'outlet n'a plus aucun conteneur de défilement — les
        coques écrivaient donc ``align="stretch"`` à la main.
        """
        assert "items-stretch" in _classes(lambda: ui.viewport())

    def test_it_does_not_space_its_regions_by_default(self) -> None:
        assert "gap-0" in _classes(lambda: ui.viewport())


# ───────────────────────────────────────────────────────────────────────
# Pane
# ───────────────────────────────────────────────────────────────────────


class TestPane:
    def test_it_carries_the_four_class_idiom(self) -> None:
        """Les quatre, dont les deux qui ne se devinent pas."""
        classes = _classes(lambda: ui.pane())
        for needed in ("flex-1", "min-h-0", "overflow-y-auto", "[&>*]:shrink-0"):
            assert needed in classes, (
                f"`{needed}` a disparu du pane. C'est l'une des quatre "
                f"classes de l'idiome : sans `min-h-0` la boîte grandit au "
                f"lieu de défiler, sans `[&>*]:shrink-0` ses items "
                f"s'écrasent (mesuré : 39 px coupés). Cf. `traps.md` § "
                f"« Une colonne qui défile ÉCRASE ses items »."
            )

    def test_it_carries_both_height_regimes(self) -> None:
        """``flex-1`` ET ``h-full`` — mesuré, pas supposé.

        Dans un parent ``flex-col``, ``flex-basis: 0%`` remplace la taille
        principale et ``h-full`` est ignoré ; dans un parent bloc à
        hauteur définie (un ``ui.resizable_panel``), ``flex-1`` est inerte
        et c'est ``h-full`` qui rend. Mesuré en Chromium sur les trois
        formes de parent : la paire défile dans les trois, ``flex-1``
        seul échoue dans deux (600 px de haut, aucun défilement).
        """
        classes = _classes(lambda: ui.pane())
        assert {"flex-1", "h-full"} <= classes

    def test_it_is_a_column(self) -> None:
        assert "flex-col" in _classes(lambda: ui.pane())

    def test_padding_is_a_token(self) -> None:
        assert {"p-6", "sm:p-8"} <= _classes(lambda: ui.pane(padding="lg"))

    def test_no_padding_by_default(self) -> None:
        """La moitié des sites n'en veut pas : une coque met sa respiration
        plus bas, autour de l'outlet."""
        assert not {c for c in _classes(lambda: ui.pane()) if c.startswith("p-")}

    def test_gap_reaches_the_theme(self) -> None:
        assert "gap-1" in _classes(lambda: ui.pane(gap="xs"))

    def test_it_refuses_to_wrap(self) -> None:
        """``wrap`` est SCELLÉ, pas ignoré.

        Le socle absorberait un kwarg inconnu en attribut HTML muet, donc
        un refus silencieux serait pire que l'absence de la prop. Et le
        message doit dire quoi écrire à la place — c'est la leçon de la
        coupe de ``bottom_bar(variant=)``.
        """
        with render_isolated(), pytest.raises(TypeError, match="ne se replie pas"):
            ui.pane(wrap=True)

    def test_the_seal_is_visible_from_outside(self) -> None:
        """Une prop refusée à l'appel doit sortir de la fiche publique.

        Sinon ``bretzel describe pane`` l'annonce utilisable et le lecteur
        prend un ``TypeError`` en l'écrivant.
        """
        from bretzel.introspect import describe

        assert "wrap" not in describe("pane")
