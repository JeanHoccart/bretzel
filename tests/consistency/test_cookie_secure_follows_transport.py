"""Gate : ``Secure`` sur les cookies suit le TRANSPORT, jamais le mode.

Le bug fermé ici
----------------

``secure=not debug`` liait la sécurité des cookies au mode de
l'application. Reproduit : un outil interne en ``mode="prod"`` derrière un
LAN sans TLS posait des cookies ``Secure`` que le navigateur ne renvoyait
jamais — session et auth mortes, sans erreur ni log. Le seul contournement
était ``mode="dev"``, qui exposait au passage les stack traces.

Invisible en local : les navigateurs traitent ``localhost`` et
``127.0.0.1`` comme des origines de confiance et y acceptent les cookies
``Secure``. Il fallait déployer sur un vrai nom d'hôte pour le voir.

Ces tests pinnent les deux moitiés : la fonction de résolution, et
l'absence de tout retour en arrière vers le mode.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import bretzel.server as _server_pkg
from bretzel import Bretzel, page, ui
from bretzel.server.auth import resolve_cookie_secure
from tests.consistency._discovery import parsed_sources

_SECRET = "k" * 32
_SERVER_DIR = Path(_server_pkg.__file__).parent
#: 31 fichiers sous ``bretzel/server`` le 2026-08-19 ; le plancher laisse
#: de la marge pour une réorganisation sans laisser passer un balayage mort.
_SERVER_FLOOR = 20


@pytest.mark.parametrize(
    ("scheme", "override", "attendu"),
    [
        ("https", None, True),    # transport sûr → durci
        ("http", None, False),    # transport clair → sinon session morte
        ("HTTPS", None, True),    # insensible à la casse
        ("", None, False),        # scheme inconnu → ne pas casser la session
        (None, None, False),
        ("http", True, True),     # forçage : proxy TLS non déclaré à uvicorn
        ("https", False, False),  # forçage inverse, tout aussi explicite
    ],
)
def test_resolution(scheme: str | None, override: bool | None, attendu: bool) -> None:
    assert resolve_cookie_secure(scheme, override) is attendu


def _secure_kwargs_referencing_the_mode(tree: ast.AST) -> list[int]:
    """Lignes où un ``secure=`` est calculé à partir du mode.

    Sur l'AST et pas sur le texte : ce fichier-ci, et le docstring de
    ``resolve_cookie_secure``, citent ``secure=not debug`` en prose pour
    expliquer le bug — un scan textuel se ferait piéger par sa propre
    documentation.
    """
    found: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "secure":
                continue
            names = {
                n.id for n in ast.walk(kw.value) if isinstance(n, ast.Name)
            } | {
                n.attr for n in ast.walk(kw.value) if isinstance(n, ast.Attribute)
            }
            if names & {"debug", "mode"}:
                found.append(node.lineno)
    return found


def test_no_site_derives_secure_from_the_mode() -> None:
    # La régression exacte à interdire : ré-accrocher ``secure`` au mode.
    offenders = [
        f"{source.path.relative_to(_SERVER_DIR)}:{line}"
        for source in parsed_sources(_SERVER_DIR, floor=_SERVER_FLOOR)
        for line in _secure_kwargs_referencing_the_mode(source.tree)
    ]
    assert not offenders, (
        f"``secure`` est de nouveau dérivé du mode en {offenders}. C'est une "
        "question de transport : un cookie Secure n'est pas renvoyé sur http, "
        "donc lier les deux casse la session de toute app déployée sans TLS."
    )


@pytest.mark.parametrize("mode", ["dev", "prod"])
@pytest.mark.parametrize(
    ("base_url", "secure_attendu"),
    [("http://tool.interne.lan", False), ("https://app.example.com", True)],
)
def test_session_survives_whatever_the_mode(
    mode: str, base_url: str, secure_attendu: bool
) -> None:
    # Bout-en-bout : le cookie est-il émis avec le bon attribut ET renvoyé
    # par le client à la requête suivante ? C'est le renvoi qui manquait.
    @page("/")
    def home() -> None:
        ui.text("x")

    app = Bretzel(secret_key=_SECRET, mode=mode)
    app.include(home)

    vu: list[str | None] = []

    @app.fastapi.middleware("http")
    async def spy(request, call_next):  # type: ignore[no-untyped-def]
        vu.append(request.headers.get("cookie"))
        return await call_next(request)

    with TestClient(app, base_url=base_url) as client:
        first = client.get("/")
        client.get("/")

    emis = first.headers.get_list("set-cookie")
    assert any("Secure" in c for c in emis) is secure_attendu
    assert vu[-1], (
        f"mode={mode} sur {base_url} : le cookie de session n'est pas revenu "
        "à la seconde requête — la session est perdue à chaque page."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : un ``secure=`` dérivé du mode est encore reconnu.

    C'est une question de TRANSPORT : un cookie Secure n'est pas renvoyé
    sur http, donc lier les deux casse la session de toute app déployée
    sans TLS. Si le détecteur cessait de matcher, l'interdiction
    passerait sur les 31 fichiers du serveur sans rien regarder.
    """
    fautif = ast.parse("resp.set_cookie(k, v, secure=(config.mode == 'prod'))")
    assert _secure_kwargs_referencing_the_mode(fautif), (
        "un ``secure=`` dérivé du mode devrait mordre"
    )

    licite = ast.parse("resp.set_cookie(k, v, secure=resolve_cookie_secure(url))")
    assert not _secure_kwargs_referencing_the_mode(licite), (
        "la résolution par le transport est la bonne forme — faux positif"
    )
