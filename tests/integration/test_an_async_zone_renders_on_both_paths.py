"""Une zone ``@refreshable`` ``async`` rend — au premier affichage ET au refresh.

Le bug, mesuré le 2026-08-21 (finding [1], rencontré en construisant
``examples/crm``) : ``RefreshableHandle.__call__`` appelait ``self.fn(...)``
sans jamais l'attendre. Un corps ``async def`` rendait donc une **coroutine
jamais attendue** — que le test ``hasattr(result, "render")`` laissait
tomber. Résultat : une zone **VIDE**, sans exception, sans 500, sans rien
d'autre qu'un ``RuntimeWarning`` que personne ne lit en production.

Ce que ça coûtait, et pourquoi ce n'était pas contournable
-----------------------------------------------------------
``@page`` et ``@layout`` acceptent l'async depuis toujours
(``pipeline._call`` attend si c'est une coroutine). La zone était la seule
surface de rendu à ne pas le faire — et c'est la seule qui compte pour ça :
sur un refetch SSE, **seule la zone se rend**. Une lecture asynchrone n'a
donc aucun endroit où vivre en amont. Le principe 3 du charter (« async
partout ») était faux pour tout ce qui LIT, et c'est ce qui a forcé le CRM
entier à être synchrone.

La convention d'appel ne change pas
------------------------------------
Une zone s'appelle ``zone()``, jamais ``await zone()``, qu'elle soit async
ou non. C'est une décision, pas une facilité : un ``await`` à écrire serait
un ``await`` à oublier, et l'oublier redonnerait exactement la panne
d'origine — silencieuse. ``__call__`` pose donc la section dans l'arbre
tout de suite (la PLACE de la zone se décide à l'appel) et empile son
corps ; ``drain_pending_async_zones`` l'attend ensuite, section repoussée
sur la pile.

Pourquoi les deux chemins sont testés
--------------------------------------
Le rendu complet et le fragment sont **deux appelants distincts** du
drain. N'en câbler qu'un donnerait une zone pleine au premier affichage et
vide à chaque refresh — la moitié la plus difficile à voir, parce qu'elle
demande une action pour se manifester.
"""

from __future__ import annotations

import asyncio
import re

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.server.handlers import encode_action_id, sign_action
from bretzel.state import AppState, field

_SECRET = "y" * 32


class Tally(AppState):
    n: int = field(default=0)


_app = Bretzel(secret_key=_SECRET, mode="dev")


async def read_tally() -> int:
    """Une lecture asynchrone — le point de tout l'exercice.

    ``sleep(0)`` cède vraiment la main à la boucle : un ``async def`` qui
    n'``await`` rien peut se comporter comme du sync par accident.
    """
    await asyncio.sleep(0)
    return Tally().n


@refreshable(deps=[Tally])
async def async_zone() -> None:
    ui.text(f"async={await read_tally()}")


@refreshable(deps=[Tally])
def sync_zone() -> None:
    """Le témoin. Sans lui, une régression du harnais (app qui ne rend
    plus rien) ferait passer les assertions d'absence pour des succès."""
    ui.text(f"sync={Tally().n}")


@refreshable(deps=[Tally])
async def outer_zone() -> None:
    """Une zone async qui en appelle une autre.

    C'est ce cas qui exige que le drain soit une BOUCLE : la zone
    intérieure s'ajoute à la file pendant qu'on attend celle-ci.
    """
    ui.text(f"outer={await read_tally()}")
    inner_zone()


@refreshable(deps=[Tally])
async def inner_zone() -> None:
    ui.text(f"inner={await read_tally()}")


def bump() -> None:
    Tally().n += 1


@page("/")
def home() -> None:
    ui.text("AVANT")
    async_zone()
    ui.text("APRES")
    sync_zone()
    outer_zone()


_app.include(home)


@pytest.fixture(autouse=True)
def _reset():
    yield
    if _app.state_backend is not None:

        async def _wipe() -> None:
            await _app.state_backend.save(
                "app", "Tally:default", {"n": 0}, ttl=None
            )

        asyncio.new_event_loop().run_until_complete(_wipe())


def _signed(action):
    action_id = encode_action_id(action)
    return action_id, sign_action(_app.config._action_key, action_id, "")


# ───────────────────────────────────────────────────────────────────────
# Le témoin — le harnais rend vraiment quelque chose
# ───────────────────────────────────────────────────────────────────────


def test_the_sync_zone_still_renders() -> None:
    with TestClient(_app) as client:
        body = client.get("/").text
    assert "sync=0" in body, (
        "la zone SYNCHRONE ne rend plus — le harnais est cassé, et les "
        "assertions sur la zone async ne prouveraient rien."
    )


# ───────────────────────────────────────────────────────────────────────
# Chemin 1 — la page complète
# ───────────────────────────────────────────────────────────────────────


def test_an_async_zone_renders_on_the_full_page() -> None:
    with TestClient(_app) as client:
        body = client.get("/").text
    assert "async=0" in body, (
        "une zone `@refreshable async` rend VIDE : son corps est une "
        "coroutine que personne n'attend. Le pipeline doit drainer "
        "`ctx.pending_async_zones` avant de descendre l'arbre."
    )


def test_the_zone_lands_where_it_was_CALLED() -> None:
    """La place de la zone se décide à l'appel, pas quand sa donnée arrive.

    C'est la propriété qui rend la convention ``zone()`` tenable : le
    corps est différé, mais la SECTION est posée tout de suite. Sans ça,
    une zone async se retrouverait à la fin de la page — un rendu qui
    dépend de la latence de sa requête.
    """
    with TestClient(_app) as client:
        body = client.get("/").text
    order = [
        m.group(0) for m in re.finditer(r"AVANT|async=\d|APRES|sync=\d", body)
    ]
    assert order[:4] == ["AVANT", "async=0", "APRES", "sync=0"], (
        f"la zone async n'est pas rendue à sa place : {order[:6]}"
    )


def test_a_nested_async_zone_is_drained_too() -> None:
    """Le drain est une boucle, pas une passe."""
    with TestClient(_app) as client:
        body = client.get("/").text
    assert "outer=0" in body and "inner=0" in body, (
        "une zone async appelée DEPUIS une zone async n'est pas rendue — "
        "le drain ne repasse pas sur la file qui a grossi pendant qu'il "
        "attendait."
    )


# ───────────────────────────────────────────────────────────────────────
# Chemin 2 — le fragment, celui qui se perd en silence
# ───────────────────────────────────────────────────────────────────────


def test_an_async_zone_re_renders_on_a_refresh() -> None:
    action_id, sig = _signed(bump)
    with TestClient(_app) as client:
        client.get("/")  # établit la session et les bz-id
        response = client.post(
            f"/_bretzel/action/{action_id}",
            headers={"X-Bz-Sig": sig},
            data={"_args": ""},
        )
    assert response.status_code == 200
    body = response.text
    assert "hx-swap-oob" in body, "aucun fragment OOB n'est revenu"
    assert "sync=1" in body, (
        "la zone SYNCHRONE n'a pas été rafraîchie — le harnais ne prouve "
        "rien sur l'async."
    )
    assert "async=1" in body, (
        "la zone async revient VIDE du refresh alors qu'elle rendait bien "
        "au premier affichage. Le fragment (`render/partials.py`) est un "
        "appelant du drain à part entière : ne câbler que le rendu "
        "complet donne une zone qui marche une fois puis se vide."
    )
    assert "inner=1" in body, (
        "la zone async IMBRIQUÉE ne revient pas du refresh — le drain du "
        "fragment ne boucle pas."
    )
