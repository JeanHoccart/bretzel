"""Gate : une seule chose au monde décide QUI est une requête.

Le défaut qu'elle ferme
----------------------
Le 2026-08-23, ``AuthMiddleware`` lisait le cookie ``Bretzel_auth`` et le
vérifiait lui-même. Rien ne l'interdisait, et la conséquence n'était pas
un bug local : **une app qui résolvait son propre utilisateur dans son
middleware recevait ``401``**, parce que le middleware du framework
tournait après le sien et écrasait ``state.user_id``. Le charter disait
« l'app fait son auth » pendant que le code livrait un scope d'état
entier (``UserState``) qui n'existait que par le cookie du framework.

La réparation a été de faire passer TOUT LE MONDE par
:func:`bretzel.server.auth.resolve_identity` — le cookie signé d'abord,
puis les sources déclarées avec ``@auth.source``. Cette gate empêche le
deuxième lecteur de réapparaître : un module qui relit ``COOKIE_AUTH``
pour décider d'une identité court-circuite les sources de l'app, et il
le fait **en silence** (une identité qui manque se lit « anonyme », pas
« erreur »).

Ce qu'elle ne garde PAS
-----------------------
La clé dérivée ``_auth_key``. La lire n'est pas un second lecteur
d'identité : ``oauth.py`` s'en sert pour signer sa transaction (state +
vérifieur PKCE), ce qui est de la crypto, pas de l'identité. Ce que les
apps en font est gardé ailleurs, par
``test_an_app_never_reaches_inside_the_framework``.
"""

from __future__ import annotations

import ast

from tests.consistency._discovery import (
    PACKAGE_DIR,
    PACKAGE_FLOOR,
    ParsedSource,
    parsed_sources,
)

#: Les deux noms par lesquels on lit une identité de cookie.
_IDENTITY_NAMES = frozenset({"COOKIE_AUTH", "verify_auth_cookie"})


def identity_reads(tree: ast.Module) -> list[int]:
    """Les lignes qui NOMMENT une lecture d'identité — le détecteur.

    Sur l'AST et non sur le texte, parce que le premier jumeau licite
    rencontré est un commentaire : ``crypto.py`` écrit « auth.login /
    verify_auth_cookie » pour dire à quoi sert une clé dérivée. Un
    balayage textuel l'accusait.
    """
    hits: list[int] = []
    for node in ast.walk(tree):
        named = ""
        if isinstance(node, ast.Name):
            named = node.id
        elif isinstance(node, ast.Attribute):
            named = node.attr
        elif isinstance(node, ast.alias):
            named = node.name
        if named in _IDENTITY_NAMES:
            hits.append(getattr(node, "lineno", 0))
    return hits


def _is_owner(source: ParsedSource) -> bool:
    """``bretzel/server/auth.py`` — le seul propriétaire."""
    return source.path.name == "auth.py" and source.path.parent.name == "server"


def _sources() -> list[ParsedSource]:
    return parsed_sources(PACKAGE_DIR, floor=PACKAGE_FLOOR)


def offenders() -> list[str]:
    """Les sites du framework qui lisent une identité hors de ``auth.py``."""
    return [
        f"{source.path.relative_to(PACKAGE_DIR).as_posix()}:{lineno}"
        for source in _sources()
        if not _is_owner(source)
        for lineno in identity_reads(source.tree)
    ]


def owner_hits() -> list[int]:
    """Les lectures DANS ``auth.py`` — le contrôle positif.

    Sans lui, un détecteur cassé rendrait la même liste vide que la
    conformité, et la gate serait verte pour la mauvaise raison. C'est
    ce versant-là qui a trouvé les deux seuls bugs de gate du 2026-08-19.
    """
    return [
        lineno
        for source in _sources()
        if _is_owner(source)
        for lineno in identity_reads(source.tree)
    ]


def test_the_sweep_is_not_vacuous() -> None:
    assert len(_sources()) >= PACKAGE_FLOOR


def test_the_detector_finds_the_owner() -> None:
    hits = owner_hits()
    assert len(hits) >= 4, (
        "le détecteur ne trouve plus les lectures de auth.py lui-même — il "
        f"ne mesure donc plus rien. Trouvé : {hits}"
    )


def test_nothing_else_reads_an_identity() -> None:
    sites = offenders()
    assert not sites, (
        "Ces modules décident d'une identité en relisant le cookie, donc "
        "sans passer par les sources déclarées avec @auth.source :\n  "
        + "\n  ".join(sites)
        + "\n\nAppelle auth.resolve_identity(request) — c'est elle qui joue "
        "le cookie PUIS les sources de l'app. Un second lecteur rend le "
        "framework aveugle à l'identité que l'app connaît, et il le fait "
        "sans erreur : la personne est simplement anonyme."
    )


def test_the_detector_still_bites() -> None:
    assert identity_reads(ast.parse('cookies.get(COOKIE_AUTH, "")'))
    assert identity_reads(ast.parse("verify_auth_cookie(cookie, key)"))
    assert identity_reads(ast.parse("from bretzel.server.auth import COOKIE_AUTH"))
    # Les jumeaux LICITES. Le premier est celui qui a fait rougir la
    # version textuelle de cette gate : un commentaire qui NOMME la
    # vérification pour dire à quoi sert une clé.
    assert not identity_reads(ast.parse("# auth.login / verify_auth_cookie"))
    assert not identity_reads(ast.parse("resolve_identity(request, self._bretzel)"))
    assert not identity_reads(ast.parse("auth.user_id(request)"))
    assert not identity_reads(ast.parse("key = config._auth_key"))
    assert not identity_reads(ast.parse("COOKIE_AUTHORITY = 1"))
