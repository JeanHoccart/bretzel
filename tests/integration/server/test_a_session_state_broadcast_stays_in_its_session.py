"""La diffusion d'un ``SessionState`` reste dans sa session.

Un ``SessionState`` appartient à sa session : quand il change, ce sont les
AUTRES onglets de cette session qui doivent le voir, et personne d'autre.
Le courtier publiait pourtant à toutes les sessions abonnées à l'état, et
chacune redemandait sa propre zone, inchangée.

Relevé le 2026-10-03 sur la démo publique ``examples/kanban`` : le tableau
y est un ``SessionState`` — un tableau par visiteur, pour qu'un inconnu ne
puisse rien écrire chez les autres. Faire en sorte
que deux fenêtres d'un même visiteur se suivent aurait fait recharger le
tableau de CHAQUE visiteur connecté à chaque geste de chacun.

Les deux versants comptent : l'onglet frère de la même session reçoit (le
temps réel est la fonction), l'autre session ne reçoit rien (la portée), et
un ``AppState`` continue d'atteindre tout le monde (partagé par nature).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from bretzel.render.decorators.refreshable import _publish_broadcast
from bretzel.server.sse import MemoryBroker, RedisBroker
from bretzel.state import AppState, SessionState, field

_ETAT = "app.features.donnees::Tableau"


class PanierDuVisiteur(SessionState):
    lignes: int = field(default=0)


class AnnonceCommune(AppState):
    texte: str = field(default="")


async def _ouvrir(broker: Any, session: str, tab: str) -> Any:
    """Ouvre un flux, consomme le bonjour, et rend le générateur vivant."""
    flux = broker.connect(session, tab)
    bonjour = await flux.__anext__()
    assert bonjour.startswith(":"), bonjour
    return flux


def _livraisons(only_session: str) -> dict[str, int]:
    """Deux onglets en session s1, un en s2 ; s1/onglet-a publie."""

    async def tour() -> dict[str, int]:
        broker = MemoryBroker()
        flux = [await _ouvrir(broker, "s1", "onglet-a"),
                await _ouvrir(broker, "s1", "onglet-a-bis"),
                await _ouvrir(broker, "s2", "onglet-b")]
        broker.subscribe("s1", _ETAT)
        broker.subscribe("s2", _ETAT)
        broker.publish(_ETAT, except_tab="onglet-a", only_session=only_session)
        mesure = {broker._conn_tabs.get(conn): q.qsize()
                  for conn, q in broker._queues.items()}
        for f in flux:
            await f.aclose()
        return mesure

    return asyncio.run(tour())


def test_a_session_scoped_signal_reaches_only_its_session() -> None:
    mesure = _livraisons(only_session="s1")
    assert mesure == {"onglet-a": 0, "onglet-a-bis": 1, "onglet-b": 0}, (
        f"le signal d'une session a atteint une autre session : {mesure}")


def test_an_unscoped_signal_still_reaches_every_session() -> None:
    """Versant licite : sans portée, l'autre session reçoit (``AppState``)."""
    mesure = _livraisons(only_session="")
    assert mesure == {"onglet-a": 0, "onglet-a-bis": 1, "onglet-b": 1}, mesure


class _Courtier:
    """Note les publications au lieu de pousser."""

    def __init__(self) -> None:
        self.publie: list[tuple[str, str, str]] = []

    def publish(self, qualname: str, *, except_tab: str = "",
                only_session: str = "") -> None:
        self.publie.append((qualname, except_tab, only_session))


def _contexte(courtier: _Courtier) -> Any:
    return SimpleNamespace(app=SimpleNamespace(sse_broker=courtier),
                           tab_id="onglet-a", session_id="s1")


def test_the_pipeline_scopes_a_session_state_to_its_session() -> None:
    courtier = _Courtier()
    _publish_broadcast(_contexte(courtier), [PanierDuVisiteur])
    [(_, onglet, session)] = courtier.publie
    assert (onglet, session) == ("onglet-a", "s1"), courtier.publie


def test_the_pipeline_leaves_an_app_state_unscoped() -> None:
    courtier = _Courtier()
    _publish_broadcast(_contexte(courtier), [AnnonceCommune])
    [(_, onglet, session)] = courtier.publie
    assert (onglet, session) == ("onglet-a", ""), courtier.publie


def test_the_scope_crosses_redis_workers() -> None:
    """La session visée voyage avec le signal : elle peut tenir son flux
    sur un autre worker que celui qui publie."""
    fakeredis = pytest.importorskip("fakeredis")
    from fakeredis import aioredis

    serveur = fakeredis.FakeServer()
    a = RedisBroker(aioredis.FakeRedis(server=serveur))
    b = RedisBroker(aioredis.FakeRedis(server=serveur))

    async def tour() -> tuple[int, int]:
        await a.start()
        await b.start()
        b.subscribe("s1", _ETAT)
        b.subscribe("s2", _ETAT)
        f1 = await _ouvrir(b, "s1", "onglet-a-bis")
        f2 = await _ouvrir(b, "s2", "onglet-b")
        a.publish(_ETAT, except_tab="onglet-a", only_session="s1")
        recu = await asyncio.wait_for(f1.__anext__(), timeout=2.0)
        assert _ETAT in recu
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(f2.__anext__(), timeout=0.3)
        for f in (f1, f2):
            await f.aclose()
        await a.aclose()
        await b.aclose()
        return 1, 0

    asyncio.new_event_loop().run_until_complete(tour())
