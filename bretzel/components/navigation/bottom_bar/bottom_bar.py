"""``BottomBar`` / ``BottomBarItem`` — tab bar bas d'écran (mobile).

API ::

    # Le shell mobile — la barre d'onglets EN BAS, le contenu au-dessus.
    # Le responsive reste server-driven : c'est le layout qui branche sur
    # ``Screen().is_mobile`` (cf. ``.claude/bretzel/screen-responsive-nav.md``).
    if Screen().is_mobile:
        with ui.vstack():
            ui.outlet()
            with ui.bottom_bar():
                ui.bottom_bar_item("Accueil",   icon="home",   href="/")
                ui.bottom_bar_item("Recherche", icon="search", href="/search")
                ui.bottom_bar_item("Alertes",   icon="bell",   href="/alerts",
                                   badge=3)
                ui.bottom_bar_item("Profil",    icon="user",   href="/me")
    else:
        with ui.hstack():
            ui.sidebar(...)
            ui.outlet()

Deux pièces, pas trois — **il n'y a pas de ``bottom_bar_section``.** Une tab
bar est une rangée d'onglets à largeur égale (``flex-1``) ; le groupement
gauche / centre / droite de ``NavbarSection`` n'y a aucun sens, c'est
justement ce qui la distingue d'une navbar.

Le framework **n'impose aucune nav mobile** (décision actée, cf.
``todo.md`` § A) : ``ui.sidebar`` n'a plus de drawer intégré, et ce composant
n'est jamais monté tout seul. C'est le dev qui écrit son ``if``, et qui
choisit la barre du bas plutôt qu'une navbar horizontale — laquelle reste un
mauvais compromis sur téléphone (cibles trop petites, hors de portée du
pouce).

Pourquoi ``sticky`` et pas ``fixed``
------------------------------------

Une barre en ``position: fixed`` sort du flux : elle masque le bas de la
page, et il faut compenser — soit un ``padding-bottom`` écrit à la main dans
le code app (ce que la règle dure n°1 du funnel refuse), soit un nœud
« spacer » émis à côté de la barre. Cette seconde voie **casse les kwargs
universels** : ``_apply_universal_modifiers`` ne sait poser ``classes=`` /
``style=`` / ``visible=binding`` / ``tooltip=`` que sur un ``Element``
racine, donc un ``Fragment(spacer, barre)`` les perdrait en silence, et un
wrapper les poserait sur le spacer invisible.

``position: sticky`` donne les deux propriétés en **un seul nœud** : il reste
dans le flux (il réserve donc sa propre hauteur, aucun contenu masqué) et se
colle au bas du viewport pendant le scroll. C'est exactement le mécanisme de
``ui.navbar(sticky=True)``, retourné.

⚠️ Deux corollaires hérités de sticky, et il n'y a **pas de prop pour les
contourner** (cf. ``_CUT``) :

- un ancêtre en ``overflow: hidden`` ou ``overflow: auto`` déplace
  l'accrochage — la barre se colle au bas de CE conteneur, pas du viewport.
  Même fragilité que ``ui.navbar(sticky=True)``.
- un élément sticky ne peut pas sortir de son bloc conteneur. Monter
  plusieurs barres sur une même page (un banc, un aperçu) les fait donc
  s'épingler à tour de rôle ; leur donner chacune un conteneur à SA hauteur
  les immobilise. C'est ce que fait la page ``/bottom-bar``.

Dans une coque « document gelé », la barre LÈVE si elle est mal placée
-----------------------------------------------------------------------
Une page qui écrit ``ui.viewport`` choisit le modèle du document gelé, et
le cadre est ``fixed inset-0`` — il quitte le flux. Deux placements
naturels rendent alors une page qui a l'air construite, et
``check_sticky_bar_placement`` (``base/_wiring``, appelée par le pipeline
quand l'arbre est bâti) les refuse tous les deux avec le geste à écrire :

- **hors du cadre** — le placement que suggère « collée au bas de
  l'écran ». Mesuré : la barre se rend à **y = 0** ;
- **enfant direct d'un cadre en rangée** — la barre est pleine largeur,
  donc elle prend toute la rangée et le ``ui.pane`` voisin tombe à
  **0 px de large**. C'est le contenu de la page qui disparaît, pas la
  barre.

La garde ne dit rien tant qu'aucun ``ui.viewport`` n'existe dans le
rendu : le modèle par défaut — le document qui défile — n'est pas
concerné. ``traps.md`` § *Une barre `sticky` hors du cadre gelé*.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    ComponentUsageError,
    reactive_prop,
)
from bretzel.components.base._wiring import register_sticky_bar
from bretzel.components.navigation._wiring import (
    capture_layout,
    current_path_resync_init,
    current_path_scope,
    render_badge,
    wire_nav_item,
)
from bretzel.components.navigation.bottom_bar.theme import (
    BOTTOM_BAR_ITEM_THEME,
    BOTTOM_BAR_THEME,
)
from bretzel.core.tree import Element

# ───────────────────────────────────────────────────────────────────────────
# BottomBar — root container
# ───────────────────────────────────────────────────────────────────────────


class BottomBar(Component):
    """Render a bottom navigation bar that tracks the current path."""

    THEME: ClassVar[dict[str, Any]] = BOTTOM_BAR_THEME
    THEME_KEY: ClassVar[str] = "bottom_bar"
    DEFAULT_TAG: ClassVar[str] = "nav"
    # Le composant n'a **aucun axe** : ni couleur, ni taille, ni variante, ni
    # positionnement. Sa forme est celle d'une tab bar, un point. ``()`` et
    # pas ``None`` : ``None`` signifierait « ne vérifie rien » et un binding
    # serait accepté puis jeté en silence.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    # Les deux axes livrés puis coupés, chacun pour la même raison : ils
    # échouent le test décisif de la règle d'opinionation — « aurait-on ce
    # composant sous deux formes dans la MÊME app ? ». Non : une app a une
    # seule tab bar.
    #
    # ⚠️ Le garde n'est pas de la politesse. Sans lui, le socle absorbe le
    # kwarg inconnu dans les attrs bruts : ``ui.bottom_bar(sticky=False)``
    # émettrait un attribut HTML ``sticky="false"`` **en silence**, sans rien
    # changer au rendu. Le risque est concret — la navbar, dont ce composant
    # est le miroir, a gardé ``sticky=`` ET ``variant=``, donc le geste
    # s'imite.
    _CUT: ClassVar[dict[str, str]] = {
        "variant": (
            "le look (pilule arrondie détachée vs barre pleine largeur) se "
            "choisit une fois par app : c'est une décision de thème"
        ),
        "sticky": (
            "une tab bar est TOUJOURS collée — une barre qui s'en va au "
            "scroll n'est plus une tab bar, c'est un pied de page"
        ),
    }

    def __init__(self, **kwargs: Any) -> None:
        for name, why in self._CUT.items():
            if name in kwargs:
                raise ComponentUsageError(
                    f"ui.bottom_bar n'a pas de `{name}=` : {why}. "
                    f"Override le slot `root` du thème pour changer ça — "
                    f'Bretzel(theme=Theme(components={{"bottom_bar": '
                    f'{{"slots": {{"root": "…"}}}}}})), ou '
                    f'`slots={{"root": "…"}}` sur l\'instance pour un cas '
                    f"unique."
                )
        super().__init__(**kwargs)
        # Elle s'inscrit, elle ne se juge pas : « suis-je bien placée ? »
        # est une question posée à l'ARBRE, et l'arbre n'existe pas
        # encore. C'est ``render/pipeline._drain`` qui tranche, une fois
        # la page bâtie. Cf. ``base/_wiring.check_sticky_bar_placement``.
        register_sticky_bar(self, "ui.bottom_bar")

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})

        attrs = self.emit_attrs()
        attrs["class"] = slots.get("root", "")

        # Scope ``current_path`` — strictement le même que Navbar et
        # Sidebar, pour que les trois restent d'accord sur l'item actif
        # quand une page en monte plusieurs. La redondance est voulue :
        # la barre du bas doit marcher sur une page qui n'a ni l'une ni
        # l'autre.
        attrs.setdefault("bz-data", current_path_scope())
        # Resync sur back/forward et sur une nav partielle déclenchée
        # ailleurs — sans ça le surlignage se décolle de l'URL au premier
        # back (le bug que la navbar a porté jusqu'au 2026-07-27).
        attrs.setdefault("bz-init", current_path_resync_init())

        inner = Element(
            tag="div",
            attrs={"class": slots.get("inner", "")},
            children=tuple(self._render_children()),
        )

        return Element(tag=self._tag, attrs=attrs, children=(inner,))


# ───────────────────────────────────────────────────────────────────────────
# BottomBarItem — un onglet
# ───────────────────────────────────────────────────────────────────────────


class BottomBarItem(Component):
    """Render a bottom-bar item with an icon, label, and optional badge."""

    THEME: ClassVar[dict[str, Any]] = BOTTOM_BAR_ITEM_THEME
    THEME_KEY: ClassVar[str] = "bottom_bar_item"
    IS_CONTAINER: ClassVar[bool] = False
    EVENTS: ClassVar[tuple[str, ...]] = ("click",)
    NAMED_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    ICON_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    # Miroir exact de NavbarItem : ``active`` est auto-dérivé de
    # ``current_path`` quand rien n'est passé ; ``badge`` et ``disabled``
    # acceptent un ClientBinding pour un compteur vivant (non-lus, panier).
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
        # Le raccourci ``icon="home"`` est emballé une taille au-dessus du
        # défaut : une cible tactile a besoin d'un glyphe lisible (24px,
        # l'ordre de grandeur iOS/Android), là où ``Icon`` par défaut rend du
        # 18px calibré pour une ligne de texte. On ne re-taille QUE le
        # raccourci string — un ``icon=ui.icon("home", size="xl")`` construit
        # par l'appelant garde sa taille.
        #
        # ⚠️ AVANT le ``super()``, pas après. Passer la string puis écraser
        # ``_slot_components`` construit DEUX ``Icon`` par onglet — celui que
        # ``adopt_slot`` fabrique à la taille par défaut, jeté aussitôt, puis
        # le bon. Mesuré : ~10,6 µs par item, soit 40 % du coût de
        # construction et plus de la moitié d'un ``render()`` complet. En
        # normalisant ici, le pipeline de slot standard adopte la valeur une
        # seule fois. (EmptyState fait l'inverse par nécessité : sa taille
        # d'icône vient du thème résolu, donc après ``super()``. Ici c'est la
        # constante ``"lg"`` — la contrainte ne s'applique pas.)
        if isinstance(icon, str):
            from bretzel.components.primitives.icon.icon import Icon

            icon = Icon(icon, size="lg")

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

        # Capture du layout englobant pour le partial-nav HTMX (même
        # mécanique que SidebarItem / NavbarItem). Au construct, parce que
        # le ``with @layout(): ...`` est encore ouvert ici — ``layout_stack``
        # est vide au moment du ``render()``.
        self._captured_layout: str | None = capture_layout()

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})

        # Lecture + câblage : le corps partagé des trois items de nav
        # (navigation/_wiring.py). Ce qui suit est propre à ce composant.
        w = wire_nav_item(self, slots)
        tag, attrs = w.tag, w.attrs
        badge_value, badge_binding = w.badge_value, w.badge_binding
        label = w.label

        # ── Enfants : (icône + badge) au-dessus, label dessous ────────
        #
        # Le badge est ancré à l'ICÔNE, pas à l'onglet : ``flex-1`` rend
        # l'onglet bien plus large que son contenu, donc un badge collé au
        # coin de l'onglet flotterait dans le vide. D'où ce wrapper relatif.
        wrapped: list[Any] = []
        icon = self._slot_components.get("icon")
        if isinstance(icon, Component):
            Component._detach_from_parent(icon)
            wrapped.append(
                Component.with_slot_class(icon.render(), slots.get("icon", ""))
            )

        # Un Component passé en badge ne reçoit que le PLACEMENT : il a déjà
        # décidé de son look, et le lui repeindre par-dessus poserait deux
        # ``bg-*`` concurrents sur le même nœud (cf. le thème).
        badge_class = slots.get("badge", "")
        if not isinstance(badge_value, Component):
            badge_class = f"{badge_class} {slots.get('badge_pill', '')}".strip()

        if badge_binding is not None:
            wrapped.append(
                render_badge(
                    badge_value,
                    badge_class,
                    reactive_path=self.path_of(badge_binding),
                )
            )
        elif badge_value is not None:
            wrapped.append(render_badge(badge_value, badge_class))

        children: list[Any] = []
        if wrapped:
            children.append(
                Element(
                    tag="span",
                    attrs={"class": slots.get("icon_wrap", "")},
                    children=tuple(wrapped),
                )
            )

        if label:
            children.append(
                Element(
                    tag="span",
                    attrs={"class": slots.get("label", "")},
                    children=(self.emit_text_slot(label),),
                )
            )

        return Element(tag=tag, attrs=attrs, children=tuple(children))


__all__ = ["BottomBar", "BottomBarItem"]
