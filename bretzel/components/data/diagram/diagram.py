"""``Diagram`` — un graphe orienté, placé en couches côté serveur.

Usage, niveau 1 — on ne déclare que les arêtes, les nœuds s'en
déduisent dans leur ordre d'apparition ::

    ui.diagram(edges=[("planning", "planning_engine"),
                      ("tournees", "planning_engine"),
                      ("planning_engine", "geo")])

Niveau 2 — chaque nœud est décrit, et le rendu d'un nœud t'appartient ::

    def carte(node):
        with ui.card(padding="sm") as c:
            with ui.hstack(gap="sm", align="center"):
                ui.icon(node.icon, color=node.color)
                ui.text(node.label, weight="medium", truncate=True)
        return c

    ui.diagram(
        nodes=[ui.node("geo", label="geo", icon="map-pin", color="warning")],
        edges=[ui.edge("planning", "geo", label="uses", style="dashed")],
        focus=state.selected,
        render=carte,
        on_item_click=select,
    )

Pourquoi des DESCRIPTEURS et pas des sous-composants
-----------------------------------------------------
``ui.tree_node`` existe parce que la contenance s'imbrique : un bloc
``with`` dit « dedans ». Un graphe ne s'imbrique pas — une arête relie
deux nœuds quelconques, et aucun ``with`` n'exprime ça. Et le composant
possède la boucle : c'est LUI qui casse les cycles, assigne les couches
et décide quels nœuds sont dessinés selon ``focus``. L'auteur n'a donc
aucun endroit où écrire son balisage, d'où ``render=`` — même contrat
que ``ui.column(render=)``. Cf. ``Component.COLLECTION_OWNER``.

⚠️ ``render=`` est rappelé pendant le rabattage de l'arbre, comme le
``render=`` d'une colonne : il doit être **synchrone**. Une coroutine y
est refusée par le socle.

Le partage HTML / SVG
---------------------
Les nœuds sont du HTML positionné en absolu ; seules les arêtes vivent
dans un ``<svg>`` posé derrière eux. C'est ce que retient React Flow, et
pour la même raison : un nœud dessiné en ``<rect>`` + ``<text>`` perdrait
tout ce que le reste du framework lui donne gratuitement — la troncature,
l'anneau de focus, une icône thémée, un badge, l'ordre de tabulation.
L'ordre du DOM suit les couches, donc la tabulation suit le sens de
lecture.

La vue par défaut
-----------------
``focus=None`` montre tout le graphe : il n'y a rien sur quoi se
centrer. Dès que ``focus`` nomme un nœud, la vue se resserre sur son
voisinage à ``depth`` sauts — parce qu'un graphe d'app réelle est dense
(22 nœuds et 61 arêtes, mesurés sur une app depuis retirée) et qu'un enchevêtrement
ne répond à aucune question, alors que le voisinage répond à celle
qu'on a : « qui touche à ça ».

Le placement, lui, ne vit pas ici : :mod:`bretzel.components.data.diagram.layout`
est pur, sans import du framework, et c'est ce qui rend la moitié
difficile testable sans navigateur.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    ComponentUsageError,
    coerce_children,
    reactive_prop,
)
from bretzel.components.base._wiring import (
    activate_keydown,
    hidden_carrier_attrs,
    server_sync_marker,
)
from bretzel.components.base.events import (
    client_event_attr,
    item_action_attrs,
)
from bretzel.components.data.diagram.layout import (
    Metrics,
    keys_from_edges,
    layout,
    neighbourhood,
)
from bretzel.components.data.diagram.theme import DIAGRAM_THEME
from bretzel.core.tree import Element, Node, TextNode
from bretzel.render.context import current_context

#: Un clic sur un enfant interactif d'un nœud (un bouton posé par un
#: ``render=``, un lien) ne déclenche PAS le clic du nœud.
#:
#: Même construction que celle de ``Table`` pour les lignes cliquables,
#: et pour la même contrainte de parseur : HTMX découpe ``hx-trigger``
#: sur les virgules et referme le filtre au premier ``]``, donc pas de
#: ``closest('a,button')`` — on conjugue des ``closest()`` à une balise.
_NODE_INTERACTIVE_TAGS = ("button", "a", "input", "select", "textarea", "label")
_NODE_CLICK_GUARD = " && ".join(
    f"!event.target.closest('{tag}')" for tag in _NODE_INTERACTIVE_TAGS
)
_NODE_CLICK_KEYDOWN = activate_keydown("$el.click();")

#: Les styles d'arête, et le nom du slot de thème qui les porte.
_EDGE_STYLES = {"solid": "edge", "dashed": "edge_flipped"}


# ───────────────────────────────────────────────────────────────────────────
# Descripteurs
# ───────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class GraphNode:
    """Un nœud du graphe.

    - ``key`` est son identité — c'est ce que citent les arêtes, ce que
      reçoit ``on_item_click``, et ce sur quoi ``focus`` se centre.
      ``key`` et non ``id`` : ``id`` est un kwarg universel du framework,
      et la collision serait un piège silencieux.
    - ``label`` est le texte affiché ; à défaut, la clé.
    - ``icon`` / ``color`` / ``badge`` nourrissent le rendu par défaut, et
      restent lisibles depuis un ``render=`` maison.
    - ``group`` est une étiquette libre, rendue en ``data-bz-group`` :
      de quoi cibler une famille de nœuds en CSS sans que le composant
      impose une sémantique.
    - ``width`` déroge à la largeur du palier pour ce nœud seul.
    """

    key: str
    label: str = ""
    icon: str | None = None
    color: str | None = None
    badge: str | None = None
    group: str | None = None
    width: float | None = None


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """Une arête orientée, de ``source`` vers ``target``.

    ``source`` / ``target`` plutôt que ``from`` / ``to`` : ``from`` est un
    mot-clé Python, donc impossible en nom d'argument.
    """

    source: str
    target: str
    label: str = ""
    style: str = "solid"
    color: str | None = None


def node(
    key: str,
    *,
    label: str = "",
    icon: str | None = None,
    color: str | None = None,
    badge: str | None = None,
    group: str | None = None,
    width: float | None = None,
) -> GraphNode:
    """Décrire un nœud — sucre pour ``ui.node(...)``."""
    return GraphNode(
        key=key, label=label, icon=icon, color=color,
        badge=badge, group=group, width=width,
    )


def edge(
    source: str,
    target: str,
    *,
    label: str = "",
    style: str = "solid",
    color: str | None = None,
) -> GraphEdge:
    """Décrire une arête — sucre pour ``ui.edge(...)``."""
    return GraphEdge(
        source=source, target=target, label=label, style=style, color=color
    )


def _as_pair(item: Any) -> tuple[str, str]:
    """``("a", "b")`` ou ``ui.edge("a", "b")`` — la même paire."""
    if isinstance(item, GraphEdge):
        return (item.source, item.target)
    source, target = item
    return (str(source), str(target))


def _as_node(item: Any) -> GraphNode:
    """``"a"`` ou ``ui.node("a")`` — le même descripteur."""
    return item if isinstance(item, GraphNode) else GraphNode(key=str(item))


# ───────────────────────────────────────────────────────────────────────────
# Le composant
# ───────────────────────────────────────────────────────────────────────────


class Diagram(Component):
    """Un graphe orienté placé en couches, rendu côté serveur."""

    THEME: ClassVar[dict[str, Any]] = DIAGRAM_THEME
    THEME_KEY: ClassVar[str] = "diagram"
    #: Le composant possède la boucle : cycles cassés, couches
    #: assignées, croisements réduits, et ``focus`` décide même QUELS
    #: nœuds sont dessinés. L'auteur ne peut pas écrire cette boucle —
    #: d'où le rappel ``render=``, seul point d'entrée possible.
    COLLECTION_OWNER: ClassVar[str | None] = "component"
    #: ``item_click`` est un VRAI event, pas un paramètre bricolé.
    #:
    #: La conséquence n'est pas cosmétique : `on_item_click=` accepte
    #: désormais les trois formes de tout `on_*` du framework — un
    #: callable serveur, une chaîne d'expression cliente, ou une LISTE
    #: des deux. Tant qu'il n'était pas déclaré, il n'acceptait qu'un
    #: callable, et le gabarit du playground lisait « ce composant n'a
    #: pas d'event » — donc pas de carte Server events ni Client events.
    #:
    #: ⚠️ Le routage reste MANUEL, contrairement au cas courant. Le socle
    #: pose l'`hx-post` d'un event déclaré sur la RACINE, or ici chaque
    #: nœud porte le sien, avec sa clé. `on_item_click` est donc un
    #: paramètre nommé de l'``__init__`` — le socle ne le voit jamais
    #: passer — et `_click_attrs` fait le travail. Même situation que le
    #: `on_item_click` de `ui.table`.
    EVENTS: ClassVar[tuple[str, ...]] = ("item_click",)
    IS_CONTAINER: ClassVar[bool] = False
    #: ``value`` = le nœud SÉLECTIONNÉ, et il est ⇄ two-way.
    #:
    #: La règle de `client-reactive-surface.md` § *La règle* est
    #: explicite au premier temps du test : « l'utilisateur édite-t-il
    #: cette valeur en interagissant avec CE composant ? … la
    #: sélection → ⇄ two-way ». Le pilote client existe — c'est le clic
    #: sur un nœud — donc `@refreshable` seul ne suffit pas.
    #:
    #: ⚠️ Ce composant a livré une surface bindable VIDE pendant une
    #: journée, sur l'intuition « affichage pur ». L'intuition était
    #: fausse et la règle écrite disait le contraire : un diagramme
    #: n'est pas un affichage, c'est un SÉLECTEUR.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value",)

    value: Any = reactive_prop(
        default="", emit_attr=False, writes=True,
        names_field=True,
    )
    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)

    def __init__(
        self,
        *,
        value: Any = None,
        edges: Iterable[Any] = (),
        nodes: Iterable[Any] = (),
        focus: str | None = None,
        depth: int = 1,
        direction: str = "right",
        render: Callable[[GraphNode], Any] | None = None,
        on_item_click: Callable[..., Any] | str
        | list[Callable[..., Any] | str] | None = None,
        size: str | None = None,
        color: str | None = None,
        empty_text: str = "No graph.",
        empty_icon: str | None = "workflow",
        empty_description: str | None = None,
        empty: Callable[[], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None.
        super().__init__(value=value, size=size, color=color, **kwargs)
        if direction not in ("right", "down"):
            raise ComponentUsageError(
                f"ui.diagram: direction={direction!r} — attendu 'right' "
                f"(les couches sont des colonnes) ou 'down'."
            )
        self._edges = [e if isinstance(e, GraphEdge) else GraphEdge(*_as_pair(e))
                       for e in edges]
        self._pairs = [_as_pair(e) for e in self._edges]
        declared = [_as_node(n) for n in nodes]
        self._declared = {n.key: n for n in declared}
        # Niveau 1 : sans ``nodes=``, les clés viennent des arêtes, dans
        # leur ordre de première apparition — donc déterministe.
        self._keys = (
            [n.key for n in declared] if declared else keys_from_edges(self._pairs)
        )
        self._focus = focus
        self._depth = depth
        self._direction = direction
        self._render = render
        self._click = on_item_click
        self._empty_text = empty_text
        self._empty_icon = empty_icon
        self._empty_description = empty_description
        self._empty = empty
        self._reject_unknown_endpoints()

    def _reject_unknown_endpoints(self) -> None:
        """Une arête qui cite un nœud non déclaré est refusée, nommée.

        Seulement quand ``nodes=`` est donné : sans lui les clés SORTENT
        des arêtes, donc rien ne peut être inconnu. Le moteur de
        placement, lui, ignore silencieusement — c'est le bon
        comportement pour une fonction pure appelée dans un rendu, mais
        au niveau du composant on peut nommer le fautif, donc on le
        nomme. Un nœud qui manque produit sinon un dessin amputé qu'on
        relit dix minutes avant de comprendre.
        """
        if not self._declared:
            return
        known = set(self._keys)
        missing = sorted(
            {k for pair in self._pairs for k in pair if k not in known}
        )
        if missing:
            raise ComponentUsageError(
                f"ui.diagram: les arêtes citent {', '.join(missing)}, qui "
                f"n'est pas dans nodes=. Ajoute le nœud, corrige la clé, ou "
                f"retire nodes= pour que les nœuds se déduisent des arêtes."
            )

    def _build_empty(self, size_key: str) -> tuple[Node, ...]:
        """L'état vide : ``empty=`` s'il est donné, sinon l'auto.

        Même API que ``ui.table`` et ``ui.datatable`` — trois props de
        confort plus une échappatoire, et les deux branches passent par
        ``coerce_children``. Sans elle, un ``empty=`` qui rend ``None``
        écrit la chaîne ``"None"`` à l'écran ; c'est le bug qu'a payé
        ``ui.table`` le 2026-08-18.
        """
        if self._empty is not None:
            return coerce_children(self._empty())

        # `ui.empty_state`, comme `ui.table` — pas un texte gris centré
        # à la main. Il porte l'icône, la hiérarchie de titre et
        # l'espacement du thème ; les réécrire ici en donnerait une
        # deuxième version qui dériverait.
        from bretzel.components.feedback.empty_state import EmptyState

        # ⚠️ `_detach_from_parent` AVANT `render()`. Un Component
        # construit dans un `render()` s'auto-enregistre au parent ACTIF
        # et fuit quand le composant est détaché — le piège « Icon
        # construit dans render() sans detach » de traps.md.
        empty = EmptyState(
            self._empty_text,
            icon=self._empty_icon,
            description=self._empty_description,
            # L'état vide suit le palier du diagramme : sans ça un
            # `size=` ne change RIEN sur un graphe vide, ce qui est
            # exactement le kwarg mort que ce dépôt traque.
            size=size_key,
        )
        Component._detach_from_parent(empty)
        return (empty.render(),)

    # ── Sélection de la vue ─────────────────────────────────────────────

    def _drawn(self) -> tuple[list[str], list[GraphEdge]]:
        """Les nœuds et arêtes effectivement dessinés.

        ``_drawn`` et pas ``_visible`` : ``visible`` est un kwarg
        universel, et le socle range le sien dans ``self._visible``. La
        méthode l'écrasait — le composant levait « NoneType is not
        callable » au rendu, pas à la construction.

        ``focus=None`` rend tout : il n'y a rien sur quoi se centrer.
        Sinon on se resserre sur le voisinage — et un ``focus`` qui ne
        désigne aucun nœud connu retombe sur le graphe entier plutôt que
        sur un dessin vide, parce qu'une clé périmée dans un état
        d'interface est un accident banal (une feature renommée, un id
        gardé en session) et qu'un écran blanc n'en dit rien.
        """
        if self._focus is None or self._focus not in set(self._keys):
            return list(self._keys), list(self._edges)
        keep = neighbourhood(self._focus, self._pairs, depth=self._depth)
        keys = [k for k in self._keys if k in keep]
        edges = [e for e in self._edges if e.source in keep and e.target in keep]
        return keys, edges

    def _adjacency(
        self, keys: list[str], edges: list[GraphEdge]
    ) -> dict[str, list[str]]:
        """``{clé: elle-même + ce qui la touche}``, dans les deux sens.

        Calculé UNE fois au rendu et cuit dans le DOM : c'est ce qui rend
        la mise en évidence gratuite côté client. Le navigateur n'a rien
        à parcourir, il lit un tableau.

        Trié, parce que le HTML de deux rendus du même graphe doit être
        identique à l'octet — sinon idiomorph remplace au lieu de
        fusionner, et toute comparaison de non-régression devient du
        bruit.
        """
        near: dict[str, set[str]] = {k: {k} for k in keys}
        for edge in edges:
            if edge.source in near and edge.target in near:
                near[edge.source].add(edge.target)
                near[edge.target].add(edge.source)
        return {k: sorted(v) for k, v in near.items()}

    # ── Rendu ───────────────────────────────────────────────────────────

    def _node_body(self, spec: GraphNode, step: dict, slots: dict) -> tuple[Node, ...]:
        """Le contenu d'un nœud — le ``render=`` de l'auteur, ou le défaut."""
        if self._render is not None:
            return coerce_children(self._render(spec))

        from bretzel.components.feedback.badge import Badge
        from bretzel.components.primitives.icon import Icon

        inner: list[Node] = []
        if spec.icon:
            glyph = Icon(name=spec.icon, size=step.get("icon", "sm"),
                         color=spec.color)
            Component._detach_from_parent(glyph)
            inner.append(glyph.render())
        label_class = " ".join(
            p for p in (slots.get("label", ""), step.get("text", "")) if p
        )
        inner.append(
            Element(
                tag="span",
                attrs={"class": label_class},
                children=(TextNode(spec.label or spec.key),),
            )
        )
        if spec.badge:
            pill = Badge(label=spec.badge, size=step.get("badge", "xs"),
                         color="muted")
            Component._detach_from_parent(pill)
            inner.append(pill.render())
        return (
            Element(
                tag="div",
                attrs={"class": slots.get("node_body", "")},
                children=tuple(inner),
            ),
        )

    def _click_attrs(self, key: str, lit: str) -> dict[str, Any]:
        """Le câblage de ``item_click`` pour CE nœud.

        L'action est par NŒUD, pas sur la racine — donc elle passe par
        ``item_action_attrs``, le routeur partagé des quatre composants
        dans ce cas (une ligne de ``ui.table``, une barre, une part, un
        nœud). Il rend les trois formes d'un ``on_*`` du framework : un
        callable serveur, une chaîne d'expression cliente, ou une liste
        des deux.

        ⚠️ Ce site RECOPIAIT ce routeur au lieu de l'appeler, et il a
        payé les deux choses que le routeur savait déjà faire : le
        trigger réécrit à la main juste après ``action_attrs``, et une
        expression cliente NON gardée — donc un ``on_item_click="…"``
        partait aussi quand on cliquait un bouton posé par ``render=``,
        là où la même expression sur ``ui.table`` ne part pas. Adopté le
        2026-09-07 ; c'est le mode d'échec « primitive livrée, jamais
        adoptée aux call-sites » que l'audit de cohérence nomme.

        ``lit`` est l'expression d'éclairage. Elle vient EN PREMIER pour
        que la mise en évidence soit visible avant que la requête parte,
        et elle est la SEULE chose que ce site ajoute au routeur.
        """
        attrs = item_action_attrs(
            self._click,
            event="item_click",
            bind=lambda fn: functools.partial(fn, key),
            owner_id=self.id,
            ctx=current_context(),
            # L'event DÉCLARÉ est `item_click`, celui du DOM est `click`.
            dom_event="click",
            guard=_NODE_CLICK_GUARD,
            # `debounce=` / `throttle=` : le socle ne les
            # applique qu'à l'action de la RACINE.
            modifier=self._trigger_modifier,
        )
        # L'ÉCLAIRAGE vient en premier, et il n'est PAS gardé — c'est la
        # seule chose que ce site ajoute au routeur partagé. La mise en
        # évidence doit être visible avant que la requête parte, et un
        # clic sur un bouton posé par `render=` doit quand même désigner
        # le nœud, même s'il ne déclenche pas l'action.
        handler_side = attrs.get(client_event_attr("click"), "")
        attrs[client_event_attr("click")] = (
            f"{lit}; {handler_side}" if handler_side else lit
        )
        handlers = (
            list(self._click) if isinstance(self._click, (list, tuple))
            else [self._click]
        )
        # Un nœud sur lequel il y a quelque chose à faire s'annonce comme
        # tel. L'éclairage seul ne suffit pas à en faire un bouton — il
        # se déclenche par le clic, pas par le clavier.
        if any(callable(h) for h in handlers if h is not None):
            attrs["role"] = "button"
            attrs["tabindex"] = "0"
            attrs["bz-on:keydown"] = _NODE_CLICK_KEYDOWN
        return attrs

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        sizes = theme.get("sizes", {})
        size_key = self._reactive_values.get("size") or "md"
        step = sizes.get(size_key, sizes.get("md", {}))

        # ⚠️ Le scope et l'input caché se bâtissent AVANT la branche
        # vide, et sont posés sur la racine dans LES DEUX cas.
        #
        # La première version sortait tôt sur un graphe vide, donc sa
        # racine n'avait ni `bz-data` ni porteur : un `value=` lié y
        # perdait sa cellule, et `_serverSync` disparaissait avec. Le
        # contrat d'un composant ne doit pas changer de forme avec ses
        # DONNÉES — c'est ce que `test_server_sync_completeness` a
        # attrapé, en le construisant sans arête.
        root_attrs, carrier = self._selection_wiring(slots)

        keys, edges = self._drawn()
        if not keys:
            hollow = Element(
                tag="div",
                attrs={"class": slots.get("empty", "")},
                children=self._build_empty(size_key),
            )
            return Element(
                tag="div",
                attrs=root_attrs,
                children=(hollow, carrier) if carrier is not None else (hollow,),
            )

        metrics = Metrics(
            node_width=float(step.get("w", 160)),
            node_height=float(step.get("h", 44)),
            layer_gap=float(step.get("layer", 72)),
            lane_gap=float(step.get("lane", 20)),
        )
        widths = {
            k: float(self._declared[k].width)
            for k in keys
            if k in self._declared and self._declared[k].width is not None
        }
        placed = layout(
            keys,
            [(e.source, e.target) for e in edges],
            metrics=metrics,
            direction=self._direction,
            widths=widths,
        )

        # ── Le calque d'arêtes ──────────────────────────────────────
        # Le marqueur de flèche est identifié par l'id de l'instance :
        # deux diagrammes sur une page partageraient sinon un ``<defs>``
        # et le second réutiliserait la flèche du premier — même forme
        # ici, mais un ``color=`` différent la ferait diverger.
        marker = f"{self.id or 'bz-diagram'}__arrow"
        by_pair = {(e.source, e.target): e for e in edges}
        paths: list[Node] = []
        for route in placed.routes:
            spec = by_pair.get((route.source, route.target))
            slot = _EDGE_STYLES.get(
                spec.style if spec else "solid", "edge"
            )
            attrs: dict[str, Any] = {
                "d": route.path,
                "class": theme.get(slot, theme.get("edge", "")),
                "marker-end": f"url(#{marker})",
                # Une arête ne reste en avant que si ses DEUX extrémités
                # le sont — sinon l'écran se remplit des liaisons qui
                # partent du voisinage vers l'extérieur, c'est-à-dire de
                # ce qu'on cherchait justement à retirer.
                "bz-class": (
                    f"isEdgeLit({json.dumps(route.source)}, "
                    f"{json.dumps(route.target)}) ? '' : "
                    f"{json.dumps(theme.get('edge_dim', 'opacity-15'))}"
                ),
            }
            if spec is not None and spec.color:
                attrs["class"] = f"{attrs['class']} stroke-(--bz-fg)"
            if spec is not None and spec.label:
                paths.append(
                    Element(
                        tag="path",
                        attrs=attrs,
                        children=(
                            Element(tag="title", attrs={},
                                    children=(TextNode(spec.label),)),
                        ),
                    )
                )
                continue
            paths.append(Element(tag="path", attrs=attrs, children=()))

        arrow = Element(
            tag="defs",
            attrs={},
            children=(
                Element(
                    tag="marker",
                    attrs={
                        "id": marker,
                        "viewBox": "0 0 8 8",
                        "refX": "7", "refY": "4",
                        # 5 et non 7 : la pointe portait autant d'encre
                        # que le nœud qu'elle désigne. Le sens est déjà
                        # dit par les couches (on lit vers la droite) —
                        # la flèche le CONFIRME, elle ne l'annonce pas.
                        "markerWidth": "5", "markerHeight": "5",
                        "orient": "auto-start-reverse",
                    },
                    children=(
                        Element(
                            tag="path",
                            attrs={"d": "M0,0 L8,4 L0,8 z",
                                   "class": "fill-text/20"},
                            children=(),
                        ),
                    ),
                ),
            ),
        )
        svg = Element(
            tag="svg",
            attrs={
                "class": slots.get("edges", ""),
                "viewBox": f"0 0 {placed.width:.0f} {placed.height:.0f}",
                "width": f"{placed.width:.0f}",
                "height": f"{placed.height:.0f}",
                # Le tracé est décoratif : ce que le lecteur d'écran doit
                # parcourir, ce sont les nœuds, dans l'ordre des couches.
                "aria-hidden": "true",
            },
            children=(arrow, *paths),
        )

        # ── Les nœuds ───────────────────────────────────────────────
        # Dans l'ordre des COUCHES, pas dans celui d'entrée : l'ordre du
        # DOM est l'ordre de tabulation, et on veut lire le graphe dans
        # le sens des flèches.
        boxes = {b.key: b for b in placed.boxes}
        near = self._adjacency(keys, edges)
        node_els: list[Node] = []
        for layer in placed.layers:
            for key in layer:
                box = boxes.get(key)
                if box is None:  # pragma: no cover — une couche ne cite
                    continue     # que des nœuds placés
                spec = self._declared.get(key, GraphNode(key=key))
                node_class = slots.get("node", "")
                if key == self._focus:
                    node_class = " ".join(
                        p for p in (node_class, slots.get("node_focus", "")) if p
                    )
                attrs: dict[str, Any] = {
                    "class": node_class,
                    # ⚠️ Position et taille en style INLINE. Une classe
                    # assemblée (`left-[240px]`) n'existe qu'en dev : le
                    # compilateur de prod ne balaie que des littéraux, et
                    # la page se disloque en prod seulement.
                    "style": (
                        f"left:{box.x:.2f}px;top:{box.y:.2f}px;"
                        f"width:{box.width:.2f}px;height:{box.height:.2f}px"
                    ),
                    "data-bz-node": key,
                # L'adjacence reste EXPOSÉE en donnée : le prédicat la
                # reçoit en argument, mais un `render=` maison ou un
                # sélecteur CSS peut vouloir la lire.
                "data-bz-adj": json.dumps(near.get(key, [key])),
                }
                if spec.group:
                    attrs["data-bz-group"] = spec.group
                # Désigner un nœud éclaire ce qui le touche. Zéro
                # requête : l'adjacence est cuite ici, le navigateur ne
                # parcourt rien. C'est un geste de LECTURE, il n'a rien
                # à demander au serveur.
                #
                # Sur le clic et pas sur le survol : un écran tactile n'a
                # pas de survol, et un `hover` est aussi mort sur un
                # poste dont le pointeur est grossier.
                adj = json.dumps(near.get(key, [key]))
                lit_expr = f"light({json.dumps(key)})"
                # L'adjacence voyage dans le PRÉDICAT, pas dans un état :
                # `isLit` dérive de la sélection, donc l'éclairage suit
                # une écriture venue de dehors (un contrôle lié au même
                # champ) exactement comme un clic.
                attrs["bz-class"] = (
                    f"isLit({json.dumps(key)}, {adj}) ? '' : "
                    f"{json.dumps(slots.get('node_dim', 'opacity-25'))}"
                )
                attrs.update(self._click_attrs(key, lit_expr))
                node_els.append(
                    Element(
                        tag="div",
                        attrs=attrs,
                        children=self._node_body(spec, step, slots),
                    )
                )

        # Le scope de mise en évidence, posé sur la toile pour que le
        # calque d'arêtes ET les nœuds en héritent — c'est un seul scope,
        # comme la disclosure d'un `ui.tree`.
        #
        # Les méthodes sortent de `$bz.diagram.scope` plutôt que d'être
        # sérialisées ici : leur corps est rigoureusement le même d'un
        # nœud à l'autre, seule l'ADJACENCE diffère, et elle voyage sur
        # le nœud.
        canvas = Element(
            tag="div",
            attrs={
                "class": slots.get("canvas", ""),
                "style": f"width:{placed.width:.2f}px;height:{placed.height:.2f}px",
            },
            children=(svg, *node_els),
        )
        return Element(
            tag="div",
            attrs=root_attrs,
            children=(
                (canvas, carrier) if carrier is not None else (canvas,)
            ),
        )

    def _selection_wiring(
        self, slots: dict
    ) -> tuple[dict[str, Any], Element | None]:
        """Les attributs de la racine, et l'input caché s'il en faut un.

        ⚠️ Ce littéral de scope rejoint la dette n°1 du socle (14 → 15
        fichiers, `test_scope_literal_debt_only_shrinks`), et c'est une
        DÉCISION, pas un oubli. Une prop ⇄ two-way exige la bascule
        « valeur locale → cellule du magasin » ; les 13 composants qui
        ont à la fois un slab runtime et une sélection la portent tous.
        Le prix de l'éviter serait de réinliner les cinq méthodes de
        `$bz.diagram.scope` dans CHAQUE nœud.
        """
        binding = self._binding_metadata.get("value")
        initial = str(self._reactive_values.get("value") or "")
        (scope_key,) = self._scope_keys("value")
        if binding is not None:
            # Lié : la cellule du magasin EST la vérité, on ne la
            # duplique pas localement (ça courserait l'application du
            # delta par le framework).
            path = self.path_of(binding)
            scope = (
                "{...$bz.diagram.scope,"
                f"_read(){{return {path};}},"
                f"_write(v){{{path} = v;}}}}"
            )
        else:
            sync = server_sync_marker(
                *self._scope_keys("value"),
                enabled=self._value_server_backed("value"),
            )
            scope = (
                "{...$bz.diagram.scope,"
                f"{scope_key}: {json.dumps(initial)}"
                + (f",{sync}" if sync else "")
                + "}"
            )

        # ── L'input caché — intégration formulaire / action serveur ──
        # Un `<div>` ne porte ni `name`/`value` ni `change` natif : le
        # porteur fait les deux, comme chez les 11 autres composants
        # dont la racine n'est pas un contrôle de formulaire.
        carrier: Element | None = None
        name = self._reactive_values.get("name") or self._derive_field_name()
        if name:
            value_directive = self.path_of(binding) if binding is not None else scope_key
            carrier_attrs: dict[str, Any] = {
                **hidden_carrier_attrs(value_directive, initial=initial),
                "name": str(name),
            }
            carrier = Element(tag="input", attrs=carrier_attrs, children=())

        return (
            {
                "class": slots.get("root", ""),
                # Le scope vit sur la RACINE et non sur la toile : c'est
                # elle qui doit pouvoir répondre au clic tombé À CÔTÉ
                # d'un nœud, dans le blanc du dessin.
                "bz-data": scope,
                # Cliquer dans le vide rallume tout. Le clic HORS du
                # composant aussi — c'est ce qu'arme `arm($el)`, via le
                # `clickOutside` partagé des overlays.
                "bz-on:click": (
                    "if (!$event.target.closest('[data-bz-node]')) reset()"
                ),
                "bz-effect": "arm($el)",
            },
            carrier,
        )
