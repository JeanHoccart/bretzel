"""L'onglet qui écrit ne se rediffuse pas à lui-même.

Une zone ``@refreshable(broadcast=[Etat])`` reçoit son HTML DANS la
réponse de l'action qui a muté ``Etat``. Le signal temps réel part
ensuite vers les autres clients — et partait aussi vers celui qui venait
d'écrire, qui redemandait donc chacune de ses zones pour obtenir
exactement ce qu'il affichait déjà.

Mesuré sur ``examples/kanban`` avant l'exclusion : cocher une sous-tâche
coûtait **cinq requêtes et 354 Ko** — l'action à 177 Ko, plus quatre
re-lectures qui renvoyaient la même chose. Après : **une requête**.

Le commentaire de ``_publish_broadcast`` annonçait la chose comme
différée — « needs a per-tab id threaded through the action ». C'est
l'identité que le navigateur tire par chargement de page, portée dans
l'URL du flux (``EventSource`` ne sait pas poser d'en-tête) et dans un
en-tête sur chaque action.

Les DEUX bras comptent
-----------------------
Exclure trop large supprime la fonctionnalité : c'est la SESSION qu'il ne
faut pas exclure — deux onglets d'une même personne doivent continuer à
se voir, et c'est le geste même qu'on recommande pour observer le
partage. Le troisième test tient ce versant.

⚠️ Ce dépôt n'a **aucun** test ``async def`` et pas de ``pytest-asyncio``
(cf. ``pyproject.toml``). Chaque scénario tourne donc dans son propre
``asyncio.run`` : le flux est un générateur asynchrone dont le ``finally``
retire la connexion, il doit vivre et mourir dans la même boucle que les
assertions.
"""

from __future__ import annotations

import asyncio
from typing import Any

from bretzel.server.sse import MemoryBroker

_ETAT = "app.features.donnees::Tableau"


async def _ouvrir(broker: MemoryBroker, session: str, tab: str) -> Any:
    """Ouvre un flux, consomme le bonjour, et rend le générateur vivant."""
    flux = broker.connect(session, tab)
    bonjour = await flux.__anext__()
    assert bonjour.startswith(":"), bonjour
    return flux


def _en_attente(broker: MemoryBroker) -> dict[str, int]:
    """Combien de chunks attendent, par identité d'onglet."""
    return {
        broker._conn_tabs.get(conn_id, ""): queue.qsize()
        for conn_id, queue in broker._queues.items()
    }


def _joue(scenario: Any) -> dict[str, int]:
    """Monte un courtier neuf, joue le scénario, rend les files."""
    broker = MemoryBroker()
    broker.reset()

    async def tour() -> dict[str, int]:
        flux = await scenario(broker)
        mesure = _en_attente(broker)
        for f in flux:
            await f.aclose()
        return mesure

    return asyncio.run(tour())


def test_the_bench_really_delivers_without_exclusion() -> None:
    """Plancher : sans livraison, les deux bras ne mesurent rien."""

    async def scenario(broker: MemoryBroker) -> Any:
        flux = [await _ouvrir(broker, "s1", "onglet-a")]
        broker.subscribe("s1", _ETAT)
        broker.publish(_ETAT)
        return flux

    assert _joue(scenario) == {"onglet-a": 1}, (
        "le courtier ne livre rien du tout — le reste du fichier ne "
        "prouverait qu'une absence de mécanisme")


def test_the_writing_tab_is_skipped() -> None:
    """Le versant INTERDIT : l'onglet nommé ne reçoit pas le signal."""

    async def scenario(broker: MemoryBroker) -> Any:
        flux = [await _ouvrir(broker, "s1", "onglet-a"),
                await _ouvrir(broker, "s2", "onglet-b")]
        broker.subscribe("s1", _ETAT)
        broker.subscribe("s2", _ETAT)
        broker.publish(_ETAT, except_tab="onglet-a")
        return flux

    mesure = _joue(scenario)
    assert mesure == {"onglet-a": 0, "onglet-b": 1}, (
        f"l'onglet émetteur a reçu sa propre diffusion : {mesure}")


def test_a_sibling_tab_of_the_same_session_still_hears_it() -> None:
    """Le versant LICITE, et c'est lui qui coûte cher à casser.

    Exclure la SESSION au lieu de l'onglet ferait passer le test
    ci-dessus et supprimerait le temps réel pour qui ouvre son tableau
    deux fois — le geste même qu'on recommande pour le voir.
    """

    async def scenario(broker: MemoryBroker) -> Any:
        flux = [await _ouvrir(broker, "s1", "onglet-a"),
                await _ouvrir(broker, "s1", "onglet-a-bis")]
        broker.subscribe("s1", _ETAT)
        broker.publish(_ETAT, except_tab="onglet-a")
        return flux

    mesure = _joue(scenario)
    assert mesure.get("onglet-a-bis") == 1, (
        f"le second onglet de la MÊME session n'a rien reçu : {mesure}. "
        f"L'exclusion porte sur la session au lieu de l'onglet.")
    assert mesure.get("onglet-a") == 0, mesure


def test_a_silent_client_keeps_the_old_behaviour() -> None:
    """Un runtime plus ancien n'annonce pas d'onglet : il reçoit tout.

    C'est plus cher, et c'est correct — le taire par défaut supprimerait
    le temps réel pour un client qu'on ne sait pas identifier.
    """

    async def scenario(broker: MemoryBroker) -> Any:
        flux = [await _ouvrir(broker, "s1", "")]
        broker.subscribe("s1", _ETAT)
        broker.publish(_ETAT, except_tab="onglet-a")
        return flux

    assert _joue(scenario) == {"": 1}, "un client muet a été exclu"
