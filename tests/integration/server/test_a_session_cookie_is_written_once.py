"""Un seul ``Set-Cookie: Bretzel_session`` par réponse, et c'est le bon.

Le défaut mesuré le 2026-08-24
------------------------------
Deux couches écrivent ce cookie : ``SessionMiddleware`` en frappe un neuf
quand la requête n'en portait pas, et ``auth.login`` / ``auth.logout``
le font TOURNER par le contexte de rendu. Sur une connexion au **tout
premier hit**, les deux partaient — et comme le middleware de session est
le plus EXTERNE, son en-tête était ajouté en dernier. Pour un même nom,
le navigateur garde la dernière valeur : la rotation était écrasée.

Ce que ça coûtait vraiment, au-delà de l'inélégance : pendant cette
requête, l'état de portée session s'écrit sous l'identifiant **tourné** —
celui que le navigateur n'allait pas garder. Un brouillon posé dans le
handler de connexion se perdait à la page suivante, sans erreur.

Les deux versants
-----------------
Ce fichier ne vérifie pas seulement qu'on n'écrit plus deux fois : il
vérifie aussi que le middleware **frappe toujours** quand il est seul, et
qu'il **se tait** quand la requête portait déjà une session. Une gate qui
ne tiendrait que le premier versant serait satisfaite par un middleware
débranché.
"""

from __future__ import annotations

from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from bretzel import Bretzel, auth
from bretzel.render.context import current_context
from bretzel.server.auth import COOKIE_SESSION

SECRET = "s" * 32


def build_app() -> Bretzel:
    """Deux routes brutes, montées sur le FastAPI sous-jacent.

    Des routes brutes et non des ``@page`` : ce qu'on mesure est le
    passage dans la pile de middlewares, pas un rendu. Elles voient
    quand même un contexte de rendu — ``RenderContextMiddleware``
    enveloppe TOUTES les requêtes — donc ``auth.login`` y pose ses
    cookies exactement comme depuis un handler.
    """
    app = Bretzel(title="cookies", secret_key=SECRET, mode="dev")

    @app.fastapi.get("/entrer")
    async def entrer() -> PlainTextResponse:
        auth.login("u-42")
        return PlainTextResponse(current_context().session_id)

    @app.fastapi.get("/sortir")
    async def sortir() -> PlainTextResponse:
        auth.logout()
        return PlainTextResponse(current_context().session_id)

    @app.fastapi.get("/rien")
    async def rien() -> PlainTextResponse:
        return PlainTextResponse(current_context().session_id)

    return app


def session_cookies(response: object) -> list[str]:
    """Les valeurs de session posées par cette réponse, dans l'ordre."""
    return [
        header.split(";", 1)[0].split("=", 1)[1]
        for header in response.headers.get_list("set-cookie")  # type: ignore[attr-defined]
        if header.startswith(f"{COOKIE_SESSION}=")
    ]


# ── le défaut fermé ────────────────────────────────────────────────────────


def test_a_login_on_a_first_hit_writes_one_cookie() -> None:
    with TestClient(build_app(), follow_redirects=False) as client:
        response = client.get("/entrer")

    posed = session_cookies(response)
    assert len(posed) == 1, (
        f"{len(posed)} Set-Cookie de session sur une même réponse — le "
        "dernier écrase le premier, donc le navigateur ne garde pas "
        f"forcément celui sous lequel l'état vient d'être écrit : {posed}"
    )
    assert posed[0] == response.text, (
        "le cookie envoyé n'est pas la session sous laquelle la requête a "
        f"travaillé ({posed[0]} vs {response.text})"
    )


def test_a_logout_on_a_first_hit_writes_one_cookie() -> None:
    with TestClient(build_app(), follow_redirects=False) as client:
        response = client.get("/sortir")

    posed = session_cookies(response)
    assert len(posed) == 1, posed
    assert posed[0] == response.text


# ── le versant licite : le middleware fait toujours son travail ────────────


def test_a_plain_first_hit_still_mints_a_session() -> None:
    with TestClient(build_app(), follow_redirects=False) as client:
        response = client.get("/rien")

    posed = session_cookies(response)
    assert len(posed) == 1, (
        "le middleware de session ne frappe plus rien — une app sans "
        f"connexion n'aurait plus de session du tout : {posed}"
    )
    assert posed[0] == response.text


def test_a_returning_visitor_gets_no_new_cookie() -> None:
    with TestClient(build_app(), follow_redirects=False) as client:
        client.get("/rien")
        response = client.get("/rien")

    assert session_cookies(response) == [], (
        "une session déjà connue est réécrite à chaque requête"
    )


def test_a_login_rotates_an_existing_session() -> None:
    """L'anti-fixation, dans le cas où elle compte vraiment.

    Ici la session existe AVANT la connexion — c'est exactement ce qu'un
    attaquant fixerait. Le cookie doit changer.
    """
    with TestClient(build_app(), follow_redirects=False) as client:
        before = client.get("/rien").text
        response = client.get("/entrer")

    posed = session_cookies(response)
    assert len(posed) == 1, posed
    assert posed[0] != before, "la session n'a pas tourné à la connexion"
    assert posed[0] == response.text
