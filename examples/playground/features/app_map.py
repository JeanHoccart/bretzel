"""App map (tree) — banc de démo du composant « squelette vivant ».

Le playground n'a pas de contrats ``Feature`` à introspecter, alors on nourrit
``render_app_map`` avec un graphe-EXEMPLE construit à la main (une petite app
MAD). De quoi exercer l'arbre : replier/déplier un layout (chevron ▼ / ▶ sans
ambiguïté), survoler une ligne pour éclairer ses dépendances, cliquer pour le
contrat + le fichier + la chaîne de consommation.
"""

from __future__ import annotations

from bretzel import ui
from bretzel.server import AppGraph, FeatureNode, ProvideInfo

from examples.shared.app_map_view import render_app_map

PATH = "/app-map"


def feature_node(name: str, kind: str, **kw) -> FeatureNode:
    return FeatureNode(name=name, kind=kind, **kw)


# Un petit graphe réaliste : 2 layouts (repliables), des pages, du socle à
# deux niveaux, un « privé à une page », un job, une erreur.
_NODES = (
    feature_node("shell", "shell", renderable=True,
       provides=(ProvideInfo("shell", "layout", "", "app.shell"),)),
    feature_node("account_nav", "layout", renderable=True, render_parent="shell",
       provides=(ProvideInfo("account_nav", "layout", "", "app.account.nav"),)),
    feature_node("dashboard", "page", renderable=True, render_parent="shell",
       reads=("patients_data", "session"),
       provides=(ProvideInfo("dashboard_page", "page", "/", "app.dashboard"),)),
    feature_node("patients", "page", renderable=True, render_parent="shell",
       uses=("patients_data",),
       provides=(ProvideInfo("patients_page", "page", "/patients",
                             "app.patients"),)),
    feature_node("profile", "page", renderable=True, render_parent="account_nav",
       uses=("account_data",),
       provides=(ProvideInfo("profile_page", "page", "/account",
                             "app.account.profile"),)),
    feature_node("security", "page", renderable=True, render_parent="account_nav",
       reads=("account_data",),
       provides=(ProvideInfo("security_page", "page", "/account/security",
                             "app.account.security"),)),
    feature_node("errors", "error", renderable=True, render_parent="shell",
       provides=(ProvideInfo("not_found", "error", "HTTP 404", "app.errors"),)),
    feature_node("db", "infra", optimal_parent="shell",
       provides=(ProvideInfo("query", "function", "", "app.core.db"),)),
    feature_node("patients_data", "data", optimal_parent="shell", uses=("db",),
       provides=(ProvideInfo("PatientsStore", "state", "", "app.patients_data"),)),
    feature_node("account_data", "data", optimal_parent="account_nav", uses=("db",),
       provides=(ProvideInfo("AccountStore", "state", "", "app.account.data"),)),
    feature_node("session", "state", optimal_parent="dashboard",
       provides=(ProvideInfo("CurrentUser", "state", "", "app.session"),)),
    feature_node("nightly_sync", "job", uses=("patients_data",),
       provides=(ProvideInfo("run_sync", "function", "", "app.jobs.sync"),)),
)


def edges() -> tuple:
    out: list = []
    for n in _NODES:
        out += [(n.name, d, "uses") for d in n.uses]
        out += [(n.name, d, "reads") for d in n.reads]
    return tuple(out)


SAMPLE = AppGraph(
    nodes=_NODES,
    routes=tuple(sorted((p.detail, n.name) for n in _NODES for p in n.provides
                        if p.kind == "page" and p.detail)),
    edges=edges(),
)


def page() -> None:
    with ui.container():
        with ui.vstack(gap="md"):
            ui.heading("App map · le composant tree", level=1)
            ui.text(
                "Le squelette vivant : l'arbre d'architecture dérivé du graphe. "
                "Le playground n'a pas de Features à introspecter, alors on "
                "démontre le composant sur un graphe-exemple (une petite app "
                "MAD). Replie un layout (le chevron passe de ▼ à ▶ sans "
                "ambiguïté), survole une ligne pour éclairer ses dépendances, "
                "clique pour le contrat + le fichier.",
                color="muted",
            )
            render_app_map(SAMPLE, title="Exemple : une app MAD")
