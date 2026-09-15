"""Ce que le HASH change, et que le contrat commun ne dit pas.

Le comportement partagé par les deux backends — fusionner sans effacer,
créer une ligne absente, honorer les durées — est joué sur les DEUX dans
``tests/unit/state/persistence/test_both_backends_agree.py``. Ce qui
reste ici est propre à Redis, et ne se vérifie que contre un serveur :

1. **la fusion ne LIT rien.** C'est la propriété que le hash achète, et
   la seule qu'une implémentation lire-fusionner-réécrire ne peut pas
   imiter. Un scénario séquentiel, lui, passerait sur les deux ;
2. **une ligne du format d'AVANT** (un document JSON en bloc) ne fait
   planter ni la lecture ni l'écriture qui la suit.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable

import pytest

from bretzel.state.persistence.redis import RedisBackend


def run[T](coro: Awaitable[T]) -> T:
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture
def serveur():
    """Un serveur fakeredis partagé — l'async ET le sync tapent dedans.

    Le second client, synchrone, sert à poser une ligne au format d'AVANT
    sans passer par le backend, qui ne sait plus l'écrire.
    """
    fakeredis = pytest.importorskip("fakeredis")
    return fakeredis, fakeredis.FakeServer()


@pytest.fixture
def backend(serveur):
    fakeredis, server = serveur
    client = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    return RedisBackend(client, prefix="test")


def test_a_merge_reads_nothing(backend) -> None:
    """La propriété que le hash achète, et la seule qui distingue.

    « Fusionner n'efface pas les autres champs » est vrai aussi d'une
    implémentation qui relit le document et le réécrit — c'est ce que
    faisait la version d'avant. Ce qui a changé, c'est qu'il n'y a plus
    de lecture DU TOUT : donc rien à protéger par un verrou, rien à
    reprendre, un aller-retour.

    On le prouve en rendant toute lecture explosive pendant la fusion.
    """

    async def scenario() -> dict[str, object] | None:
        await backend.save("session", "sid:X:default", {"filtre": "date"})

        async def interdit(*args, **kwargs):
            raise AssertionError(
                "la fusion a LU le magasin — le hash devait rendre la "
                "lecture inutile."
            )

        backend._client.hgetall = interdit  # type: ignore[method-assign]
        backend._client.get = interdit  # type: ignore[method-assign]
        try:
            await backend.merge("session", "sid:X:default", {"articles": ["pull"]})
        finally:
            del backend._client.hgetall
            del backend._client.get
        return await backend.load("session", "sid:X:default")

    assert run(scenario()) == {"filtre": "date", "articles": ["pull"]}


def test_a_legacy_json_row_does_not_crash_the_read(backend, serveur) -> None:
    """Une ligne du format d'AVANT : lue comme absente, puis remplacée.

    Le format a changé (chaîne JSON → hash). Sans ce rattrapage,
    ``HGETALL`` sur l'ancienne ligne rendrait ``WRONGTYPE`` et TOUTE
    écriture ultérieure sur la même clé échouerait aussi — l'app resterait
    cassée pour cet état tant que la clé n'aurait pas expiré.
    """
    fakeredis, server = serveur
    ancien = fakeredis.FakeStrictRedis(server=server, decode_responses=True)
    ancien.set("test:app:Flags:default", json.dumps({"beta": True}))

    async def scenario() -> tuple[object, object]:
        avant = await backend.load("app", "Flags:default")
        # …et la clé doit être écrivable juste après, sans WRONGTYPE.
        await backend.merge("app", "Flags:default", {"beta": False})
        return avant, await backend.load("app", "Flags:default")

    avant, apres = run(scenario())
    assert avant is None, (
        "l'ancienne ligne devrait se lire comme absente (donc : valeurs "
        f"par défaut, une fois), pas comme {avant!r}"
    )
    assert apres == {"beta": False}


def test_the_ttl_travels_like_a_full_write(backend) -> None:
    async def scenario() -> int:
        await backend.merge("session", "sid:X:default", {"a": 1}, ttl=120)
        return await backend._client.ttl("test:session:sid:X:default")

    assert 0 < run(scenario()) <= 120
