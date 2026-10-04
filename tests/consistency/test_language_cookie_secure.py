"""Le cookie de langue est ``Secure`` sur https, comme les autres.

``Language.set`` posait ``bz_lang`` sans ``secure=`` : le seul cookie
que le serveur émet sans durcissement sur https, pendant que session et
auth suivaient le transport. Même règle ici — ``resolve_cookie_secure``,
avec le même override ``secure_cookies=`` derrière un proxy qui termine
TLS — vérifiée de bout en bout sur l'en-tête ``Set-Cookie``.

``Language.set`` appelle ``reload()``, qui refuse la requête sans
``HX-Request: true`` : sans cet en-tête, le cookie n'atteint jamais la
réponse et le test ne mesurerait rien.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, page, ui
from bretzel.render.lang import Language
from bretzel.runtime.protocol import LANG_COOKIE

_SECRET = "k" * 32
_HX = {"HX-Request": "true"}


def _cookie_lang(base_url: str, **kwargs: bool) -> str:
    """L'en-tête ``Set-Cookie`` de ``bz_lang``, après un ``Language.set``."""

    @page("/")
    def home() -> None:
        Language.set("fr")
        ui.text("x")

    app = Bretzel(
        secret_key=_SECRET, languages=["en", "fr"], **kwargs
    )
    app.include(home)

    with TestClient(app, base_url=base_url) as client:
        response = client.get("/", headers=_HX)
    for cookie in response.headers.get_list("set-cookie"):
        if cookie.startswith(f"{LANG_COOKIE}="):
            return cookie
    raise AssertionError(f"aucun Set-Cookie {LANG_COOKIE} dans la réponse")


@pytest.mark.parametrize(
    ("base_url", "attendu"),
    [
        ("https://app.example.com", True),
        ("http://tool.interne.lan", False),
    ],
)
def test_la_lang_suit_le_transport(base_url: str, attendu: bool) -> None:
    assert ("Secure" in _cookie_lang(base_url)) is attendu


def test_l_override_prime() -> None:
    # Proxy qui termine TLS sans réécrire scope["scheme"] : l'app voit http,
    # et c'est l'override qui décide.
    assert "Secure" in _cookie_lang("http://app.example.com", secure_cookies=True)
