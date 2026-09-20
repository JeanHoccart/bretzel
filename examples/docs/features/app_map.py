"""REFERENCE — The app map (the living skeleton).

``describe_app()`` reads the ``Feature()`` contracts → the app's graph,
live. This page runs it on a demo app (the design doc's mini SaaS) and
renders the result: the features by ``kind``, their classified
``provides``, the ``uses`` / ``reads`` dependencies, the routes, and the
JSON export — the map an AI can read. The same thing runs on any app
through ``describe_app(app.features)``.
"""

from __future__ import annotations

import json

from bretzel import Feature, page, ui
from bretzel.components import GraphEdge, GraphNode
from bretzel.server import describe_app

from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr

PATH = "/app-map"


def page_stub(name: str, path: str):
    """A page provide for the illustration — never mounted.

    ``@page`` MARKS the function without registering it (it is the
    charter's anti-rule 4: nothing registers at import, ``create_app``
    alone mounts); the demo set never being included, the route does not
    exist.

    This function forged the marking by hand until 2026-08-23 — a
    ``SimpleNamespace`` carrying ``_bz_page``, the private attribute
    ``describe_app`` reads. It worked, and it was wrong twice over: the
    docs showed a form no app must copy, and the day ``PageMeta``'s shape
    moves, the forgery breaks in silence. Using the real decorator gives
    the real marking.
    """
    stub = fn(name)
    return page(path)(stub)


def fn(name: str):
    def f() -> None: ...
    f.__name__ = name
    return f


# The demo feature set — the design doc's project-management mini SaaS.
_DEMO: list[Feature] = [
    Feature(name="shell", kind="shell"),
    Feature(name="errors", kind="error"),
    Feature(name="db", kind="infra"),
    Feature(name="money", kind="logic", provides=[fn("format_price")]),
    Feature(name="realtime", kind="infra", provides=[fn("broadcast")]),
    Feature(name="users", kind="data", provides=[fn("UserRepo")], uses=["db"]),
    Feature(name="auth", kind="logic", provides=[fn("login_required")], uses=["users"]),
    Feature(name="project_data", kind="data", provides=[fn("ProjectRepo")], uses=["db"]),
    Feature(name="tasks", kind="data", provides=[fn("TaskRepo")], uses=["db", "project_data"]),
    Feature(name="dashboard", kind="page",
            provides=[page_stub("dashboard_page", "/")],
            uses=["project_data", "users", "money"]),
    Feature(name="settings", kind="page",
            provides=[page_stub("settings_page", "/settings")],
            uses=["users", "auth"]),
    Feature(name="board", kind="page",
            provides=[page_stub("board_page", "/p/{id}")],
            uses=["project_data", "tasks", "realtime"]),
    Feature(name="stats", kind="page",
            provides=[page_stub("stats_page", "/p/{id}/stats")],
            uses=["project_data", "tasks", "money"]),
    Feature(name="reporting", kind="data", provides=[fn("global_stats")],
            reads=["project_data", "users"]),
]

_KIND_COLOR = {
    "page": "primary", "data": "warning", "state": "info", "logic": "muted",
    "infra": "muted", "shell": "info", "layout": "info", "error": "error",
    "facade": "secondary", "job": "muted",
}
_KIND_ORDER = ["shell", "layout", "page", "data", "state", "logic",
               "infra", "facade", "job", "error"]


def node_card(node) -> None:
    with ui.card():
        with ui.vstack(gap="xs"):
            with ui.hstack(align="center", gap="sm", wrap=True):
                ui.text(node.name, weight="bold", classes="font-mono")
                ui.badge(node.kind, color=_KIND_COLOR.get(node.kind, "muted"),
                         variant="soft")
            if node.provides:
                with ui.hstack(gap="xs", align="center", wrap=True):
                    ui.text("provides", color="muted", size="xs",
                            classes="font-mono")
                    for p in node.provides:
                        ui.badge(f"{p.label} · {p.kind}"
                                 + (f" {p.detail}" if p.detail else ""),
                                 color="muted", variant="outline")
            if node.uses:
                with ui.hstack(gap="xs", align="center", wrap=True):
                    ui.text("uses", color="muted", size="xs", classes="font-mono")
                    for u in node.uses:
                        ui.badge(u, color="info", variant="soft")
            if node.reads:
                with ui.hstack(gap="xs", align="center", wrap=True):
                    ui.text("reads", color="muted", size="xs", classes="font-mono")
                    for r in node.reads:
                        ui.badge(r, color="secondary", variant="soft")


@page(PATH, layout=shell, title="Carte de l'app")
def app_map_page() -> None:
    graph = describe_app(_DEMO)
    by_kind: dict[str, list] = {}
    for n in graph.nodes:
        by_kind.setdefault(n.kind, []).append(n)

    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Carte de l'app", level=1, size="3xl")
            ui.text(
                tr("`describe_app()` reads an app's `Feature()` contracts → "
                   'its graph, live. This page runs it on a demo app. The '
                   'same thing runs on yours through '
                   '`describe_app(app.features)` — it cannot fall out of '
                   'step, it is the running code, read.',
                   "`describe_app()` lit les contrats `Feature()` d'une app →"
                   " son graphe, en direct. Cette page l'exécute sur une app "
                   'de démo. La même chose tourne sur la tienne via '
                   '`describe_app(app.features)` — elle ne peut pas se '
                   "désynchroniser, c'est le code qui tourne, lu."),
                color="muted", size="lg",
            )
            with ui.hstack(gap="sm", wrap=True):
                ui.badge(f"{len(graph.nodes)} features", color="primary",
                         variant="soft")
                ui.badge(f"{len(graph.routes)} routes", color="info",
                         variant="soft")
                ui.badge(f"{len(graph.edges)} dépendances", color="muted",
                         variant="soft")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The same graph, DRAWN',
                                  'Le même graphe, DESSINÉ'), level=2)
                    ui.text(
                        tr('`ui.diagram` lays a directed graph out in layers,'
                           ' rendered on the server — no drawing library, no '
                           'canvas. The same nodes and the same edges as the '
                           'tables below: it is `describe_app()` that '
                           'supplies them, not a hand entry.',
                           '`ui.diagram` place un graphe orienté en couches, '
                           'rendu côté serveur — aucune bibliothèque de '
                           'dessin, aucun canvas. Les mêmes nœuds et les '
                           "mêmes arêtes que les tableaux ci-dessous : c'est "
                           '`describe_app()` qui les fournit, pas une saisie.'),
                        color="muted", size="sm",
                    )
                    ui.diagram(
                        nodes=[
                            GraphNode(key=n.name, label=n.name,
                                      color=_KIND_COLOR.get(n.kind, "muted"),
                                      badge=n.kind, group=n.kind)
                            for n in graph.nodes
                        ],
                        edges=[
                            GraphEdge(source=src, target=dst,
                                      style="dashed" if lien == "reads"
                                      else "solid")
                            for src, dst, lien in graph.edges
                        ],
                        size="sm",
                    )
                    ui.text(
                        tr('Clicking a node LIGHTS IT UP with what touches '
                           'it, with no request — the highlighting is client '
                           'side. `value=` makes the designated node two-way,'
                           ' so a server handler can read it or set it; '
                           '`on_item_click=` triggers an action; `focus=` and'
                           " `depth=` reduce the display to a node's "
                           'neighbourhood, which is the only remedy when the '
                           'graph grows. A dashed edge is a `reads`: one '
                           'reads without depending.',
                           "Cliquer un nœud l'ÉCLAIRE avec ce qui le touche, "
                           'sans une requête — la mise en avant est client. '
                           '`value=` rend le nœud désigné à double sens, donc'
                           ' un handler serveur peut le lire ou le poser ; '
                           '`on_item_click=` déclenche une action ; `focus=` '
                           "et `depth=` réduisent l'affichage au voisinage "
                           "d'un nœud, ce qui est le seul remède quand le "
                           'graphe grossit. Une arête pointillée est un '
                           '`reads` : on lit sans dépendre.'),
                        color="muted", size="sm",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="lg"):
                    ui.heading(tr('The features, by kind',
                                  'Les features, par kind'), level=2)
                    for kind in _KIND_ORDER:
                        nodes = by_kind.get(kind)
                        if not nodes:
                            continue
                        with ui.vstack(gap="sm"):
                            with ui.hstack(align="center", gap="sm"):
                                ui.badge(kind,
                                         color=_KIND_COLOR.get(kind, "muted"),
                                         variant="solid")
                                ui.text(str(len(nodes)), color="muted",
                                        size="sm")
                            for n in nodes:
                                node_card(n)

            if graph.routes:
                with ui.card():
                    with ui.vstack(gap="sm"):
                        ui.heading(tr('Mounted routes',
                                      'Routes montées'), level=2)
                        ui.table(
                            columns=[
                                ui.column("path", label="Path"),
                                ui.column("feat", label="Feature"),
                            ],
                            rows=[{"path": p, "feat": f} for p, f in graph.routes],
                            size="sm",
                        )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The map, machine-readable',
                                  'La carte, lisible par une machine'), level=2)
                    ui.text(
                        tr('`describe_app(app.features).to_dict()` — what an '
                           "AI reads to understand the app's shape, instead "
                           'of grepping.',
                           '`describe_app(app.features).to_dict()` — ce '
                           "qu'une IA lit pour comprendre la forme de l'app, "
                           'au lieu de grepper.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        json.dumps(graph.to_dict(), indent=2, ensure_ascii=False),
                        lang="json",
                    )
