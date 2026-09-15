"""Un backend borne ses attentes — sinon il gare un thread pour toujours.

Ce que ferme ce fichier
------------------------

``RedisBackend`` ne posait ni ``socket_timeout`` ni
``socket_connect_timeout``, et redis-py laisse les deux à ``None`` :
sans fin. Or une lecture d'état part depuis un **thread du pool**
(``StateRegistry._load_via_loop``), qui reste bloqué tant que la réponse
n'arrive pas. Un Redis silencieux — pas refusé, pas coupé : muet — gare
donc ce thread définitivement, sans exception, sans log et sans reprise.
Quarante ainsi garés (le défaut ``anyio``, écrit dans ``core/invoke.py``)
et plus aucun corps d'app synchrone ne tourne. C'est exactement la panne
que le délestage dit exister pour empêcher, déplacée de la boucle vers le
pool.

Et le second plafond n'est pas un doublon du premier : ``socket_timeout``
ne borne qu'une opération sur une connexion **déjà ouverte**. Un hôte qui
avale les paquets sans répondre ne rencontre que ``socket_connect_timeout``
— et c'est celui-là qui pendait au DÉMARRAGE, ``_check_state_backend``
attendant un ``health()`` qui ne revenait jamais.

Pourquoi ces tests n'ouvrent aucune connexion
----------------------------------------------

Rien ici ne parle à un Redis : on lit les options que le client a
retenues, et on fait lever un client factice. Une vraie expiration
demanderait un service qui accepte puis se tait — un banc à part, pas une
suite rapide. Ce fichier prouve que **le plafond est posé** et que
**l'erreur est lisible** ; il ne prouve pas que le noyau le respecte.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path
from typing import Any

import pytest
from redis import asyncio as redis_asyncio
from redis import exceptions as redis_exceptions

from bretzel.core.errors import BretzelError
from bretzel.state.persistence import redis as redis_module
from bretzel.state.persistence.redis import RedisBackend

_URL = "redis://localhost:6379"


def _connection_kwargs(backend: RedisBackend) -> dict[str, Any]:
    return dict(backend._client.connection_pool.connection_kwargs)


# ── Le plancher : le défaut de redis-py est-il toujours « sans fin » ? ──


def test_redis_py_still_defaults_to_no_deadline_at_all() -> None:
    """Le plancher, et il regarde la BIBLIOTHÈQUE, pas notre code.

    Que nos deux valeurs soient finies ne prouve rien si redis-py en
    posait déjà : le jour où il se met à borner tout seul, ce fichier
    testerait une propriété qui ne vient plus de nous, et le retrait de
    nos ``setdefault`` passerait inaperçu. Mesuré le 2026-09-04 : les
    deux valent ``None``.
    """
    nu = redis_asyncio.Redis.from_url(_URL)
    kwargs = dict(nu.connection_pool.connection_kwargs)
    assert kwargs.get("socket_timeout") is None
    assert kwargs.get("socket_connect_timeout") is None


# ── Les deux plafonds sont posés ────────────────────────────────────


@pytest.mark.parametrize(
    "option", ["socket_timeout", "socket_connect_timeout"]
)
def test_the_backend_posts_a_finite_deadline(option: str) -> None:
    valeur = _connection_kwargs(RedisBackend.from_url(_URL)).get(option)
    assert valeur is not None, (
        f"{option} est sans fin : une attente qui ne rend jamais garde son "
        f"thread du pool pour toujours."
    )
    assert 0 < valeur <= 30, (
        f"{option} vaut {valeur} s — un plafond de PANNE au-delà d'une "
        f"poignée de secondes ne borne plus rien d'utile."
    )


# ── … et l'exploitant garde la main ─────────────────────────────────


def test_the_url_outranks_the_framework_default() -> None:
    """Le sens de préséance, vérifié plutôt que supposé.

    redis-py applique les options de l'URL APRÈS les kwargs, donc notre
    ``setdefault`` est bien un DÉFAUT. Si le sens s'inversait, le
    plafond du framework deviendrait un plafond imposé, et une instance
    légitimement lente n'aurait plus aucun recours.
    """
    backend = RedisBackend.from_url(f"{_URL}?socket_timeout=17")
    assert _connection_kwargs(backend)["socket_timeout"] == 17.0


def test_an_explicit_kwarg_is_kept() -> None:
    backend = RedisBackend.from_url(_URL, socket_timeout=3.0)
    assert _connection_kwargs(backend)["socket_timeout"] == 3.0


# ── L'erreur est une phrase, pas une trace ──────────────────────────


class _ClientQuiSeTait:
    """Un client dont l'opération expire — la panne, sans le réseau."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def hgetall(self, key: str) -> dict[str, str]:
        raise self._exc


@pytest.mark.parametrize(
    ("levee", "attendu"),
    [
        (redis_exceptions.TimeoutError("timed out"), "socket_timeout"),
        (redis_exceptions.ConnectionError("refusée"), "injoignable"),
    ],
)
def test_a_transport_failure_says_what_to_do(
    levee: Exception, attendu: str
) -> None:
    backend = RedisBackend(_ClientQuiSeTait(levee))  # type: ignore[arg-type]
    with pytest.raises(BretzelError) as capture:
        asyncio.run(backend.load("session", "abc"))
    assert attendu in str(capture.value)
    # La cause d'origine reste attachée : on traduit, on n'efface pas.
    assert capture.value.__cause__ is levee


def test_a_response_error_still_passes_through() -> None:
    """La moitié qui coûte : ne PAS avaler ce qui n'est pas du transport.

    ``load`` rattrape lui-même un ``WRONGTYPE`` — une ligne écrite au
    format d'avant — pour la supprimer et rendre « absent ». Si la
    traduction attrapait tout, cette reprise deviendrait une 500.
    """
    autre = redis_exceptions.ResponseError("NOSCRIPT")
    backend = RedisBackend(_ClientQuiSeTait(autre))  # type: ignore[arg-type]
    with pytest.raises(redis_exceptions.ResponseError):
        asyncio.run(backend.load("session", "abc"))


# ── Aucune méthode ne s'échappe en silence ──────────────────────────

#: Ce qui parle au client SANS être traduit, et pourquoi.
_SANS_TRADUCTION = {
    # Avale déjà toute exception et rend ``False`` : c'est son contrat,
    # et le démarrage lit ce booléen.
    "health",
    # Un générateur asynchrone — le décorateur attend une coroutine. Ces
    # deux-là ne sont sur aucun chemin de requête (zéro appelant dans
    # ``bretzel/``, vérifié).
    "scan",
    # Ferme le pool à l'arrêt : il n'y a plus de requête à informer.
    "close",
}


def test_every_method_that_talks_to_redis_is_bounded() -> None:
    """Le cliquet : une méthode neuve ne peut pas oublier la traduction.

    Découverte par la SOURCE — les méthodes dont le corps touche
    ``self._client`` —, pas par une liste recopiée : c'est la seule
    forme qui voit arriver ce qui n'existe pas encore.
    """
    source = Path(inspect.getfile(redis_module)).read_text(encoding="utf-8")
    classe = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ClassDef) and node.name == "RedisBackend"
    )

    def _appelle_le_client(node: ast.AST) -> bool:
        """Une COMMANDE envoyée au client, pas une simple référence.

        Le test porte sur ``self._client.quelque_chose(...)`` : c'est ce
        qui part sur le réseau. ``__init__`` range le client dans un
        attribut sans rien lui demander, et n'a donc rien à traduire.
        """
        return any(
            isinstance(sous, ast.Call)
            and isinstance(sous.func, ast.Attribute)
            and isinstance(sous.func.value, ast.Attribute)
            and sous.func.value.attr == "_client"
            and isinstance(sous.func.value.value, ast.Name)
            and sous.func.value.value.id == "self"
            for sous in ast.walk(node)
        )

    parlantes = {
        node.name
        for node in classe.body
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
        and _appelle_le_client(node)
    }
    # Plancher : la découverte trouve quelque chose. Sans lui, un
    # renommage de ``_client`` viderait l'ensemble et laisserait le test
    # vert sur zéro méthode.
    assert len(parlantes) >= 5, parlantes

    attendues = parlantes - _SANS_TRADUCTION
    non_bornees = {
        nom
        for nom in attendues
        if not hasattr(getattr(RedisBackend, nom), "__wrapped__")
    }
    assert not non_bornees, (
        f"{sorted(non_bornees)} parlent à Redis sans passer par `_bounded` : "
        f"une panne de transport y remonterait nue, et l'attente ne dirait "
        f"pas comment la desserrer. Ajoute le décorateur, ou inscris la "
        f"méthode dans `_SANS_TRADUCTION` avec sa raison."
    )
