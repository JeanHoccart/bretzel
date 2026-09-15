"""Gate : ``mode`` est un préréglage, pas un levier universel.

Ce qui était cassé
------------------

Un booléen unique, ``debug``, gouvernait sept concerns : sécurité des
cookies, exposition des erreurs, verbosité, pipeline CSS, en-têtes de
cache, cache-bust, lisibilité des IDs. Il était nommé d'après le moins
critique des sept — et ne pilotait, ironie, aucun log (le niveau de log
est un paramètre séparé de ``app.run()``).

Le coût réel a été un bug de session en production (cf.
``test_cookie_secure_follows_transport``) : impossible de rendre les
cookies utilisables sans allumer aussi la fuite des stack traces.

Le modèle maintenant : ``mode`` pose les DÉFAUTS d'axes indépendants,
chacun surchargeable seul. Deux combinaisons impossibles avant deviennent
naturelles — une prod bavarde qui n'expose rien, et un dev qui rend les
vraies pages d'erreur.

L'axe assets / cache (``is_dev``) est vérifié séparément par la gate
d'invariance de rendu entre modes.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import bretzel.server as _server_pkg
from bretzel import Bretzel, page
from bretzel.server.config import BretzelConfig
from bretzel.server.errors import BretzelError
from tests.consistency._discovery import parsed_sources

_SECRET = "k" * 32
_SERVER_DIR = Path(_server_pkg.__file__).parent
#: 31 fichiers sous ``bretzel/server`` le 2026-08-19 ; le plancher laisse
#: de la marge pour une réorganisation sans laisser passer un balayage mort.
_SERVER_FLOOR = 20


def _config(**kw: object) -> BretzelConfig:
    return BretzelConfig.from_kwargs(secret_key=_SECRET, **kw)


@pytest.mark.parametrize(
    ("mode", "debug", "expose"),
    [("dev", True, True), ("prod", False, False)],
)
def test_preset_sets_the_defaults(mode: str, debug: bool, expose: bool) -> None:
    cfg = _config(mode=mode)
    assert cfg.mode == mode
    assert cfg.is_dev is (mode == "dev")
    assert cfg.debug is debug
    assert cfg.expose_errors is expose


def test_each_axis_overrides_alone() -> None:
    # Prod bavarde mais fermée — diagnostics sans exposition.
    cfg = _config(mode="prod", debug=True)
    assert (cfg.debug, cfg.expose_errors, cfg.is_dev) == (True, False, False)

    # Dev qui rend les vraies pages d'erreur.
    cfg = _config(mode="dev", expose_errors=False)
    assert (cfg.debug, cfg.expose_errors, cfg.is_dev) == (True, False, True)

    # Le préréglage ne touche jamais au transport.
    assert _config(mode="dev").secure_cookies is None
    assert _config(mode="prod").secure_cookies is None


@pytest.mark.parametrize(
    ("kwargs", "fuite_attendue"),
    [
        ({"mode": "prod"}, False),
        ({"mode": "dev"}, True),
        ({"mode": "prod", "debug": True}, False),   # bavard ≠ exposé
        ({"mode": "dev", "expose_errors": False}, False),
    ],
)
def test_only_expose_errors_decides_what_leaks(
    kwargs: dict[str, object], fuite_attendue: bool
) -> None:
    @page("/boom")
    def boom() -> None:
        raise BretzelError("secret-interne-42")

    app = Bretzel(secret_key=_SECRET, **kwargs)  # type: ignore[arg-type]
    app.include(boom)
    with TestClient(app, raise_server_exceptions=False) as client:
        body = client.get("/boom").text
    assert ("secret-interne-42" in body) is fuite_attendue


def _detail_gated_on_debug(tree: ast.AST) -> list[int]:
    """``detail = ... if debug else ...`` — l'exposition re-branchée sur
    la verbosité. Sur l'AST : la prose des docstrings cite le motif."""
    found: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.IfExp):
            continue
        names = {n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)}
        if "debug" in names:
            found.append(node.lineno)
    return found


def test_error_exposure_is_not_derived_from_debug() -> None:
    offenders = [
        f"{source.path.relative_to(_SERVER_DIR)}:{line}"
        for source in parsed_sources(_SERVER_DIR, floor=_SERVER_FLOOR)
        for line in _detail_gated_on_debug(source.tree)
    ]
    assert not offenders, (
        f"L'exposition des erreurs est de nouveau branchée sur ``debug`` en "
        f"{offenders}. Ce sont deux axes : on doit pouvoir être bavard sans "
        "rien exposer, et discret tout en rendant les vraies pages d'erreur."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : une exposition d'erreur rebranchée sur ``debug`` est vue.

    Ce sont deux axes : on doit pouvoir être bavard sans rien exposer, et
    discret tout en rendant les vraies pages d'erreur. Si le détecteur
    cessait de reconnaître le ternaire, l'interdiction passerait sur les
    31 fichiers du serveur sans rien regarder.
    """
    fautif = ast.parse("detail = str(exc) if debug else None")
    assert _detail_gated_on_debug(fautif), "le ternaire sur ``debug`` devrait mordre"

    licite = ast.parse("detail = str(exc) if expose_errors else None")
    assert not _detail_gated_on_debug(licite), (
        "un ternaire sur ``expose_errors`` est le bon axe — faux positif"
    )
