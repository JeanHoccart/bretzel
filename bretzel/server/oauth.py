"""Les portes de connexion — deux protocoles, aucun service nommé.

Ce module ne connaît ni Google, ni GitHub, ni Microsoft, et c'est
délibéré : **la découverte OIDC rend un préréglage strictement pire que
son absence.** Un ``oauth.Google(...)`` figerait trois URL que
``/.well-known/openid-configuration`` va chercher correctement pour
toujours ; le jour où le fournisseur en bouge une, le préréglage ment et
la découverte non. Le catalogue est donc de la **donnée** — un issuer
dans le code de l'app — jamais de l'API ici.

Deux classes, parce qu'il n'existe que deux formes :

- :class:`OIDC` — le fournisseur publie un ``issuer``. Une URL suffit,
  tout le reste est découvert, et l'identité arrive dans l'``id_token``.
  Couvre Google, Microsoft Entra, Auth0, Okta, Keycloak, Authentik,
  Zitadel, GitLab, LinkedIn, Salesforce, Twitch…
- :class:`OAuth2` — pas de découverte dans le protocole, donc les trois
  URL sont données. L'identité arrive d'un appel ``userinfo``. Couvre
  GitHub, Discord, Slack, Facebook, Notion, Atlassian, Spotify…

**Aucune dépendance neuve**, et c'est ce qui a décidé de la forme :

- pas de vérification de signature JWT, donc pas de ``cryptography``.
  Dans le flux ``authorization_code`` avec ``client_secret``,
  l'``id_token`` arrive **directement du token endpoint, par TLS** —
  OpenID Connect Core § 3.1.3.7 autorise explicitement à ne pas
  revérifier sa signature dans ce cas. On décode le payload, puis on
  vérifie ``iss``, ``aud``, ``exp`` et le ``nonce`` ;
- pas de client HTTP, donc pas d'``httpx`` en production. Un échange de
  code, c'est **un** POST par connexion : ``urllib.request`` de la
  bibliothèque standard, poussé dans un thread par ``anyio`` (qui arrive
  avec starlette) pour ne pas bloquer la boucle. Le coût d'un saut de
  thread une fois par connexion ne se mesure pas.

⚠️ Un fournisseur reste hors de portée : **Apple**, dont le
``client_secret`` est lui-même un JWT signé en ES256. Il demanderait
``cryptography``. Une app qui en a besoin peut fabriquer le secret
elle-même et le passer à :class:`OIDC` — la porte ne fait aucune
différence.

"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from bretzel.core import call_without_blocking
from bretzel.server.auth import (
    app_of,
    login,
    request_scheme,
    resolve_cookie_secure,
)
from bretzel.server.crypto import sign as _crypto_sign
from bretzel.server.crypto import verify as _crypto_verify
from bretzel.server.navigation import redirect_response

__all__ = ["OIDC", "OAuth2", "OAuthProfile", "OAuthError"]

#: Durée de vie du cookie de transaction (``state`` + vérifieur PKCE).
#: Dix minutes : le temps d'une saisie de mot de passe et d'un second
#: facteur chez le fournisseur, pas celui d'un onglet oublié.
_TRANSACTION_MAX_AGE = 600

_HTTP_TIMEOUT = 10


class OAuthError(RuntimeError):
    """Une transaction OAuth qui n'aboutit pas, côté framework.

    Ne porte **jamais** le détail au navigateur : les causes (état
    absent, code refusé, profil sans identifiant) sont du diagnostic
    serveur. Le visiteur, lui, est renvoyé sur la page de connexion.
    """


@dataclass(frozen=True, slots=True)
class OAuthProfile:
    """Ce qu'une porte sait de la personne, une fois le code échangé.

    ``subject`` est son identifiant **chez le fournisseur** — stable,
    opaque, et ce n'est PAS ton ``user_id`` : c'est la clé de jointure
    avec ta table. ``raw`` porte le profil entier, parce que ce qui est
    propre à un service (l'``avatar_url`` de GitHub, le ``hd`` de
    Google) n'a pas à remonter dans une forme normalisée pour être
    accessible.
    """

    subject: str
    email: str = ""
    name: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    token: str = ""


# ───────────────────────────────────────────────────────────────────────────
# HTTP — stdlib, poussé dans un thread
# ───────────────────────────────────────────────────────────────────────────


def _http_json(
    url: str,
    *,
    data: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Un aller-retour HTTP qui rend du JSON. Bloquant — cf. :func:`_fetch`."""
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method="POST" if data else "GET")
    req.add_header("Accept", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            payload = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        # ⚠️ Un endpoint OAuth qui REFUSE répond 4xx **avec un corps JSON
        # utile** (``{"error": "invalid_grant"}``) — c'est le protocole,
        # pas une panne. ``urlopen`` lève pourtant sur tout non-2xx, et
        # sans ce rattrapage l'exception traversait la porte : le
        # visiteur recevait une 500 au lieu de revenir sur la connexion.
        # Trouvé le 2026-08-24 en faussant le vérifieur PKCE contre un
        # vrai fournisseur — la sonde ne rougissait pas, elle CASSAIT.
        try:
            payload = exc.read().decode("utf-8")
        except Exception:
            # Large exprès : corps vide, tronqué, encodage exotique — la
            # cause exacte n'a aucune valeur ici, il n'y a qu'une suite
            # possible, refuser proprement.
            raise OAuthError(f"{url} a répondu {exc.code} sans corps lisible.") from None
    except urllib.error.URLError as exc:
        # Fournisseur injoignable, DNS, TLS. Un refus propre plutôt qu'une
        # trace : le visiteur n'y peut rien.
        raise OAuthError(f"{url} injoignable : {exc.reason}") from None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        # GitHub rend du form-urlencoded quand l'en-tête ``Accept`` n'est
        # pas honoré — on le pose, mais un fournisseur peut l'ignorer, et
        # un échec ici serait illisible.
        parsed = {k: v[0] for k, v in urllib.parse.parse_qs(payload).items()}
    if not isinstance(parsed, dict):
        raise OAuthError(f"{url} n'a pas rendu un objet JSON.")
    return parsed


async def _fetch(
    url: str,
    *,
    data: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """:func:`_http_json`, hors de la boucle d'événements.

    Même point de passage que le code d'app (``core/invoke``) : l'appel
    HTTP d'ici est bloquant par nature — ``urllib`` — et le laisser sur
    la boucle gèlerait le worker le temps de l'échange de code.
    """
    return await call_without_blocking(_http_json, url, data=data, headers=headers)


def _b64url_json(segment: str) -> dict[str, Any]:
    """Décode un segment de JWT (base64url sans padding) en dict."""
    padded = segment + "=" * (-len(segment) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except Exception as exc:
        raise OAuthError("id_token illisible.") from exc


# ───────────────────────────────────────────────────────────────────────────
# La porte
# ───────────────────────────────────────────────────────────────────────────


class _Door:
    """Le tronc commun des deux protocoles : deux routes et une transaction.

    Sous-classer n'est pas prévu hors de ce module — ce qui varie entre
    les deux formes tient dans deux méthodes (:meth:`_endpoints`,
    :meth:`_profile`), pas dans le déroulement.
    """

    def __init__(
        self,
        *,
        name: str,
        client_id: str,
        client_secret: str,
        scope: str,
        path: str | None = None,
        redirect_uri: str | None = None,
        on_denied: str = "/login",
        on_success: str = "/",
    ) -> None:
        if not name or not name.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                f"oauth : name={name!r} doit être alphanumérique — il devient "
                "un segment d'URL et distingue deux portes du même protocole."
            )
        if not client_id or not client_secret:
            raise ValueError(
                f"oauth {name!r} : client_id et client_secret sont requis."
            )
        self.name = name
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self.path = path or f"/auth/{name}"
        self.redirect_uri = redirect_uri
        self.on_denied = on_denied
        self.on_success = on_success

    # ── ce que l'app et la garde lisent ────────────────────────────────

    @property
    def callback_path(self) -> str:
        return f"{self.path}/callback"

    @property
    def paths(self) -> tuple[str, str]:
        """Les deux chemins, à laisser ouverts par toute garde d'auth.

        Les DEUX : oublier la callback produit une boucle de redirection
        dont le symptôme ne désigne rien. C'est pour ça qu'ils remontent
        dans ``app.public_paths`` au lieu d'être recopiés par l'app.
        """
        return (self.path, self.callback_path)

    # ── à spécialiser ──────────────────────────────────────────────────

    async def _endpoints(self) -> dict[str, str]:
        raise NotImplementedError

    async def _profile(self, tokens: dict[str, Any], nonce: str) -> OAuthProfile:
        raise NotImplementedError

    # ── le déroulement, commun ─────────────────────────────────────────

    def mount(self, app: Any, on_user: Any) -> None:
        """Monte les deux routes sur le FastAPI sous-jacent.

        Des routes brutes, pas des ``@page`` : une porte ne rend aucun
        HTML — elle redirige, deux fois. Elles n'ont pas besoin d'un
        contexte de rendu pour autant : ``RenderContextMiddleware``
        enveloppe TOUTES les requêtes, donc ``auth.login()`` pose bien
        son cookie depuis la callback (mesuré le 2026-08-23).

        ⚠️ Les trois redirections passent par :func:`redirect_response`
        et **jamais** par un ``RedirectResponse`` nu. La raison est un
        piège que rien ne signale : ``render/shell.py`` pose
        ``hx-boost="true"`` au niveau du document dès qu'une page porte
        un ``outlet``. Le lien « Continuer avec X » est un ``<a>``
        interne, donc boosté — htmx suivrait la 302 en ``fetch``, vers
        une AUTRE origine, et ça échoue en silence (CORS) ou swappe du
        HTML étranger dans l'outlet. ``redirect_response`` répond alors
        un ``HX-Redirect``, que le navigateur exécute en vraie
        navigation. ``examples/auth`` y échappait par accident (sa
        page de connexion n'a pas d'outlet), donc la sonde était verte.
        """
        async def start(request: Any) -> Any:
            endpoints = await self._endpoints()
            state = secrets.token_urlsafe(24)
            verifier = secrets.token_urlsafe(48)
            nonce = secrets.token_urlsafe(16)
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .decode()
                .rstrip("=")
            )
            params = {
                "response_type": "code",
                "client_id": self.client_id,
                "redirect_uri": self._redirect_uri(request),
                "scope": self.scope,
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
            response = redirect_response(
                request, f"{endpoints['authorize']}?{urllib.parse.urlencode(params)}"
            )
            self._seal(request, response, state, verifier, nonce)
            return response

        async def callback(request: Any) -> Any:
            try:
                state, verifier, nonce = self._unseal(request)
                supplied = request.query_params.get("state", "")
                if not supplied or not hmac.compare_digest(supplied, state):
                    raise OAuthError("state absent ou non concordant.")
                code = request.query_params.get("code", "")
                if not code:
                    raise OAuthError(
                        "pas de code — le fournisseur a répondu "
                        f"{request.query_params.get('error', 'sans rien dire')}."
                    )
                endpoints = await self._endpoints()
                tokens = await _fetch(
                    endpoints["token"],
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": self._redirect_uri(request),
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "code_verifier": verifier,
                    },
                )
                if "access_token" not in tokens and "id_token" not in tokens:
                    raise OAuthError(
                        f"le token endpoint a refusé : {tokens.get('error')}"
                    )
                profile = await self._profile(tokens, nonce)
                # ``@auth.door`` REFUSE une ``async def`` (cf.
                # ``decorators/identity.py``), et son exemple canonique
                # est un ``users.upsert(...)`` — donc une écriture en
                # base, forcément synchrone, dans la callback. Délestée,
                # sinon elle gèle la boucle à chaque connexion.
                user_id = await call_without_blocking(on_user, profile)
            except OAuthError:
                return self._refuse(request)
            if not user_id:
                return self._refuse(request)
            login(str(user_id))
            response = redirect_response(request, self.on_success)
            response.delete_cookie(self._cookie_name)
            return response

        app.fastapi.add_route(
            self.path, start, methods=["GET"], name=f"bz_login_{self.name}"
        )
        app.fastapi.add_route(
            self.callback_path,
            callback,
            methods=["GET"],
            name=f"bz_login_{self.name}_cb",
        )

    # ── transaction ────────────────────────────────────────────────────

    @property
    def _cookie_name(self) -> str:
        return f"Bretzel_oauth_{self.name}"

    def _refuse(self, request: Any) -> Any:
        """Toute cause de refus sort par la même porte, sans détail.

        Un anonyme qui apprend *pourquoi* sa transaction a échoué apprend
        quelque chose sur le compte visé. Le diagnostic reste côté
        serveur, dans l'exception levée.
        """
        response = redirect_response(request, self.on_denied)
        response.delete_cookie(self._cookie_name)
        return response

    def _key(self, request: Any) -> bytes:
        key = getattr(getattr(app_of(request), "config", None), "_auth_key", None)
        if not key:
            raise OAuthError("clé dérivée introuvable — l'app n'est pas montée.")
        return key

    def _secure(self, request: Any) -> bool:
        config = getattr(app_of(request), "config", None)
        return resolve_cookie_secure(
            request_scheme(request), getattr(config, "secure_cookies", None)
        )

    def _seal(
        self, request: Any, response: Any, state: str, verifier: str, nonce: str
    ) -> None:
        """Pose ``state`` + vérifieur PKCE + ``nonce`` dans un cookie signé.

        Signé, et pas seulement posé : sans signature, un attaquant
        choisit le ``state`` des deux côtés et la protection CSRF du flux
        tombe. Dix minutes de vie, ``HttpOnly``, ``SameSite=lax`` — et
        ``lax`` plutôt que ``strict``, sinon le navigateur ne le renvoie
        pas au retour du fournisseur, qui est une navigation inter-site.
        """
        payload = f"{state}:{verifier}:{nonce}"
        signature = _crypto_sign(self._key(request), payload)
        response.set_cookie(
            self._cookie_name,
            f"{payload}.{signature}",
            max_age=_TRANSACTION_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=self._secure(request),
        )

    def _unseal(self, request: Any) -> tuple[str, str, str]:
        raw = request.cookies.get(self._cookie_name, "")
        if not raw or "." not in raw:
            raise OAuthError("cookie de transaction absent — lien direct, ou expiré.")
        payload, signature = raw.rsplit(".", 1)
        if not _crypto_verify(self._key(request), payload, signature):
            raise OAuthError("cookie de transaction non signé par nous.")
        parts = payload.split(":")
        if len(parts) != 3:
            raise OAuthError("cookie de transaction malformé.")
        return parts[0], parts[1], parts[2]

    def _redirect_uri(self, request: Any) -> str:
        """L'URL absolue de la callback.

        Déduite de la requête par défaut, surchargeable par
        ``redirect_uri=`` : derrière un proxy qui termine le TLS,
        ``base_url`` peut annoncer ``http`` alors que le fournisseur
        exigera l'``https`` enregistré chez lui.
        """
        if self.redirect_uri:
            return self.redirect_uri
        return str(request.base_url).rstrip("/") + self.callback_path


# ───────────────────────────────────────────────────────────────────────────
# OIDC
# ───────────────────────────────────────────────────────────────────────────


class OIDC(_Door):
    """Un fournisseur OpenID Connect, décrit par son seul ``issuer`` ::

        oauth.OIDC(name="google", issuer="https://accounts.google.com",
                   client_id=..., client_secret=...)

    Les trois endpoints sortent de
    ``{issuer}/.well-known/openid-configuration``, lu une fois puis gardé
    pour la vie du process. C'est ce qui remplace un préréglage par
    service : le fournisseur reste maître de ses URL.
    """

    def __init__(
        self,
        *,
        name: str,
        issuer: str,
        client_id: str,
        client_secret: str,
        scope: str = "openid email profile",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            name=name,
            client_id=client_id,
            client_secret=client_secret,
            scope=scope,
            **kwargs,
        )
        self.issuer = issuer.rstrip("/")
        self._cache: dict[str, str] | None = None

    async def _endpoints(self) -> dict[str, str]:
        if self._cache is None:
            doc = await _fetch(f"{self.issuer}/.well-known/openid-configuration")
            try:
                self._cache = {
                    "authorize": doc["authorization_endpoint"],
                    "token": doc["token_endpoint"],
                    "userinfo": doc.get("userinfo_endpoint", ""),
                }
            except KeyError as exc:
                raise OAuthError(
                    f"{self.issuer} ne publie pas de configuration OIDC complète "
                    f"({exc}). Si le fournisseur n'est pas OIDC, utilise "
                    "oauth.OAuth2 avec ses trois URL."
                ) from None
        return self._cache

    async def _profile(self, tokens: dict[str, Any], nonce: str) -> OAuthProfile:
        raw_id = tokens.get("id_token", "")
        if not raw_id or raw_id.count(".") != 2:
            raise OAuthError("réponse OIDC sans id_token exploitable.")
        claims = _b64url_json(raw_id.split(".")[1])

        # Ce qu'on vérifie, et pourquoi pas la signature : le jeton arrive
        # du token endpoint, par TLS, en réponse à NOTRE POST authentifié
        # — OIDC Core § 3.1.3.7 le dit suffisant. Restent les quatre
        # contrôles que le transport ne donne pas.
        if str(claims.get("iss", "")).rstrip("/") != self.issuer:
            raise OAuthError("id_token émis par un autre issuer.")
        aud = claims.get("aud", "")
        auds = aud if isinstance(aud, list) else [aud]
        if self.client_id not in auds:
            raise OAuthError("id_token destiné à un autre client.")
        if int(claims.get("exp", 0)) <= int(time.time()):
            raise OAuthError("id_token expiré.")
        # ⚠️ Le ``and claims.get("nonce")`` qui se trouvait ici rendait le
        # contrôle FACULTATIF : un jeton SANS nonce passait, alors qu'on
        # en avait envoyé un. C'est exactement la porte au rejeu que le
        # nonce existe pour fermer, et OIDC Core l'exige dans l'autre
        # sens (« si un nonce a été envoyé, sa présence ET sa valeur
        # DOIVENT être vérifiées »). Trouvé le 2026-08-24 en mutant
        # l'envoi du nonce : la sonde restait verte.
        if nonce and not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
            raise OAuthError("nonce absent ou non concordant — rejeu possible.")

        subject = str(claims.get("sub", ""))
        if not subject:
            raise OAuthError("id_token sans sub.")
        return OAuthProfile(
            subject=subject,
            email=str(claims.get("email", "")),
            name=str(claims.get("name", "")),
            raw=claims,
            token=str(tokens.get("access_token", "")),
        )


# ───────────────────────────────────────────────────────────────────────────
# OAuth2 nu
# ───────────────────────────────────────────────────────────────────────────


class OAuth2(_Door):
    """Un fournisseur OAuth2 sans OIDC — les trois URL sont données ::

        oauth.OAuth2(name="github",
                     authorize="https://github.com/login/oauth/authorize",
                     token="https://github.com/login/oauth/access_token",
                     userinfo="https://api.github.com/user",
                     subject="id", scope="read:user user:email",
                     client_id=..., client_secret=...)

    ``subject`` nomme le champ du profil qui sert d'identifiant stable —
    ``id`` chez GitHub, ``sub`` ailleurs. Il n'y a pas de valeur par
    défaut universelle, et deviner ici produirait un identifiant qui
    change sous les pieds de l'app : le champ est déclaré.
    """

    def __init__(
        self,
        *,
        name: str,
        authorize: str,
        token: str,
        userinfo: str,
        client_id: str,
        client_secret: str,
        subject: str = "id",
        email_field: str = "email",
        name_field: str = "name",
        scope: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            name=name,
            client_id=client_id,
            client_secret=client_secret,
            scope=scope,
            **kwargs,
        )
        self._urls = {"authorize": authorize, "token": token, "userinfo": userinfo}
        self.subject_field = subject
        self.email_field = email_field
        self.name_field = name_field

    async def _endpoints(self) -> dict[str, str]:
        return self._urls

    async def _profile(self, tokens: dict[str, Any], nonce: str) -> OAuthProfile:
        access = str(tokens.get("access_token", ""))
        if not access:
            raise OAuthError("réponse sans access_token.")
        raw = await _fetch(
            self._urls["userinfo"],
            headers={"Authorization": f"Bearer {access}", "User-Agent": "bretzel"},
        )
        subject = str(raw.get(self.subject_field, "") or "")
        if not subject:
            raise OAuthError(
                f"le profil ne porte pas {self.subject_field!r} — vérifie "
                "subject= contre la doc du fournisseur."
            )
        return OAuthProfile(
            subject=subject,
            email=str(raw.get(self.email_field, "") or ""),
            name=str(raw.get(self.name_field, "") or ""),
            raw=raw,
            token=access,
        )
