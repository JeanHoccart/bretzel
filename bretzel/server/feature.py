"""The ``Feature`` contract — a colocated slice's public boundary.

A feature is the unit of a Bretzel app : a package that colocates state,
logic and ui. Its ``feature.py`` declares three things and nothing more —
what it **is** (``kind``), what it **exposes** (``provides``), and what it
**depends on** (``uses`` / ``reads``).

The contract is meant to be *load-bearing*, not descriptive :
:meth:`bretzel.Bretzel.include` reads it to wire the app and validate the
dependency graph, so a contract that lies makes the app refuse to
assemble — it can't silently drift from the code (same principle as the
rest of Bretzel : execute the truth, don't write it on the side).

``uses`` are hard dependencies (I import that feature's public surface);
the graph they form must stay **acyclic**. ``reads`` is the sanctioned
read-only escape hatch for cross-domain reporting (a read-model reads
several domains but never writes them) — its targets must exist, but it
is deliberately kept out of the acyclicity check : a read is a runtime
lookup, not a construction-order dependency.
"""

from __future__ import annotations

import ast
import dataclasses
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _defining_module() -> str:
    """The dotted name of the module that constructed the ``Feature`` — the
    caller of ``Feature(...)``. Walks past this module's own frames so a
    factory here doesn't shadow the real definition site. Empty on failure."""
    frame = sys._getframe(1) if hasattr(sys, "_getframe") else None
    while frame is not None:
        name = frame.f_globals.get("__name__", "")
        if name != __name__:
            return name
        frame = frame.f_back
    return ""

# The fixed vocabulary of what a feature can BE. Kept small on purpose —
# a new kind is a real design decision, not a convenience.
FEATURE_KINDS: frozenset[str] = frozenset(
    {
        "shell",    # the root layout / app chrome
        "layout",   # a reusable frame referenced by ``layout=``
        "page",     # a route that renders a view
        "error",    # an HTTP-status handler (404 / 500 / …)
        "state",    # owns a typed State scope (page/session/user/app)
        "data",     # owns a persistent entity (model + repository)
        "logic",    # pure functions / a service — no state, no route
        "infra",    # wraps an external resource (db, cache, an SDK, the bus)
        "facade",   # fronts a sub-tree, re-exports a curated public surface
        "job",      # a scheduled / background task — no route
    }
)


class FeatureError(ValueError):
    """Raised when a feature contract is malformed, or a set of features
    doesn't form a valid graph (unknown dependency, cycle, name clash)."""


@dataclass(frozen=True)
class Feature:
    """One feature's contract. Declared once per feature package ::

        # features/cart/feature.py
        from bretzel import Feature
        from .state import CartState
        from .ui import cart_page

        feature = Feature(
            name="cart",
            kind="page",
            provides=[CartState, cart_page],   # the public surface
            uses=["catalog_data", "money"],    # the only features I may import
        )
    """

    name: str
    kind: str
    provides: tuple[Any, ...] = ()
    uses: tuple[str, ...] = ()
    reads: tuple[str, ...] = ()
    # The module that declared this feature — auto-captured, so the app map
    # can read the folder arborescence from it. Excluded from eq/hash/repr.
    module: str = field(default="", compare=False, repr=False)

    def __post_init__(self) -> None:
        # Frozen dataclass : normalise the iterables to tuples via the
        # object escape hatch, then validate the two scalar fields.
        object.__setattr__(self, "provides", tuple(self.provides))
        object.__setattr__(self, "uses", tuple(self.uses))
        object.__setattr__(self, "reads", tuple(self.reads))
        if not self.module:
            object.__setattr__(self, "module", _defining_module())

        if not isinstance(self.name, str) or not self.name.strip():
            raise FeatureError(
                f"Feature.name must be a non-empty string, got {self.name!r}."
            )
        if self.kind not in FEATURE_KINDS:
            raise FeatureError(
                f"Feature {self.name!r} has unknown kind {self.kind!r}. "
                f"Valid kinds : {', '.join(sorted(FEATURE_KINDS))}."
            )
        for label, deps in (("uses", self.uses), ("reads", self.reads)):
            for dep in deps:
                if not isinstance(dep, str) or not dep.strip():
                    raise FeatureError(
                        f"Feature {self.name!r} has a non-string {label} "
                        f"entry {dep!r} — {label} holds feature NAMES."
                    )


def validate_features(features: Iterable[Feature]) -> tuple[Feature, ...]:
    """Check a set of features forms a valid graph.

    Enforces, with a loud error rather than a silent surprise :

    - **unique names** — two features can't claim the same name ;
    - **resolvable dependencies** — every ``uses`` / ``reads`` target is a
      known feature in the set ;
    - **acyclic ``uses``** — the hard-dependency graph is a DAG.

    Returns the features as a tuple (handy for the caller). Raises
    :class:`FeatureError` on the first problem, with the offending name(s).
    This is what :meth:`bretzel.Bretzel.include` runs so the app refuses
    to assemble on a broken contract.
    """
    feats = tuple(features)

    by_name: dict[str, Feature] = {}
    for f in feats:
        if f.name in by_name:
            raise FeatureError(
                f"Duplicate feature name {f.name!r} — every feature is unique."
            )
        by_name[f.name] = f
    known = set(by_name)

    for f in feats:
        for label, deps in (("uses", f.uses), ("reads", f.reads)):
            for dep in deps:
                if dep not in known:
                    raise FeatureError(
                        f"Feature {f.name!r} declares {label}={dep!r}, which "
                        f"isn't a known feature. Known : {sorted(known)}."
                    )

    # Acyclicity of the ``uses`` graph — iterative DFS with white/grey/black
    # colouring so a cycle reports its full path instead of just "cycle".
    WHITE, GREY, BLACK = 0, 1, 2
    color = dict.fromkeys(known, WHITE)

    def _visit(start: str) -> None:
        # (node, iterator-of-remaining-deps) frames + a path for the message.
        frames: list[tuple[str, Any]] = [(start, iter(by_name[start].uses))]
        color[start] = GREY
        path = [start]
        while frames:
            node, deps = frames[-1]
            advanced = False
            for dep in deps:
                if color[dep] == GREY:
                    cycle = path[path.index(dep):] + [dep]
                    raise FeatureError(
                        "Cycle in uses : " + " → ".join(cycle)
                    )
                if color[dep] == WHITE:
                    color[dep] = GREY
                    path.append(dep)
                    frames.append((dep, iter(by_name[dep].uses)))
                    advanced = True
                    break
            if not advanced:
                color[node] = BLACK
                path.pop()
                frames.pop()

    for name in known:
        if color[name] == WHITE:
            _visit(name)

    return feats


# ───────────────────────────────────────────────────────────────────────
# The living skeleton — read the contracts into a graph
# ───────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProvideInfo:
    """One item a feature exposes, classified by what it is."""

    label: str        # the symbol's name (e.g. "cart_page", "CartState")
    kind: str         # "page" | "layout" | "error" | "state" | "view" | "class" | "function" | "value"
    detail: str = ""  # route path for a page, "HTTP 404" for an error, else ""
    module: str = ""  # the symbol's DEFINING module (obj.__module__) — the
                      # actual file it lives in, distinct from the feature's
                      # contract module. Lets the map link symbol → code.


@dataclass(frozen=True)
class FeatureNode:
    """One feature in the app graph — its contract, with ``provides``
    classified, plus its folder ``path`` (the group hierarchy)."""

    name: str
    kind: str
    provides: tuple[ProvideInfo, ...] = ()
    uses: tuple[str, ...] = ()
    reads: tuple[str, ...] = ()
    path: tuple[str, ...] = ()   # folder groups above it, e.g. ("projects",)
    module: str = ""
    renderable: bool = False     # provides a page or a layout (in the render tree)
    render_parent: str = ""      # the feature whose layout it renders under
    optimal_parent: str = ""     # for a SHARED (non-render) feature : the render
                                 # feature at the LCA of its consumers — where its
                                 # dependencies say it optimally belongs, regardless
                                 # of the repo folder. "" = global (whole app / unused).


@dataclass(frozen=True)
class AppGraph:
    """The whole app, read from its feature contracts : the nodes, the
    routes they mount, and the dependency edges. This is the living
    skeleton — one source (the ``Feature`` objects), read live, so it
    can't drift from the app it describes."""

    nodes: tuple[FeatureNode, ...] = ()
    routes: tuple[tuple[str, str], ...] = ()       # (path, feature name)
    edges: tuple[tuple[str, str, str], ...] = ()   # (from, to, "uses" | "reads")

    def to_dict(self) -> dict[str, Any]:
        """A JSON-friendly form — the machine-readable app map (for an
        agent to read the app's shape instead of grepping for it)."""
        return dataclasses.asdict(self)


def _classify_provide(obj: Any) -> ProvideInfo:
    """Label + kind + defining module for one provided symbol — read from
    its decorator marks / type, no heavy imports (keeps this module a leaf)."""
    label = getattr(obj, "__name__", None) or type(obj).__name__
    module = getattr(obj, "__module__", "") or ""

    err = getattr(obj, "_bz_error_page", None)
    if err is not None:
        return ProvideInfo(label, "error",
                           f"HTTP {getattr(err, 'status_code', '?')}", module)
    page_meta = getattr(obj, "_bz_page", None)
    if page_meta is not None:
        return ProvideInfo(label, "page",
                           str(getattr(page_meta, "path", "") or ""), module)
    if getattr(obj, "_bz_layout", None) is not None:
        return ProvideInfo(label, "layout", "", module)

    if isinstance(obj, type):
        # A Bretzel State stashes __scope__ (server) / __persist__ (client)
        # via its metaclass — cheap duck-check, no state-layer import.
        if hasattr(obj, "__scope__") or hasattr(obj, "__persist__"):
            return ProvideInfo(obj.__name__, "state", "", module)
        return ProvideInfo(obj.__name__, "class", "", module)

    # A ``@refreshable`` zone is a RefreshableHandle wrapping ``fn`` — an
    # embeddable render fragment ("view"), not an anonymous function. Duck-
    # check ``fn`` + ``id`` (its two ctor fields) — no render-layer import.
    fn = getattr(obj, "fn", None)
    if fn is not None and callable(fn) and hasattr(obj, "id"):
        return ProvideInfo(getattr(fn, "__name__", label), "view",
                           "", getattr(fn, "__module__", "") or module)
    if callable(obj):
        return ProvideInfo(label, "function", "", module)
    return ProvideInfo(label, "value", "", module)


def _common_prefix(seqs: list[list[str]]) -> list[str]:
    """Longest positional common prefix of a set of sequences (``[]`` if none
    or empty). Shared by the folder-path derivation and the LCA placement —
    both want "how far do these paths agree from the start"."""
    out: list[str] = []
    # ``strict=False`` explicite : la troncature à la plus COURTE séquence
    # est le comportement voulu — un préfixe commun ne peut pas dépasser
    # le plus court des chemins. C'est ce que `B905` demande d'écrire au
    # lieu de le laisser deviner, et `strict=True` casserait la fonction.
    for tier in zip(*seqs, strict=False):
        if len(set(tier)) == 1:
            out.append(tier[0])
        else:
            break
    return out


def _feature_paths(feats: list[Feature]) -> dict[str, tuple[str, ...]]:
    """Folder group-path per feature, derived from the defining modules.

    Strips the trailing ``feature`` / ``__init__`` segment and the common
    prefix shared by every feature (the ``features/`` root), leaving the
    folders that nest it — ``("projects",)`` for ``features/projects/board``,
    ``()`` for a top-level ``features/home``."""
    segs: dict[str, list[str]] = {}
    for f in feats:
        parts = (f.module or "").split(".") if f.module else []
        if parts and parts[-1] in ("feature", "__init__"):
            parts = parts[:-1]
        segs[f.name] = parts

    non_empty = [s for s in segs.values() if s]
    prefix = len(_common_prefix(non_empty))

    paths: dict[str, tuple[str, ...]] = {}
    for name, parts in segs.items():
        rel = parts[prefix:]
        paths[name] = tuple(rel[:-1])   # drop the feature's own leaf segment
    return paths


def _render_parents(feats: list[Feature]) -> dict[str, tuple[bool, str]]:
    """Per feature : ``(renderable?, the feature it renders under)``.

    Reads the render marks — a page's ``_bz_page.layout`` and a layout's
    ``_bz_layout.parent`` — and maps those functions back to the feature
    that PROVIDES them, so the app map can draw the render hierarchy
    (shell ▸ its pages ▸ a sub-layout ▸ its pages). A feature that provides
    neither a page nor a layout is not renderable — it's shared (data /
    logic / infra), lives outside the render tree."""
    provider: dict[Any, str] = {}
    for f in feats:
        for obj in f.provides:
            if getattr(obj, "_bz_page", None) is not None or \
                    getattr(obj, "_bz_layout", None) is not None:
                provider[obj] = f.name

    out: dict[str, tuple[bool, str]] = {}
    for f in feats:
        renderable, parent = False, ""
        for obj in f.provides:
            layout_meta = getattr(obj, "_bz_layout", None)
            page_meta = getattr(obj, "_bz_page", None)
            if layout_meta is not None:
                renderable = True
                if layout_meta.parent is not None:
                    parent = provider.get(layout_meta.parent, "")
                break
            if page_meta is not None:
                renderable = True
                if page_meta.layout is not None:
                    parent = provider.get(page_meta.layout, "")
                break
        out[f.name] = (renderable, parent)
    return out


def _optimal_parents(
    feats: list[Feature], render: dict[str, tuple[bool, str]]
) -> dict[str, str]:
    """Derived placement for each SHARED (non-render) feature : the render
    feature at the **lowest common ancestor** of everything that depends on it.

    This is the "optimal architecture" the app map reconstructs — independent
    of the repo folders. A data feature used across the whole app commons at
    the root (a global foundation) ; one used by a single branch sinks into
    that branch ; one used by a single page nests under that page. It answers
    "where does this piece *belong*, given who actually uses it".

    Method : reverse the ``uses``/``reads`` edges to get each feature's
    consumers ; resolve every consumer to its renderable **anchor** (a
    non-render consumer forwards to *its* consumers, so a logic→data→page
    chain lands on the page) ; take the LCA of those anchors' render-tree
    root-paths. No consumers (unused) or consumers under disjoint roots →
    ``""`` (global / floats to the top)."""
    renderable = {n: r for n, (r, _p) in render.items()}
    rparent = {n: p for n, (_r, p) in render.items()}
    names = {f.name for f in feats}

    def root_path(name: str) -> list[str]:
        """Render-tree path, root first, walking ``render_parent`` up."""
        chain: list[str] = []
        seen: set[str] = set()
        cur = name
        while cur and cur not in seen:
            seen.add(cur)
            chain.append(cur)
            cur = rparent.get(cur, "")
        chain.reverse()
        return chain

    rpaths = {n: root_path(n) for n in names if renderable.get(n)}

    consumers: dict[str, list[str]] = {n: [] for n in names}
    for f in feats:
        for dep in (*f.uses, *f.reads):
            if dep in consumers:
                consumers[dep].append(f.name)

    def anchors(name: str, seen: set[str]) -> set[str]:
        """Renderable features that (transitively) depend on ``name``."""
        if name in seen:
            return set()
        seen.add(name)
        out: set[str] = set()
        for c in consumers.get(name, ()):
            if renderable.get(c):
                out.add(c)
            else:
                out.update(anchors(c, seen))
        return out

    def lca(anchor_names: set[str]) -> str:
        # Every anchor is renderable (anchors() only adds renderable names) and
        # rpaths holds every renderable → no missing-key guard needed.
        cp = _common_prefix([rpaths[a] for a in anchor_names])
        return cp[-1] if cp else ""

    return {
        f.name: lca(anchors(f.name, set()))
        for f in feats
        if not renderable.get(f.name)
    }


def describe_app(features: Iterable[Feature]) -> AppGraph:
    """Read a set of feature contracts into an :class:`AppGraph`.

    Pass ``app.features``. Returns the nodes (each with its ``provides``
    classified, its folder ``path``, its render parent, and its derived
    ``optimal_parent``), the routes the pages mount, and the ``uses`` /
    ``reads`` edges. The anti-rot spine for the app map : it reads the
    ``Feature`` objects the app runs on."""
    feats = list(features)
    paths = _feature_paths(feats)
    render = _render_parents(feats)
    optimal = _optimal_parents(feats, render)
    nodes: list[FeatureNode] = []
    routes: list[tuple[str, str]] = []
    edges: list[tuple[str, str, str]] = []

    for f in feats:
        provides = tuple(_classify_provide(p) for p in f.provides)
        renderable, render_parent = render.get(f.name, (False, ""))
        nodes.append(FeatureNode(
            f.name, f.kind, provides, f.uses, f.reads,
            path=paths.get(f.name, ()), module=f.module or "",
            renderable=renderable, render_parent=render_parent,
            optimal_parent=optimal.get(f.name, ""),
        ))
        for pv in provides:
            if pv.kind == "page" and pv.detail:
                routes.append((pv.detail, f.name))
        edges.extend((f.name, dep, "uses") for dep in f.uses)
        edges.extend((f.name, dep, "reads") for dep in f.reads)

    routes.sort()
    return AppGraph(tuple(nodes), tuple(routes), tuple(edges))


# ───────────────────────────────────────────────────────────────────────
# Lints — le manifeste arbitré contre la réalité (le graphe ne peut pas
# mentir : L1 attrape l'oubli, L2 attrape la dérive). Émis en WARN au
# démarrage — jamais bloquants, contrairement à validate_features.
# ───────────────────────────────────────────────────────────────────────


def undeclared_provides(
    features: Iterable[Feature], registered: Iterable[Any]
) -> list[tuple[str, str]]:
    """L1 — routables enregistrés (pages / handlers d'erreur) couverts par
    AUCUNE ``Feature`` : ils tournent, mais la carte ne les voit pas et le
    graphe ne les valide pas — le squelette mentirait par omission.

    Retourne ``[(label, route_ou_vide), ...]`` pour chaque orphelin.
    """
    covered = {id(obj) for f in features for obj in f.provides}
    out: list[tuple[str, str]] = []
    for obj in registered:
        if id(obj) in covered:
            continue
        page_meta = getattr(obj, "_bz_page", None)
        route = str(getattr(page_meta, "path", "") or "") if page_meta else ""
        out.append((getattr(obj, "__name__", repr(obj)), route))
    return out


@dataclass(frozen=True)
class DriftReport:
    """L2 — l'écart d'UNE feature entre son contrat et ses imports réels."""

    feature: str
    missing: tuple[str, ...] = ()   # importé mais non déclaré (uses/reads)
    stale: tuple[str, ...] = ()     # déclaré mais jamais importé


def _feature_prefix(module: str) -> str:
    """Le package qu'une feature POSSÈDE : son module de contrat, débarrassé
    du segment ``feature``/``__init__`` (dossier-feature → tout le dossier)."""
    parts = module.split(".") if module else []
    if parts and parts[-1] in ("feature", "__init__"):
        parts = parts[:-1]
    return ".".join(parts)


def _imports_of(file: str, module_name: str) -> set[str]:
    """Modules (absolus) importés par ``file`` — top-level ET locaux (un
    import différé est une vraie dépendance). Les relatifs sont résolus
    contre le module. Limite documentée : un import sous ``TYPE_CHECKING``
    compte aussi (rare dans du code de feature, et un WARN se discute)."""
    try:
        tree = ast.parse(Path(file).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = module_name.split(".")[: -node.level]
                mod = ".".join(base + ([node.module] if node.module else []))
            else:
                mod = node.module or ""
            if mod:
                out.add(mod)
    return out


def dependency_drift(features: Iterable[Feature]) -> list[DriftReport]:
    """L2 — confronte les ``uses``/``reads`` DÉCLARÉS aux imports RÉELS
    (AST des modules de chaque feature, déjà chargés dans ``sys.modules``).

    Excusés : soi-même ; le parent de RENDU (une page importe son layout
    via ``layout=`` — c'est un lien de rendu déclaré par le mark, pas une
    dépendance à redire) ; tout module n'appartenant à aucune feature.
    La distinction uses/reads n'étant pas dérivable d'un import, c'est
    l'UNION déclarée qui est comparée. Le pattern est celui de Nx
    (``enforce-module-boundaries``) : déclaré + dérivé + réconciliateur.
    """
    feats = list(features)
    prefixes = {f.name: _feature_prefix(f.module or "") for f in feats}
    owners = sorted(((p, n) for n, p in prefixes.items() if p),
                    key=lambda t: -len(t[0]))

    def owner_of(mod: str) -> str:
        for prefix, name in owners:   # plus long préfixe d'abord
            if mod == prefix or mod.startswith(prefix + "."):
                return name
        return ""

    render = _render_parents(feats)
    out: list[DriftReport] = []
    for f in feats:
        prefix = prefixes[f.name]
        if not prefix:
            continue
        imported: set[str] = set()
        for mod_name, mod in list(sys.modules.items()):
            if mod is None or owner_of(mod_name) != f.name:
                continue
            file = getattr(mod, "__file__", None)
            if not file:
                continue
            for target in _imports_of(file, mod_name):
                owner = owner_of(target)
                if owner and owner != f.name:
                    imported.add(owner)
        _renderable, parent = render.get(f.name, (False, ""))
        imported.discard(parent)
        declared = (set(f.uses) | set(f.reads)) - {parent}
        missing = tuple(sorted(imported - declared))
        stale = tuple(sorted(declared - imported))
        if missing or stale:
            out.append(DriftReport(f.name, missing, stale))
    return out
