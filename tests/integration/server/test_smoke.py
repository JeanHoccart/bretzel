"""End-to-end smoke tests — boot a Bretzel app, hit it via TestClient.

These cover the request lifecycle most likely to break first :
constructor → startup → page render → action POST → static asset.
Anything finer-grained is unit-tested in ``tests/unit/server/``.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from bretzel import Bretzel, page, ui


_SECRET = "x" * 32


# ───────────────────────────────────────────────────────────────────────────
# Module-level handlers — addressable via ``module::qualname``
# ───────────────────────────────────────────────────────────────────────────


# The action handler we'll target via /_bretzel/action.
_call_log: list[dict[str, object]] = []


def smoke_action(message: str = "") -> None:
    _call_log.append({"message": message})


# ───────────────────────────────────────────────────────────────────────────
# Construction / readiness
# ───────────────────────────────────────────────────────────────────────────


class TestConstruction:
    def test_secret_key_required(self) -> None:
        import pytest

        with pytest.raises(Exception):
            Bretzel()  # no secret_key, no env override → ConfigError

    def test_basic_app_starts(self) -> None:
        app = Bretzel(secret_key=_SECRET, mode="dev")
        with TestClient(app) as _:
            # TestClient enters lifespan → bretzel_startup completes.
            assert app.is_ready is True

    def test_shutdown_clears_ready(self) -> None:
        app = Bretzel(secret_key=_SECRET, mode="dev")
        with TestClient(app):
            pass
        # Lifespan exited → not ready any more.
        assert app.is_ready is False


# ───────────────────────────────────────────────────────────────────────────
# Static assets
# ───────────────────────────────────────────────────────────────────────────


class TestStatic:
    def test_runtime_js_served(self) -> None:
        app = Bretzel(secret_key=_SECRET, mode="dev")
        with TestClient(app) as client:
            response = client.get("/_bretzel/runtime.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]
        assert "$bz" in response.text  # the runtime.js bundle exposes $bz

    def test_theme_css_served(self) -> None:
        app = Bretzel(secret_key=_SECRET, mode="dev")
        with TestClient(app) as client:
            response = client.get("/_bretzel/theme.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]
        # Theme.generate_css emits at least the @theme block.
        assert "@theme" in response.text

    def test_theme_css_safelists_component_color_shapes(self) -> None:
        # Preuve bout-en-bout du câblage : le theme.css SERVI (celui que
        # le compilateur de prod ingère) porte les classes couleur que
        # seuls les thèmes composants connaissent. Sans l'injection des
        # gabarits par ``_resolve_theme``, la safelist retombe sur son
        # plancher et ces classes disparaissent du style.css compilé —
        # invisible en dev, où le compilateur navigateur scanne le DOM.
        app = Bretzel(secret_key=_SECRET, mode="dev")
        with TestClient(app) as client:
            css = client.get("/_bretzel/theme.css").text
        # ⚠️ **Le sujet de ce test a changé le 2026-08-30** — phase 3 du
        # chantier des jetons de couleur. Il vérifiait que la CLÔTURE
        # couleur (chaque forme × chaque couleur) était servie dans la
        # safelist ; cette clôture n'existe plus. Les thèmes écrivent des
        # PALIERS — ``ring-(--bz-focus)`` — qui sont des classes complètes
        # que le compilateur voit dans le source. Rien à clôturer.
        #
        # Ce qui doit être servi maintenant, et qui a la même valeur : les
        # RÈGLES DE PONT, sans lesquelles aucun palier n'a de valeur et
        # tout composant coloré rendrait nu.
        for rule in (".bz-c-primary", ".bz-c-error", ".bz-c-current"):
            assert rule in css, (
                f"{rule!r} absent du CSS servi — les paliers de cette "
                "couleur seraient indéfinis, donc toute déclaration qui "
                "les lit serait invalide : le composant rendrait SANS "
                "style, sans erreur et sans trace."
            )
        assert "--bz-bg:" in css and "--bz-solid:" in css, (
            "les paliers ne sont pas déclarés dans le CSS servi."
        )

    def test_style_css_placeholder(self) -> None:
        # Phase 1 ships a placeholder until ``bretzel build`` is wired.
        app = Bretzel(secret_key=_SECRET, mode="dev")
        with TestClient(app) as client:
            response = client.get("/_bretzel/style.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]


# ───────────────────────────────────────────────────────────────────────────
# Page render
# ───────────────────────────────────────────────────────────────────────────


def _build_app_with_page() -> Bretzel:
    app = Bretzel(secret_key=_SECRET, mode="dev")

    @page("/")
    def home() -> None:
        ui.text("Hello, world.", size="xl")

    app.include(home)
    return app


class TestPages:
    def test_home_returns_html(self) -> None:
        app = _build_app_with_page()
        with TestClient(app) as client:
            response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "<!doctype html>" in response.text
        assert ">Hello, world.<" in response.text

    def test_session_cookie_minted(self) -> None:
        app = _build_app_with_page()
        with TestClient(app) as client:
            response = client.get("/")
        assert "Bretzel_session" in response.cookies

    def test_envelope_tag_present(self) -> None:
        app = _build_app_with_page()
        with TestClient(app) as client:
            response = client.get("/")
        assert "<bz-envelope>" in response.text


# ───────────────────────────────────────────────────────────────────────────
# Action POST — HMAC verify + handler invocation
# ───────────────────────────────────────────────────────────────────────────


class TestActions:
    def test_signed_action_invokes_handler(self) -> None:
        from bretzel.server.handlers import encode_action_id, sign_action

        app = Bretzel(secret_key=_SECRET, mode="dev")
        action_id = encode_action_id(smoke_action)
        signature = sign_action(app.config._action_key, action_id, "")

        _call_log.clear()
        with TestClient(app) as client:
            # V3 wire : sig in the X-Bz-Sig header (the bridge forwards
            # it from data-bz-sig), _args as a regular form field.
            response = client.post(
                f"/_bretzel/action/{action_id}",
                headers={"X-Bz-Sig": signature},
                data={"_args": "", "message": "hi from the wire"},
            )
        # 204 because the handler queued no refreshable + no client state.
        assert response.status_code == 204
        assert _call_log == [{"message": "hi from the wire"}]

    def test_unsigned_action_rejected(self) -> None:
        from bretzel.server.handlers import encode_action_id

        app = Bretzel(secret_key=_SECRET, mode="dev")
        action_id = encode_action_id(smoke_action)

        _call_log.clear()
        with TestClient(app) as client:
            response = client.post(f"/_bretzel/action/{action_id}")
        assert response.status_code == 403
        assert _call_log == []

    def test_tampered_signature_rejected(self) -> None:
        from bretzel.server.handlers import encode_action_id

        app = Bretzel(secret_key=_SECRET, mode="dev")
        action_id = encode_action_id(smoke_action)

        _call_log.clear()
        with TestClient(app) as client:
            response = client.post(
                f"/_bretzel/action/{action_id}",
                headers={"X-Bz-Sig": "badbadbadbadbadbad"},
                data={"_args": ""},
            )
        assert response.status_code == 403
        assert _call_log == []

    def test_unknown_action_id_404(self) -> None:
        from bretzel.server.handlers import sign_action

        app = Bretzel(secret_key=_SECRET, mode="dev")
        # Sign correctly, but the resolved id won't exist.
        bogus = "does.not.exist::nope"
        signature = sign_action(app.config._action_key, bogus, "")
        with TestClient(app) as client:
            response = client.post(
                f"/_bretzel/action/{bogus}",
                headers={"X-Bz-Sig": signature},
                data={"_args": ""},
            )
        assert response.status_code == 404


# ───────────────────────────────────────────────────────────────────────────
# Sanity — Bretzel implements the BretzelApp Protocol
# ───────────────────────────────────────────────────────────────────────────


def test_satisfies_bretzelapp_protocol() -> None:
    from bretzel.render.types import BretzelApp

    app = Bretzel(secret_key=_SECRET, mode="dev")
    # ``runtime_checkable`` Protocol → structural conformance check.
    assert isinstance(app, BretzelApp)
