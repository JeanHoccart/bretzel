"""Placement en couches d'un graphe orienté — pur, sans rendu.

Aucun import du framework : ce module prend des clés et des arêtes, il
rend des coordonnées. C'est délibéré, et c'est ce qui rend la moitié
difficile du diagramme testable sans navigateur — un test unitaire peut
affirmer « aucune arête ne traverse un nœud » ou « le placement est
stable d'un run à l'autre » sans monter une page.

Les quatre passes (Sugiyama, 1981) :

1. **Casser les cycles.** Un parcours en profondeur, dans l'ordre
   d'entrée ; toute arête qui pointe vers un nœud encore sur la pile est
   inversée et mémorisée. On dessine ensuite la flèche dans le sens
   d'origine — l'inversion sert au placement, pas à l'affichage.
2. **Assigner les couches** — plus long chemin : ``couche(n) = 1 + max``
   des couches de ses prédécesseurs. La couche EST l'ordre de lecture :
   un nœud est toujours après ce qu'il consomme.
3. **Réduire les croisements** — l'heuristique de la médiane, quatre
   balayages aller-retour. Minimiser les croisements est NP-difficile ;
   la médiane en enlève l'essentiel pour vingt lignes. On garde le
   meilleur ordre rencontré, mesuré par un comptage réel.
4. **Poser les coordonnées** — chaque nœud tiré vers la médiane de ses
   voisins, puis on écarte ce qui se chevauche.

Les **nœuds fantômes** ne sont pas un détail d'implémentation. Une arête
qui saute deux couches sans eux passe en ligne droite PAR-DESSUS les
nœuds intermédiaires : c'est le défaut visuel n°1 d'un moteur en
couches écrit à la va-vite, et il est invisible tant qu'on ne teste que
des graphes à deux niveaux. Une arête longue est donc découpée en
segments d'une couche, chaque segment passant par un fantôme qui
participe à l'ordonnancement et au placement comme un vrai nœud.

⚠️ **Déterminisme.** Tout part de l'ORDRE d'entrée : les clés sont une
séquence, jamais un ensemble, et chaque égalité se départage par la
clé. Sans ça, deux rendus du même graphe diffèrent, et ni la
comparaison à l'octet près ni les captures de référence ne valent plus
rien.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Sequence

#: Le nombre de balayages de la passe 3. Quatre est la valeur classique :
#: mesuré sur les graphes d'app de ce dépôt (9 à 25 nœuds), le gain
#: s'annule dès le troisième — au-delà on paie sans rien gagner.
_SWEEPS = 4


@dataclasses.dataclass(frozen=True, slots=True)
class Metrics:
    """Les distances du placement, en pixels.

    Elles viennent du thème (``sizes``), pas d'ici : ce module ne
    connaît aucune valeur de design. ``node_width`` est FIXE par palier
    — le serveur ne mesure pas le texte, donc la seule façon de placer
    sans mesurer côté client est de décider la largeur à l'avance. Un
    nœud qui doit respirer passe par ``Node.width``.
    """

    node_width: float = 160.0
    node_height: float = 44.0
    #: Entre deux couches — c'est la longueur visible des arêtes.
    layer_gap: float = 72.0
    #: Entre deux nœuds d'une même couche.
    lane_gap: float = 20.0
    #: Marge autour du dessin, pour que rien ne colle au bord.
    padding: float = 16.0


@dataclasses.dataclass(frozen=True, slots=True)
class Box:
    """Un nœud placé — coin haut-gauche, plus sa taille effective."""

    key: str
    x: float
    y: float
    width: float
    height: float


@dataclasses.dataclass(frozen=True, slots=True)
class Route:
    """Une arête placée.

    ``path`` est le ``d`` d'un ``<path>`` SVG. ``flipped`` dit que
    l'arête remontait le graphe et a été inversée en passe 1 : le tracé
    va toujours de ``source`` à ``target``, c'est seulement sa forme qui
    tient compte du fait qu'elle revient en arrière.
    """

    source: str
    target: str
    path: str
    flipped: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class Placement:
    """Ce que rend le moteur, et tout ce qu'il rend."""

    boxes: tuple[Box, ...]
    routes: tuple[Route, ...]
    width: float
    height: float
    #: Les couches dans l'ordre de lecture, fantômes retirés. C'est
    #: l'ordre du DOM, donc l'ordre de tabulation.
    layers: tuple[tuple[str, ...], ...]

    def box(self, key: str) -> Box | None:
        for b in self.boxes:
            if b.key == key:
                return b
        return None


# ───────────────────────────────────────────────────────────────────────
# 1 — casser les cycles
# ───────────────────────────────────────────────────────────────────────


def break_cycles(
    keys: Sequence[str], edges: Sequence[tuple[str, str]]
) -> tuple[list[tuple[str, str]], frozenset[tuple[str, str]]]:
    """``(arêtes acycliques, arêtes inversées)``.

    Parcours en profondeur dans l'ordre d'entrée. Une arête vers un nœud
    encore SUR LA PILE ferme un cycle : on l'inverse. Une arête vers un
    nœud déjà fini n'en ferme aucun — c'est la distinction que rate un
    « déjà vu » naïf, et elle inverserait des arêtes parfaitement
    saines.
    """
    outgoing: dict[str, list[str]] = {k: [] for k in keys}
    for source, target in edges:
        if source in outgoing and target in outgoing:
            outgoing[source].append(target)

    done: set[str] = set()
    stack: set[str] = set()
    flipped: set[tuple[str, str]] = set()

    def walk(node: str) -> None:
        stack.add(node)
        for nxt in outgoing[node]:
            if nxt in stack:
                flipped.add((node, nxt))
            elif nxt not in done:
                walk(nxt)
        stack.discard(node)
        done.add(node)

    for key in keys:
        if key not in done:
            walk(key)

    acyclic: list[tuple[str, str]] = []
    for source, target in edges:
        if source not in outgoing or target not in outgoing:
            continue
        if (source, target) in flipped:
            acyclic.append((target, source))
        else:
            acyclic.append((source, target))
    return acyclic, frozenset(flipped)


# ───────────────────────────────────────────────────────────────────────
# 2 — assigner les couches
# ───────────────────────────────────────────────────────────────────────


def assign_layers(
    keys: Sequence[str], edges: Sequence[tuple[str, str]]
) -> dict[str, int]:
    """``{clé: index de couche}`` — plus long chemin depuis les racines.

    Sur un graphe acyclique, l'ordre topologique suffit : la couche d'un
    nœud est un de plus que la plus profonde de ses sources. Une boucle
    sur soi-même (``a → a``) est ignorée plutôt que refusée — elle ne
    contraint aucune couche, et lever dessus punirait un graphe légitime
    (une feature qui se cite elle-même) pour une raison cosmétique.
    """
    incoming: dict[str, list[str]] = {k: [] for k in keys}
    outgoing: dict[str, list[str]] = {k: [] for k in keys}
    for source, target in edges:
        if source == target or source not in incoming or target not in incoming:
            continue
        incoming[target].append(source)
        outgoing[source].append(target)

    layer = {k: 0 for k in keys}
    pending = {k: len(incoming[k]) for k in keys}
    queue = [k for k in keys if pending[k] == 0]
    seen = 0
    while queue:
        node = queue.pop(0)
        seen += 1
        for nxt in outgoing[node]:
            layer[nxt] = max(layer[nxt], layer[node] + 1)
            pending[nxt] -= 1
            if pending[nxt] == 0:
                queue.append(nxt)

    # Un reste signifie un cycle non cassé : impossible si `break_cycles`
    # a tourné, mais ce module s'appelle aussi tout seul dans les tests.
    # On empile les survivants derrière tout le monde plutôt que de
    # lever — un diagramme dégradé reste plus utile qu'une exception.
    if seen < len(keys):
        floor = max(layer.values(), default=0) + 1
        for key in keys:
            if pending[key] > 0:
                layer[key] = floor
    return layer


# ───────────────────────────────────────────────────────────────────────
# 3 — réduire les croisements
# ───────────────────────────────────────────────────────────────────────


def _median(positions: list[int], fallback: float) -> float:
    """La médiane, et le nœud SANS voisin garde sa place.

    Rendre 0 pour un nœud isolé le catapulterait en tête de couche à
    chaque balayage : il n'a aucune raison de bouger, donc son rang
    courant fait office de médiane.
    """
    if not positions:
        return fallback
    positions = sorted(positions)
    middle = len(positions) // 2
    if len(positions) % 2:
        return float(positions[middle])
    return (positions[middle - 1] + positions[middle]) / 2


def _crossings(
    upper: Sequence[str], lower: Sequence[str], pairs: Sequence[tuple[str, str]]
) -> int:
    """Les croisements entre deux couches adjacentes.

    Comptage par paires : deux arêtes se croisent quand leurs extrémités
    sont dans l'ordre inverse d'un côté à l'autre. C'est quadratique en
    nombre d'arêtes, ce qui est sans conséquence ici — le plus dense des
    graphes du dépôt fait 61 arêtes.
    """
    rank_upper = {k: i for i, k in enumerate(upper)}
    rank_lower = {k: i for i, k in enumerate(lower)}
    linked = [
        (rank_upper[a], rank_lower[b])
        for a, b in pairs
        if a in rank_upper and b in rank_lower
    ]
    total = 0
    for i, (a1, b1) in enumerate(linked):
        for a2, b2 in linked[i + 1 :]:
            if (a1 - a2) * (b1 - b2) < 0:
                total += 1
    return total


def order_layers(
    layers: Sequence[Sequence[str]], edges: Sequence[tuple[str, str]]
) -> tuple[tuple[str, ...], ...]:
    """Ordonne chaque couche pour réduire les croisements.

    Quatre balayages, descendant puis montant, et on GARDE le meilleur
    ordre rencontré — pas le dernier. La médiane n'est pas monotone :
    un balayage peut dégrader, et sans cette mémoire on livrerait
    parfois un ordre pire que celui de départ.
    """
    current = [list(layer) for layer in layers]
    by_pair = [
        [(a, b) for a, b in edges if a in set(current[i]) and b in set(current[i + 1])]
        for i in range(max(len(current) - 1, 0))
    ]

    def total_crossings(state: list[list[str]]) -> int:
        return sum(
            _crossings(state[i], state[i + 1], by_pair[i])
            for i in range(len(state) - 1)
        )

    best = [list(layer) for layer in current]
    best_score = total_crossings(current)

    for sweep in range(_SWEEPS):
        descending = sweep % 2 == 0
        indexes = (
            range(1, len(current)) if descending else range(len(current) - 2, -1, -1)
        )
        for i in indexes:
            fixed = current[i - 1] if descending else current[i + 1]
            rank = {k: j for j, k in enumerate(fixed)}
            pairs = by_pair[i - 1] if descending else by_pair[i]
            neighbours: dict[str, list[int]] = {k: [] for k in current[i]}
            for a, b in pairs:
                moving, anchor = (b, a) if descending else (a, b)
                if moving in neighbours and anchor in rank:
                    neighbours[moving].append(rank[anchor])
            # L'égalité se départage par le rang COURANT puis par la clé :
            # deux nœuds de même médiane doivent se classer pareil à
            # chaque exécution, sinon le placement n'est plus stable.
            order = {k: j for j, k in enumerate(current[i])}
            current[i] = sorted(
                current[i],
                key=lambda k: (_median(neighbours[k], order[k]), order[k], k),
            )
        score = total_crossings(current)
        if score < best_score:
            best_score = score
            best = [list(layer) for layer in current]

    return tuple(tuple(layer) for layer in best)


# ───────────────────────────────────────────────────────────────────────
# 4 — poser les coordonnées
# ───────────────────────────────────────────────────────────────────────


def _cross_positions(
    layers: Sequence[Sequence[str]],
    edges: Sequence[tuple[str, str]],
    sizes: dict[str, float],
    metrics: Metrics,
) -> dict[str, float]:
    """La position de chaque nœud SUR l'axe transverse.

    Deux temps par couche : chacun vise la moyenne de ses voisins déjà
    placés, puis un balayage écarte les chevauchements en respectant
    l'ordre décidé en passe 3 — on ne réordonne jamais ici, sinon on
    défait les croisements qu'on vient d'enlever.
    """
    incoming: dict[str, list[str]] = {}
    for source, target in edges:
        incoming.setdefault(target, []).append(source)
        incoming.setdefault(source, [])

    pos: dict[str, float] = {}
    for index, layer in enumerate(layers):
        cursor = 0.0
        wanted: list[float] = []
        for key in layer:
            if index == 0:
                wanted.append(cursor)
            else:
                anchors = [
                    pos[n] + sizes.get(n, metrics.node_height) / 2
                    for n in incoming.get(key, [])
                    if n in pos
                ]
                centre = sum(anchors) / len(anchors) if anchors else cursor
                wanted.append(centre - sizes.get(key, metrics.node_height) / 2)
            cursor += sizes.get(key, metrics.node_height) + metrics.lane_gap

        # Écartement : on remonte le premier à 0 puis on pousse vers
        # l'avant. Un seul sens suffit — l'ordre est déjà figé.
        placed: list[float] = []
        edge_of_previous = float("-inf")
        for key, want in zip(layer, wanted, strict=True):
            value = max(want, edge_of_previous)
            placed.append(value)
            edge_of_previous = value + sizes.get(key, metrics.node_height) + metrics.lane_gap
        for key, value in zip(layer, placed, strict=True):
            pos[key] = value

    # Recentrer chaque couche sur l'étendue globale : sans ça, une
    # couche courte reste collée en haut et le dessin part en escalier.
    spans = []
    for layer in layers:
        if not layer:
            spans.append((0.0, 0.0))
            continue
        start = min(pos[k] for k in layer)
        end = max(pos[k] + sizes.get(k, metrics.node_height) for k in layer)
        spans.append((start, end))
    widest = max((end - start for start, end in spans), default=0.0)
    for layer, (start, end) in zip(layers, spans, strict=True):
        shift = (widest - (end - start)) / 2 - start
        for key in layer:
            pos[key] += shift
    return pos


# ───────────────────────────────────────────────────────────────────────
# Le moteur
# ───────────────────────────────────────────────────────────────────────


def _dummy(source: str, target: str, index: int) -> str:
    return f"\x00{source}\x00{target}\x00{index}"


def _is_dummy(key: str) -> bool:
    return key.startswith("\x00")


def _spline(points: Sequence[tuple[float, float]], horizontal: bool) -> str:
    """Une courbe lisse passant par ``points``.

    Cubique par segment, avec des poignées posées à mi-distance sur
    l'axe des couches : la courbe part et arrive perpendiculaire au
    nœud, ce qui la rend lisible même quand deux arêtes se rejoignent
    au même endroit.
    """
    if len(points) < 2:
        return ""
    out = [f"M{points[0][0]:.2f},{points[0][1]:.2f}"]
    for (x1, y1), (x2, y2) in zip(points, points[1:], strict=False):
        if horizontal:
            mid = (x1 + x2) / 2
            out.append(f"C{mid:.2f},{y1:.2f} {mid:.2f},{y2:.2f} {x2:.2f},{y2:.2f}")
        else:
            mid = (y1 + y2) / 2
            out.append(f"C{x1:.2f},{mid:.2f} {x2:.2f},{mid:.2f} {x2:.2f},{y2:.2f}")
    return " ".join(out)


def layout(
    keys: Sequence[str],
    edges: Sequence[tuple[str, str]],
    *,
    metrics: Metrics | None = None,
    direction: str = "right",
    widths: dict[str, float] | None = None,
) -> Placement:
    """Placer un graphe orienté.

    ``keys`` donne l'ordre d'entrée — c'est lui qui rend le résultat
    reproductible. ``direction`` vaut ``"right"`` (les couches sont des
    colonnes, on lit de gauche à droite) ou ``"down"``.

    Les arêtes qui citent une clé inconnue sont ignorées : un diagramme
    amputé vaut mieux qu'une exception au milieu d'un rendu, et le
    composant, lui, refuse en amont ce qu'il peut nommer.
    """
    metrics = metrics or Metrics()
    widths = widths or {}
    keys = list(dict.fromkeys(keys))  # dédoublonne en gardant l'ordre
    known = set(keys)
    pairs = [(a, b) for a, b in edges if a in known and b in known]

    acyclic, flipped = break_cycles(keys, pairs)
    depth = assign_layers(keys, acyclic)

    # Fantômes : une arête qui saute des couches est découpée, sinon
    # elle passe en droite ligne par-dessus ce qu'il y a entre.
    routed: list[tuple[str, list[str]]] = []
    expanded: list[tuple[str, str]] = []
    ghosts: list[tuple[str, int]] = []
    for source, target in acyclic:
        gap = depth[target] - depth[source]
        if gap <= 1:
            expanded.append((source, target))
            routed.append((f"{source}\x00{target}", [source, target]))
            continue
        chain = [source]
        for step in range(1, gap):
            ghost = _dummy(source, target, step)
            ghosts.append((ghost, depth[source] + step))
            chain.append(ghost)
        chain.append(target)
        for a, b in zip(chain, chain[1:], strict=False):
            expanded.append((a, b))
        routed.append((f"{source}\x00{target}", chain))

    for ghost, level in ghosts:
        depth[ghost] = level

    # `max(..., default=0) + 1` donnerait UNE couche vide sur un graphe
    # sans nœud, et `layers` cesserait d'être le témoin fiable du vide.
    height = (max(depth.values(), default=0) + 1) if keys else 0
    layers: list[list[str]] = [[] for _ in range(height)]
    for key in keys:
        layers[depth[key]].append(key)
    for ghost, level in ghosts:
        layers[level].append(ghost)

    ordered = order_layers(layers, expanded)

    # Un fantôme réserve une VOIE ENTIÈRE, comme un vrai nœud.
    #
    # Il ne se dessine pas, donc le réduire à un point est tentant — et
    # c'est faux. Un point se retrouve collé au bord d'un nœud voisin,
    # et le tracé qui en repart bombe dans la boîte de ce voisin : une
    # arête PASSE ALORS SUR un nœud, le défaut n°1 d'un moteur en
    # couches. Mesuré par `test_no_edge_passes_through_a_node`, qui
    # rougissait exactement là-dessus avant ce correctif.
    horizontal = direction != "down"

    def _cross_extent(key: str) -> float:
        if horizontal:
            return metrics.node_height
        return metrics.node_width if _is_dummy(key) else widths.get(key, metrics.node_width)

    cross_size = {k: _cross_extent(k) for layer in ordered for k in layer}
    cross = _cross_positions(ordered, expanded, cross_size, metrics)

    # L'axe des couches : chaque couche est posée après la plus large de
    # la précédente, pour que `width=` sur un nœud ne chevauche rien.
    along: dict[int, float] = {}
    extent: dict[int, float] = {}
    cursor = metrics.padding
    for index, layer in enumerate(ordered):
        along[index] = cursor
        if horizontal:
            extent[index] = max(
                (widths.get(k, metrics.node_width) for k in layer if not _is_dummy(k)),
                default=metrics.node_width,
            )
        else:
            extent[index] = metrics.node_height
        cursor += extent[index] + metrics.layer_gap

    boxes: list[Box] = []
    centres: dict[str, tuple[float, float]] = {}
    spans: dict[str, tuple[float, float]] = {}
    #: Un fantôme n'est pas un POINT mais un SEGMENT : l'arête traverse
    #: la couche à plat sur sa voie, et ne remonte ou ne descend que dans
    #: l'écart entre deux couches, où il n'y a rien.
    #:
    #: Le point seul plaçait l'entrée du fantôme au bord GAUCHE de la
    #: couche : la courbe qui en repartait balayait alors toute la
    #: largeur du nœud voisin en descendant, et le traversait. Mesuré :
    #: `a→d` entrait dans `b` à x≈408 sur le losange du test.
    ghosts_line: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {}
    for index, layer in enumerate(ordered):
        for key in layer:
            width = widths.get(key, metrics.node_width)
            if horizontal:
                x, y = along[index], cross[key] + metrics.padding
            else:
                x, y = cross[key] + metrics.padding, along[index]
            w, h = width, metrics.node_height
            if _is_dummy(key):
                if horizontal:
                    lane = y + metrics.node_height / 2
                    ghosts_line[key] = ((x, lane), (x + extent[index], lane))
                else:
                    lane = x + metrics.node_width / 2
                    ghosts_line[key] = ((lane, y), (lane, y + extent[index]))
                continue
            boxes.append(Box(key=key, x=x, y=y, width=w, height=h))
            centres[key] = (x + w / 2, y + h / 2)
            spans[key] = (x, x + w) if horizontal else (y, y + h)

    routes: list[Route] = []
    for tag, chain in routed:
        source, target = tag.split("\x00")
        points: list[tuple[float, float]] = []
        for position, key in enumerate(chain):
            if _is_dummy(key):
                points.extend(ghosts_line[key])
                continue
            cx, cy = centres[key]
            low, high = spans[key]
            if position == 0:
                points.append((high, cy) if horizontal else (cx, high))
            elif position == len(chain) - 1:
                points.append((low, cy) if horizontal else (cx, low))
            else:  # pragma: no cover — un vrai nœud n'est jamais au milieu
                points.append((cx, cy))
        was_flipped = (target, source) in flipped
        head, tail = (target, source) if was_flipped else (source, target)
        if was_flipped:
            points.reverse()
        routes.append(
            Route(source=head, target=tail, path=_spline(points, horizontal), flipped=was_flipped)
        )

    # La toile doit contenir les ARETES aussi, pas seulement les boites.
    #
    # Un fantome n'est pas une boite : mesurer sur `boxes` seul rendait
    # une toile trop courte, et une arete longue — dont la voie est
    # justement HORS des couches occupees — sortait par le bas du cadre
    # et disparaissait. Invisible a toute lecture de HTML, invisible aux
    # sondes qui ne regardent que les noeuds ; vu sur la capture.
    edge_points = [pt for line in ghosts_line.values() for pt in line]
    width = max(
        [b.x + b.width for b in boxes] + [x for x, _y in edge_points],
        default=0.0,
    ) + metrics.padding
    total_height = max(
        [b.y + b.height for b in boxes] + [y for _x, y in edge_points],
        default=0.0,
    ) + metrics.padding
    return Placement(
        boxes=tuple(boxes),
        routes=tuple(routes),
        width=width,
        height=total_height,
        layers=tuple(tuple(k for k in layer if not _is_dummy(k)) for layer in ordered),
    )


def neighbourhood(
    focus: str, edges: Sequence[tuple[str, str]], *, depth: int = 1
) -> set[str]:
    """``focus`` plus ce qu'il touche, à ``depth`` sauts, les deux sens.

    C'est la vue par défaut du composant. Le graphe entier d'une app
    réelle est dense — 61 arêtes pour 22 nœuds, mesurés sur une app depuis retirée —
    et un enchevêtrement ne répond à aucune question ; le voisinage
    répond à celle qu'on a effectivement : « qui touche à ça ».
    """
    reached = {focus}
    frontier = {focus}
    for _ in range(max(depth, 0)):
        nxt: set[str] = set()
        for source, target in edges:
            if source in frontier:
                nxt.add(target)
            if target in frontier:
                nxt.add(source)
        frontier = nxt - reached
        reached |= nxt
    return reached


def keys_from_edges(edges: Iterable[tuple[str, str]]) -> list[str]:
    """L'ensemble des nœuds cités, dans l'ordre de première apparition.

    C'est le niveau 1 de l'API : ``ui.diagram(edges=[…])`` sans déclarer
    les nœuds. L'ordre vient des arêtes, donc il reste déterministe.
    """
    out: list[str] = []
    for source, target in edges:
        for key in (source, target):
            if key not in out:
                out.append(key)
    return out
