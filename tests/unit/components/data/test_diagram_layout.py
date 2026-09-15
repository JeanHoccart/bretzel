"""Le moteur de placement du diagramme — pur, donc testable sans navigateur.

C'est là que vit la moitié difficile du composant, et c'est le seul
endroit du dépôt où un invariant visuel — « aucune arête ne traverse un
nœud » — se vérifie par le calcul plutôt que par une capture d'écran.
"""

from __future__ import annotations

import pytest

from bretzel.components.data.diagram.layout import (
    Metrics,
    assign_layers,
    break_cycles,
    keys_from_edges,
    layout,
    neighbourhood,
    order_layers,
)

# Un losange : deux chemins de longueur différente vers le même nœud.
# La forme minimale qui exige des fantômes (``a → d`` saute une couche).
DIAMOND = [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("a", "d")]


# ── 1 — casser les cycles ──────────────────────────────────────────────


def test_a_graph_without_a_cycle_keeps_every_edge() -> None:
    """Le versant licite : on n'inverse rien quand il n'y a rien à casser."""
    keys = keys_from_edges(DIAMOND)
    acyclic, flipped = break_cycles(keys, DIAMOND)
    assert flipped == frozenset()
    assert acyclic == DIAMOND


def test_a_cycle_loses_exactly_one_edge() -> None:
    edges = [("a", "b"), ("b", "c"), ("c", "a")]
    _, flipped = break_cycles(keys_from_edges(edges), edges)
    assert len(flipped) == 1


def test_a_diamond_is_not_mistaken_for_a_cycle() -> None:
    """Le piège du « déjà vu » : ``d`` est atteint deux fois sans cycle.

    Un parcours qui inverse toute arête vers un nœud DÉJÀ VU casserait
    ``c → d`` ici. Seul un nœud encore SUR LA PILE ferme un cycle.
    """
    _, flipped = break_cycles(keys_from_edges(DIAMOND), DIAMOND)
    assert flipped == frozenset()


# ── 2 — les couches ────────────────────────────────────────────────────


def test_a_node_comes_after_everything_it_consumes() -> None:
    depth = assign_layers(keys_from_edges(DIAMOND), DIAMOND)
    for source, target in DIAMOND:
        assert depth[source] < depth[target], (source, target)


def test_the_longest_path_wins() -> None:
    """``d`` descend derrière le plus LONG de ses chemins, pas le plus court."""
    depth = assign_layers(keys_from_edges(DIAMOND), DIAMOND)
    assert depth["a"] == 0
    assert depth["d"] == 2


def test_a_self_loop_constrains_nothing() -> None:
    edges = [("a", "a"), ("a", "b")]
    depth = assign_layers(keys_from_edges(edges), edges)
    assert depth == {"a": 0, "b": 1}


# ── 3 — les croisements ────────────────────────────────────────────────


def test_the_median_untangles_a_crossed_pair() -> None:
    """Deux arêtes croisées à l'entrée, zéro croisement à la sortie."""
    edges = [("a1", "b2"), ("a2", "b1")]
    layers = [["a1", "a2"], ["b1", "b2"]]
    assert order_layers(layers, edges)[1] == ("b2", "b1")


def test_ordering_never_loses_a_node() -> None:
    """Plancher : la passe 3 réordonne, elle ne filtre pas.

    Une heuristique qui laisse tomber un nœud sans voisin rendrait un
    diagramme incomplet SANS erreur — le mode d'échec le plus cher ici.
    """
    layers = [["a", "orphan"], ["b"]]
    ordered = order_layers(layers, [("a", "b")])
    assert sorted(ordered[0]) == ["a", "orphan"]
    assert ordered[1] == ("b",)


# ── 4 — le placement ───────────────────────────────────────────────────


def _overlap(lo1: float, hi1: float, lo2: float, hi2: float) -> float:
    return min(hi1, hi2) - max(lo1, lo2)


def test_two_nodes_never_overlap() -> None:
    placed = layout(keys_from_edges(DIAMOND), DIAMOND)
    for i, first in enumerate(placed.boxes):
        for second in placed.boxes[i + 1 :]:
            horizontal = _overlap(
                first.x, first.x + first.width, second.x, second.x + second.width
            )
            vertical = _overlap(
                first.y, first.y + first.height, second.y, second.y + second.height
            )
            assert horizontal <= 0 or vertical <= 0, (first, second)


def test_a_long_edge_traverses_its_layer_flat() -> None:
    """``a → d`` saute une couche : sans fantôme elle passerait sur ``b``.

    Trois segments, et c'est le SECOND qui compte : le fantôme est un
    segment, pas un point, donc l'arête traverse la couche du milieu à
    plat sur sa propre voie et ne remonte que dans l'écart entre deux
    couches, là où il n'y a rien. Deux segments signifieraient un retour
    au modèle « fantôme = point », où la courbe balaie la largeur du
    nœud voisin en descendant — et le traverse.
    """
    placed = layout(keys_from_edges(DIAMOND), DIAMOND)
    long_edge = next(r for r in placed.routes if (r.source, r.target) == ("a", "d"))
    assert long_edge.path.count("C") == 3
    flat = [
        (x, y) for x, y in _sample(long_edge.path)
    ]
    middle = [y for x, y in flat if 248 <= x <= 408]
    assert max(middle) - min(middle) < 1.0, "la traversée n'est pas plate"


def test_no_edge_passes_through_a_node() -> None:
    """L'invariant visuel, vérifié par le calcul.

    On échantillonne chaque tracé et on refuse qu'un point tombe dans
    une boîte qui n'est ni sa source ni sa cible. C'est ce qu'un œil
    voit en premier sur un diagramme raté, et ce qu'aucune capture ne
    garde d'un run à l'autre.
    """
    edges = DIAMOND + [("a", "e"), ("b", "e"), ("c", "e")]
    placed = layout(keys_from_edges(edges), edges)
    boxes = {b.key: b for b in placed.boxes}
    for route in placed.routes:
        for x, y in _sample(route.path):
            for key, box in boxes.items():
                if key in (route.source, route.target):
                    continue
                inside = (
                    box.x < x < box.x + box.width
                    and box.y < y < box.y + box.height
                )
                assert not inside, f"{route.source}->{route.target} traverse {key}"


def _sample(path: str, steps: int = 24) -> list[tuple[float, float]]:
    """Les points d'une suite de cubiques ``M… C… C…``.

    Une évaluation de Bézier plutôt qu'une lecture des poignées : ce
    qu'on veut savoir, c'est où la courbe PASSE, pas où on l'a tirée.
    """
    import re

    numbers = [float(n) for n in re.findall(r"-?\d+\.?\d*", path)]
    points: list[tuple[float, float]] = []
    start = (numbers[0], numbers[1])
    rest = numbers[2:]
    for i in range(0, len(rest) - 5, 6):
        c1 = (rest[i], rest[i + 1])
        c2 = (rest[i + 2], rest[i + 3])
        end = (rest[i + 4], rest[i + 5])
        for step in range(steps + 1):
            t = step / steps
            u = 1 - t
            points.append(
                (
                    u**3 * start[0] + 3 * u**2 * t * c1[0]
                    + 3 * u * t**2 * c2[0] + t**3 * end[0],
                    u**3 * start[1] + 3 * u**2 * t * c1[1]
                    + 3 * u * t**2 * c2[1] + t**3 * end[1],
                )
            )
        start = end
    return points


def test_the_canvas_contains_every_edge() -> None:
    """La toile mesure aussi les ARETES, pas seulement les boites.

    Une arete longue passe par une voie qui est HORS des couches
    occupees, donc une toile mesuree sur les seules boites la coupe :
    elle sort par le bas du cadre et disparait. Le HTML est intact, les
    noeuds sont tous la, et il n'y a rien a lire — c'est une capture
    d'ecran qui l'a montre.
    """
    placed = layout(keys_from_edges(DIAMOND), DIAMOND)
    for route in placed.routes:
        for x, y in _sample(route.path):
            assert -0.5 <= x <= placed.width + 0.5, (route.source, route.target, x)
            assert -0.5 <= y <= placed.height + 0.5, (route.source, route.target, y)


def test_the_sampler_finds_the_curve() -> None:
    """Plancher du détecteur ci-dessus : il lit vraiment des points.

    Sans lui, une regex cassée rendrait une liste vide et
    ``test_no_edge_passes_through_a_node`` serait vert sur rien.
    """
    points = _sample("M0.00,0.00 C10.00,0.00 10.00,20.00 20.00,20.00")
    assert len(points) == 25
    assert points[0] == pytest.approx((0.0, 0.0))
    assert points[-1] == pytest.approx((20.0, 20.0))


# ── Déterminisme ───────────────────────────────────────────────────────


def test_the_same_graph_places_identically() -> None:
    """Sans ça, ni comparaison à l'octet ni capture de référence ne tient."""
    keys = keys_from_edges(DIAMOND)
    first = layout(keys, DIAMOND)
    second = layout(keys, DIAMOND)
    assert first.boxes == second.boxes
    assert first.routes == second.routes


def test_the_input_order_is_what_decides() -> None:
    """Deux ordres d'entrée peuvent différer — mais chacun est stable.

    Le placement n'est pas invariant par permutation, et c'est voulu :
    l'ordre déclaré est une information de l'auteur. Ce qui est promis,
    c'est la reproductibilité à entrée égale.
    """
    edges = [("a", "c"), ("b", "c")]
    one = layout(["a", "b", "c"], edges)
    again = layout(["a", "b", "c"], edges)
    assert one.boxes == again.boxes


# ── Direction, voisinage, cas dégénérés ────────────────────────────────


def test_direction_swaps_the_axes() -> None:
    """Le MÊME graphe, comparé à lui-même dans les deux sens.

    Pas « la sortie est plus large que haute » : un losange de nœuds
    larges reste plus large que haut même en vertical, donc cette
    assertion-là mesurerait la forme du graphe et pas la direction.
    """
    keys = keys_from_edges(DIAMOND)
    right = layout(keys, DIAMOND, direction="right")
    down = layout(keys, DIAMOND, direction="down")
    assert right.width > down.width
    assert down.height > right.height


def test_metrics_drive_the_geometry() -> None:
    """Le thème décide des distances ; le moteur n'a aucune valeur à lui."""
    keys = keys_from_edges(DIAMOND)
    tight = layout(keys, DIAMOND, metrics=Metrics(layer_gap=10))
    loose = layout(keys, DIAMOND, metrics=Metrics(layer_gap=200))
    assert loose.width > tight.width


def test_a_declared_width_is_honoured() -> None:
    keys = keys_from_edges(DIAMOND)
    placed = layout(keys, DIAMOND, widths={"a": 400.0})
    assert placed.box("a").width == 400.0
    # La couche suivante commence APRÈS le nœud élargi, pas dessus.
    assert placed.box("b").x >= 400.0


def test_the_neighbourhood_reaches_both_ways() -> None:
    assert neighbourhood("b", DIAMOND) == {"a", "b", "d"}


def test_a_deeper_neighbourhood_reaches_further() -> None:
    assert neighbourhood("b", DIAMOND, depth=2) == {"a", "b", "c", "d"}


def test_an_empty_graph_places_nothing() -> None:
    placed = layout([], [])
    assert placed.boxes == ()
    assert placed.layers == ()


def test_an_edge_to_an_unknown_node_is_ignored() -> None:
    """Une fonction pure appelée en plein rendu ne lève pas ; le
    composant, lui, refuse en amont ce qu'il peut nommer."""
    placed = layout(["a"], [("a", "ghost")])
    assert [b.key for b in placed.boxes] == ["a"]
    assert placed.routes == ()
