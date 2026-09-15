"""Un ``def`` bloquant ne gèle plus l'``event loop`` du worker.

La gate ``tests/consistency/test_app_code_never_runs_on_the_loop.py``
dit que la FORME est partie et que les quatre points d'entrée passent
bien par :func:`bretzel.core.call_without_blocking`. Elle lit du code.
Ici on lit du TEMPS : pendant qu'un handler synchrone dort 600 ms, une
autre requête doit être servie — sinon le délestage ne sert à rien.

Le montage est le seul qui reproduise la panne : **deux threads, un seul
event loop**. ``TestClient`` fait tourner l'app dans la boucle d'un
thread de fond ; deux requêtes émises depuis deux threads Python y
arrivent donc en concurrence, exactement comme deux navigateurs sur un
worker uvicorn. Une requête émise séquentiellement ne prouverait rien —
c'est ce qu'ont fait toutes les suites de ce dépôt pendant que le bug
était vivant.

Mesuré le 2026-09-04, le témoin lancé pendant un blocage de 600 ms —
le contraste ne demande aucune interprétation :

====================  ==========  ==========
le témoin met…        inline      délesté
====================  ==========  ==========
handler d'action      539 ms      13 ms
corps de page         548 ms      11 ms
zone refetchée seule  540 ms      11 ms
====================  ==========  ==========

Inline, le témoin attend ce qu'il reste du blocage — il n'est pas
« lent », il n'est pas SERVI.

``test_the_harness_would_catch_a_regression`` rejoue le montage avec
l'ANCIEN geste remis en place : sans lui, ce fichier resterait vert sur
une boucle bloquée qu'il n'aurait simplement pas su regarder.

Tout vit au niveau MODULE — la route d'action résout ses handlers par
``sys.modules`` et refuse un ``<locals>``.
"""

from __future__ import annotations

import inspect
import re
import threading
import time
from typing import Any

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.runtime import DATA_SUBSCRIBE_URL
from bretzel.server.handlers import encode_action_id, sign_action
from bretzel.state import AppState, field

_SECRET = "x" * 32

#: Assez long pour que la différence soit une évidence, assez court pour
#: que trois scénarios tiennent dans la suite rapide.
_BLOCK = 0.6

_app = Bretzel(secret_key=_SECRET, mode="dev")


class Ticker(AppState):
    n: int = field(default=0)


def blocking_action() -> None:
    """Le cas nominal : un handler d'app qui appelle du code bloquant
    (base synchrone, ``requests.get``, un export PDF…)."""
    time.sleep(_BLOCK)


@page("/")
def light_page() -> None:
    """La requête TÉMOIN : elle ne demande rien, elle doit passer."""
    ui.text("ok")


@page("/lourde")
def blocking_page() -> None:
    time.sleep(_BLOCK)
    ui.text("lourde")


@refreshable(deps=[Ticker], broadcast=[Ticker])
def blocking_zone() -> None:
    time.sleep(_BLOCK)
    ui.text(f"n={Ticker().n}")


@page("/zone")
def zone_page() -> None:
    blocking_zone()


_app.include(light_page)
_app.include(blocking_page)
_app.include(zone_page)


# ───────────────────────────────────────────────────────────────────────────
# Le montage : deux threads, une boucle
# ───────────────────────────────────────────────────────────────────────────


def _race(client: TestClient, slow_request) -> tuple[float, float, bool]:
    """Lancer ``slow_request``, puis un GET témoin pendant qu'elle court.

    Rend ``(durée du témoin, durée de la lente, le témoin a fini avant)``.
    """
    marks: dict[str, tuple[float, float]] = {}

    def slow() -> None:
        t0 = time.perf_counter()
        slow_request()
        marks["slow"] = (t0, time.perf_counter())

    def witness() -> None:
        # Démarre APRÈS la lente — sinon on ne mesure pas la concurrence,
        # on mesure l'ordre d'arrivée.
        time.sleep(_BLOCK / 8)
        t0 = time.perf_counter()
        response = client.get("/")
        assert response.status_code == 200
        marks["fast"] = (t0, time.perf_counter())

    threads = [threading.Thread(target=slow), threading.Thread(target=witness)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    fast_start, fast_end = marks["fast"]
    slow_start, slow_end = marks["slow"]
    return fast_end - fast_start, slow_end - slow_start, fast_end < slow_end


def _assert_loop_stayed_free(witness: float, slow: float, first: bool) -> None:
    assert slow >= _BLOCK, (
        f"la requête lente n'a duré que {slow * 1e3:.0f} ms — elle n'a pas "
        "bloqué du tout, donc la course ne prouve rien."
    )
    assert first, (
        f"le témoin ({witness * 1e3:.0f} ms) n'a été servi qu'APRÈS la "
        f"requête lente ({slow * 1e3:.0f} ms) : la boucle était gelée."
    )
    assert witness < _BLOCK / 2, (
        f"le témoin a mis {witness * 1e3:.0f} ms alors que rien ne le "
        f"retenait — il a attendu une partie du blocage de {_BLOCK * 1e3:.0f} ms."
    )


def _signed_action(handler: Any) -> tuple[str, str]:
    action_id = encode_action_id(handler)
    return action_id, sign_action(_app.config._action_key, action_id, "")


def _post_blocking_action(client: TestClient):
    action_id, sig = _signed_action(blocking_action)

    def go() -> None:
        response = client.post(
            f"/_bretzel/action/{action_id}",
            headers={"X-Bz-Sig": sig},
            data={"_args": ""},
        )
        assert response.status_code in (200, 204), response.status_code

    return go


# ───────────────────────────────────────────────────────────────────────────
# Les trois entrées
# ───────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    with TestClient(_app) as c:
        c.get("/")  # chauffe le thème, les routes et le pool de threads
        yield c


def test_a_blocking_action_handler_serves_other_requests(client) -> None:
    _assert_loop_stayed_free(*_race(client, _post_blocking_action(client)))


def test_a_blocking_page_body_serves_other_requests(client) -> None:
    def go() -> None:
        assert client.get("/lourde").status_code == 200

    _assert_loop_stayed_free(*_race(client, go))


def test_a_blocking_zone_refetch_serves_other_requests(client) -> None:
    """La zone rendue SEULE — le chemin SSE / OOB.

    L'URL n'est pas fabriquée ici : on lit celle que la page a stampée
    pour le runtime, donc le test suit le vrai chemin.
    """
    html = client.get("/zone").text
    match = re.search(rf'{DATA_SUBSCRIBE_URL}="([^"]+)"', html)
    assert match, "la zone n'a pas stampé son URL de refetch"
    url = match.group(1)

    def go() -> None:
        assert client.get(url).status_code == 200

    _assert_loop_stayed_free(*_race(client, go))


# ───────────────────────────────────────────────────────────────────────────
# La preuve que le montage MORD
# ───────────────────────────────────────────────────────────────────────────


def test_the_harness_would_catch_a_regression(client, monkeypatch) -> None:
    """Remettre l'ancien geste doit rendre la course ROUGE.

    Sans ce test, les trois précédents pourraient passer pour une raison
    qui n'a rien à voir — un handler qui ne bloque pas, un témoin servi
    par un cache — et personne ne le saurait.
    """
    import bretzel.server.routing.actions as actions

    async def inline(fn, /, *args, **kwargs):
        result = fn(*args, **kwargs)
        if inspect.iscoroutine(result):
            result = await result
        return result

    monkeypatch.setattr(actions, "call_without_blocking", inline)

    witness, _slow, _first = _race(client, _post_blocking_action(client))
    assert witness >= _BLOCK / 2, (
        f"l'appel INLINE a laissé passer le témoin en {witness * 1e3:.0f} ms "
        "— le montage ne mesure donc pas ce qu'il prétend mesurer (la "
        "requête lente bloque-t-elle vraiment ? le témoin part-il bien "
        "pendant ?)."
    )
