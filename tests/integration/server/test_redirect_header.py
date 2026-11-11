"""``redirect()`` — l'en-tête arrive vraiment sur la réponse d'action.

La fonction fait UNE chose : poser ``HX-Redirect`` sur la réponse, en
comptant sur deux faits qu'elle ne contrôle pas — que ``ctx`` recopie
ses ``response_headers`` vers la réponse d'action, et qu'htmx traite cet
en-tête nativement. Le premier se teste ici ; le second demande un vrai
navigateur : ``tests/runtime_js/test_redirect_actually_navigates.py``.

Ce que ce fichier verrouille, dans l'ordre où ça casserait :

1. l'en-tête traverse le round-trip d'action jusqu'à la réponse HTTP ;
2. le handler continue après l'appel (pas de sortie non-locale) ;
3. un rendu de page classique REFUSE l'appel au lieu de l'avaler — le
   demi-branchement silencieux est précisément la classe de défaut qui a
   coûté six mois au kind ``"redirect"`` du bridge ;
4. une URL porteuse d'un CR/LF est refusée (response splitting).

App + handlers au niveau MODULE : la route d'action résout ses handlers
via ``sys.modules`` et rejette les ``<locals>``.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, layout, page, redirect, ui
from bretzel.core.errors import BretzelError
from bretzel.server.handlers import encode_action_id, sign_action
from tests._session import session_of

_SECRET = "r" * 32

_app = Bretzel(secret_key=_SECRET, mode="dev")

#: Ce que le handler a exécuté, dans l'ordre. Prouve que ``redirect()``
#: n'interrompt pas — la ligne d'après doit y figurer.
_trace: list[str] = []


def save_and_go() -> None:
    _trace.append("before")
    redirect("/factures/42")
    _trace.append("after")


@page("/form")
def form_page() -> None:
    ui.button("Enregistrer", on_click=save_and_go)


_app.include(form_page)


def go_to_crlf() -> None:
    redirect("/ok\r\nX-Injected: 1")


@page("/crlf")
def crlf_page() -> None:
    ui.button("Injecter", on_click=go_to_crlf)


_app.include(crlf_page)


@page("/plain")
def plain_page() -> None:
    """Une page qui appelle ``redirect()`` pendant son rendu — le cas où
    l'en-tête serait invisible, donc celui qui doit lever."""
    redirect("/ailleurs")


_app.include(plain_page)


@layout
def coque() -> None:
    ui.outlet()


@layout
def autre_coque() -> None:
    ui.outlet()


def go_inside() -> None:
    redirect("/dedans/b?x=1")


def go_other_shell() -> None:
    redirect("/hors-coque")


def go_elsewhere() -> None:
    redirect("https://example.com/x")


@page("/dedans/a", layout=coque)
def dedans_a() -> None:
    ui.button("Dedans", on_click=go_inside)
    ui.button("Autre coque", on_click=go_other_shell)
    ui.button("Ailleurs", on_click=go_elsewhere)


@page("/dedans/b", layout=coque)
def dedans_b() -> None:
    ui.text("b")


@page("/hors-coque", layout=autre_coque)
def hors_coque() -> None:
    ui.text("hors")


_app.include(dedans_a, dedans_b, hors_coque)


@pytest.fixture(autouse=True)
def _clear_trace():
    _trace.clear()
    yield


@pytest.fixture
def client():
    """Un seul client pour tout le fichier.

    ``raise_server_exceptions=False`` partout : les deux tests qui ne
    lèvent pas se comportent à l'identique avec ou sans, et les trois qui
    lèvent ont besoin de lire le statut plutôt que de propager.
    """
    with TestClient(_app, raise_server_exceptions=False) as c:
        yield c


def _post(client: TestClient, action, *, current: str | None = None) -> object:
    action_id = encode_action_id(action)
    sig = sign_action(_app.config._action_key, action_id, "", session_id=session_of(client))
    return client.post(
        f"/_bretzel/action/{action_id}",
        # htmx pose ``HX-Request`` sur toute requête qu'il émet ; la
        # garde de ``redirect()`` s'appuie dessus, donc le test doit
        # reproduire le vrai câblage plutôt que de le contourner.
        headers={
            "X-Bz-Sig": sig,
            "HX-Request": "true",
            # htmx sends the displayed page on every request; it is what
            # tells ``redirect()`` which layout is already mounted.
            **({"HX-Current-URL": f"http://testserver{current}"} if current else {}),
        },
        data={"_args": ""},
    )


class TestActionResponse:
    def test_header_reaches_the_http_response(self, client) -> None:
        client.get("/form")
        response = _post(client, save_and_go)

        assert response.headers.get("HX-Redirect") == "/factures/42"

    def test_handler_keeps_running_after_the_call(self, client) -> None:
        """Pas de sortie non-locale — c'est ce qui distingue ``redirect()``
        d'``abort()``, et ce qu'un humain lit de haut en bas."""
        client.get("/form")
        _post(client, save_and_go)

        assert _trace == ["before", "after"]


class TestPartialNavigation:
    """Like a link: a shared layout stays mounted, only its outlet changes."""

    def test_a_shared_layout_swaps_only_its_outlet(self, client) -> None:
        client.get("/dedans/a")
        response = _post(client, go_inside, current="/dedans/a")

        assert "HX-Redirect" not in response.headers
        assert json.loads(response.headers["HX-Location"]) == {
            "path": "/dedans/b?x=1",
            "target": "#outlet_coque",
            "swap": "morph:innerHTML",
        }

    def test_the_page_answers_that_outlet_without_its_layout(self, client) -> None:
        """The other half of the contract: the GET htmx then issues is a
        partial render, not a document swapped into a ``<main>``."""
        response = client.get(
            "/dedans/b",
            headers={"HX-Request": "true", "HX-Target": "outlet_coque"},
        )

        assert response.status_code == 200
        assert "<body" not in response.text

    @pytest.mark.parametrize(
        ("action", "current", "expected"),
        [
            (go_other_shell, "/dedans/a", "/hors-coque"),
            (go_inside, None, "/dedans/b?x=1"),
        ],
        ids=["no-shared-layout", "unknown-current-page"],
    )
    def test_anything_uncertain_loads_the_whole_document(
        self, client, action, current, expected
    ) -> None:
        client.get("/dedans/a")
        response = _post(client, action, current=current)

        assert "HX-Location" not in response.headers
        assert response.headers.get("HX-Redirect") == expected


class TestGuards:
    def test_plain_page_render_answers_a_real_redirect(self, client) -> None:
        """Sur un GET de page nu, htmx n'est pas dans la boucle : l'en-tête
        ne serait lu par personne. Le rendu s'arrête et le navigateur reçoit
        un vrai 307 (depuis le 2026-11-11 ; avant, ça levait)."""
        response = client.get("/plain", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/ailleurs"

    def test_boosted_partial_nav_is_accepted(self, client) -> None:
        """La même page, demandée par htmx, passe : la réponse d'une nav
        partielle EST lue par htmx. La garde vise le rendu nu, pas la page."""
        response = client.get("/plain", headers={"HX-Request": "true"})

        assert response.status_code == 200
        assert response.headers.get("HX-Redirect") == "/ailleurs"

    def test_crlf_in_url_is_refused(self, client) -> None:
        """Response splitting : une URL de redirection vient souvent d'une
        donnée utilisateur (``?next=``)."""
        client.get("/crlf")
        response = _post(client, go_to_crlf)

        assert response.status_code == 500
        assert "X-Injected" not in response.headers


    def test_another_origin_is_refused(self, client) -> None:
        """Une cible vient souvent de l'utilisateur (``?next=``) : une autre
        origine est refusée, et aucun en-tête ne part (gate :
        ``test_a_redirect_stays_on_this_site``)."""
        client.get("/dedans/a")
        response = _post(client, go_elsewhere, current="/dedans/a")

        assert response.status_code == 500
        assert "HX-Redirect" not in response.headers


class TestCallableOutsideARequest:
    def test_no_context_raises_rather_than_no_op(self) -> None:
        with pytest.raises((RuntimeError, BretzelError)):
            redirect("/nulle-part")
