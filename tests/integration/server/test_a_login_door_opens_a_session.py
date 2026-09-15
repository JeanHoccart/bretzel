"""Une porte OAuth ouvre une session Bretzel — le flux entier, sans réseau.

Ce qui est vérifié ici est le **déroulement**, pas la conformité au RFC :
que la porte pose sa transaction signée, que le retour du fournisseur
soit refusé s'il ne correspond pas, que ``on_user`` décide, et surtout
qu'un aboutissement pose le cookie ``Bretzel_auth`` — c'est-à-dire que la
porte se termine dans le mécanisme d'identité existant plutôt qu'à côté
de lui.

Le fournisseur est simulé en remplaçant :func:`oauth._fetch` — le seul
point où ce module touche le réseau. Ce qui reste réel : les deux routes,
le cookie de transaction et sa signature, la comparaison du ``state``, la
lecture de l'``id_token``, ``auth.login`` et le contexte de rendu qui
applique ses cookies.

⚠️ Sans ce test, la panne à craindre n'est pas visible : une callback qui
« marche » en renvoyant une 302 vers ``/`` **sans avoir posé de cookie**
laisse l'app tourner en anonyme, et le symptôme (on retombe sur /login)
accuse la garde, pas la porte.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.parse

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, auth, oauth
from bretzel.server.auth import COOKIE_AUTH

ISSUER = "https://provider.test"
CLIENT_ID = "client-abc"

def make_door(**kwargs: object) -> oauth.OIDC:
    return oauth.OIDC(
        name="prov",
        issuer=ISSUER,
        client_id=CLIENT_ID,
        client_secret="s3cret",
        **kwargs,  # type: ignore[arg-type]
    )


def id_token(nonce: str, *, sub: str = "prov-42", aud: str = CLIENT_ID,
             iss: str = ISSUER, ttl: int = 300,
             email: str = "jean@macorp.fr") -> str:
    """Un ``id_token`` non signé — la porte ne vérifie pas la signature.

    C'est le contrat, pas un raccourci de test : le jeton arrive du token
    endpoint par TLS en réponse à un POST authentifié (OIDC Core
    § 3.1.3.7). Ce que la porte contrôle — ``iss``, ``aud``, ``exp``,
    ``nonce`` — est justement ce que chaque paramètre d'ici permet de
    fausser.
    """
    claims = {
        "iss": iss,
        "aud": aud,
        "sub": sub,
        "exp": int(time.time()) + ttl,
        "nonce": nonce,
        "email": email,
        "name": "Jean",
    }
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{body}.signature"


@pytest.fixture
def door_app(monkeypatch: pytest.MonkeyPatch):
    """Une app d'une porte, dont le fournisseur est un dictionnaire.

    ``token_response`` est une boîte mutable : chaque test y écrit ce que
    le fournisseur est censé rendre, une fois qu'il connaît le ``nonce``
    tiré par la porte.
    """
    token_response: dict[str, object] = {}
    #: Ce que ``on_user`` a vu. La fixture le POSSÈDE — une liste au
    #: niveau du module aurait été l'état global que l'anti-règle 2 vise,
    #: et il aurait fallu la vider à chaque test pour compenser.
    seen: list[oauth.OAuthProfile] = []

    async def fake_fetch(url: str, *, data=None, headers=None):
        if url.endswith("/.well-known/openid-configuration"):
            return {
                "authorization_endpoint": f"{ISSUER}/authorize",
                "token_endpoint": f"{ISSUER}/token",
                "userinfo_endpoint": f"{ISSUER}/userinfo",
            }
        if url == f"{ISSUER}/token":
            return dict(token_response)
        raise AssertionError(f"appel réseau inattendu : {url}")

    monkeypatch.setattr(oauth, "_fetch", fake_fetch)

    door = make_door()

    @auth.door(door)
    def on_user(profile: oauth.OAuthProfile) -> str | None:
        seen.append(profile)
        return "u-7" if profile.email.endswith("@macorp.fr") else None

    app = Bretzel(title="portes", secret_key="k" * 32, mode="dev")
    app.include(on_user)
    return app, token_response, seen


def start(client: TestClient) -> tuple[str, str]:
    """Joue ``/auth/prov`` et rend le ``state`` et le ``nonce`` émis."""
    response = client.get("/auth/prov")
    assert response.status_code == 302, response.status_code
    query = urllib.parse.parse_qs(urllib.parse.urlparse(response.headers["location"]).query)
    return query["state"][0], query["nonce"][0]


# ── le chemin nominal ──────────────────────────────────────────────────────


def test_a_completed_flow_sets_the_bretzel_cookie(door_app) -> None:
    app, token_response, seen = door_app
    with TestClient(app, follow_redirects=False) as client:
        state, nonce = start(client)
        token_response["id_token"] = id_token(nonce)

        response = client.get("/auth/prov/callback", params={"code": "c", "state": state})

        assert response.status_code == 302
        assert response.headers["location"] == "/"
        cookies = "; ".join(response.headers.get_list("set-cookie"))
        assert COOKIE_AUTH in cookies, (
            "la porte a redirigé sans ouvrir de session — c'est la panne "
            "qui se lit comme un bug de garde"
        )
        assert "u-7:" in cookies, "le cookie porte l'id du fournisseur, pas le nôtre"


def test_the_profile_reaches_on_user(door_app) -> None:
    app, token_response, seen = door_app
    with TestClient(app, follow_redirects=False) as client:
        state, nonce = start(client)
        token_response["id_token"] = id_token(nonce)
        client.get("/auth/prov/callback", params={"code": "c", "state": state})

    assert len(seen) == 1
    assert seen[0].subject == "prov-42"
    assert seen[0].email == "jean@macorp.fr"
    assert seen[0].raw["iss"] == ISSUER


def test_the_start_route_carries_pkce_and_state(door_app) -> None:
    app, _, seen = door_app
    with TestClient(app, follow_redirects=False) as client:
        response = client.get("/auth/prov")
        query = urllib.parse.parse_qs(
            urllib.parse.urlparse(response.headers["location"]).query
        )
        assert query["code_challenge_method"] == ["S256"]
        assert query["code_challenge"][0]
        assert query["client_id"] == [CLIENT_ID]
        assert query["redirect_uri"][0].endswith("/auth/prov/callback")
        assert "Bretzel_oauth_prov" in "; ".join(response.headers.get_list("set-cookie"))


# ── les refus ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("state qui ne correspond pas", lambda s, n: {"code": "c", "state": "autre"}),
        ("pas de code", lambda s, n: {"state": s}),
    ],
)
def test_a_broken_return_refuses_without_a_session(door_app, label, mutate) -> None:
    app, token_response, seen = door_app
    with TestClient(app, follow_redirects=False) as client:
        state, nonce = start(client)
        token_response["id_token"] = id_token(nonce)

        response = client.get("/auth/prov/callback", params=mutate(state, nonce))

        assert response.status_code == 302, label
        assert response.headers["location"] == "/login", label
        assert COOKIE_AUTH not in "; ".join(response.headers.get_list("set-cookie")), label


@pytest.mark.parametrize(
    ("label", "kwargs"),
    [
        ("émis par un autre issuer", {"iss": "https://ailleurs.test"}),
        ("destiné à un autre client", {"aud": "un-autre-client"}),
        ("expiré", {"ttl": -10}),
        ("nonce d'une autre transaction", {"nonce_override": "rejeu"}),
        # ⚠️ Celui-là passait jusqu'au 2026-08-24 : le contrôle était
        # écrit ``if nonce and claims.get("nonce") and …``, donc un jeton
        # SANS nonce sautait la vérification qu'on venait d'exiger. C'est
        # la porte au rejeu que le nonce existe pour fermer.
        ("sans nonce du tout", {"nonce_override": ""}),
    ],
)
def test_a_forged_id_token_refuses(door_app, label, kwargs) -> None:
    app, token_response, seen = door_app
    with TestClient(app, follow_redirects=False) as client:
        state, nonce = start(client)
        forged_nonce = kwargs.pop("nonce_override", nonce)
        token_response["id_token"] = id_token(forged_nonce, **kwargs)

        response = client.get("/auth/prov/callback", params={"code": "c", "state": state})

        assert response.headers["location"] == "/login", label
        assert COOKIE_AUTH not in "; ".join(response.headers.get_list("set-cookie")), label
        assert not seen, f"on_user a été appelé malgré un id_token {label}"


def test_a_refused_user_never_opens_a_session(door_app) -> None:
    """``on_user`` qui rend ``None`` est un refus — le défaut-fermé."""
    app, token_response, seen = door_app
    with TestClient(app, follow_redirects=False) as client:
        state, nonce = start(client)
        # L'adresse ne finit pas par @macorp.fr : ``on_user`` refuse.
        token_response["id_token"] = id_token(nonce, email="quelquun@ailleurs.com")

        response = client.get("/auth/prov/callback", params={"code": "c", "state": state})

        assert response.headers["location"] == "/login"
        assert COOKIE_AUTH not in "; ".join(response.headers.get_list("set-cookie"))
        assert seen, "on_user devait être consulté — c'est lui qui refuse"


def test_a_callback_without_a_transaction_refuses(door_app) -> None:
    """Une callback jouée seule — lien direct, ou cookie expiré."""
    app, _, seen = door_app
    with TestClient(app, follow_redirects=False) as client:
        response = client.get("/auth/prov/callback", params={"code": "c", "state": "x"})
        assert response.headers["location"] == "/login"
        assert COOKIE_AUTH not in "; ".join(response.headers.get_list("set-cookie"))


# ── la nature de la requête ────────────────────────────────────────────────


def test_a_boosted_link_gets_an_hx_redirect(door_app) -> None:
    """Le lien « Continuer avec X » est un ``<a>`` — donc BOOSTÉ.

    ``render/shell.py`` pose ``hx-boost="true"`` au niveau du document dès
    qu'une page porte un ``outlet``, ce qui est le cas de toute page de
    connexion vivant dans une coque. htmx suivrait alors une 302 en
    ``fetch``, vers une AUTRE origine : échec CORS en silence, ou HTML
    du fournisseur swappé dans l'outlet. Il faut un ``HX-Redirect``, que
    le navigateur exécute en vraie navigation.

    ⚠️ Ce cas ne se voit pas dans ``examples/auth`` : sa page de
    connexion n'a pas d'outlet, donc rien n'y est boosté et la sonde
    navigateur reste verte quoi qu'il arrive. C'est exactement pour ça
    qu'il est épinglé ici.
    """
    app, _, seen = door_app
    with TestClient(app, follow_redirects=False) as client:
        response = client.get("/auth/prov", headers={"HX-Request": "true"})

    assert response.status_code == 200, (
        "une 302 sur une requête htmx est suivie en transparence par fetch "
        "— le fournisseur est cross-origin, ça échoue sans rien dire"
    )
    assert response.headers.get("HX-Redirect", "").startswith(f"{ISSUER}/authorize")
    assert "Bretzel_oauth_prov" in "; ".join(response.headers.get_list("set-cookie")), (
        "la transaction doit être scellée même sur la branche htmx"
    )


def test_a_plain_navigation_still_gets_a_302(door_app) -> None:
    """Le versant licite : sans htmx, une vraie redirection."""
    app, _, seen = door_app
    with TestClient(app, follow_redirects=False) as client:
        response = client.get("/auth/prov")

    assert response.status_code == 302
    assert response.headers["location"].startswith(f"{ISSUER}/authorize")


# ── ce que la porte déclare à la garde ─────────────────────────────────────


def test_the_two_paths_are_public_by_construction(door_app) -> None:
    """Les deux chemins remontent dans ``app.public_paths``.

    Sans la callback, une garde produit une boucle de redirection dont le
    symptôme ne désigne rien : le fournisseur renvoie, la garde refuse,
    on repart chez le fournisseur.
    """
    app, _, seen = door_app
    assert {"/auth/prov", "/auth/prov/callback"} <= app.public_paths
