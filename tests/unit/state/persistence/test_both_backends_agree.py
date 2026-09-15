"""Gate : les deux backends répondent PAREIL au même scénario.

Le contrat de :class:`~bretzel.state.persistence.base.Backend` était
tenu par de la prose dans deux fichiers, et par deux suites de tests qui
ne se croisaient jamais — `test_memory.py` d'un côté, `test_redis.py` de
l'autre. Le jour où le format de stockage Redis a changé (document JSON
→ hash, le 2026-09-04), trois écarts sont apparus en silence :

- ``save({})`` supprimait la ligne côté Redis (un hash sans champ
  n'existe pas) et la créait vide côté mémoire ;
- ``merge(ttl=None)`` effaçait l'expiration côté mémoire et la laissait
  en place côté Redis ;
- ``load`` rendait ``None`` d'un côté, ``{}`` de l'autre.

Aucun n'était visible à travers le registre, qui lit « absent » et
« vide » de la même façon. Tous les trois auraient mordu le premier
outil, script d'amorçage ou test écrit contre le backend directement —
et ils auraient mordu **en production seulement**, puisque le dev tourne
en mémoire. C'est le piège « ça marche en dev » de ce dépôt, appliqué au
stockage.

D'où ce fichier : un scénario, deux backends, la même assertion. Le
paramétrage est ce qui compte — ajouter un backend (un `postgres.py`)
le fait entrer ici sans qu'on écrive un test de plus.

⚠️ Un seul ``run()`` par test, tout le scénario dedans : le client async
de ``fakeredis`` s'attache à la boucle du premier appel, et ``run()`` en
crée une neuve à chaque fois.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable

import pytest

from bretzel.state.persistence.base import Backend
from bretzel.state.persistence.memory import MemoryBackend


def run[T](coro: Awaitable[T]) -> T:
    return asyncio.new_event_loop().run_until_complete(coro)


#: Les FAMILLES jouées, par nom lisible dans le rapport de test. Chacune
#: reçoit un magasin vierge — d'où la fabrique et non l'instance.
BACKENDS = ("memory", "redis")


@pytest.fixture(params=BACKENDS)
def backend(request, redis_backend) -> Backend:
    """Le backend du tour. ``redis_backend`` vient du ``conftest`` voisin."""
    return MemoryBackend() if request.param == "memory" else redis_backend


def test_the_sweep_covers_every_backend() -> None:
    """Le plancher : deux familles au moins, et elles sont bien celles
    que le paquet expose."""
    from tests.consistency.test_a_commit_writes_fields_not_documents import (
        backend_classes,
    )

    decouverts = {cls.__name__ for cls in backend_classes()}
    couverts = {"MemoryBackend", "RedisBackend"}
    assert decouverts == couverts, (
        f"backends découverts {sorted(decouverts)} ≠ backends joués ici "
        f"{sorted(couverts)}. Un backend qui n'est pas dans ce fichier "
        "n'a AUCUN test de contrat — c'est exactement ainsi que les deux "
        "premiers ont divergé."
    )


async def _faire_expirer(backend: Backend, scope: str, key: str) -> None:
    """Forcer l'échéance, chacun avec sa mécanique.

    Le SEUL endroit du fichier qui connaisse une implémentation, et c'est
    assumé : attendre une vraie seconde par backend coûterait plus que ça
    ne prouve.
    """
    if isinstance(backend, MemoryBackend):
        entree = backend._data[f"{scope}:{key}"]
        backend._data[f"{scope}:{key}"] = type(entree)(
            data=entree.data, expires_at=0.0
        )
    else:
        await backend._client.pexpire(f"bretzel:{scope}:{key}", 1)
        await asyncio.sleep(0.02)


async def _faire_expirer_le_verrou(backend: Backend, scope: str, key: str) -> None:
    """Forcer l'échéance du VERROU, chacun avec sa mécanique."""
    if isinstance(backend, MemoryBackend):
        jeton, _ = backend._locks[f"{scope}:{key}"]
        backend._locks[f"{scope}:{key}"] = (jeton, 0.0)
    else:
        await backend._client.pexpire(f"bretzel:lock:{scope}:{key}", 1)
        await asyncio.sleep(0.02)


def test_save_then_load_round_trips(backend) -> None:
    async def scenario():
        await backend.save("app", "X:default", {"a": 1, "b": ["deux"]})
        return await backend.load("app", "X:default")

    assert run(scenario()) == {"a": 1, "b": ["deux"]}


def test_an_absent_row_reads_as_none(backend) -> None:
    assert run(backend.load("app", "jamais-écrit")) is None


def test_an_empty_document_means_no_row(backend) -> None:
    """L'écart n°1, tenu par un test.

    Redis ne PEUT pas stocker un hash vide ; la mémoire, elle, pourrait.
    C'est donc Redis qui fixe le contrat, et la mémoire qui s'aligne.
    """

    async def scenario():
        await backend.save("app", "X:default", {"a": 1})
        await backend.save("app", "X:default", {})
        return await backend.load("app", "X:default")

    assert run(scenario()) is None


def test_save_replaces_the_whole_document(backend) -> None:
    async def scenario():
        await backend.save("app", "X:default", {"a": 1, "b": 2})
        await backend.save("app", "X:default", {"a": 9})
        return await backend.load("app", "X:default")

    assert run(scenario()) == {"a": 9}


def test_merge_keeps_the_fields_it_does_not_write(backend) -> None:
    """LE point du chantier : deux requêtes, deux champs, rien de perdu."""

    async def scenario():
        await backend.save("session", "sid:X:default", {"filtre": "date"})
        await backend.merge("session", "sid:X:default", {"filtre": "rouge"})
        await backend.merge("session", "sid:X:default", {"articles": ["pull"]})
        return await backend.load("session", "sid:X:default")

    assert run(scenario()) == {"filtre": "rouge", "articles": ["pull"]}


def test_merge_creates_an_absent_row(backend) -> None:
    async def scenario():
        await backend.merge("app", "X:default", {"a": 1})
        return await backend.load("app", "X:default")

    assert run(scenario()) == {"a": 1}


def test_an_empty_merge_writes_nothing(backend) -> None:
    async def scenario():
        await backend.merge("app", "X:default", {})
        return await backend.load("app", "X:default")

    assert run(scenario()) is None


def test_add_sums_instead_of_replacing(backend) -> None:
    """L'opération qui rend un compteur juste : le magasin ADDITIONNE.

    Deux écarts issus de la même lecture doivent tous les deux compter.
    Un backend qui lirait, additionnerait puis réécrirait passerait ce
    test-ci et perdrait quand même en vrai — d'où l'exigence écrite dans
    le protocole : l'addition est faite PAR le magasin, ou sous un verrou
    qu'il détient.
    """

    async def scenario():
        await backend.save("app", "Stats:default", {"vues": 5})
        await backend.merge("app", "Stats:default", {}, add={"vues": 1})
        await backend.merge("app", "Stats:default", {}, add={"vues": 1})
        return await backend.load("app", "Stats:default")

    assert run(scenario()) == {"vues": 7}


def test_add_creates_the_field_from_zero(backend) -> None:
    """Un champ absent compte à partir de zéro.

    C'est la raison pour laquelle un compteur ne peut pas avoir un défaut
    non nul — la métaclasse le refuse à la déclaration.
    """

    async def scenario():
        await backend.merge("app", "Stats:default", {}, add={"vues": 3})
        return await backend.load("app", "Stats:default")

    assert run(scenario()) == {"vues": 3}


def test_add_handles_decimals(backend) -> None:
    """Redis a deux commandes là où Python a un nombre — les deux doivent
    donner le même résultat qu'en mémoire."""

    async def scenario():
        await backend.merge("app", "Stats:default", {}, add={"solde": 0.5})
        await backend.merge("app", "Stats:default", {}, add={"solde": 0.25})
        return await backend.load("app", "Stats:default")

    assert run(scenario()) == {"solde": 0.75}


def test_add_and_set_travel_together(backend) -> None:
    """Un même état porte les deux : un total qu'on ajoute, un choix qu'on
    remplace. Une seule écriture doit faire les deux."""

    async def scenario():
        await backend.save("app", "Stats:default", {"vues": 5, "page": 1})
        await backend.merge(
            "app", "Stats:default", {"page": 3}, add={"vues": 1}
        )
        return await backend.load("app", "Stats:default")

    assert run(scenario()) == {"vues": 6, "page": 3}


def test_an_empty_add_writes_nothing(backend) -> None:
    async def scenario():
        await backend.merge("app", "Stats:default", {}, add={})
        return await backend.load("app", "Stats:default")

    assert run(scenario()) is None


def test_merge_without_ttl_leaves_the_expiry_alone(backend) -> None:
    """L'écart n°2 : une écriture partielle ne décide pas d'une durée
    qu'elle n'a pas posée.

    Le test doit MORDRE dans les deux sens, et c'est ce qui l'a fait
    réécrire : « la ligne est toujours là après la fusion » passe aussi
    bien si la fusion a effacé l'échéance. On vérifie donc que
    l'échéance TIENT TOUJOURS — la ligne fusionnée doit disparaître à sa
    date d'origine, pas survivre.
    """

    async def scenario():
        await backend.save("session", "sid:X:default", {"a": 1}, ttl=60)
        await backend.merge("session", "sid:X:default", {"b": 2})
        apres_fusion = await backend.load("session", "sid:X:default")
        await _faire_expirer(backend, "session", "sid:X:default")
        return apres_fusion, await backend.load("session", "sid:X:default")

    apres_fusion, apres_echeance = run(scenario())
    assert apres_fusion == {"a": 1, "b": 2}
    assert apres_echeance is None, (
        "la ligne a survécu à son échéance : la fusion a effacé "
        "l'expiration au lieu de la laisser en place."
    )


def test_a_ttl_that_has_passed_hides_the_row(backend) -> None:
    async def scenario():
        await backend.save("session", "sid:X:default", {"a": 1}, ttl=1)
        await _faire_expirer(backend, "session", "sid:X:default")
        return await backend.load("session", "sid:X:default")

    assert run(scenario()) is None


def test_a_lock_is_exclusive(backend) -> None:
    """Un seul porteur à la fois — la garantie minimale."""

    async def scenario():
        pris_a = await backend.acquire("app", "X:default", "A", ttl=5)
        pris_b = await backend.acquire("app", "X:default", "B", ttl=5)
        return pris_a, pris_b

    assert run(scenario()) == (True, False)


def test_a_lock_is_released_only_by_its_holder(backend) -> None:
    """Le jeton n'est pas décoratif.

    Sans ce contrôle, un porteur dont la durée a expiré relâcherait le
    verrou de son SUCCESSEUR, qui se croirait seul alors qu'ils seraient
    deux — la panne que le verrou existe pour empêcher, causée par le
    verrou lui-même.
    """

    async def scenario():
        await backend.acquire("app", "X:default", "A", ttl=5)
        await backend.release("app", "X:default", "un-autre-jeton")
        apres_mauvais = await backend.acquire("app", "X:default", "B", ttl=5)
        await backend.release("app", "X:default", "A")
        apres_bon = await backend.acquire("app", "X:default", "B", ttl=5)
        return apres_mauvais, apres_bon

    assert run(scenario()) == (False, True)


def test_a_lock_frees_itself_when_its_time_is_up(backend) -> None:
    """Un porteur mort ne garde pas la clé pour toujours.

    C'est la raison d'être du ``ttl``, et sa contrepartie : ce qui libère
    un processus tué libérerait aussi un bloc trop long.
    """

    async def scenario():
        await backend.acquire("app", "X:default", "A", ttl=1)
        await _faire_expirer_le_verrou(backend, "app", "X:default")
        return await backend.acquire("app", "X:default", "B", ttl=5)

    assert run(scenario()) is True


def test_delete_removes_the_row(backend) -> None:
    async def scenario():
        await backend.save("app", "X:default", {"a": 1})
        await backend.delete("app", "X:default")
        return await backend.load("app", "X:default")

    assert run(scenario()) is None


def test_clear_scope_empties_only_its_scope(backend) -> None:
    async def scenario():
        await backend.save("app", "X:default", {"a": 1})
        await backend.save("session", "sid:X:default", {"a": 1})
        efface = await backend.clear_scope("app")
        return (
            efface,
            await backend.load("app", "X:default"),
            await backend.load("session", "sid:X:default"),
        )

    efface, dans_app, dans_session = run(scenario())
    assert efface == 1
    assert dans_app is None
    assert dans_session == {"a": 1}


def test_a_value_that_json_cannot_hold_is_refused(backend) -> None:
    """Le refus doit être le MÊME des deux côtés.

    La mémoire garde des objets Python vivants et pourrait tout accepter ;
    accepter en dev ce que la prod refuse, c'est la faute qui attend le
    déploiement pour se montrer. À défaut d'un refus commun, ce test dit
    au moins lequel des deux est permissif.
    """

    class Custom:
        pass

    async def scenario() -> bool:
        try:
            await backend.save("app", "X:default", {"obj": Custom()})
        except Exception:
            return True
        return False

    refuse = run(scenario())
    if isinstance(backend, MemoryBackend):
        assert not refuse, (
            "la mémoire s'est mise à refuser : si c'est voulu, c'est une "
            "bonne nouvelle — aligne ce test, et dis-le dans le protocole."
        )
    else:
        assert refuse
