"""Unit tests for :class:`SidebarTrigger` — le bouton qui rouvre la barre.

Ce que ces tests tiennent, c'est le CONTRAT du composant : quel bouton il
rend, à quoi il parle, et ce qu'il refuse. Le versant « une barre
escamotable doit avoir un moyen de revenir » est une question d'arbre
entier — elle vit dans
``tests/consistency/test_a_sidebar_can_always_come_back.py``, qui monte
de vraies pages.
"""

from __future__ import annotations

import pytest

from bretzel.components.base import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.navigation.sidebar import Sidebar, SidebarTrigger
from bretzel.core.serialize import serialize


class TestRender:
    def test_it_renders_a_button_that_toggles_the_sidebar_by_id(self) -> None:
        with render_isolated():
            sidebar = Sidebar(collapsible="overlay", open=False)
            trigger = SidebarTrigger(sidebar)
            html = serialize(trigger.render())
        assert "<button" in html
        # Les apostrophes du JS sont échappées dans l'attribut HTML.
        assert f"getElementById('{sidebar.id}')" in html
        assert "bz-toggle" in html

    def test_it_declares_what_it_controls(self) -> None:
        """``aria-controls`` — ce que l'échappatoire tier 2 ne fait jamais."""
        with render_isolated():
            sidebar = Sidebar(collapsible="overlay", open=False)
            html = serialize(SidebarTrigger(sidebar).render())
        assert f'aria-controls="{sidebar.id}"' in html

    def test_it_names_itself_for_a_screen_reader(self) -> None:
        with render_isolated():
            sidebar = Sidebar(collapsible="overlay")
            html = serialize(SidebarTrigger(sidebar).render())
        assert 'aria-label="Toggle sidebar"' in html

    def test_the_glyph_says_what_it_opens(self) -> None:
        """``panel-left`` par défaut — le glyphe « barre latérale »."""
        with render_isolated():
            sidebar = Sidebar(collapsible="overlay")
            html = serialize(SidebarTrigger(sidebar).render())
        assert "panel-left" in html

    def test_the_glyph_is_choosable(self) -> None:
        """Le dépôt écrit ``menu`` dans crm et ``panel-left`` dans chat."""
        with render_isolated():
            sidebar = Sidebar(collapsible="overlay")
            html = serialize(SidebarTrigger(sidebar, icon="menu").render())
        assert "menu" in html

    def test_size_reaches_the_button(self) -> None:
        with render_isolated():
            sidebar = Sidebar(collapsible="overlay")
            small = serialize(SidebarTrigger(sidebar, size="sm").render())
            large = serialize(SidebarTrigger(sidebar, size="lg").render())
        assert small != large

    def test_universal_kwargs_land_on_the_rendered_button(self) -> None:
        """Le socle les résout sur CE composant : ils doivent être reversés.

        Sans ce report ils tomberaient dans le vide — le mode d'échec
        silencieux que ``_apply_universal_modifiers`` documente, et le
        piège de tout composant qui rend un AUTRE composant.
        """
        with render_isolated():
            sidebar = Sidebar(collapsible="overlay")
            html = serialize(
                SidebarTrigger(sidebar, classes="ml-auto", id="burger").render()
            )
        assert "ml-auto" in html
        assert 'id="burger"' in html


class TestWithoutASidebar:
    def test_it_falls_back_to_the_stable_marker(self) -> None:
        """Aucune barre dans CE rendu : on résout au clic, pas au montage.

        Le cas d'un rafraîchissement de zone qui ne rejoue pas la coque.
        Le bouton doit marcher quand même — il ne peut juste pas annoncer
        ce qu'il contrôle.
        """
        with render_isolated():
            html = serialize(SidebarTrigger().render())
        assert "[data-bz-sidebar]" in html
        assert "aria-controls" not in html

    def test_the_sidebar_carries_that_marker(self) -> None:
        """L'autre moitié du repli : sans l'attribut, le sélecteur est mort."""
        with render_isolated():
            html = serialize(Sidebar(collapsible="overlay").render())
        assert "data-bz-sidebar" in html


class TestCutAxes:
    @pytest.mark.parametrize("axis", ["variant", "color"])
    def test_a_cut_axis_raises_instead_of_being_swallowed(self, axis) -> None:
        """Sans le garde, le socle l'émettrait en attribut HTML muet."""
        with render_isolated():
            sidebar = Sidebar(collapsible="overlay")
            with pytest.raises(ComponentUsageError, match=axis):
                SidebarTrigger(sidebar, **{axis: "solid"})

    def test_the_message_points_at_the_escape_hatch(self) -> None:
        with render_isolated():
            sidebar = Sidebar(collapsible="overlay")
            with pytest.raises(ComponentUsageError) as caught:
                SidebarTrigger(sidebar, color="primary")
        assert "icon_button" in str(caught.value)


class TestBinding:
    def test_binding_a_sidebar_marks_it_commandable(self) -> None:
        """C'est ce qui fait taire la garde d'atteignabilité.

        Le déclencheur passe par ``sidebar.toggle()`` plutôt que de
        fabriquer la commande lui-même — donc les deux tiers de l'API
        empruntent le même chemin, et un seul endroit marque.
        """
        with render_isolated():
            sidebar = Sidebar(collapsible="overlay", open=False)
            assert getattr(sidebar, "_commanded", False) is False
            SidebarTrigger(sidebar)
            assert sidebar._commanded is True
