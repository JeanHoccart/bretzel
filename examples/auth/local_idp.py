"""A real OIDC provider, locally — to try the door WITHOUT an account.

⚠️ **It is almost never launched alone**: ``py -m examples.auth.demo``
starts this one AND the app, with the variables already set. This module
stays launchable on its own (port 8954, ``BZ_IDP_PORT`` to change it) when
you want to plug something else into it.

It is the fastest way to click a real OAuth flow end to end: no signing
up at Google, no secret to set.

Not a stub: it publishes its discovery, holds a consent screen,
**verifies PKCE** (SHA-256 of the verifier against the challenge
received), signs its ``id_token`` in HS256 with the ``client_secret``, and
refuses an already-exchanged code. That is what it takes for the probe to
measure Bretzel's door and not the agreement of two fictions.

What it is not: a compliant provider. No refresh token, no JWKS (the door
does not verify the signature — the token reaches it from the token
endpoint over TLS, cf. ``oauth.py``), no session management.

Its issuer is ``http://localhost:8954`` when the app is on ``127.0.0.1``
— **two distinct sites** for the browser, and that is deliberate: the
provider's return is then a CROSS-SITE navigation, which puts the
transaction cookie's ``SameSite=lax`` under constraint. ⚠️ Two ports of
the same host would have proved nothing (cross-origin ≠ cross-site):
measured on 2026-08-24, a ``SameSite=strict`` passed there.

⚠️ **It lives in the example and not in the tests**, on purpose: the probe
``tests/probes/probe_oauth_door.py`` launches it too. A test provider in
`tests/` and a second one for the demo would have drifted apart — the one
you click must be the one you measure.
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

#: ⚠️ The port and the issuer are TIED: an OIDC provider identifies
#: itself by its issuer, and the door compares it to the one the
#: ``id_token`` carries. Keeping them apart let it announce ``:8954``
#: while listening elsewhere — the sign-in then failed on "id_token
#: issued by another issuer", a message that would have named nobody.
PORT = int(os.environ.get("BZ_IDP_PORT", "8954"))
ISSUER = f"http://localhost:{PORT}"
CLIENT_ID = "bretzel-test-client"
CLIENT_SECRET = "bretzel-test-secret"

#: The two accounts the consent screen offers. The second serves the
#: REFUSAL side: its address is outside the domain the app accepts.
ACCOUNTS = {
    "jean": {"sub": "prov-jean", "email": "jean@macorp.fr",
             "name": "Jean Insider"},
    "outsider": {"sub": "prov-outsider", "email": "someone@elsewhere.com",
                 "name": "An Outsider"},
}

#: code -> transaction in flight. A process-wide dict: this bench serves
#: one probe at a time.
CODES: dict[str, dict[str, str]] = {}


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


async def index(request: Request) -> HTMLResponse:
    """A home page, because people COME and look at it.

    An OIDC provider has no root in the protocol, so it returned "Not
    Found" — and that is exactly the URL a human opens to check the
    server is alive. A 404 there answers "dead" to the question being
    asked.
    """
    app_port = os.environ.get("BZ_APP_PORT", "8012")
    return HTMLResponse(
        f"<h1>Test OIDC provider</h1>"
        f"<p>It is alive. This is not the app — the app is on "
        f"<a href='http://127.0.0.1:{app_port}'>127.0.0.1:{app_port}</a>.</p>"
        f"<p>issuer <code>{ISSUER}</code> — "
        f"<a href='/.well-known/openid-configuration'>its discovery</a></p>"
        f"<p>Accounts: {', '.join(a['email'] for a in ACCOUNTS.values())}</p>"
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
    """The consent screen — two accounts, one link each."""
    query = request.query_params
    if query.get("client_id") != CLIENT_ID:
        return HTMLResponse("unknown client_id", status_code=400)
    if query.get("code_challenge_method") != "S256" or not query.get("code_challenge"):
        return HTMLResponse("PKCE required", status_code=400)

    carry = {
        key: query.get(key, "")
        for key in ("state", "nonce", "code_challenge", "redirect_uri")
    }
    links = "".join(
        f'<p><a id="pick-{name}" href="/pick?account={name}&'
        + "&".join(f"{k}={v}" for k, v in carry.items()).replace("&", "&amp;")
        + f'">Continue as {data["email"]}</a></p>'
        for name, data in ACCOUNTS.items()
    )
    return HTMLResponse(f"<h1>Test provider</h1>{links}")


async def pick(request: Request) -> RedirectResponse:
    """The click on an account: we mint a code and send the app back."""
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
    pending = CODES.pop(code, None)  # a code is exchanged exactly ONCE
    if pending is None:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    if form.get("client_id") != CLIENT_ID or form.get("client_secret") != CLIENT_SECRET:
        return JSONResponse({"error": "invalid_client"}, status_code=401)

    # PKCE, really verified: it is the half of the flow only a provider
    # can put under constraint.
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
    """For the ``oauth.OAuth2`` class, which has no ``id_token``."""
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
    """Start the provider, AND SAY SO.

    It ran with ``log_level="warning"``: uvicorn only announces its
    listening in ``info``, so the command did not give the hand back
    **and printed nothing**. Total silence reads as a crash — that is
    what happened to the first human who launched it, and they were right
    to believe it.
    """
    accounts = ", ".join(a["email"] for a in ACCOUNTS.values())
    # ``flush``: with no terminal (redirection, subprocess), Python
    # buffers stdout and the banner would come out AFTER uvicorn's lines,
    # which go through logging.
    print(
        f"Test OIDC provider — issuer {ISSUER}\n"
        f"  discovery : {ISSUER}/.well-known/openid-configuration\n"
        f"  client_id : {CLIENT_ID}\n"
        f"  accounts  : {accounts}\n"
        "Leave it running, and start the app in ANOTHER terminal "
        "(cf. examples/auth/README.md § 3).",
        flush=True,
    )
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")


if __name__ == "__main__":
    main()
