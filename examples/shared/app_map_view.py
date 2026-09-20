"""Shared renderer of the app map — v4, on the agreed model
(``.claude/bretzel/app-map-model.md``). Reused by flat, mad, …

Three roles, each with ITS representation:

- **ANCHOR** (shell/layout/page/error — renders): the pure render tree. A
  page is never a folder; the errors live in a micro-group "erreurs"
  under their layout.
- **BASE** (data/state/logic/facade/infra — is consumed): groups attached
  to **layouts only** (Option A agreed). What is private to one page goes
  up to the parent layout with a "private to <page>" badge.
- **ENTRY** (job — is triggered): an "entry points" group at the root.

The visuals are deliberately generic: ONE single guide-line style
(containment); the colour lives in the icons; a group is a plain title
(eyebrow), with no border of its own.

Click grammar: a click on a row is ALWAYS selection/detail; the chevron
is a separate target (layouts only). Hover: what the feature consumes
lights up — direct in full, transitive dimmed. The detail shows the
consumption chain ("geo ← planning_engine ← planning · rounds") and
each symbol's file. The routes badge is clickable → the table.
"""

from __future__ import annotations

from bretzel import refreshable, ui
from bretzel.render import maybe_current_context
from bretzel.server import AppGraph, describe_app
from bretzel.state import ClientState, PageState, field

# The colour lives in the icon (the name stays neutral). One glyph per
# rank.
_KIND_ICON = {
    "shell": "layout", "layout": "layout-template", "page": "file-text",
    "data": "database", "state": "box",
    "logic": "cog", "infra": "server", "facade": "layers",
    "error": "triangle-alert", "job": "clock",
}
_KIND_COLOR = {
    "page": "primary", "layout": "info", "shell": "info",
    "data": "warning", "state": "warning",
    "logic": "secondary", "infra": "secondary", "facade": "secondary",
    "error": "error", "job": "muted",
}
_KIND_SORT = {
    "shell": 0, "layout": 0, "page": 1, "data": 2, "state": 2,
    "logic": 3, "infra": 3, "facade": 3, "error": 4, "job": 4,
}
_BRANCH_KINDS = ("shell", "layout")

#: The rank's weight, in WHOLE classes. Above all not `f"font-{weight}"`:
#: an assembled class only exists under the dev compiler, which scans the
#: already-resolved DOM; in production the Tailwind binary only sweeps the
#: sources and will never see `font-medium`. The HTML is identical on both
#: sides, so nothing would say so.
_WEIGHT_CLASS = {"normal": "font-normal", "medium": "font-medium"}

_CLOSED = "$bz.state.MapUI.default.closed"
_LIT = "$bz.state.MapUI.default.lit"
_VIA = "$bz.state.MapUI.default.via"
_SEL = "$bz.state.MapUI.default.sel"
_PANEL = "$bz.state.MapUI.default.panel"


#: The icon per kind, reused by the dependency graph.
_KIND_OF_NODE = _KIND_ICON


class MapFocus(PageState):
    """The node at the centre of the dependency graph.

    SERVER side, unlike `MapUI.sel` which drives the tree: changing the
    centre changes the nodes DRAWN, hence the placement — and the
    placement is computed on the server. The two selections stay separate
    on purpose, because they answer two questions: the tree says "where
    this lives", the graph "who touches this".
    """

    key: str = field(default="")


def focus_node(key: str) -> None:
    # Clicking the centre again returns the overview: without that one
    # gets locked into a neighbourhood with no way out.
    state = MapFocus()
    state.key = "" if state.key == key else key


@refreshable(deps=[MapFocus])
def dependency_graph() -> None:
    """The map's DEPENDENCY axis — the one the tree does not show.

    `AppGraph` IS a graph: `nodes` plus `edges` as
    ``(source, target, "uses"|"reads")``. The tree projects its
    CONTAINMENT and only shows the edges highlighted on hover — so
    nothing at all on a machine with no fine pointer, and nothing
    printable anywhere. Here they are drawn.

    The zone takes no parameter (a zone never does), so it
    re-introspects the current app. That is also why the panel is not
    shown when `render_app_map(graph=…)` receives an explicit graph: it
    would show the app hosting it, not that one.
    """
    ctx = maybe_current_context()
    graph = describe_app(ctx.app.features if ctx is not None else ())
    known = {n.name for n in graph.nodes}
    # The panel never OPENS on the whole graph. Measured on an app since
    # removed: 22 nodes and 61 edges, unreadable — which is exactly the
    # reproach made to the map, and showing it by default would move the
    # problem without solving it.
    focus = MapFocus().key or entry_feature(graph)
    ui.diagram(
        nodes=[
            ui.node(n.name, label=n.name,
                    icon=_KIND_OF_NODE.get(n.kind, "box"),
                    color=_KIND_COLOR.get(n.kind, "muted"),
                    group=n.kind)
            for n in graph.nodes
        ],
        edges=[
            ui.edge(a, b, label=kind,
                    style="dashed" if kind == "reads" else "solid")
            for a, b, kind in graph.edges
            if a in known and b in known
        ],
        focus=focus or None,
        on_item_click=focus_node,
        size="sm",
        empty_text="No declared dependency.",
    )
    ui.text(
        f"Centred on “{focus}”. Click a node to move there — "
        f"solid line = uses, dashed = reads."
        if focus else "No declared dependency.",
        color="muted", size="sm",
    )


def entry_feature(graph: AppGraph) -> str:
    """The feature serving the home page — the default centre.

    ⚠️ Above all NOT the most connected node, which is the natural
    intuition and the worst possible choice: the most connected one is a
    HUB (the database module), so its neighbourhood is almost the whole
    graph. Measured: 18 nodes out of 22, that is, the same tangle one was
    trying to avoid.

    A PAGE, for its part, has few neighbours, and its neighbourhood
    answers a real question — "what does this screen need". We take the
    one for "/", failing that the first declared route.
    """
    for path, feature in graph.routes:
        if path == "/":
            return feature
    return graph.routes[0][1] if graph.routes else ""


class MapUI(ClientState, persist="memory"):
    # Sentinel: starts with a space so the FIRST fold lines up with the
    # ``.includes(' key ')`` test. Default = everything unfolded.
    closed: str = field(default=' ')      # folded layouts (delimited, space-padded)
    sel: str = field(default='')          # selected feature → detail on the right
    lit: list[str] = field(default_factory=list)   # consumed DIRECTLY (hover)
    via: list[str] = field(default_factory=list)   # consumed TRANSITIVELY (dimmed)
    panel: str = field(default='')        # "" | "routes" — le volet table des routes


# ───────────────────────────────────────────────────────────────────────────
# Reading the graph — pure, with no rendering
# ───────────────────────────────────────────────────────────────────────────


def pkg_prefix(modules: list[str]) -> list[str]:
    """Common package prefix (to shorten the displayed paths)."""
    seqs = [m.split(".") for m in modules if m]
    out: list[str] = []
    for tier in zip(*seqs):
        if len(set(tier)) == 1:
            out.append(tier[0])
        else:
            break
    return out


def short_path(module: str, prefix: list[str]) -> str:
    """``examples.mad.features.geo`` → ``features/geo.py`` (prefix dropped)."""
    parts = module.split(".")
    rel = parts[len(prefix):] if parts[: len(prefix)] == prefix else parts
    return "/".join(rel or parts[-1:]) + ".py"


def consumption(node, by: dict) -> tuple[list[str], list[str]]:
    """(direct, transitive) — what ``node`` consumes, for the hover."""
    direct = [*node.uses, *node.reads]
    seen, stack = set(direct), list(direct)
    while stack:
        d = by.get(stack.pop())
        if d is None:
            continue
        for x in (*d.uses, *d.reads):
            if x not in seen:
                seen.add(x)
                stack.append(x)
    return direct, [x for x in seen if x not in direct]


def consumer_chains(name: str, consumers: dict, by: dict) -> list[str]:
    """The consumption chains, traced back to the anchors/entries — the
    explanation of the placement ("geo ← planning_engine ← planning")."""
    paths: list[list[str]] = []

    def walk(n: str, path: list[str]) -> None:
        entries = consumers.get(n, [])
        if not entries and path:
            paths.append(path)
            return
        for c in entries:
            node = by.get(c)
            if node is None or c in path:
                continue
            if node.renderable or node.kind == "job":
                paths.append(path + [c])
            else:
                walk(c, path + [c])

    walk(name, [])
    # Merges the paths sharing the same intermediaries:
    # {(planning_engine,): [planning, tournees, nightly_replan]}
    groups: dict[tuple, list[str]] = {}
    for p in paths:
        groups.setdefault(tuple(p[:-1]), []).append(p[-1])
    lines = []
    for mids, ends in groups.items():
        tag = lambda e: e + (" (job)" if by.get(e) and by[e].kind == "job" else "")
        prefix = "".join(f"← {m} " for m in mids)
        lines.append(prefix + "← " + " · ".join(tag(e) for e in sorted(set(ends))))
    return lines[:8]


def layout_of(nodes: list, by: dict) -> dict[str, list[tuple]]:
    """Option A: every base feature → the LAYOUT that carries it.
    ``optimal_parent`` layout → that layout; page → goes up to the page's
    layout ("private to <page>" badge); "" → global group (root)."""
    out: dict[str, list[tuple]] = {}
    for n in nodes:
        if n.renderable or n.kind == "job":
            continue
        target, badge = n.optimal_parent, None
        anchor = by.get(target)
        if anchor is not None and anchor.kind not in _BRANCH_KINDS:
            badge = f"private to {target}"
            target = anchor.render_parent
        out.setdefault(target, []).append((n, badge))
    for group in out.values():
        group.sort(key=lambda t: (_KIND_SORT.get(t[0].kind, 5), t[0].name))
    return out


def reach_label(node, by: dict) -> str:
    """The detail's placement badge — where the graph says this lives."""
    if node.render_parent:
        return f"rendered in {node.render_parent}"
    if node.kind == "job":
        return "entry point (job)"
    if node.renderable:
        return ""
    tgt = by.get(node.optimal_parent)
    if tgt is None:
        return "global base"
    if tgt.kind in _BRANCH_KINDS:
        return ("base common to the whole app" if not tgt.render_parent
                else f"base of {node.optimal_parent}")
    return f"private to {node.optimal_parent}"


# ───────────────────────────────────────────────────────────────────────────
# The rows — ONE grammar: click = detail, chevron = separate target
# ───────────────────────────────────────────────────────────────────────────


def row_state(name: str) -> dict:
    """Reactive class: a background if selected; a strong ring if consumed
    directly by the hovered feature, dimmed if transitive.

    ``bz-class`` and NOT ``bz-attr:class`` — although that is what the
    base layer's error message advises when it refuses a ``:class``. Here
    it would be wrong: the button already carries a static ``classes=``
    (``flex-1 min-w-0 justify-start …``), and ``bz-attr:class`` REPLACES
    the whole string, whereas ``bz-class`` MERGES its tokens on top. The
    first would have rendered the page — by erasing every rank's layout.
    """
    sel = f"{_SEL} === '{name}'"
    lit = f"({_LIT} || []).includes('{name}')"
    via = f"({_VIA} || []).includes('{name}')"
    return {
        "bz-class": (
            f"({sel} ? 'bg-primary/15 ' : '') + "
            f"({lit} ? 'ring-1 ring-warning/70 bg-warning/5' : "
            f"({via} ? 'ring-1 ring-warning/25' : ''))"
        )
    }


def row(node, m: MapUI, hover: tuple[list[str], list[str]], *,
         weight: str = "normal", chevron_key: str = "", right: str = "") -> None:
    """A row. Chevron (layouts) = separate button; the row itself ALWAYS
    selects. Optional badge on the right (outside the clickable area)."""
    direct, via = hover
    with ui.hstack(gap="none", align="center", classes="w-full"):
        if chevron_key:
            shut = f"{_CLOSED}.includes(' {chevron_key} ')"
            toggle = (f"{_CLOSED} = {shut} ? "
                      f"{_CLOSED}.replace(' {chevron_key} ', ' ') : "
                      f"{_CLOSED} + '{chevron_key} '")
            # Unfolded/folded state with NO ambiguity: two glyphs
            # toggled by ``visible`` (bz-show) — open = chevron down (v),
            # folded = chevron right (>). Robust: both are in the DOM, no
            # dynamic class to compile (works in dev AND in production),
            # unlike a CSS rotation (``rotate-90`` may not be in the
            # safelist).
            with ui.hstack(gap="none", align="center") as chev:
                ui.icon("chevron-down", color="muted", size="sm",
                        visible=m.closed.contains(f" {chevron_key} ").not_())
                ui.icon("chevron-right", color="muted", size="sm",
                        visible=m.closed.contains(f" {chevron_key} "))
            ui.button(chev, variant="ghost", size="xs", on_click=toggle,
                      classes="h-7 w-7 p-0 min-w-0 shrink-0 justify-center")
        else:
            # inline-block : un <span> inline ignore w-7 (bug d'alignement).
            ui.text("", classes="inline-block w-7 shrink-0")
        ui.button(
            node.name,
            variant="ghost", size="sm", color="text",
            icon_left=ui.icon(_KIND_ICON.get(node.kind, "box"),
                              color=_KIND_COLOR.get(node.kind, "muted"),
                              size="sm"),
            on_click=m.sel.set(node.name),
            on_mouseenter=m.lit.set(direct) + "; " + m.via.set(via),
            on_mouseleave=m.lit.set([]) + "; " + m.via.set([]),
            classes=f"flex-1 min-w-0 justify-start font-mono {_WEIGHT_CLASS[weight]} "
                    "transition-shadow overflow-hidden",
            **row_state(node.name),
        )
        if right:
            ui.badge(right, color="warning", variant="outline",
                     classes="shrink-0 ml-1")


def eyebrow(label: str) -> None:
    ui.text(label, size="xs", color="muted",
            classes="uppercase tracking-wider px-2 pt-2 pb-0.5 opacity-60")


def labelled_group(label: str, rows, m: MapUI, hovers) -> None:
    """A labelled subgroup (base / errors / entries): a plain eyebrow +
    its rows, at the same level as the sibling pages — NO border of its
    own (a single line style throughout the tree)."""
    eyebrow(label)
    for node, badge in rows:
        row(node, m, hovers[node.name], right=badge or "")


def kids(nodes: list, parent: str) -> tuple[list, list]:
    """``parent``'s render children, split (nav, errors). Branches first,
    then pages, stable sort by kind then name."""
    ren = [n for n in nodes if n.renderable and n.render_parent == parent]
    nav = sorted((n for n in ren if n.kind != "error"),
                 key=lambda n: (0 if n.kind in _BRANCH_KINDS else 1,
                                _KIND_SORT.get(n.kind, 5), n.name))
    errs = sorted((n for n in ren if n.kind == "error"), key=lambda n: n.name)
    return nav, errs


def branch(node, nodes, m, hovers, socle_by_layout, by) -> None:
    """A layout: its row (separate chevron), then — foldable — its render
    children, its base group, its errors group."""
    row(node, m, hovers[node.name], weight="medium", chevron_key=node.name)
    nav, errs = kids(nodes, node.name)
    socle = socle_by_layout.get(node.name, [])
    with ui.vstack(gap="none", classes="pl-3 ml-3 border-l border-muted/20",
                   visible=m.closed.contains(f" {node.name} ").not_()):
        for child in nav:
            if child.kind in _BRANCH_KINDS:
                branch(child, nodes, m, hovers, socle_by_layout, by)
            else:
                row(child, m, hovers[child.name])
        if socle:
            # At the ROOT layout, "branche shell" would read badly: this
            # base is common to the whole app (db, the data consumed
            # everywhere…).
            label = ("base · common to the whole app"
                     if not node.render_parent
                     else f"base · {node.name} branch")
            labelled_group(label, socle, m, hovers)
        if errs:
            labelled_group("erreurs", [(e, "") for e in errs], m, hovers)


# ───────────────────────────────────────────────────────────────────────────
# The detail — contract + placement + files + chains
# ───────────────────────────────────────────────────────────────────────────


def detail(node, m: MapUI, by, consumers, prefix) -> None:
    with ui.card(visible=(m.sel == node.name)):
        with ui.vstack(gap="sm"):
            with ui.hstack(align="center", gap="sm", wrap=True):
                ui.icon(_KIND_ICON.get(node.kind, "box"),
                        color=_KIND_COLOR.get(node.kind, "muted"), size="sm")
                ui.text(node.name, weight="bold", classes="font-mono")
                ui.badge(node.kind, color=_KIND_COLOR.get(node.kind, "muted"),
                         variant="soft")
                reach = reach_label(node, by)
                if reach:
                    ui.badge(f"↳ {reach}",
                             color="info" if node.renderable else "warning",
                             variant="outline")
            if node.provides:
                ui.text("provides", color="muted", size="xs",
                        classes="font-mono")
                for p in node.provides:
                    with ui.hstack(gap="sm", align="center", wrap=True):
                        ui.badge(f"{p.label} · {p.kind}"
                                 + (f" {p.detail}" if p.detail else ""),
                                 color="muted", variant="outline")
                        if p.module:
                            ui.text(short_path(p.module, prefix),
                                    color="muted", size="xs",
                                    classes="font-mono opacity-70")
            for label, deps, color in (("uses", node.uses, "warning"),
                                       ("reads", node.reads, "secondary")):
                if deps:
                    with ui.hstack(gap="xs", align="center", wrap=True):
                        ui.text(label, color="muted", size="xs",
                                classes="font-mono")
                        for d in deps:
                            ui.badge(d, color=color, variant="soft")
            chains = (consumer_chains(node.name, consumers, by)
                      if not node.renderable else [])
            if chains:
                ui.text("consumed by", color="muted", size="xs",
                        classes="font-mono")
                for line in chains:
                    ui.text(line, size="sm",
                            classes="font-mono text-text/80")
            if not node.uses and not node.reads and not chains:
                ui.text("No dependency — a leaf.", color="muted",
                        size="sm")


# ───────────────────────────────────────────────────────────────────────────
# La page
# ───────────────────────────────────────────────────────────────────────────


def render_app_map(graph: AppGraph | None = None, *,
                   title: str = "Carte de l'app") -> None:
    """Draw the map. With no argument, introspects the CURRENT app
    (``def app_map_page(): render_app_map()``). With an explicit ``graph``,
    draws THAT graph — useful to demonstrate the component on an example
    (the playground has no Features to introspect)."""
    introspecting = graph is None
    ctx = maybe_current_context()
    if introspecting:
        features = ctx.app.features if ctx is not None else ()
        graph = describe_app(features)
    nodes = list(graph.nodes)
    by = {n.name: n for n in nodes}

    consumers: dict[str, list[str]] = {}
    for a, b, _kind in graph.edges:
        consumers.setdefault(b, []).append(a)
    hovers = {n.name: consumption(n, by) for n in nodes}
    socle_by_layout = layout_of(nodes, by)
    prefix = pkg_prefix([n.module for n in nodes])
    entries = sorted((n for n in nodes if n.kind == "job"),
                     key=lambda n: n.name)
    roots_nav, roots_err = kids(nodes, "")
    m = MapUI()

    with ui.vstack(gap="lg", classes="w-full max-w-5xl mx-auto"):
        ui.heading(title, level=1, size="2xl")
        ui.text(
            "The architecture the graph implies — not the repo's "
            "folders. The tree = the rendering (a layout contains its "
            "pages). The dashed groups = the base, placed under the layout "
            "as close as possible to its consumers. Click a line → its "
            "contract, its files and its chain of consumption. Hover "
            "→ what it consumes lights up (strong = direct, dimmed = "
            "transitive). Chevron = fold.",
            color="muted",
        )
        with ui.hstack(gap="sm", wrap=True, align="center"):
            ui.badge(f"{len(nodes)} features", color="primary", variant="soft")
            ui.button(
                f"{len(graph.routes)} routes", variant="soft", size="xs",
                color="info", icon_left="route",
                on_click=f"{_PANEL} = {_PANEL} === 'routes' ? '' : 'routes'",
            )
            ui.button(
                f"{len(graph.edges)} dependencies", variant="soft", size="xs",
                color="warning", icon_left="workflow",
                on_click=f"{_PANEL} = {_PANEL} === 'graph' ? '' : 'graph'",
            )
        with ui.card(visible=(m.panel == "routes")):
            with ui.vstack(gap="xs"):
                eyebrow("routes → feature")
                for route, feat in graph.routes:
                    with ui.hstack(gap="sm", align="center"):
                        ui.text(route, size="sm", color="info",
                                classes="font-mono min-w-[10rem]")
                        ui.text(f"→ {feat}", size="sm", classes="font-mono")

        # The graph's panel. Absent when an EXPLICIT graph is passed:
        # the zone re-introspects the current app, so it would show
        # something other than what it was asked to draw.
        if introspecting:
            with ui.card(visible=(m.panel == "graph")):
                with ui.vstack(gap="sm"):
                    eyebrow("dependencies · the other axis")
                    dependency_graph()

        with ui.hstack(gap="lg", align="start", classes="w-full max-md:flex-col"):
            with ui.card(classes="md:w-1/2 w-full"):
                with ui.vstack(gap="none"):
                    eyebrow("architecture · derived from the graph")
                    for root in roots_nav:
                        if root.kind in _BRANCH_KINDS:
                            branch(root, nodes, m, hovers, socle_by_layout, by)
                        else:
                            row(root, m, hovers[root.name])
                    global_socle = socle_by_layout.get("", [])
                    if global_socle:
                        labelled_group("base · global", global_socle, m, hovers)
                    if roots_err:
                        labelled_group("errors", [(e, "") for e in roots_err], m,
                               hovers)
                    if entries:
                        labelled_group("entry points · jobs", [(j, "") for j in entries],
                               m, hovers)
                    # Lint L1: the routables mounted OUTSIDE any Feature
                    # — the skeleton does not lie by omission, it shows
                    # them.
                    undeclared = tuple(
                        getattr(ctx.app, "undeclared_pages", ())
                        if (introspecting and ctx is not None) else ())
                    if undeclared:
                        eyebrow("⚠ undeclared · outside the manifest")
                        for label, route in undeclared:
                            with ui.hstack(gap="sm", align="center",
                                           classes="px-2 py-1"):
                                ui.icon("alert-triangle", color="warning",
                                        size="sm")
                                ui.text(f"{label}  {route}", size="sm",
                                        color="warning", classes="font-mono")
            with ui.vstack(gap="sm", classes="md:w-1/2 w-full"):
                ui.text("← Click a feature for its contract, its files "
                        "and who consumes it.", color="muted", size="sm",
                        visible=(m.sel == ""))
                for node in nodes:
                    detail(node, m, by, consumers, prefix)
