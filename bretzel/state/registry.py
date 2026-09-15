"""Per-request state registry.

Holds three responsibilities :

1. **Per-request instance cache.** Calling ``CartState()`` twice during
   the same request must return the same instance — otherwise mutations
   in one place wouldn't be visible in another. The metaclass
   :class:`bretzel.state.base._StateMeta` intercepts construction and
   delegates to the registry when one is active.

2. **Backend orchestration.** :py:meth:`resolve` async-loads a
   :class:`~bretzel.state.scopes.server.ServerState` from the
   :class:`~bretzel.state.persistence.base.Backend` ; :py:meth:`commit`
   saves every dirty server-side state at end of request.

3. **Client-side hydration.** When the request's client-state payload
   has been parsed from namespaced form-data in the POST body, ``ClientState``
   instances pick up the client-supplied values automatically on
   construction.

The registry is bound to the active async task via
:class:`~contextvars.ContextVar` ; concurrent requests have isolated
registries with no manual plumbing.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

import anyio.from_thread

# Canonical definitions live in ``core`` so the state and server layers use
# the same exception classes without violating the import DAG.
from bretzel.core.errors import AuthRequiredError, BretzelError
from bretzel.core.tracking import TRACKER
from bretzel.state.base import State
from bretzel.state.persistence.base import Backend
from bretzel.state.scopes.client import ClientState
from bretzel.state.scopes.server import ServerScope, ServerState
from bretzel.state.types import encode_value
from bretzel.state.url import apply_url_params, collect_url_params

if TYPE_CHECKING:
    from bretzel.state.locking import StateLock

# Sentinel for "field absent from a snapshot" — distinct from any real
# field value (including ``None``) so an added/removed field diffs as a
# change.
_ABSENT: Any = object()

# ───────────────────────────────────────────────────────────────────────────
# Errors
# ───────────────────────────────────────────────────────────────────────────


class ScopeConfigError(RuntimeError):
    """Raised when scope-specific identity is missing (no session id …)."""


class StateHydrationError(BretzelError):
    """Levée quand un ``ServerState`` ne PEUT pas être hydraté sur place.

    Le cas unique : un backend sans ``load_sync`` (Redis) atteint depuis
    le thread de la boucle, donc depuis du code d'app ``async def``. On
    ne peut pas y attendre — bloquer la boucle gèlerait le worker
    entier —, et rendre les défauts serait pire : le commit de fin de
    requête ÉCRASERAIT la valeur stockée par un objet vide. L'erreur
    nomme le geste qui marche (``await MonEtat.load()``).
    """


# ───────────────────────────────────────────────────────────────────────────
# Default TTLs per scope (seconds). Overridable via Bretzel(...) config.
# ───────────────────────────────────────────────────────────────────────────


# Mapping from ``.claude/bretzel/state.md`` § *TTL per scope* :
DEFAULT_TTLS: dict[str, int | None] = {
    "session": 24 * 3600,  # 24 hours (independent of the session cookie, which defaults to 30 days — cf. config.session_max_age_days)
    "user": None,  # account-scoped, no expiry
    "app": None,  # process-lived defaults
    # ``page`` lives as long as the user stays on the same render of
    # the page ; we cap it at 1 hour as a safety net (long-idle tabs
    # whose UUIDs the server has long forgotten).
    "page": 3600,
}


# ───────────────────────────────────────────────────────────────────────────
# Context-var binding
# ───────────────────────────────────────────────────────────────────────────


_CURRENT: ContextVar[StateRegistry | None] = ContextVar(
    "bretzel_current_registry", default=None
)


def current_registry() -> StateRegistry | None:
    """Return the registry bound to the active async task, if any.

    Used by the metaclass to intercept state construction. Returns
    ``None`` outside of a request — direct ``CartState()`` then behaves
    as a vanilla constructor (useful in tests).
    """
    return _CURRENT.get()


@contextmanager
def use_registry(registry: StateRegistry) -> Iterator[None]:
    """Bind a registry as the active one for the current task."""
    token = _CURRENT.set(registry)
    try:
        yield
    finally:
        _CURRENT.reset(token)


# ───────────────────────────────────────────────────────────────────────────
# Registry
# ───────────────────────────────────────────────────────────────────────────


class StateRegistry:
    """Per-request resolver, hydrator and committer."""

    def __init__(
        self,
        backend: Backend,
        *,
        client_payload: dict[str, dict[str, Any]] | None = None,
        form_data: dict[str, Any] | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        page_id: str | None = None,
        url_params: dict[str, str] | None = None,
        ttls: dict[str, int | None] | None = None,
    ) -> None:
        self._backend = backend
        self._client_payload: dict[str, dict[str, Any]] = client_payload or {}
        # ``form_data`` is set by the request middleware after parsing the
        # body (multipart / urlencoded) and exposed to user code via
        # :func:`bretzel.state.form_value`.
        self.form_data: dict[str, Any] = form_data or {}
        self._session_id = session_id
        self._user_id = user_id
        # Page-scope identity : the ``bz-page-<uuid>`` stamp generated
        # at full-document render and echoed back via the
        # ``X-Bretzel-Page-ID`` header on every action POST. Identical
        # uuid across actions on the same page → state continuity ;
        # F5 / navigate → fresh uuid → fresh PageState.
        self._page_id = page_id
        #: Les paramètres de l'URL COURANTE, par valeur. La couche
        #: ``state`` est sous ``render`` et ``server`` dans le DAG : elle
        #: ne peut pas remonter lire la requête, donc l'appelant les lui
        #: passe — exactement comme ``page_id`` et ``session_id``.
        self._url_params: dict[str, str] = dict(url_params or {})
        self._ttls = {**DEFAULT_TTLS, **(ttls or {})}
        self._instances: dict[tuple[type[State], str], State] = {}
        #: ``{classe: {champs modifies}}``, rempli par
        #: :meth:`diff_and_notify`. Vide tant qu'aucun diff n'a tourne —
        #: donc vide sur un rendu de page complet, ce qui est la bonne
        #: valeur par defaut : « on ne sait pas ce qui a change » doit
        #: faire tout re-rendre.
        self.changed_fields: dict[type[State], set[str]] = {}

    # ── Cache primitives — used by the metaclass on every State() call ──

    def get_cached(self, cls: type[State], key: str = "default") -> State | None:
        return self._instances.get((cls, key))

    def register(self, instance: State, key: str = "default") -> None:
        self._instances[(type(instance), key)] = instance
        if isinstance(instance, ServerState):
            # ── DEUX photos, et le semis d'URL passe ENTRE les deux ──
            #
            # ``deepcopy`` des deux côtés : ``_field_values`` rend des
            # références vivantes, donc une copie de surface aliaserait
            # une mutation en place et le diff ne verrait rien.

            # ① ce qui vient DU STOCKAGE. Le commit s'en sert pour
            # n'écrire que les champs modifiés, donc ne pas écraser ce
            # qu'une requête concurrente a mis dans les autres. Prise
            # AVANT le semis : sinon un ``?tri=nom`` se lit comme « déjà
            # stocké », n'est jamais écrit, et l'action suivante — dont
            # l'URL ne porte aucune query — retrouve l'ancien tri.
            # Mesuré : le tri revenait à son défaut au premier clic.
            instance._bz_stored = copy.deepcopy(instance._field_values())

            # « Absent = on ne touche à rien » : c'est ce qui fait que la
            # mécanique marche aussi sur une action, dont l'URL ne porte
            # aucune query — l'état garde ce qu'il avait.
            apply_url_params(instance, self._url_params)

            # ② la référence des MUTATIONS, prise APRÈS le semis : avant,
            # le semis se lirait comme une mutation, l'état partirait
            # ``dirty``, et la première page rendue pousserait une URL
            # alors que rien n'a bougé. ``diff_and_notify`` la re-prend à
            # chaque action — c'est pour ça qu'elle ne peut pas servir au
            # commit, qui a besoin d'un point fixe.
            instance._bz_baseline = copy.deepcopy(instance._field_values())

    # ── Sync-load fast path (called from the State metaclass) ──────────

    def try_sync_resolve(
        self,
        cls: type[State],
        key: str = "default",
    ) -> State | None:
        """Hydrate a ``ServerState`` from the backend synchronously.

        Used by :meth:`bretzel.state.base._StateMeta.__call__` to keep
        ``MyState()`` synchronous whatever the backend. Deux chemins,
        et le second est la raison d'être de ce commentaire :

        - le backend expose ``load_sync`` (mémoire) → lecture directe ;
        - il ne l'expose pas (Redis) → :meth:`_load_via_loop` fait
          exécuter le ``load`` async PAR la boucle et attend son
          résultat depuis le thread du pool.

        ⚠️ Le second chemin n'existait pas avant le 2026-09-04, et il
        n'était pas écrivable : c'est le délestage du code d'app sur le
        threadpool (``core/invoke.py``) qui donne un thread où l'on a le
        DROIT d'attendre. Jusque-là on rendait ``None`` ici, donc les
        valeurs par défaut, donc — le commit ne regardant que le drapeau
        ``_dirty`` — la première mutation écrasait ce qui était stocké.

        Returns the hydrated instance (already registered in the
        cache) or ``None`` when the backend holds no entry for it.
        """
        scope = getattr(cls, "__scope__", None)
        if scope is None:
            # Bare ``State`` has no scope — nothing to look up.
            return None

        try:
            storage_key = self._compose_storage_key(
                scope, cls.__name__, key  # type: ignore[arg-type]
            )
        except ScopeConfigError:
            # No identity for this scope (e.g. user-scope without auth) —
            # leave the metaclass to construct a fresh defaults instance.
            return None

        load_sync = getattr(self._backend, "load_sync", None)
        if callable(load_sync):
            raw = load_sync(scope, storage_key)
        else:
            raw = self._load_via_loop(cls, scope, storage_key)
        if raw is None:
            return None

        return self._build(cls, key, raw)

    def _build(
        self,
        cls: type[State],
        key: str,
        raw: dict[str, Any] | None,
    ) -> State:
        """Construire l'instance hydratée et l'inscrire au cache.

        ⚠️ ``type.__call__`` et non ``cls(...)`` : la métaclasse
        intercepte la seconde forme et RELANCE une hydratation, donc un
        appel depuis :meth:`resolve` — qui vient justement de lire le
        backend — retomberait dans :meth:`try_sync_resolve`. Sur la
        boucle, cette rentrée lève au lieu de rendre l'objet qu'on tient
        déjà : mesuré le 2026-09-04, ``await MonEtat.load()`` échouait
        avec l'erreur qui recommande… ``await MonEtat.load()``.

        Le même geste sert les deux chemins de lecture, sync et async :
        deux constructions concurrentes finiraient par diverger, et la
        version qui restait dans ``resolve`` (``cls.from_dict``) passait
        elle aussi par la métaclasse.
        """
        instance = type.__call__(cls, key=key)
        if raw is not None:
            instance._apply_fields(raw)
            # On vient de LIRE : ce n'est pas une mutation d'utilisateur.
            instance._dirty = False
        self.register(instance, key)
        return instance

    def _load_via_loop(
        self,
        cls: type[State],
        scope: str,
        storage_key: str,
    ) -> dict[str, Any] | None:
        """Faire lire le backend async-only PAR la boucle, et attendre.

        Appelé depuis un thread du pool — c'est là que tourne tout code
        d'app ``def`` depuis le délestage. Bloquer ce thread ne gèle
        rien : la boucle, elle, continue de servir les autres requêtes,
        et c'est même elle qui exécute le ``load``.

        C'est l'INVERSE exact de :func:`bretzel.core.call_without_blocking`,
        et c'est pourquoi il n'y a pas de discriminant écrit à la main
        ici : ``anyio.from_thread.run`` ne marche QUE depuis un thread
        que ``anyio.to_thread.run_sync`` a ouvert, et il le dit avec une
        exception à lui. Un appel resté sur la boucle — du code d'app
        ``async def`` — tombe donc dans le ``except``, là où bloquer
        aurait gelé le worker.

        Lever est délibérément plus brutal que l'ancien ``return None``,
        qui rendait des défauts que le commit réécrivait ensuite
        par-dessus la valeur stockée.
        """
        try:
            return anyio.from_thread.run(self._backend.load, scope, storage_key)
        except anyio.from_thread.NoEventLoopError:
            raise StateHydrationError(
                f"{cls.__name__}() ne peut pas s'hydrater ici : le backend "
                f"{type(self._backend).__name__} lit de façon asynchrone, et "
                f"ce code tourne sur la boucle — y attendre la gèlerait pour "
                f"tout le monde. Écris "
                f"`etat = await {cls.__name__}.load()`, ou passe ce corps en "
                f"`def` (le framework le délestera sur un thread, où "
                f"`{cls.__name__}()` marche tel quel)."
            ) from None

    # ── Server-side resolution ──────────────────────────────────────────

    async def resolve(
        self,
        cls: type[ServerState],
        key: str = "default",
    ) -> ServerState:
        """Return a hydrated instance of ``cls``, loading from backend if
        needed.

        Cached after the first call : two ``await registry.resolve(...)``
        on the same ``(cls, key)`` return the same instance.
        """
        cached = self._instances.get((cls, key))
        if cached is not None:
            assert isinstance(cached, cls)
            return cached

        scope = cls.__scope__

        # ``page`` scope persists keyed by ``page_id`` — same uuid
        # across actions on one rendered page, fresh uuid on
        # reload / navigation.
        storage_key = self._compose_storage_key(scope, cls.__name__, key)
        raw = await self._backend.load(scope, storage_key)
        return self._build(cls, key, raw)  # type: ignore[return-value]

    # ── Client-side hydration ───────────────────────────────────────────

    def hydrate_client(self, instance: ClientState) -> None:
        """Apply the request's parsed client-state payload (V3 :
        namespaced form-data from the POST body) to ``instance`` if a
        matching entry exists.

        Hydration is direct attribute assignment, which goes through
        ``Field.__set__`` → field validators run, dirty flag flips. We
        reset ``_dirty`` afterwards : an inbound payload is not a user
        mutation that should propagate back as a save.
        """
        envelope_key = f"{type(instance).__name__}.{instance._key}"
        data = self._client_payload.get(envelope_key)
        if data is None:
            return
        instance._apply_fields(data)
        instance._dirty = False

    async def reload(self, cls: type[State], key: str = "default") -> State:
        """Relire cet état DEPUIS le magasin, et rafraîchir l'instance.

        Muter l'instance en place plutôt que d'en poser une neuve : une
        variable prise avant le bloc (``store = Kanban()``) doit voir les
        valeurs fraîches elle aussi, sinon le verrou protégerait un objet
        que l'appelant n'utilise pas.

        Les champs ABSENTS du magasin retrouvent leur défaut — une ligne
        supprimée doit se lire comme supprimée, pas comme ce qu'on avait
        en mémoire.

        Les deux photos sont reprises : ce qu'on vient de lire EST l'état
        du magasin, donc l'écriture de sortie ne doit envoyer que ce que
        le bloc aura changé.
        """
        scope = cls.__scope__  # type: ignore[attr-defined]
        storage_key = self._compose_storage_key(scope, cls.__name__, key)
        raw = await self._backend.load(scope, storage_key)

        instance = self._instances.get((cls, key))
        if instance is None:
            return self._build(cls, key, raw)

        for nom, fld in type(instance)._all_fields().items():
            if raw is not None and nom in raw:
                continue
            # Pas dans le magasin : retirer la valeur posée fait
            # réapparaître le défaut déclaré.
            instance.__dict__.pop(fld._storage_key, None)
        if raw:
            instance._apply_fields(raw)
        instance._dirty = False
        photo = copy.deepcopy(instance._field_values())
        instance._bz_stored = photo
        instance._bz_baseline = copy.deepcopy(photo)
        return instance

    def lock(
        self,
        cls: type[State],
        key: str = "default",
        *,
        ttl: int | None = None,
        timeout: float | None = None,
    ) -> StateLock:
        """Le gestionnaire de contexte de ``MonEtat.lock()``."""
        from bretzel.state.locking import (
            DEFAULT_LOCK_TIMEOUT,
            DEFAULT_LOCK_TTL,
            StateLock,
        )

        return StateLock(
            self,
            cls,  # type: ignore[arg-type]
            key,
            ttl=DEFAULT_LOCK_TTL if ttl is None else ttl,
            timeout=DEFAULT_LOCK_TIMEOUT if timeout is None else timeout,
        )

    # ── End-of-request commit ───────────────────────────────────────────

    async def commit(self) -> None:
        """Persist every dirty :class:`ServerState` to the backend.

        ``ClientState`` is not committed — its mutations are emitted via
        the response delta and applied client-side. Every server scope
        (``session`` / ``user`` / ``app`` / ``page``) flows through
        ``_compose_storage_key`` and gets its own row.

        **On écrit les CHAMPS modifiés, pas le document.** Réécrire le
        document entier effaçait ce qu'une requête concurrente venait
        d'écrire dans les autres champs : deux onglets, la requête A
        change le filtre, la requête B le panier, et la dernière à
        commiter rendait l'autre changement invisible — sans erreur,
        sans trace. Le registre connaît les champs touchés (la photo
        prise à la lecture) et le backend applique la fusion
        atomiquement, donc B ne peut plus effacer A.

        ⚠️ Deux requêtes qui modifient LE MÊME champ perdent toujours
        une écriture, et c'est un test qui tient cette limite plutôt
        qu'une phrase :
        ``tests/unit/state/test_a_commit_keeps_a_concurrent_field.py``.

        ⚠️ L'atomicité est **par ligne, pas par requête** : une requête
        qui touche trois états fait trois écritures atomiques
        indépendantes, et un échec en laisse une partie persistée. Vrai
        avant le groupage, vrai après — mais le groupage change QUELLE
        partie, et en mieux : cf. plus bas.

        Un état marqué sale dont aucun champ n'a bougé n'écrit RIEN :
        le cas se produit quand une mutation revient à sa valeur
        d'origine dans la même requête.

        **Les écritures partent ENSEMBLE.** Une boucle ``await`` payait
        un aller-retour réseau par état, en série : mesuré le
        2026-09-05, le pic de simultanéité valait 1 et la durée était
        N fenêtres de RTT, contre une seule une fois groupées (8 états :
        224 ms → 25 ms à 20 ms de RTT simulé ; le gain est
        ``(N-1) × RTT`` par construction, soit ~3 ms sur 4 états à 1 ms
        de RTT Redis). Le nombre d'appels ne change pas — c'est leur
        chevauchement qui change.

        ⚠️ ``asyncio.gather`` et **pas** un groupe de tâches anyio, et
        c'est le mode d'échec qui tranche, pas le style. Un groupe de
        tâches annule ses frères dès la première erreur, donc il
        persisterait MOINS que la boucle séquentielle qu'il remplace.
        ``gather`` laisse les écritures déjà en vol aboutir : sur un
        échec, les N-1 autres états sont quand même enregistrés, et
        c'est strictement mieux que l'ancien comportement où tout ce qui
        suivait l'erreur était perdu. L'exception, elle, remonte pareil.

        Chaque ``write_one`` ne touche que SON instance (son écart, sa
        photo) ; rien n'est partagé entre les coroutines, hors le
        backend qui est prévu pour.
        """
        # ``gather`` accepte zéro et une coroutine : un raccourci pour ces
        # deux cas a existé le temps d'une relecture, et il coûtait un
        # SECOND site d'appel de ``write_one`` à tenir d'accord avec le
        # premier — dans la méthode dont la docstring dit justement qu'un
        # calcul dupliqué « aurait divergé au premier changement ». Ce
        # qu'il économisait, une ``Task`` (~µs), est trois ordres de
        # grandeur sous le RTT que ce groupage sert à masquer.
        await asyncio.gather(
            *(
                self.write_one(cls, key, instance)
                for (cls, key), instance in self._instances.items()
                if instance._dirty and isinstance(instance, ServerState)
            )
        )

    async def write_one(
        self, cls: type[State], key: str, instance: ServerState
    ) -> None:
        """Écrire UN état : les champs modifiés depuis sa photo.

        Extrait de :meth:`commit` pour que le verrou (:meth:`lock`) écrive
        exactement de la même façon en sortant de son bloc. Deux calculs
        d'écart séparés auraient divergé au premier changement — et c'est
        le calcul qui porte toute la correction de la mise à jour perdue.
        """
        scope = cls.__scope__  # type: ignore[attr-defined]
        try:
            storage_key = self._compose_storage_key(scope, cls.__name__, key)
        except ScopeConfigError:
            # No identity available (e.g. page-scope without a
            # page_id, or user-scope without auth) — skip rather
            # than crash. Mutations land in-memory only.
            return
        ttl = self._ttls.get(scope)
        current = instance.to_dict()
        stored = instance._bz_stored
        # On parcourt ``current``, PAS l'union des deux : la photo
        # porte les valeurs effectives (défauts compris) et
        # ``to_dict`` seulement les champs posés, donc une clé
        # présente d'un côté et pas de l'autre est normale, et n'est
        # pas un changement. ``diff_and_notify``, qui compare deux
        # photos de MÊME forme, prend l'union — chacune a raison
        # pour sa question.
        fields = type(instance)._all_fields()
        changes: dict[str, Any] = {}
        deltas: dict[str, Any] = {}
        for name, value in current.items():
            lue = stored.get(name, _ABSENT)
            if lue == value:
                continue
            fld = fields.get(name)
            if fld is not None and fld.merge == "add" and lue is not _ABSENT:
                # Un champ additif s'écrit en ÉCART, pas en valeur : le
                # magasin l'applique sans lire, donc deux requêtes qui
                # ont lu le même nombre comptent toutes les deux. Un
                # écart nul n'écrit rien.
                ecart = value - lue
                if ecart:
                    deltas[name] = ecart
            else:
                changes[name] = value
        if changes or deltas:
            # Encodé ICI, et pas dans les backends : c'est ce qui empêche
            # la mémoire et Redis de diverger. Avant, la mémoire gardait
            # l'objet Python vivant, donc un champ ``date`` marchait en
            # dev et levait le jour du branchement Redis.
            await self._backend.merge(
                scope,
                storage_key,
                {n: encode_value(v) for n, v in changes.items()},
                add=deltas,
                ttl=ttl,
            )
            # La photo suit ce qu'on vient de poser — les champs
            # écrits seulement, pas tout l'état : un second commit
            # dans la même requête ne doit pas les ré-écrire, et
            # deepcopier l'état entier coûterait 1,6 ms sur mille
            # lignes pour un champ qui bouge.
            #
            # Pour un additif, la photo prend la valeur LOCALE et non
            # le total vrai : le magasin a peut-être compté les
            # contributions d'autres requêtes, qu'on ne relit pas.
            # C'est assumé — la page affiche ce que cette requête a
            # calculé, et le rafraîchissement suivant montrera le
            # total.
            pose = {**changes, **{n: current[n] for n in deltas}}
            instance._bz_stored = {**stored, **copy.deepcopy(pose)}
        instance._dirty = False

    # ── End-of-action change detection ───────────────────────────────────

    def diff_and_notify(self) -> set[type[State]]:
        """Detect ``ServerState`` mutations since resolve, fire the change
        signal for each changed field, and return the set of changed
        ``ServerState`` CLASSES (so the caller can refresh the zones whose
        ``deps`` include them).

        Value-based : compares each instance's current :meth:`_field_values`
        against the baseline snapshot taken in :meth:`register`, so it catches
        EVERY mutation form — reassignment AND in-place list/dict/set ops
        (``state.items.append(...)``, ``state.d[k] = v``, …) and nested
        mutations — that :meth:`Field.__set__` alone never sees. On a change
        it flips ``_dirty`` (so :meth:`commit` persists the in-place mutation,
        which it otherwise skips) and calls ``TRACKER.notify_change`` — the
        exact signal ``Field.__set__`` fires on reassignment — then re-baselines.

        Call end-of-action, BEFORE the refresh drain, so the change reaches
        the current response's re-render. ClientState is skipped : it rides
        the ``<bz-patch>`` delta, not this diff.
        """
        changed_classes: set[type[State]] = set()
        # Les NOMS des champs, par classe. La boucle les connait deja ;
        # ne rendre que les classes jetait l'information la plus utile —
        # « quoi a change », pas seulement « qui ». Un rendu partiel peut
        # s'en servir pour ne pas re-emettre ce qui ne peut pas avoir
        # bouge (cf. la barre d'outils du datatable, 44 % de sa zone).
        # Attribut plutot que valeur de retour : trois appelants lisent
        # deja le set de classes.
        self.changed_fields = {}
        for instance in list(self._instances.values()):
            if not isinstance(instance, ServerState):
                continue
            baseline = getattr(instance, "_bz_baseline", None)
            if baseline is None:
                continue
            current = instance._field_values()
            changed = False
            for name in set(current) | set(baseline):
                if current.get(name, _ABSENT) != baseline.get(name, _ABSENT):
                    instance._dirty = True
                    TRACKER.notify_change(instance, name)
                    self.changed_fields.setdefault(
                        type(instance), set()).add(name)
                    changed = True
            if changed:
                changed_classes.add(type(instance))
                instance._bz_baseline = copy.deepcopy(current)
        return changed_classes

    # ── L'état adressable ───────────────────────────────────────────────

    def addressable_params(self) -> dict[str, str]:
        """``{paramètre: valeur}`` pour tout champ déclaré ``URL`` cette requête.

        Ne lit que les états DÉJÀ résolus : ceux que la page a vraiment
        montés. Un état jamais construit n'a rien à dire sur l'URL, et
        deviner sa valeur ferait apparaître un paramètre pour une vue
        qui n'existe pas à l'écran.
        """
        return collect_url_params(list(self._instances.values()))

    def addressable_param_names(self) -> set[str]:
        """TOUS les noms de paramètres déclarés, valeur par défaut ou non.

        ``addressable_params`` ne rend que ce qui n'est PAS au défaut —
        c'est ce qui garde l'URL lisible. Mais recomposer une adresse
        demande aussi de savoir ce qu'il faut RETIRER : un champ revenu à
        son défaut disparaît de la première liste, et sans celle-ci il
        resterait périmé dans l'URL.

        Le bug que ça répare (2026-08-29, rapporté par l'utilisateur) :
        trier « Secteur » puis re-trier « Compte » laissait
        ``?tri=secteur`` en place. L'URL faisant foi à l'action suivante,
        elle re-semait ``sort_key=secteur`` et écrasait le clic — donc
        « je ne peux plus trier en décroissant », et « avec un filtre
        actif plus rien ne bouge ». Une adresse périmée ne se contente
        pas de mentir : elle PILOTE.
        """
        from bretzel.state.url import addressable_fields

        out: set[str] = set()
        for instance in self._instances.values():
            out.update(addressable_fields(type(instance)).values())
        return out

    def addressable_changed(self, changed: dict[type[State], set[str]]) -> bool:
        """Un champ ADRESSABLE a-t-il bougé dans ce diff ?

        C'est la question qui décide de pousser une URL, et elle est plus
        étroite que « l'état a changé » : paginer une table dont seul le
        tri est déclaré ne doit rien pousser. Sinon chaque action
        empilerait une entrée d'historique identique à la précédente, et
        le bouton retour demanderait dix clics pour sortir d'une page.
        """
        from bretzel.state.url import addressable_fields

        return any(
            names & set(addressable_fields(cls))
            for cls, names in changed.items()
        )

    # ── Storage-key composition ─────────────────────────────────────────

    def _compose_storage_key(
        self,
        scope: ServerScope,
        class_name: str,
        state_key: str,
    ) -> str:
        """Compose the logical key handed to the backend.

        The backend prepends its own ``{prefix}:{scope}:`` ; this function
        produces only the per-(scope, identity) tail.
        """
        if scope == "session":
            if self._session_id is None:
                raise ScopeConfigError(
                    "Session-scoped state needs a session id ; the "
                    "session middleware must populate one before resolve()."
                )
            return f"{self._session_id}:{class_name}:{state_key}"

        if scope == "user":
            if self._user_id is None:
                raise AuthRequiredError(
                    f"User-scoped state {class_name!r} requires an "
                    "authenticated user."
                )
            hashed = hashlib.sha256(self._user_id.encode("utf-8")).hexdigest()
            return f"{hashed}:{class_name}:{state_key}"

        if scope == "app":
            return f"{class_name}:{state_key}"

        if scope == "page":
            if self._page_id is None:
                raise ScopeConfigError(
                    "Page-scoped state needs a page id ; the render "
                    "context middleware must populate one before resolve()."
                )
            return f"{self._page_id}:{class_name}:{state_key}"

        raise ScopeConfigError(f"Unknown server scope {scope!r}")
