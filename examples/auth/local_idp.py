"""Un vrai fournisseur OIDC, en local — pour essayer la porte SANS compte.

⚠️ **On ne le lance presque jamais seul** : ``py -m examples.auth.demo``
démarre celui-ci ET l'app, avec les variables déjà posées. Ce module reste
lançable à part (port 8954, ``BZ_IDP_PORT`` pour en changer) quand on veut
brancher autre chose dessus.

C'est la façon la plus rapide de cliquer un vrai flux OAuth de bout en
bout : aucune inscription chez Google, aucun secret à poser.

Pas un bouchon : il publie sa découverte, tient un écran de consentement,
**vérifie PKCE** (SHA-256 du vérifieur contre le défi reçu), signe son
``id_token`` en HS256 avec le ``client_secret``, et refuse un code déjà
échangé. C'est ce qu'il faut pour que le probe mesure la porte de Bretzel
et non l'accord de deux fictions.

Ce qu'il n'est pas : un fournisseur conforme. Pas de refresh token, pas
de JWKS (la porte ne vérifie pas la signature — le jeton lui arrive du
token endpoint par TLS, cf. ``oauth.py``), pas de gestion de sessions.

Son issuer est ``http://localhost:8954`` quand l'app est sur
``127.0.0.1`` — **deux sites distincts** pour le navigateur, et c'est
délibéré : le retour du fournisseur est alors une navigation INTER-SITE,
ce qui met sous contrainte le ``SameSite=lax`` du cookie de transaction.
⚠️ Deux ports du même hôte n'auraient rien prouvé (inter-origine ≠
inter-site) : mesuré le 2026-08-24, un ``SameSite=strict`` y passait.

⚠️ **Il vit dans l'exemple et pas dans les tests**, exprès : la sonde
``tests/probes/probe_oauth_door.py`` le lance aussi. Un fournisseur de
test dans `tests/` et un second pour la démo auraient dérivé l'un de
l'autre — celui qu'on clique doit être celui qu'on mesure.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

#: ⚠️ Le port et l'issuer sont LIÉS : un fournisseur OIDC s'identifie par
#: son issuer, et la porte le compare à celui que porte l'``id_token``.
#: Les tenir séparés laissait annoncer ``:8954`` en écoutant ailleurs —
#: la connexion échouait alors sur « id_token émis par un autre issuer »,
#: un message qui n'aurait désigné personne.
PORT = int(os.environ.get("BZ_IDP_PORT", "8954"))
ISSUER = f"http://localhost:{PORT}"
CLIENT_ID = "bretzel-test-client"
CLIENT_SECRET = "bretzel-test-secret"

#: Les deux comptes que l'écran de consentement propose. Le second sert
#: au versant REFUS : son adresse est hors du domaine que l'app accepte.
ACCOUNTS = {
    "jean": {"sub": "prov-jean", "email": "jean@macorp.fr", "name": "Jean Interne"},
    "intrus": {"sub": "prov-intrus", "email": "someone@ailleurs.com", "name": "Un Intrus"},
}

#: code -> transaction en cours. Un dict de process : ce banc sert un
#: probe à la fois.
CODES: dict[str, dict[str, str]] = {}


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


async def index(request: Request) -> HTMLResponse:
    """Une page d'accueil, parce qu'on VIENT y regarder.

    Un fournisseur OIDC n'a pas de racine dans le protocole, donc elle
    rendait « Not Found » — et c'est exactement l'URL qu'un humain ouvre
    pour vérifier que le serveur est vivant. Un 404 à cet endroit répond
    « mort » à la question qu'on pose.
    """
    app_port = os.environ.get("BZ_APP_PORT", "8012")
    return HTMLResponse(
        f"<h1>Fournisseur OIDC de test</h1>"
        f"<p>Il est vivant. Ce n'est pas l'app — l'app est sur "
        f"<a href='http://127.0.0.1:{app_port}'>127.0.0.1:{app_port}</a>.</p>"
        f"<p>issuer <code>{ISSUER}</code> — "
        f"<a href='/.well-known/openid-configuration'>sa découverte</a></p>"
        f"<p>Comptes : {', '.join(a['email'] for a in ACCOUNTS.values())}</p>"
    )


async def discovery(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}/authorize",
            "token_endpoint": f"{ISSUER}/token",
            "userinfo_endpoint": f"{ISSUER}/userinfo",
            "response_types_supported": ["code"],
            "code_challenge_methods_supported": ["S256"],
        }
    )


async def authorize(request: Request) -> HTMLResponse:
    """L'écran de consentement — deux comptes, un lien chacun."""
    query = request.query_params
    if query.get("client_id") != CLIENT_ID:
        return HTMLResponse("client_id inconnu", status_code=400)
    if query.get("code_challenge_method") != "S256" or not query.get("code_challenge"):
        return HTMLResponse("PKCE exigé", status_code=400)

    carry = {
        key: query.get(key, "")
        for key in ("state", "nonce", "code_challenge", "redirect_uri")
    }
    links = "".join(
        f'<p><a id="pick-{name}" href="/pick?account={name}&'
        + "&".join(f"{k}={v}" for k, v in carry.items()).replace("&", "&amp;")
        + f'">Continuer comme {data["email"]}</a></p>'
        for name, data in ACCOUNTS.items()
    )
    return HTMLResponse(f"<h1>Fournisseur de test</h1>{links}")


async def pick(request: Request) -> RedirectResponse:
    """Le clic sur un compte : on frappe un code et on renvoie l'app."""
    query = request.query_params
    account = ACCOUNTS[query["account"]]
    code = b64url(hashlib.sha256(f"{time.time_ns()}{account['sub']}".encode()).digest())
    CODES[code] = {
        "sub": account["sub"],
        "email": account["email"],
        "name": account["name"],
        "nonce": query.get("nonce", ""),
        "code_challenge": query.get("code_challenge", ""),
    }
    return RedirectResponse(
        f"{query['redirect_uri']}?code={code}&state={query.get('state', '')}",
        status_code=302,
    )


async def token(request: Request) -> JSONResponse:
    form = await request.form()
    code = str(form.get("code", ""))
    pending = CODES.pop(code, None)  # un code ne s'échange qu'UNE fois
    if pending is None:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    if form.get("client_id") != CLIENT_ID or form.get("client_secret") != CLIENT_SECRET:
        return JSONResponse({"error": "invalid_client"}, status_code=401)

    # PKCE, vraiment vérifié : c'est la moitié du flux que seul un
    # fournisseur peut mettre sous contrainte.
    verifier = str(form.get("code_verifier", ""))
    expected = b64url(hashlib.sha256(verifier.encode()).digest())
    if not verifier or expected != pending["code_challenge"]:
        return JSONResponse({"error": "invalid_grant", "detail": "pkce"}, status_code=400)

    claims = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": pending["sub"],
        "email": pending["email"],
        "name": pending["name"],
        "nonce": pending["nonce"],
        "exp": int(time.time()) + 300,
        "iat": int(time.time()),
    }
    header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64url(json.dumps(claims).encode())
    signature = b64url(
        hmac.new(
            CLIENT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256
        ).digest()
    )
    return JSONResponse(
        {
            "access_token": f"at-{pending['sub']}",
            "token_type": "Bearer",
            "expires_in": 3600,
            "id_token": f"{header}.{payload}.{signature}",
        }
    )


async def userinfo(request: Request) -> JSONResponse:
    """Pour la classe ``oauth.OAuth2``, qui n'a pas d'``id_token``."""
    bearer = request.headers.get("authorization", "").removeprefix("Bearer ")
    for account in ACCOUNTS.values():
        if bearer == f"at-{account['sub']}":
            return JSONResponse({"id": account["sub"], **account})
    return JSONResponse({"error": "invalid_token"}, status_code=401)


app = Starlette(
    routes=[
        Route("/", index),
        Route("/.well-known/openid-configuration", discovery),
        Route("/authorize", authorize),
        Route("/pick", pick),
        Route("/token", token, methods=["POST"]),
        Route("/userinfo", userinfo),
    ]
)

def main() -> None:
    """Démarre le fournisseur, EN LE DISANT.

    Il tournait en ``log_level="warning"`` : uvicorn n'annonce son écoute
    qu'en ``info``, donc la commande ne rendait pas la main **et
    n'affichait rien**. Un silence total se lit comme un plantage — c'est
    ce qui est arrivé au premier humain qui l'a lancé, et il avait raison
    de le croire.
    """
    comptes = ", ".join(account["email"] for account in ACCOUNTS.values())
    # ``flush`` : sans terminal (redirection, sous-process), Python
    # bufferise stdout et la bannière sortirait APRÈS les lignes
    # d'uvicorn, qui passent par le logging.
    print(
        f"Fournisseur OIDC de test — issuer {ISSUER}\n"
        f"  découverte : {ISSUER}/.well-known/openid-configuration\n"
        f"  client_id  : {CLIENT_ID}\n"
        f"  comptes    : {comptes}\n"
        "Laisse-le tourner, et lance l'app dans un AUTRE terminal "
        "(cf. examples/auth/README.md § 3).",
        flush=True,
    )
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")


if __name__ == "__main__":
    main()
