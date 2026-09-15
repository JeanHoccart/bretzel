"""Renderer partagé de la carte d'app — v4, sur le modèle acté
(``.claude/bretzel/app-map-model.md``). Réutilisé par flat, mad, …

Trois rôles, chacun SA représentation :

- **ANCRE** (shell/layout/page/error — se rend) : l'arbre de rendu pur.
  Une page n'est jamais un dossier ; les erreurs vivent dans un micro-groupe
  « erreurs » sous leur layout.
- **SOCLE** (data/state/logic/facade/infra — se consomme) : groupes accrochés
  aux **layouts uniquement** (Option A actée). Le privé-à-une-page remonte au
  layout parent avec un badge « privé à <page> ».
- **ENTRÉE** (job — se déclenche) : groupe « entrées » à la racine.

Visuel volontairement générique : UN seul style de ligne guide (la
contenance) ; la couleur vit dans les icônes ; un groupe = un simple
titre (eyebrow), pas de bordure propre.

Grammaire de clic : clic ligne = TOUJOURS la sélection/détail ; le chevron
est une cible séparée (layouts seulement). Survol : ce que la feature
consomme s'éclaire — direct en fort, transitif en atténué. Le détail montre
la chaîne de consommation (« geo ← planning_engine ← planning · tournées »)
et le fichier de chaque symbole. Le badge routes est cliquable → la table.
"""

from __future__ import annotations

from bretzel import refreshable, ui
from bretzel.render import maybe_current_context
from bretzel.server import AppGraph, describe_app
from bretzel.state import ClientState, PageState, field

# La couleur vit dans l'icône (le nom reste neutre). Un glyphe par rang.
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

#: Le poids du rang, en classes ENTIÈRES. Surtout pas `f"font-{weight}"` :
#: une classe assemblée n'existe que sous le compilateur de dev, qui scanne
#: le DOM déjà résolu ; en prod le binaire Tailwind ne balaie que les
#: sources et ne verra jamais `font-medium`. Le HTML est identique des deux
#: côtés, donc rien ne le dirait.
_WEIGHT_CLASS = {"normal": "font-normal", "medium": "font-medium"}

_CLOSED = "$bz.state.MapUI.default.closed"
_LIT = "$bz.state.MapUI.default.lit"
_VIA = "$bz.state.MapUI.default.via"
_SEL = "$bz.state.MapUI.default.sel"
_PANEL = "$bz.state.MapUI.default.panel"


#: L'icône par kind, réutilisée par le graphe de dépendances.
_KIND_OF_NODE = _KIND_ICON


class MapFocus(PageState):
    """Le nœud au centre du graphe de dépendances.

    SERVEUR, contrairement à `MapUI.sel` qui pilote l'arbre : changer le
    centre change les nœuds DESSINÉS, donc le placement — et le
    placement se calcule côté serveur. Les deux sélections restent
    séparées exprès, parce qu'elles répondent à deux questions : l'arbre
    dit « où ça vit », le graphe « qui touche à ça ».
    """

    key: str = field(default="")


def focus_node(key: str) -> None:
    # Recliquer sur le centre rend la vue d'ensemble : sans ça on
    # s'enferme dans un voisinage sans porte de sortie.
    state = MapFocus()
    state.key = "" if state.key == key else key


@refreshable(deps=[MapFocus])
def dependency_graph() -> None:
    """L'axe DÉPENDANCE de la carte — celui que l'arbre ne montre pas.

    `AppGraph` EST un graphe : `nodes` plus `edges` en
    ``(source, cible, "uses"|"reads")``. L'arbre en projette la
    CONTENANCE et n'affiche les arêtes qu'en surbrillance au survol —
    donc rien du tout sur une machine sans pointeur fin, et rien
    d'imprimable nulle part. Ici elles sont dessinées.

    La zone ne prend aucun paramètre (une zone n'en prend jamais), donc
    elle réintrospecte l'app courante. C'est aussi pourquoi le panneau
    ne s'affiche pas quand `render_app_map(graph=…)` reçoit un graphe
    explicite : elle montrerait l'app qui l'héberge, pas celui-là.
    """
    ctx = maybe_current_context()
    graph = describe_app(ctx.app.features if ctx is not None else ())
    known = {n.name for n in graph.nodes}
    # Le panneau ne s'OUVRE jamais sur le graphe entier. Mesuré sur
    # Mesuré sur une app depuis retirée : 22 nœuds et 61 arêtes,
    # illisible — c'est
    # exactement le reproche qu'on fait à la carte, et l'afficher par
    # défaut le déplacerait sans le régler.
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
        empty_text="Aucune dépendance déclarée.",
    )
    ui.text(
        f"Centré sur « {focus} ». Clique un nœud pour t'y déplacer — "
        f"trait plein = uses, tireté = reads."
        if focus else "Aucune dépendance déclarée.",
        color="muted", size="sm",
    )


def entry_feature(graph: AppGraph) -> str:
    """La feature qui sert la page d'accueil — le centre par défaut.

    ⚠️ Surtout PAS le nœud le plus connecté, qui est l'intuition
    naturelle et le pire choix possible : le plus connecté est un HUB
    (le module de base de données), donc son voisinage est presque tout le
    graphe. Mesuré : 18 nœuds sur 22, soit le même enchevêtrement qu'on
    cherchait à éviter.

    Une PAGE, elle, a peu de voisins, et son voisinage répond à une
    vraie question — « de quoi cet écran a-t-il besoin ». On prend celle
    de « / », sinon la première route déclarée.
    """
    for path, feature in graph.routes:
        if path == "/":
            return feature
    return graph.routes[0][1] if graph.routes else ""


class MapUI(ClientState, persist="memory"):
    # Sentinelle : commence par un espace pour que le PREMIER repli s'aligne
    # sur le test ``.includes(' key ')``. Défaut = tout déplié.
    closed: str = field(default=' ')      # layouts repliés (délimité + bordé par des espaces)
    sel: str = field(default='')          # feature sélectionnée → détail à droite
    lit: list[str] = field(default_factory=list)   # consommé DIRECT (survol)
    via: list[str] = field(default_factory=list)   # consommé TRANSITIF (atténué)
    panel: str = field(default='')        # "" | "routes" — le volet table des routes


# ───────────────────────────────────────────────────────────────────────────
# Lecture du graphe — pur, sans rendu
# ───────────────────────────────────────────────────────────────────────────


def pkg_prefix(modules: list[str]) -> list[str]:
    """Préfixe de package commun (pour raccourcir les chemins affichés)."""
    seqs = [m.split(".") for m in modules if m]
    out: list[str] = []
    for tier in zip(*seqs):
        if len(set(tier)) == 1:
            out.append(tier[0])
        else:
            break
    return out


def short_path(module: str, prefix: list[str]) -> str:
    """``examples.mad.features.geo`` → ``features/geo.py`` (préfixe retiré)."""
    parts = module.split(".")
    rel = parts[len(prefix):] if parts[: len(prefix)] == prefix else parts
    return "/".join(rel or parts[-1:]) + ".py"


def consumption(node, by: dict) -> tuple[list[str], list[str]]:
    """(direct, transitif) — ce que ``node`` consomme, pour le survol."""
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
    """Les chaînes de consommation, remontées jusqu'aux ancres/entrées —
    l'explication du placement (« geo ← planning_engine ← planning »)."""
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
    # Fusionne les chemins partageant les mêmes intermédiaires :
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
    """Option A : chaque feature socle → le LAYOUT qui la porte.
    ``optimal_parent`` layout → ce layout ; page → remonte au layout de la
    page (badge « privé à <page> ») ; "" → groupe global (racine)."""
    out: dict[str, list[tuple]] = {}
    for n in nodes:
        if n.renderable or n.kind == "job":
            continue
        target, badge = n.optimal_parent, None
        anchor = by.get(target)
        if anchor is not None and anchor.kind not in _BRANCH_KINDS:
            badge = f"privé à {target}"
            target = anchor.render_parent
        out.setdefault(target, []).append((n, badge))
    for group in out.values():
        group.sort(key=lambda t: (_KIND_SORT.get(t[0].kind, 5), t[0].name))
    return out


def reach_label(node, by: dict) -> str:
    """Le badge de placement du détail — où le graphe dit que ça vit."""
    if node.render_parent:
        return f"rendu dans {node.render_parent}"
    if node.kind == "job":
        return "entrée (job)"
    if node.renderable:
        return ""
    tgt = by.get(node.optimal_parent)
    if tgt is None:
        return "socle global"
    if tgt.kind in _BRANCH_KINDS:
        return ("socle commun à toute l'app" if not tgt.render_parent
                else f"socle de {node.optimal_parent}")
    return f"privé à {node.optimal_parent}"


# ───────────────────────────────────────────────────────────────────────────
# Les lignes — UNE grammaire : clic = détail, chevron = cible séparée
# ───────────────────────────────────────────────────────────────────────────


def row_state(name: str) -> dict:
    """Classe réactive : fond si sélectionné ; anneau fort si consommé en
    direct par la feature survolée, atténué si transitif.

    ``bz-class`` et NON ``bz-attr:class`` — pourtant c'est ce que conseille
    le message d'erreur du socle quand il refuse un ``:class``. Ici
    ce serait faux : le bouton porte déjà un ``classes=`` statique
    (``flex-1 min-w-0 justify-start …``), et ``bz-attr:class`` REMPLACE la
    chaîne entière, alors que ``bz-class`` FUSIONNE ses jetons par-dessus.
    Le premier aurait rendu la page — en effaçant la mise en page de
    chaque rang.
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
    """Un rang. Chevron (layouts) = bouton séparé ; le rang lui-même
    sélectionne TOUJOURS. Badge optionnel à droite (hors zone cliquable)."""
    direct, via = hover
    with ui.hstack(gap="none", align="center", classes="w-full"):
        if chevron_key:
            shut = f"{_CLOSED}.includes(' {chevron_key} ')"
            toggle = (f"{_CLOSED} = {shut} ? "
                      f"{_CLOSED}.replace(' {chevron_key} ', ' ') : "
                      f"{_CLOSED} + '{chevron_key} '")
            # État déplié/replié SANS ambiguïté : deux glyphes basculés par
            # ``visible`` (bz-show) — ouvert = chevron bas (v), replié = chevron
            # droit (>). Robuste : les deux sont dans le DOM, aucune classe
            # dynamique à compiler (marche en dev ET en prod), contrairement à
            # une rotation CSS (``rotate-90`` peut ne pas être dans le safelist).
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
    """Un sous-groupe étiqueté (socle / erreurs / entrées) : un simple
    eyebrow + ses rangs, au même niveau que les pages sœurs — AUCUNE
    bordure propre (un seul style de ligne dans tout l'arbre)."""
    eyebrow(label)
    for node, badge in rows:
        row(node, m, hovers[node.name], right=badge or "")


def kids(nodes: list, parent: str) -> tuple[list, list]:
    """Enfants de rendu de ``parent``, séparés (nav, erreurs). Branches
    d'abord, puis pages, tri stable par kind puis nom."""
    ren = [n for n in nodes if n.renderable and n.render_parent == parent]
    nav = sorted((n for n in ren if n.kind != "error"),
                 key=lambda n: (0 if n.kind in _BRANCH_KINDS else 1,
                                _KIND_SORT.get(n.kind, 5), n.name))
    errs = sorted((n for n in ren if n.kind == "error"), key=lambda n: n.name)
    return nav, errs


def branch(node, nodes, m, hovers, socle_by_layout, by) -> None:
    """Un layout : son rang (chevron séparé), puis — repliable — ses enfants
    de rendu, son groupe socle, son groupe erreurs."""
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
            # Au layout RACINE, « branche shell » lirait mal : ce socle est
            # commun à toute l'app (db, les data partout consommées…).
            label = ("socle · commun à toute l'app" if not node.render_parent
                     else f"socle · branche {node.name}")
            labelled_group(label, socle, m, hovers)
        if errs:
            labelled_group("erreurs", [(e, "") for e in errs], m, hovers)


# ───────────────────────────────────────────────────────────────────────────
# Le détail — contrat + placement + fichiers + chaînes
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
                ui.text("consommé par", color="muted", size="xs",
                        classes="font-mono")
                for line in chains:
                    ui.text(line, size="sm",
                            classes="font-mono text-text/80")
            if not node.uses and not node.reads and not chains:
                ui.text("Aucune dépendance — une feuille.", color="muted",
                        size="sm")


# ───────────────────────────────────────────────────────────────────────────
# La page
# ───────────────────────────────────────────────────────────────────────────


def render_app_map(graph: AppGraph | None = None, *,
                   title: str = "Carte de l'app") -> None:
    """Dessine la carte. Sans argument, introspecte l'app COURANTE
    (``def app_map_page(): render_app_map()``). Avec un ``graph`` explicite,
    dessine CE graphe — utile pour démontrer le composant sur un exemple
    (le playground n'a pas de Features à introspecter)."""
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
            "L'architecture que le graphe implique — pas les dossiers du repo. "
            "L'arbre = le rendu (un layout contient ses pages). Les groupes "
            "tiretés = le socle, posé sous le layout au plus près de ses "
            "consommateurs. Clic sur une ligne → son contrat, ses fichiers et "
            "sa chaîne de consommation. Survol → ce qu'elle consomme s'éclaire "
            "(fort = direct, atténué = transitif). Chevron = replier.",
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
                f"{len(graph.edges)} dépendances", variant="soft", size="xs",
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

        # Le panneau du graphe. Absent quand un graphe EXPLICITE est
        # passé : la zone réintrospecte l'app courante, donc elle
        # montrerait autre chose que ce qu'on lui a demandé de dessiner.
        if introspecting:
            with ui.card(visible=(m.panel == "graph")):
                with ui.vstack(gap="sm"):
                    eyebrow("dépendances · l'autre axe")
                    dependency_graph()

        with ui.hstack(gap="lg", align="start", classes="w-full max-md:flex-col"):
            with ui.card(classes="md:w-1/2 w-full"):
                with ui.vstack(gap="none"):
                    eyebrow("architecture · dérivée du graphe")
                    for root in roots_nav:
                        if root.kind in _BRANCH_KINDS:
                            branch(root, nodes, m, hovers, socle_by_layout, by)
                        else:
                            row(root, m, hovers[root.name])
                    global_socle = socle_by_layout.get("", [])
                    if global_socle:
                        labelled_group("socle · global", global_socle, m, hovers)
                    if roots_err:
                        labelled_group("erreurs", [(e, "") for e in roots_err], m,
                               hovers)
                    if entries:
                        labelled_group("entrées · jobs", [(j, "") for j in entries],
                               m, hovers)
                    # Lint L1 : les routables montés HORS de toute Feature —
                    # le squelette ne ment pas par omission, il les affiche.
                    undeclared = tuple(
                        getattr(ctx.app, "undeclared_pages", ())
                        if (introspecting and ctx is not None) else ())
                    if undeclared:
                        eyebrow("⚠ non déclaré · hors manifeste")
                        for label, route in undeclared:
                            with ui.hstack(gap="sm", align="center",
                                           classes="px-2 py-1"):
                                ui.icon("alert-triangle", color="warning",
                                        size="sm")
                                ui.text(f"{label}  {route}", size="sm",
                                        color="warning", classes="font-mono")
            with ui.vstack(gap="sm", classes="md:w-1/2 w-full"):
                ui.text("← Clique une feature pour son contrat, ses fichiers "
                        "et qui la consomme.", color="muted", size="sm",
                        visible=(m.sel == ""))
                for node in nodes:
                    detail(node, m, by, consumers, prefix)
