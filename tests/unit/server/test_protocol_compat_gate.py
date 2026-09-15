"""Le serveur refuse un client de major de protocole différent.

Le bridge envoie ``X-Bretzel-Protocol`` sur chaque POST d'action depuis
toujours, et ``check_compat`` existait avec ses tests — mais **personne ne
lisait le header** (mesuré 2026-08-01 : zéro appelant hors des tests, et
``HEADER_PROTOCOL`` jamais lu côté serveur). Le cas réel : après un
déploiement, un onglet resté ouvert garde son ``runtime.js`` en cache et
POSTe vers un serveur de major différent — ça cassait sans message.

⚠️ Ce contrôle sert la **lisibilité**, pas la sûreté : un header absent
tombe dans le chemin HMAC, qui est la vraie barrière. Ces tests fixent les
deux sens pour qu'on ne le confonde pas avec une protection.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from bretzel import Bretzel, page, ui
from bretzel.runtime.protocol import (
    HEADER_PROTOCOL,
    PROTOCOL_VERSION,
    ROUTE_ACTION,
)

_SECRET = "y" * 24
_URL = f"{ROUTE_ACTION}/whatever"


def _client() -> TestClient:
    app = Bretzel(title="t", secret_key=_SECRET)

    @page("/")
    def home() -> None:
        ui.text("hi")

    app.include(home)
    return TestClient(app)


class TestProtocolCompatGate:
    def test_mismatched_major_is_409(self) -> None:
        with _client() as client:
            resp = client.post(_URL, headers={HEADER_PROTOCOL: "v99.0"})
        assert resp.status_code == 409
        assert "reload" in resp.text

    def test_same_major_falls_through_to_hmac(self) -> None:
        """Un client compatible n'est PAS arrêté ici.

        Il continue vers la vérification de signature — donc 403 (pas de
        `X-Bz-Sig`), et surtout pas 409.
        """
        with _client() as client:
            resp = client.post(_URL, headers={HEADER_PROTOCOL: PROTOCOL_VERSION})
        assert resp.status_code != 409

    def test_absent_header_falls_through_to_hmac(self) -> None:
        """Le pendant négatif, et le plus important.

        Sans lui, on pourrait durcir le contrôle en refusant l'absence de
        header et croire avoir gagné en sécurité — alors qu'on aurait juste
        cassé tout client legacy, la sûreté étant déjà assurée par le HMAC.
        """
        with _client() as client:
            resp = client.post(_URL)
        assert resp.status_code != 409
