"""``@auth.source`` et ``@auth.door`` — les deux moitiés de l'identité.

Elles répondent à deux questions distinctes, et c'est le partage qui
tient tout le sujet :

- **``@auth.source`` — « qui est cette requête ? »** Une lecture, jouée à
  CHAQUE requête. Le cookie signé de Bretzel en est une, toujours
  essayée en premier ; un JWT porté, une clé d'API ou un en-tête posé
  par un proxy SSO en sont d'autres, qu'on ajoute derrière.
- **``@auth.door`` — « comment devient-on connu ? »** Une porte,
  empruntée UNE fois. Elle finit toujours par :func:`bretzel.auth.login`,
  c'est-à-dire par le cookie : une porte ne remplace pas la lecture,
  elle l'alimente.

Les deux restent des décorateurs **libres** — ``from bretzel import
auth`` — et non des méthodes de l'app. Ce n'est pas un détail de style :
une feature qui écrirait ``@app.auth_source`` devrait importer
l'instance, ce que ``app-structure.md`` § 9 interdit explicitement
(« ``from myapp.main import app`` dans une feature. Jamais. »). Comme
``@page`` et ``@error_page``, ces décorateurs **marquent** seulement ;
``app.include(...)`` ramasse la marque au moment de la composition.
L'anti-règle 4 du charter — « pas d'enregistrement à l'import » — est
ainsi tenue par construction.

"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

#: La marque d'une source d'identité. Lue par ``Bretzel._register_declaration``.
MARK_SOURCE = "_bz_auth_source"

#: La marque d'une porte. Porte l'objet porte lui-même, pas un booléen —
#: la fonction décorée n'a de sens qu'attachée à SA porte.
MARK_DOOR = "_bz_auth_door"


def source(fn: Callable[[Any], str | None]) -> Callable[[Any], str | None]:
    """Declare an identity source checked after the signed cookie.

    ::

        from bretzel import auth

        @auth.source
        def from_bearer(request) -> str | None:
            token = request.headers.get("authorization", "")
            return subject_of(token) if token.startswith("Bearer ") else None

    La fonction rend l'identifiant, ou ``None`` pour « je ne sais pas »
    — auquel cas la source suivante est essayée. Elle ne rend jamais un
    booléen : une garde qui journalise ou qui autorise par rôle a besoin
    du nom, et un booléen l'aurait forcée à relire.

    **Synchrone, et c'est un contrat.** Cette lecture tourne sur chaque
    requête et depuis un middleware utilisateur, où rien n'est encore
    posé ; une source qui a besoin du réseau (rafraîchir un JWKS) le
    fait hors requête et sert un cache. Une ``async def`` est refusée
    ici plutôt que d'être attendue silencieusement — ce serait un
    ``await`` par requête que personne n'a demandé.
    """
    if inspect.iscoroutinefunction(fn):
        raise TypeError(
            "@auth.source attend une fonction synchrone — elle est appelée à "
            f"chaque requête, y compris depuis un middleware ; {fn.__name__} "
            "est une coroutine. Fais l'appel réseau hors requête et sers un "
            "cache."
        )
    if not callable(fn):
        raise TypeError(f"@auth.source expects a callable; got {type(fn).__name__}")
    setattr(fn, MARK_SOURCE, True)
    return fn


def door(porte: Any) -> Callable[[Callable[..., str | None]], Callable[..., str | None]]:
    """Declare a login provider and how its profile is handled.

    ::

        from bretzel import auth, oauth

        @auth.door(oauth.OIDC(name="google", issuer="https://accounts.google.com",
                              client_id=..., client_secret=...))
        def google_user(profile) -> str | None:
            if not profile.email.endswith("@macorp.fr"):
                return None
            return str(users.upsert(email=profile.email).id)

    La fonction décorée rend **ton** identifiant — celui de ta table,
    pas celui du fournisseur — ou ``None`` pour refuser. Elle est
    obligatoire, et c'est un choix de sécurité : sans elle, le défaut
    serait « toute personne ayant un compte chez le fournisseur entre »,
    un défaut-ouvert qui ne se voit jamais en relecture parce que la
    page s'affiche parfaitement.

    Empiler plusieurs ``@auth.door`` sur la même fonction est licite —
    deux portes qui aboutissent à la même table d'utilisateurs.
    """
    if not hasattr(porte, "mount"):
        raise TypeError(
            "@auth.door attend une porte (oauth.OIDC / oauth.OAuth2) ; "
            f"reçu {type(porte).__name__}."
        )

    def decorate(fn: Callable[..., str | None]) -> Callable[..., str | None]:
        if inspect.iscoroutinefunction(fn):
            raise TypeError(
                "@auth.door attend une fonction synchrone : elle tourne "
                "dans la callback, après l'échange de code, et n'a rien à "
                f"attendre ; {fn.__name__} est une coroutine."
            )
        doors: list[Any] = list(getattr(fn, MARK_DOOR, ()))
        doors.append(porte)
        setattr(fn, MARK_DOOR, tuple(doors))
        return fn

    return decorate
