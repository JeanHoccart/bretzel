"""``Carousel`` — défilement aimanté d'une série de contenus.

Usage ::

    with ui.carousel(autoplay=5) as hero:
        ui.image(src="/a.jpg")
        ui.image(src="/b.jpg")

    with ui.carousel(value=state.slide, per_view={"base": 1, "md": 3}):
        for p in ui.each(products):
            ui.card(p.name)

**Chaque enfant direct est une slide.** Contrairement à ``Tabs``, il n'y
a qu'une sorte d'enfant : il n'y a donc rien à distinguer, donc rien à
déclarer. Le bénéfice décisif est que ça compose avec ``ui.each`` sans
une ligne de cérémonie — le cas d'usage numéro un. Une slide à plusieurs
éléments se fait avec un ``ui.vstack``, comme partout ailleurs.

**Le moteur est du CSS scroll-snap**, pas un ``translateX`` piloté. Le
swipe tactile avec inertie, la molette, le clavier et l'aimantation sont
ceux du navigateur ; le runtime ne fait qu'aller à un index et lire
l'index depuis la position (``$bz.carousel.scope``,
``runtime/_src/17_carousel.js``). C'est ce qui rend ``per_view``
responsive gratuit : le JS ne connaît aucun breakpoint, il MESURE ce que
CSS a décidé.

**Les contrôles ne sont pas des props.** Ils sont dérivés, parce que les
rendre inconditionnellement serait faux dans deux cas réels :

- rien du tout quand il n'y a nulle part où aller (``len(slides) <=
  per_view``) — et ça arrive pour de vrai, le contenu venant des données
  (une liste à un seul élément) ;
- les puces seulement là où ``per_view == 1``. Une puce dit « il y a N
  slides, tu es à la k-ième » ; avec 3 slides visibles sur 12 elle n'a
  plus de référent. Avec un ``per_view`` responsive, elles sortent en
  ``md:hidden`` — la décision reste en CSS.

Les flèches, elles, se **désactivent aux bords** en lisant la géométrie
réelle du navigateur (``scrollLeft`` vs ``scrollWidth - clientWidth``),
donc sans le moindre calcul de breakpoint côté Python ou JS.

Un écart assumé : **les flèches butent, l'autoplay boucle.** Une flèche
désactivée au bout apprend qu'il n'y a plus rien ; une rotation
automatique qui s'arrête n'est plus une rotation.

``autoplay`` porte l'activation ET la cadence en un seul prop
(``autoplay=5`` → toutes les 5 s, ``None`` → éteint) : deux props
rendraient représentable l'état absurde « éteint mais cadencé ». Il
réutilise ``$bz._tick`` (``06_helpers.js``), le timer idempotent aux
morphs déjà écrit pour ``ui.interval`` — l'autoplay n'ajoute donc aucun
timer au runtime. Au premier geste de l'utilisateur il s'arrête
DÉFINITIVEMENT : pas de reprise après délai (un contenu qui se remet à
bouger pendant qu'on le lit est la plainte d'a11y numéro un sur les
carrousels), et pas de pause au survol (elle n'existe pas sur un
pointeur grossier).

Imperative API : ``.set(i)`` / ``.next()`` / ``.prev()`` — même famille,
mêmes noms et même sémantique d'index que :class:`Stepper`. Deux
composants qui se pilotent pareil se retiennent une fois.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import (
    bool_attr,
    coerce_index,
    hidden_carrier_attrs,
    server_sync_marker,
)
from bretzel.components.base._wiring import (
    pop_change_handler as _pop_change_handler,
)
from bretzel.components.base.responsive import (
    BASE_KEYS,
    responsive_classes,
)
from bretzel.components.layout.carousel.theme import CAROUSEL_THEME, DOTS_HIDDEN
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element, Node
from bretzel.render import text


def _per_view_class(value: Any) -> str:
    """Une valeur de ``per_view`` → la classe de largeur d'une slide.

    ``1`` → ``basis-full`` ; ``N`` → ``basis-1/N``. Une chaîne passe
    verbatim (échappatoire Tailwind brute, même contrat que
    ``Grid(cols=)``). Les breakpoints ne sont PAS gérés ici :
    :func:`responsive_classes` enveloppe cette fonction et possède le
    préfixage ``{bp}:`` pour tout prop gradué de la bibliothèque.
    """
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return value
    count = int(value)
    return "basis-full" if count <= 1 else f"basis-1/{count}"


def _per_view_at_base(value: Any) -> int:
    """Le ``per_view`` au plus petit breakpoint — celui qui décide si les
    puces existent DU TOUT.

    Les puces n'ont de sens qu'à ``per_view == 1``. Avec un dict
    responsive, elles sont rendues dès que le breakpoint de base vaut 1,
    puis masquées en CSS aux breakpoints où il monte (cf.
    :meth:`Carousel._dots_hidden_class`) — la décision reste là où vit
    l'information, dans la feuille de style.

    ``BASE_KEYS`` et pas une liste écrite ici : la recopie à la main
    avait déjà dérivé DANS LES DEUX SENS — elle inventait un ``DEFAULT``
    majuscule (que ``responsive_classes`` refuse, donc branche morte) et
    oubliait ``default`` (qu'il accepte). Résultat mesuré :
    ``per_view={"default": 3}`` rendait une puce par slide en en
    montrant trois — exactement l'état que la docstring du module
    déclare impossible.
    """
    if isinstance(value, dict):
        for key, raw in value.items():
            if key in BASE_KEYS:
                return _per_view_at_base(raw)
        return 1
    if value is None or isinstance(value, (str, bool)):
        return 1
    return max(1, int(value))


def _build_bz_data(
    *,
    scope_key: str,
    has_local_value: bool,
    initial_value: int,
    binding_path: str | None,
    server_synced: bool,
    autoplay: bool,
) -> str:
    """Le ``bz-data`` de l'instance : **des données, pas du code**.

    Les méthodes (géométrie, ``goTo``/``next``/``prev``, les deux ponts
    position↔état) vivent une seule fois dans ``$bz.carousel.scope``.

    ``_track`` est déclaré ``null`` puis rempli par le ``bz-init`` du
    root : une méthode de scope n'a pas accès à ``$refs``, seules les
    directives en ont (même contrainte et même remède que Slider).

    ``still`` n'est émis que si un autoplay existe, et c'est un SIGNAL
    déclaré, pas un champ posé à la volée : c'est l'effet
    ``$bz._tick($el, !still, ms)`` qui le lit, et un champ non déclaré
    ne relancerait jamais cet effet — la rotation ne s'arrêterait
    jamais.

    ``_geom`` est déclaré pour la MÊME raison, et il est ce qui rend les
    flèches justes. La borne est MESURÉE (``scrollWidth -
    clientWidth``), et une mesure n'est pas un signal : sans un champ
    déclaré à lire, ``bz-attr:disabled="_atEnd()"`` s'évalue une fois au
    scan et se fige. Hydraté avant que la feuille de style s'applique,
    il mesure une piste qui n'est pas encore ``flex`` — donc rien à
    faire défiler, donc les DEUX flèches désactivées, donc invisibles
    (``disabled:opacity-0``), définitivement. Le champ doit être déclaré
    ICI : posé à la volée côté JS, il n'existerait pas au premier
    passage de l'effet, qui ne s'y abonnerait donc jamais.
    """
    if has_local_value:
        sync = server_sync_marker(scope_key, enabled=server_synced)
        state = f"{scope_key}: {json.dumps(initial_value)},{sync} "
        target = f"this.{scope_key}"
    else:
        assert binding_path is not None
        state = ""
        target = binding_path

    return (
        "{...$bz.carousel.scope,"
        + state
        + ("still: false," if autoplay else "")
        + "_geom: 0,"
        + "_track: null,"
        + f"_read() {{ return {target}; }},"
        + f"_write(v) {{ {target} = v; }}"
        + "}"
    )


class Carousel(Component):
    """Render a snapping track whose direct children are slides."""

    THEME: ClassVar[dict[str, Any]] = CAROUSEL_THEME
    THEME_KEY: ClassVar[str] = "carousel"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value",)
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "next", "prev")
    EVENTS: ClassVar[tuple[str, ...]] = ("change",)
    # ``per_view`` est le seul prop gradué, et sa classe est assemblée par
    # ``_per_view_class`` (clôturée par ``_LAYOUT_CLASSES``). Reste le
    # masquage des puces, dont la classe vit dans la table ``responsive``.
    RESPONSIVE_THEME_KEYS: ClassVar[tuple[str, ...]] = ("responsive",)
    RESPONSIVE_PROPS: ClassVar[frozenset[str]] = frozenset({"per_view"})

    value: Any = reactive_prop(
        default=0,
        emit_attr=False,
        writes=True,
        names_field=True,
    )
    # ``Any`` et non ``int`` : prop gradué, il prend un dict de breakpoints.
    per_view: Any = reactive_prop(default=1, emit_attr=False)
    autoplay: Any = reactive_prop(default=None, emit_attr=False)
    gap: str = reactive_prop(default="md", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    name: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        *,
        value: Any = None,
        per_view: int | dict | str | None = None,
        autoplay: float | None = None,
        gap: str | None = None,
        size: str | None = None,
        color: str | None = None,
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le défaut).
        super().__init__(
            value=value,
            per_view=per_view,
            autoplay=autoplay,
            gap=gap,
            size=size,
            color=color,
            name=name,
            on_change=on_change,
            **kwargs,
        )

    # ── API impérative ─────────────────────────────────────────────────
    #
    # Méthodes de classe ordinaires : aucun de ces noms n'est une
    # ``reactive_prop``, donc le trick non-data-descriptor des overlays
    # n'a rien à protéger ici — et il rendrait ces méthodes invisibles à
    # ``test_imperative_classvar_is_complete``, qui ne lit que les
    # méthodes publiques d'une ClassDef.

    def set(self, index: int) -> str:
        """Aller à ``index``. Write-through binding s'il y en a une."""
        return self._value_command(coerce_index(index, minimum=0))

    def next(self) -> str:
        # Toujours le dispatch, binding ou pas : la destination dépend de
        # la géométrie VIVANTE (combien de slides tiennent à l'écran au
        # breakpoint courant), que le serveur ne connaît pas au rendu.
        return self._dispatch_command("bz-next")

    def prev(self) -> str:
        return self._dispatch_command("bz-prev")

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        sizes = theme.get("sizes", {})
        gaps = theme.get("gaps", {})

        size_key = self._reactive_values.get("size") or "md"
        size_cfg = sizes.get(size_key, sizes.get("md", {}))
        per_view = self._reactive_values.get("per_view")
        autoplay = self._reactive_values.get("autoplay")
        gap_key = self._reactive_values.get("gap") or "md"

        # ── Binding de ``value`` ─────────────────────────────────────
        value_binding = self._binding_metadata.get("value")
        initial_index = coerce_index(self._reactive_values.get("value"), minimum=0)
        value_server_backed = self._value_server_backed("value")
        scope_key = self._scope_keys("value")[0]
        binding_path = (
            self.path_of(value_binding) if value_binding is not None else None
        )
        active_expr = binding_path or scope_key

        # ── Les slides = les enfants, un par un ──────────────────────
        slide_class = self.slot_class("slide", responsive_classes(per_view, _per_view_class)
        )
        slides: list[Element] = []
        for child in self._children:
            rendered = self._render_one(child)
            if isinstance(rendered, Element):
                slides.append(
                    Element(
                        tag="div",
                        attrs={"class": slide_class},
                        children=(rendered,),
                    )
                )

        count = len(slides)
        base_per_view = _per_view_at_base(per_view)
        # Rien à piloter s'il n'y a nulle part où aller — et le cas
        # arrive pour de vrai, le contenu venant des données.
        has_controls = count > base_per_view
        # Les puces n'existent que là où elles ont un référent.
        has_dots = has_controls and base_per_view == 1

        track = Element(
            tag="div",
            attrs={
                "class": self.slot_class("track", gaps.get(gap_key, "")),
                "bz-ref": "bztrack",
                # Ce qui fait re-mesurer les bornes quand la mise en page
                # change APRÈS le scan (feuille de style tardive, panneau
                # replié qui s'ouvre, breakpoint). Porté par la PISTE et
                # pas par le ``bz-init`` du root : ``bz-init`` est one-shot
                # par NŒUD et idiomorph morphe en place, donc un observer
                # installé là ne reverrait jamais les slides. Un effet est
                # refait à chaque rescan. (Raisonné depuis le code, pas
                # prouvé par un test : la boîte de la piste suit celle de
                # ses slides, donc l'observation de la piste couvre en
                # pratique les cas qu'on a su fabriquer.)
                "bz-effect": "_observeGeom()",
                # Sans modificateur, et ce n'est pas un oubli : ``bz-on:``
                # passe son suffixe VERBATIM à ``addEventListener``, donc
                # un ``.passive`` écouterait un événement nommé
                # « scroll.passive » et ce pont serait mort en silence.
                # Payé ici même (traps.md § « bz-on: n'a AUCUN
                # modificateur »), gaté depuis.
                "bz-on:scroll": "_onScroll()",
                # Le premier geste éteint l'autoplay. ``pointerdown``
                # couvre doigt et souris, ``wheel`` la molette.
                **(
                    {
                        "bz-on:pointerdown": "_touch()",
                        "bz-on:wheel": "_touch()",
                    }
                    if autoplay
                    else {}
                ),
            },
            children=tuple(slides),
        )

        # Les flèches s'ancrent sur le VIEWPORT, pas sur la root : leur
        # ``top-1/2`` se calculerait sinon sur une hauteur qui comprend la
        # rangée de puces, et elles tomberaient visiblement sous le centre
        # de la piste (mesuré à 10 px sur un carousel à puces).
        viewport_children: list[Node] = [track]
        children: list[Node] = []

        # Le préfixe qui éteint l'autoplay, une seule fois : flèches ET
        # puces le portent, et ``has_dots`` implique ``has_controls`` —
        # donc le définir dans la branche des flèches le rendait
        # disponible aux puces par un effet de bord, ce qui se lit mal.
        touch = "_touch(); " if autoplay else ""

        if has_controls:
            arrow_size = size_cfg.get("arrow", "")
            icon_size = size_cfg.get("arrow_icon", "sm")
            for direction, icon_name, label_key, disabled_call in (
                ("prev", "chevron-left", "carousel.previous", "_atStart()"),
                ("next", "chevron-right", "carousel.next", "_atEnd()"),
            ):
                viewport_children.append(
                    Element(
                        tag="button",
                        attrs={
                            "type": "button",
                            "class": self.slot_class(
                                "arrow",
                                arrow_size,
                                self.slot_class(f"arrow_{direction}"),
                            ),
                            "aria-label": text(label_key),
                            "bz-attr:disabled": disabled_call,
                            "bz-on:click": f"{touch}{direction}()",
                        },
                        children=(
                            Component.render_detached(
                                Icon(icon_name, size=icon_size)
                            ),
                        ),
                    )
                )

        children.append(
            Element(
                tag="div",
                attrs={"class": self.slot_class("viewport")},
                children=tuple(viewport_children),
            )
        )

        if has_dots:
            dot_class = self.slot_class("dot", size_cfg.get("dot", ""))
            dot_nodes: list[Node] = []
            for index in range(count):
                dot_attrs: dict[str, Any] = {
                    "type": "button",
                    "class": dot_class,
                    "aria-label": text("carousel.go_to_slide", n=index + 1),
                    # ``bool_attr`` et pas un ternaire à la main : c'est
                    # LE helper de la chaîne littérale ``"true"``/``"false"``
                    # (un booléen nu ferait DROPPER l'attribut à false et
                    # ``data-[selected=…]`` ne matcherait jamais). Dix-neuf
                    # sites l'avaient réimplémenté avant son extraction,
                    # dont dix sans parenthéser leur opérande.
                    "bz-attr:data-selected": bool_attr(
                        f"Number({active_expr}) === {index}"
                    ),
                    "bz-on:click": f"{touch}goTo({index})",
                }
                if index == initial_index:
                    # SSR statique — la puce active est juste au premier
                    # paint, avant que le runtime hydrate.
                    dot_attrs["data-selected"] = "true"
                dot_nodes.append(
                    Element(tag="button", attrs=dot_attrs, children=())
                )
            children.append(
                # Pas de ``role="tablist"`` : le motif ARIA « carousel à
                # onglets » exige AUSSI ``role="tab"`` sur chaque puce et
                # ``role="tabpanel"`` sur chaque slide, avec les
                # ``aria-controls`` qui les relient. Déclarer la moitié
                # du motif annonce aux lecteurs d'écran une structure qui
                # n'existe pas — pire que de n'en déclarer aucune. Des
                # boutons étiquetés dans un groupe nommé disent la vérité.
                Element(
                    tag="div",
                    attrs={
                        "class": self.slot_class("dots", self._dots_hidden_class(
                                per_view,
                                theme.get("responsive", {}).get(
                                    DOTS_HIDDEN, ""
                                ),
                            ),
                        ),
                        "role": "group",
                        "aria-label": text("carousel.choose_slide"),
                    },
                    children=tuple(dot_nodes),
                )
            )

        # ── Input caché — form data + source du ``change`` ───────────
        root_attrs = self.emit_attrs()
        relocated = _pop_change_handler(root_attrs)
        name = self._reactive_values.get("name") or self._derive_field_name()
        if name or relocated:
            hidden_attrs: dict[str, Any] = {
                **hidden_carrier_attrs(active_expr, initial=initial_index),
            }
            if name:
                hidden_attrs["name"] = str(name)
            hidden_attrs.update(relocated)
            children.append(
                Element(tag="input", attrs=hidden_attrs, children=())
            )

        # ── Assemblage ───────────────────────────────────────────────
        root_attrs["class"] = self.slot_class("root")
        # Le rôle vit sur la ROOT et pas sur la piste : c'est elle qui
        # contient AUSSI les flèches et les puces, donc c'est elle le
        # « carousel » qu'un lecteur d'écran doit annoncer d'un bloc.
        root_attrs["role"] = "group"
        root_attrs["aria-roledescription"] = "carousel"
        root_attrs["bz-data"] = _build_bz_data(
            scope_key=scope_key,
            has_local_value=value_binding is None,
            initial_value=initial_index,
            binding_path=binding_path,
            server_synced=value_server_backed,
            autoplay=bool(autoplay),
        )
        # Une méthode de scope n'a pas ``$refs`` — c'est ici, en contexte
        # de directive, qu'on capture la piste dans le scope.
        root_attrs["bz-init"] = "_track = $refs.bztrack"
        effects = ["_syncFromValue()"]
        if autoplay:
            ms = max(1, int(float(autoplay) * 1000))
            # ``$bz._tick`` est le timer de ``ui.interval`` : idempotent
            # aux morphs, auto-nettoyé quand l'élément quitte le DOM.
            # L'autoplay n'ajoute donc aucun timer au runtime.
            effects.append(f"$bz._tick($el, !still, {ms})")
            root_attrs["bz-on:tick"] = "next()"
        root_attrs["bz-effect"] = "; ".join(effects)
        root_attrs["bz-on:bz-set"] = "goTo($event.detail.value)"
        root_attrs["bz-on:bz-next"] = "next()"
        root_attrs["bz-on:bz-prev"] = "prev()"

        return Element(
            tag=self._tag, attrs=root_attrs, children=tuple(children)
        )

    @staticmethod
    def _dots_hidden_class(per_view: Any, hidden: str) -> str:
        """Masquer les puces aux breakpoints où ``per_view`` dépasse 1.

        Rendu seulement quand la base vaut 1 (sinon il n'y a pas de puce
        du tout). Le masquage vit en CSS et non en Python parce que le
        serveur ne sait pas quel breakpoint est actif — c'est la même
        raison qui fait lire la géométrie au runtime plutôt que la
        calculer.

        ``hidden`` vient de ``THEME["responsive"]["dots_hidden"]`` et
        n'est PAS écrit en dur ici : seul un token présent dans une table
        déclarée par ``RESPONSIVE_THEME_KEYS`` est clôturé sur les
        breakpoints par la safelist. En dur, ``lg:hidden`` n'existait
        dans aucune source, donc la règle manquait du CSS compilé et les
        puces restaient visibles en prod — exactement le comportement que
        cette méthode existe pour empêcher.
        """
        if not isinstance(per_view, dict) or not hidden:
            return ""
        return " ".join(
            f"{bp}:{token}"
            for bp, raw in per_view.items()
            if bp not in BASE_KEYS
            and isinstance(raw, int)
            and not isinstance(raw, bool)
            and raw > 1
            for token in hidden.split()
        )


__all__ = ["Carousel"]
