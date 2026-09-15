"""``Diagram`` — le rendu Python, ses refus, et son contrat DOM.

Le placement lui-même est testé à part, dans
``test_diagram_layout.py`` : il est pur, donc il n'a besoin d'aucun
contexte de rendu. Ce qui vit ici, c'est ce que le COMPOSANT en fait —
les classes du thème, les attributs, ce qu'il refuse, et le partage
HTML / SVG.
"""

from __future__ import annotations

import pytest

from bretzel import ui
from bretzel.components.base import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.data.diagram import Diagram
from bretzel.core.tree import Element

EDGES = [("a", "b"), ("b", "c"), ("a", "c")]


def _walk(node: object):
    """Tous les ``Element`` d'un arbre rendu, racine comprise."""
    if isinstance(node, Element):
        yield node
        for child in node.children:
            yield from _walk(child)


def _render(**kwargs) -> Element:
    with render_isolated():
        return Diagram(**kwargs).render()


def _nodes(root: Element) -> list[Element]:
    return [e for e in _walk(root) if "data-bz-node" in e.attrs]


# ── Le partage HTML / SVG ──────────────────────────────────────────────


def test_the_edges_live_in_an_svg_and_the_nodes_do_not() -> None:
    """Le partage qui justifie tout le composant.

    Si un nœud devenait un ``<rect>``, il perdrait la troncature,
    l'anneau de focus, l'icône thémée et l'ordre de tabulation — et
    l'argument contre mermaid tomberait avec.
    """
    root = _render(edges=EDGES)
    svgs = [e for e in _walk(root) if e.tag == "svg"]
    assert len(svgs) == 1
    assert all(e.tag == "div" for e in _nodes(root))
    assert all("data-bz-node" not in e.attrs for e in _walk(svgs[0]))


def test_the_edge_layer_never_swallows_a_click() -> None:
    """``pointer-events-none`` est STRUCTUREL, pas cosmétique.

    Le calque recouvre les nœuds ; sans lui aucun clic n'atteint un
    nœud, et ça ne se voit qu'à l'essai — jamais en relecture.
    """
    svg = next(e for e in _walk(_render(edges=EDGES)) if e.tag == "svg")
    assert "pointer-events-none" in svg.attrs["class"]


def test_the_arrow_marker_is_scoped_to_the_instance() -> None:
    """Deux diagrammes sur une page ne partagent pas leur flèche."""
    with render_isolated():
        first = Diagram(edges=EDGES)
        first.id = "one"
        second = Diagram(edges=EDGES)
        second.id = "two"
        roots = (first.render(), second.render())
    ids = [
        e.attrs["id"]
        for root in roots
        for e in _walk(root)
        if e.tag == "marker"
    ]
    assert ids == ["one__arrow", "two__arrow"]


# ── Le positionnement ──────────────────────────────────────────────────


def test_a_position_is_inline_and_never_a_class() -> None:
    """Le piège de la classe ASSEMBLÉE, gardé là où il se produirait.

    ``left-[240px]`` n'existe qu'en dev : le compilateur de prod ne
    balaie que des littéraux. L'HTML serait identique des deux côtés et
    la page ne se disloquerait qu'en production.
    """
    for element in _nodes(_render(edges=EDGES)):
        assert "left:" in element.attrs["style"]
        assert "left-[" not in element.attrs.get("class", "")


def test_the_drawn_box_is_the_placed_box() -> None:
    """La taille est inline elle aussi — sinon dessin et placement
    divergent d'un ou deux pixels par nœud, et les arêtes ratent leur
    cible."""
    element = _nodes(_render(edges=EDGES))[0]
    assert "width:" in element.attrs["style"]
    assert "height:" in element.attrs["style"]


# ── La vue ─────────────────────────────────────────────────────────────


def test_without_a_focus_the_whole_graph_is_drawn() -> None:
    assert len(_nodes(_render(edges=EDGES))) == 3


def test_a_focus_narrows_to_the_neighbourhood() -> None:
    edges = EDGES + [("d", "e")]
    keys = {e.attrs["data-bz-node"] for e in _nodes(_render(edges=edges, focus="a"))}
    assert keys == {"a", "b", "c"}


def test_a_stale_focus_falls_back_to_the_whole_graph() -> None:
    """Une clé périmée (une feature renommée, un id gardé en session)
    est un accident banal — un écran blanc n'en dirait rien."""
    assert len(_nodes(_render(edges=EDGES, focus="disparu"))) == 3


def test_the_dom_order_follows_the_layers() -> None:
    """L'ordre du DOM EST l'ordre de tabulation : on veut lire le
    graphe dans le sens des flèches."""
    order = [e.attrs["data-bz-node"] for e in _nodes(_render(edges=EDGES))]
    assert order == ["a", "b", "c"]


# ── L'API ──────────────────────────────────────────────────────────────


def test_the_nodes_are_deduced_from_the_edges() -> None:
    """Niveau 1 : aucune déclaration de nœud."""
    assert len(_nodes(_render(edges=[("x", "y")]))) == 2


def test_a_declared_node_carries_its_label_and_group() -> None:
    root = _render(
        nodes=[ui.node("a", label="Alpha", group="socle"), ui.node("b")],
        edges=[("a", "b")],
    )
    alpha = next(e for e in _nodes(root) if e.attrs["data-bz-node"] == "a")
    assert alpha.attrs["data-bz-group"] == "socle"
    assert "Alpha" in _text(root)


def test_a_node_without_a_label_falls_back_to_its_key() -> None:
    assert "planning" in _text(_render(edges=[("planning", "geo")]))


def _text(node: object) -> str:
    from bretzel.core.tree import TextNode

    if isinstance(node, TextNode):
        return node.content
    if isinstance(node, Element):
        return " ".join(_text(c) for c in node.children)
    return ""


def test_render_replaces_the_default_body() -> None:
    root = _render(edges=[("a", "b")], render=lambda spec: f"<{spec.key}>")
    assert "<a>" in _text(root)


def test_an_edge_citing_an_undeclared_node_is_refused_by_name() -> None:
    """Le moteur pur ignore ; le composant, lui, peut NOMMER le fautif.

    Un nœud manquant produit sinon un dessin amputé qu'on relit dix
    minutes avant de comprendre.
    """
    with render_isolated(), pytest.raises(ComponentUsageError, match="fantome"):
        Diagram(nodes=[ui.node("a")], edges=[("a", "fantome")])


def test_an_unknown_direction_is_refused() -> None:
    with render_isolated(), pytest.raises(ComponentUsageError, match="direction"):
        Diagram(edges=EDGES, direction="diagonal")


def test_an_empty_graph_says_so() -> None:
    assert "Rien" in _text(_render(edges=[], empty_text="Rien à montrer"))


def test_the_empty_slot_accepts_a_component() -> None:
    """Le contrat universel des slots textuels : une chaîne OU un arbre."""
    with render_isolated():
        root = Diagram(edges=[], empty_text=ui.badge("vide")).render()
    assert "vide" in _text(root)


# ── Thème ──────────────────────────────────────────────────────────────


def test_each_size_step_changes_the_geometry() -> None:
    """Deux paliers ne rendent pas la même boîte — c'est ce que
    ``size=`` promet, et un palier manquant retomberait sur ``md`` en
    silence."""
    widths = {
        size: _nodes(_render(edges=EDGES, size=size))[0].attrs["style"]
        for size in ("xs", "sm", "md", "lg", "xl")
    }
    assert len(set(widths.values())) == 5


def test_the_focused_node_is_marked() -> None:
    root = _render(edges=EDGES, focus="a")
    focused = next(e for e in _nodes(root) if e.attrs["data-bz-node"] == "a")
    other = next(e for e in _nodes(root) if e.attrs["data-bz-node"] == "b")
    assert focused.attrs["class"] != other.attrs["class"]
