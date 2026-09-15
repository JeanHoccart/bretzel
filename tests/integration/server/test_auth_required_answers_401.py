"""Un ``UserState`` résolu sans utilisateur répond 401 — sur les DEUX chemins.

Le bug, mesuré le 2026-08-15 : ``AuthRequiredError`` existait en deux
classes sans lien — ``state/registry.py`` (``RuntimeError``, la seule
levée) et ``server/errors.py`` (``HTTPException``, celle qu'exportait
``from bretzel import AuthRequiredError``). Conséquences, dans l'ordre de
gravité :

1. une PAGE qui touchait ``UserState`` anonymement tombait en **500 nu** —
   aucun handler n'était enregistré pour la classe réellement levée, la
   ligne de doc qui affirmait que ``StarletteHTTPException`` la couvrait
   ne parlait que de l'homonyme mort ;
2. un ``except AuthRequiredError`` écrit par l'utilisateur n'attrapait
   **rien**, en silence.

Ce fichier verrouille le comportement observable — un statut sur le fil —
plutôt que la forme des classes (c'est le travail de
``tests/consistency/test_one_name_one_object.py``). Les deux chemins sont
testés séparément parce qu'ils rendent volontairement des corps
différents : une page d'erreur complète côté navigation, un corps nu côté
action (sinon le bridge swappe la page d'erreur *dans* le bouton).

App + handlers au niveau MODULE : la route d'action résout ses handlers
via ``sys.modules`` et rejette les ``<locals>``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, page, ui
from bretzel.core.errors import AuthRequiredError
from bretzel.server.handlers import encode_action_id, sign_action
from bretzel.state import UserState, field

_SECRET = "a" * 32


class Prefs(UserState):
    theme: str = field(default="dark")


@page("/compte")
def account_page() -> None:
    # Aucune auth dans cette app : la résolution du scope ``user`` lève.
    ui.text(Prefs().theme)


def touch_user_state() -> None:
    Prefs().theme = "light"


@page("/action")
def action_page() -> None:
    ui.button("Changer", on_click=touch_user_state)


_app = Bretzel(secret_key=_SECRET, mode="dev", expose_errors=False)
_app.include(account_page, action_page)


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(_app, raise_server_exceptions=False) as c:
        yield c


class TestPagePath:
    def test_anonymous_page_answers_401_not_500(self, client: TestClient) -> None:
        """Le cœur du bug : c'était un 500 nu avant le 2026-08-15."""
        response = client.get("/compte")
        assert response.status_code == 401, (
            f"Attendu 401, reçu {response.status_code}. Un 500 signifie "
            f"qu'aucun handler n'est enregistré pour la classe que "
            f"state/registry.py lève réellement."
        )

    def test_body_is_the_error_page_not_a_traceback(
        self, client: TestClient
    ) -> None:
        body = client.get("/compte").text
        assert "401" in body
        # Le détail « quel scope, quel utilisateur » ne sort jamais.
        assert "Prefs" not in body


def _post(client: TestClient, action) -> object:
    action_id = encode_action_id(action)
    sig = sign_action(_app.config._action_key, action_id, "")
    return client.post(
        f"/_bretzel/action/{action_id}",
        headers={"X-Bz-Sig": sig, "HX-Request": "true"},
        data={"_args": ""},
    )


class TestActionPath:
    def test_anonymous_action_answers_401(self, client: TestClient) -> None:
        client.get("/action")

        assert _post(client, touch_user_state).status_code == 401

    def test_action_body_stays_bare(self, client: TestClient) -> None:
        """Pas de page d'erreur complète : le bridge la swapperait dans le
        bouton qui a déclenché l'action."""
        client.get("/action")

        assert "<!doctype html>" not in _post(client, touch_user_state).text.lower()


class TestUserFacingCatch:
    def test_the_exported_class_catches_the_raised_one(self) -> None:
        """Le second symptôme : ``except AuthRequiredError`` doit mordre.

        Écrit sans TestClient exprès — c'est le code que l'utilisateur
        écrit dans SON handler, et il n'attrapait rien.
        """
        from bretzel import AuthRequiredError as Exported

        with pytest.raises(Exported):
            raise AuthRequiredError("no user")
