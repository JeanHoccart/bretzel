"""``Bretzel(api_docs=True)`` documente l'API de l'app, et rien d'autre.

Une app sert son API JSON par des routes ``app.fastapi`` ; le réglage
leur donne ``/openapi.json`` et la page interactive ``/docs``. Ce
fichier tient les quatre choses qui en font une page UTILE plutôt que
celle de FastAPI telle quelle :

1. le schéma liste les routes de l'app, jamais celles du framework ni les
   pages ;
2. il déclare le schéma ``bearer`` : sans lui, « Try it out » n'envoie
   pas la clé, et toute écriture essayée depuis la page reçoit le 403 du
   CSRF ;
3. sous ``csp=``, la page porte SA politique (Swagger vient d'un CDN et
   s'initialise dans un script en ligne) sans l'étendre aux pages ;
4. une page déjà à ``/docs`` fait échouer le démarrage, au lieu que la
   première route enregistrée gagne en silence — mais pas un second
   démarrage de la même app.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page
from bretzel.server.routing.api_docs import INLINE_SCRIPT
from bretzel.server.security import script_hash

SECRET = "k" * 32


@page("/")
def home() -> None:
    return None


def make_app(**kwargs: object) -> Bretzel:
    app = Bretzel(title="École", secret_key=SECRET, **kwargs)  # type: ignore[arg-type]
    app.include(home)

    @app.fastapi.post("/api/eleves")
    def create_eleve(body: dict) -> dict:
        return {"created": body["name"]}

    return app


def test_nothing_is_published_by_default() -> None:
    with TestClient(make_app()) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_the_schema_lists_the_app_routes_and_the_bearer_key() -> None:
    with TestClient(make_app(api_docs=True)) as client:
        schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "École"
    assert list(schema["paths"]) == ["/api/eleves"], (
        "le schéma expose une route qui n'est pas l'API de l'app — une "
        "route du framework a perdu son include_in_schema=False"
    )
    assert schema["components"]["securitySchemes"]["bearer"] == {
        "type": "http",
        "scheme": "bearer",
    }
    assert schema["security"] == [{"bearer": []}]


def test_the_page_loads_the_schema() -> None:
    with TestClient(make_app(api_docs=True)) as client:
        response = client.get("/docs")
    assert response.status_code == 200
    assert "url: '/openapi.json'" in response.text
    assert "content-security-policy" not in response.headers


@pytest.mark.parametrize(
    ("csp", "header"),
    [(True, "content-security-policy"), ("report-only", "content-security-policy-report-only")],
)
def test_under_csp_the_page_carries_its_own_policy(csp: object, header: str) -> None:
    with TestClient(make_app(api_docs=True, csp=csp)) as client:
        docs = client.get("/docs")
        home_page = client.get("/")
    [inline] = INLINE_SCRIPT.findall(docs.text)
    policy = docs.headers[header]
    assert "https://cdn.jsdelivr.net" in policy
    assert script_hash(inline) in policy
    assert "cdn.jsdelivr.net" not in home_page.headers[header], (
        "la politique de /docs a fui sur les pages de l'app"
    )


def test_the_same_app_starts_twice() -> None:
    # Les routes s'enregistrent à CHAQUE démarrage ; le second ``/docs``
    # ne doit se lire ni comme une collision, ni comme un second schéma.
    app = make_app(api_docs=True)
    with TestClient(app):
        pass
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").json()["security"] == [{"bearer": []}]


def test_a_page_already_at_docs_refuses_to_start() -> None:
    @page("/docs")
    def user_docs() -> None:
        return None

    app = make_app(api_docs=True)
    app.include(user_docs)
    with pytest.raises(RuntimeError, match="/docs"), TestClient(app):
        pass
