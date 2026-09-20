"""The little this demo owns: a user table and the doors' configuration,
read from the environment.

**Nothing here belongs to the framework.** That split is what we want to
show: Bretzel owns the identity and its transport (the signed cookie, the
read chain); the app owns the proof — the password, the table, the roles,
and the decision to accept an address or not.
"""

from __future__ import annotations

import os

#: The "database". A dict rather than a SQLite: this demo measures auth,
#: not persistence, and the CRM already covers the realistic case.
USERS: dict[str, dict[str, str]] = {
    "u-1": {"id": "u-1", "email": "jean@macorp.fr", "name": "Jean", "password": "demo"},
    "u-2": {"id": "u-2", "email": "ada@macorp.fr", "name": "Ada", "password": "demo"},
}

#: The domain the doors accept. An OAuth door without this filter lets in
#: **anyone holding an account at the provider** — the open-by-default
#: that ``on_user`` exists to refuse.
ALLOWED_DOMAIN = "@macorp.fr"

#: Machine tokens, in clear — a real app would verify a signature (cf.
#: ``features/access.py``). They are here to show that an identity can
#: arrive WITHOUT a cookie and make ``UserState`` work exactly the same.
API_TOKENS: dict[str, str] = {"demo-token": "u-2"}

LOGIN_PATH = "/login"

#: The port being served — read so the screen can write a ``curl`` command
#: that really works, including when ``BZ_APP_PORT`` has moved.
APP_PORT = os.environ.get("BZ_APP_PORT", "8012")

#: The header an SSO proxy sets once the person is authenticated —
#: ``X-Forwarded-Email`` at oauth2-proxy, ``X-Goog-Authenticated-User-Email``
#: at IAP, ``Cf-Access-Authenticated-User-Email`` at Cloudflare Access.
PROXY_HEADER = "X-Remote-User"


def trusted_proxy() -> bool:
    """Is reading the header switched on?

    Off by default: a header is forged in one line of ``curl``. It is only
    worth anything behind a proxy that overwrites it on every request, and
    only operations knows that — so operations is what turns it on.
    """
    return os.environ.get("BZ_TRUST_PROXY_HEADER", "") == "1"


def by_email(email: str) -> dict[str, str] | None:
    for user in USERS.values():
        if user["email"].lower() == email.lower():
            return user
    return None


def by_id(user_id: str | None) -> dict[str, str] | None:
    return USERS.get(user_id or "")


def authenticate(email: str, password: str) -> dict[str, str] | None:
    """True/false as one — we do not say which of the two causes failed,
    otherwise we hand out the list of accounts that exist."""
    user = by_email(email)
    return user if user and user["password"] == password else None


def upsert_by_email(email: str, name: str) -> dict[str, str]:
    """The account a door has just made known.

    A door does not create a user: it proves an address. It is the app
    that decides that address deserves a row.
    """
    existing = by_email(email)
    if existing:
        return existing
    user_id = f"u-{len(USERS) + 1}"
    USERS[user_id] = {"id": user_id, "email": email, "name": name or email, "password": ""}
    return USERS[user_id]


# ── The doors, described by the environment ────────────────────────────────
#
# No service name in the framework's code — and here, no hard-coded
# service name either: three variables are enough to describe any OIDC
# provider.
#
#   BZ_OIDC_NAME=google
#   BZ_OIDC_ISSUER=https://accounts.google.com
#   BZ_OIDC_CLIENT_ID=…
#   BZ_OIDC_CLIENT_SECRET=…
#
# Microsoft Entra: ISSUER=https://login.microsoftonline.com/<tenant>/v2.0
# Auth0: https://<domain>.eu.auth0.com — Keycloak:
# https://<host>/realms/<realm>. None needs a line of code.


def oidc_settings() -> dict[str, str] | None:
    """The OIDC configuration, or ``None`` if the environment is silent."""
    issuer = os.environ.get("BZ_OIDC_ISSUER", "")
    client_id = os.environ.get("BZ_OIDC_CLIENT_ID", "")
    client_secret = os.environ.get("BZ_OIDC_CLIENT_SECRET", "")
    if not (issuer and client_id and client_secret):
        return None
    return {
        "name": os.environ.get("BZ_OIDC_NAME", "sso"),
        "issuer": issuer,
        "client_id": client_id,
        "client_secret": client_secret,
    }


def oauth2_settings() -> dict[str, str] | None:
    """Same for a provider without OIDC (GitHub, Discord, Slack…).

        BZ_OAUTH2_NAME=github
        BZ_OAUTH2_AUTHORIZE=https://github.com/login/oauth/authorize
        BZ_OAUTH2_TOKEN=https://github.com/login/oauth/access_token
        BZ_OAUTH2_USERINFO=https://api.github.com/user
        BZ_OAUTH2_SUBJECT=id
        BZ_OAUTH2_SCOPE=read:user user:email
    """
    required = ("AUTHORIZE", "TOKEN", "USERINFO", "CLIENT_ID", "CLIENT_SECRET")
    values = {key: os.environ.get(f"BZ_OAUTH2_{key}", "") for key in required}
    if not all(values.values()):
        return None
    return {
        "name": os.environ.get("BZ_OAUTH2_NAME", "oauth2"),
        "authorize": values["AUTHORIZE"],
        "token": values["TOKEN"],
        "userinfo": values["USERINFO"],
        "client_id": values["CLIENT_ID"],
        "client_secret": values["CLIENT_SECRET"],
        "subject": os.environ.get("BZ_OAUTH2_SUBJECT", "id"),
        "scope": os.environ.get("BZ_OAUTH2_SCOPE", ""),
    }
