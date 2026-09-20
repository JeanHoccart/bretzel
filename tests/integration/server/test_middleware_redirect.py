"""``redirect_response`` — la garde d'auth par middleware, bout en bout.

Ce que ce fichier existe pour verrouiller : **un middleware voit deux
natures de requête, et elles n'attendent pas la même réponse.**

Sur un GET de page, il faut une vraie ``302`` — le navigateur la suit.
Sur un POST d'action venant du bridge, il faut un ``200`` +
``HX-Redirect`` : une 302 y serait suivie de façon **transparente** par
``fetch``, et le HTML de ``/login`` finirait swappé **dans le bouton** qui
a déclenché l'action. C'est le piège que chaque utilisateur redécouvre au
débogage, et c'est pour ne pas le faire recopier que la décision vit dans
``server/navigation.py`` plutôt que dans une recette de doc.

Pourquoi un middleware et pas un ``@page(auth=…)`` : décision utilisateur,
réaffirmée le 2026-08-14. Un kwarg par page met la politique de sécurité
en défaut-OUVERT — une page ajoutée sans le kwarg fuit en silence. Un
middleware est en défaut-fermé : tout est protégé sauf une liste publique
explicite.

Pourquoi ``redirect()`` ne suffit pas ici : un middleware utilisateur est
monté le plus EXTERNE (``lifecycle.py`` : « user middlewares last so they
wrap everything above »), donc à l'inbound il tourne AVANT
``RenderContextMiddleware``. ``current_context()`` y lève. Le dernier test
du fichier le prouve, pour que la contrainte reste vérifiée et pas
seulement écrite.

App + handlers au niveau MODULE : la route d'action résout ses handlers
via ``sys.modules`` et rejette les ``<locals>``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, page, ui
from bretzel.core.errors import BretzelError
from bretzel.server.handlers import encode_action_id, sign_action
from bretzel.server.navigation import redirect, redirect_response

_SECRET = "m" * 32
_PUBLIC = {"/login"}

#: Ce que le middleware a fait, pour distinguer « il n'a pas tourné » de
#: « il a laissé passer ».
_trace: list[str] = []


def touch_nothing() -> None:
    _trace.append("handler-ran")


@page("/login")
def login_page() -> None:
    ui.text("Connexion")


@page("/prive")
def private_page() -> None:
    ui.button("Agir", on_click=touch_nothing)


_app = Bretzel(secret_key=_SECRET, mode="dev")


@_app.middleware
async def require_login(request, call_next):
    """La garde. Aucune session n'est jamais créée dans ce fichier : tout
    ce qui n'est pas public est donc redirigé."""
    if request.url.path in _PUBLIC or request.url.path.startswith("/_bretzel/runtime"):
        return await call_next(request)
    if request.url.path.startswith("/_bretzel") and "action" not in request.url.path:
        return await call_next(request)
    _trace.append(f"guard:{request.url.path}")
    return redirect_response(request, "/login")


_app.include(login_page, private_page)


@pytest.fixture(autouse=True)
def _clear_trace():
    _trace.clear()
    yield


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(_app, raise_server_exceptions=False) as c:
        yield c


class TestPlainNavigation:
    def test_page_get_gets_a_real_302(self, client: TestClient) -> None:
        response = client.get("/prive", follow_redirects=False)

        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    def test_the_browser_lands_on_login(self, client: TestClient) -> None:
        response = client.get("/prive")

        assert response.status_code == 200
        assert "Connexion" in response.text

    def test_public_path_is_untouched(self, client: TestClient) -> None:
        response = client.get("/login")

        assert response.status_code == 200
        assert _trace == []


class TestHtmxRequest:
    """Le cœur du sujet : une 302 serait suivie par ``fetch`` en silence."""

    def test_action_post_gets_200_plus_header(self, client: TestClient) -> None:
        action_id = encode_action_id(touch_nothing)
        sig = sign_action(_app.config._action_key, action_id, "")
        response = client.post(
            f"/_bretzel/action/{action_id}",
            headers={"X-Bz-Sig": sig, "HX-Request": "true"},
            data={"_args": ""},
            follow_redirects=False,
        )

        assert response.status_code == 200, (
            "Une 302 sur une requête htmx est suivie de façon transparente "
            "par fetch : le HTML de /login finirait swappé dans le bouton."
        )
        assert response.headers["HX-Redirect"] == "/login"

    def test_the_body_is_empty(self, client: TestClient) -> None:
        """htmx lit l'en-tête et navigue — il ne doit rien avoir à swapper."""
        action_id = encode_action_id(touch_nothing)
        sig = sign_action(_app.config._action_key, action_id, "")
        response = client.post(
            f"/_bretzel/action/{action_id}",
            headers={"X-Bz-Sig": sig, "HX-Request": "true"},
            data={"_args": ""},
        )

        assert response.text == ""

    def test_the_handler_never_ran(self, client: TestClient) -> None:
        """La garde est en amont : le handler protégé ne s'exécute pas."""
        action_id = encode_action_id(touch_nothing)
        sig = sign_action(_app.config._action_key, action_id, "")
        client.post(
            f"/_bretzel/action/{action_id}",
            headers={"X-Bz-Sig": sig, "HX-Request": "true"},
            data={"_args": ""},
        )

        assert "handler-ran" not in _trace

    def test_boosted_nav_also_gets_the_header(self, client: TestClient) -> None:
        """Une nav partielle boostée EST une requête htmx."""
        response = client.get(
            "/prive", headers={"HX-Request": "true"}, follow_redirects=False
        )

        assert response.status_code == 200
        assert response.headers["HX-Redirect"] == "/login"


class TestGuards:
    def test_crlf_in_url_is_refused(self) -> None:
        """Response splitting : l'URL vient souvent d'un ``?next=``."""
        with pytest.raises(ValueError, match="control character"):
            redirect_response(object(), "/ok\r\nX-Injected: 1")

    def test_empty_url_is_refused(self) -> None:
        with pytest.raises(TypeError):
            redirect_response(object(), "")

    def test_redirect_is_not_callable_from_a_middleware(self) -> None:
        """La contrainte qui justifie ``redirect_response``, vérifiée.

        Un middleware utilisateur est le plus externe, donc sans
        ``RenderContext``. Si ça cessait d'être vrai, ``redirect_response``
        perdrait sa raison d'être — mieux vaut le savoir par un test rouge
        que par une relecture.
        """
        with pytest.raises((BretzelError, LookupError, RuntimeError)):
            redirect("/login")
