"""``Sidebar`` / ``SidebarSection`` / ``SidebarItem`` — navigation rail.

API ::

    with ui.sidebar(open=client_state.expanded, collapsible=True):
        with ui.sidebar_section(label="MAIN"):
            ui.sidebar_item("Dashboard", icon="home", href="/")
            ui.sidebar_item("Issues", icon="bug", href="/issues",
                            badge=42)
        with ui.sidebar_section(label="ACCOUNT"):
            ui.sidebar_item("Settings", icon="settings", href="/settings")

Three pieces, all V1-derived but consolidated :

- **Sidebar** — the ``<aside>`` container. Drives the
  ``current_path`` reactive via ``bz-data`` + window listeners on
  ``popstate`` / ``htmx:after-request`` so the active
  ``SidebarItem`` highlights live without a server round-trip when
  the URL changes. ``open=`` (literal or ClientBinding) drives
  ``data-open`` which the theme reads to fade out labels + badges
  via ``md:group-data-[open=false]:*`` Tailwind selectors. The
  sidebar is DESKTOP navigation chrome only — responsive mobile nav
  is the app layout's job (``if Screen().is_mobile:``), not built
  into this component.
- **SidebarSection** — optional grouping with an uppercase label
  that hides on collapse.
- **SidebarItem** — the one nav-row primitive. When ``href`` is
  passed AND we're inside an ``@layout`` (the render context
  carries the layout name on ``ctx.layout_stack``), the item
  auto-injects ``hx-get`` / ``hx-target=#outlet_<layout>`` /
  ``hx-swap=morph:innerHTML`` / ``hx-push-url=true`` so the click
  partial-navigates without reloading the layout. The active
  highlight is driven by a reactive ``bz-attr:data-active`` comparing
  the item's href to the sidebar's ``current_path``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.actions.icon_button import IconButton
from bretzel.components.base import (
    Component,
    ComponentUsageError,
    reactive_prop,
    stamp_display_none,
)
from bretzel.components.base._wiring import (
    TOGGLE_NEAREST_SIDEBAR,
    anchored_dismiss_init,
    anchored_panel_effect,
    bool_attr,
    escape_init,
    imperative_listeners,
    install_open_close_toggle,
    modal_root_effect,
    server_sync_marker,
    teleport_to_body,
    unwrap_transparent,
)
from bretzel.components.navigation._wiring import (
    capture_layout,
    current_path_resync_init,
    current_path_scope,
    is_external_href,
    render_badge,
    wire_nav_item,
)
from bretzel.components.navigation.sidebar.theme import (
    SIDEBAR_FOOTER_ITEM_THEME,
    SIDEBAR_FOOTER_THEME,
    SIDEBAR_ITEM_THEME,
    SIDEBAR_THEME,
)
from bretzel.components.primitives.divider import Divider
from bretzel.components.primitives.icon import Icon
from bretzel.components.primitives.menu_item import MenuItem
from bretzel.core.tree import Element
from bretzel.core.tree import TextNode as TextNode
from bretzel.render import text
from bretzel.render.context import maybe_current_context


def _icon_name(icon: Any) -> str | None:
    """Normalise a title/footer ``icon=`` argument to a bare name string.

    Accepts ``"zap"`` (a name, optionally set-prefixed like ``"mdi:home"``)
    OR a built :class:`Icon` component (``ui.icon("zap")``). The sidebar
    title styles the glyph itself, so we only need the name — passing a
    full ``Icon`` is a convenience that should never crash. Returns
    ``None`` for a falsy icon.
    """
    if not icon:
        return None
    if isinstance(icon, str):
        return icon
    if isinstance(icon, Component):
        # Read the public ``name`` reactive prop (an Icon exposes "zap") ;
        # any other component without one yields None.
        name = getattr(icon, "name", None)
        return str(name) if name else None
    return str(icon)


def _iconify_ref(name: str) -> str:
    """Full iconify ``set:name`` reference for a glyph : honour an explicit
    set prefix ("mdi:home"), default to lucide for a bare name."""
    return name if ":" in name else f"lucide:{name}"


# ───────────────────────────────────────────────────────────────────────────
# Sidebar — root container
# ───────────────────────────────────────────────────────────────────────────


class Sidebar(Component):
    """Render a collapsible application sidebar."""

    THEME: ClassVar[dict[str, Any]] = SIDEBAR_THEME
    THEME_KEY: ClassVar[str] = "sidebar"
    DEFAULT_TAG: ClassVar[str] = "aside"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("open",)
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("open", "close", "toggle")
    # Accepts literal / server-resolved / ClientBinding. Drives the
    # desktop expand/collapse.
    open: Any = reactive_prop(default=True, emit_attr=False, writes=True)
    width: str = reactive_prop(default="md", emit_attr=False)
    # UN axe : ce que « replié » veut dire. Remplace le couple
    # ``variant=`` (rail/drawer) + ``collapsible=`` (True/False), qui
    # faisait deux props pour une seule décision et laissait passer une
    # combinaison absurde (``collapsible=False`` + drawer = une sidebar
    # qu'on ne peut ni replier ni rouvrir).
    #
    #   "rail"      replié → bande d'icônes de 64px, DANS le flux
    #   "offcanvas" replié → largeur 0, dans le flux, le contenu s'étale
    #   "overlay"   fermé → absent ; ouvert → flotte au-dessus du
    #               contenu, fond assombri, Escape, scroll bloqué
    #   "none"      ne se replie jamais, aucun chevron rendu
    #
    # ``overlay`` est le mode qu'on monte sur un téléphone — c'est le
    # SEUL qui ne soit pas gaté ``md:``, cf. le thème.
    collapsible: str = reactive_prop(default="rail", emit_attr=False)

    #: Les quatre valeurs légales, lues par le garde du constructeur ET
    #: par le thème. Une seule source : un cinquième mode s'ajoute ici.
    COLLAPSE_MODES: ClassVar[tuple[str, ...]] = (
        "rail", "offcanvas", "overlay", "none",
    )

    # Axe livré puis COUPÉ (2026-08-15), sur le test décisif de la règle
    # d'opinionation : « aurait-on ce composant sous deux formes dans la
    # MÊME app ? ». Non — une app a une seule nav latérale, et elle est à
    # gauche. Aucun call-site du dépôt ne passait ``side="right"`` ; le
    # seul était la carte du banc qui le démontrait.
    #
    # Le mode droite était de toute façon à moitié mort : le tooltip du
    # rail ancre son X sur ``aside.getBoundingClientRect().right + 8``
    # (cf. ``SidebarItem.render``), donc en ``side="right"`` le panneau
    # sortait de l'écran.
    #
    # ⚠️ Le garde n'est pas de la politesse — même raison que
    # ``bottom_bar._CUT``, dont ceci est la copie exacte : sans lui, le
    # socle absorbe le kwarg inconnu dans les attrs bruts et
    # ``ui.sidebar(side="right")`` émettrait un attribut HTML
    # ``side="right"`` **en silence**, sans rien changer au rendu.
    _CUT: ClassVar[dict[str, str]] = {
        "side": (
            "une nav latérale vit à gauche — les deux côtés ne coexistent "
            "jamais dans la même app, donc c'est une décision de thème"
        ),
        "variant": (
            "fusionné dans `collapsible=` le 2026-08-15 — il ne disait "
            'jamais autre chose que « à quoi ressemble le replié ». '
            'Écris `collapsible="rail"` (ex-variant="rail") ou '
            '`collapsible="offcanvas"` (ex-variant="drawer")'
        ),
    }

    def __init__(
        self,
        *,
        open: Any = None,
        width: str | None = None,
        collapsible: str | None = None,
        **kwargs: Any,
    ) -> None:
        # ``collapsible`` etait un BOOL jusqu'au 2026-08-15. Un appel
        # resté à l'ancienne forme passerait ici sans bruit — ``True``
        # n'est aucun des quatre modes, donc le thème ne composerait
        # aucune règle de repli et la sidebar cesserait juste de se
        # replier, en silence. Le message dit quoi écrire.
        if isinstance(collapsible, bool):
            raise ComponentUsageError(
                f"ui.sidebar(collapsible={collapsible!r}) : `collapsible=` "
                f"n'est plus un booléen, c'est le mode de repli. Écris "
                f'`collapsible="rail"` (ex-True) ou `collapsible="none"` '
                f"(ex-False)."
            )
        if collapsible is not None and collapsible not in self.COLLAPSE_MODES:
            raise ComponentUsageError(
                f"ui.sidebar(collapsible={collapsible!r}) : mode inconnu. "
                f"Les quatre modes sont {', '.join(self.COLLAPSE_MODES)}."
            )
        for name, why in self._CUT.items():
            if name in kwargs:
                raise ComponentUsageError(
                    f"ui.sidebar n'a pas de `{name}=` : {why}. "
                    f"Override le slot `root` du thème pour changer ça — "
                    f'Bretzel(theme=Theme(components={{"sidebar": '
                    f'{{"slots": {{"root": "…"}}}}}})), ou '
                    f'`slots={{"root": "…"}}` sur l\'instance pour un cas '
                    f"unique."
                )
        # Forward direct : le socle drope les kwargs reactive ``None``
        # (garde le défaut) — plus de garde manuelle.
        super().__init__(
            open=open,
            width=width,
            collapsible=collapsible,
            **kwargs,
        )
        # API impérative write-only ``.open()`` / ``.close()`` /
        # ``.toggle()`` — installée en attributs d'instance (shadow le
        # descripteur ``open``) par le helper base, identique aux 4 overlays
        # open-driven (write-through binding ∪ dispatch). Cf. `imperative-api.md`.
        install_open_close_toggle(self)
        # Le registre de la requête. Il sert deux questions qui ne se
        # répondent qu'une fois la page bâtie : à QUELLE barre un
        # ``ui.sidebar_trigger`` sans argument parle, et cette barre
        # a-t-elle un moyen d'être rouverte
        # (``base/_wiring.check_sidebars_are_reachable``).
        ctx = maybe_current_context()
        if ctx is not None:
            ctx.sidebars.append(self)


    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        widths = theme.get("widths", {})
        collapse = theme.get("collapse", {})

        width_key = self._reactive_values.get("width") or "md"
        mode = self._reactive_values.get("collapsible") or "rail"
        # ``overlay`` sort la sidebar du flux : elle devient un panneau
        # modal (fond assombri, Escape, scroll bloqué). C'est le seul
        # mode qui demande du câblage en plus des classes.
        is_overlay = mode == "overlay"

        # ── ``open`` resolution — literal vs binding ─────────────────
        # ``data-open`` reflects the desktop expanded state. The theme
        # composes ``data-[open=false]`` selectors per variant : rail
        # narrows to a 64px icon strip, drawer collapses to width 0.
        open_binding = self._binding_metadata.get("open")
        open_initial = bool(self._reactive_values.get("open"))
        initial_open = "true" if open_initial else "false"
        if open_binding is not None:
            bound_open = True
            open_expr = open_binding.binding_path()
            data_open_expr = open_expr
        else:
            bound_open = False
            open_expr = "open"
            data_open_expr = "open"

        root_class = " ".join(
            p
            for p in (
                slots.get("root", ""),
                widths.get(width_key, ""),
                collapse.get(mode, ""),
            )
            if p
        )

        attrs = self.emit_attrs()
        attrs["class"] = root_class
        attrs.setdefault("role", "navigation")
        attrs.setdefault("aria-label", "Sidebar")
        # Marqueur stable, lu par ``ui.sidebar_trigger`` quand il n'a pas
        # pu résoudre d'id (une barre bâtie dans un AUTRE rendu que le
        # sien — un rafraîchissement de zone, par exemple). Même geste que
        # ``data-sidebar`` chez shadcn : un crochet nommé plutôt qu'un
        # sélecteur de balise, parce qu'une page a le droit d'avoir un
        # autre ``<aside>``.
        attrs.setdefault("data-bz-sidebar", "")
        # Static initial state + reactive override. Theme rules read
        # ``data-open`` (desktop expand/collapse).
        # Runtime quirk : ``bz-attr:attr="expr"`` REMOVES the attribute
        # when ``expr`` is boolean ``false`` (the boolean-HTML-attr
        # idiom — sensible for ``disabled`` / ``hidden`` / ``checked``,
        # disastrous for data-attrs since we want the literal string
        # ``"false"`` so CSS ``[data-open="false"]`` selectors match.
        # Force a string via ternary so the runtime always writes a
        # value.
        # ⚠️ En mode ``none``, ``data-open`` est FIGÉ à ``true``, et
        # l'attribut réactif n'est pas émis du tout.
        #
        # « none » veut dire : cette sidebar n'a pas d'état replié. Or le
        # repli se décide à DEUX endroits — la LARGEUR vient de la table
        # ``collapse`` (donc du mode), mais tout le reste (le logo qui se
        # centre, le libellé de section qui devient un filet, les labels
        # et les badges qui disparaissent) est gaté sur
        # ``md:group-data-[open=false]/sidebar:``, donc sur ``data-open``
        # SEUL. Deux clés pour une seule décision.
        #
        # Conséquence mesurée le 2026-08-15 :
        # ``ui.sidebar(collapsible="none", open=False)`` rendait une
        # sidebar PLEINE LARGEUR au contenu replié — logo centré, filet à
        # la place du titre de section, lignes réduites à leur icône. 12
        # règles enfants se déclenchaient pendant qu'aucune règle de
        # largeur ne le faisait.
        #
        # Figer l'attribut plutôt que d'aller gater les 12 règles sur le
        # mode : le mode dit qu'il n'y a pas d'état replié, donc l'état
        # replié ne doit simplement jamais pouvoir s'écrire. ``.toggle()``
        # sur une sidebar ``none`` devient un no-op, ce qui est le
        # contrat.
        if mode == "none":
            attrs["data-open"] = "true"
        else:
            attrs.setdefault("data-open", initial_open)
            attrs["bz-attr:data-open"] = bool_attr(data_open_expr)
        # ``data-collapse`` remplace ``data-variant`` : c'est le mode qui
        # est porté, et le nom suit la prop.
        attrs.setdefault("data-collapse", mode)

        # bz-data layout :
        #  - ``current_path`` : same path tracking as before, used by
        #    every SidebarItem to compute active-link state without a
        #    server round-trip on browser back/fwd.
        #  - ``open`` : present ONLY when no external binding drives
        #    the desktop state, so the chevron can flip something.
        # ``rail_tip`` / ``rail_tip_x`` / ``rail_tip_y`` alimentent le
        # panneau de tooltip PARTAGÉ du rail (cf. le slot ``rail_tip`` du
        # thème). Chaque SidebarItem y écrit son label et le rect de sa
        # ligne au survol ; le panneau se déplace au lieu d'exister en 62
        # exemplaires. Vide = rien de survolé, donc panneau masqué.
        rail_tip = "rail_tip: '', rail_tip_x: 0, rail_tip_y: 0"
        if bound_open:
            bz_data = current_path_scope(rail_tip)
        else:
            # ``open`` vit dans un signal de scope, donc ``scope.absorb``
            # le PRÉSERVE au morph (c'est voulu : un refresh voisin ne doit
            # pas refermer le menu qu'on vient d'ouvrir). Conséquence : sans
            # marker, un ``open=state.champ`` changé côté SERVEUR n'est
            # jamais ré-adopté — le menu resterait ouvert. D'où le
            # ``_serverSync``.
            sync = server_sync_marker(
                "open", enabled=self._value_server_backed("open")
            )
            # ⚠️ La virgule après ``{initial_open}`` est à l'APPELANT, et le
            # marqueur porte la SIENNE en fin — c'est le contrat documenté
            # sur ``server_sync_marker`` (« leading space + trailing comma »)
            # et la forme qu'utilisent Select/Slider/Combobox. En écrivant
            # ``{initial_open}{sync}, `` on produisait
            # ``open: true _serverSync: ['open'],,`` : littéral invalide,
            # donc TOUT le scope de l'aside échouait à parser — plus de
            # ``current_path`` (aucun surlignage actif), plus de ``open``
            # (le chevron mort) et plus de tooltip de rail. Silencieux côté
            # serveur, une seule SyntaxError console côté client. Le cas
            # n'apparaît que sur ``open=state.champ`` — aucun exemple du
            # dépôt n'en passait, d'où six mois de survie.
            bz_data = current_path_scope(
                f"open: {initial_open},{sync} {rail_tip}"
            )
        attrs.setdefault("bz-data", bz_data)
        # Resync ``current_path`` — partagé avec Navbar (le détail des
        # deux écoutes et du garde compare-puis-assigne est documenté sur
        # le helper).
        attrs.setdefault("bz-init", current_path_resync_init())
        # ⚠️ ``bz-init`` est DÉJÀ posé ci-dessus (resync ``current_path``).
        # Le mode overlay en veut un second (Escape) : on COMPOSE, on
        # n'écrase pas — c'est le piège « handler interne clobberé » de
        # traps.md, celui qui avait mangé on_focus/on_blur le 2026-07-18.
        _base_init = attrs["bz-init"]

        # ── Imperative API listeners ─────────────────────────────────
        # Wire ``bz-open`` / ``bz-close`` / ``bz-toggle`` on the root so
        # ``.open()`` / ``.close()`` / ``.toggle()`` work in both bound
        # and unbound modes (uniform contract). Bound mode : the
        # binding setter writes to ``open_expr`` directly, the event
        # arrives at this listener but the assignment is a no-op
        # because the binding has already settled the value. Cheap,
        # idempotent, simpler than gating. Shared with Dialog/Drawer/
        # Dropdown/Popover via the single-source helper (no drift).
        for _ev, _handler in imperative_listeners(open_expr).items():
            attrs.setdefault(_ev, _handler)

        # ── Câblage modal — mode ``overlay`` seulement ───────────────
        # Un menu de téléphone ouvert au-dessus du contenu doit se
        # fermer par Escape et ne pas laisser la page défiler derrière
        # lui. Les deux helpers viennent de ``base/_wiring`` — les MÊMES
        # que Dialog et Drawer — donc rien n'est réécrit ici et le
        # groupe ``overlay/`` n'est pas importé (anti-règle 5).
        #
        # Les modes de flux (rail / offcanvas) n'en veulent surtout pas :
        # replier un rail sur desktop ne doit ni voler la touche Escape
        # ni bloquer le scroll de la page.
        if is_overlay:
            attrs["bz-init"] = f"{_base_init}; {escape_init(open_expr)}"
            attrs["bz-effect"] = modal_root_effect(open_expr)

        # ── Children layout ──────────────────────────────────────────
        children: list[Any] = []
        # ⚠️ **Le chevron flottant auto a été RETIRÉ le 2026-08-21.** Il
        # se rendait quand la barre n'avait pas de ``SidebarTitle``, en
        # ``absolute top-2 right-2`` — c'est-à-dire très exactement sous
        # l'arête, qui prend les 24 px de droite sur toute la hauteur.
        # Mesuré par la gate : le clic n'arrivait plus jamais jusqu'à lui,
        # timeout de 30 s sur un bouton pourtant « visible, enabled and
        # stable ». Deux commandes au même endroit, dont une
        # inatteignable.
        #
        # Le décaler aurait été un pansement : l'arête fait le même
        # travail, dans les deux états, sur toute la hauteur — et sans
        # que le composant décide de la place d'une affordance de l'app,
        # ce que le commentaire ci-dessous reproche déjà à son
        # prédécesseur téléporté.
        # ── L'arête cliquable ────────────────────────────────────────
        # Elle vit ICI, sur la barre, et pas dans ``SidebarTitle`` : une
        # barre sans titre doit pouvoir se replier aussi, et c'est la
        # BORDURE de l'aside qu'on rend atteignable — un détail de la
        # barre, pas de son en-tête.
        #
        # Elle ne remplace pas le chevron : les deux coexistent, comme
        # chez shadcn, qui livre son rail EN PLUS d'un déclencheur
        # visible. Ce qu'elle remplace, c'est le seul geste qui n'existait
        # pas sur une machine sans survol.
        if mode != "none":
            children.append(_render_rail_edge(slots, open_expr))
        # ⚠️ Il n'y a plus de bouton de ré-ouverture auto-rendu. Il a
        # existé pour ``variant="drawer"`` : replié, la sidebar
        # disparaissait avec son chevron, donc le composant téléportait
        # sous ``<body>`` un hamburger flottant en dur (``top-3 left-3
        # z-50``). C'était le composant qui décidait de la place d'une
        # affordance de l'APP — et il en aurait fait un deuxième si l'app
        # avait déjà sa propre topbar. Le dev pose son bouton où il veut
        # et appelle ``sb.toggle()`` ; l'API impérative existe pour ça.
        # ⚠️ Le fond N'EST PLUS un enfant de l'aside, et surtout il n'est
        # plus téléporté — il devient un FRÈRE, sous une racine
        # ``display:contents`` (cf. la fin de ce ``render``). Voir le
        # commentaire là-bas : c'est la seule position d'où son ``z-40``
        # peut se comparer au ``z-50`` de l'aside.
        backdrop = _render_backdrop(theme, open_expr) if is_overlay else None

        # ── User children : pin header + footer, scroll the middle ───
        # The aside is a rigid ``flex-col h-screen`` frame ; it no longer
        # carries the scroll itself (it used to — ``overflow-y-auto`` on
        # the root — which scrolled the FOOTER away with an overflowing
        # nav list). So we partition the user children by type :
        #   • titre  → en-tête épinglé (``shrink-0``)
        #   • pied    → pied épinglé (``shrink-0``)
        #   • le reste → dans la box ``flex-1 min-h-0 overflow-y-auto``,
        #     la SEULE partie qui défile.
        #
        # ⚠️ **Le tri se fait sur le nœud RENDU, pas sur le type Python
        # de l'enfant** — et c'est la correction du 2026-08-23. La
        # version qui testait ``isinstance(child, SidebarFooter)`` ratait
        # tout pied ENVELOPPÉ : un ``@refreshable`` rend un
        # ``_RefreshableSection``, un ``ui.fragment`` rend un
        # ``Fragment``. Le pied tombait alors dans le milieu, donc DANS
        # la barre de défilement.
        #
        # Mesuré sur `examples/crm`, dont le pied est un
        # ``@refreshable(deps=[ViewerPrefs])`` — il faut bien qu'il se
        # rafraîchisse quand on change de compte : le bloc du compte
        # glissait de 656 à 504 px quand on faisait défiler la nav,
        # pendant qu'un pied nu ne bougeait pas d'un pixel. Le playground
        # n'a jamais montré le défaut parce que son pied n'est pas dans
        # une zone.
        #
        # Un nœud qui porte DEUX rôles, ou un rôle plus du contenu de
        # nav, reste au milieu : on ne peut pas épingler la moitié d'un
        # nœud, et le découper serait décider à la place de l'app.
        # We replicate ``_render_children``'s ``is_rendering`` bookkeeping
        # (sub-components built inside a ``render()`` skip parent-stack
        # registration) since we walk ``_children`` by hand to keep the
        # Python type for the partition.
        title_nodes: list[Any] = []
        middle_nodes: list[Any] = []
        footer_nodes: list[Any] = []
        ctx = maybe_current_context()
        prev_rendering = ctx.is_rendering if ctx is not None else None
        if ctx is not None:
            ctx.is_rendering = True
        try:
            for raw in getattr(self, "_children", []):
                # ``unwrap_transparent`` : sans lui, un pied ENVELOPPÉ —
                # et celui d'une vraie app l'est, il affiche le compte
                # connecté donc il doit se rafraîchir — n'est plus une
                # instance de ``SidebarFooter`` et tombe dans le milieu,
                # c'est-à-dire DANS la zone qui défile. Le rehabillage
                # rend son ``bz-id`` à la zone.
                child, rewrap = unwrap_transparent(raw)
                node = self._render_one(child)
                if node is None:
                    continue
                node = rewrap(node)
                if isinstance(child, SidebarTitle):
                    title_nodes.append(node)
                elif isinstance(child, SidebarFooter):
                    footer_nodes.append(node)
                else:
                    middle_nodes.append(node)
        finally:
            if ctx is not None:
                ctx.is_rendering = bool(prev_rendering)

        children.extend(title_nodes)
        if middle_nodes:
            children.append(
                Element(
                    tag="div",
                    attrs={"class": slots.get("scroll", "")},
                    children=tuple(middle_nodes),
                )
            )
        children.extend(footer_nodes)

        # Le panneau de tooltip PARTAGÉ du rail, dernier enfant de l'aside.
        # ``aria-hidden`` : il est purement décoratif — le nom accessible de
        # chaque entrée voyage sur son propre ``aria-label`` (cf.
        # ``SidebarItem.render``), ce qui est de toute façon la bonne a11y
        # pour un rail icon-only et ne dépend pas du survol.
        children.append(
            Element(
                tag="div",
                attrs={
                    # ``bz-c-text`` : le panneau du rail est un tooltip,
                    # donc il porte la teinte NEUTRE d'un tooltip et non
                    # la couleur de la barre. Son pont est posé ici parce
                    # qu'il diverge de celui de la racine.
                    "class": f'{slots.get("rail_tip", "")} bz-c-text'.strip(),
                    "role": "tooltip",
                    "aria-hidden": "true",
                    "data-tip": "off",
                    "bz-attr:data-tip": "rail_tip ? 'on' : 'off'",
                    "bz-attr:style": (
                        "'top:' + rail_tip_y + 'px;left:' + rail_tip_x + 'px'"
                    ),
                },
                children=(
                    # ⚠️ ``bz-text`` écrit ``textContent``, ce qui EFFACE
                    # les enfants du nœud. Il vit donc sur un ``<span>``
                    # intérieur, pas sur le panneau — sans quoi la flèche
                    # serait balayée au premier survol.
                    Element(
                        tag="span",
                        attrs={"bz-text": "rail_tip"},
                        children=(),
                    ),
                    Element(
                        tag="div",
                        attrs={"class": slots.get("rail_tip_arrow", "")},
                        children=(),
                    ),
                ),
            )
        )

        aside = Element(tag=self._tag, attrs=attrs, children=tuple(children))
        if backdrop is None:
            return aside

        # ── Mode overlay : le fond et l'aside doivent être FRÈRES ──────
        #
        # Un ``z-index`` ne se compare qu'entre frères de contexte
        # d'empilement — il ne traverse pas une frontière. Le fond a donc
        # vécu **téléporté sous ``<body>``** jusqu'au 2026-08-15, sur
        # l'hypothèse qu'il y serait « frère de la sidebar ». Il ne l'est
        # que si l'aside est lui aussi enfant direct de ``<body>``, ce
        # qu'aucun shell réel ne fait : le shell recommandé est
        # ``fixed inset-0`` (``traps.md``), et ``position: fixed`` CRÉE un
        # contexte. Le ``z-50`` de l'aside restait donc enfermé dedans, la
        # comparaison réelle devenait « shell (``z-auto``) contre fond
        # (``z-40``) », et le fond recouvrait toute l'app — sidebar
        # comprise, qu'il floutait avec son ``backdrop-filter``.
        #
        # ``display:contents`` (Tailwind ``contents``) est ce qui règle
        # ça : la racine ne génère AUCUNE boîte, donc aucun contexte
        # d'empilement, et ses deux enfants participent à celui du shell.
        # ``z-40`` et ``z-50`` s'y comparent enfin. C'est aussi la
        # structure de ``ui.dialog`` / ``ui.drawer``, qui n'ont jamais eu
        # le défaut parce qu'ils gardent leur paire au même endroit —
        # trois composants, une seule façon de faire (principe 4).
        #
        # Le ``classes=`` de l'appelant est recopié sur l'ASIDE : la wrap
        # universelle le poserait sur cette racine, où il serait inerte
        # (une boîte qui n'existe pas ne se style pas).
        # ⚠️ Le SCOPE remonte sur la racine — sans ça le fond ne voit plus
        # rien. Le runtime résout un ``bz-*`` en remontant jusqu'au plus
        # proche ancêtre porteur de ``bz-data`` ; un fond devenu FRÈRE de
        # l'aside n'a donc plus le scope au-dessus de lui, et son
        # ``bz-attr:data-open`` s'évalue dans le vide. Mesuré en le
        # livrant : le fond restait à ``data-open="true"`` sidebar fermée,
        # donc opaque et flou sur tout l'écran — exactement le symptôme
        # qu'on répare.
        #
        # L'aside continue de le voir : il descend de cette racine, donc
        # la remontée le trouve. Un seul scope, deux consommateurs.
        # L'IDENTITÉ du composant suit le scope sur la racine — ``id``
        # compris, et avec lui les écouteurs impératifs.
        #
        # ⚠️ Ne PAS laisser l'``id`` sur l'aside : le socle estampille
        # ``id`` + ``bz-id`` sur toute racine qui porte un ``bz-data`` et
        # n'a pas encore d'``id`` (``_stamp_scope_id``). Le wrapper en
        # recevait donc un — le MÊME que l'aside. Deux nœuds, un seul id :
        # ``document.getElementById`` renvoie le premier, c'est-à-dire le
        # wrapper, et l'API impérative dispatchait ``bz-toggle`` sur un
        # nœud sans écouteur. Mesuré : le hamburger ne faisait plus rien,
        # en silence, alors que l'état et le rendu étaient corrects.
        #
        # Les trois ``bz-on:bz-*`` migrent donc avec l'``id`` qu'ils
        # servent. Le reste (``bz-init``, ``bz-effect``,
        # ``bz-attr:data-open``) reste sur l'aside : ça décrit l'aside,
        # et la résolution de scope remonte jusqu'ici de toute façon.
        aside_attrs = dict(aside.attrs)
        root_attrs: dict[str, Any] = {"class": "contents"}
        for key in (
            "bz-data",
            "bz-id",
            "id",
            "bz-on:bz-open",
            "bz-on:bz-close",
            "bz-on:bz-toggle",
        ):
            if key in aside_attrs:
                root_attrs[key] = aside_attrs.pop(key)

        # Le ``classes=`` de l'appelant est recopié sur l'ASIDE : la wrap
        # universelle le poserait sur cette racine, où il serait inerte
        # (une boîte qui n'existe pas ne se style pas).
        user_cls = self._user_classes_str()
        if user_cls:
            aside_attrs["class"] = (
                f"{aside_attrs.get('class', '')} {user_cls}".strip()
            )

        aside = Element(
            tag=aside.tag, attrs=aside_attrs, children=aside.children
        )
        return Element(tag="div", attrs=root_attrs, children=(backdrop, aside))


# ───────────────────────────────────────────────────────────────────────────
# SidebarTrigger — le bouton qui la rouvre, pose par l'app
# ───────────────────────────────────────────────────────────────────────────


class SidebarTrigger(Component):
    """Render a button that opens or closes a sidebar."""

    THEME: ClassVar[dict[str, Any]] = SIDEBAR_THEME
    THEME_KEY: ClassVar[str] = "sidebar"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    #: ``panel-left`` et pas ``menu`` : c'est le glyphe que lucide,
    #: shadcn et VS Code associent a « barre laterale », donc il dit CE
    #: QU'IL OUVRE. C'est aussi celui que porte deja le chevron du
    #: :class:`SidebarTitle` — les deux commandes se ressemblent parce
    #: qu'elles font la meme chose.
    icon: str | Component = reactive_prop(
        default="panel-left", emit_attr=False
    )
    #: La densité de la barre où il est posé — une barre du haut compacte
    #: veut ``sm``. C'est le seul axe qui varie DANS une même app.
    size: str = reactive_prop(default="md", emit_attr=False)

    # Deux axes coupés sur le test décisif de la règle d'opinionation :
    # « aurait-on ce composant sous deux formes dans la MÊME app ? ».
    # Non — une app a un déclencheur de barre latérale, et il ressemble
    # au reste de sa barre du haut. ``icon=`` survit au même test parce
    # que le désaccord est réel et mesurable : ce dépôt écrit ``menu``
    # dans ``examples/crm`` et ``panel-left`` dans ``examples/chat``.
    #
    # ⚠️ Le garde n'est pas de la politesse — même raison que
    # ``bottom_bar._CUT``, dont ceci est la copie : sans lui, le socle
    # absorbe le kwarg inconnu dans les attrs bruts, et
    # ``ui.sidebar_trigger(variant="solid")`` émettrait un attribut HTML
    # ``variant="solid"`` **en silence**, sans rien changer au rendu.
    _CUT: ClassVar[dict[str, str]] = {
        "variant": (
            "le look du bouton se décide une fois par app, avec le reste "
            "de sa barre du haut : c'est une décision de thème"
        ),
        "color": (
            "idem — et `classes=` reste là pour le cas unique. Si tu veux "
            "vraiment un bouton à toi, l'échappatoire tier 2 est entière : "
            "`ui.icon_button(…, on_click=sb.toggle())`"
        ),
    }

    def __init__(
        self,
        sidebar: Any = None,
        *,
        icon: str | Component | None = None,
        size: str | None = None,
        **kwargs: Any,
    ) -> None:
        for name, why in self._CUT.items():
            if name in kwargs:
                raise ComponentUsageError(
                    f"ui.sidebar_trigger n'a pas de `{name}=` : {why}."
                )
        super().__init__(icon=icon, size=size, **kwargs)
        self._sidebar: Any = None
        #: Le repli : viser le marqueur stable et resoudre au CLIC.
        #: Remplace par la commande par id des qu'une barre est connue.
        self._command: str = TOGGLE_NEAREST_SIDEBAR
        if sidebar is not None:
            self.bind_sidebar(sidebar)
        else:
            # Resolu par ``base/_wiring.wire_sidebar_triggers`` une fois
            # l'arbre bati — l'ordre d'ecriture ne doit pas decider si
            # le bouton marche.
            ctx = maybe_current_context()
            if ctx is not None:
                ctx.sidebar_triggers.append(self)

    def bind_sidebar(self, sidebar: Any) -> None:
        """Attacher ce declencheur a *sidebar*.

        Appele soit a la construction (``ui.sidebar_trigger(sb)``), soit
        par la passe de resolution. Passer par ``sidebar.toggle()``
        n'est pas un detail : c'est ce qui marque la barre comme
        pilotable, donc ce qui fait taire
        :func:`check_sidebars_are_reachable`. Les deux tiers de l'API
        empruntent le meme chemin.
        """
        self._sidebar = sidebar
        self._command = sidebar.toggle()

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        button = IconButton(
            self._reactive_values.get("icon") or "panel-left",
            variant="ghost",
            size=self._reactive_values.get("size") or "md",
            color="muted",
            aria_label=text("sidebar.toggle"),
            on_click=self._command,
        )
        Component._detach_from_parent(button)
        node = button.render()
        attrs = dict(node.attrs)
        # Les kwargs universels (``classes=``, ``id=``, ``visible=``,
        # ``tooltip=``...) sont resolus par le socle sur CE composant :
        # on les reverse sur le bouton reellement rendu, sinon ils
        # tomberaient dans le vide — le mode d'echec silencieux que
        # ``_apply_universal_modifiers`` documente.
        mine = self.emit_attrs()
        classes = " ".join(
            c for c in (attrs.get("class", ""), mine.pop("class", "")) if c
        )
        attrs.update(mine)
        if classes:
            attrs["class"] = classes
        if self._sidebar is not None:
            # Ce que l'echappatoire tier 2 ne fera jamais a la main.
            attrs["aria-controls"] = self._sidebar.id
        return Element(tag=node.tag, attrs=attrs, children=node.children)


# ───────────────────────────────────────────────────────────────────────────
# SidebarSection — optional grouping with a label
# ───────────────────────────────────────────────────────────────────────────


class SidebarSection(Component):
    """Group of items with an optional uppercase label."""

    THEME: ClassVar[dict[str, Any]] = SIDEBAR_THEME
    THEME_KEY: ClassVar[str] = "sidebar"
    # ``None`` désactive la vérification, donc un binding sur ``label``
    # était accepté puis jeté en silence. ``()`` rend le refus explicite.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    label: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        *,
        label: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le défaut).
        super().__init__(label=label, **kwargs)

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        label = self._reactive_values.get("label")

        attrs = self.emit_attrs()
        attrs["class"] = slots.get("section", "")

        children = list(self._render_children())
        if label:
            # Rail divider — the collapsed-rail form of the label. The
            # uppercase caption (``section_label``) hides at md+ collapse ;
            # in its place we drop a real :class:`~bretzel.components.
            # primitives.divider.Divider` (dogfooding — a primitive, so
            # importable here per anti-règle 5), so the caption visually
            # turns into a separator line. Only labelled sections get it :
            # an unlabelled group has no caption to collapse.
            #
            # The Divider's own root is ``flex`` ; ``hidden`` can't reliably
            # override a hardcoded ``flex`` (Tailwind orders ``display``
            # utilities by source, not class-attr order). So the rail-only
            # gate rides a PLAIN wrapper div (no base ``display``), and the
            # Divider sits inside it untouched.
            divider = Divider(color="muted")
            Component._detach_from_parent(divider)
            # Build the header in DOM order — label first, divider second —
            # then prepend it (only one of the two is ever visible : the
            # label when expanded, the divider in the rail).
            header = [
                Element(
                    tag="div",
                    attrs={"class": slots.get("section_label", "")},
                    children=(self.emit_text_slot(label),),
                ),
                Element(
                    tag="div",
                    attrs={"class": slots.get("section_divider", "")},
                    children=(divider.render(),),
                ),
            ]
            children = header + children

        return Element(tag=self._tag, attrs=attrs, children=tuple(children))


# ───────────────────────────────────────────────────────────────────────────
# SidebarTitle — the header : logo + title + collapse toggle
# ───────────────────────────────────────────────────────────────────────────


class SidebarTitle(Component):
    """Render the sidebar title and optional home link."""

    THEME: ClassVar[dict[str, Any]] = SIDEBAR_THEME
    THEME_KEY: ClassVar[str] = "sidebar"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    title: str = reactive_prop(default="", emit_attr=False)
    #: ⚠️ Le défaut est un GLYPHE, pas ``None`` — même motif que
    #: ``ui.datatable(empty_icon="inbox")``. Sans lui, un titre écrit sans
    #: ``icon=`` laissait la tête de rail vide, et un rail replié montrait
    #: un trou au-dessus de ses items (signalé à l'écran le 2026-09-12).
    #: ``home`` et pas autre chose : ce lien mène à ``href=``, dont le
    #: défaut est ``/``. Le glyphe décrit donc ce que le lien FAIT.
    #:
    #: **Pour n'avoir aucune marque : ``icon=""``.** Pas ``icon=None`` —
    #: le socle drope les kwargs réactifs à ``None`` pour garder le
    #: défaut, donc un ``None`` explicite est indistinguable d'un
    #: argument absent (vérifié). La chaîne vide, elle, arrive jusqu'ici.
    icon: str | Component | None = reactive_prop(default="home", emit_attr=False)
    href: str = reactive_prop(default="/", emit_attr=False, never_code=True)

    def __init__(
        self,
        title: str = "",
        *,
        icon: str | Component | None = "home",
        href: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le défaut).
        super().__init__(title=title, icon=icon, href=href, **kwargs)
        # (A ``ui.icon(...)`` passed as ``icon=`` is detached from the parent
        # by ``Component.__init__`` now — the systemic fix for the "component
        # passed as a prop renders twice" class, cf. traps.md.)

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        # PAS de ``str(...)`` : ``title`` est un slot textuel, donc il
        # peut porter un Component — le coercer ici expédiait son repr
        # Python dans la page (``emit_text_slot`` fait le tri en aval).
        title = self._reactive_values.get("title") or ""
        # ``icon`` accepts a bare name ("zap") OR a built ``ui.icon(...)``.
        # We read its NAME (the title sizes the glyph uniformly) and its
        # COLOUR : a bare string gets the brand ``primary`` ; a passed
        # ``ui.icon(...)`` keeps its OWN colour (default "current" = inherit
        # the brand link) so ``ui.icon("zap", color="warning")`` shows orange.
        icon_arg = self._reactive_values.get("icon")
        icon_name = _icon_name(icon_arg)
        icon_color = (
            (getattr(icon_arg, "color", None) or "current")
            if isinstance(icon_arg, Component)
            else "primary"
        )
        # Le PALIER **plus le pont de l'icône**, et les deux sont
        # nécessaires : la couleur de l'icône peut différer de celle de
        # l'en-tête (``ui.icon("zap", color="warning")`` dans une barre
        # ``primary``), donc le pont que le socle a posé sur la racine ne
        # convient pas. On en pose un sur le glyphe lui-même.
        #
        # ``current`` est un pont comme un autre : ``bz-c-current`` fait
        # partir ``--bz-text`` de ``currentColor``, donc l'icône hérite
        # du lien de marque — le comportement d'avant, à l'identique.
        from bretzel.theme.bridges import bridge_class

        icon_text_class = f"text-(--bz-text) {bridge_class(icon_color)}"
        href = str(self._reactive_values.get("href") or "/")

        def _glyph(name: str, cls: str) -> Element:
            return Element(
                tag="iconify-icon",
                attrs={"icon": _iconify_ref(name), "class": cls},
                children=(),
            )

        # ── In-sidebar header : brand link + collapse chevron ────────
        brand_children: list[Any] = []
        if icon_name:
            brand_children.append(
                _glyph(icon_name, f"{slots.get('title_logo', '')} {icon_text_class}")
            )
        if title:
            brand_children.append(
                Element(
                    tag="span",
                    attrs={"class": slots.get("title_text", "")},
                    children=(self.emit_text_slot(title),),
                )
            )
        brand = Element(
            tag="a",
            attrs={"href": href, "class": slots.get("title_brand", "")},
            children=tuple(brand_children),
        )
        # Collapse toggle — a real IconButton (hover / a11y). ``Icon(size="lg")``
        # = ``text-2xl`` = glyphe 24 px (comme le logo et le titre), dans un
        # IconButton ``size="md"`` = boîte ``h-10 w-10``. Le lockup d'en-tête
        # ne change donc pas de taille au repli. Bubbling ``bz-toggle`` —
        # caught by the Sidebar root's ``bz-on:bz-toggle``.
        #
        # ⚠️ Ce commentaire affirmait « Sized to MATCH the rail toggle
        # exactly » et renvoyait à un slot ``title_rail_toggle``. Ni le slot
        # ni ce second bouton n'existent : le chevron flottant auto a été
        # retiré le 2026-08-21, et le slot ``toggle`` qui l'habillait est
        # parti avec le 2026-08-29 — plus personne ne le lisait.
        # ``panel-left`` et non un chevron : c'est le glyphe que tout le
        # monde associe à « barre latérale » (lucide, shadcn, VS Code),
        # donc il dit CE QU'IL REPLIE. Un chevron ne dit qu'une
        # direction, et il en existe déjà quatre autres dans le
        # catalogue qui veulent dire autre chose.
        toggle = IconButton(
            Icon("panel-left", size="lg"),
            variant="ghost",
            size="md",
            color="muted",
            aria_label=text("sidebar.toggle"),
            on_click=(
                "$el.dispatchEvent(new CustomEvent("
                "'bz-toggle', {bubbles: true}))"
            ),
            classes=slots.get("title_toggle", ""),
        )
        Component._detach_from_parent(toggle)
        toggle_node = toggle.render()

        # ── Le logo du rail : un LIEN, pas un bouton de repli ────────
        # Il portait le logo et se changeait en chevron au survol ; le
        # clic repliait. Deux défauts d'un coup : sur une machine sans
        # survol rien n'annonçait le geste (le logo restait un logo), et
        # le logo changeait de métier selon l'état de la barre — lien
        # dépliée, bouton repliée.
        #
        # Le repli a maintenant son ARÊTE (``Sidebar._render_rail_edge``),
        # visible dans les deux états, donc le logo n'a plus qu'un métier :
        # mener à ``href=``.
        # ⚠️ **Pas de marque de rail SANS glyphe.** Un ``<a>`` sans enfant
        # n'est pas « invisible » : mesuré le 2026-09-12 sur un rail
        # replié, il occupe **40 × 40 px** en tête de barre et prend le
        # PREMIER focus — la première tabulation atterrit sur un lien
        # qu'on ne voit pas. Même famille que l'overlay fermé qui gardait
        # ses commandes joignables (``traps.md`` § A11y).
        #
        # Signalé par l'utilisateur, qui voyait le trou : « tu n'as pas
        # mis de logo, et maintenant on voit un espace vide ». Sans
        # glyphe, le rail commence donc à ses items — il se remplit
        # entièrement, ce qu'il proposait — et l'affordance de
        # ré-ouverture reste l'ARÊTE (``_render_rail_edge``), qui est
        # visible dans les deux états.
        rail_brand = Element(
            tag="a",
            attrs={
                "href": href,
                "class": slots.get("title_rail_brand", ""),
                # Le titre disparaît dans le rail, donc le lien n'a plus
                # que son glyphe : sans nom accessible il s'annonce
                # « lien » et rien d'autre. C'est la classe que
                # ``test_icon_only_controls_are_named`` garde depuis le
                # finding 18.
                #
                # Seulement une CHAÎNE, comme ``ui.icon_button`` le fait
                # avec son ``tooltip=`` : un ``title=ui.text(...)`` est du
                # contenu riche, et aplatir un arbre en étiquette
                # produirait une phrase que personne n'a écrite.
                "aria-label": (
                    title.strip() if isinstance(title, str) and title.strip()
                    else text("sidebar.home")
                ),
            },
            children=(
                _glyph(
                    icon_name,
                    f"text-2xl {icon_text_class}",
                ),
            ) if icon_name else (),
        )

        attrs = self.emit_attrs()
        attrs["class"] = slots.get("title_root", "")

        children: list[Any] = [brand, toggle_node]
        if icon_name:
            children.append(rail_brand)

        return Element(tag=self._tag, attrs=attrs, children=tuple(children))


# ───────────────────────────────────────────────────────────────────────────
# SidebarItem — the nav row primitive
# ───────────────────────────────────────────────────────────────────────────


class SidebarItem(Component):
    """One nav row : icon + label + optional badge."""

    THEME: ClassVar[dict[str, Any]] = SIDEBAR_ITEM_THEME
    THEME_KEY: ClassVar[str] = "sidebar_item"
    IS_CONTAINER: ClassVar[bool] = False
    EVENTS: ClassVar[tuple[str, ...]] = ("click",)
    NAMED_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    ICON_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    # Curated reactive surface — active state (current_path derived
    # at runtime, see sidebar __init__) + badge content + disabled.
    # label and href are design-time (routes don't change live).
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("active", "badge", "disabled")

    label: str = reactive_prop(default="", emit_attr=False)
    href: str | None = reactive_prop(default=None, emit_attr=False, never_code=True)
    active: Any = reactive_prop(default=None, emit_attr=False)
    badge: Any = reactive_prop(default=None, emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)

    def __init__(
        self,
        label: str = "",
        *,
        icon: Any = None,
        href: str | None = None,
        active: Any = None,
        badge: Any = None,
        disabled: bool | None = None,
        color: str | None = None,
        on_click: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le défaut).
        super().__init__(
            label=label,
            href=href,
            active=active,
            badge=badge,
            disabled=disabled,
            color=color,
            icon=icon,
            on_click=on_click,
            **kwargs,
        )

        # Capture the enclosing layout name at construction time —
        # the ``with @layout(): ...`` block is still active so
        # ``ctx.layout_stack`` is populated. We need this for the
        # ``hx-target`` attribute baked at render time.
        self._captured_layout: str | None = capture_layout()

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})

        # Lecture + câblage : le corps partagé des trois items de nav
        # (navigation/_wiring.py). Ce qui suit est propre à la sidebar.
        w = wire_nav_item(self, slots)
        tag, attrs = w.tag, w.attrs
        label, href, disabled = w.label, w.href, w.disabled
        badge_value, badge_binding = w.badge_value, w.badge_binding

        # Extra propre à la sidebar : au montage, si l'item résout à actif
        # (refresh profond dans une liste de 50+ entrées), le ramener dans le
        # viewport. ``block: 'nearest'`` est un no-op quand il est déjà
        # visible — le cas courant — et ne pousse que le minimum sinon.
        # Différé via ``$nextTick`` pour que le runtime ait appliqué
        # ``bz-attr:data-active`` avant qu'on le lise.
        #
        # Posé APRÈS les trois ``apply_*`` (avant, il vivait entre le
        # partial-nav et le disabled) : ``apply_disabled`` ne retire que les
        # canaux de clic, jamais le ``bz-init``, donc le résultat est le même.
        if href and self._captured_layout and not is_external_href(href):
            attrs.setdefault(
                "bz-init",
                "$nextTick(() => { if ($el.dataset.active === 'true') "
                "$el.scrollIntoView({ block: 'nearest' }); })",
            )

        # In the collapsed rail the label is ``hidden`` (icon-only square),
        # so we bring the name back on hover — via the ONE shared panel the
        # Sidebar renders (slot ``rail_tip``), which this row moves onto
        # itself. Disabled rows are skipped : ``pointer-events-none`` /
        # ``tabindex=-1`` already make them unhoverable / unfocusable.
        #
        # ⚠️ ``isinstance(label, str)`` discrimine Component-vs-string, et
        # RIEN D'AUTRE : une binding n'arrive jamais jusqu'ici, parce que
        # ``Component.__init__`` range ``binding.value`` — une string —
        # dans ``_reactive_values``, d'où ``wire_nav_item`` lit ce label.
        #
        # ``label`` est un slot textuel, il accepte donc un Component. Le
        # tooltip du rail, lui, n'a que des cibles STRING — il part dans un
        # ``aria-label`` et dans le littéral JS de ``rail_tip = "…"``, que
        # ``json.dumps`` refuse. La ligne garde son contenu riche ; le
        # tooltip du rail se tait, comme pour une entrée sans libellé.
        show_rail_tip = isinstance(label, str) and bool(label) and not disabled

        # ── Children : icon + label + badge ──────────────────────────
        children: list[Any] = []
        icon = self._slot_components.get("icon")
        if isinstance(icon, Component):
            Component._detach_from_parent(icon)
            children.append(Component.with_slot_class(
                icon.render(), slots.get("icon", ""),
            ))

        if label:
            children.append(
                Element(
                    tag="span",
                    attrs={"class": slots.get("label", "")},
                    children=(self.emit_text_slot(label),),
                )
            )

        # ── Badge — reactive when bound, static otherwise ────────────
        # ``badge`` is in BINDABLE_PROPS, so a ClientBinding must emit a
        # live directive — not silently degrade to the static SSR snapshot.
        # The badge holds CONTENT (a count / short label), so the live
        # channel is ``bz-text`` (the pill's textContent tracks the bound
        # value), paired with ``bz-show`` so the pill hides when the value
        # goes empty/null — mirroring the static ``is not None`` gate.
        if badge_binding is not None:
            children.append(render_badge(
                badge_value, slots.get("badge", ""),
                reactive_path=self.path_of(badge_binding),
            ))
        elif badge_value is not None:
            children.append(render_badge(badge_value, slots.get("badge", "")))

        # ── Rail tooltip : alimenter le panneau PARTAGÉ de la sidebar ──
        # On n'instancie plus un ``ui.tooltip`` par entrée (62 panneaux
        # pré-rendus = 94 ko, un tiers de la sidebar, pour une affordance
        # qui n'en montre jamais qu'un). L'entrée se contente d'écrire son
        # label et sa position dans le scope de l'aside ; le panneau unique
        # s'y déplace. Le gate « rail replié + desktop » est en CSS sur le
        # panneau, donc il n'y a plus de ``matchMedia`` ni de
        # ``closest('aside')`` recopiés 62 fois.
        #
        # ``aria-label`` porte le nom accessible sur le lien lui-même :
        # dans le rail le libellé visible est ``hidden``, et un tooltip au
        # survol n'est pas une affordance clavier/lecteur d'écran. C'est
        # donc à la fois plus juste qu'avant et indépendant du panneau.
        if show_rail_tip:
            attrs.setdefault("aria-label", label)
            # X sur le bord du RAIL, pas sur celui de l'entrée : replié,
            # l'entrée est un carré ``w-10`` centré (``mx-auto``) dans un
            # rail de 64 px, donc son bord droit tombe 4 px À L'INTÉRIEUR
            # du rail et le panneau le chevauchait (probe, 2026-07-27).
            # Y sur le centre de l'entrée ; le décalage de moitié est fait
            # en CSS (``-translate-y-1/2``), pas avec une hauteur devinée.
            enter = (
                f"rail_tip = {json.dumps(label)}; "
                "rail_tip_x = $el.closest('aside')"
                ".getBoundingClientRect().right + 8; "
                "(r => { rail_tip_y = r.top + r.height / 2 })"
                "($el.getBoundingClientRect())"
            )
            # Composer, pas écraser : un ``on_mouseenter=`` utilisateur est
            # déjà posé dans ``attrs`` par ``emit_attrs``. L'écraser est le
            # piège « handler interne clobberé » de traps.md (passe
            # on_focus/on_blur, 2026-07-18).
            for event, internal in (
                ("bz-on:mouseenter", enter),
                ("bz-on:mouseleave", "rail_tip = ''"),
                ("bz-on:focus", enter),
                ("bz-on:blur", "rail_tip = ''"),
            ):
                existing = attrs.get(event)
                attrs[event] = f"{existing}; {internal}" if existing else internal

        node = Element(tag=tag, attrs=attrs, children=tuple(children))

        return node


# ───────────────────────────────────────────────────────────────────────────
# SidebarFooter — account row + popover menu, pinned to the bottom
# ───────────────────────────────────────────────────────────────────────────


def _footer_initials(name: Any) -> str:
    """Derive up-to-2-char initials from a display name ("Jean Hoccart"
    → "JH", "Jean" → "JE"). Falls back to "?" for an empty name.

    ``name`` est un slot textuel, donc il porte aussi un Component — dont
    aucune initiale ne se dérive (``.split()`` lèverait). Le repli est la
    même pastille « ? » que pour un nom vide, décidé ICI pour que ce
    littéral ait un seul propriétaire. Une binding, elle, arrive déjà
    résolue en string : ``Component.__init__`` range ``binding.value``
    dans ``_reactive_values``."""
    parts = [p for p in name.split() if p] if isinstance(name, str) else []
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


class SidebarFooter(Component):
    """Render the footer region of a sidebar."""

    THEME: ClassVar[dict[str, Any]] = SIDEBAR_FOOTER_THEME
    THEME_KEY: ClassVar[str] = "sidebar_footer"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    name: str = reactive_prop(default="", emit_attr=False)
    subtitle: str | None = reactive_prop(default=None, emit_attr=False)
    # ``never_code`` : la forme string est une URL d'image — même famille
    # que ``ui.avatar(src=)``, donc même exposition au faux positif.
    avatar: str | Component | None = reactive_prop(
        default=None, emit_attr=False, never_code=True
    )
    # Colour axis — tints the avatar chip + focus ring. Posée par la
    # classe-pont ``bz-c-<couleur>`` sur la racine, qui installe les onze
    # paliers sur le sous-arbre (cf. ``color_bridge_class``) ; le thème
    # écrit des classes COMPLÈTES comme ``bg-(--bz-bg)``. Ce commentaire
    # a dit « via ``{bg_color}`` in the theme » jusqu'au 2026-09-07,
    # c'est-à-dire le mécanisme d'AVANT le pont.
    # Defaults to ``primary`` like every other Bretzel component
    # (Button / Avatar / SidebarItem …).
    color: str = reactive_prop(default="primary", emit_attr=False)

    def __init__(
        self,
        name: str = "",
        *,
        subtitle: str | None = None,
        avatar: str | Component | None = None,
        color: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le défaut).
        super().__init__(
            name=name,
            subtitle=subtitle,
            avatar=avatar,
            color=color,
            **kwargs,
        )

    def _render_avatar(self, avatar: Any, name: Any, avatar_cls: str) -> Element:
        if isinstance(avatar, Component):
            # A passed ``ui.avatar(...)`` carries its OWN size/shape/colour
            # (and is already detached by ``Component.__init__``) — render it
            # as-is, don't double-wrap it in the initials-chip styling.
            return Element(
                tag="span", attrs={"class": "shrink-0 inline-flex"},
                children=(avatar.render(),),
            )
        # ``avatar`` is now ``str | None`` (the Component case returned
        # above) : use it as initials text if given, else derive from name
        # (``_footer_initials`` possède le repli pour un nom non-textuel).
        text = avatar or _footer_initials(name)
        return Element(
            tag="span", attrs={"class": avatar_cls},
            children=(TextNode(text),),
        )

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        # Idem ``title`` ci-dessus : slot textuel, pas de coercition.
        name = self._reactive_values.get("name") or ""
        subtitle = self._reactive_values.get("subtitle")
        avatar = self._reactive_values.get("avatar")
        open_expr = "acct_open"

        # ── Trigger row ──────────────────────────────────────────────
        avatar_node = self._render_avatar(
            avatar, name, slots.get("avatar", "")
        )

        # ⚠️ ``emit_text_slot`` renvoie ``None`` pour un slot VIDE, et un
        # ``None`` dans ``children`` fait lever le sérialiseur (« Cannot
        # serialize unknown Node type »). Le span du nom est le seul des
        # six slots de ce fichier à n'être gardé par aucun ``if`` — un
        # ``ui.sidebar_footer()`` sans nom est légal, et il rendait un
        # span vide avant. On garde ce comportement.
        name_node = self.emit_text_slot(name)
        meta_children: list[Any] = [
            Element(
                tag="span", attrs={"class": slots.get("name", "")},
                children=(name_node,) if name_node is not None else (),
            )
        ]
        if subtitle:
            meta_children.append(
                Element(
                    tag="span", attrs={"class": slots.get("subtitle", "")},
                    children=(self.emit_text_slot(subtitle),),
                )
            )
        meta = Element(
            tag="div", attrs={"class": slots.get("meta", "")},
            children=tuple(meta_children),
        )

        # Up/down chevron — Icon primitive (font-size sized, centered).
        chevron = Icon(
            "chevrons-up-down", size="sm", color="muted",
            classes=slots.get("chevron", ""),
        )
        Component._detach_from_parent(chevron)

        trigger = Element(
            tag="button",
            attrs={
                "type": "button",
                "class": slots.get("trigger", ""),
                "bz-ref": "bztrigger",
                "bz-on:click": f"{open_expr} = !{open_expr}",
                "aria-haspopup": "menu",
                "bz-attr:aria-expanded": bool_attr(f"{open_expr}"),
                # Persistent SELECTED state while the popover is open (the
                # theme reads ``data-[menu-open=true]``). Stringified ternary
                # so bz-attr never drops the attr (cf. data-open quirk).
                "data-menu-open": "false",
                "bz-attr:data-menu-open": bool_attr(open_expr),
            },
            children=(avatar_node, meta, chevron.render()),
        )

        # ── Popover panel (the children) ─────────────────────────────
        # Shared anchored-overlay wiring (same as Dropdown/Popover) :
        # toggles display + attaches ``$bz.helpers.floating`` (→
        # position:fixed, escapes the sidebar overflow), anchored on the
        # trigger box. ``auto`` = best-fit : the footer sits at the bottom
        # so there's no room below → it opens UPWARD in the expanded
        # sidebar, and adapts on its own in the collapsed rail.
        panel_attrs: dict[str, Any] = {
            "class": slots.get("panel", ""),
            "role": "menu",
            # ``bzpanel`` ref : the teleport moves the panel out of the
            # root's subtree, so click-outside checks it as "inside".
            "bz-ref": "bzpanel",
            "bz-effect": anchored_panel_effect(open_expr, "auto"),
            # DropdownItem children dispatch ``bz-dropdown-pick`` on click
            # → close the menu after the action runs.
            "bz-on:bz-dropdown-pick": f"{open_expr} = false",
        }
        stamp_display_none(panel_attrs)  # hidden until opened (no FOUC)
        panel = Element(
            tag="div", attrs=panel_attrs,
            children=tuple(self._render_children()),
        )

        # ── Root ─────────────────────────────────────────────────────
        attrs = self.emit_attrs()
        attrs["class"] = self.compose_class("root")
        # Local open flag + Escape / click-outside dismiss (shared wiring).
        # clickOutside targets the root (trigger + panel), so clicking the
        # trigger never counts as "outside".
        attrs.setdefault("bz-data", f"{{{open_expr}: false}}")
        attrs["bz-init"] = anchored_dismiss_init(open_expr)
        # Panel teleports to <body> — the footer sits inside the sidebar's
        # overflow + stacking context, which would clip / hide an inline
        # panel (cf. traps.md ; see ``teleport_to_body``).
        return Element(
            tag=self._tag,
            attrs=attrs,
            children=(trigger, teleport_to_body(panel, self)),
        )


class SidebarFooterItem(MenuItem):
    """A clickable row inside a :class:`SidebarFooter` popover.

    Exactly the API of ``ui.dropdown_item`` — ``label`` / ``icon_left`` /
    ``icon_right`` / ``shortcut`` / ``href`` / ``color`` / ``disabled`` /
    ``on_click`` — because the row logic lives in the shared
    :class:`~bretzel.components.primitives.menu_item.MenuItem`. This shell
    only binds the footer-item theme. On click it dispatches
    ``bz-dropdown-pick``, which the footer popover catches to close ::

        with ui.sidebar_footer(name="Jean", subtitle="jean@acme.com"):
            ui.sidebar_footer_item(label="Settings", icon_left="settings",
                                   href="/me")
            ui.sidebar_footer_item(label="Log out", icon_left="log-out",
                                   color="error", on_click=auth.logout())
    """

    THEME: ClassVar[dict[str, Any]] = SIDEBAR_FOOTER_ITEM_THEME
    THEME_KEY: ClassVar[str] = "sidebar_footer_item"


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────


def _render_backdrop(theme: dict, open_expr: str) -> Element:
    """Le fond assombri du mode ``overlay`` — FRÈRE de l'aside.

    ⚠️ Il a été **téléporté sous ``<body>``** jusqu'au 2026-08-15, sur ce
    raisonnement écrit ici même : « l'aside est lui-même ``fixed z-50``,
    donc un enfant vivrait au-dessus de lui ; sous ``<body>`` il est un
    frère, et son ``z-40`` le range derrière la sidebar ». La première
    moitié est juste, la seconde est **fausse** : il n'est frère de
    l'aside que si l'aside est lui aussi enfant direct de ``<body>``, ce
    qu'aucun shell réel ne fait. Un ``z-index`` ne se compare qu'entre
    frères de contexte d'empilement, et le shell recommandé
    (``fixed inset-0``) en crée un. Le fond recouvrait donc la sidebar et
    la floutait — signalé à l'écran, puis mesuré.

    La sortie n'était ni « enfant » ni « sous body » mais une TROISIÈME
    position : frère, sous une racine ``display:contents`` qui ne génère
    aucune boîte donc aucun contexte (cf. ``Sidebar.render``). C'est la
    structure de ``ui.dialog`` / ``ui.drawer``, qui n'ont jamais eu le
    défaut. Gate : ``tests/runtime_js/test_backdrop_never_covers_its_panel.py``.

    Il porte ``data-open`` en miroir (le thème lit
    ``data-[open=false]:opacity-0`` + ``pointer-events-none``, donc
    fermé il est à la fois invisible ET traversable), et un clic le
    ferme — l'affordance que tout le monde attend d'un menu de
    téléphone. ``aria-hidden`` : il est décoratif, la fermeture au
    clavier passe par Escape.
    """
    node = Element(
        tag="div",
        attrs={
            "class": theme.get("backdrop", ""),
            "aria-hidden": "true",
            "data-open": "false",
            "bz-attr:data-open": bool_attr(open_expr),
            "bz-on:click": f"{open_expr} = false",
        },
        children=(),
    )
    return node


def _render_rail_edge(
    slots: dict[str, str],
    open_expr: str,
) -> Element:
    """L'arête droite de la barre, rendue cliquable.

    Pourquoi elle existe (finding [29], 2026-08-21)
    ------------------------------------------------
    Dans le rail replié, le bouton de repli PORTAIT LE LOGO et se
    changeait en chevron **au survol**. Sur une machine sans survol — un
    portable tactile, celle de l'utilisateur — il n'y avait donc aucun
    signal : le logo avait l'air d'un logo, et rien ne disait que la barre
    pouvait se rouvrir. Le geste existait et personne ne pouvait le
    découvrir.

    L'arête répare ça sans rien cacher : la bordure droite de l'aside est
    déjà peinte en permanence, on la rend simplement atteignable. C'est la
    différence exacte avec le ``SidebarRail`` de shadcn, invisible au
    repos — et que ``test_hover_only_controls_reachable`` interdirait ici.

    Elle libère aussi le logo, qui redevient un lien : il arrête de
    changer de métier selon l'état de la barre.
    """
    return Element(
        tag="button",
        attrs={
            "type": "button",
            "class": slots.get("rail_edge", ""),
            "aria-label": text("sidebar.rail_toggle"),
            "bz-on:click": f"{open_expr} = !{open_expr}",
            # ── L'arête est une VITRE : le clic s'y arrête, la molette
            # la traverse ────────────────────────────────────────────
            # Elle est ``absolute`` et enfant direct de l'aside, donc
            # HORS de la boîte qui défile. Le navigateur fait défiler ce
            # qui est sous le pointeur ; sous le pointeur il y a
            # l'arête, qui ne défile pas. Mesuré le 2026-08-23, dans les
            # DEUX états : 400 px de molette au-dessus de la bande
            # laissaient ``scrollTop`` à 0.
            #
            # Rapporté ainsi : « je ne peux pas scroller car il y a la
            # sidebar qui me propose la fermeture ». Sur une bande de
            # 16 px courant sur toute la hauteur, c'est toute la colonne
            # de droite de la barre qui devient morte à la molette.
            #
            # ``:scope >`` et pas un ``querySelector`` nu : une barre
            # IMBRIQUÉE verrait sinon la boîte de son enfant.
            # ``preventDefault`` parce qu'on a repris le geste à la main
            # — sans lui un ancêtre défilable bougerait aussi. Un
            # ``wheel`` posé par ``bz-on:`` n'est PAS passif (le défaut
            # passif ne vaut que sur window/document/body), donc
            # l'annulation prend.
            "bz-on:wheel": (
                "(() => { const b = $el.parentElement"
                ".querySelector(':scope > .bz-rail-scroll');"
                " if (!b) return; b.scrollTop += $event.deltaY;"
                " $event.preventDefault(); })()"
            ),
        },
        children=(
            Element(
                tag="span",
                attrs={
                    "class": slots.get("rail_edge_line", ""),
                    "aria-hidden": "true",
                },
                children=(),
            ),
        ),
    )


__all__ = [
    "Sidebar",
    "SidebarFooter",
    "SidebarFooterItem",
    "SidebarItem",
    "SidebarSection",
    "SidebarTitle",
]


