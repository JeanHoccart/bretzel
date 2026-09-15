"""``@refreshable`` — mark a function as a partial swap target.

The decorated function is wrapped in a :class:`RefreshableHandle`. The
handle is callable like the original function (so it slots into a page
render naturally). A zone re-renders declaratively when a state in its
``deps=`` changes ; :func:`refresh` (the free function) forces one
imperatively from anywhere.

"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Sequence
from typing import Any, ClassVar

from bretzel.core import hash_segment
from bretzel.render.context import maybe_current_context
from bretzel.runtime.protocol import (
    DATA_SUBSCRIBE_STATE,
    DATA_SUBSCRIBE_URL,
    DATA_ZONE,
    ROUTE_REFETCH,
    WIRE_ID_SEP,
)


def _resolve_broadcast(
    broadcast: Sequence[type], zone: str
) -> tuple[type, ...]:
    """``broadcast=`` → les états sur lesquels la zone écoute le SSE.

    **Orthogonal à ``deps``**, et c'est tout le modèle :

    ==============  ====================================================
    qui change      où on l'écrit
    ==============  ====================================================
    **moi**         ``deps`` — la zone est re-rendue DANS la réponse de
                    l'action. Un aller-retour, un swap.
    **les autres**  ``broadcast`` — un signal SSE, puis un refetch. Deux
                    allers-retours, mais l'onglet qui n'a rien fait suit.
    **les deux**    les deux listes. Ce n'est pas une redondance : ça dit
                    « instantané pour moi, poussé aux autres ».
    ==============  ====================================================

    Un ``broadcast=[X]`` SEUL est donc légitime — le cas « cet état, je
    ne le change jamais moi-même » (un job de fond, un autre utilisateur).
    Il n'y a aucune règle d'inclusion : les deux listes ne se recouvrent
    que si l'auteur le veut.

    Les booléens sont refusés : déduire les états diffusés de ``deps``
    couplerait les deux listes. L'appelant nomme explicitement les états
    qu'il veut observer chez les autres clients.
    """
    if broadcast is True or broadcast is False:
        raise TypeError(
            f"@refreshable({zone}) : broadcast= prend une LISTE d'états, "
            f"plus un booléen (supprimé le 2026-08-23). `deps` dit ce qui "
            f"me re-rend dans la réponse de MON action, `broadcast` ce sur "
            f"quoi j'écoute les AUTRES clients — ce sont deux questions. "
            f"Écris `broadcast=[MonEtat]`, et garde-le aussi dans `deps` "
            f"si c'est ta propre action qui le change (sinon tu paies un "
            f"aller-retour de plus pour l'onglet qui a cliqué)."
        )
    return tuple(broadcast)


#: Les deux formes variadiques. Elles ne sont PAS refusées : rien dans
#: une signature ne dit ce qu'un ``**kwargs`` porte, donc les refuser
#: reviendrait à juger sur le nom. Un banc du dépôt s'en sert
#: (``tests/unit/components/data/test_datatable.py``) pour bâtir une vraie
#: zone autour d'un composant paramétré.
_VARIADIC = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)


def _reject_parameters(fn: Callable[..., Any], zone: str) -> None:
    """Une zone ne prend pas de paramètre — refusé à la DÉCORATION.

    Le chemin de rafraîchissement appelle la poignée **nue**
    (``render/partials.py``, ``handle()``), alors que le rendu de page,
    lui, passe par ``__call__(*args, **kwargs)``. Les deux chemins ne
    voient donc pas la même signature, et la divergence est invisible :

    ``def zone(x)``
        La page s'affiche parfaitement. Puis la première action qui
        touche un ``deps`` lève ``TypeError`` — **un 500 sur le
        re-rendu, pas sur la page**, donc à l'endroit où on ne le
        cherche pas. C'est le cas qui a motivé ce refus (2026-09-04).

    ``def zone(x=0)``
        Pire, parce que muet : la page rend ``zone(3)``, et chaque
        rafraîchissement rend ``zone(0)``. Rien ne lève, l'écran change
        de contenu tout seul. Refusé pour la même raison, et c'est la
        moitié que l'énoncé d'origine ratait.

    Le fond : une zone est re-rendue **hors de son appelant**, donc tout
    ce dont elle a besoin doit être joignable depuis elle — c'est-à-dire
    un état. Un paramètre est une donnée que le rafraîchissement ne peut
    pas retrouver. Deux pages qui appelleraient la même zone avec deux
    arguments partageraient de toute façon un ``id`` et un ``name``
    uniques : le modèle n'a nulle part où ranger la différence.

    Remède : lire l'état dans le corps, ou garder une fonction ordinaire
    (paramétrable) que la zone appelle.
    """
    fautifs = [
        p.name
        for p in inspect.signature(fn).parameters.values()
        if p.kind not in _VARIADIC
    ]
    if not fautifs:
        return
    raise TypeError(
        f"@refreshable({zone}) : une zone ne prend pas de paramètre, et "
        f"celle-ci en déclare {', '.join(fautifs)}. Le rafraîchissement "
        f"l'appelle SANS argument — un paramètre obligatoire lève un 500 "
        f"à la première action qui touche un `deps` (jamais au "
        f"chargement de la page), un paramètre à valeur par défaut ne "
        f"lève rien et re-rend simplement autre chose. Lis un état dans "
        f"le corps de la zone, ou garde une fonction ordinaire "
        f"paramétrable que la zone appelle."
    )


def state_qualname(state_class: type) -> str:
    """Return the stable wire identifier for ``state_class``.

    Format : ``<module>::<qualname>`` — the same scheme action handlers
    and zones use, unique across modules. Vit ici, et nulle part
    ailleurs : l'ancien ``subscribe.py`` a été **supprimé** en Phase 6
    (plus aucun back-compat, plus de ré-export). Cette docstring
    annonçait le contraire jusqu'au 2026-08-01.
    """
    return f"{state_class.__module__}{WIRE_ID_SEP}{state_class.__qualname__}"


# Registry of every refreshable zone by its ``name`` (default = the
# module-qualified zone name). Lets the free ``refresh("name")`` resolve a
# zone from ANYWHERE without importing the zone function (a cron, a webhook,
# another feature). Populated at decoration time — import order applies, the
# same caveat as action handlers.
_ZONE_BY_NAME: dict[str, RefreshableHandle] = {}

# Reverse index : State class → the zones that declared it in ``deps``. The
# action pipeline uses it to enqueue exactly the zones affected by a state
# change (see :func:`enqueue_deps`).
_ZONES_BY_DEP: dict[type, list[RefreshableHandle]] = {}

#: ``État → zones qui l'écoutent sur le SSE``. Un index SÉPARÉ de
#: ``_ZONES_BY_DEP``, et pas un filtre dessus : les deux listes sont
#: orthogonales depuis le 2026-08-23, donc une zone peut être ici
#: sans être là-bas (« cet état, je ne le change jamais moi-même »).
#: Les fusionner rendrait le re-rendu LOCAL sensible à un canal, ce
#: qui est exactement la confusion qu'on vient de défaire.
_ZONES_BY_CHANNEL: dict[type, list[RefreshableHandle]] = {}


def zone_attrs(
    refresh_id: str,
    *,
    subscribe_state_qualname: str | None = None,
    subscribe_url: str | None = None,
) -> dict[str, str]:
    """Les attributs qu'une zone pose EN PLUS de son ``bz-id``.

    Au niveau module et non sur la section, parce que **trois** chemins
    en ont besoin : le rendu (``_RefreshableSection.render``), la
    recomposition par un parent (``_rewrap``), et le fragment de secours
    d'une zone qui a levé (``render/partials._zone_failure_fragment``).

    Le troisième a été écrit à la main pendant une journée, et ça a coûté
    exactement ce que cette fonction existe pour empêcher : il omettait
    ``DATA_ZONE``, donc après une erreur la zone sortait de
    l'énumération du navigateur, donc l'en-tête ``X-Bretzel-Zones`` ne la
    portait plus, donc ``enqueue_deps`` la filtrait — **elle ne se
    rafraîchissait plus jamais** jusqu'au rechargement complet, sans un
    mot. Deux gates la couvraient, chacune de son côté ; aucune ne
    voyait le croisement.

    ``DATA_ZONE`` est VIDE : l'identifiant est déjà sur le même élément
    en ``bz-id``. Le marqueur dit « je suis une zone », ``bz-id`` dit
    laquelle. Un attribut dédié plutôt qu'un préfixe d'``id`` deviné en
    JS — ``refresh_`` est une convention de ``_stable_id``, et la
    recopier côté client ferait un miroir qui dérive.
    """
    attrs = {DATA_ZONE: ""}
    if subscribe_state_qualname and subscribe_url:
        attrs[DATA_SUBSCRIBE_STATE] = subscribe_state_qualname
        attrs[DATA_SUBSCRIBE_URL] = subscribe_url
    return attrs


def _stable_id(fn: Callable[..., Any]) -> str:
    """Hash ``module.qualname`` to a short stable id.

    The id is used as the ``bz-id`` of the wrapping element, so it must
    survive code reloads but stay readable in DevTools. We keep the
    last 8 hex chars — collision risk is negligible at this scale.
    """
    qual = f"{fn.__module__}.{fn.__qualname__}"
    return f"refresh_{hash_segment(qual)}"


_section_cls_cache: type | None = None


def _section_cls() -> type:
    """Lazy-build the ``_RefreshableSection`` Component class.

    ``bretzel.components.base`` imports from us indirectly via
    ``Component.__init__`` reaching the render context, so a top-level
    ``from bretzel.components.base import Component`` would close a
    cycle. Building the class on first ``__call__`` postpones the
    import until both modules are fully loaded.
    """
    global _section_cls_cache
    if _section_cls_cache is not None:
        return _section_cls_cache

    from bretzel.components.base import Component
    from bretzel.render.fusion import fuse_or_wrap

    class _RefreshableSection(Component):
        """Wraps the children of a ``@refreshable`` call.

        Carries the section's ``bz-id`` on the rendered Element so the
        INITIAL page ships a target HTMX can find later via
        ``hx-swap-oob``. Without this wrapper, OOB swaps had no
        matching id and were silently dropped — buttons fired, server
        responded, DOM never updated.

        Pure framework concern : never instantiated by user code.

        When the wrapping handle is a ``@refreshable(deps=[State], broadcast=[State])`` zone,
        ``subscribe_state_qualname`` + ``subscribe_url`` are emitted
        as ``data-bz-subscribe-*`` attributes the runtime parses on
        DOMContentLoaded to wire the EventSource + refetch URL.
        """

        THEME_KEY: ClassVar[str] = "_refreshable"
        DEFAULT_TAG: ClassVar[str] = "div"
        IS_CONTAINER: ClassVar[bool] = True
        #: « Je ne suis pas là. » Un parent qui trie ses enfants SELON
        #: LEUR TYPE doit me traverser pour trouver ce que je porte, puis
        #: me rendre mon ``bz-id`` sur le nœud qu'il a composé — sinon
        #: l'onglet est correct et ne se rafraîchit plus jamais. Cf.
        #: ``base/_wiring.unwrap_transparent``.
        IS_TRANSPARENT_WRAPPER: ClassVar[bool] = True

        def __init__(
            self,
            *,
            refresh_id: str,
            subscribe_state_qualname: str | None = None,
            subscribe_url: str | None = None,
            **kwargs: Any,
        ) -> None:
            # The handle's stable id wins over auto-generated so
            # initial render and partial rerender share one target.
            kwargs.setdefault("id", refresh_id)
            super().__init__(**kwargs)
            self._refresh_id = refresh_id
            self._subscribe_state_qualname = subscribe_state_qualname
            self._subscribe_url = subscribe_url

        def _rewrap(self, node: Any) -> Any:
            """Reposer l'identité de la zone sur un nœud composé AILLEURS.

            Le parent (``ui.tabs`` et compagnie) a besoin de l'enfant nu
            pour le composer à sa façon ; la zone a besoin que son
            ``bz-id`` soit sur le résultat. Les deux passent par le même
            ``fuse_or_wrap`` que ``render``, donc la forme est identique
            — une seule règle wrap-ou-fusionne dans le dépôt.
            """
            return fuse_or_wrap([node], bz_id=self._refresh_id,
                                extra_attrs=self._zone_attrs())

        def _zone_attrs(self) -> dict[str, str]:
            """Délègue à :func:`zone_attrs` — la source unique des trois
            chemins (rendu, recomposition, fragment de secours)."""
            return zone_attrs(
                self._refresh_id,
                subscribe_state_qualname=self._subscribe_state_qualname,
                subscribe_url=self._subscribe_url,
            )

        def render(self) -> Any:
            children_nodes = self._render_children()
            extra_attrs = self._zone_attrs()
            return fuse_or_wrap(
                children_nodes,
                bz_id=self._refresh_id,
                extra_attrs=extra_attrs,
            )

    _section_cls_cache = _RefreshableSection
    return _section_cls_cache


async def drain_pending_async_zones(ctx: Any) -> None:
    """Attendre le corps des zones ``async`` posées pendant ce rendu.

    Appelée par les DEUX chemins de rendu — la page complète
    (``render/pipeline.py``) et le fragment (``render/partials.py``) —
    parce qu'une zone se rend par les deux, et qu'une file drainée d'un
    seul côté redonnerait la zone vide sur l'autre.

    Trois propriétés, et chacune répare une façon de se tromper :

    - **en boucle**, pas en une passe : une zone async peut en appeler
      une autre, qui s'ajoute à la file pendant qu'on attend la première ;
    - **en SÉRIE**, pas en ``gather`` : les corps partagent
      ``ctx.parent_stack``, donc deux corps concurrents enregistreraient
      leurs enfants l'un chez l'autre. La concurrence se prend DANS un
      corps (un ``asyncio.gather`` sur ses requêtes), là où elle ne
      traverse pas la pile ;
    - **sous ``with section``** : la section a été posée dans l'arbre à
      l'appel, mais la pile a continué à vivre depuis. La repousser est
      ce qui fait atterrir les enfants dans LA zone et pas à la racine.
    """
    while ctx.pending_async_zones:
        section, coro = ctx.pending_async_zones.pop(0)
        with section:
            result = await coro
            RefreshableHandle._attach_direct_return(section, result)


class RefreshableHandle:
    """Callable wrapper carrying refresh metadata.

    Behaviour :

    - Calling the handle (during a render) wraps the underlying
      function's output in a ``_RefreshableSection`` carrying the
      stable ``bz-id``. Initial render and partial re-render produce
      the SAME target shape so HTMX OOB swaps land cleanly.
    - A change to any state in ``deps=`` enqueues the zone for a partial
      re-render at end-of-action ; the free :func:`refresh` forces one
      imperatively.
    - When the zone declares ``broadcast=[State]`` its ``deps`` are the
      SSE channels : the call path (a) emits ``data-bz-subscribe-*``
      attrs (a space-separated list of the deps' wire qualnames + a
      refetch URL) so the runtime refetches on any matching signal ;
      (b) records the session against each dep on the app's SSE broker
      so a future dep-change fan-out knows which sessions to ping.
    """

    __slots__ = (
        "broadcast",
        "deps",
        "fn",
        "id",
        "is_async",
        "name",
        "zone_qualname",
    )

    def __init__(
        self,
        fn: Callable[..., Any],
        id: str,
        *,
        deps: Sequence[type] = (),
        broadcast: Sequence[type] = (),
        name: str | None = None,
    ) -> None:
        self.fn = fn
        self.id = id
        # Avant tout le reste : une signature paramétrée ne survit pas au
        # rafraîchissement, qui appelle nu. Ici plutôt que dans ``_wrap``
        # pour que ce soit STRUCTUREL — aucune poignée ne peut exister
        # autour d'une fonction paramétrée, quel que soit le chemin de
        # construction.
        _reject_parameters(fn, f"{fn.__module__}.{fn.__qualname__}")
        # Lu UNE fois à la décoration : ``iscoroutinefunction`` déballe
        # les ``functools.wraps``/``partial`` et coûte une introspection
        # qu'on ne veut pas payer à chaque rendu de zone.
        self.is_async: bool = inspect.iscoroutinefunction(fn)
        # Wire identifier for the zone function — ``module::qualname``,
        # same scheme as action handlers. Used by the realtime route
        # to resolve the fn back through ``sys.modules`` and re-render.
        self.zone_qualname = f"{fn.__module__}{WIRE_ID_SEP}{fn.__qualname__}"
        # ── Declarative reactivity (target model) ──────────────────────
        # ``deps`` : the State classes this zone reads. A change to ANY of
        # them re-renders the zone (wired in the action pipeline, Phase 3).
        # ``broadcast`` : pousse AUSSI le changement aux autres clients
        # par SSE.
        # ``name`` : stable string address for ``refresh("name")`` ;
        # defaults to the module-qualified zone name.
        self.deps: tuple[type, ...] = tuple(deps)
        #: **Les états sur lesquels cette zone écoute le SSE.**
        #: Orthogonal à ``deps`` : les deux listes ne se recouvrent que si
        #: l'auteur le veut. Vide = zone purement locale.
        #:
        #: Jusqu'au 2026-08-23, ``broadcast`` était un booléen et
        #: ``deps`` servait DEUX rôles dans le même mot : « ce qui me
        #: re-rend » et « ce sur quoi je diffuse ». Conséquence, mesurée
        #: sur `examples/crm` : une zone temps réel ne pouvait pas
        #: déclarer une dépendance PERSONNELLE — y mettre la préférence
        #: de portefeuille de la direction aurait fait refetcher le monde
        #: entier dès qu'un seul utilisateur change SON réglage. L'écran
        #: temps réel ne suivait donc pas le changement de portefeuille,
        #: faute de pouvoir l'écrire.
        self.broadcast: tuple[type, ...] = _resolve_broadcast(
            broadcast, self.zone_qualname
        )
        self.name: str = name or self.zone_qualname
        _ZONE_BY_NAME[self.name] = self
        for dep in self.deps:
            _ZONES_BY_DEP.setdefault(dep, []).append(self)
        for channel in self.broadcast:
            _ZONES_BY_CHANNEL.setdefault(channel, []).append(self)

    def _broadcast_qualnames(self) -> list[str]:
        """Wire qualnames of the states this zone broadcasts on.

        Vide pour une zone locale. Sinon, exactement les états déclarés
        dans ``broadcast`` — qui peut être un sous-ensemble strict de
        ``deps``. Calculé à la demande (les deps sont peu nombreux),
        donc la poignée ne garde aucun cache dérivé à tenir à jour.
        """
        return [state_qualname(dep) for dep in self.broadcast]

    def _subscribe_url(self, states: list[str]) -> str:
        """Refetch URL for this zone. The state segment is any of the
        zone's deps (the realtime route validates membership, not exact
        match, so one URL serves a multi-dep zone). Built server-side so
        the runtime never hardcodes a framework route."""
        return f"{ROUTE_REFETCH}/{states[0]}/{self.zone_qualname}"

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        ctx = maybe_current_context()

        # No active context → straight passthrough (test rigs that
        # don't go through a page render).
        if ctx is None:
            return self.fn(*args, **kwargs)

        # Broadcast zones : notify the broker that this session now
        # renders a zone for each dep State, so a future dep-change
        # fan-out knows to push to its queue. The wire attrs flow
        # through ``_RefreshableSection.render()`` and land on the
        # rendered Element for the runtime to discover.
        broadcast_states = self._broadcast_qualnames()
        subscribe_state_attr: str | None = None
        subscribe_url: str | None = None
        if broadcast_states:
            for qualname in broadcast_states:
                self._register_subscription(ctx, qualname)
            subscribe_state_attr = " ".join(broadcast_states)
            subscribe_url = self._subscribe_url(broadcast_states)

        # Push the section as the current parent, run the function, pop.
        # Children registered inside fn() (``ui.text(...)``, …) attach to
        # the section. The section renders to a single Element whose
        # ``bz-id`` matches what the partial-rerender response will
        # target via ``hx-swap-oob``.
        #
        # Returns the function's return value so the partial-render
        # path (``partials._render_one``) can pick up a directly-
        # returned Node (the test-rig idiom where ``fn`` returns a
        # ``ui.text(...).render()`` instead of registering via
        # ``parent_stack``). The full-page flow continues to ignore
        # the return.
        section = _section_cls()(
            refresh_id=self.id,
            subscribe_state_qualname=subscribe_state_attr,
            subscribe_url=subscribe_url,
        )
        # ── Corps ASYNC : la section est posée, le corps est différé ──
        #
        # La zone garde sa convention d'appel — ``zone()``, jamais
        # ``await zone()``. Un ``await`` à écrire serait un ``await`` à
        # OUBLIER, et l'oublier redonnerait exactement la panne que ce
        # chemin répare : une coroutine jamais attendue, donc une zone
        # VIDE, sans erreur (finding [1], 2026-08-21).
        #
        # La section entre dans l'arbre MAINTENANT parce que la place de
        # la zone dans la page se décide ici — à l'endroit de l'appel — et
        # pas quand sa donnée arrive. Le pipeline attendra le corps
        # ensuite, en repoussant cette section-là sur ``parent_stack``,
        # donc les enfants atterrissent au bon endroit.
        if self.is_async:
            ctx.pending_async_zones.append(
                (section, self.fn(*args, **kwargs))
            )
            return None

        with section:
            result = self.fn(*args, **kwargs)
            self._attach_direct_return(section, result)
        return result

    @staticmethod
    def _attach_direct_return(section: Any, result: Any) -> None:
        """Rattacher une valeur RENDUE directement par le corps.

        L'idiome de banc où ``fn`` retourne un ``ui.text(...).render()``
        au lieu de s'enregistrer via ``parent_stack``. Sans cette
        branche, le chemin partiel — qui passe par ``__call__`` — le
        laisserait tomber.
        """
        if result is not None and (
            hasattr(result, "tag") or hasattr(result, "render")
        ):
            section.add_child(result)

    @staticmethod
    def _register_subscription(ctx: Any, state_qualname: str) -> None:
        """Notify the broker that this session now renders this zone.

        ``ctx`` is the active render context — passed in by the
        caller so we don't pay the ContextVar lookup twice per call.
        Silently no-ops in setups where the broker isn't wired (test
        rigs that bypass lifecycle).
        """
        broker = ctx.app.sse_broker
        if broker is None:
            return
        session_id = ctx.session_id
        if not session_id:
            return
        broker.subscribe(session_id, state_qualname)

    def __repr__(self) -> str:
        return f"RefreshableHandle({self.fn.__qualname__}, id={self.id!r})"


def zone_ids_watching(state_cls: type) -> frozenset[str]:
    """Refresh ids des zones que ``state_cls`` fait re-rendre, par L'UN
    OU L'AUTRE chemin.

    Vue en lecture seule sur les deux index, pour les composants qui
    vérifient à la construction que *quelqu'un* les re-rendra quand ils
    muteront leur état. Sans elle, un contrôle dont la zone a oublié le
    dep POSTe son action, mute l'état, et la page ne change pas — le mode
    d'échec est le silence, le plus cher.

    ``deps`` ET ``broadcast`` : la question posée est « serai-je
    re-rendu ? », et un canal SSE répond oui — plus lentement (un
    aller-retour de plus), pas moins sûrement. Ne regarder que ``deps``
    accuserait de silence une zone qui parle.
    """
    return frozenset(
        zone.id
        for zone in (
            *_ZONES_BY_DEP.get(state_cls, ()),
            *_ZONES_BY_CHANNEL.get(state_cls, ()),
        )
    )


def enqueue_deps(ctx: Any, changed_classes: set[type]) -> None:
    """Enqueue every zone whose ``deps`` include a changed State class for
    the end-of-action refresh drain.

    Called by the action pipeline right after
    :meth:`~bretzel.state.registry.StateRegistry.diff_and_notify`. Dedup is
    by handle identity (a zone hit by several changed deps enqueues once) —
    the same ``if self not in queue`` guard an explicit refresh uses. This is
    the LOCAL auto-refresh ; the cross-client broadcast for ``broadcast=[State]``
    zones is wired separately (Phase 5).

    **On n'enfile que ce que le navigateur a sous les yeux.**
    ``_ZONES_BY_DEP`` est indexé par CLASSE d'état, pas par page : une
    classe partagée par plusieurs écrans traîne toutes leurs zones, et
    sans filtre le serveur rendait celles des autres pages pour rien —
    le navigateur les jetait faute de cible, sans une erreur nulle part.
    Mesuré le 2026-09-05 sur ``examples/mad`` : une action depuis
    ``/patients`` rendait aussi la zone du tableau de bord, **8,4 ms**
    contre 9,6 ms pour la zone utile. Sur ``examples/crm``,
    ``ViewerPrefs`` traîne 14 zones sur 8 modules pour 4 au plus par
    page.

    ⚠️ ``ctx.live_zones is None`` veut dire « le client ne l'a pas dit »
    et **ne filtre rien** — pas « aucune zone ». Un runtime en cache, un
    client tiers ou un test qui POSTe à la main retombent donc sur
    l'ancien comportement. Confondre les deux ferait taire toutes les
    zones du premier client qui ne parle pas la dernière version du
    protocole, et le symptôme serait une page qui cesse de se mettre à
    jour sans que rien ne lève.
    """
    if not changed_classes:
        return
    vivantes = ctx.live_zones
    queue = ctx.refresh_queue
    for cls in changed_classes:
        for zone in _ZONES_BY_DEP.get(cls, ()):
            if vivantes is not None and zone.id not in vivantes:
                continue
            if zone not in queue:
                queue.append(zone)


def _publish_broadcast(ctx: Any, qualnames: Iterable[str]) -> None:
    """Push an SSE ``state-dirty`` for each state qualname to every
    subscribed connection (tab). No-op when no broker is wired (test rigs
    bypassing the lifecycle).

    ⚠️ **L'onglet qui vient d'écrire est EXCLU** depuis le 2026-09-09.
    Il a déjà reçu ses zones dans la réponse de son action ; sa
    re-lecture renvoyait donc exactement ce qu'il affichait — un
    aller-retour PAR ZONE, pour un rendu identique qu'idiomorph diffait
    en no-op. Mesuré sur ``examples/kanban`` : cocher une sous-tâche
    coûtait **cinq requêtes et 354 Ko**, dont 177 Ko de re-lectures.

    Cette ligne a longtemps dit que l'exclusion « needs a per-tab id
    threaded through the action ; that optimization is deferred ». C'est
    exactement ce qui a été fait : le navigateur tire une identité par
    chargement de page, la porte dans l'URL du flux et dans un en-tête
    sur chaque action, et le broker saute cette connexion-là.

    On exclut l'ONGLET, pas la session — deux onglets de la même personne
    doivent continuer à se voir. Un client muet (runtime plus ancien,
    appel hors navigateur) retombe sur l'ancien comportement : il
    reçoit sa propre diffusion, ce qui est correct, juste plus cher.
    """
    broker = getattr(ctx.app, "sse_broker", None)
    if broker is None:
        return
    emetteur = getattr(ctx, "tab_id", "") or ""
    for qualname in qualnames:
        broker.publish(qualname, except_tab=emetteur)


def broadcast_deps(ctx: Any, changed_classes: set[type]) -> None:
    """Fan out ``state-dirty`` for every changed state that a
    ``broadcast=[State]`` zone depends on, so OTHER clients refetch it.

    Called by the action pipeline right after :func:`enqueue_deps`. No-op
    when no changed state feeds a broadcast zone — the common case, so the
    ``any(...)`` scan short-circuits cheaply.
    """
    if not changed_classes:
        return
    # L'index des CANAUX, pas celui des deps — c'est ici que se joue la
    # correction du 2026-08-23. Une zone qui diffuse sur ``Deals`` et lit
    # AUSSI une préférence personnelle ne publie rien quand c'est la
    # préférence qui bouge : la préférence n'est pas dans cet index.
    to_publish = [
        state_qualname(cls) for cls in changed_classes if _ZONES_BY_CHANNEL.get(cls)
    ]
    if to_publish:
        _publish_broadcast(ctx, to_publish)


def refreshable(
    fn: Callable[..., Any] | None = None,
    *,
    deps: Sequence[type] = (),
    broadcast: Sequence[type] = (),
    name: str | None = None,
) -> Any:
    """Wrap ``fn`` as a refreshable section.

    Two forms :

    - ``@refreshable`` (bare) — an imperatively-refreshed zone.
    - ``@refreshable(deps=[State], name="...")`` — a
      **declarative** zone : it re-renders when any state in ``deps``
      changes (OR-semantics), ``broadcast`` écoute les AUTRES clients
      par SSE, et ``name=`` gives a stable address for
      :func:`refresh`.

    ``deps`` et ``broadcast`` sont **deux listes orthogonales**, et la
    question qu'elles posent n'est pas la même : *qui change cet état ?*

    ==============  ====================================================
    qui le change   où on l'écrit
    ==============  ====================================================
    **moi**         ``deps`` — re-rendu DANS la réponse de l'action. Un
                    aller-retour, un swap.
    **les autres**  ``broadcast`` — signal SSE puis refetch. Deux
                    allers-retours, mais l'onglet inactif suit.
    **les deux**    les deux listes. Pas une redondance : « instantané
                    pour moi, poussé aux autres ».
    ==============  ====================================================

    ::

        @refreshable(deps=[Cart])                        # purement local
        @refreshable(broadcast=[FileAttente])            # je ne le change jamais
        @refreshable(deps=[Deals], broadcast=[Deals])    # les deux
        @refreshable(deps=[Deals, MesPrefs], broadcast=[Deals])

    Une zone est réexécutée sans arguments, hors de son appelant initial.
    Lire les paramètres nécessaires dans un état ; les paramètres nommés
    sont refusés à la décoration. Le corps peut être synchrone ou asynchrone.
    ``broadcast`` attend une liste de classes d'état, jamais un booléen.

    Free decorator — needs no app instance. The handle resolves back
    through ``sys.modules`` at request time (the realtime route's
    :func:`resolve_handler` lookup, same scheme as action handlers), so
    *registration is implicit* : binding the decorated result to a
    module attribute IS the registration. Nothing to thread the app
    through, no import of ``main.app`` from a feature module.
    """

    def _wrap(f: Callable[..., Any]) -> RefreshableHandle:
        return RefreshableHandle(
            fn=f,
            id=_stable_id(f),
            deps=tuple(deps),
            broadcast=broadcast,
            name=name,
        )

    # Bare ``@refreshable`` → decorate now ; ``@refreshable(...)`` → return
    # the decorator for Python to apply.
    return _wrap(fn) if fn is not None else _wrap


def refresh(zone_or_name: RefreshableHandle | str) -> None:
    """Force a refresh of a zone — the single imperative trigger.

    Accepts the zone **handle** (``refresh(my_zone)`` — type-safe,
    refactor-safe) or its ``name`` **string** (``refresh("my_zone")`` —
    usable from anywhere without importing the zone, e.g. a cron or webhook).
    Enqueues it for the end-of-action OOB drain with the same identity dedup
    as the declarative ``deps=`` path. Raises loudly on an unknown name
    (never a silent no-op). Reach follows the zone's ``broadcast`` flag — the
    cross-client push for ``broadcast=[State]`` is wired separately (Phase 5).
    """
    if isinstance(zone_or_name, str):
        zone = _ZONE_BY_NAME.get(zone_or_name)
        if zone is None:
            raise ValueError(
                f"refresh(): no refreshable zone named {zone_or_name!r}. "
                f"Known zones: {sorted(_ZONE_BY_NAME)}."
            )
    else:
        zone = zone_or_name
    ctx = maybe_current_context()
    if ctx is None:
        # Out of any request (cron / webhook) : there is no response to
        # attach a local OOB swap to, and no context to reach the broker
        # through. A global broker handle for cron-driven broadcast is a
        # deferred follow-up ; no-op here.
        return
    if zone not in ctx.refresh_queue:
        ctx.refresh_queue.append(zone)
    # A broadcast zone forced via refresh(x) also fans out to every
    # subscribed tab ; the acting tab additionally gets the local OOB
    # swap enqueued just above.
    if zone.broadcast:
        _publish_broadcast(ctx, zone._broadcast_qualnames())
