"""Unit tests for :class:`bretzel.components.navigation.breadcrumb.Breadcrumb`."""

from __future__ import annotations

import pytest

from bretzel import ui
from bretzel.components.base.testing import render_isolated
from bretzel.components.navigation.breadcrumb import Breadcrumb
from bretzel.components.primitives.icon import Icon
from bretzel.core.serialize import serialize

# ───────────────────────────────────────────────────────────────────────────
# A. Render structure
# ───────────────────────────────────────────────────────────────────────────


class TestStructure:
    def test_renders_nav_with_role(self) -> None:
        with render_isolated():
            out = serialize(
                Breadcrumb([
                    {"label": "Home", "href": "/"},
                    {"label": "Tracker"},
                ]).render()
            )
        assert "<nav" in out
        assert 'aria-label="Breadcrumb"' in out

    def test_anchors_for_intermediate_items(self) -> None:
        with render_isolated():
            out = serialize(
                Breadcrumb([
                    {"label": "Home", "href": "/"},
                    {"label": "Projects", "href": "/projects"},
                    {"label": "Tracker"},
                ]).render()
            )
        # Two clickable parents → two <a> elements.
        assert out.count("<a") == 2
        assert 'href="/"' in out
        assert 'href="/projects"' in out

    def test_last_item_renders_as_span_with_aria_current(self) -> None:
        with render_isolated():
            out = serialize(
                Breadcrumb([
                    {"label": "Home", "href": "/"},
                    {"label": "Tracker"},
                ]).render()
            )
        assert 'aria-current="page"' in out
        # Tracker label sits in a <span aria-current=page>, not <a>.
        assert ">Tracker</span>" in out

    def test_separator_between_each_pair(self) -> None:
        with render_isolated():
            out = serialize(
                Breadcrumb([
                    {"label": "A", "href": "/a"},
                    {"label": "B", "href": "/b"},
                    {"label": "C"},
                ]).render()
            )
        # Three items → two separators.
        assert out.count('aria-hidden="true"') == 2


# ───────────────────────────────────────────────────────────────────────────
# B. Item shape acceptance
# ───────────────────────────────────────────────────────────────────────────


class TestItemShapes:
    def test_dict_items(self) -> None:
        with render_isolated():
            out = serialize(
                Breadcrumb([
                    {"label": "A", "href": "/a"},
                    {"label": "B"},
                ]).render()
            )
        assert "A</a>" in out and "B</span>" in out

    def test_tuple_items(self) -> None:
        with render_isolated():
            out = serialize(
                Breadcrumb([("A", "/a"), ("B", None)]).render()
            )
        assert 'href="/a"' in out
        # Tuple with None href on a non-last item → <span> with no
        # href ; on the last item → current span. Test the last one.
        assert 'aria-current="page"' in out

    def test_string_items(self) -> None:
        with render_isolated():
            out = serialize(
                Breadcrumb(["Home", "Tracker"]).render()
            )
        # Strings = label only, no href ; intermediate item becomes
        # a no-href <span>, last becomes current.
        assert "Home</span>" in out
        assert "Tracker</span>" in out

    def test_empty_items_renders_empty_nav(self) -> None:
        with render_isolated():
            out = serialize(Breadcrumb([]).render())
        # Empty trail still emits the wrapper — useful for layout
        # spacing during loading states.
        assert "<nav" in out
        assert "</nav>" in out
        assert "<a" not in out


# ───────────────────────────────────────────────────────────────────────────
# C. Custom separator
# ───────────────────────────────────────────────────────────────────────────


class TestSeparator:
    def test_default_chevron_icon(self) -> None:
        with render_isolated():
            out = serialize(
                Breadcrumb([
                    {"label": "A", "href": "/a"},
                    {"label": "B"},
                ]).render()
            )
        assert "lucide:chevron-right" in out

    def test_short_string_renders_as_text(self) -> None:
        with render_isolated():
            out = serialize(
                Breadcrumb(
                    [{"label": "A", "href": "/a"}, {"label": "B"}],
                    separator="/",
                ).render()
            )
        # Single-char separator becomes a plain text span — no
        # iconify-icon emitted.
        assert "iconify-icon" not in out
        assert ">/<" in out

    def test_iconify_name_separator(self) -> None:
        with render_isolated():
            out = serialize(
                Breadcrumb(
                    [{"label": "A", "href": "/a"}, {"label": "B"}],
                    separator="slash",
                ).render()
            )
        # Multi-char string is interpreted as an Iconify name.
        assert "lucide:slash" in out

    def test_component_separator(self) -> None:
        with render_isolated():
            out = serialize(
                Breadcrumb(
                    [{"label": "A", "href": "/a"}, {"label": "B"}],
                    separator=Icon("dot", size="xs"),
                ).render()
            )
        assert "lucide:dot" in out


# ───────────────────────────────────────────────────────────────────────────
# D. Theme — color & size
# ───────────────────────────────────────────────────────────────────────────


class TestTheme:
    @pytest.mark.parametrize(
        ("size", "expected"),
        [("sm", "text-xs"), ("md", "text-sm"), ("lg", "text-base")],
    )
    def test_size_applies(self, size: str, expected: str) -> None:
        with render_isolated():
            out = serialize(
                Breadcrumb(
                    [{"label": "A", "href": "/"}, {"label": "B"}],
                    size=size,
                ).render()
            )
        assert expected in out

    def test_color_focus_ring(self) -> None:
        with render_isolated():
            out = serialize(
                Breadcrumb(
                    [{"label": "A", "href": "/"}, {"label": "B"}],
                    color="success",
                ).render()
            )
        # Focus ring color resolves via {bg_color} substitution.
        assert "focus-visible:ring-(--bz-focus)" in out
        assert "{bg_color}" not in out


# ───────────────────────────────────────────────────────────────────────────
# E. Type errors
# ───────────────────────────────────────────────────────────────────────────


class TestErrors:
    def test_unsupported_item_type_raises(self) -> None:
        with render_isolated(), pytest.raises(TypeError):
            serialize(Breadcrumb([42]).render())


# ───────────────────────────────────────────────────────────────────────────
# F. Enfants — le niveau 2 de l'API
# ───────────────────────────────────────────────────────────────────────────


class TestChildren:
    """`COLLECTION_OWNER = "author"` : l'auteur écrit son ``for``, donc il
    lui faut des enfants. Gaté catalogue-large par
    ``tests/consistency/test_collection_owner_decides_the_api.py`` ; ici
    on épingle ce qui est propre à Breadcrumb."""

    def _trail(self):
        with Breadcrumb() as b:
            ui.breadcrumb_item("Home", href="/")
            ui.breadcrumb_item("Docs", icon="book", href="/docs")
            ui.breadcrumb_item("Ici")
        return b

    def test_icon_and_label_render_inside_their_segment(self) -> None:
        """Même surface que ``ui.tab`` / ``ui.sidebar_item`` : ``icon=``
        accepte le raccourci string, ``label`` le texte."""
        with render_isolated():
            out = serialize(self._trail().render())
        assert "lucide:book" in out
        assert "Docs" in out

    def test_a_component_in_label_replaces_the_text(self) -> None:
        """Pour un contenu vraiment arbitraire, on bâtit AVANT et on
        passe en ``label`` — c'est ce qui rend le conteneur inutile."""
        with render_isolated():
            with ui.hstack() as rich:
                ui.icon("star", size="xs")
                ui.text("Perso")
            with Breadcrumb() as b:
                ui.breadcrumb_item(rich, href="/x")
            out = serialize(b.render())
        assert out.count("lucide:star") == 1
        assert "Perso" in out

    def test_the_component_marks_the_last_one_itself(self) -> None:
        """L'auteur n'a jamais à calculer un ``is_last`` : seul le
        composant connaît la longueur du fil."""
        with render_isolated():
            out = serialize(self._trail().render())
        assert out.count('aria-current="page"') == 1
        assert out.index("Ici") > out.index('aria-current="page"')

    def test_a_non_last_item_keeps_its_href(self) -> None:
        with render_isolated():
            out = serialize(self._trail().render())
        assert 'href="/"' in out and 'href="/docs"' in out

    def test_items_shortcut_materialises_the_same_children(self) -> None:
        """``items=`` est le niveau 1 : il doit produire EXACTEMENT le
        même DOM que les enfants équivalents, sinon les deux niveaux
        divergent en silence. L'icône est comprise — c'est pourquoi la
        forme dict porte une clé ``icon``."""
        with render_isolated():
            via_items = serialize(
                Breadcrumb([
                    {"label": "Home", "href": "/", "icon": "house"},
                    {"label": "Ici"},
                ]).render()
            )
        with render_isolated():
            with Breadcrumb() as b:
                ui.breadcrumb_item("Home", icon="house", href="/")
                ui.breadcrumb_item("Ici")
            via_children = serialize(b.render())
        assert via_items == via_children

    def test_item_label_accepts_a_component(self) -> None:
        """Le contrat universel de slot textuel vaut aussi ici."""
        with render_isolated():
            with Breadcrumb() as b:
                ui.breadcrumb_item(ui.badge(label="ZZ"))
            out = serialize(b.render())
        assert out.count("ZZ") == 1

    def test_an_orphan_item_renders_without_the_parent_classes(self) -> None:
        """Hors d'un fil, un segment rend son corps plutôt que de lever —
        même contrat que ``Tab`` / ``Step`` / ``TreeNode``."""
        with render_isolated():
            out = serialize(ui.breadcrumb_item("Seul", href="/x").render())
        assert "Seul" in out
