"""features/access — les DEUX moitiés de l'identité, dans un seul fichier.

C'est le fichier que cette démo existe pour montrer : `@auth.source` dit
d'où une identité peut venir, `@auth.door` dit comment on entre, et les
deux finissent au même endroit — ``auth.user_id()``, donc ``UserState``,
donc tout le reste de l'app sans un seul `if`.

Il n'importe PAS ``main`` : les deux décorateurs sont libres, exactement
comme ``@page`` (``app-structure.md`` § 9). C'est ``main.include(...)``
qui ramasse les marques.
"""

from __future__ import annotations

from typing import Any

from bretzel import Feature, auth, oauth, redirect
from bretzel.server import auth

from examples.auth.core.domain import (
    ALLOWED_DOMAIN,
    API_TOKENS,
    LOGIN_PATH,
    PROXY_HEADER,
    by_email,
    by_id,
    oauth2_settings,
    oidc_settings,
    trusted_proxy,
    upsert_by_email,
)

# ── Qui est cette requête ? ────────────────────────────────────────────────


@auth.source
def from_api_token(request: object) -> str | None:
    """Une identité de machine, portée par l'en-tête à chaque appel.

    Aucun cookie, aucune session : le porteur EST la preuve, et il est
    revérifié à chaque requête. C'est la deuxième des deux familles —
    l'autre (le cookie signé) est jouée avant celle-ci par le framework.

    Une app réelle vérifierait ici une signature JWT plutôt qu'un dict.
    Ce qui ne changerait pas : la fonction est **synchrone** (elle tourne
    à chaque requête), et rend un identifiant ou ``None``.
    """
    header = request.headers.get("authorization", "")  # type: ignore[attr-defined]
    if not header.lower().startswith("bearer "):
        return None
    return API_TOKENS.get(header.split(" ", 1)[1].strip())


@auth.source
def from_trusted_proxy(request: object) -> str | None:
    """L'identité posée par un proxy SSO — oauth2-proxy, IAP, Access.

    La quatrième façon d'entrer, et **la seule qui n'a pas d'écran** :
    l'authentification a eu lieu avant d'arriver ici, le reverse proxy
    l'atteste par un en-tête, et l'app n'a plus qu'à joindre sa table.

    ⚠️ **Elle est éteinte par défaut, et c'est le sujet.** Un en-tête est
    déclaratif : n'importe qui peut l'envoyer. Elle ne vaut QUE derrière
    un proxy qui l'écrase systématiquement, et une app qui l'active sans
    ça ouvre une porte à qui sait taper `curl -H`. D'où l'interrupteur
    explicite (``BZ_TRUST_PROXY_HEADER=1``) plutôt qu'un défaut : dans ce
    sens-là, l'oubli ferme au lieu d'ouvrir.
    """
    if not trusted_proxy():
        return None
    email = request.headers.get(PROXY_HEADER, "")  # type: ignore[attr-defined]
    user = by_email(email) if email else None
    return user["id"] if user else None


# ── Comment devient-on connu ? ─────────────────────────────────────────────


def on_oauth_user(profile: oauth.OAuthProfile) -> str | None:
    """La décision d'accepter, et l'endroit où la porte devient une ligne.

    ``None`` refuse. C'est le seul filtre qui existe entre « cette
    personne a un compte chez Google » et « cette personne entre chez
    moi » — sans lui, une porte est ouverte à la planète entière.
    """
    if not profile.email or not profile.email.endswith(ALLOWED_DOMAIN):
        return None
    return upsert_by_email(profile.email, profile.name)["id"]


def configured_doors() -> list[Any]:
    """Les portes que l'environnement décrit — zéro, une, ou deux.

    Construites au lieu d'être écrites en dur parce qu'une démo ne peut
    pas porter de secrets. Le code d'une vraie app écrit simplement le
    décorateur au-dessus de sa fonction.
    """
    doors: list[object] = []
    oidc = oidc_settings()
    if oidc:
        doors.append(oauth.OIDC(on_denied=LOGIN_PATH, **oidc))
    plain = oauth2_settings()
    if plain:
        doors.append(oauth.OAuth2(on_denied=LOGIN_PATH, **plain))
    return doors


#: Les noms des portes montées, pour que la page de connexion sache quels
#: boutons afficher. Une liste vide n'est pas une panne : la démo tourne
#: en mot de passe seul.
DOORS = configured_doors()

for porte in DOORS:
    # ``@auth.door(porte)`` s'empile — deux portes peuvent aboutir à la
    # même fonction, et c'est le cas ici. Le décorateur MARQUE en place
    # et rend le même objet : pas de réaffectation, elle ferait croire à
    # un enveloppement.
    auth.door(porte)(on_oauth_user)


# ── Le reste, qui ne connaît plus qu'un ``user_id`` ────────────────────────


def current_user() -> dict[str, str] | None:
    """Le profil de la personne connectée, quelle que soit la porte.

    ``auth.user_id()`` rend la même chaîne que la connexion vienne du
    formulaire, d'une porte OAuth ou d'un jeton de machine. C'est tout
    l'objet du dispositif : au-delà de cette ligne, l'app ne sait plus
    par où on est entré, et n'a pas à le savoir.
    """
    return by_id(auth.user_id())


def sign_out() -> None:
    auth.logout()
    redirect(LOGIN_PATH)


feature = Feature(
    name="access",
    kind="logic",
    provides=[from_api_token, from_trusted_proxy, on_oauth_user,
              current_user, sign_out, configured_doors],
)
