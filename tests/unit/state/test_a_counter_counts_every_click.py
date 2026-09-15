"""Deux clics concurrents sur un compteur en font DEUX.

``state.vues += 1`` lit 5, calcule 6, et le commit envoyait « mets 6 ».
Deux requêtes qui avaient lu 5 envoyaient toutes les deux « mets 6 » : il
en manquait un. Ce n'était pas une affaire de Redis — mesuré le
2026-09-04, le backend mémoire perdait l'incrément aussi.

Un champ déclaré ``field(merge="add")`` fait envoyer l'ÉCART au lieu de
la valeur, et c'est le magasin qui additionne. Le code de l'app ne change
pas : ``+= 1`` s'écrit toujours pareil, et c'est la DÉCLARATION qui dit
que ce nombre est un total plutôt qu'un choix.

Le chevauchement est écrit à la main — A lit, B lit, A écrit, B écrit —
plutôt que joué au chronomètre : une course reproduite par le temps est
une course qu'on ne reproduit pas.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable

import pytest

from bretzel.state import field
from bretzel.state.persistence.memory import MemoryBackend
from bretzel.state.registry import StateRegistry, use_registry
from bretzel.state.scopes.server import ServerState


def run[T](coro: Awaitable[T]) -> T:
    return asyncio.new_event_loop().run_until_complete(coro)


class Stats(ServerState, scope="app"):
    """Les trois genres de nombre dans le même état."""

    vues: int = field(default=0, merge="add")
    solde: float = field(default=0.0, merge="add")
    page: int = field(default=1)


def _ouvrir(backend: MemoryBackend) -> StateRegistry:
    return StateRegistry(backend)


def test_two_overlapping_clicks_both_count() -> None:
    backend = MemoryBackend()

    requete_a = _ouvrir(backend)
    with use_registry(requete_a):
        Stats().vues += 1

    # B a lu AVANT que A n'ait commité — le cas des deux onglets.
    requete_b = _ouvrir(backend)
    with use_registry(requete_b):
        Stats().vues += 1

    run(requete_a.commit())
    run(requete_b.commit())

    with use_registry(_ouvrir(backend)):
        assert Stats().vues == 2, (
            "un des deux incréments s'est perdu : le commit a envoyé une "
            "valeur au lieu d'un écart."
        )


def test_a_chosen_value_still_keeps_the_last_writer() -> None:
    """Le pendant : tout n'est pas un total.

    ``page`` est un CHOIX. Deux onglets qui vont à la page 3 et à la
    page 5 doivent donner 5 — pas 7. C'est ce que l'automatisme aurait
    cassé, et c'est pourquoi la déclaration existe.
    """
    backend = MemoryBackend()

    requete_a = _ouvrir(backend)
    with use_registry(requete_a):
        Stats().page = 3
    requete_b = _ouvrir(backend)
    with use_registry(requete_b):
        Stats().page = 5

    run(requete_a.commit())
    run(requete_b.commit())

    with use_registry(_ouvrir(backend)):
        assert Stats().page == 5


def test_both_kinds_travel_in_one_request() -> None:
    """Un total et un choix dans le même état, la même requête."""
    backend = MemoryBackend()

    requete_a = _ouvrir(backend)
    with use_registry(requete_a):
        etat = Stats()
        etat.vues += 1
        etat.solde += 0.5
        etat.page = 3
    requete_b = _ouvrir(backend)
    with use_registry(requete_b):
        etat = Stats()
        etat.vues += 1
        etat.solde += 0.25
        etat.page = 5

    run(requete_a.commit())
    run(requete_b.commit())

    with use_registry(_ouvrir(backend)):
        apres = Stats()
        assert (apres.vues, apres.solde, apres.page) == (2, 0.75, 5)


def test_several_mutations_collapse_into_one_delta() -> None:
    """Trois ajouts dans une requête font UN écart de trois.

    C'est ce qui rend l'écriture juste sans rien comprendre au code : on
    ne compte pas les gestes, on mesure la différence entre ce qu'on a lu
    et ce qu'on a maintenant.
    """
    backend = MemoryBackend()
    ecrits: list[dict[str, object]] = []
    vraie_fusion = backend.merge

    async def espion(scope, key, changes, *, add=None, ttl=None):  # type: ignore[no-untyped-def]
        ecrits.append(dict(add or {}))
        await vraie_fusion(scope, key, changes, add=add, ttl=ttl)

    requete = _ouvrir(backend)
    with use_registry(requete):
        etat = Stats()
        etat.vues += 1
        etat.vues += 1
        etat.vues += 1

    backend.merge = espion  # type: ignore[method-assign]
    run(requete.commit())

    assert ecrits == [{"vues": 3}]


def test_a_decrement_is_just_a_negative_delta() -> None:
    backend = MemoryBackend()
    requete = _ouvrir(backend)
    with use_registry(requete):
        Stats().vues -= 2
    run(requete.commit())
    with use_registry(_ouvrir(backend)):
        assert Stats().vues == -2


def test_a_counter_that_does_not_move_writes_nothing() -> None:
    """Un écart nul n'est pas une écriture.

    Sans ça, une requête qui incrémente puis annule pousserait un
    ``+0`` — et sur un scope à durée, rafraîchirait l'expiration d'un
    état que personne n'a modifié.
    """
    backend = MemoryBackend()
    ecrits: list[object] = []
    vraie_fusion = backend.merge

    async def espion(scope, key, changes, *, add=None, ttl=None):  # type: ignore[no-untyped-def]
        ecrits.append((dict(changes), dict(add or {})))
        await vraie_fusion(scope, key, changes, add=add, ttl=ttl)

    requete = _ouvrir(backend)
    with use_registry(requete):
        etat = Stats()
        etat.vues += 1
        etat.vues -= 1

    backend.merge = espion  # type: ignore[method-assign]
    run(requete.commit())

    assert ecrits == []


def test_a_counter_must_start_at_zero() -> None:
    """Le refus, et sa raison.

    ``HINCRBY`` compte à partir de 0 quand le champ n'existe pas encore :
    un compteur dont le défaut serait 10 écrirait 1 là où l'app affiche
    11, et l'écart ne se rattraperait jamais. Refusé à la déclaration
    plutôt que rattrapé au commit — le backend n'a pas à connaître les
    défauts de chaque état.
    """
    with pytest.raises(TypeError, match="part de zéro"):

        class Mauvais(ServerState, scope="app"):
            vues: int = field(default=10, merge="add")


def test_the_declaration_does_not_disturb_the_type() -> None:
    """``merge=`` ne doit RIEN changer en aval.

    La coercition de formulaire, l'adressage URL et la sérialisation ne
    connaissent que ``int`` et ``float``. Si déclarer un total altérait le
    type du champ, une valeur venue d'un formulaire cesserait d'être
    convertie — une panne sans rapport visible avec les compteurs.
    """
    champs = Stats._all_fields()
    assert champs["vues"].type_ is int
    assert champs["solde"].type_ is float
    assert champs["vues"].merge == "add" and champs["solde"].merge == "add"
    assert champs["page"].merge is None

    # Et la conversion marche pour de vrai : une valeur de formulaire
    # arrive en texte.
    etat = Stats()
    etat.vues = "7"  # type: ignore[assignment]
    assert etat.vues == 7


def test_a_sum_is_refused_on_something_that_cannot_be_summed() -> None:
    """``HINCRBY`` sur du texte rend « hash value is not an integer ».

    Sans ce refus, la faute attendrait la première écriture EN
    PRODUCTION : le dev tourne en mémoire, où additionner deux chaînes
    lève ailleurs et autrement.
    """
    with pytest.raises(TypeError, match="ADDITIONNE"):

        class Mauvais(ServerState, scope="app"):
            nom: str = field(default="", merge="add")


def test_a_typo_in_merge_is_refused() -> None:
    with pytest.raises(ValueError, match="valeurs acceptées"):
        field(merge="ad")
