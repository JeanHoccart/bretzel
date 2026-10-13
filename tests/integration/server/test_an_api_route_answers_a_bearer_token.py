"""Une route d'API écrit avec un jeton, et seulement avec un jeton.

Une app Bretzel fournit son API dans le même serveur que ses pages :
une route ``app.fastapi.post`` qui appelle la même fonction métier que
l'écran, et un ``@auth.source`` qui reconnaît la clé de l'appelant.
Jusqu'ici, tout POST d'un autre programme recevait 403 : il n'a ni
cookie de session ni jeton CSRF, et le CSRF est toujours actif.

Ce fichier monte la pile COMPLÈTE — session, CSRF, auth, contexte de
rendu — parce que le contrat tient à leur ordre : le CSRF laisse passer
le porteur, PUIS l'auth lit le même en-tête pour dire qui parle. Les deux
sens sont tenus : sans jeton, le POST reste refusé.
"""

from __future__ import annotations

from fastapi import Request
from starlette.testclient import TestClient

from bretzel import Bretzel, auth

KEYS = {"cle-du-partenaire": "u-partenaire"}


@auth.source
def from_api_key(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    return KEYS.get(token.strip())


def make_app() -> Bretzel:
    app = Bretzel(title="api", secret_key="k" * 32)
    app.include(from_api_key)

    @app.fastapi.post("/api/eleves")
    def create_eleve(body: dict, request: Request) -> dict:
        return {"created": body["name"], "by": request.state.user_id}

    return app


def test_a_program_with_a_key_writes_through_the_api() -> None:
    with TestClient(make_app()) as client:
        response = client.post(
            "/api/eleves",
            json={"name": "Ada"},
            headers={"Authorization": "Bearer cle-du-partenaire"},
        )
    assert response.status_code == 200, response.text
    assert response.json() == {"created": "Ada", "by": "u-partenaire"}


def test_a_program_without_a_key_is_still_refused() -> None:
    with TestClient(make_app()) as client:
        response = client.post("/api/eleves", json={"name": "Ada"})
    assert response.status_code == 403
    assert "CSRF" in response.text
