"""``auth.session_key()`` laisse un programme agir dans la session d'un navigateur.

Le cas de la démo : un visiteur a SON tableau, rangé dans un
``SessionState`` que reconnaît le cookie de son navigateur. Un ``curl``
n'a pas ce cookie ; sans clé, il ouvre une session à lui, et la carte
qu'il crée atterrit sur un tableau que personne ne regarde. La clé nomme
la session : la requête qui la porte en ``Authorization: Bearer`` y
travaille, et lit ce que le navigateur y a écrit.

Les deux versants : la clé ouvre SA session, et rien d'autre — un autre
programme, une clé falsifiée ou expirée, restent dans une session neuve.
"""

from __future__ import annotations

import time

from starlette.testclient import TestClient

from bretzel import Bretzel, auth
from bretzel.server.auth import _sign_until
from bretzel.state import SessionState, field

SECRET = "k" * 32


class Panier(SessionState):
    lignes: int = field(default=0)


def make_app() -> Bretzel:
    app = Bretzel(secret_key=SECRET)

    @app.fastapi.get("/api/cle")
    def cle() -> str:
        return auth.session_key()

    @app.fastapi.post("/api/plus")
    def plus() -> int:
        Panier().lignes += 1
        return Panier().lignes

    @app.fastapi.get("/api/lire")
    def lire() -> int:
        return Panier().lignes

    return app


def bearer(cle: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {cle}"}


def test_a_program_with_the_key_works_in_the_browsers_session() -> None:
    app = make_app()
    with TestClient(app) as navigateur, TestClient(app) as programme:
        cle = navigateur.get("/api/cle").json()
        reponse = programme.post("/api/plus", headers=bearer(cle))
        assert reponse.json() == 1
        assert "set-cookie" not in reponse.headers, (
            "la clé suffit à revenir : la session ne doit pas poser de cookie"
        )
        assert navigateur.get("/api/lire").json() == 1, (
            "le navigateur ne voit pas ce que le programme a écrit avec sa clé"
        )


def test_without_the_right_key_a_program_has_its_own_session() -> None:
    app = make_app()
    expiree = _sign_until(app.config._session_key, "s-quelconque", int(time.time()) - 1)
    # Les deux clients s'ouvrent AVANT toute requête : chaque démarrage de
    # l'app refait son stockage en mémoire, et un client ouvert plus tard
    # effacerait ce que les autres ont écrit — le test passerait à vide.
    with TestClient(app) as navigateur, TestClient(app) as programme:
        cle = navigateur.get("/api/cle").json()
        session, _, signature = cle.rpartition(".")
        falsifiee = f"{session}.{'0' * len(signature)}"
        for autre in ("jeton-de-l-app", falsifiee, expiree):
            programme.post("/api/plus", headers=bearer(autre))
        assert navigateur.get("/api/lire").json() == 0, (
            "une clé qui n'est pas celle de la session a écrit dedans"
        )
