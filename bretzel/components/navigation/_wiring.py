"""Le corps partagé d'un item de navigation — NavbarItem, SidebarItem,
BottomBarItem.

Les trois composants sont des **variantes visuelles d'un même
comportement** : résoudre l'état actif, brancher le partial-nav HTMX,
neutraliser un item désactivé, rendre un badge. Seuls le thème et deux
extras propres à la sidebar (le scroll-into-view au montage, le tooltip
du rail replié) diffèrent réellement.

⚠️ Ce docstring est le SEUL endroit où la promesse « ces composants se
comportent à l'identique » est écrite — leurs docstrings s'appuient dessus.
Un quatrième consommateur s'ajoute ici, pas seulement dans les imports.

Tout ça vivait en double (audit F15, F16, F54), et la dérive **avait
déjà eu lieu** — c'est ce qui rend le finding concret plutôt que
théorique :

- l'``aria-disabled`` réactif s'écrivait ``'true' : null`` côté navbar et
  ``'true' : 'false'`` côté sidebar (F88) — sans conséquence aujourd'hui,
  une variante Tailwind ``aria-disabled:*`` ne matchant que ``="true"``,
  mais les deux composants auraient divergé le jour où un thème
  sélectionnerait ``aria-disabled=false`` ;
- le badge réactif de la sidebar rendait une pastille **vide** au premier
  paint, là où celui de la navbar peignait la valeur SSR en attendant le
  boot du runtime, et savait accepter un Component.

Les deux sont réconciliés ici sur la meilleure des deux versions.
"""

from __future__ import annotations

import json
from typing import Any, NamedTuple

from bretzel.components.base import Component
from bretzel.components.base._wiring import bool_attr
from bretzel.core.tree import Element
from bretzel.render.context import maybe_current_context
from bretzel.runtime.protocol import outlet_id_for

# Les canaux par lesquels un clic peut partir. Un item désactivé les perd
# TOUS : ``href`` (nav navigateur), ``hx-*`` (swap partiel), et le flip
# optimiste de ``current_path`` (sinon le surlignage se désynchronise de
# l'URL sans navigation pour le réconcilier).
_CLICK_CHANNELS = (
    "href", "hx-get", "hx-target", "hx-swap", "hx-push-url", "bz-on:click",
)


def capture_layout() -> str | None:
    """Le nom du layout englobant, lu **au construct**.

    Le ``with @layout(): …`` est encore ouvert pendant le ``__init__`` d'un
    item ; ``ctx.layout_stack`` est vide au moment du ``render()``. C'est
    donc ici, et nulle part ailleurs, qu'on peut savoir dans quel outlet le
    partial-nav devra taper.

    Son SEUL consommateur est :func:`apply_partial_nav`, juste en dessous —
    d'où sa place ici plutôt qu'en trois copies dont chacune tirait un import
    de ``bretzel.render.context`` pour trois lignes.
    """
    ctx = maybe_current_context()
    stack = list(getattr(ctx, "layout_stack", ()) or ()) if ctx else []
    return stack[-1] if stack else None


def current_path_scope(extra: str = "") -> str:
    """Le littéral ``bz-data`` qui déclare le signal ``current_path``.

    La moitié « resync » de ce mécanisme est partagée depuis toujours
    (:func:`current_path_resync_init`) ; la DÉCLARATION, elle, était recopiée
    à la main dans navbar, sidebar (deux fois, en concaténation) et
    bottom_bar. Or la clé est porteuse : :func:`apply_partial_nav` écrit
    ``current_path = "…"`` en identifiant nu, et le resync compare
    ``current_path !== p``. Un renommage dans une seule copie tuait le
    surlignage de CETTE nav en silence.

    ``extra`` ajoute les champs propres au composant (la sidebar y met son
    ``open`` et les trois champs de son tooltip de rail).
    """
    base = "current_path: window.location.pathname"
    return "{ " + (f"{base}, {extra}" if extra else base) + " }"


class NavItemWiring(NamedTuple):
    """Ce que :func:`wire_nav_item` a résolu — le comportement, pas le rendu.

    ``tag`` et ``attrs`` sont prêts à être posés sur l'``Element`` racine ;
    les autres champs sont les valeurs déjà lues, pour que l'appelant compose
    ses enfants sans relire ``_reactive_values``.
    """

    tag: str
    attrs: dict[str, Any]
    #: ``Any``, pas ``str`` : ``label`` est un slot textuel, donc il
    #: porte ``str | ClientBinding | Component``. L'annoter ``str`` avait
    #: pour pendant un ``str(...)`` à la lecture, qui expédiait le repr
    #: Python d'un Component dans la page — sur les TROIS items de nav
    #: d'un coup, puisque ce corps est partagé.
    label: Any
    href: Any
    color: str
    disabled: bool
    badge_value: Any
    badge_binding: Any


def wire_nav_item(item: Component, slots: dict[str, Any]) -> NavItemWiring:
    """Le prologue de ``render()`` d'un item de nav — lecture + câblage.

    Les trois items (Navbar / Sidebar / BottomBar) faisaient exactement ces
    45 lignes, à l'identique : les huit lectures de valeurs et de bindings,
    le choix du tag, la résolution des deux chaînes de classes, ``emit_attrs``,
    puis les trois ``apply_*``. Ce qui les distingue vraiment commence APRÈS —
    la composition des enfants, et deux extras de la sidebar.

    ⚠️ Ce n'est pas de l'esthétique : l'en-tête de ce module raconte que cette
    duplication a **déjà dérivé deux fois** (l'``aria-disabled`` réactif écrit
    de deux façons, le badge réactif qui peignait une pastille vide d'un seul
    côté). La troisième copie est arrivée avec ``bottom_bar``.

    L'ordre des trois ``apply_*`` est celui d'avant, et il compte :
    ``apply_disabled`` passe en DERNIER parce qu'il retire les canaux de clic
    que les deux précédents viennent de poser.
    """
    values = item._reactive_values
    bindings = item._binding_metadata

    label = values.get("label") or ""
    href = values.get("href")
    color = values.get("color") or "primary"
    disabled = bool(values.get("disabled"))
    disabled_binding = bindings.get("disabled")

    # Ancre si l'item navigue, tag par défaut du composant sinon.
    tag = "a" if href else item._tag

    # ``bz-class`` n'ajoute/retire que ce que son expression produit — le
    # ``class=`` statique n'est jamais touché. Les classes de base vivent
    # donc dans ``class=`` seul, l'expression ne porte que la couche active.
    base_class = slots.get("root", "")
    active_class = slots.get("active", "")

    attrs: dict[str, Any] = item.emit_attrs()
    attrs["class"] = base_class

    apply_active_state(
        attrs,
        active_binding=bindings.get("active"),
        active_value=values.get("active"),
        href=href,
        base_class=base_class,
        active_class=active_class,
    )
    apply_partial_nav(
        attrs, href=href, captured_layout=item._captured_layout,
    )
    apply_disabled(
        attrs,
        disabled=disabled,
        disabled_path=(
            item.path_of(disabled_binding)
            if disabled_binding is not None else None
        ),
    )
    return NavItemWiring(
        tag=tag, attrs=attrs, label=label, href=href, color=color,
        disabled=disabled, badge_value=values.get("badge"),
        badge_binding=bindings.get("badge"),
    )


def is_external_href(href: Any) -> bool:
    """Un href qui sort du site — jamais partial-nav-é.

    HTMX irait XHR-fetch l'hôte externe (bloqué par CORS) et le clic
    échouerait en silence.
    """
    return bool(href) and (
        "://" in href or href.startswith(("mailto:", "tel:"))
    )


def apply_active_state(
    attrs: dict[str, Any],
    *,
    active_binding: Any,
    active_value: Any,
    href: Any,
    base_class: str,
    active_class: str,
) -> None:
    """Pose l'état actif sur ``attrs`` — trois sources, dans l'ordre.

    1. binding explicite → ``bz-attr:data-active`` réactif ;
    2. booléen littéral → ``data-active`` statique ;
    3. ``None`` (auto) → comparaison réactive à ``current_path``, le
       signal que le Navbar / la Sidebar possède dans son ``bz-data``.

    Les expressions data-attr sont des ternaires **stringifiés** à
    dessein : ``bz-attr`` SUPPRIME l'attribut sur un ``false`` nu, et les
    styles ``data-[active=false]:hover:*`` du thème ont besoin de la
    chaîne littérale (cf. traps.md § data-attrs stringifiés).

    ``bz-class`` n'ajoute/retire que les classes que son expression
    produit — le ``class=""`` statique émis par le serveur n'est jamais
    touché. L'expression ne porte donc QUE la couche active (ne pas y
    répéter les classes de base).
    """
    active_js = json.dumps(active_class)
    if active_binding is not None:
        expr = active_binding.binding_path()
        attrs["bz-attr:data-active"] = bool_attr(expr)
        attrs["bz-class"] = f"({expr}) ? {active_js} : ''"
    elif active_value is True:
        attrs["data-active"] = "true"
        attrs["class"] = f"{base_class} {active_class}".strip()
    elif active_value is False:
        attrs["data-active"] = "false"
    elif href:
        # Auto : ``/`` ne doit matcher QUE la racine, pas tout chemin qui
        # commence par ``/``.
        #
        # Tout ce qui est constant AU RENDU est évalué ici, en Python, pas
        # 186 fois par page dans le navigateur : ``href !== '/'`` compare
        # deux littéraux dont le serveur connaît déjà le verdict, et
        # ``href + '/'`` est une concaténation de constantes. L'expression
        # passe de ~150 à ~62 caractères, et elle est recopiée sur trois
        # attributs par entrée (cf. todo.md § sidebar).
        #
        # La garde ``current_path !== '/'`` disparaît avec eux, et c'est
        # sûr : elle ne protégeait que le cas ``href == '/'``, désormais
        # traité par sa propre branche. Pour tout autre href,
        # ``'/'.startsWith('/text/')`` est déjà faux.
        if href == "/":
            condition = "(current_path === '/')"
        else:
            condition = (
                f"(current_path === {json.dumps(href)} || "
                f"current_path.startsWith({json.dumps(href + '/')}))"
            )
        attrs["bz-attr:data-active"] = bool_attr(condition)
        attrs["bz-class"] = f"{condition} ? {active_js} : ''"
        attrs["bz-attr:aria-current"] = f"{condition} ? 'page' : null"


def apply_partial_nav(
    attrs: dict[str, Any],
    *,
    href: Any,
    captured_layout: Any,
) -> None:
    """Branche le swap d'outlet HTMX quand l'item porte un href ET qu'un
    layout a été capturé.

    Sans layout, le lien retombe sur une ancre simple (rechargement
    complet, ce qui est correct). Un href externe garde ``target=_blank``
    + la paire ``rel`` de sécurité.
    """
    if not href:
        return
    if captured_layout and not is_external_href(href):
        attrs["href"] = href
        attrs.setdefault("hx-get", href)
        attrs.setdefault("hx-target", f"#{outlet_id_for(captured_layout)}")
        attrs.setdefault("hx-swap", "morph:innerHTML")
        attrs.setdefault("hx-push-url", "true")
        # Feedback optimiste : bascule ``current_path`` de façon
        # synchrone pour que le surlignage bouge au clic, avant l'aller-
        # retour. L'item n'a pas de ``bz-data`` à lui, donc l'expression
        # résout (et écrit) dans le scope du parent. Identifiant nu, sans
        # ``this.`` — dans une directive, ``this`` serait l'élément DOM.
        attrs.setdefault("bz-on:click", f"current_path = {json.dumps(href)}")
        return
    attrs["href"] = href
    if is_external_href(href):
        attrs.setdefault("target", "_blank")
        attrs.setdefault("rel", "noopener noreferrer")


def apply_disabled(
    attrs: dict[str, Any],
    *,
    disabled: bool,
    disabled_path: str | None,
) -> None:
    """Neutralise l'item — a11y, ordre de tabulation, canaux de clic.

    Le thème habille l'état verrouillé entièrement via les variantes
    ``aria-disabled:*`` (``opacity-50``, ``cursor-not-allowed``,
    ``pointer-events-none``), donc basculer ce seul attribut change
    l'apparence ET l'interactivité.

    Deux couches complémentaires :

    - ``disabled_path`` (un binding) → directives ``bz-attr:`` pour que
      le runtime suive les changements sans aller-retour serveur ;
    - ``disabled`` (l'instantané SSR) → verrouillage statique, y compris
      le strip des canaux de clic, pour qu'un item né désactivé ne
      navigue pas avant le boot du runtime.

    Le strip de ``href`` / ``hx-*`` reste SSR-only : les routes sont
    design-time, les re-cuire côté client se battrait avec le moteur de
    partial-nav. Une fois le binding passé à vrai, **c'est le socle
    runtime qui bloque** — ``$bz._inert`` dérive l'inertie du seul
    ``aria-disabled="true"`` et refuse le clic, la navigation native et
    l'action serveur (``02_directives.js`` + ``05_bridge.js``). Aucun
    ``hx-get`` périmé ne peut partir.

    ⚠️ Deux versions de ce docstring ont menti avant celle-ci, dans deux
    directions opposées, et ça vaut d'être gardé : la première décrivait
    ``pointer-events-none`` comme toujours présent — il l'était, dans
    ``root``, et c'était le bug (sur le même élément que
    ``cursor-not-allowed`` il annule le curseur) ; la seconde annonçait
    une classe ``locked_live`` posée ici, solution intermédiaire qui
    laissait le curseur mort dans le cas réactif. Les deux ont disparu
    quand l'inertie est devenue une propriété du socle.
    """
    if disabled_path is not None:
        # Ternaire stringifié : sur un booléen faux nu, ``bz-attr``
        # retirerait l'attribut au lieu d'écrire ``"false"``.
        attrs["bz-attr:aria-disabled"] = bool_attr(disabled_path)
        attrs["bz-attr:tabindex"] = f"({disabled_path}) ? '-1' : null"
    if disabled:
        attrs.setdefault("aria-disabled", "true")
        attrs["tabindex"] = "-1"
        for channel in _CLICK_CHANNELS:
            attrs.pop(channel, None)


def render_badge(
    value: Any,
    slot_class: str,
    *,
    reactive_path: str | None = None,
) -> Element:
    """La pastille de badge d'un item de nav.

    Accepte un Component (rendu tel quel, la classe de slot fusionnée
    dans ses attrs) ou un scalaire (rendu en petite pastille).

    Avec ``reactive_path`` (le chemin JS d'une ``ClientBinding`` portée
    par la prop ``badge``), la pastille devient un compteur vivant :
    ``bz-text`` y écrit la valeur courante et ``bz-show`` la replie quand
    le compte est falsy (0 / "" / null) — un « 0 non lus » disparaît au
    lieu d'afficher un zéro périmé. La valeur SSR peint quand même la
    première frame avant le boot du runtime.
    """
    if isinstance(value, Component):
        Component._detach_from_parent(value)
        node = value.render()
        if isinstance(node, Element):
            extra = (
                {"bz-text": reactive_path, "bz-show": reactive_path}
                if reactive_path is not None else {}
            )
            return Component.with_slot_class(node, slot_class, **extra)

    # ── Scalaire → une VRAIE pastille ────────────────────────────────
    # Import différé : ``primitives`` est en dessous de ``navigation``
    # dans le DAG, mais l'importer en tête ferait remonter le module de
    # badge à chaque chargement de nav pour un cas qui n'arrive qu'au
    # rendu. (Le socle autorise l'import ; c'est le coût qu'on évite.)
    #
    # Les slots ``badge`` des familles de navigation ne sont que des
    # positionneurs ; le composant Badge fournit l'aspect de la pastille.
    # ``error`` + ``xs`` : rouge est l'idiome du compteur de non-lus, et
    # ``xs`` ne fait pas grossir une ligne de nav de 36px. Un appelant qui
    # veut autre chose passe un ``ui.badge(...)`` complet — c'est la
    # branche Component ci-dessus, et le contrat à deux étages du
    # framework (magie par défaut, échappatoire pour les 20 %).
    if value is not None:
        from bretzel.components.feedback.badge import Badge

        pill = Badge(str(value), color="error", size="xs")
        Component._detach_from_parent(pill)
        node = pill.render()
        if isinstance(node, Element):
            extra = (
                {"bz-text": reactive_path, "bz-show": reactive_path}
                if reactive_path is not None else {}
            )
            return Component.with_slot_class(node, slot_class, **extra)

    # Valeur nulle : l'enveloppe vide reste, elle porte le ``bz-show`` qui
    # la fera apparaître quand le binding se remplira.
    attrs: dict[str, Any] = {"class": slot_class}
    if reactive_path is not None:
        # ``bz-text`` possède le textContent au runtime : l'enfant SSR
        # n'est que l'échafaudage du premier paint (omis quand il n'y a
        # pas de valeur SSR, pour éviter un flash de pastille vide).
        attrs["bz-text"] = reactive_path
        attrs["bz-show"] = reactive_path
    return Element(tag="span", attrs=attrs, children=())


__all__ = [
    "apply_active_state",
    "NavItemWiring",
    "capture_layout",
    "current_path_scope",
    "current_path_resync_init",
    "apply_disabled",
    "apply_partial_nav",
    "is_external_href",
    "render_badge",
    "wire_nav_item",
]


def current_path_resync_init() -> str:
    """``bz-init`` qui garde ``current_path`` collé à l'URL réelle.

    Le scope ``current_path`` (que Navbar et Sidebar possèdent chacun
    dans son ``bz-data``) pilote le surlignage actif. Le clic sur un item
    le bascule de façon optimiste, mais **tout ce qui navigue autrement**
    le laisserait périmé : le back/forward du navigateur, et une nav
    partielle déclenchée ailleurs dans la page (un item de sidebar quand
    une navbar est montée à côté, un lien in-page).

    Deux écoutes, donc : ``popstate`` et ``htmx:after-request`` — la
    seconde couvre le succès ET le rollback d'erreur en un seul handler
    (htmx saute ``hx-push-url`` sur 4xx/5xx, donc l'URL est déjà revenue
    quand on la relit).

    ⚠️ Elles passent par ``$bz.helpers.onWindow`` : ``bz-on:`` écoute sur
    l'ÉLÉMENT et n'a pas de modificateur ``.window``. ``popstate`` ne
    fire que sur window, et un événement htmx déclenché hors du composant
    ne remonte jamais à travers lui.

    ⚠️ Le garde compare-puis-assigne n'est pas cosmétique : sans lui,
    CHAQUE événement htmx de la page ré-évaluerait les
    ``bz-attr:data-active`` / ``bz-class`` de tous les items — une
    cascade réactive en O(N) pour rien.

    Les deux sources sont nécessaires pour garder le surlignage synchronisé
    avec l'URL, y compris après une navigation dans l'historique.
    """
    guard = (
        "const p = window.location.pathname; "
        "if (current_path !== p) { current_path = p; } "
    )
    return (
        f"$bz.helpers.onWindow('popstate', () => {{ {guard}}}); "
        f"$bz.helpers.onWindow('htmx:after-request', () => {{ {guard}}})"
    )
