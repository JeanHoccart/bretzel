"""In-memory storage backend for dev / tests.

Plain ``dict`` under the hood. Lost on process restart — production
deployments use the Redis backend instead.

Used as the default when no ``redis_url`` is configured. Sufficient for
single-worker uvicorn dev runs and for the unit / integration test
suite (``MemoryBackend`` removes the need for a live Redis in CI).

Ce que devient une entrée expirée
----------------------------------

Elle est retirée à la RELECTURE, et — depuis le 2026-09-04 — par un
**balayage amorti à l'écriture**. La relecture seule ne suffisait pas, et
la raison tient en une phrase : *une entrée abandonnée n'est par
définition plus relue*. Une session qu'on ne reprend pas, un ``PageState``
dont l'onglet est fermé, une clé de page neuve à chaque F5 — leur date
limite passait sans que personne ne regarde, et rien d'autre ne les
touchait (``scan`` et ``clear_scope`` purgent aussi, mais **aucun code du
framework ne les appelle** : zéro site, vérifié). Le magasin suivait donc
le nombre de pages chargées depuis le démarrage, pas le nombre
d'utilisateurs actifs.

Le balayage est **sur l'écriture**, et c'est délibéré : ce qui fait
grossir un magasin, ce sont les écritures. Sans écriture, pas de
croissance, donc rien à balayer — et surtout aucune tâche de fond à
faire vivre pour un backend dont le rôle est de tenir dans un process de
développement.

⚠️ **Ce que le balayage ne borne PAS, et ce n'est pas un oubli.** Les
portées ``user`` et ``app`` portent ``ttl=None`` par choix (cf.
``DEFAULT_TTLS``) : elles n'expirent jamais, donc rien ne les retire. Le
magasin est borné par « utilisateurs connus + sessions vivantes + pages
vues dans la dernière heure », ce qui est la taille des données de
l'app — plus par la durée de fonctionnement du process.
"""

from __future__ import annotations

import fnmatch
import threading
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass
class _Entry:
    """A stored payload with optional Unix-time expiry."""

    data: dict[str, Any]
    expires_at: float | None  # ``None`` → never expires


#: Le temps minimal entre deux balayages complets.
#:
#: Une minute, et le choix est celui d'un COÛT PAR UNITÉ DE TEMPS plutôt
#: que par écriture : un balayage vaut ``O(entrées)``, donc le déclencher
#: toutes les N écritures ferait payer une rafale N fois. Ici, mille
#: écritures en dix secondes en paient un seul.
#:
#: Une minute de retard sur une purge ne coûte rien : les durées en jeu
#: sont l'heure (``page``) et le jour (``session``).
_SWEEP_INTERVAL_SECONDS = 60.0


class MemoryBackend:
    """:class:`Backend` implementation backed by a process-local dict.

    Keys are composed as ``f"{scope}:{key}"``. The same shape as the
    Redis backend produces, so test assertions written against either
    backend translate cleanly.
    """

    def __init__(self) -> None:
        self._data: dict[str, _Entry] = {}
        #: ``{clé: (jeton, échéance)}`` — les verrous tenus. Cf.
        #: :meth:`acquire`.
        self._locks: dict[str, tuple[str, float]] = {}
        #: Sérialise la lecture-modification-écriture de :meth:`merge`.
        #: Cf. sa docstring : le module ne peut pas garantir que rien ne
        #: l'appelle hors de la boucle, donc il ne le suppose pas.
        self._write_lock = threading.Lock()
        #: Quand le dernier balayage a eu lieu. ``monotonic`` et non
        #: ``time()`` : on mesure ici une DURÉE, et une horloge murale
        #: qui recule (NTP, changement d'heure) ferait sauter le
        #: balayage — ou le déclencherait en boucle. Les dates
        #: d'expiration, elles, restent en horloge murale : ce sont des
        #: instants, et ils survivent à la comparaison entre appels.
        self._last_sweep = time.monotonic()

    # ── Read / write ────────────────────────────────────────────────────

    def _sweep_if_due(self) -> None:
        """Retirer les entrées expirées, au plus une fois par intervalle.

        Appelée sous le verrou d'écriture, depuis les deux chemins qui
        font GROSSIR le magasin. C'est ce qui rend le coût amorti : la
        purge ne s'attache pas à une écriture en particulier, seulement
        au fait qu'il y en ait.
        """
        maintenant = time.monotonic()
        if maintenant - self._last_sweep < _SWEEP_INTERVAL_SECONDS:
            return
        self._last_sweep = maintenant
        limite = time.time()
        for cle, entree in list(self._data.items()):
            if entree.expires_at is not None and limite >= entree.expires_at:
                self._data.pop(cle, None)

    async def load(self, scope: str, key: str) -> dict[str, Any] | None:
        return self.load_sync(scope, key)

    def load_sync(self, scope: str, key: str) -> dict[str, Any] | None:
        """Synchronous read — the in-memory backend has no I/O so this
        is a plain dict lookup. Lets the sync ``State()`` construction
        path hydrate on first use without dragging async into the
        metaclass.

        Redis (and any future I/O-backed backend) won't expose this
        method. Son absence n'empêche PLUS l'hydratation depuis le
        2026-09-04 : le registre fait alors exécuter le ``load`` async
        par la boucle depuis le thread du pool. C'est donc un
        raccourci — il évite un aller-retour de thread quand la lecture
        ne coûte rien —, et non plus une capacité qui change le
        comportement. Le seul cas qu'il couvre encore SEUL est l'appel
        hors de toute boucle (script, test synchrone).
        """
        full_key = f"{scope}:{key}"
        entry = self._data.get(full_key)
        if entry is None:
            return None
        if entry.expires_at is not None and time.time() >= entry.expires_at:
            # Lazy expiry — drop on read.
            self._data.pop(full_key, None)
            return None
        # Defensive copy : mutations on the returned dict mustn't leak
        # back into the store.
        return dict(entry.data)

    async def save(
        self,
        scope: str,
        key: str,
        data: dict[str, Any],
        *,
        ttl: int | None = None,
    ) -> None:
        full_key = f"{scope}:{key}"
        with self._write_lock:
            self._sweep_if_due()
            # Un document VIDE veut dire « pas de ligne ». Redis ne peut
            # PAS faire autrement — un hash sans champ n'existe pas —, et
            # deux backends qui divergent sur un cas rare, c'est le piège
            # « ça marche en dev » de ce dépôt. Cf.
            # ``test_both_backends_agree``.
            if not data:
                self._data.pop(full_key, None)
                return
            expires_at = None if ttl is None else time.time() + ttl
            self._data[full_key] = _Entry(
                data=dict(data), expires_at=expires_at
            )

    async def merge(
        self,
        scope: str,
        key: str,
        changes: dict[str, Any],
        *,
        add: dict[str, Any] | None = None,
        ttl: int | None = None,
    ) -> None:
        """Fusionner ``changes`` dans l'entrée, en créant ce qui manque.

        **Deux protections, parce qu'il y a deux façons de perdre la
        course.** Aucun ``await`` entre la lecture et l'écriture : la
        boucle ne peut pas passer la main à une autre requête au milieu.
        Et un verrou, parce que « personne d'autre ne touche ce dict »
        est une affirmation que ce module ne peut PAS tenir : depuis le
        délestage du code d'app sur un threadpool, ``load_sync`` est
        appelée depuis un thread du pool, et elle mute ``_data`` (elle
        purge l'entrée expirée). Aucun chemin d'ÉCRITURE ne tourne hors
        de la boucle aujourd'hui — les deux appelants de ``commit`` sont
        awaités dessus — mais c'est une propriété de deux sites d'appel,
        pas du module. Le verrou coûte une centaine de nanosecondes et
        rend la garantie locale.

        La lecture passe par :meth:`load_sync` : elle sait déjà ce qu'est
        une entrée expirée, et cette règle avait déjà trois définitions
        dans ce fichier.

        ``ttl=None`` LAISSE l'expiration en place, à la différence de
        :meth:`save` qui remplace tout — même contrat que côté Redis, où
        une fusion sans durée n'émet simplement aucune commande
        d'expiration.

        ``add`` est appliqué SOUS LE VERROU, entre la lecture et
        l'écriture — c'est ce qui rend l'addition juste ici. Le verrou
        tient la place de l'``HINCRBY`` de Redis : dans les deux cas
        c'est le magasin qui additionne, jamais l'appelant.
        """
        if not changes and not add:
            return
        full_key = f"{scope}:{key}"
        with self._write_lock:
            self._sweep_if_due()
            document = self.load_sync(scope, key) or {}
            document.update(changes)
            for champ, ecart in (add or {}).items():
                document[champ] = document.get(champ, 0) + ecart
            # APRÈS la lecture, jamais avant : ``load_sync`` purge une
            # entrée expirée, et reprendre l'expiration d'une entrée
            # qu'il vient de jeter poserait une date déjà passée — la
            # ligne neuve naîtrait morte.
            existante = self._data.get(full_key)
            if ttl is not None:
                expires_at = time.time() + ttl
            elif existante is not None:
                expires_at = existante.expires_at
            else:
                expires_at = None
            self._data[full_key] = _Entry(
                data=document, expires_at=expires_at
            )

    # ── Verrou ──────────────────────────────────────────────────────────

    async def acquire(
        self, scope: str, key: str, token: str, *, ttl: int
    ) -> bool:
        """Prendre le verrou, sans attendre.

        Le ``ttl`` sert autant ici qu'en Redis, et pour la même raison :
        un handler qui lève en tenant le verrou laisserait la clé bloquée
        pour la vie du processus. Le gestionnaire de contexte relâche
        dans son ``finally``, mais un ``kill -9`` n'a pas de ``finally``.
        """
        full_key = f"{scope}:{key}"
        with self._write_lock:
            porteur = self._locks.get(full_key)
            if porteur is not None and porteur[1] > time.time():
                return False
            self._locks[full_key] = (token, time.time() + ttl)
            return True

    async def release(self, scope: str, key: str, token: str) -> None:
        """Relâcher, si le jeton est bien celui du porteur.

        Le contrôle et la suppression sont sous le même verrou : entre un
        ``get`` et un ``pop`` séparés, l'expiration pourrait donner la
        clé à quelqu'un d'autre, qu'on effacerait.
        """
        full_key = f"{scope}:{key}"
        with self._write_lock:
            porteur = self._locks.get(full_key)
            if porteur is not None and porteur[0] == token:
                del self._locks[full_key]

    async def delete(self, scope: str, key: str) -> None:
        self._data.pop(f"{scope}:{key}", None)

    # ── Bulk operations ─────────────────────────────────────────────────

    async def scan(self, pattern: str) -> AsyncIterator[str]:
        # Snapshot the keys to make iteration tolerant to concurrent saves.
        for stored_key in list(self._data.keys()):
            if fnmatch.fnmatchcase(stored_key, pattern):
                # Drop any entry that has expired, mirroring ``load``.
                entry = self._data.get(stored_key)
                if (
                    entry is not None
                    and entry.expires_at is not None
                    and time.time() >= entry.expires_at
                ):
                    self._data.pop(stored_key, None)
                    continue
                yield stored_key

    async def clear_scope(
        self,
        scope: str,
        *,
        pattern: str | None = None,
    ) -> int:
        match = f"{scope}:{pattern}" if pattern else f"{scope}:*"
        victims = [k for k in self._data if fnmatch.fnmatchcase(k, match)]
        for k in victims:
            del self._data[k]
        return len(victims)

    async def health(self) -> bool:
        return True
