"""Le verrou qu'une app demande, autour d'une lecture-modification-écriture.

Ce qu'il répare
---------------

Le commit par champ (cf. ``registry.commit``) sauve ce qui se combine :
deux requêtes qui écrivent des champs DIFFÉRENTS ne s'effacent plus, et
un champ déclaré ``merge="add"`` additionne. Reste ce qui ne se combine
pas — un geste qui CALCULE à partir de ce qu'il a lu ::

    store.tâches = [t for t in store.tâches if t["id"] != cible]

Deux suppressions simultanées lisent la même liste, en retirent chacune
un élément, et la seconde écriture réintroduit celui que la première
venait d'ôter. Aucune opération de magasin ne peut résoudre ça : ni
``RPUSH`` (ce n'est pas un ajout), ni un écart (ce n'est pas un nombre).
La seule réponse générale est de **ne pas les laisser se chevaucher** ::

    def supprimer(cible: str) -> None:
        with Kanban.lock() as store:
            store.tâches = [t for t in store.tâches if t["id"] != cible]

Ce que le bloc garantit
-----------------------

Il est une petite transaction sur la ligne de cet état :

1. **entrée** — le verrou est pris, puis l'état est RELU. Ce que tu lis
   dedans est donc frais, même si tu l'avais déjà lu avant le bloc ;
2. **sortie** — les champs modifiés sont écrits, puis le verrou est
   relâché.

L'écriture est DANS le bloc, et ce n'est pas un détail : si on se
contentait de bloquer en laissant le commit de fin de requête écrire
plus tard, une autre requête se glisserait entre la libération et
l'écriture — le verrou n'aurait rien protégé.

``with`` et non ``async with``
-------------------------------

Les handlers de ce framework s'écrivent ``def`` (mesuré : 1 659 contre
16), parce qu'un corps synchrone est délesté sur un thread et ne gèle
rien. Un ``async with`` les forcerait tous en ``async def``, c'est-à-dire
sur la boucle, où le moindre appel bloquant coûte le worker entier. Le
même objet accepte les deux formes — ``async with`` marche dans un corps
``async def`` — mais la normale est synchrone.

Ce qu'un verrou à durée ne peut pas
------------------------------------

Il porte un ``ttl``, sans quoi un processus tué en le tenant le garderait
pour toujours. La contrepartie est inhérente : **si ton bloc dépasse le
``ttl``, un second porteur entre**. Le jeton empêche la libération
croisée — tu ne relâcheras jamais le verrou de quelqu'un d'autre — pas le
recouvrement. Garde le bloc court, et n'y mets ni appel réseau lent ni
rendu.

Et il sérialise : deux requêtes sur la MÊME clé s'attendent. C'est le
prix demandé, et il n'est payé que là où on l'a demandé.
"""

from __future__ import annotations

import secrets
import time
from types import TracebackType
from typing import TYPE_CHECKING, Any

import anyio
import anyio.from_thread

from bretzel.core.errors import BretzelError

if TYPE_CHECKING:
    from bretzel.state.registry import StateRegistry
    from bretzel.state.scopes.server import ServerState

#: Combien de temps un porteur garde le verrou s'il meurt sans relâcher.
#: Cinq secondes : un bloc protégé fait une lecture, un calcul en mémoire
#: et une écriture — jamais un appel lent. Au-delà, ce n'est plus une
#: section critique, c'est un travail de fond.
DEFAULT_LOCK_TTL = 5

#: Combien de temps on ATTEND son tour avant d'abandonner. Distinct du
#: ``ttl`` : l'un borne la panne d'un porteur, l'autre la patience d'un
#: suiveur. Trois secondes tient dans le budget d'une requête HTTP.
DEFAULT_LOCK_TIMEOUT = 3.0

#: Entre deux tentatives. Court, parce que les sections protégées sont
#: brèves ; pas nul, pour ne pas marteler le magasin.
_RETRY_DELAY = 0.02


class LockTimeoutError(BretzelError):
    """Raised when a state lock cannot be acquired before its deadline."""


class StateLock:
    """Le gestionnaire de contexte rendu par ``MonEtat.lock()``.

    Synchrone ET asynchrone : ``__enter__`` sert les corps ``def`` (le
    cas courant, exécuté sur un thread du pool) en faisant exécuter les
    appels du backend PAR la boucle ; ``__aenter__`` sert les corps
    ``async def`` en les attendant directement.
    """

    __slots__ = ("_cls", "_key", "_registry", "_storage_key", "_timeout", "_token", "_ttl")

    def __init__(
        self,
        registry: StateRegistry,
        cls: type[ServerState],
        key: str,
        *,
        ttl: int,
        timeout: float,
    ) -> None:
        self._registry = registry
        self._cls = cls
        self._key = key
        self._ttl = ttl
        self._timeout = timeout
        self._token = secrets.token_hex(8)
        self._storage_key: str | None = None

    # ── Le travail, écrit une fois en async ─────────────────────────────

    async def _acquire(self) -> ServerState:
        scope = self._cls.__scope__
        self._storage_key = self._registry._compose_storage_key(
            scope, self._cls.__name__, self._key
        )
        backend = self._registry._backend
        fin = time.monotonic() + self._timeout
        while True:
            if await backend.acquire(
                scope, self._storage_key, self._token, ttl=self._ttl
            ):
                break
            if time.monotonic() >= fin:
                raise LockTimeoutError(
                    f"{self._cls.__name__}.lock() n'a pas obtenu le verrou en "
                    f"{self._timeout} s. Une autre requête tient la même clé "
                    f"plus longtemps que prévu : regarde ce que fait le bloc "
                    f"protégé — il doit lire, calculer et écrire, jamais "
                    f"attendre le réseau."
                )
            await anyio.sleep(_RETRY_DELAY)
        # RELIRE sous le verrou : ce qu'on avait lu avant peut dater.
        return await self._registry.reload(self._cls, self._key)

    async def _release(self) -> None:
        instance = self._registry.get_cached(self._cls, self._key)
        try:
            if instance is not None:
                await self._registry.write_one(self._cls, self._key, instance)  # type: ignore[arg-type]
        finally:
            # Relâcher MÊME si l'écriture lève : garder le verrou en plus
            # de l'erreur punirait les requêtes suivantes pour une faute
            # qui n'est pas la leur.
            assert self._storage_key is not None
            await self._registry._backend.release(
                self._cls.__scope__, self._storage_key, self._token
            )

    # ── Les deux portes ─────────────────────────────────────────────────

    def __enter__(self) -> Any:
        return _via_loop(self._acquire)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        _via_loop(self._release)

    async def __aenter__(self) -> Any:
        return await self._acquire()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._release()


def _via_loop(coro_fn: Any) -> Any:
    """Faire exécuter ``coro_fn`` PAR la boucle, depuis un thread du pool.

    Le pendant exact de ``StateRegistry._load_via_loop`` : un corps
    ``def`` tourne sur un thread où l'on a le droit d'attendre, et
    ``anyio.from_thread.run`` ne marche QUE depuis un tel thread. Un
    appel resté sur la boucle tombe donc dans le ``except`` — et là,
    bloquer aurait gelé le worker.
    """
    try:
        return anyio.from_thread.run(coro_fn)
    except anyio.from_thread.NoEventLoopError:
        raise BretzelError(
            "`with MonEtat.lock()` a été utilisé dans un corps `async def`, "
            "où il ne peut pas attendre le magasin sans geler la boucle. "
            "Écris `async with MonEtat.lock()` ici — ou repasse ce corps en "
            "`def`, que le framework délestera sur un thread."
        ) from None
