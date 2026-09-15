"""Unit tests for ``bretzel.state.persistence.redis``.

Deux doublures, et le partage n'est pas arbitraire :

- ``fakeredis`` (fixture ``redis_backend``, dans le ``conftest`` voisin)
  pour tout ce qui a une SÉMANTIQUE de stockage — écrire, relire,
  expirer. Un état vit en hash depuis le 2026-09-04, donc l'écriture
  passe par un pipeline : vérifier la forme des appels sur un mock
  dirait « oui » à un pipeline qui n'exécute rien ;
- un ``MagicMock`` pour ce qui n'est que de la PLOMBERIE de client —
  composition de clé, schéma d'URL, propagation de ``scan_iter``.

Le contrat commun aux deux backends est ailleurs, et c'est le fichier
qui compte le plus : ``test_both_backends_agree.py``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable
from unittest.mock import AsyncMock, MagicMock

import pytest

from bretzel.state.persistence.base import Backend
from bretzel.state.persistence.redis import (
    BretzelError,
    RedisBackend,
    _chunks,
)


def run[T](coro: Awaitable[T]) -> T:
    return asyncio.new_event_loop().run_until_complete(coro)


def _fake_client() -> MagicMock:
    """Build a mock that mimics the subset of ``redis.asyncio.Redis``
    we exercise. Async methods are :class:`AsyncMock` ; ``scan_iter``
    is an attribute-style async generator factory that the test injects."""
    client = MagicMock(name="FakeRedis")
    client.delete = AsyncMock(return_value=1)
    client.ping = AsyncMock(return_value=True)
    client.aclose = AsyncMock(return_value=None)

    async def _empty(match: str | None = None) -> AsyncIterator[str]:
        # Default scan_iter yields nothing — tests override per-case.
        if False:  # pragma: no cover — needed to satisfy the generator shape
            yield ""

    client.scan_iter = _empty
    return client


# ───────────────────────────────────────────────────────────────────────────
# Protocol conformance
# ───────────────────────────────────────────────────────────────────────────


class TestProtocol:
    def test_satisfies_backend_protocol(self) -> None:
        backend: Backend = RedisBackend(_fake_client())
        assert isinstance(backend, Backend)


# ───────────────────────────────────────────────────────────────────────────
# Key composition
# ───────────────────────────────────────────────────────────────────────────


class TestCompose:
    def test_default_prefix(self) -> None:
        b = RedisBackend(_fake_client())
        assert b._compose("session", "abc") == "bretzel:session:abc"

    def test_custom_prefix(self) -> None:
        b = RedisBackend(_fake_client(), prefix="myapp")
        assert b._compose("user", "xyz") == "myapp:user:xyz"


# ───────────────────────────────────────────────────────────────────────────
# from_url
# ───────────────────────────────────────────────────────────────────────────


class TestFromUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "redis://localhost:6379",
            "rediss://secure.example.com:6379",
            "unix:///tmp/redis.sock",
        ],
    )
    def test_accepted_schemes(
        self, url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Stub Redis.from_url so we don't open a real connection.
        from bretzel.state.persistence import redis as r_mod

        def fake_from_url(url: str, **kwargs: object) -> object:
            return _fake_client()

        monkeypatch.setattr(r_mod.redis_asyncio.Redis, "from_url", fake_from_url)
        backend = RedisBackend.from_url(url)
        assert isinstance(backend, RedisBackend)

    def test_invalid_scheme_rejected(self) -> None:
        with pytest.raises(BretzelError, match="scheme"):
            RedisBackend.from_url("http://no-no/")


# ───────────────────────────────────────────────────────────────────────────
# save / load — le hash, et le JSON par champ
# ───────────────────────────────────────────────────────────────────────────


class TestSaveLoad:
    """Sur ``fakeredis`` (fixture ``redis_backend``), et plus sur un mock.

    Un état est stocké en HASH depuis le 2026-09-04, et écrire un hash
    demande un pipeline. Vérifier la FORME des appels sur un mock dirait
    « oui » à un pipeline qui n'exécute rien : ce qui compte, c'est de
    relire ce qu'on a écrit. ``fakeredis`` est déjà une dépendance de dev
    et tourne en process, donc ça ne coûte rien.

    ⚠️ Un seul ``run()`` par test, tout le scénario dedans : le client
    async de ``fakeredis`` s'attache à la boucle du premier appel, et
    ``run()`` en crée une neuve à chaque fois.
    """

    def test_save_then_load_round_trips(self, redis_backend) -> None:
        async def scenario():
            await redis_backend.save("session", "abc", {"x": 1, "y": "two"})
            return await redis_backend.load("session", "abc")

        assert run(scenario()) == {"x": 1, "y": "two"}

    def test_save_writes_one_redis_field_per_state_field(self, redis_backend) -> None:
        """La forme sur le fil, parce que c'est elle qui rend ``HSET`` utile."""

        async def scenario():
            await redis_backend.save("session", "abc", {"x": 1, "y": "two"})
            return await redis_backend._client.hgetall("bretzel:session:abc")

        assert run(scenario()) == {"x": "1", "y": '"two"'}

    def test_save_without_ttl_leaves_no_expiry(self, redis_backend) -> None:
        async def scenario():
            await redis_backend.save("session", "abc", {"x": 1})
            return await redis_backend._client.ttl("bretzel:session:abc")

        assert run(scenario()) == -1

    def test_save_with_ttl_sets_one(self, redis_backend) -> None:
        async def scenario():
            await redis_backend.save("session", "abc", {"x": 1}, ttl=60)
            return await redis_backend._client.ttl("bretzel:session:abc")

        assert 0 < run(scenario()) <= 60

    def test_save_drops_a_field_the_document_no_longer_has(self, redis_backend) -> None:
        """``save`` REMPLACE — sans le ``DEL``, l'ancien champ survivrait."""

        async def scenario():
            await redis_backend.save("session", "abc", {"x": 1, "y": 2})
            await redis_backend.save("session", "abc", {"x": 1})
            return await redis_backend.load("session", "abc")

        assert run(scenario()) == {"x": 1}

    def test_save_rejects_non_json(self, redis_backend) -> None:
        class Custom:
            pass

        async def scenario():
            with pytest.raises(BretzelError, match="JSON"):
                await redis_backend.save("session", "abc", {"ok": 1, "obj": Custom()})
            # Rien de posé : l'encodage échoue AVANT la moindre écriture,
            # donc le champ valide de la même passe n'est pas arrivé non plus.
            return await redis_backend.load("session", "abc")

        assert run(scenario()) is None

    def test_load_missing_returns_none(self, redis_backend) -> None:
        assert run(redis_backend.load("session", "abc")) is None

    def test_load_corrupt_json_raises(self, redis_backend) -> None:
        async def scenario():
            await redis_backend._client.hset("bretzel:session:abc", "x", "not json {")
            with pytest.raises(BretzelError, match="not valid JSON"):
                await redis_backend.load("session", "abc")

        run(scenario())



# ───────────────────────────────────────────────────────────────────────────
# delete / health / close
# ───────────────────────────────────────────────────────────────────────────


class TestMisc:
    def test_delete(self) -> None:
        client = _fake_client()
        backend = RedisBackend(client)
        run(backend.delete("session", "abc"))
        client.delete.assert_called_once_with("bretzel:session:abc")

    def test_health_ok(self) -> None:
        client = _fake_client()
        client.ping.return_value = True
        assert run(RedisBackend(client).health()) is True

    def test_health_swallows_errors(self) -> None:
        client = _fake_client()
        client.ping.side_effect = ConnectionError("nope")
        assert run(RedisBackend(client).health()) is False

    def test_close(self) -> None:
        client = _fake_client()
        run(RedisBackend(client).close())
        client.aclose.assert_called_once()


# ───────────────────────────────────────────────────────────────────────────
# scan / clear_scope — async generator wiring
# ───────────────────────────────────────────────────────────────────────────


def _scan_yielding(*items: str):
    """Build a ``scan_iter``-shaped factory that yields the given items."""

    async def _factory(match: str | None = None) -> AsyncIterator[str]:
        for it in items:
            yield it

    return _factory


class TestScanClear:
    def test_scan_strips_prefix(self) -> None:
        client = _fake_client()
        client.scan_iter = _scan_yielding(
            "bretzel:session:a", "bretzel:session:b"
        )
        backend = RedisBackend(client)

        async def collect() -> list[str]:
            return [k async for k in backend.scan("session:*")]

        assert run(collect()) == ["session:a", "session:b"]

    def test_clear_scope_deletes_all(self) -> None:
        client = _fake_client()
        client.scan_iter = _scan_yielding(
            "bretzel:session:a", "bretzel:session:b"
        )
        # ``delete`` returns the number of keys removed — emulate.
        client.delete.return_value = 2

        backend = RedisBackend(client)
        count = run(backend.clear_scope("session"))
        assert count == 2
        # One DEL call, with both keys.
        client.delete.assert_called_once_with(
            "bretzel:session:a", "bretzel:session:b"
        )

    def test_clear_scope_empty(self) -> None:
        client = _fake_client()
        backend = RedisBackend(client)
        assert run(backend.clear_scope("session")) == 0
        client.delete.assert_not_called()


# ───────────────────────────────────────────────────────────────────────────
# _chunks helper
# ───────────────────────────────────────────────────────────────────────────


class TestChunks:
    def test_exact_division(self) -> None:
        assert list(_chunks(["a", "b", "c", "d"], 2)) == [["a", "b"], ["c", "d"]]

    def test_remainder(self) -> None:
        assert list(_chunks(["a", "b", "c"], 2)) == [["a", "b"], ["c"]]

    def test_empty(self) -> None:
        assert list(_chunks([], 5)) == []

    def test_size_larger_than_seq(self) -> None:
        assert list(_chunks(["a"], 100)) == [["a"]]
