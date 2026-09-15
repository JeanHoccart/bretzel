"""Deux requêtes qui se chevauchent ne s'effacent plus l'une l'autre.

Le commit réécrivait le document ENTIER (``backend.save(to_dict())``).
Deux requêtes sur la même session — deux onglets, deux clics rapides,
une action pendant un rafraîchissement — lisaient donc la même base, et
la seconde à commiter rendait invisible ce que la première avait écrit.
Sans erreur, sans trace : c'est la « mise à jour perdue ».

Le chevauchement est écrit ICI en toutes lettres — A lit, B lit, A
écrit, B écrit — plutôt que joué au chronomètre. Une course reproduite
par le temps est une course qu'on ne reproduit pas : elle passe neuf
fois sur dix, et la dixième on accuse la machine.

``test_the_old_commit_would_lose_it`` rejoue exactement la même
séquence en écrivant à l'ancienne. Sans lui, ce fichier serait vert pour
une raison qu'on n'aurait pas vérifiée — par exemple parce que les deux
registres ne partagent pas vraiment leur stockage.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable

from bretzel.state.fields.descriptor import field
from bretzel.state.persistence.memory import MemoryBackend
from bretzel.state.registry import StateRegistry, use_registry
from bretzel.state.scopes.server import ServerState


def run[T](coro: Awaitable[T]) -> T:
    return asyncio.new_event_loop().run_until_complete(coro)


class Boutique(ServerState, scope="session"):
    """Deux champs indépendants — le cas que la fusion répare."""

    filtre: str = field(default='')
    articles: list[str] = field(default_factory=list)


class Vue(ServerState, scope="session", addressable=True):
    """Un champ semé depuis l'URL — le piège de la photo de référence."""

    tri: str = field(default="date", url="tri")


def _ouvrir(backend: MemoryBackend) -> StateRegistry:
    """Une requête qui commence : son registre lit le stockage partagé."""
    return StateRegistry(backend, session_id="sid")


def test_a_concurrent_field_survives_the_commit() -> None:
    """A change le filtre, B le panier, personne ne perd rien."""
    backend = MemoryBackend()

    requete_a = _ouvrir(backend)
    with use_registry(requete_a):
        Boutique().filtre = "rouge"

    # B ouvre AVANT que A n'ait commité : c'est le chevauchement, et
    # c'est exactement ce que fait un second onglet.
    requete_b = _ouvrir(backend)
    with use_registry(requete_b):
        Boutique().articles = ["pull"]

    run(requete_a.commit())
    run(requete_b.commit())

    # Relu comme l'app le relirait — par un registre neuf, pas en
    # allant fouiller la forme du stockage.
    relecture = _ouvrir(backend)
    with use_registry(relecture):
        apres = Boutique()

    assert apres.filtre == "rouge", (
        "le commit de B a effacé le champ que A avait écrit — le "
        "document entier est réécrit au lieu des champs touchés."
    )
    assert apres.articles == ["pull"]


def test_the_old_commit_would_lose_it() -> None:
    """Le versant qui MORD : la même séquence, écrite à l'ancienne."""
    backend = MemoryBackend()

    requete_a = _ouvrir(backend)
    with use_registry(requete_a):
        a = Boutique()
        a.filtre = "rouge"

    requete_b = _ouvrir(backend)
    with use_registry(requete_b):
        b = Boutique()
        b.articles = ["pull"]

    # L'ancien commit : tout le document, à chaque fois.
    run(backend.save("session", "sid:Boutique:default", a.to_dict()))
    run(backend.save("session", "sid:Boutique:default", b.to_dict()))

    relecture = _ouvrir(backend)
    with use_registry(relecture):
        apres = Boutique()

    assert apres.filtre == "", (
        "écrire le document entier devrait perdre le champ de A — s'il "
        "survit, c'est que les deux registres ne partagent pas leur "
        "stockage et que le test d'à côté ne prouve rien."
    )


def test_the_same_field_is_still_lost_and_that_is_written() -> None:
    """La limite, tenue par un test plutôt que par une phrase.

    Deux écritures du même champ restent une
    lecture-modification-écriture : le second gagne. Aucune fusion ne
    peut deviner qu'il fallait garder les deux — il y faudrait un verrou
    sur toute la requête, qui mettrait en file toutes les requêtes d'une
    même session. Le jour où ce test devient rouge, c'est que quelqu'un
    a livré ce verrou : c'est une bonne nouvelle, pas une régression.

    ⚠️ **Sauf si le champ dit ce qu'il est.** Un champ déclaré
    ``Counter`` s'écrit en ÉCART, et deux incréments concurrents comptent
    tous les deux — cf.
    ``tests/unit/state/test_a_counter_counts_every_click.py``. La limite
    tenue ici est donc celle d'un champ ORDINAIRE, qui ne peut rien dire
    de la façon dont ses écritures se combinent.
    """
    backend = MemoryBackend()

    requete_a = _ouvrir(backend)
    with use_registry(requete_a):
        Boutique().articles = ["pull"]

    requete_b = _ouvrir(backend)
    with use_registry(requete_b):
        Boutique().articles = ["écharpe"]

    run(requete_a.commit())
    run(requete_b.commit())

    relecture = _ouvrir(backend)
    with use_registry(relecture):
        apres = Boutique()

    assert apres.articles == ["écharpe"], (
        f"attendu la limite connue (le second écrase), obtenu "
        f"{apres.articles!r}"
    )


def test_an_untouched_state_writes_nothing() -> None:
    """Un état sale dont aucun champ n'a bougé n'écrit pas.

    Le cas arrive quand une mutation revient à sa valeur d'origine dans
    la même requête. Écrire alors rafraîchirait le TTL d'une session que
    personne n'a modifiée.
    """
    backend = MemoryBackend()
    ecritures: list[dict[str, object]] = []
    fusion = backend.merge

    async def espion(scope, key, changes, *, ttl=None):  # type: ignore[no-untyped-def]
        ecritures.append(dict(changes))
        await fusion(scope, key, changes, ttl=ttl)

    requete = _ouvrir(backend)
    with use_registry(requete):
        etat = Boutique()
        etat.filtre = "rouge"
        etat.filtre = ""

    backend.merge = espion  # type: ignore[method-assign]
    run(requete.commit())

    assert ecritures == [], f"écrit {ecritures} alors que rien n'a changé"


def test_a_url_seeded_field_is_persisted() -> None:
    """Le semis d'URL doit être ÉCRIT, pas seulement affiché.

    Le piège tient à l'ordre : le registre prend deux photos, et le
    semis passe entre les deux. Si la photo « ce qui est en base » est
    prise APRÈS le semis, ``?tri=nom`` se lit comme déjà stocké — donc
    n'est jamais écrit —, et l'action suivante, dont l'URL ne porte
    aucune query, retrouve l'ancien tri.

    Mesuré tel quel pendant l'écriture de la fusion : le tri revenait à
    son défaut au premier clic. C'est la régression que ce test
    interdit de refaire.
    """
    backend = MemoryBackend()

    # La page arrive avec ``?tri=nom``.
    rendu = StateRegistry(backend, session_id="sid", url_params={"tri": "nom"})
    with use_registry(rendu):
        assert Vue().tri == "nom"
    run(rendu.commit())

    # L'action qui suit ne porte AUCUNE query — c'est le cas normal.
    action = StateRegistry(backend, session_id="sid")
    with use_registry(action):
        apres = Vue()

    assert apres.tri == "nom", (
        "le semis d'URL n'a pas été persisté : la photo de référence du "
        "commit est prise après le semis, qui se lit donc comme « déjà "
        "stocké »."
    )
