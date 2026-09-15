"""Redis storage backend for production deployments.

Strict rules :

- **Un HASH par état, un champ Redis par champ d'état.** C'est la forme
  que Redis propose pour un objet, et c'est elle qui rend l'écriture
  partielle native : ``HSET clé filtre "rouge"`` ne lit rien, n'écrase
  rien d'autre, et tient en un aller-retour. Le document JSON en bloc
  qu'on stockait avant obligeait à relire, fusionner et tout réécrire
  sous un verrou optimiste — trois allers-retours et une boucle de
  reprise pour changer un champ.

- **Toute attente est BORNÉE, et c'est le backend qui la borne.** Une
  lecture d'état part depuis un thread du pool (cf.
  ``StateRegistry._load_via_loop``), et ce thread reste bloqué tant que
  la réponse n'arrive pas. Sans délai côté client, un Redis qui ne
  répond plus — pas refusé, pas coupé : silencieux — gare le thread
  pour toujours, sans exception, sans log et sans reprise. Quarante
  ainsi garés (le défaut ``anyio``, cf. ``core/invoke.py``) et plus
  aucun code d'app synchrone ne tourne. D'où ``socket_timeout`` et
  ``socket_connect_timeout`` posés par défaut ici : redis-py les laisse
  tous les deux à ``None``, c'est-à-dire sans fin (mesuré).

- **JSON-only serialisation.** Bretzel never falls back to ``pickle`` —
  pickle deserialisation is a documented RCE vector when an attacker
  can write to the store. If a state field carries a value
  :func:`json.dumps` cannot encode, we surface :class:`BretzelError`
  at write time with a clear message rather than silently accepting it.

- **Logical key composition is the registry's job.** This backend only
  prepends ``{prefix}:{scope}:`` to whatever the registry hands it.
  The registry is responsible for hashing user IDs (privacy by design,
  see ``.claude/bretzel/state.md``) and embedding the State class name + instance
  key into the logical key.

- **TTL.** ``save(..., ttl=N)`` pose ``EXPIRE N`` ; ``ttl=None`` ne laisse
  aucune expiration (la clé vient d'être supprimée). ``merge`` renouvelle
  l'expiration quand on lui en donne une, et ne touche pas à celle en
  place quand ``ttl`` vaut ``None`` — cf. sa docstring.

⚠️ **Ce que le hash coûte, mesuré le 2026-09-04** — l'écrire ici parce
que la moitié qui gagne est déjà écrite plus haut :

- la LECTURE décode champ par champ, donc N appels ``json.loads`` au lieu
  d'un : **18,3 µs contre 3,7** pour vingt champs, 63 contre 13,7 pour
  cinquante. À comparer aux millisecondes d'un aller-retour réseau, mais
  ce n'est pas gratuit ;
- un seul champ dont le JSON dépasse 64 octets fait basculer TOUT le hash
  hors du codage compact de Redis (``hash-max-listpack-value``), ce qui
  coûte quelques dizaines d'octets par champ au lieu d'une cinquantaine
  pour la ligne entière.

Le troc est assumé : ces deux coûts se paient en microsecondes et en
kilo-octets, la mise à jour perdue se payait en données effacées.
"""

from __future__ import annotations

import functools
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import Any
from urllib.parse import urlparse

from redis import asyncio as redis_asyncio
from redis import exceptions as redis_exceptions

# Canonical framework error — one class, so a serialisation failure here
# is caught by the server's ``except BretzelError`` / FastAPI handler
# (previously a *distinct* local class silently escaped into a bare 500).
# Re-exported so ``redis.BretzelError`` keeps resolving.
from bretzel.core.errors import BretzelError

#: Le plafond d'une opération et celui d'une connexion, en secondes.
#:
#: **Cinq**, parce que les deux erreurs coûtent cher dans des sens
#: opposés : trop court, une pointe de charge fait échouer des requêtes
#: qui auraient abouti ; trop long, chaque requête bloquée retient un
#: thread du pool, et il y en a quarante. Cinq secondes est déjà une
#: éternité pour une UI — c'est un plafond de PANNE, pas un budget de
#: latence.
#:
#: Se change par l'URL (``redis://hôte?socket_timeout=2``), qui l'emporte
#: sur ce défaut : redis-py applique les options de l'URL APRÈS les
#: kwargs (vérifié le 2026-09-04 — un ``socket_timeout=9`` en kwarg
#: perdait contre le ``1.5`` de l'URL). C'est bien le sens qu'on veut :
#: la valeur du framework est un défaut, celle de l'exploitant gagne.
_DEFAULT_TIMEOUT_SECONDS = 5.0

def _bounded[T](
    method: Callable[..., Awaitable[T]],
) -> Callable[..., Awaitable[T]]:
    """Traduire une panne de TRANSPORT en :class:`BretzelError` lisible.

    Sans ça, un Redis muet remonte un ``redis.exceptions.TimeoutError``
    nu : une 500 sans phrase, dans une trace où rien ne dit que
    l'attente était bornée exprès ni comment la desserrer. Le refus est
    une aide — c'est la norme du dépôt.

    Ne couvre QUE le transport. Un ``ResponseError`` (WRONGTYPE, script
    refusé…) parle du contenu et doit continuer de remonter tel quel :
    :meth:`RedisBackend.load` en traite un lui-même, et l'avaler ici
    casserait sa reprise.
    """

    @functools.wraps(method)
    async def wrapper(self: RedisBackend, *args: Any, **kwargs: Any) -> T:
        try:
            return await method(self, *args, **kwargs)
        except redis_exceptions.TimeoutError as exc:
            raise BretzelError(
                f"Redis n'a pas répondu à {method.__name__!r} dans le délai "
                f"imparti ({exc}). L'attente est bornée EXPRÈS : la lecture "
                f"d'un état part depuis un thread du pool, et une attente "
                f"sans fin le garderait pour toujours. Si ton instance est "
                f"légitimement lente, desserre le plafond dans l'URL "
                f"(`redis://…?socket_timeout=15`)."
            ) from exc
        except redis_exceptions.ConnectionError as exc:
            raise BretzelError(
                f"Redis est injoignable pendant {method.__name__!r} ({exc}). "
                f"L'état de cette requête n'a pas pu être lu ou écrit."
            ) from exc

    return wrapper


class RedisBackend:
    """:class:`Backend` implementation backed by ``redis.asyncio``.

    Un état est un **hash** dont chaque champ porte la valeur JSON d'un
    champ d'état. La clé sur le fil est ``f"{prefix}:{scope}:{key}"``, où
    ``prefix`` vaut ``"bretzel"`` par défaut — deux apps Bretzel peuvent
    donc partager une instance Redis avec des préfixes distincts.
    """

    def __init__(
        self,
        client: redis_asyncio.Redis,
        *,
        prefix: str = "bretzel",
    ) -> None:
        self._client = client
        self._prefix = prefix

    # ── Construction helpers ────────────────────────────────────────────

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        prefix: str = "bretzel",
        **client_kwargs: Any,
    ) -> RedisBackend:
        """Build a backend from a ``redis://`` / ``rediss://`` URL."""
        # ``decode_responses=True`` makes ``hgetall`` / ``scan_iter``
        # return ``str`` instead of ``bytes`` — noms de champs comme
        # valeurs, et on n'y stocke que du JSON de toute façon.
        client_kwargs.setdefault("decode_responses", True)
        # Les deux plafonds, et il en faut DEUX : ``socket_timeout`` borne
        # une opération sur une connexion déjà ouverte, jamais son
        # ouverture. Un hôte qui avale les paquets sans répondre — DNS
        # qui résout vers le vide, groupe de sécurité fermé — ne
        # rencontre que le second, et c'est celui-là qui pendait au
        # DÉMARRAGE : ``lifecycle._check_state_backend`` attend un
        # ``health()``, donc le boot lui-même ne finissait jamais.
        client_kwargs.setdefault("socket_timeout", _DEFAULT_TIMEOUT_SECONDS)
        client_kwargs.setdefault(
            "socket_connect_timeout", _DEFAULT_TIMEOUT_SECONDS
        )
        # Quick sanity check : reject unknown schemes early.
        scheme = urlparse(url).scheme
        if scheme not in {"redis", "rediss", "unix"}:
            raise BretzelError(
                f"Unsupported Redis URL scheme {scheme!r} : "
                "expected one of 'redis', 'rediss', 'unix'."
            )
        client = redis_asyncio.Redis.from_url(url, **client_kwargs)
        return cls(client, prefix=prefix)

    # ── Key composition ─────────────────────────────────────────────────

    def _compose(self, scope: str, key: str) -> str:
        return f"{self._prefix}:{scope}:{key}"

    # ── Read / write ────────────────────────────────────────────────────

    def _decode(self, raw: Any, scope: str, key: str, field: str) -> Any:
        """La valeur d'UN champ, ou l'erreur qui dit pourquoi elle ne l'est pas.

        Redis ne regarde jamais DANS une valeur : le JSON reste du
        ``json`` Python de bout en bout, donc rien ne peut confondre une
        liste vide avec un objet vide.
        """
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BretzelError(
                f"Stored field {field!r} at {scope}:{key} is not valid JSON : "
                f"{exc}. This usually indicates a foreign writer or a backend "
                "version mismatch."
            ) from exc

    def _encode(self, value: Any, scope: str, key: str, field: str) -> str:
        try:
            return json.dumps(value)
        except (TypeError, ValueError) as exc:
            raise BretzelError(
                f"State field {field!r} at {scope}:{key} is not "
                f"JSON-serialisable : {exc}. Bretzel does NOT fall back to "
                "pickle (RCE risk). Make sure your fields hold JSON-friendly "
                "types (str, int, float, bool, None, list, dict) or implement "
                "to_dict() on custom values."
            ) from exc

    def _mapping(
        self, data: dict[str, Any], scope: str, key: str
    ) -> dict[str, str]:
        """``{champ: valeur JSON}`` prêt pour ``HSET``.

        Encode TOUT avant d'écrire quoi que ce soit : un champ
        non-sérialisable doit faire échouer l'écriture entière, pas la
        laisser à moitié posée.
        """
        return {
            field: self._encode(value, scope, key, field)
            for field, value in data.items()
        }

    @_bounded
    async def load(self, scope: str, key: str) -> dict[str, Any] | None:
        composed = self._compose(scope, key)
        try:
            raw = await self._client.hgetall(composed)
        except redis_exceptions.ResponseError as exc:
            if "WRONGTYPE" not in str(exc).upper():
                raise
            # Une ligne écrite par la version d'AVANT (un document JSON
            # en bloc, pas un hash). Elle est illisible ici, et pire :
            # elle ferait échouer toute écriture ultérieure sur la même
            # clé. On la retire et on rend « absent », ce qui redonne les
            # défauts — une fois, puis la ligne se reconstruit au format
            # courant. Le paquet est en alpha : il n'y a pas d'état
            # ancien à préserver, seulement à ne pas faire planter.
            await self.delete(scope, key)
            return None
        if not raw:
            return None
        return {
            field: self._decode(value, scope, key, field)
            for field, value in raw.items()
        }

    @_bounded
    async def save(
        self,
        scope: str,
        key: str,
        data: dict[str, Any],
        *,
        ttl: int | None = None,
    ) -> None:
        """Remplacer le document entier.

        Plus aucun appelant dans le framework : le commit passe par
        :meth:`merge`. Reste l'amorçage, les tests et l'outillage, où
        « pose exactement ceci » est ce qu'on veut dire.

        Le remplacement est une transaction ``DEL`` + ``HSET`` : sans le
        ``DEL``, un champ retiré du document survivrait dans le hash. Pas
        de ``PERSIST`` quand ``ttl`` vaut ``None`` — la clé vient d'être
        supprimée, elle ne peut porter aucune expiration.

        Un document VIDE ne laisse donc que le ``DEL`` : la ligne est
        absente, et non présente-mais-vide. Un hash Redis ne peut pas
        exister sans champ, et le registre lit « absent » et « vide » de
        la même façon — les deux rendent les défauts.
        """
        mapping = self._mapping(data, scope, key)
        composed = self._compose(scope, key)
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.delete(composed)
            if mapping:
                pipe.hset(composed, mapping=mapping)
                if ttl is not None:
                    pipe.expire(composed, ttl)
            await pipe.execute()

    @_bounded
    async def merge(
        self,
        scope: str,
        key: str,
        changes: dict[str, Any],
        *,
        add: dict[str, Any] | None = None,
        ttl: int | None = None,
    ) -> None:
        """Écrire les champs de ``changes``, et EUX SEULS.

        **Une seule commande, et aucune lecture.** ``HSET`` est atomique
        par champ côté Redis : deux requêtes qui écrivent des champs
        différents de la même clé ne peuvent pas s'effacer, sans verrou,
        sans transaction optimiste et sans boucle de reprise.

        ``add`` part en ``HINCRBY`` — ou ``HINCRBYFLOAT`` si l'écart est
        décimal, Redis ayant deux commandes là où Python a un nombre.
        C'est REDIS qui additionne, donc deux requêtes ayant lu le même
        total comptent toutes les deux. Le résultat reste du JSON
        valide : ``json.dumps(5)`` s'écrit ``5``, ce que ces commandes
        savent lire, et ce qu'elles rendent se relit pareil (vérifié).

        Avec un ``ttl``, la valeur et l'expiration partent dans la MÊME
        transaction : séparées, l'``EXPIRE`` d'une requête pourrait
        tomber après celui d'une autre et laisser une durée qui n'est
        plus la bonne.

        ``ttl=None`` ne touche PAS à l'expiration existante — à la
        différence de :meth:`save`, qui remplace tout. Une écriture
        partielle n'a pas à décider du sort d'une durée qu'elle n'a pas
        posée, et les deux scopes concernés (``user``, ``app``) n'en ont
        de toute façon jamais.
        """
        if not changes and not add:
            return
        composed = self._compose(scope, key)
        mapping = self._mapping(changes, scope, key) if changes else {}
        # Une seule commande reste une seule commande : pas de pipeline
        # quand il n'y a rien à y mettre d'autre.
        if mapping and not add and ttl is None:
            await self._client.hset(composed, mapping=mapping)
            return
        async with self._client.pipeline(transaction=True) as pipe:
            if mapping:
                pipe.hset(composed, mapping=mapping)
            for champ, ecart in (add or {}).items():
                if isinstance(ecart, int):
                    pipe.hincrby(composed, champ, ecart)
                else:
                    pipe.hincrbyfloat(composed, champ, ecart)
            if ttl is not None:
                pipe.expire(composed, ttl)
            await pipe.execute()

    # ── Verrou ──────────────────────────────────────────────────────────

    @_bounded
    async def acquire(
        self, scope: str, key: str, token: str, *, ttl: int
    ) -> bool:
        """``SET clé jeton NX EX ttl`` — la prise atomique de Redis.

        ``NX`` ne réussit que si la clé n'existe pas : c'est exactement
        « prendre le verrou si personne ne le tient », sans lecture
        préalable et sans course entre les deux.
        """
        pris = await self._client.set(
            self._lock_key(scope, key), token, nx=True, ex=ttl
        )
        return bool(pris)

    @_bounded
    async def release(self, scope: str, key: str, token: str) -> None:
        """Relâcher SI le jeton est le nôtre, sans fenêtre entre les deux.

        ``GET`` puis ``DEL`` séparés laisseraient la place à une
        expiration au milieu : on effacerait alors le verrou d'un
        successeur, qui se croirait seul. ``WATCH`` ferme cette fenêtre —
        si la clé bouge entre la lecture et le ``EXEC``, la transaction
        échoue et on ne touche à rien, ce qui est exactement la bonne
        conduite : notre verrou avait déjà expiré.

        Pas de reprise. Un échec ici veut dire « ce n'est plus le nôtre »,
        pas « réessaie ».

        (Un script Lua ferait la même chose en un aller-retour, mais
        ``fakeredis`` ne l'exécute pas sans un moteur Lua en plus — et
        une garantie qu'aucun test ne peut exercer n'en est pas une.)
        """
        cle = self._lock_key(scope, key)
        async with self._client.pipeline(transaction=True) as pipe:
            await pipe.watch(cle)
            if await pipe.get(cle) != token:
                await pipe.reset()
                return
            pipe.multi()
            pipe.delete(cle)
            try:
                await pipe.execute()
            except redis_exceptions.WatchError:
                # Quelqu'un a touché la clé pendant qu'on regardait : notre
                # verrou n'était donc plus le nôtre. Ne rien faire.
                return

    def _lock_key(self, scope: str, key: str) -> str:
        """Un espace de noms SÉPARÉ de celui des états.

        Le verrou et la ligne qu'il protège ne doivent pas partager une
        clé : un ``clear_scope`` balaierait les deux, et un verrou tenu
        disparaîtrait sous son porteur.
        """
        return f"{self._prefix}:lock:{scope}:{key}"

    @_bounded
    async def delete(self, scope: str, key: str) -> None:
        await self._client.delete(self._compose(scope, key))

    # ── Bulk operations ─────────────────────────────────────────────────

    async def scan(self, pattern: str) -> AsyncIterator[str]:
        # ``pattern`` is in the registry's logical space ; prepend the
        # prefix so callers don't need to think about the wire layout.
        wire_pattern = f"{self._prefix}:{pattern}"
        prefix_len = len(self._prefix) + 1  # ``+1`` for the trailing colon
        async for storage_key in self._client.scan_iter(match=wire_pattern):
            # Strip the backend prefix so callers see the same space they
            # write to via ``(scope, key)``.
            yield storage_key[prefix_len:]

    @_bounded
    async def clear_scope(
        self,
        scope: str,
        *,
        pattern: str | None = None,
    ) -> int:
        suffix = pattern if pattern else "*"
        wire_pattern = f"{self._prefix}:{scope}:{suffix}"
        # Stage the matching keys ; ``DEL`` accepts variadic arguments so
        # we can drop them in one round-trip when there are few enough.
        victims: list[str] = []
        async for storage_key in self._client.scan_iter(match=wire_pattern):
            victims.append(storage_key)
        if not victims:
            return 0
        # Chunk to keep the DEL command bounded — Redis supports thousands
        # of args per call but we stay well under typical limits.
        deleted = 0
        for chunk in _chunks(victims, 1024):
            deleted += await self._client.delete(*chunk)
        return deleted

    async def health(self) -> bool:
        try:
            return bool(await self._client.ping())
        except Exception:
            return False

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def close(self) -> None:
        """Tear down the connection pool. Called on app shutdown."""
        await self._client.aclose()


def _chunks(seq: list[str], size: int) -> Iterator[list[str]]:
    """Yield successive ``size``-length slices of ``seq``."""
    for i in range(0, len(seq), size):
        yield seq[i : i + size]
