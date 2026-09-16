"""Authentication helpers for Bretzel applications."""

from __future__ import annotations

import contextlib
import secrets
import time
from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import TYPE_CHECKING, Any

from bretzel.render.context import current_context
from bretzel.server.crypto import sign as _crypto_sign
from bretzel.server.crypto import verify as _crypto_verify

# Les deux DÉCLARATIONS d'identité, ré-exportées ici pour que le sujet
# entier tienne dans un seul import (``from bretzel import auth``). Elles
# vivent dans ``decorators/identity.py`` parce qu'elles ne partagent
# aucune plomberie avec le cookie — seulement le domaine.
from bretzel.server.decorators.identity import door, source

if TYPE_CHECKING:
    from starlette.types import Scope

#: **Ce que l'utilisateur écrit** — ce que ce docstring annonce.
#:
#: Les quatre VERBES agissent tout de suite ; les deux NOMS déclarent, et
#: rien ne se produit avant ``app.include(...)``. La forme du mot dit
#: laquelle des deux on lit — cf. le docstring de
#: :mod:`bretzel.server.decorators.identity`.
__all__ = [
    "login",
    "logout",
    "user_id",
    "is_authenticated",
    "source",
    "door",
]

#: **Ré-exporté pour les autres couches, pas pour l'auteur d'une app.**
#: ``middleware/auth.py`` vérifie le cookie, ``middleware/session.py`` le
#: parse, ``config`` décide de son attribut ``Secure``.
_INTERNAL = [
    "COOKIE_AUTH",
    "COOKIE_SESSION",
    "verify_auth_cookie",
    # La chaîne d'identité, jouée sur une requête brute. ``AuthMiddleware``
    # l'appelle à chaque requête et ``user_id(request)`` est sa porte
    # publique — une app n'a donc jamais à la nommer.
    "resolve_identity",
    # La remontée requête → instance, partagée avec ``oauth.py``.
    "app_of",
    "parse_cookies_from_scope",
    "resolve_cookie_secure",
    "request_scheme",
    # ``AuthUser`` est ce que ``middleware/auth.py`` pose sur
    # ``request.state.user``. Une app ne le construit ni ne le lit :
    # elle lit ``auth.user_id()`` et joint sur SA table utilisateur.
    "AuthUser",
    # Importé de ``render``, utilisé par les quatre fonctions publiques.
    # Il apparaît ici par simple visibilité de module — pas un ré-export.
    "current_context",
]

# ── Cookie names ───────────────────────────────────────────────────────────

COOKIE_AUTH = "Bretzel_auth"
COOKIE_SESSION = "Bretzel_session"


def resolve_cookie_secure(scheme: str | None, override: bool | None) -> bool:
    """Faut-il poser l'attribut ``Secure`` sur les cookies ?

    C'est une question de **transport**, pas d'environnement : un cookie
    ``Secure`` n'est tout simplement pas renvoyé par le navigateur sur une
    origine ``http://``. On la déduit donc du scheme de la requête.

    Ça remplace un ``secure=not debug`` qui liait la sécurité des cookies
    au mode de l'application. Conséquence vécue, reproduite : un outil
    interne en ``mode="prod"`` derrière un LAN sans TLS posait des cookies
    ``Secure`` que le navigateur ne renvoyait jamais — session et auth
    mortes, sans erreur ni log, le seul contournement étant de repasser en
    ``mode="dev"``, ce qui exposait au passage les stack traces. Le piège
    était invisible en local : les navigateurs traitent ``localhost`` et
    ``127.0.0.1`` comme des origines de confiance et y acceptent les
    cookies ``Secure``.

    ``override`` (``config.secure_cookies``) court-circuite la déduction.
    Il est nécessaire derrière un proxy qui termine le TLS : uvicorn ne
    réécrit ``scope["scheme"]`` depuis ``X-Forwarded-Proto`` que s'il a été
    lancé avec ``proxy_headers=True``. Sans ça l'application voit ``http``
    et sous-estimerait.

    Scheme inconnu (contexte de rendu synthétique, tests) → ``False`` :
    seul un ``https`` positif justifie de durcir, et se tromper dans
    l'autre sens casserait la session au lieu de la protéger.
    """
    if override is not None:
        return override
    return (scheme or "").lower() == "https"


def request_scheme(request: Any) -> str:
    """Le scheme d'une requête, en tolérant les objets duck-typés.

    ``RenderContext.request`` est typée ``Any`` — le socle de rendu ne
    connaît pas Starlette — et vaut un simple sentinelle dans les
    contextes de test.
    """
    url = getattr(request, "url", None)
    scheme = getattr(url, "scheme", None) if url is not None else None
    if scheme is None:
        scheme = getattr(request, "scheme", None)
    return str(scheme or "")


def _ctx_cookie_secure(ctx: Any) -> bool:
    """``Secure`` pour les cookies posés depuis un contexte de rendu."""
    config = getattr(ctx.app, "config", None)
    override = getattr(config, "secure_cookies", None) if config else None
    return resolve_cookie_secure(request_scheme(ctx.request), override)


def parse_cookies_from_scope(scope: Scope) -> dict[str, str]:
    """Parse the ``Cookie`` header on an ASGI scope into a name→value dict.

    Called once per request by the session middleware, which stashes
    the result on ``request.state.cookies`` so downstream middlewares
    (auth) read by lookup instead of re-parsing.
    """
    for k, v in scope.get("headers", ()):
        if k == b"cookie":
            jar: SimpleCookie = SimpleCookie()
            try:
                jar.load(v.decode("latin-1"))
            except Exception:
                return {}
            return {name: morsel.value for name, morsel in jar.items()}
    return {}


@dataclass(frozen=True, slots=True)
class AuthUser:
    """Minimal auth identity — the framework only knows the id.

    Apps that need profile / role / email join from their own user
    table using ``auth.user_id()`` as the join key.
    """

    id: str
    is_authenticated: bool = True


# ───────────────────────────────────────────────────────────────────────────
# Login / logout
# ───────────────────────────────────────────────────────────────────────────


def login(user_id: str) -> None:
    """Open a session for ``user_id`` — the proof already happened.

    Cette fonction ne vérifie **rien** : le mot de passe, le code OAuth
    ou l'assertion SSO ont été jugés avant, par l'app ou par une porte.
    Ce qu'elle fait est du transport — poser de quoi reconnaître cette
    identité à la requête suivante.

    Side-effects :

    1. Rotate ``Bretzel_session`` (anti-fixation — a fresh session id
       prevents pre-login session-fixation attacks).
    2. Set ``Bretzel_auth`` cookie (HMAC-signed) carrying ``user_id``
       + expiry timestamp.
    3. Update ``request.state.user`` so the rest of the request
       already sees the authenticated identity.

    The string requirement on ``user_id`` is intentional : whatever
    primary key the app uses (UUID, integer, email…) gets stringified
    upstream so we have one shape to sign and ship around.
    """
    if not isinstance(user_id, str) or not user_id:
        raise TypeError("user_id must be a non-empty string.")

    ctx = current_context()
    auth_key = _auth_key(ctx)
    max_age_days = _session_max_age_days(ctx)
    expires_at = int(time.time()) + max_age_days * 86400

    payload = f"{user_id}:{expires_at}"
    signature = _crypto_sign(auth_key, payload)
    cookie_value = f"{payload}.{signature}"

    secure = _ctx_cookie_secure(ctx)
    ctx.set_cookie(
        COOKIE_AUTH,
        cookie_value,
        max_age=expires_at - int(time.time()),
        httponly=True,
        samesite="lax",
        secure=secure,
    )

    # Anti-fixation : rotate session id at every privilege change.
    ctx.session_id = secrets.token_hex(16)
    ctx.set_cookie(
        COOKIE_SESSION,
        ctx.session_id,
        max_age=max_age_days * 86400,
        httponly=True,
        samesite="lax",
        secure=secure,
    )

    # Make the new identity available immediately for the remainder
    # of this request.
    ctx.user_id = user_id
    _forget_identity(ctx)
    _attach_user(ctx, AuthUser(id=user_id))


def logout() -> None:
    """Clear the auth cookie + rotate the session id.

    Idempotent — safe to call when the session is already anonymous.
    """
    ctx = current_context()
    ctx.delete_cookie(COOKIE_AUTH)
    # Rotate session so anything tied to the previous one (e.g.,
    # cart contents, in-flight forms) starts fresh on the next page.
    ctx.session_id = secrets.token_hex(16)
    secure = _ctx_cookie_secure(ctx)
    ctx.set_cookie(
        COOKIE_SESSION,
        ctx.session_id,
        max_age=_session_max_age_days(ctx) * 86400,
        httponly=True,
        samesite="lax",
        secure=secure,
    )
    ctx.user_id = None
    _forget_identity(ctx)
    _attach_user(ctx, None)


# ───────────────────────────────────────────────────────────────────────────
# Read API
# ───────────────────────────────────────────────────────────────────────────


def user_id(request: Any = None) -> str | None:
    """Return the authenticated user id, or ``None`` for an anonymous request."""
    if request is not None:
        return resolve_identity(request)
    return current_context().user_id


def is_authenticated() -> bool:
    """Convenience boolean wrapper around :func:`user_id`."""
    return user_id() is not None


# ───────────────────────────────────────────────────────────────────────────
# Cookie verification (used by ``server/middleware/auth.py``)
# ───────────────────────────────────────────────────────────────────────────


def verify_auth_cookie(cookie_value: str, auth_key: bytes) -> str | None:
    """Validate a ``Bretzel_auth`` cookie and return the user id.

    Returns ``None`` for : missing cookie, malformed payload, expired
    timestamp, or signature mismatch. Constant-time signature compare
    via :func:`hmac.compare_digest`.

    ``auth_key`` is the **derived** key (``config._auth_key``), not the
    raw ``secret_key``.
    """
    if not cookie_value or "." not in cookie_value:
        return None
    try:
        payload, supplied_sig = cookie_value.rsplit(".", 1)
        user_id, expires_at_str = payload.split(":", 1)
        expires_at = int(expires_at_str)
    except (ValueError, IndexError):
        return None

    if not _crypto_verify(auth_key, payload, supplied_sig):
        return None

    if int(time.time()) >= expires_at:
        return None

    return user_id


def resolve_identity(request: Any, bretzel: Any = None) -> str | None:
    """La chaîne d'identité, jouée sur une requête brute.

    Les quatre autres lectures d'identité ne répondent pas à cet
    endroit, et c'est structurel : un middleware utilisateur est le plus
    EXTERNE (``lifecycle.py`` : « user middlewares last so they wrap
    everything above »), donc à l'inbound il tourne AVANT ceux du
    framework. :func:`user_id` sans argument lit le contexte de rendu,
    qui n'est posé que pendant le rendu ; ``request.state.user`` est
    écrit par ``AuthMiddleware``, plus interne que toi. Il ne reste que
    la requête elle-même.

    Le vérifier demande la clé **dérivée** — pas le ``secret_key`` brut.
    Cette fonction récupère elle-même la clé dérivée sur l'application afin
    que le middleware utilisateur n'accède pas à un attribut privé sensible.

    Rend ``None`` pour : pas de cookie, cookie malformé, expiré,
    signature fausse, aucune source déclarée qui reconnaisse la requête,
    ou app introuvable. **Un seul retour pour tous les refus**, parce
    qu'un middleware de garde n'a qu'une décision à prendre — laisser
    passer ou rediriger — et que distinguer les causes ici inviterait à
    en dire trop à un anonyme ::

        from bretzel import auth
        from bretzel.server import action_path, redirect_response

        # ``action_path`` n'est pas décoratif : le formulaire de connexion
        # POSTe une action, qu'une garde en défaut-fermé bloque comme le
        # reste. Le symptôme ne ressemble à rien — htmx suit la
        # redirection en transparence et le bouton paraît mort.
        PUBLIC = {"/login", action_path(sign_in), *app.public_paths}

        @app.middleware
        async def require_login(request, call_next):
            if request.url.path in PUBLIC or auth.user_id(request):
                return await call_next(request)
            return redirect_response(request, "/login")

    Elle rend l'**identifiant**, pas un booléen : une garde qui veut
    juste savoir « connecté ? » teste la vérité de la valeur, tandis
    qu'une garde qui journalise ou qui autorise par rôle a besoin du
    nom. Un booléen aurait forcé la seconde à refaire la lecture.

    **Une fois par requête.** Le résultat est gardé sur le ``scope``,
    parce que la chaîne est jouée DEUX fois sur toute requête protégée :
    la garde de l'app (le middleware le plus externe) demande
    ``auth.user_id(request)``, puis ``AuthMiddleware``, plus interne,
    redemande la même chose sans pouvoir voir la première réponse. C'est
    la recette que la doc prescrit, donc ce n'est pas un mésusage — mais
    sans mémo, **la fonction ``@auth.source`` de l'app tourne deux fois**,
    alors qu'elle peut vérifier un JWT ou interroger une source distante.

    ``auth.login`` et ``auth.logout`` effacent le mémo — ils changent
    l'identité au milieu de la requête.

    **L'ordre est le cookie d'abord, les sources ``@auth.source`` ensuite,
    dans l'ordre d'écriture.** Le cookie en tête parce que c'est lui qui
    porte les sessions de navigateur — la population de loin la plus
    nombreuse — et parce qu'il est le seul que le framework ait signé
    lui-même. Une exception levée par une source **remonte** : une
    lecture d'identité qui casse est un incident, pas un anonyme, et
    l'avaler ferait exactement ce que ce dépôt a passé un audit à
    retirer (onze sites qui rattrapaient une construction en silence).
    """
    scope = getattr(request, "scope", None)
    if isinstance(scope, dict) and _MEMO in scope:
        return scope[_MEMO]

    if bretzel is None:
        # Les appelants internes la passent en clair — ils l'ont déjà, et
        # dépendre de la façon dont on est monté serait fragile sur ce
        # chemin-là.
        bretzel = app_of(request)
    found = _from_signed_cookie(request, bretzel)
    if not found:
        for source in getattr(bretzel, "identity_sources", ()):
            found = source(request)
            if found:
                break
        else:
            found = None

    if isinstance(scope, dict):
        scope[_MEMO] = found
    return found


#: La clé sous laquelle une requête garde l'identité déjà résolue. Dans
#: le ``scope`` ASGI et pas sur ``request.state`` : les deux couches qui
#: la lisent construisent chacune leur ``Request``, mais partagent le
#: scope — c'est le seul endroit qui les relie.
_MEMO = "_bz_identity"


def app_of(request: Any) -> Any:
    """L'instance :class:`Bretzel` atteignable depuis une requête brute.

    ``request.app`` rend le FastAPI ; l'instance est posée sur son
    ``state`` par le constructeur. Trois sites écrivaient cette même
    remontée en ``getattr`` chaînés — ici, et deux fois dans ``oauth.py``
    — donc trois endroits à trouver le jour où elle se pose ailleurs.

    Tolérante par ``getattr`` : les stubs bas niveau des tests unitaires
    n'ont ni ``app`` ni ``state``, et c'est la convention du module (cf.
    :func:`request_scheme`).
    """
    return getattr(getattr(getattr(request, "app", None), "state", None), "bretzel", None)


def _from_signed_cookie(request: Any, bretzel: Any) -> str | None:
    """La source par défaut : le cookie ``Bretzel_auth`` que ``login`` pose.

    Elle n'est pas déclarée par l'app et ne peut pas être retirée — le
    reste du framework en dépend (``UserState``, la rotation de session,
    l'écriture de ``request.state.user``). Les ``@auth.source`` s'ajoutent
    derrière elle, ils ne la remplacent pas.
    """
    key = getattr(getattr(bretzel, "config", None), "_auth_key", None)
    if not key:
        return None
    state = getattr(request, "state", None)
    jar = getattr(state, "cookies", None)
    if not isinstance(jar, dict):
        # Avant ``SessionMiddleware``, ou hors pile Bretzel : on relit
        # l'en-tête nous-mêmes plutôt que de supposer.
        jar = parse_cookies_from_scope(getattr(request, "scope", {}) or {})
    cookie = jar.get(COOKIE_AUTH, "")
    return verify_auth_cookie(cookie, key) if cookie else None


# ───────────────────────────────────────────────────────────────────────────
# Internals — config + request-state shim
# ───────────────────────────────────────────────────────────────────────────


def _auth_key(ctx: object) -> bytes:
    """Pull the derived auth key from ``ctx.app.config``.

    Fails loudly when no config / no key is reachable. **Asymmetric**
    with :func:`render.context.RenderContext._action_key`, which
    silently falls back to empty bytes (action-id rendering can run
    without an attached app in component unit tests, and a bare id
    that won't verify at dispatch time is harmless there). Here in
    auth, signing with an empty key would produce attacker-forgeable
    cookies — ``hmac.new(b"", payload).hexdigest()`` is computable by
    anyone — so we refuse to sign rather than write a cookie nobody
    should trust.
    """
    config = getattr(getattr(ctx, "app", None), "config", None)
    if config is None:
        raise RuntimeError(
            "auth.login/logout needs ctx.app.config — none reachable. "
            "Build a stub via BretzelConfig(secret_key=...) and attach it "
            "to the test app."
        )
    try:
        return config._auth_key
    except AttributeError:
        raise RuntimeError(
            "ctx.app.config has no derived _auth_key. Always go through "
            "BretzelConfig(secret_key=...) so __post_init__ derives the keys."
        ) from None


def _session_max_age_days(ctx: object) -> int:
    config = getattr(getattr(ctx, "app", None), "config", None)
    return int(getattr(config, "session_max_age_days", 30) or 30) if config else 30


def _forget_identity(ctx: object) -> None:
    """Oublie l'identité mémoïsée — l'identité vient de changer.

    Sans ça, une lecture postérieure à ``login()`` dans la même requête
    rendrait l'identité précédente.
    """
    scope = getattr(getattr(ctx, "request", None), "scope", None)
    if isinstance(scope, dict):
        scope.pop(_MEMO, None)


def _attach_user(ctx: object, user: AuthUser | None) -> None:
    """Store ``user`` on the underlying request so app code reaching
    ``request.state.user`` (FastAPI idiom) sees the change without
    going through the framework's ``auth.user_id()`` API."""
    request = getattr(ctx, "request", None)
    if request is not None and hasattr(request, "state"):
        # Tests may use bare ``object()`` as the request stand-in — we
        # don't fail just because state isn't writable.
        with contextlib.suppress(Exception):
            request.state.user = user
