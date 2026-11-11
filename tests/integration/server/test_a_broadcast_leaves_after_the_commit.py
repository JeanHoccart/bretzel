"""Gate — une action ne prévient les autres fenêtres qu'APRÈS avoir écrit.

Le défaut qu'elle ferme (2026-10-23)
-------------------------------------
La route d'action publiait le signal ``state-dirty`` juste après le
handler, AVANT le drain de la réponse et AVANT ``commit()``. Le courtier
mémoire pousse le signal tout de suite : une autre fenêtre pouvait donc
relire sa zone pendant que l'action rendait encore la sienne, trouver
l'ANCIEN état, et ne plus jamais recevoir de signal — elle restait
fausse jusqu'au geste suivant.

Trouvé par ``doceo-bretzel`` (le tableau d'un professeur : l'iPad tourne
la page, le PC du vidéoprojecteur suit) : un tour de page sur trois
n'arrivait pas au mur. Mesuré : la relecture du mur, 227 ms après le
clic, rendait la page d'avant ; l'état servi juste après était le bon.
La fenêtre de course est la durée du drain, donc elle grandit avec la
zone que l'action redessine — invisible sur une démo, certaine sur une
vraie page.

Une route d'API, elle, écrivait PUIS publiait (``_save_route_state``) :
les deux portes disent maintenant la même chose.

Ce qu'elle mesure
------------------
Un faux courtier lit le MAGASIN au moment où on lui demande de publier :
la valeur écrite par l'action doit déjà y être. Versant licite : le
signal part bien (sans quoi la gate passerait sur une action muette).
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.runtime import HEADER_PAGE_ID
from bretzel.server.handlers import sign_action
from bretzel.state import AppState, field
from tests._session import session_of


class Compteur(AppState):
    valeur: int = field(default=0, merge="add")


def avancer() -> None:
    Compteur().valeur += 1


@refreshable
def zone() -> None:
    ui.text(f"valeur {Compteur().valeur}")


@page("/")
def accueil() -> None:
    zone()
    ui.button("Avancer", on_click=avancer)


def _app() -> Bretzel:
    app = Bretzel(secret_key="x" * 32, mode="dev")
    app.include(zone, accueil)
    return app


def _valeur_stockee(app: Bretzel) -> int | None:
    """Ce que le magasin contient À CET INSTANT, hors de toute requête."""
    backend = app.state_backend
    for cle in list(backend._data):
        scope, _, key = cle.partition(":")
        donnees = backend.load_sync(scope, key) or {}
        if "valeur" in donnees:
            return int(donnees["valeur"])
    return None


def _cliquer(client: TestClient, app: Bretzel) -> None:
    html = client.get("/").text
    url = re.search(r'hx-post="([^"]+avancer[^"]*)"', html).group(1)
    page_id = re.search(r'data-bz-page-id="([^"]+)"', html).group(1)
    action_id = url.rsplit("/", 1)[-1]
    reponse = client.post(url, data={"_args": ""}, headers={
        "X-Bz-Sig": sign_action(app.config._action_key, action_id, "", session_id=session_of(client)),
        HEADER_PAGE_ID: page_id,
    })
    assert reponse.status_code == 200, reponse.text


def test_the_signal_leaves_once_the_state_is_written(
        monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app()
    vu_au_signal: list[int | None] = []
    with TestClient(app) as client:
        monkeypatch.setattr(app._sse_broker, "publish",
                            lambda nom, **_: vu_au_signal.append(_valeur_stockee(app)))
        _cliquer(client, app)
        _cliquer(client, app)
    assert vu_au_signal, "l'action n'a prévenu personne : la gate ne mesure rien"
    assert vu_au_signal == [1, 2], (
        "le signal est parti avant que l'état soit écrit : une autre fenêtre "
        f"relirait l'ancienne valeur (magasin au moment du signal : {vu_au_signal})")
