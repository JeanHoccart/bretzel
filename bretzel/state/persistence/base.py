"""Storage backend protocol.

The :class:`Backend` :class:`~typing.Protocol` defines the minimal async
interface every concrete backend (memory, Redis, …) must implement. The
state registry talks to backends through this protocol exclusively, so
swapping implementations is a single-line config change.

The protocol is intentionally *narrow* — neuf méthodes, no inheritance,
no abstract base class. Pydantic-style serialisation lives one layer
up : the registry hands backends already-serialised :class:`dict`
payloads.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Backend(Protocol):
    """Async key-value store with scope-aware key namespacing.

    Implementations are responsible for :

    - **Composing the storage key** from ``scope`` + ``key`` in their own
      namespace (e.g., ``bretzel:session:<sid>:<state_class>:<state_key>``
      for the Redis backend). The registry passes the logical pieces
      separately ; the backend formats them.
    - **Honouring TTLs** on ``save`` (``EX <seconds>`` for Redis, expiry
      check at read time for in-memory).
    - **Returning JSON-friendly dicts** on ``load`` — never custom Python
      objects. Validation / casting is the registry's job.
    - **Bornant leurs propres attentes.** Un backend qui parle à un
      service distant DOIT poser un délai — ``RedisBackend`` le fait à
      la construction du client. La raison n'est pas la politesse : une
      lecture d'état est appelée depuis un thread du pool
      (``StateRegistry._load_via_loop``), qui reste bloqué tant qu'elle
      n'a pas rendu. Un service silencieux gare ce thread pour
      toujours ; quarante ainsi garés (le défaut ``anyio``) et plus
      aucun code d'app synchrone ne tourne.

      ⚠️ Le registre ne double PAS ce délai d'un plafond à lui, et c'est
      un choix : deux limites empilées obligent à garder la plus interne
      strictement plus courte, faute de quoi celle du framework tombe la
      première et masque l'erreur juste — celle qui nomme le service
      injoignable. La responsabilité reste donc là où vit l'I/O.
    """

    async def load(self, scope: str, key: str) -> dict[str, Any] | None:
        """Return the stored payload, or ``None`` if not present.

        ``key`` is the State instance's logical key (``"default"``,
        ``"basket"``, …). ``scope`` is one of ``"session"`` / ``"user"``
        / ``"app"`` / ``"page"``. Page-scope IS persisted, keyed by ``page_id`` with a 1h TTL (cf. registry).
        """
        ...

    async def save(
        self,
        scope: str,
        key: str,
        data: dict[str, Any],
        *,
        ttl: int | None = None,
    ) -> None:
        """Persist ``data`` under ``(scope, key)``.

        ``ttl`` is in seconds. ``None`` means no expiration, et le
        remplacement emporte l'expiration avec le reste : la ligne
        écrite n'en porte aucune.

        Un document VIDE veut dire « pas de ligne » : elle est
        supprimée, pas créée vide. Un hash Redis ne peut pas exister
        sans champ, et le registre lit « absent » et « vide » de la même
        façon — les deux rendent les défauts.
        """
        ...

    async def merge(
        self,
        scope: str,
        key: str,
        changes: dict[str, Any],
        *,
        add: dict[str, Any] | None = None,
        ttl: int | None = None,
    ) -> None:
        """Appliquer ``changes`` SUR ce qui est stocké, atomiquement.

        C'est par ici que passe la fin de requête, et pas par
        :meth:`save` — qui réécrit le document entier et efface donc ce
        qu'une requête concurrente venait d'y mettre.

        **Atomiquement, et par CHAMP** : un champ écrit par une requête
        ne peut pas être effacé par une autre qui en écrit d'autres —
        valeur et expiration comprises. C'est la promesse minimale, et
        elle est plus forte qu'elle n'en a l'air : une implémentation
        qui lit le document, le fusionne et le réécrit ne la tient PAS,
        sauf à rendre cette séquence indivisible.

        Une clé absente est créée avec ``changes`` seul : les champs
        qu'on n'écrit pas valent leur défaut à la relecture.

        ``add`` porte les champs à INCRÉMENTER — ``{champ: écart}`` — au
        lieu de les remplacer. C'est ce qui rend un compteur juste sous
        concurrence : deux requêtes qui ont lu le même nombre envoient
        chacune « ajoute 1 », et le magasin arrive à deux. Un backend qui
        se contenterait de lire, additionner et réécrire perdrait
        exactement ce que ce paramètre existe pour sauver — l'addition
        doit être faite PAR le magasin, ou sous un verrou qu'il détient.

        ``ttl`` renouvelle l'expiration ; ``None`` laisse en place celle
        qui existe. C'est là que la fusion diffère de :meth:`save` — une
        écriture partielle n'a pas à décider du sort d'une durée qu'elle
        n'a pas posée.
        """
        ...

    async def acquire(
        self, scope: str, key: str, token: str, *, ttl: int
    ) -> bool:
        """Prendre le verrou de ``(scope, key)``. ``True`` si obtenu.

        Ne bloque PAS : rend ``False`` immédiatement quand quelqu'un le
        tient déjà. C'est l'appelant qui décide d'attendre, et de combien
        — un backend n'a pas à connaître la patience d'une requête.

        ``token`` identifie le porteur, et il n'est pas décoratif :
        :meth:`release` ne relâche que si le jeton correspond. Sans ça,
        un porteur dont le ``ttl`` a expiré relâcherait le verrou d'un
        SUCCESSEUR, qui se croirait seul alors qu'ils seraient deux.

        ``ttl`` est un plafond de PANNE, en secondes : sans lui, un
        processus qui meurt en tenant le verrou le garde pour toujours.

        ⚠️ La limite est inhérente à tout verrou à durée : si le travail
        dépasse le ``ttl``, un second porteur entre. Le jeton empêche la
        libération croisée, pas le recouvrement.
        """
        ...

    async def release(self, scope: str, key: str, token: str) -> None:
        """Relâcher le verrou, SI ``token`` est bien celui du porteur.

        Le contrôle et la suppression doivent être indivisibles : lire
        puis supprimer laisse la place à une expiration entre les deux.
        """
        ...

    async def delete(self, scope: str, key: str) -> None:
        """Remove the entry. No-op when missing."""
        ...

    def scan(self, pattern: str) -> AsyncIterator[str]:
        """Yield logical keys matching ``pattern``.

        Pattern grammar follows Redis SCAN globs (``*``, ``?``, ``[set]``).
        Use cases : admin listing, debug introspection. Returns the
        backend-prefixed keys as strings — callers parse them.
        """
        ...

    async def clear_scope(
        self,
        scope: str,
        *,
        pattern: str | None = None,
    ) -> int:
        """Delete every entry in ``scope`` (optionally narrowed by pattern).

        Returns the count of removed entries. Used on logout (``"session"``
        scope), account deletion (``"user"``), admin operations.
        """
        ...

    async def health(self) -> bool:
        """Quick connection check. Return ``True`` if the backend is
        reachable and writable. Called once at app startup."""
        ...
