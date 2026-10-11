"""Une route d'API lit l'état typé et sauvegarde ce qu'elle y écrit.

Une action et une page branchent le registre des états et l'enregistrent
à la fin ; une route déclarée sur ``app.fastapi`` — l'API JSON d'une app —
ne faisait ni l'un ni l'autre. Mesuré le 2026-10-10 : ``Compteur().n += 1``
dans une route rendait 0, et la lecture suivante encore 0. Rien ne
cassait : la route lisait les défauts et perdait ses écritures, en
silence. Une app dont les données vivent dans ses états (le kanban de la
démo) ne pouvait donc pas avoir d'API.

Ce fichier tient les trois versants :

1. ce qu'une route écrit est relu par la requête suivante ;
2. une route qui REFUSE (4xx) ne garde rien de ce qu'elle a écrit avant
   de refuser — y compris quand une ``@error_page`` est rendue à sa place,
   qui sauvegardait jusque-là l'état de la page qu'elle rend ;
3. un état diffusé (``broadcast=``) prévient les fenêtres ouvertes, comme
   après un clic — mais seulement pour une écriture : un GET qui écrit
   (une relecture de zone) ferait relire chaque fenêtre à son tour.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.testclient import TestClient

from bretzel import Bretzel, error_page, refreshable, ui
from bretzel.state import AppState, SessionState, field

SECRET = "k" * 32
#: Un POST d'un programme : le jeton porteur le dispense du token CSRF.
API = {"Authorization": "Bearer programme"}


class Compteur(AppState):
    n: int = field(default=0, merge="add")


class Panier(SessionState):
    lignes: int = field(default=0)


@refreshable(deps=[Compteur], broadcast=[Compteur])
def affichage() -> None:
    ui.text(str(Compteur().n))


def make_app() -> Bretzel:
    app = Bretzel(secret_key=SECRET)

    @app.fastapi.post("/api/plus")
    def plus() -> dict:
        Compteur().n += 1
        Panier().lignes += 1
        return {"n": Compteur().n, "lignes": Panier().lignes}

    @app.fastapi.post("/api/refus")
    def refus() -> dict:
        Compteur().n += 100
        raise HTTPException(409, "refusé après avoir écrit")

    @app.fastapi.get("/api/lire")
    def lire() -> dict:
        return {"n": Compteur().n, "lignes": Panier().lignes}

    @app.fastapi.get("/api/compter-une-visite")
    def visite() -> int:
        Compteur().n += 1
        return Compteur().n

    return app


@error_page(409)
def conflit() -> None:
    ui.text(f"Conflit — compteur à {Compteur().n}")


def test_what_a_route_writes_is_read_back() -> None:
    with TestClient(make_app()) as client:
        assert client.post("/api/plus", headers=API).json() == {"n": 1, "lignes": 1}
        assert client.post("/api/plus", headers=API).json() == {"n": 2, "lignes": 2}
        assert client.get("/api/lire").json() == {"n": 2, "lignes": 2}


def test_a_route_that_refuses_keeps_nothing() -> None:
    with TestClient(make_app()) as client:
        client.post("/api/plus", headers=API)
        assert client.post("/api/refus", headers=API).status_code == 409
        assert client.get("/api/lire").json()["n"] == 1, (
            "une route a gardé ce qu'elle avait écrit AVANT de refuser"
        )


def test_an_error_page_does_not_save_what_the_route_half_wrote() -> None:
    app = make_app()
    app.include(conflit)
    with TestClient(app) as client:
        client.post("/api/plus", headers=API)
        page = client.post("/api/refus", headers=API)
        assert page.status_code == 409
        assert "compteur à 1" in page.text, "la page d'erreur a lu l'écriture refusée"
        assert client.get("/api/lire").json()["n"] == 1, (
            "la page d'erreur a sauvegardé ce que la route avait écrit avant de refuser"
        )


def test_a_get_saves_but_notifies_nobody(monkeypatch: pytest.MonkeyPatch) -> None:
    app = make_app()
    publies: list[str] = []
    with TestClient(app) as client:
        monkeypatch.setattr(app._sse_broker, "publish", lambda nom, **_: publies.append(nom))
        client.get("/api/compter-une-visite")
        assert client.get("/api/lire").json()["n"] == 1
    assert publies == [], f"un GET a prévenu les fenêtres ouvertes : {publies}"


def test_a_broadcast_state_reaches_the_open_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    app = make_app()
    publies: list[str] = []
    with TestClient(app) as client:
        monkeypatch.setattr(app._sse_broker, "publish", lambda nom, **_: publies.append(nom))
        client.post("/api/plus", headers=API)
    assert any(nom.endswith("Compteur") for nom in publies), (
        f"la route a changé un état diffusé sans prévenir : {publies}"
    )
