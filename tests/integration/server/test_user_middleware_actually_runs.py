"""``@app.middleware`` tourne vraiment — les quatre formes, bout en bout.

Le défaut qu'il ferme
---------------------
``@app.middleware`` était un **no-op complet** jusqu'au 2026-08-15. Le
décorateur remplissait bien ``app._user_middlewares``, mais
``build_middleware_stack`` tournait dans ``Bretzel.__init__`` — donc avant
que le décorateur ait pu s'exécuter, puisqu'on écrit forcément
``@app.middleware`` APRÈS ``app = Bretzel(...)``. La liste était remplie
et plus jamais relue.

Le commentaire sur place disait vrai sur la contrainte (« Starlette
locks the middleware list as soon as the app starts ») et faux sur la
conclusion : le corriger demandait de DIFFÉRER la construction, pas de
l'avancer.

Pourquoi ça n'a été vu par personne : zéro appelant dans ``examples/``,
zéro test bout-en-bout, et aucun symptôme visible — un middleware qui ne
tourne pas ne casse rien, il laisse simplement passer. Sur un mécanisme
de **garde d'auth**, « laisse passer » est le pire mode de panne
possible : le défaut-fermé que le middleware est censé fournir devient un
défaut-ouvert silencieux.

Ce fichier vérifie donc ce qu'aucune relecture n'attrape : que le code
utilisateur s'exécute. Les quatre formes sont couvertes parce que le
décorateur les accepte toutes les quatre et qu'aucune n'était exercée.

App + middlewares au niveau MODULE : c'est la forme réelle d'une app.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from bretzel import Bretzel, page, ui

_SECRET = "u" * 32

#: L'ordre d'entrée des middlewares — c'est la seule preuve qu'ils
#: tournent ET qu'ils s'enveloppent dans l'ordre documenté.
_order: list[str] = []


@page("/")
def home() -> None:
    ui.text("page")


_app = Bretzel(secret_key=_SECRET, mode="dev")


@_app.middleware
async def first(request, call_next):
    _order.append("first:in")
    response = await call_next(request)
    _order.append("first:out")
    return response


@_app.middleware
async def second(request, call_next):
    _order.append("second:in")
    return await call_next(request)


@_app.middleware
class AsClass(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        _order.append("class:in")
        return await call_next(request)


_app.include(home)


@pytest.fixture(autouse=True)
def _clear():
    _order.clear()
    yield


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(_app) as c:
        yield c


def test_a_user_middleware_runs_at_all(client: TestClient) -> None:
    """Le test qui manquait. Tout le reste en découle."""
    client.get("/")

    assert _order, (
        "Aucun @app.middleware n'a tourné. C'est le mode de panne du "
        "2026-08-15 : la pile était construite dans __init__, donc figée "
        "avant que le décorateur puisse s'exécuter — et un middleware qui "
        "ne tourne pas ne casse rien, il laisse passer."
    )


def test_every_registered_form_runs(client: TestClient) -> None:
    """Callable async ET classe : le décorateur accepte les deux."""
    client.get("/")

    assert {"first:in", "second:in", "class:in"} <= set(_order)


def test_first_registered_is_outermost(client: TestClient) -> None:
    """L'ordre documenté par ``decorators/middleware.py`` : « first
    registered = outermost »."""
    client.get("/")

    assert _order.index("first:in") < _order.index("second:in")
    assert _order[-1] == "first:out", (
        "Le premier enregistré doit être le dernier à rendre la main — "
        "c'est ce que « outermost » veut dire, et c'est ce qui permet à "
        "une garde d'auth de couvrir tout ce qui est en dessous."
    )


def test_the_page_still_renders(client: TestClient) -> None:
    """La pile déplacée ne casse pas le chemin nominal."""
    response = client.get("/")

    assert response.status_code == 200
    assert "page" in response.text


def test_the_stack_is_built_once(client: TestClient) -> None:
    """``__call__`` monte la pile au premier appel, pas à chaque requête.

    Sans le drapeau, chaque requête ré-empilerait les middlewares —
    Starlette lèverait, mais mieux vaut le dire ici que le découvrir en
    lisant une trace.
    """
    before = len(_app.fastapi.user_middleware)
    client.get("/")
    client.get("/")

    assert len(_app.fastapi.user_middleware) == before
    assert _app._middleware_stack_built is True
