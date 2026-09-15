"""Fabriques partagées par les tests de persistance.

``fakeredis`` était construit à l'identique dans trois fichiers — même
``decode_responses=True``, même ``importorskip``, et un ``prefix=``
présent ici, absent là. Une seule définition, donc, pour que les tests
parlent au même backend que celui qu'ils croient tester.
"""

from __future__ import annotations

import pytest

from bretzel.state.persistence.redis import RedisBackend


@pytest.fixture
def redis_backend() -> RedisBackend:
    """Un ``RedisBackend`` sur ``fakeredis``, magasin vierge.

    ``fakeredis`` est une dépendance de dev déclarée, mais l'``importorskip``
    reste : la suite doit rester lançable sur une install partielle.
    """
    fakeredis = pytest.importorskip("fakeredis")
    # Préfixe par DÉFAUT : les tests qui regardent la clé sur le fil
    # doivent voir celle que la prod écrit, pas une de circonstance.
    return RedisBackend(fakeredis.aioredis.FakeRedis(decode_responses=True))
