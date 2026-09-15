"""La chaîne d'identité — l'ordre, la décision, et ce qu'elle refuse.

``resolve_identity`` est la seule chose qui répond à « qui est cette
requête ». Elle joue le cookie signé, puis les sources déclarées par
l'app avec ``@auth.source``, dans l'ordre d'inclusion. Ce fichier fixe les
trois propriétés qui font que ce n'est pas qu'une boucle :

1. **le cookie d'abord** — la population des navigateurs est de loin la
   plus nombreuse, et c'est le seul porteur que le framework ait signé ;
2. **la première réponse gagne**, et les suivantes ne sont pas jouées —
   sinon une source lente coûterait à chaque requête déjà résolue ;
3. **une source qui casse remonte**. Une identité avalée se lit
   « anonyme », donc une garde referme la porte au nez de tout le monde
   sans qu'aucune erreur ne s'affiche : c'est le mode de panne le plus
   cher de ce sujet, et il est identique aux onze ``except`` silencieux
   que l'audit du 2026-08-19 a retirés.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bretzel import Bretzel, auth
from bretzel.server.auth import COOKIE_AUTH, resolve_identity

SECRET = "k" * 32


def make_app(*sources: object) -> Bretzel:
    app = Bretzel(title="chaîne", secret_key=SECRET)
    for source in sources:
        app.include(source)
    return app


def make_request(app: Bretzel, cookies: dict[str, str] | None = None) -> SimpleNamespace:
    """Une requête réduite à ce que la chaîne lit vraiment."""
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(bretzel=app)),
        state=SimpleNamespace(cookies=cookies or {}),
        # Un dict FRAIS par requête : c'est lui qui porte le mémo
        # d'identité, et le partager ferait passer une gate pour verte.
        scope={},
        headers={},
    )


def signed_cookie_for(app: Bretzel, user_id: str) -> str:
    """Le cookie que ``auth.login`` poserait, fabriqué sans contexte."""
    import time

    from bretzel.server.crypto import sign

    payload = f"{user_id}:{int(time.time()) + 600}"
    return f"{payload}.{sign(app.config._auth_key, payload)}"


# ── l'ordre ────────────────────────────────────────────────────────────────


def test_the_signed_cookie_wins_over_a_declared_source() -> None:
    @auth.source
    def from_header(request: object) -> str | None:
        return "u-source"

    app = make_app(from_header)
    request = make_request(app, {COOKIE_AUTH: signed_cookie_for(app, "u-cookie")})

    assert resolve_identity(request) == "u-cookie"


def test_sources_are_tried_in_declaration_order() -> None:
    calls: list[str] = []

    @auth.source
    def first(request: object) -> str | None:
        calls.append("first")
        return None

    @auth.source
    def second(request: object) -> str | None:
        calls.append("second")
        return "u-second"

    @auth.source
    def third(request: object) -> str | None:
        calls.append("third")
        return "u-third"

    app = make_app(first, second, third)

    assert resolve_identity(make_request(app)) == "u-second"
    assert calls == ["first", "second"], (
        "la troisième source a été jouée alors que la deuxième avait "
        "répondu — une chaîne qui continue coûte à chaque requête"
    )


def test_no_source_and_no_cookie_is_anonymous() -> None:
    assert resolve_identity(make_request(make_app())) is None


def test_a_source_that_breaks_surfaces() -> None:
    @auth.source
    def broken(request: object) -> str | None:
        raise RuntimeError("annuaire injoignable")

    app = make_app(broken)
    with pytest.raises(RuntimeError, match="annuaire"):
        resolve_identity(make_request(app))


def test_a_source_runs_once_per_request() -> None:
    """La chaîne est jouée DEUX fois sur une requête protégée.

    La garde de l'app est le middleware le plus EXTERNE et demande
    ``auth.user_id(request)`` ; ``AuthMiddleware``, plus interne,
    redemande la même chose sans pouvoir voir la première réponse. C'est
    la recette que la doc prescrit — donc sans mémo, la fonction de
    l'app tourne deux fois, et son docstring suggère lui-même d'y
    vérifier un JWT (10² à 10³ fois le coût d'un dict).
    """
    calls: list[str] = []

    @auth.source
    def compte(request: object) -> str | None:
        calls.append("x")
        return "u-9"

    app = make_app(compte)
    request = make_request(app)

    assert resolve_identity(request) == "u-9"
    assert resolve_identity(request) == "u-9"
    assert calls == ["x"], f"la source a tourné {len(calls)} fois"


def test_two_requests_do_not_share_the_memo() -> None:
    """Le versant licite : le mémo est par requête, pas par process."""
    seen: list[object] = []

    @auth.source
    def compte(request: object) -> str | None:
        seen.append(request)
        return "u-9"

    app = make_app(compte)
    resolve_identity(make_request(app))
    resolve_identity(make_request(app))
    assert len(seen) == 2


def test_logging_in_forgets_the_memo() -> None:
    """``login`` change l'identité au milieu de la requête."""
    from bretzel.server.auth import _MEMO

    app = make_app()
    request = make_request(app)
    assert resolve_identity(request) is None
    assert _MEMO in request.scope

    class _Ctx:
        pass

    ctx = _Ctx()
    ctx.request = request
    from bretzel.server.auth import _forget_identity

    _forget_identity(ctx)
    assert _MEMO not in request.scope


# ── la collecte ────────────────────────────────────────────────────────────


def test_include_collects_in_order_and_deduplicates() -> None:
    @auth.source
    def alpha(request: object) -> str | None:
        return None

    @auth.source
    def beta(request: object) -> str | None:
        return None

    app = make_app(alpha, beta, alpha)
    assert [fn.__name__ for fn in app.identity_sources] == ["alpha", "beta"]


def test_an_identity_source_is_not_mistaken_for_a_page() -> None:
    """La marque est testée AVANT celle de ``@page`` — sans quoi une
    source d'identité finirait montée comme une route."""

    @auth.source
    def source(request: object) -> str | None:
        return None

    app = make_app(source)
    assert not app.routables


# ── ce que le décorateur refuse ────────────────────────────────────────────


def test_identify_refuses_a_coroutine() -> None:
    with pytest.raises(TypeError, match="synchrone"):

        @auth.source
        async def from_directory(request: object) -> str | None:  # pragma: no cover
            return None


def test_auth_source_refuses_a_non_callable() -> None:
    with pytest.raises(TypeError):
        auth.source("X-Remote-User")  # type: ignore[arg-type]
