"""Le transport HTTP d'une porte — ce qui arrive quand l'autre bout dit non.

Un endpoint OAuth qui REFUSE répond ``4xx`` **avec un corps JSON utile**
(``{"error": "invalid_grant"}``) : c'est le protocole, pas une panne.
``urllib.request.urlopen`` lève pourtant sur tout non-2xx — et jusqu'au
2026-08-24 cette exception traversait la porte, donc un visiteur dont le
code était refusé recevait une **500** au lieu de revenir sur la page de
connexion.

Trouvé en faussant volontairement le vérifieur PKCE contre un vrai
fournisseur local (``tests/probes/probe_oauth_door.py``) : la sonde ne
rougissait pas, elle **cassait** — le mode d'échec qui se lit comme une
panne d'outillage.

Ce fichier tient le niveau que la sonde ne peut pas atteindre : elle
passe par un vrai réseau, donc elle ne peut pas fabriquer un corps
illisible ni un hôte injoignable.
"""

from __future__ import annotations

import io
import urllib.error
import urllib.request

import pytest

from bretzel.server.oauth import OAuthError, _http_json

URL = "https://provider.test/token"


def raising(exc: Exception):
    def fake_urlopen(*args: object, **kwargs: object):
        raise exc

    return fake_urlopen


def test_a_4xx_with_a_json_body_is_a_refusal_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = urllib.error.HTTPError(
        URL, 400, "Bad Request", {}, io.BytesIO(b'{"error": "invalid_grant"}')
    )
    monkeypatch.setattr(urllib.request, "urlopen", raising(error))

    assert _http_json(URL, data={"code": "x"}) == {"error": "invalid_grant"}


def test_a_4xx_without_a_readable_body_refuses_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Unreadable(io.BytesIO):
        def read(self, *args: object) -> bytes:
            raise OSError("connexion coupée")

    error = urllib.error.HTTPError(URL, 500, "Boom", {}, Unreadable(b""))
    monkeypatch.setattr(urllib.request, "urlopen", raising(error))

    with pytest.raises(OAuthError, match="500"):
        _http_json(URL, data={"code": "x"})


def test_an_unreachable_provider_refuses_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        urllib.request, "urlopen", raising(urllib.error.URLError("nom inconnu"))
    )

    with pytest.raises(OAuthError, match="injoignable"):
        _http_json(URL)


def test_a_form_encoded_answer_is_still_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """GitHub rend du ``x-www-form-urlencoded`` quand ``Accept`` n'est pas
    honoré — le versant licite, pour que le rattrapage JSON reste utile."""

    class Resp(io.BytesIO):
        def __enter__(self) -> Resp:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *a, **k: Resp(b"access_token=at-1&token_type=bearer"),
    )

    assert _http_json(URL, data={"code": "x"})["access_token"] == "at-1"
