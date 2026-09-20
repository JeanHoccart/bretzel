"""Layered layout of a directed graph — pure, with no rendering.

No framework import: this module takes keys and edges, it returns
coordinates. It is deliberate, and it is what makes the diagram's hard
half testable without a browser — a unit test can assert "no edge crosses
a node" or "the layout is stable from one run to the next" without
mounting a page.

The four passes (Sugiyama, 1981):

1. **Break the cycles.** A depth-first walk, in input order; any edge
   pointing at a node still on the stack is reversed and remembered. We
   then draw the arrow in the original direction — the reversal serves
   the layout, not the display.
2. **Assign the layers** — longest path: ``layer(n) = 1 + max`` of its
   predecessors' layers. The layer IS the reading order: a node always
   comes after what it consumes.
3. **Reduce the crossings** — the median heuristic, four back-and-forth
   sweeps. Minimising crossings is NP-hard; the median removes the bulk
   of them in twenty lines. We keep the best order encountered, measured
   by a real count.
4. **Set the coordinates** — each node pulled towards the median of its
   neighbours, then we push apart what overlaps.

The **ghost nodes** are not an implementation detail. An edge that jumps
two layers without them goes in a straight line OVER the intermediate
nodes: it is the number-one visual defect of a hastily written layered
engine, and it is invisible as long as you only test two-level graphs. A
long edge is therefore cut into one-layer segments, each segment passing
through a ghost that takes part in ordering and placement like a real
node.

⚠️ **Determinism.** Everything starts from the input ORDER: the keys are
a sequence, never a set, and every tie is broken by the key. Without
that, two renders of the same graph differ, and neither byte-exact
comparison nor reference screenshots are worth anything any more.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Sequence

#: The number of sweeps of pass 3. Four is the classic value: measured
#: on this repository's app graphs (9 to 25 nodes), the gain vanishes
#: from the third onwards — beyond that you pay without gaining.
_SWEEPS = 4


@dataclasses.dataclass(frozen=True, slots=True)
class Metrics:
    """The layout's distances, in pixels.

    They come from the theme (``sizes``), not from here: this module
    knows no design value. ``node_width`` is FIXED per step — the server
    does not measure text, so the only way to lay out without measuring
    on the client is to decide the width in advance. A node that needs
    room goes through ``Node.width``.
    """

    node_width: float = 160.0
    node_height: float = 44.0
    #: Between two layers — it is the visible length of the edges.
    layer_gap: float = 72.0
    #: Between two nodes of the same layer.
    lane_gap: float = 20.0
    #: Margin around the drawing, so nothing sticks to the edge.
    padding: float = 16.0


@dataclasses.dataclass(frozen=True, slots=True)
class Box:
    """A placed node — top-left corner, plus its effective size."""

    key: str
    x: float
    y: float
    width: float
    height: float


@dataclasses.dataclass(frozen=True, slots=True)
class Route:
    """A placed edge.

    ``path`` is an SVG ``<path>``'s ``d``. ``flipped`` says the edge went
    back up the graph and was reversed in pass 1: the path always goes
    from ``source`` to ``target``, only its shape takes account of the
    fact that it goes backwards.
    """

    source: str
    target: str
    path: str
    flipped: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class Placement:
    """What the engine returns, and all it returns."""

    boxes: tuple[Box, ...]
    routes: tuple[Route, ...]
    width: float
    height: float
    #: The layers in reading order, ghosts removed. It is the DOM's
    #: order, so the tab order.
    layers: tuple[tuple[str, ...], ...]

    def box(self, key: str) -> Box | None:
        for b in self.boxes:
            if b.key == key:
                return b
        return None


# ───────────────────────────────────────────────────────────────────────
# 1 — break the cycles
# ───────────────────────────────────────────────────────────────────────


def break_cycles(
    keys: Sequence[str], edges: Sequence[tuple[str, str]]
) -> tuple[list[tuple[str, str]], frozenset[tuple[str, str]]]:
    """``(acyclic edges, reversed edges)``.

    A depth-first walk in input order. An edge towards a node still ON
    THE STACK closes a cycle: we reverse it. An edge towards an already
    finished node closes none — it is the distinction a naive "already
    seen" misses, and it would reverse perfectly healthy edges.
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
# 2 — assign the layers
# ───────────────────────────────────────────────────────────────────────


def assign_layers(
    keys: Sequence[str], edges: Sequence[tuple[str, str]]
) -> dict[str, int]:
    """``{key: layer index}`` — longest path from the roots.

    On an acyclic graph, the topological order is enough: a node's layer
    is one more than the deepest of its sources. A self-loop (``a → a``)
    is ignored rather than refused — it constrains no layer, and raising
    on it would punish a legitimate graph (a feature that cites itself)
    for a cosmetic reason.
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

    # A remainder means an unbroken cycle: impossible if `break_cycles`
    # has run, but this module is also called on its own in the tests. We
    # stack the survivors behind everybody else rather than raise — a
    # degraded diagram is still more useful than an exception.
    if seen < len(keys):
        floor = max(layer.values(), default=0) + 1
        for key in keys:
            if pending[key] > 0:
                layer[key] = floor
    return layer


# ───────────────────────────────────────────────────────────────────────
# 3 — reduce the crossings
# ───────────────────────────────────────────────────────────────────────


def _median(positions: list[int], fallback: float) -> float:
    """The median, and a node WITH no neighbour keeps its place.

    Returning 0 for an isolated node would catapult it to the head of the
    layer at every sweep: it has no reason to move, so its current rank
    serves as its median.
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
    """The crossings between two adjacent layers.

    Counted pairwise: two edges cross when their ends are in the reverse
    order from one side to the other. It is quadratic in the number of
    edges, which is of no consequence here — the repository's densest
    graph has 61 edges.
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
    """Order each layer so as to reduce the crossings.

    Four sweeps, downward then upward, and we KEEP the best order
    encountered — not the last. The median is not monotone: a sweep can
    make things worse, and without that memory we would sometimes ship
    an order worse than the starting one.
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
            # Ties are broken by the CURRENT rank then by the key: two
            # nodes with the same median must rank alike at every run,
            # otherwise the layout is no longer stable.
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
# 4 — set the coordinates
# ───────────────────────────────────────────────────────────────────────


def _cross_positions(
    layers: Sequence[Sequence[str]],
    edges: Sequence[tuple[str, str]],
    sizes: dict[str, float],
    metrics: Metrics,
) -> dict[str, float]:
    """Each node's position ON the cross axis.

    Two steps per layer: each aims at the mean of its already placed
    neighbours, then a sweep pushes apart the overlaps while respecting
    the order decided in pass 3 — we never reorder here, otherwise we
    would undo the crossings we have just removed.
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

        # Pushing apart: we bring the first back up to 0 then push
        # forward. One direction is enough — the order is already fixed.
        placed: list[float] = []
        edge_of_previous = float("-inf")
        for key, want in zip(layer, wanted, strict=True):
            value = max(want, edge_of_previous)
            placed.append(value)
            edge_of_previous = value + sizes.get(key, metrics.node_height) + metrics.lane_gap
        for key, value in zip(layer, placed, strict=True):
            pos[key] = value

    # Re-centre each layer on the overall extent: without that, a short
    # layer stays stuck at the top and the drawing goes staircase.
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
    """A smooth curve through ``points``.

    Cubic per segment, with handles set halfway along the layer axis: the
    curve leaves and arrives perpendicular to the node, which keeps it
    readable even when two edges meet at the same place.
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
    """Lay out a directed graph.

    ``keys`` gives the input order — it is what makes the result
    reproducible. ``direction`` is ``"right"`` (the layers are columns,
    you read left to right) or ``"down"``.

    Edges citing an unknown key are ignored: an amputated diagram is
    better than an exception in the middle of a render, and the
    component, for its part, refuses upstream what it can name.
    """
    metrics = metrics or Metrics()
    widths = widths or {}
    keys = list(dict.fromkeys(keys))  # dedupe while keeping the order
    known = set(keys)
    pairs = [(a, b) for a, b in edges if a in known and b in known]

    acyclic, flipped = break_cycles(keys, pairs)
    depth = assign_layers(keys, acyclic)

    # Ghosts: an edge that jumps layers is cut, otherwise it goes in a
    # straight line over whatever is in between.
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

    # `max(..., default=0) + 1` would give ONE empty layer on a graph
    # with no node, and `layers` would stop being a reliable witness of
    # emptiness.
    height = (max(depth.values(), default=0) + 1) if keys else 0
    layers: list[list[str]] = [[] for _ in range(height)]
    for key in keys:
        layers[depth[key]].append(key)
    for ghost, level in ghosts:
        layers[level].append(ghost)

    ordered = order_layers(layers, expanded)

    # A ghost reserves a WHOLE LANE, like a real node.
    #
    # It is not drawn, so reducing it to a point is tempting — and it is
    # wrong. A point ends up stuck to a neighbouring node's edge, and the
    # path leaving it bulges into that neighbour's box: an edge THEN
    # PASSES OVER a node, the number-one defect of a layered engine.
    # Measured by `test_no_edge_passes_through_a_node`, which went red on
    # exactly that before this fix.
    horizontal = direction != "down"

    def _cross_extent(key: str) -> float:
        if horizontal:
            return metrics.node_height
        return metrics.node_width if _is_dummy(key) else widths.get(key, metrics.node_width)

    cross_size = {k: _cross_extent(k) for layer in ordered for k in layer}
    cross = _cross_positions(ordered, expanded, cross_size, metrics)

    # The layer axis: each layer is placed after the widest of the
    # previous one, so a `width=` on a node overlaps nothing.
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
    #: A ghost is not a POINT but a SEGMENT: the edge crosses the layer
    #: flat along its lane, and only rises or falls in the gap between
    #: two layers, where there is nothing.
    #:
    #: The point alone placed the ghost's entry at the LEFT edge of the
    #: layer: the curve leaving it then swept the whole width of the
    #: neighbouring node on its way down, and went through it. Measured:
    #: `a→d` entered `b` at x≈408 on the test's diamond.
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
            else:  # pragma: no cover — a real node is never in the middle
                points.append((cx, cy))
        was_flipped = (target, source) in flipped
        head, tail = (target, source) if was_flipped else (source, target)
        if was_flipped:
            points.reverse()
        routes.append(
            Route(source=head, target=tail, path=_spline(points, horizontal), flipped=was_flipped)
        )

    # The canvas must contain the EDGES too, not only the boxes.
    #
    # A ghost is not a box: measuring on `boxes` alone gave a canvas that
    # was too short, and a long edge — whose lane is precisely OUTSIDE
    # the occupied layers — left through the bottom of the frame and
    # disappeared. Invisible to any reading of the HTML, invisible to
    # probes that only look at the nodes; seen on the screenshot.
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
    """``focus`` plus what it touches, at ``depth`` hops, both ways.

    It is the component's default view. A real app's whole graph is dense
    — 61 edges for 22 nodes, measured on an app since removed — and a
    tangle answers no question; the neighbourhood answers the one you
    actually have: "what touches this".
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
    """The set of cited nodes, in order of first appearance.

    It is the API's tier 1: ``ui.diagram(edges=[…])`` without declaring
    the nodes. The order comes from the edges, so it stays
    deterministic.
    """
    out: list[str] = []
    for source, target in edges:
        for key in (source, target):
            if key not in out:
                out.append(key)
    return out
