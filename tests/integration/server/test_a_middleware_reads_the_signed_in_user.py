"""``auth.user_id(request)`` — l'identité, lue là où rien ne répond.

Le défaut qu'elle ferme (finding [22], prédit le 2026-08-14)
-------------------------------------------------------------
La garde d'auth de Bretzel est un **middleware** — décision utilisateur,
défaut-FERMÉ. Mais un middleware utilisateur est monté le plus EXTERNE
(``lifecycle.py`` : « user middlewares last so they wrap everything
above »), donc à l'inbound il tourne AVANT ceux du framework :
``auth.user_id()`` sans argument lève (pas de contexte de rendu) et
``request.state.user`` n'est pas encore écrit. Il ne restait que le
cookie, et le vérifier demandait la clé **dérivée** —
``app.config._auth_key``, un attribut **privé**, sur le chemin le plus
sensible d'une app.

``todo.md`` le notait le 2026-08-14 avec la prédiction « tout le monde va
le copier ». Le CRM, premier exemple à se connecter pour de vrai, l'a
copiée le 2026-08-20. La prédiction est donc vérifiée sur n = 1, et c'est
ce qui a débloqué la correction.

Ce que le fichier verrouille
-----------------------------
Le complément exact de ``test_middleware_redirect``, qui ne crée **jamais
de session** et prouve donc seulement le refus. Ici on prouve l'autre
moitié : la garde **laisse passer** un connecté, et elle sait **qui**.

⚠️ Elle rend l'identifiant, pas un booléen — une garde qui journalise ou
qui autorise par rôle a besoin du nom, et un booléen l'aurait forcée à
refaire la lecture.

App + handlers au niveau MODULE : la route d'action résout ses handlers
via ``sys.modules`` et rejette les ``<locals>``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, auth, page, ui
from bretzel.server.handlers import encode_action_id, sign_action
from bretzel.server.navigation import redirect_response

_SECRET = "u" * 32
_PUBLIC = {"/login"}
_USER = "u-42"

#: Ce que la garde a LU, requête par requête. C'est l'instrument : sans
#: lui on ne distinguerait pas « laissé passer parce que connecté » de
#: « laissé passer parce que la garde n'a pas tourné ».
_seen: list[str | None] = []


def sign_me_in() -> None:
    auth.login(_USER)


@page("/login")
def login_page() -> None:
    ui.button("Entrer", on_click=sign_me_in)


@page("/prive")
def private_page() -> None:
    ui.text("Zone privée")


_app = Bretzel(secret_key=_SECRET, mode="dev")


@_app.middleware
async def require_login(request, call_next):
    """La garde, écrite comme la documente ``handlers.md`` — sans un seul
    attribut privé."""
    path = request.url.path
    if path in _PUBLIC or path.startswith("/_bretzel"):
        return await call_next(request)
    user_id = auth.user_id(request)
    _seen.append(user_id)
    if user_id:
        return await call_next(request)
    return redirect_response(request, "/login")


_app.include(login_page, private_page)


@pytest.fixture(autouse=True)
def _clear():
    _seen.clear()
    yield


@pytest.fixture
def client() -> TestClient:
    """Un client NEUF par test : le bocal à cookies est l'état sous test."""
    with TestClient(_app, raise_server_exceptions=False) as c:
        yield c


def _sign_in(client: TestClient) -> None:
    action_id = encode_action_id(sign_me_in)
    sig = sign_action(_app.config._action_key, action_id, "")
    response = client.post(
        f"/_bretzel/action/{action_id}",
        headers={"X-Bz-Sig": sig, "HX-Request": "true"},
        data={"_args": ""},
    )
    # 204 : l'action a tourné et n'a rien à faire swapper.
    assert response.status_code in (200, 204), response.text
    assert auth.COOKIE_AUTH in client.cookies, (
        "auth.login n'a posé aucun cookie — le reste du fichier "
        "mesurerait le vide."
    )


class TestTheGuardLetsASignedInUserThrough:
    def test_an_anonymous_visitor_is_redirected(self, client: TestClient) -> None:
        response = client.get("/prive", follow_redirects=False)

        assert response.status_code == 302
        assert _seen == [None]

    def test_a_signed_in_visitor_passes(self, client: TestClient) -> None:
        _sign_in(client)

        response = client.get("/prive", follow_redirects=False)

        assert response.status_code == 200, (
            "la garde a refusé un visiteur connecté : "
            "auth.user_id(request) ne voit pas le cookie que login() "
            "vient de poser."
        )
        assert "Zone privée" in response.text

    def test_the_guard_knows_which_user(self, client: TestClient) -> None:
        """Le point de conception : un identifiant, pas un booléen."""
        _sign_in(client)
        client.get("/prive")

        assert _seen == [_USER], (
            f"la garde a laissé passer sans savoir qui : {_seen}. Une "
            f"garde qui journalise ou qui autorise par rôle aurait dû "
            f"relire le cookie une deuxième fois."
        )


class TestTheRefusals:
    """Un seul retour — ``None`` — pour toutes les causes de refus."""

    def test_a_forged_cookie_is_refused(self, client: TestClient) -> None:
        client.cookies.set(auth.COOKIE_AUTH, f"{_USER}:99999999999.deadbeef")

        response = client.get("/prive", follow_redirects=False)

        assert response.status_code == 302
        assert _seen == [None], (
            "une signature fabriquée a été acceptée — la vérification "
            "HMAC ne tourne pas."
        )

    def test_a_malformed_cookie_is_refused(self, client: TestClient) -> None:
        client.cookies.set(auth.COOKIE_AUTH, "pas-un-cookie")

        assert client.get("/prive", follow_redirects=False).status_code == 302
        assert _seen == [None]

    def test_a_cookie_signed_with_another_key_is_refused(
        self, client: TestClient
    ) -> None:
        """La clé est bien DÉRIVÉE, pas le ``secret_key`` brut.

        Une implémentation qui signerait avec le secret maître passerait
        les trois tests précédents et échouerait celui-ci — c'est la
        seule façon de distinguer les deux.
        """
        from bretzel.server.crypto import sign

        payload = f"{_USER}:99999999999"
        forged = f"{payload}.{sign(_SECRET.encode(), payload)}"
        client.cookies.set(auth.COOKIE_AUTH, forged)

        assert client.get("/prive", follow_redirects=False).status_code == 302
        assert _seen == [None]
