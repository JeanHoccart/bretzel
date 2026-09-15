"""Le magasin mémoire rend ce qui a expiré, sans qu'on le relise.

Le trou que ça ferme
---------------------

``MemoryBackend`` ne retirait une entrée expirée qu'à la RELECTURE. Or
une entrée abandonnée n'est **par définition** plus relue : une session
qu'on ne reprend pas, un ``PageState`` dont l'onglet est fermé, une clé
de page neuve à chaque F5. Leur date limite passait sans que personne ne
regarde. ``scan`` et ``clear_scope`` purgent aussi, mais aucun code du
framework ne les appelle — zéro site, vérifié. Le magasin suivait donc le
nombre de pages chargées **depuis le démarrage**, pas le nombre
d'utilisateurs actifs.

Ce que ces tests fixent, et ce qu'ils NE fixent pas
----------------------------------------------------

Ils fixent trois choses : ce qui a expiré part même sans relecture, ce
qui est VIVANT reste, et ce qui n'a pas de date (``user`` / ``app``, par
choix) n'est jamais touché. Cette dernière est la moitié qui coûte : un
balayage qui mange de l'état valide serait bien pire que la fuite qu'il
répare.

Ils ne fixent pas la borne mémoire elle-même. Le magasin reste
proportionnel à « utilisateurs connus + sessions vivantes + pages vues
dans la dernière heure » — c'est la taille des données de l'app, et c'est
le contrat, pas un reste à traiter.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from bretzel.state.persistence import memory as memory_module
from bretzel.state.persistence.memory import MemoryBackend


@pytest.fixture
def store() -> MemoryBackend:
    return MemoryBackend()


def _ecrire(store: MemoryBackend, cle: str, *, ttl: int | None) -> None:
    asyncio.run(store.save("page", cle, {"n": 1}, ttl=ttl))


def _forcer_le_prochain_balayage(store: MemoryBackend) -> None:
    """Faire comme si l'intervalle était écoulé.

    On déplace la DERNIÈRE date plutôt que de raccourcir l'intervalle :
    c'est la même chose pour le code testé, et ça laisse la vraie
    constante sous les yeux du test qui la vérifie.
    """
    store._last_sweep -= memory_module._SWEEP_INTERVAL_SECONDS + 1


# ── Ce qui a expiré part, même si personne ne le relit ──────────────


def test_an_abandoned_entry_is_dropped_without_being_read(store) -> None:
    for i in range(50):
        _ecrire(store, f"abandonnee-{i}", ttl=1)
    assert len(store._data) == 50

    # Les 50 sont expirées. Personne ne les relira jamais — c'est tout
    # le sujet : avant, elles restaient là pour la vie du process.
    for entree in store._data.values():
        entree.expires_at = time.time() - 1
    _forcer_le_prochain_balayage(store)

    _ecrire(store, "vivante", ttl=3600)
    assert list(store._data) == ["page:vivante"]


def test_a_live_entry_survives_the_sweep(store) -> None:
    """La moitié qui coûte : ne PAS manger de l'état valide."""
    _ecrire(store, "encore-la", ttl=3600)
    _forcer_le_prochain_balayage(store)
    _ecrire(store, "autre", ttl=3600)

    assert asyncio.run(store.load("page", "encore-la")) == {"n": 1}


def test_an_entry_without_a_deadline_is_never_swept(store) -> None:
    """``user`` et ``app`` portent ``ttl=None`` par CHOIX.

    Les balayer serait effacer le compte d'un utilisateur parce que le
    serveur tourne depuis longtemps.
    """
    asyncio.run(store.save("user", "jean", {"n": 1}, ttl=None))
    _forcer_le_prochain_balayage(store)
    _ecrire(store, "declencheur", ttl=3600)

    assert asyncio.run(store.load("user", "jean")) == {"n": 1}


# ── Le coût : amorti, pas payé à chaque écriture ────────────────────


def test_the_sweep_is_amortised_not_per_write(store) -> None:
    """Deux écritures rapprochées ne balaient qu'une fois — au plus.

    Sans cette borne, une rafale de mille écritures paierait mille
    parcours du magasin. C'est ce qui justifie de compter en TEMPS
    plutôt qu'en nombre d'écritures.
    """
    _ecrire(store, "morte", ttl=1)
    store._data["page:morte"].expires_at = time.time() - 1

    # Aucun forçage : l'intervalle n'est pas écoulé, rien ne doit bouger.
    _ecrire(store, "a", ttl=3600)
    _ecrire(store, "b", ttl=3600)
    assert "page:morte" in store._data

    _forcer_le_prochain_balayage(store)
    _ecrire(store, "c", ttl=3600)
    assert "page:morte" not in store._data


def test_the_interval_is_short_enough_to_matter(store) -> None:
    """Le plancher sur la vraie constante.

    Les tests d'à côté déplacent la date du dernier balayage ; ils
    resteraient donc verts avec un intervalle réglé à une semaine, où le
    balayage n'existerait plus vraiment.
    """
    assert 0 < memory_module._SWEEP_INTERVAL_SECONDS <= 300


def test_the_sweep_runs_on_merge_too(store) -> None:
    """``merge`` est l'autre chemin qui fait grossir le magasin.

    C'est même le seul que le commit emprunte depuis que l'écriture est
    partielle — un balayage posé sur ``save`` seul ne tournerait donc
    jamais en vrai.
    """
    _ecrire(store, "morte", ttl=1)
    store._data["page:morte"].expires_at = time.time() - 1
    _forcer_le_prochain_balayage(store)

    asyncio.run(store.merge("page", "vivante", {"n": 2}, ttl=3600))
    assert "page:morte" not in store._data
    assert asyncio.run(store.load("page", "vivante")) == {"n": 2}
