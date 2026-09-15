"""Per-request :class:`RenderContext` + :class:`~contextvars.ContextVar` binding.

One ``RenderContext`` is constructed per request by the render
middleware and bound on the active asyncio task. Components, state
helpers and the runtime envelope all read from it via
:func:`current_context` — no thread-local globals, no manual plumbing.

"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from bretzel.core.identity import IdGenerator
from bretzel.render.texts import DEFAULT_TEXTS

if TYPE_CHECKING:
    from bretzel.render.types import BretzelApp
    from bretzel.state.registry import StateRegistry


# ───────────────────────────────────────────────────────────────────────────
# Cookie option payload
# ───────────────────────────────────────────────────────────────────────────


# Keep the schema permissive on purpose : rendering / auth code passes
# whatever Starlette's ``Response.set_cookie`` accepts, so we don't need
# a strict TypedDict here.
CookieOptions = dict[str, Any]


# ───────────────────────────────────────────────────────────────────────────
# RenderContext
# ───────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class RenderContext:
    """The per-request scope object.

    Assembled by ``server/middleware/render_context.py`` (Layer 6) and
    consumed everywhere downstream. Direct construction is also
    supported for tests — most fields have sensible defaults.
    """

    # ── Request reference ────────────────────────────────────────────────
    # ``app`` is typed via the Protocol so render stays free of any
    # import from the server layer (CR-2 fix from the spec review).
    app: BretzelApp
    # ``Any`` rather than ``fastapi.Request`` so the unit suite can
    # exercise this layer without spinning up FastAPI ; production code
    # will receive the real thing from the middleware.
    request: Any

    # ── Identity / page wrapper ──────────────────────────────────────────
    page_uuid: str = field(
        default_factory=lambda: uuid.uuid4().hex
    )
    # Render timestamp (unix seconds, as a string) — set once per request,
    # signed into every action HMAC and baked as ``data-bz-ts``. Bounds how
    # long a captured request stays valid (``config.action_max_age``) and is
    # the idempotency key for ``@idempotent`` handlers.
    render_ts: str = field(default_factory=lambda: str(int(time.time())))
    id_generator: IdGenerator = field(default_factory=IdGenerator)
    parent_stack: list[Any] = field(default_factory=list)
    root_children: list[Any] = field(default_factory=list)
    is_rendering: bool = False  # set during the tree-walk render phase

    # ── Langue et mots du framework ──────────────────────────────────────
    #: Recopiés de la config au montage du contexte plutôt que lus à
    #: travers ``ctx.app`` : un composant qui a besoin de la langue est
    #: en couche 5, la config en couche 7, et la moitié des bancs de test
    #: construisent un ``RenderContext`` sans app complète. Les défauts
    #: ci-dessous sont donc ce que voit un composant monté hors requête.
    lang: str = "en"
    texts: Mapping[str, str] = field(default_factory=lambda: DEFAULT_TEXTS)

    # ── State + reactivity ───────────────────────────────────────────────
    # Concrete StateRegistry comes from Layer 1 ; we keep the type loose
    # to avoid a hard dependency from this dataclass header.
    state_registry: StateRegistry | None = None

    # ── Hydration payloads pre-parsed by the middleware ──────────────────
    client_state_payload: dict[str, dict[str, Any]] = field(default_factory=dict)
    form_data: dict[str, Any] = field(default_factory=dict)
    #: Pourquoi ``form_data`` est vide alors que la requête portait un
    #: formulaire — ``None`` quand tout s'est bien passé.
    #:
    #: Sans ce champ, un corps multipart illisible (part trop grosse,
    #: connexion coupée en plein envoi) rendait un formulaire VIDE et le
    #: handler tournait quand même : il lisait `""` partout et écrivait
    #: ça dans l'état. La panne n'était donc pas une erreur, c'était une
    #: SAISIE — un formulaire qui s'efface tout seul. Le dispatcher
    #: d'action refuse quand ce champ est posé.
    form_error: str | None = None

    # ── Auth ─────────────────────────────────────────────────────────────
    user_id: str | None = None
    session_id: str = ""
    csrf_token: str = ""

    #: Les zones ``@refreshable`` que le NAVIGATEUR porte réellement, ou
    #: ``None`` quand on ne sait pas.
    #:
    #: La distinction est tout le mécanisme : ``None`` veut dire « je
    #: n'ai pas l'information » — un runtime en cache, un client tiers,
    #: un test qui POSTe à la main — et le drain ne filtre alors rien,
    #: exactement comme avant. Un ensemble VIDE voudrait dire « ce
    #: document ne porte aucune zone », ce que le runtime n'envoie
    #: jamais (il omet l'en-tête dans ce cas). Confondre les deux ferait
    #: taire toutes les zones au premier client qui ne parle pas la
    #: dernière version du protocole, sans une erreur.
    live_zones: frozenset[str] | None = None

    #: ``{id de zone: empreinte}`` que le navigateur dit AFFICHER, lu du
    #: même en-tête que :attr:`live_zones`. Sert à taire une zone dont le
    #: rendu neuf est identique. Vide quand le client se tait — donc le
    #: comportement par défaut est d'expédier.
    zone_hashes: dict[str, str] = field(default_factory=dict)

    #: L'onglet qui a émis la requête courante, ou ``""`` s'il se tait
    #: (un runtime plus ancien, un appel hors navigateur). Sert à ne pas
    #: lui rediffuser ce qu'il vient de recevoir — cf.
    #: :data:`~bretzel.runtime.protocol.HEADER_TAB`.
    tab_id: str = ""

    # ── Pipeline state ───────────────────────────────────────────────────
    layout: Callable[..., Any] | None = None
    # Stack of active layout function names. Pushed when the pipeline
    # invokes a layout, popped on the way out. Nested layouts (parent=)
    # appear in outer→inner order ; ``Outlet.__init__`` reads the
    # tail to derive its ``outlet_<layout>`` id, ``SidebarItem.__init__``
    # reads the same to plumb ``hx-target=#outlet_<layout>``.
    layout_stack: list[str] = field(default_factory=list)
    #: Les ``ui.sidebar`` construites pendant CE rendu. Sert deux
    #: questions qui ne se repondent qu'une fois la page batie :
    #: resoudre a QUELLE barre un ``ui.sidebar_trigger`` sans argument
    #: parle, et verifier qu'une barre escamotable a bien un moyen
    #: d'etre rouverte — sinon la navigation est injoignable, en
    #: silence (mesure le 2026-08-24 : aside a x=-256, ZERO element
    #: cliquable a l'ecran, page a 200).
    sidebars: list[Any] = field(default_factory=list)
    #: Les ``ui.sidebar_trigger`` construits pendant CE rendu. Resolus
    #: par ``base/_wiring.wire_sidebar_triggers`` quand l'arbre est bati,
    #: pas a la construction : sinon un declencheur ecrit AVANT la barre
    #: — une coque qui pose sa barre du haut d'abord — ne trouverait
    #: rien, et la garde d'atteignabilite le prendrait pour une absence.
    #: Meme lecon que les barres ``sticky`` : l'ordre d'ecriture ne doit
    #: pas changer le verdict.
    sidebar_triggers: list[Any] = field(default_factory=list)
    #: Les barres ``sticky`` construites pendant CE rendu, chacune avec
    #: son nom d'appel et le fichier:ligne qui l'a ecrite. Remplie par
    #: ``base/_wiring.register_sticky_bar``, videe par la passe de
    #: ``render/pipeline._drain``.
    #:
    #: **Pourquoi une liste et pas un controle a la construction** :
    #: « suis-je bien placee ? » est une question posee a l'ARBRE, et
    #: l'arbre n'existe pas encore quand la barre se construit. Deux
    #: defauts mesures le 2026-08-24 le prouvent — une barre ecrite AVANT
    #: le ``ui.viewport`` ne peut pas savoir qu'un cadre va venir, et une
    #: barre enveloppee dans un ``ui.fragment`` n'a pas son vrai parent de
    #: DISPOSITION sur ``parent_stack``. Les deux rendaient une page
    #: cassee en silence.
    #:
    #: Vide sur l'immense majorite des rendus : seules ``ui.bottom_bar``
    #: et ``ui.navbar(sticky=True)`` s'y inscrivent, donc la passe ne
    #: part meme pas.
    sticky_bars: list[Any] = field(default_factory=list)
    #: ``{classe d'etat: {champs modifies}}`` pour CETTE requete, pose
    #: par la route d'action depuis ``StateRegistry.diff_and_notify``.
    #: **Vide veut dire « on ne sait pas »**, pas « rien n'a change » :
    #: un rendu de page complet et un refetch SSE le laissent vide, et
    #: doivent donc tout re-rendre. Tout lecteur doit traiter le vide
    #: comme le cas conservateur.
    changed_fields: dict = field(default_factory=dict)
    is_partial: bool = False
    # Two distinct flows flip ``is_partial`` :
    #
    # - **Partial nav** (``server/routing/pages.py``) : an htmx-boosted
    #   internal link sends ``HX-Request: true`` + ``HX-Target: outlet_X``
    #   matching a layout in the page's chain. Sets ``partial_target =
    #   "outlet_X"`` so the pipeline can slice the layout chain at the
    #   right depth (``_slice_chain_for_partial``).
    # - **Refreshable / action OOB drain** (``render/partials.py``) :
    #   flipped to skip the shell + envelope when emitting refreshable
    #   OOB fragments. ``partial_target`` stays ``None`` — the pipeline
    #   only renders what the action-driven refresh queue produced, no
    #   layout walk involved.
    #
    # So ``partial_target`` is set ONLY in the partial-nav flow ; the
    # action-drain flow leaves it ``None`` and that's expected.
    partial_target: str | None = None
    is_action: bool = False
    refreshable_target: str | None = None

    #: Le jeton qui rend les ``bz-id`` de la page UNIQUES À CETTE PAGE.
    #:
    #: Le défaut qu'il ferme, mesuré le 2026-08-13 : le magasin de scopes
    #: du runtime est une ``Map`` indexée par le ``bz-id`` **chaîne**
    #: (``03_scope.js``), et un ``hx-boost`` ne recharge pas le runtime. Or
    #: un ``bz-id`` décrit une POSITION dans l'arbre
    #: (``outlet_shell_container_0_…_accordion_0``) et ne dit rien de la
    #: page. Deux pages de même forme produisaient donc la même clé : sur
    #: les 68 pages du playground, **13 collisions** hors du shell — un
    #: tooltip sur 13 pages, un dialog sur 7. Après une navigation, le
    #: scope de la page précédente était retrouvé par son id et ses
    #: valeurs l'emportaient sur le littéral frais du serveur (ouvrir
    #: l'accordéon de ``/accordion``, aller sur ``/markdown``, il y arrive
    #: ouvert ; un F5 le rend correctement).
    #:
    #: ⚠️ Il qualifie l'id que l'outlet donne à ses ENFANTS, jamais l'id
    #: que l'outlet REND : htmx renvoie ce dernier en ``HX-Target``, donc
    #: le bouger casserait le rendu partiel à la navigation suivante.
    #:
    #: Le CHEMIN et pas la route : ``/contacts/5`` et ``/contacts/9`` sont
    #: deux pages pour l'utilisateur, et partager leur état ferait fuir
    #: l'accordéon d'un contact à l'autre. La query en est exclue —
    #: ``/issues?tri=date`` est la même page qu'``/issues``.
    page_scope: str = ""

    @property
    def child_scope_root(self) -> str:
        """Le suffixe à coller à un id de parent pour le rendre page-unique.

        Vide quand ``page_scope`` l'est — hors requête (bancs, tests
        unitaires) les ids gardent exactement leur forme d'avant, ce qui
        laisse intacts les inventaires et les captures qui les citent.
        """
        return f"__{self.page_scope}" if self.page_scope else ""


    # ── Outgoing — applied to the response by the middleware ─────────────
    new_cookies: dict[str, CookieOptions] = field(default_factory=dict)
    deleted_cookies: set[str] = field(default_factory=set)
    response_headers: dict[str, str] = field(default_factory=dict)
    head_extras: list[Any] = field(default_factory=list)
    # Page-level title override — ``ui.title("…")`` writes here. When
    # set, supersedes the ``@page(title=…)`` decorator value in
    # the pipeline (last call wins, so the deepest ``ui.title()`` in
    # the render scope is the one that ships).
    head_title: str | None = None

    # Pending refreshable handles whose ``.refresh()`` was called during
    # this request — drained by the partial-renderer at end-of-action
    # to emit OOB swap fragments.
    refresh_queue: list[Any] = field(default_factory=list)

    # Zones ``@refreshable`` ASYNC dont le corps reste à attendre.
    #
    # Une zone s'appelle ``zone()``, sans ``await``, y compris quand son
    # corps est une coroutine : c'est la convention d'appel du framework,
    # et elle ne change pas parce qu'une lecture devient asynchrone.
    # ``RefreshableHandle.__call__`` pose donc la SECTION dans l'arbre
    # immédiatement — la place de la zone dans la page est décidée au
    # moment de l'appel, pas au moment où sa donnée arrive — puis empile
    # ici ``(section, coroutine)``. Le pipeline draine la file quand le
    # corps de la page a fini.
    #
    # Une liste, pas un ``gather`` : les zones s'attendent en SÉRIE parce
    # qu'elles partagent ``parent_stack`` — deux corps concurrents
    # s'enregistreraient l'un chez l'autre. La concurrence, si elle est
    # voulue un jour, se prend DANS un corps de zone (``asyncio.gather``
    # sur ses requêtes), pas entre les zones.
    #
    # Drainée en BOUCLE : une zone async peut en appeler une autre, qui
    # s'ajoute ici pendant qu'on attend la première.
    pending_async_zones: list[Any] = field(default_factory=list)

    # Toast notifications queued by ``ui.notification(...)`` during the
    # request. Drained by the partial-renderer at end-of-action : elles
    # partent dans un ``<bz-patch>`` sous la clé réservée
    # ``_notifications``, que le bridge forwarde à ``$bz.notify``. Le
    # toaster s'auto-monte au premier toast (pas de container à monter).
    notifications: list[dict[str, Any]] = field(default_factory=list)

    # Components register their callable event handlers here at render
    # time — the action-route handler in Layer 6 reads this map (or
    # the encoded ``module::qualname`` form) to dispatch incoming
    # requests. Closure / lambda handlers are rejected at registration
    # time (see :py:meth:`register_action`).
    action_registry: dict[str, Callable[..., Any]] = field(default_factory=dict)

    # ── End-of-request hooks ─────────────────────────────────────────────
    cleanup_callbacks: list[Callable[[], None]] = field(default_factory=list)

    # ── Helper methods ───────────────────────────────────────────────────

    def set_cookie(self, name: str, value: str, **opts: Any) -> None:
        """Schedule ``Set-Cookie`` to be emitted on the response.

        Cancels any pending ``delete_cookie`` for the same name — the
        last write wins, just like Starlette's own behaviour.
        """
        self.new_cookies[name] = {"value": value, **opts}
        self.deleted_cookies.discard(name)

    def delete_cookie(self, name: str) -> None:
        """Schedule the cookie to be cleared on the response."""
        self.deleted_cookies.add(name)
        self.new_cookies.pop(name, None)

    def set_header(self, name: str, value: str) -> None:
        """Set a custom response header (``HX-Trigger``, ``Cache-Control``, …)."""
        self.response_headers[name] = value

    def register_action(
        self,
        handler: Callable[..., Any],
        component_id: str,
        event: str,
    ) -> tuple[str, str, str]:
        """Register a component event handler ; return its wire triplet.

        Returns ``(action_id, args_blob, sig)`` — the component layer
        turns it into the V3 HTMX attribute set via
        :func:`bretzel.components.base.events.action_attrs`
        (``hx-post`` + ``hx-vals`` + ``data-bz-sig``). The action route
        verifies the sig (forwarded as ``X-Bz-Sig`` by the runtime
        bridge) before resolving the callable.
        """
        from bretzel.components.base.events import encode_handler_id
        from bretzel.server.handlers import encode_args, sign_action

        action_id = encode_handler_id(handler)
        # Multiple components binding the same module-level handler
        # share the same id — the registry stores it once. For a
        # ``functools.partial``, the underlying ``handler.func`` is
        # what the server will resolve through ``sys.modules`` ; the
        # bound args ride separately via the ``_args`` form field.
        self.action_registry.setdefault(action_id, handler)

        # Bound args (from a ``partial``) → base64-JSON blob. Empty
        # string for plain callables.
        args_blob = encode_args(handler)

        # Pre-sign the (id, args_blob) pair at render time. No key
        # available (test rigs, plain ``RenderContext`` with no app
        # attached) → empty sig ; the call won't verify but unit tests
        # don't go through the route either.
        action_key = self._action_key()
        sig = (
            sign_action(action_key, action_id, args_blob, ts=self.render_ts)
            if action_key
            else ""
        )
        return action_id, args_blob, sig

    def _action_key(self) -> bytes:
        """Pull the derived action key from ``app.config``, else empty bytes."""
        config = getattr(self.app, "config", None)
        return getattr(config, "_action_key", b"") if config is not None else b""

    def add_cleanup(self, callback: Callable[[], None]) -> None:
        """Register a cleanup ; callbacks fire in LIFO order at request end."""
        self.cleanup_callbacks.append(callback)

    def run_cleanups(self) -> None:
        """Drain :attr:`cleanup_callbacks` in LIFO order.

        Each callback runs with its own ``try/except`` so a misbehaving
        one doesn't poison the rest. Errors are logged but never
        re-raised — the response has already been sent at this point.
        """
        while self.cleanup_callbacks:
            cb = self.cleanup_callbacks.pop()
            try:
                cb()
            except Exception as exc:
                # Stdlib logging avoids dragging an extra dep in the
                # render layer's import surface.
                import logging
                logging.getLogger("bretzel.render").exception(
                    "render cleanup callback failed", exc_info=exc
                )


# ───────────────────────────────────────────────────────────────────────────
# Context-var binding
# ───────────────────────────────────────────────────────────────────────────


_CURRENT: ContextVar[RenderContext | None] = ContextVar(
    "bretzel_render_context", default=None
)


def current_context() -> RenderContext:
    """Return the active context. Raises if called outside a render scope.

    Components and state helpers rely on this to discover their
    surrounding request without explicit plumbing.
    """
    ctx = _CURRENT.get()
    if ctx is None:
        raise RuntimeError(
            "No render context is active. This function must be called "
            "from within a request — typically from a @page handler, a "
            "@refreshable scope, or a component's render() method."
        )
    return ctx


def maybe_current_context() -> RenderContext | None:
    """Variant that returns ``None`` outside a render scope (no raise)."""
    return _CURRENT.get()


_UNSAFE_IN_ID = re.compile(r"[^A-Za-z0-9]+")


def page_scope_of(ctx: RenderContext) -> str:
    """Le jeton de page, derive du CHEMIN de la requete.

    Le meme pour un chargement complet et pour une navigation boostee de
    la meme URL — c'est la condition pour que
    ``test_partial_nav_keeps_identity`` continue de tenir : les deux
    chemins d'arrivee doivent produire les MEMES ids.

    Rend ``""`` hors requete (bancs, ``render_isolated``), et les ids
    gardent alors leur forme d'avant.
    """
    url = getattr(getattr(ctx, "request", None), "url", None)
    chemin = getattr(url, "path", None)
    if not isinstance(chemin, str) or not chemin:
        return ""
    return _UNSAFE_IN_ID.sub("_", chemin).strip("_") or "racine"


@contextmanager
def use_context(ctx: RenderContext) -> Iterator[None]:
    """Bind ``ctx`` as the active context for the duration of the block.

    Used by the pipeline once per request. Nested calls compose : on
    exit, the previously-bound context (if any) is restored, so unit
    tests can spin up a temporary context without disturbing the outer
    scope.
    """
    token = _CURRENT.set(ctx)
    try:
        yield
    finally:
        _CURRENT.reset(token)
