"""Ce que les en-têtes de sécurité font, vu du client.

Trois choses qui ne se lisent pas dans le code : que les en-têtes
ennuyeux soient un DÉFAUT (donc présents sans rien demander), qu'ils
couvrent aussi les réponses que les couches basses produisent seules (un
403 CSRF n'est pas rendu par une page), et qu'une faute de frappe dans
``csp_sources`` rougisse au démarrage plutôt qu'en silence dans un
navigateur.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, ui
from bretzel.server.config import ConfigError
from bretzel.server.security import BORING_HEADERS

_SECRET = "x" * 32


def _app(**kwargs) -> Bretzel:
    app = Bretzel(secret_key=_SECRET, mode="dev", **kwargs)

    @page("/")
    def home() -> None:
        ui.text("ok")

    app.include(home)
    return app


def test_the_boring_headers_are_a_default() -> None:
    """Sans rien demander. C'est toute la différence avec la CSP."""
    with TestClient(_app()) as client:
        reponse = client.get("/")
    for nom, valeur in BORING_HEADERS.items():
        assert reponse.headers[nom] == valeur


def test_no_policy_without_asking_for_one() -> None:
    """Le pendant : la CSP n'est PAS un défaut.

    Bretzel ne peut pas deviner les polices, CDN et iframes de l'app ;
    l'activer d'office casserait une app sur deux au premier déploiement.
    """
    with TestClient(_app()) as client:
        reponse = client.get("/")
    assert "content-security-policy" not in reponse.headers
    assert "content-security-policy-report-only" not in reponse.headers


def test_they_cover_a_response_no_page_rendered() -> None:
    """Un 404 n'est pas rendu par une page — il doit être couvert aussi.

    C'est la raison pour laquelle le middleware est le plus externe de la
    pile framework. Posé plus bas, il ne verrait que les pages.
    """
    with TestClient(_app(csp=True)) as client:
        reponse = client.get("/nexiste-pas")
    assert reponse.status_code == 404
    assert reponse.headers["X-Content-Type-Options"] == "nosniff"
    assert "content-security-policy" in reponse.headers


def test_report_only_uses_its_own_header() -> None:
    """Le premier barreau ne doit RIEN bloquer.

    Se tromper d'en-tête ici serait le pire des bugs de cette
    fonctionnalité : le dev croirait observer et bloquerait en vrai.
    """
    with TestClient(_app(csp="report-only")) as client:
        reponse = client.get("/")
    assert "content-security-policy-report-only" in reponse.headers
    assert "content-security-policy" not in reponse.headers


def test_an_app_can_widen_the_policy() -> None:
    with TestClient(
        _app(csp=True, csp_sources={"img-src": ["https://cdn.exemple.test"]})
    ) as client:
        politique = client.get("/").headers["content-security-policy"]
    img = next(d for d in politique.split("; ") if d.startswith("img-src "))
    assert "https://cdn.exemple.test" in img
    # Élargir, pas remplacer : ce que le framework posait est toujours là.
    assert "'self'" in img and "data:" in img


def test_the_app_cannot_turn_the_headers_off_by_accident() -> None:
    """``security_headers=False`` est explicite, et c'est le seul chemin."""
    with TestClient(_app(security_headers=False)) as client:
        reponse = client.get("/")
    assert "X-Content-Type-Options" not in reponse.headers


def test_a_typo_in_a_directive_is_refused_at_boot() -> None:
    """Une directive mal orthographiée ne fait RIEN dans un navigateur.

    La ressource est bloquée, sans message ailleurs que dans la console —
    exactement le mode d'échec que ce dépôt refuse de laisser passer.
    """
    with pytest.raises(ConfigError, match="directive inconnue"):
        _app(csp=True, csp_sources={"img_src": ["https://x.test"]})


def test_sources_without_a_mode_are_refused() -> None:
    """Sinon les sources ne seraient posées nulle part, en silence."""
    with pytest.raises(ConfigError, match="csp_sources"):
        _app(csp_sources={"img-src": ["https://x.test"]})


def test_an_unknown_mode_is_refused() -> None:
    """``csp="report"`` serait vrai au sens booléen — donc BLOQUANT."""
    with pytest.raises(ConfigError, match="report-only"):
        _app(csp="report")


def test_declaring_a_new_directive_never_narrows_it() -> None:
    """Le piège qui a mordu pour de vrai, le 2026-09-05.

    Une directive ABSENTE de la politique n'est pas permissive : elle
    retombe sur ``default-src``. La déclarer la sort de ce repli, donc
    ``csp_sources={"frame-src": ["data:"]}`` a bloqué une iframe
    MÊME-ORIGINE qui passait avant. Un ajout qui retire, et la seule
    trace était une ligne de console sur une page du playground.
    """
    with TestClient(
        _app(csp=True, csp_sources={"frame-src": ["data:"]})
    ) as client:
        politique = client.get("/").headers["content-security-policy"]
    frame = next(d for d in politique.split("; ") if d.startswith("frame-src "))
    assert "data:" in frame, "l'ajout demandé n'est pas là"
    assert "'self'" in frame, (
        "frame-src ne porte plus 'self' : déclarer la directive lui a "
        "fait perdre ce dont elle héritait de default-src. C'est un "
        "rétrécissement déguisé en ajout."
    )


def test_an_existing_directive_keeps_what_the_framework_put_there() -> None:
    """Le pendant, sur une directive que le socle porte déjà."""
    with TestClient(
        _app(csp=True, csp_sources={"connect-src": ["https://api.exemple.test"]})
    ) as client:
        politique = client.get("/").headers["content-security-policy"]
    connect = next(
        d for d in politique.split("; ") if d.startswith("connect-src ")
    )
    assert "https://api.exemple.test" in connect
    assert "https://api.iconify.design" in connect, (
        "les hôtes d'icônes ont sauté : les icônes disparaîtraient chez "
        "toute app qui étend connect-src."
    )
