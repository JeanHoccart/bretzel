"""Rendu du banc Diagram — ses cartes et leurs panneaux.

HUIT, et c'est ``playground-pattern.md`` § 3 qui fixe lesquelles, pas
une préférence : ``Diagram`` déclare un event et une prop bindable, donc
Server events, Client events et Client playground sont OBLIGATOIRES
(§ 4, § 6, § 5). Restent omis Slots et External controls — le composant
n'a ni slot nommé ni API impérative, et le gabarit dit « no empty
cards ».

⚠️ Trois de ces cartes ont manqué à la première livraison, et la raison
était fausse de la même façon à chaque fois : je lisais des ClassVar
VIDES et j'en concluais que le composant n'avait ni event ni sélection.
Ils étaient vides parce que je ne les avais pas déclarés — pas parce
qu'il n'y avait rien à déclarer. Le gabarit se lit contre le composant
qu'on AURAIT dû écrire, pas contre celui qu'on vient d'écrire.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression

from examples.playground.features.diagram.logic import (
    clear_log,
    log_item_click,
    pick,
    playground_click_handler,
    server_changed,
)
from examples.playground.features.diagram.state import (
    COLORS,
    DIRECTIONS,
    EDGES,
    NODES,
    SIZES,
    DiagramClient,
    DiagramClientEvents,
    DiagramPlayground,
    DiagramServerEvents,
    Picked,
)
from examples.playground.features.inspection import emitted_html_block


def card_node(spec):
    """Un ``render=`` maison : le contenu d'un nœud appartient à l'auteur.

    ⚠️ Ce qu'une PROP sait faire passe par la prop. La première version
    centrait par ``classes="justify-center"`` alors que ``ui.vstack``
    émet déjà ``justify-start`` : deux ``justify-*`` sur le même élément
    se départagent par l'ordre de la FEUILLE Tailwind, pas de
    l'attribut, et le contenu restait collé en haut.

    Et un palier du pont de couleur (``bg-(--bz-bg)``) est TEINTÉ : un
    ``render=`` hérite du pont de la racine, donc ces nœuds-là
    ressortaient colorés au milieu de nœuds neutres.
    """
    with ui.vstack(gap="none", align="start", justify="center",
                   classes="h-full w-full px-3 rounded-box "
                           "border-(length:--bz-stroke) border-(--bz-border) "
                           "bg-surface") as box:
        ui.text(spec.label or spec.key, size="sm", weight="medium",
                truncate=True)
        if spec.group:
            ui.text(spec.group, size="xs", color="muted")
    return box


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: DiagramPlayground) -> dict:
    kwargs: dict = {
        "nodes": NODES,
        "edges": [] if state.empty else EDGES,
        "depth": state.depth,
        "direction": state.direction,
        "size": state.size,
        "color": state.color,
        "empty_text": state.empty_text,
    }
    if state.focus:
        kwargs["focus"] = state.focus
    if state.empty_icon:
        kwargs["empty_icon"] = state.empty_icon
    if state.empty_desc:
        kwargs["empty_description"] = state.empty_desc
    if state.render_mode == "custom":
        kwargs["render"] = card_node
    if state.click_mode == "server":
        kwargs["on_item_click"] = playground_click_handler
    if state.classes:
        kwargs["classes"] = state.classes
    if state.custom_id:
        kwargs["id"] = state.custom_id
    if state.style:
        kwargs["style"] = state.style
    attrs: dict = {}
    if state.aria_label:
        attrs["aria-label"] = state.aria_label
    attrs.update(parse_extra_attrs(state.extra_attrs))
    if attrs:
        kwargs["attrs"] = attrs
    if state.tooltip:
        kwargs["tooltip"] = state.tooltip
    if state.visible == "off":
        kwargs["visible"] = False
    return kwargs


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[Picked])
def focus_panel() -> None:
    """``focus=`` piloté par un clic serveur — le resserrement."""
    picked = Picked().key
    ui.diagram(nodes=NODES, edges=EDGES, focus=picked or None,
               on_item_click=pick)
    ui.text(
        f"Centré sur « {picked} » — reclique dessus pour tout revoir."
        if picked else
        "Clique un nœud : la vue se resserre sur son voisinage (serveur). "
        "Un simple clic éclaire déjà ses voisins, lui, sans requête.",
        color="muted", size="sm",
    )


@refreshable(deps=[DiagramPlayground])
def server_panel() -> None:
    state = DiagramPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("focus (nœud centré)"):
            ui.select(value=state.focus,
                      options=[("", "None (tout le graphe)"),
                               *[(n.key, n.key) for n in NODES]],
                      on_change=server_changed)
        with control("depth (sauts de voisinage)"):
            ui.number_input(value=state.depth, min=1, max=4,
                            on_change=server_changed)
        with control("direction"):
            ui.select(value=state.direction,
                      options=[(d, d) for d in DIRECTIONS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("render (contenu d'un nœud)"):
            ui.select(value=state.render_mode,
                      options=[("default", "Défaut (icône + label)"),
                               ("custom", "card_node (rappel)")],
                      on_change=server_changed)
        with control("on_item_click"):
            ui.select(value=state.click_mode,
                      options=[("none", "None (aucun handler)"),
                               ("server", "Server callable")],
                      on_change=server_changed)
        with control("edges (vide → l'état vide)"):
            ui.switch(checked=state.empty, label="graphe vide",
                      on_change=server_changed)
        with control("empty_text"):
            ui.input(value=state.empty_text, placeholder="No graph.",
                     on_change=server_changed)
        with control("empty_icon"):
            ui.input(value=state.empty_icon, placeholder="workflow",
                     on_change=server_changed)
        with control("empty_description"):
            ui.input(value=state.empty_desc,
                     placeholder="Aucune feature n'en consomme une autre.",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="!max-h-64",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-diagram",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Dépendances entre features",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="max-width: 480px",
                     on_change=server_changed)
        with control("extra_attrs (un par ligne, clé=valeur)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=diagram",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="L'axe dépendance",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (défaut)"),
                               ("off", "False (aucun rendu)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    ui.diagram(**kwargs)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(ui.diagram(**kwargs)),
    )


@refreshable(deps=[DiagramServerEvents])
def events_panel() -> None:
    state = DiagramServerEvents()

    ui.text(
        "``item_click`` est le seul event de Diagram. Le handler reçoit "
        "la CLÉ du nœud — c'est le nom de la feature, pas un index ni un "
        "objet à re-résoudre.",
        color="muted", size="sm",
    )
    ui.diagram(nodes=NODES, edges=EDGES, on_item_click=log_item_click)

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)", color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)
    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}", color="muted", size="sm",
                        classes="font-mono")
    else:
        ui.text("(aucun event — clique un nœud ci-dessus)",
                color="muted", size="sm")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (item_click serveur)",
        serialize_html(ui.diagram(edges=[("a", "b")],
                                  on_item_click=log_item_click)),
    )


def client_events_panel() -> None:
    """Le MÊME event, câblé sur une expression cliente.

    Pas de ``@refreshable`` : c'est tout l'intérêt. Le journal vit dans
    un ``ClientState`` et le texte se ré-évalue dans le navigateur —
    aucune requête ne part, donc il n'y a rien à re-rendre côté serveur.
    """
    events = DiagramClientEvents()

    ui.text(
        "``item_click`` câblé sur une expression cliente qui empile la "
        "clé dans un ClientState. Zéro requête.",
        color="muted", size="sm",
    )
    # ``$event.detail`` porte la clé du nœud : c'est ce que le composant
    # met dans le payload, et c'est la même valeur que reçoit un
    # handler serveur.
    clicked = ClientExpression("$event.currentTarget.dataset.bzNode")
    ui.diagram(nodes=NODES, edges=EDGES,
               on_item_click=events.log.push(clicked))

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (client-réactif — aucun rafraîchissement)",
                color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=events.log.clear())
    # ⚠️ Chaîne BRUTE, et guillemets simples côté JS.
    #
    # Une version antérieure portait un vrai saut de ligne là où il faut
    # la séquence d'échappement : le JS émis était `join("` suivi d'une
    # fin de ligne, donc un littéral non terminé. Le prix n'est pas
    # local — le runtime ENTIER cesse de démarrer, `html.bz-ready`
    # n'arrive jamais, et plus une seule directive de la page ne
    # fonctionne. Une expression cliente malformée ne dégrade pas :
    # elle éteint.
    log_text = ClientExpression(
        r"($bz.state.DiagramClientEvents.default.log || []).join('\n')"
        r" || '(aucun event — clique un nœud ci-dessus)'"
    )
    ui.text(log_text, color="muted", size="sm",
            classes="font-mono whitespace-pre")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (item_click client)",
        serialize_html(ui.diagram(edges=[("a", "b")],
                                  on_item_click=events.log.push(clicked))),
    )


def client_panel() -> None:
    """Le miroir du contrat ``BINDABLE_PROPS = ("value",)``.

    Pas de ``@refreshable`` : c'est le point. ``value`` est lié au
    magasin client, donc un clic écrit dedans et tout ce qui le lit
    suit — la ligne de texte, l'aperçu, le champ caché — sans qu'une
    seule requête parte. Le bloc HTML ci-dessous est une capture SSR :
    ce que le runtime en fait ensuite ne s'y voit pas.
    """
    pick = DiagramClient()

    ui.text(
        "``value`` = le nœud sélectionné, ⇄ two-way. Le pilote client "
        "est le clic sur un nœud ; c'est ce qui rend la prop bindable "
        "plutôt que statique (client-reactive-surface.md § La règle).",
        color="muted", size="sm",
    )
    # ⚠️ Le CONTRÔLE EXTERNE est le cœur de cette carte, pas un
    # ornement. Sans lui on ne montre qu'un sens — le composant qui
    # écrit dans le magasin — et « ⇄ two-way » n'est plus qu'une
    # affirmation. Ici le `select` est lié au MÊME champ : choisir dedans
    # déplace la sélection du diagramme, cliquer un nœud déplace le
    # `select`. Aucune requête dans un sens comme dans l'autre.
    with control("value (lié) — le select ÉCRIT, le diagramme LIT"):
        with ui.hstack(gap="sm", align="center"):
            ui.select(
                value=pick.node,
                options=[("", "(aucun)"), *[(n.key, n.key) for n in NODES]],
            )
            ui.button("Effacer", variant="ghost", size="xs",
                      on_click=pick.node.set(""))
    with ui.hstack(gap="sm", align="center"):
        ui.text("valeur courante :", color="muted", size="sm")
        ui.text(pick.node, weight="medium", size="sm")
    ui.diagram(nodes=NODES, edges=EDGES, value=pick.node)

    ui.divider()

    emitted_html_block(
        "Emitted HTML (value lié à un ClientState)",
        serialize_html(ui.diagram(edges=[("a", "b")], value=pick.node)),
    )


def page() -> None:
    with ui.container():
        with ui.vstack(gap="lg"):
            ui.heading("Diagram", level=1)
            ui.text(
                "Un graphe orienté placé en couches côté serveur : cycles "
                "cassés, couches par plus long chemin, croisements réduits "
                "à la médiane. Les arêtes vivent dans un ``<svg>``, les "
                "nœuds sont du HTML positionné — donc chaque nœud reste un "
                "composant thémé, tabulable et cliquable. Désigner un nœud "
                "éclaire ce qui le touche, sans une requête.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Basic — les arêtes suffisent", level=3)
                    ui.diagram(edges=EDGES)

                    ui.heading("nodes= + edges= (descripteurs)", level=3)
                    ui.diagram(
                        nodes=NODES,
                        edges=[ui.edge("planning", "planning_engine",
                                       label="uses"),
                               ui.edge("planning_engine", "geo",
                                       label="reads", style="dashed"),
                               ui.edge("geo", "db")],
                    )

                    ui.heading("Sizes", level=3)
                    for s in SIZES:
                        ui.text(f"size={s}", color="muted", size="xs")
                        ui.diagram(edges=[("a", "b"), ("b", "c")], size=s)

                    ui.heading("Colors", level=3)
                    for c in COLORS:
                        ui.text(f"color={c}", color="muted", size="xs")
                        ui.diagram(edges=[("a", "b"), ("b", "c")], color=c)

                    ui.heading("direction", level=3)
                    for d in DIRECTIONS:
                        ui.text(f"direction={d}", color="muted", size="xs")
                        ui.diagram(edges=EDGES, direction=d)

                    ui.heading("focus= + depth=", level=3)
                    ui.text("focus='planning_engine', depth=1 puis 2",
                            color="muted", size="xs")
                    ui.diagram(edges=EDGES, focus="planning_engine")
                    ui.diagram(edges=EDGES, focus="planning_engine", depth=2)

                    ui.heading("on_item_click — le resserrement serveur",
                               level=3)
                    focus_panel()

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)

                    ui.heading("Un cycle", level=3)
                    ui.text("L'arête qui revient est inversée pour le "
                            "PLACEMENT, jamais pour la flèche.",
                            color="muted", size="xs")
                    ui.diagram(edges=[("a", "b"), ("b", "c"), ("c", "a")])

                    ui.heading("Une arête qui saute une couche", level=3)
                    ui.text("Elle traverse à plat sous la couche du milieu ; "
                            "elle ne passe pas SUR le nœud.",
                            color="muted", size="xs")
                    ui.diagram(edges=[("a", "b"), ("b", "c"), ("a", "c")])

                    ui.heading("Une boucle sur soi-même", level=3)
                    ui.diagram(edges=[("a", "a"), ("a", "b")])

                    ui.heading("Un nœud isolé", level=3)
                    ui.diagram(nodes=[ui.node("seul", icon="circle")],
                               edges=[])

                    ui.heading("focus= vers un nœud inexistant", level=3)
                    ui.text("Une clé périmée retombe sur le graphe entier, "
                            "pas sur un écran blanc.",
                            color="muted", size="xs")
                    ui.diagram(edges=EDGES, focus="disparu")

                    ui.heading("Un label à échapper (XSS)", level=3)
                    ui.diagram(nodes=[ui.node("x", label="<script>alert(1)"),
                                      ui.node("y", label="a & b")],
                               edges=[("x", "y")])

                    ui.heading("Graphe vide", level=3)
                    ui.diagram(edges=[], empty_text="Aucune dépendance.",
                               empty_icon="unplug",
                               empty_description="Aucune feature n'en "
                                                 "consomme une autre.")

                    ui.heading("Graphe vide — l'échappatoire ``empty=``",
                               level=3)
                    ui.text("Les trois props de confort couvrent le cas "
                            "courant ; ``empty=`` rend ce qu'on veut à "
                            "leur place. Même API que ``ui.table`` et "
                            "``ui.datatable``.",
                            color="muted", size="xs")
                    ui.diagram(
                        edges=[],
                        empty=lambda: ui.button("Déclarer une dépendance",
                                                icon_left="plus",
                                                color="primary"),
                    )

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text(
                        "Ce que le composant devient une fois posé "
                        "AILLEURS — c'est là que se voient les fautes "
                        "qu'un montage isolé ne montre jamais.",
                        color="muted", size="sm")

                    ui.heading("render= — un nœud est un sous-arbre ui.*",
                               level=3)
                    ui.diagram(nodes=NODES, edges=EDGES, render=card_node,
                               size="lg")

                    ui.heading("Dans une grille contrainte", level=3)
                    ui.text("La cellule est plus étroite que le dessin : il "
                            "doit DÉFILER, pas rétrécir.",
                            color="muted", size="xs")
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        ui.diagram(edges=EDGES)
                        ui.diagram(edges=EDGES, direction="down")

                    ui.heading("Dans une colonne de hauteur bornée", level=3)
                    ui.text("Le piège de traps.md : une racine qui clippe a "
                            "une hauteur minimale de ZÉRO.",
                            color="muted", size="xs")
                    with ui.vstack(classes="h-[260px]"):
                        with ui.pane():
                            ui.diagram(nodes=NODES, edges=EDGES, size="xl")

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "C'est là que se joue l'argument du composant. Un "
                        "nœud est du HTML, pas un ``<rect>`` : il se tabule "
                        "dans l'ordre des COUCHES, porte l'anneau de focus "
                        "du thème, et Entrée / Espace l'activent quand il "
                        "porte un handler. Le calque d'arêtes est "
                        "``aria-hidden`` — ce qu'un lecteur d'écran doit "
                        "parcourir, ce sont les nœuds.",
                        color="muted", size="sm")
                    ui.text("Tabule ici : l'ordre suit les flèches.",
                            color="muted", size="xs")
                    ui.diagram(nodes=NODES, edges=EDGES, on_item_click=pick)

            # ── Card 5 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Chaque prop, chaque échappatoire universelle, "
                        "chaque modificateur — pilotés depuis un PageState.",
                        color="muted", size="sm")
                    server_panel()

            # ── Card 6 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    events_panel()

            # ── Card 7 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    client_panel()

            # ── Card 8 — Client events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    client_events_panel()
