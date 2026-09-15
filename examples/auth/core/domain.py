"""Le peu que cette démo possède : une table d'utilisateurs et la
configuration des portes, lue dans l'environnement.

**Rien ici n'est du framework.** C'est le partage qu'on veut montrer :
Bretzel possède l'identité et son transport (le cookie signé, la chaîne
de lecture) ; l'app possède la preuve — le mot de passe, la table, les
rôles, et la décision d'accepter ou non une adresse.
"""

from __future__ import annotations

import os

#: La « base ». Un dict plutôt qu'un SQLite : cette démo mesure l'auth,
#: pas la persistance, et le CRM couvre déjà le cas réaliste.
USERS: dict[str, dict[str, str]] = {
    "u-1": {"id": "u-1", "email": "jean@macorp.fr", "name": "Jean", "password": "demo"},
    "u-2": {"id": "u-2", "email": "ada@macorp.fr", "name": "Ada", "password": "demo"},
}

#: Le domaine que les portes acceptent. Une porte OAuth sans ce filtre
#: laisse entrer **toute personne ayant un compte chez le fournisseur** —
#: c'est le défaut-ouvert que ``on_user`` existe pour refuser.
ALLOWED_DOMAIN = "@macorp.fr"

#: Les jetons de machine, en clair — une app réelle vérifierait une
#: signature (cf. ``features/access.py``). Ils servent à montrer qu'une
#: identité peut arriver SANS cookie et faire marcher ``UserState``
#: exactement pareil.
API_TOKENS: dict[str, str] = {"jeton-demo": "u-2"}

LOGIN_PATH = "/login"

#: Le port servi — lu pour que l'écran puisse écrire une commande ``curl``
#: qui marche vraiment, y compris quand ``BZ_APP_PORT`` a bougé.
APP_PORT = os.environ.get("BZ_APP_PORT", "8012")

#: L'en-tête qu'un proxy SSO pose une fois la personne authentifiée —
#: ``X-Forwarded-Email`` chez oauth2-proxy, ``X-Goog-Authenticated-User-Email``
#: chez IAP, ``Cf-Access-Authenticated-User-Email`` chez Cloudflare Access.
PROXY_HEADER = "X-Remote-User"


def trusted_proxy() -> bool:
    """La lecture de l'en-tête est-elle activée ?

    Éteinte par défaut : un en-tête se falsifie en une ligne de ``curl``.
    Elle ne vaut que derrière un proxy qui l'écrase à chaque requête, et
    ça, seule l'exploitation le sait — donc c'est elle qui l'allume.
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
    """Vrai/faux d'un seul tenant — on ne dit pas laquelle des deux
    causes a échoué, sinon on offre la liste des comptes qui existent."""
    user = by_email(email)
    return user if user and user["password"] == password else None


def upsert_by_email(email: str, name: str) -> dict[str, str]:
    """Le compte qu'une porte vient de faire connaître.

    Une porte ne crée pas d'utilisateur : elle prouve une adresse. C'est
    l'app qui décide que cette adresse mérite une ligne.
    """
    existing = by_email(email)
    if existing:
        return existing
    user_id = f"u-{len(USERS) + 1}"
    USERS[user_id] = {"id": user_id, "email": email, "name": name or email, "password": ""}
    return USERS[user_id]


# ── Les portes, décrites par l'environnement ───────────────────────────────
#
# Aucun nom de service dans le code du framework — et ici, aucun nom de
# service en dur non plus : trois variables suffisent à décrire n'importe
# quel fournisseur OIDC.
#
#   BZ_OIDC_NAME=google
#   BZ_OIDC_ISSUER=https://accounts.google.com
#   BZ_OIDC_CLIENT_ID=…
#   BZ_OIDC_CLIENT_SECRET=…
#
# Microsoft Entra : ISSUER=https://login.microsoftonline.com/<tenant>/v2.0
# Auth0 : https://<domaine>.eu.auth0.com — Keycloak :
# https://<hôte>/realms/<realm>. Aucun n'a besoin d'une ligne de code.


def oidc_settings() -> dict[str, str] | None:
    """La configuration OIDC, ou ``None`` si l'environnement est muet."""
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
    """Idem pour un fournisseur sans OIDC (GitHub, Discord, Slack…).

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
