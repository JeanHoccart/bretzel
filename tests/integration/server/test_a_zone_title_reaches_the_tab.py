"""Un ``ui.title`` rendu par une zone rafraîchie atteint l'onglet.

Ce que ça ferme, mesuré le 2026-09-29
--------------------------------------
``ui.title`` écrit ``ctx.head_title`` ; le pipeline ne le lisait qu'en
rendant une PAGE (document complet, ou navigation partielle qui pousse
``HX-Trigger: {"bretzel:title": …}``). Une action qui re-rend une zone
``@refreshable`` contenant ``ui.title`` rendait le nouveau titre… dans le
vide : le rendu partiel ne le transmettait pas, et l'onglet gardait
l'ancien jusqu'à la prochaine navigation. Le playground affirmait
l'inverse (``examples/playground/features/meta.py``).

Le runtime écoute déjà ``bretzel:title`` (``bridge.js``) : il manquait
seulement l'en-tête sur la réponse d'action.

Le versant licite : une action dont les zones n'appellent pas
``ui.title`` ne pousse aucun titre — sinon chaque clic réécrirait
l'onglet avec le titre du décorateur.
"""

from __future__ import annotations

import json

from starlette.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.render.context import current_context
from bretzel.runtime.protocol import TITLE_EVENT
from bretzel.server.handlers import encode_action_id, sign_action
from bretzel.state import SessionState, field
from tests._session import session_of

_SECRET = "t" * 32


class Titre(SessionState):
    texte: str = field(default="Avant")


class Compteur(SessionState):
    """Un état À PART : sans ``X-Bretzel-Zones``, le drain rend toute zone
    qui dépend de l'état muté, même absente de la page — partager ``Titre``
    ferait re-rendre ``zone_titree`` au versant licite."""

    n: int = field(default=0)


@refreshable
def zone_titree() -> None:
    ui.title(Titre().texte)
    ui.text(f"TITRE={Titre().texte}")


@refreshable
def zone_muette() -> None:
    ui.text(f"N={Compteur().n}")


def renommer() -> None:
    Titre().texte = "Après"


def renommer_et_signaler() -> None:
    """Un handler qui pose SON PROPRE ``HX-Trigger`` : le titre s'y ajoute."""
    Titre().texte = "Après"
    current_context().set_header("HX-Trigger", json.dumps({"app:saved": 1}))


def compter() -> None:
    Compteur().n += 1


def _monter(zone) -> Bretzel:
    app = Bretzel(secret_key=_SECRET, mode="dev")

    @page("/", title="Décorateur")
    def home() -> None:
        zone()

    app.include(home)
    return app


def _agir(client: TestClient, app: Bretzel, handler):
    action_id = encode_action_id(handler)
    sig = sign_action(app.config._action_key, action_id, "", session_id=session_of(client))
    return client.post(
        f"/_bretzel/action/{action_id}",
        headers={"X-Bz-Sig": sig},
        data={"_args": ""},
    )


def _triggers(response) -> dict:
    raw = response.headers.get("HX-Trigger")
    return json.loads(raw) if raw else {}


def test_the_page_title_comes_from_the_zone() -> None:
    """Plancher : la zone pose bien le titre au rendu de la page."""
    app = _monter(zone_titree)
    with TestClient(app) as client:
        html = client.get("/").text
    assert "<title>Avant</title>" in html


def test_an_action_pushes_the_title_its_zone_rendered() -> None:
    app = _monter(zone_titree)
    with TestClient(app) as client:
        client.get("/")
        reponse = _agir(client, app, renommer)
    assert reponse.status_code == 200 and "TITRE=Après" in reponse.text
    assert _triggers(reponse).get(TITLE_EVENT) == "Après", (
        f"HX-Trigger reçu : {reponse.headers.get('HX-Trigger')!r}. La zone a "
        f"rendu ui.title('Après') mais l'onglet n'en saura rien avant la "
        f"prochaine navigation."
    )


def test_the_title_joins_a_trigger_the_handler_set() -> None:
    """Un seul en-tête ``HX-Trigger`` : le titre ne doit pas écraser celui
    de l'app, ni l'inverse."""
    app = _monter(zone_titree)
    with TestClient(app) as client:
        client.get("/")
        reponse = _agir(client, app, renommer_et_signaler)
    triggers = _triggers(reponse)
    assert triggers.get(TITLE_EVENT) == "Après", triggers
    assert triggers.get("app:saved") == 1, triggers


def test_a_zone_without_ui_title_pushes_no_title() -> None:
    """Le versant licite : pas de ``ui.title`` rendu, pas de titre poussé."""
    app = _monter(zone_muette)
    with TestClient(app) as client:
        client.get("/")
        reponse = _agir(client, app, compter)
    assert reponse.status_code == 200 and "N=1" in reponse.text
    assert TITLE_EVENT not in _triggers(reponse), reponse.headers.get("HX-Trigger")
