"""Unit tests for ``bretzel.server.errors``."""

from __future__ import annotations

import pytest
from starlette.exceptions import HTTPException

from bretzel.server.errors import (
    AuthRequiredError,
    BretzelError,
    abort,
    default_error_page,
)

# ───────────────────────────────────────────────────────────────────────────
# Error types
# ───────────────────────────────────────────────────────────────────────────


class TestErrorTypes:
    def test_bretzel_error_is_runtime_error(self) -> None:
        assert issubclass(BretzelError, RuntimeError)

    def test_auth_required_is_the_class_the_state_layer_raises(self) -> None:
        """Le ré-export serveur EST la classe levée par ``state/registry``.

        Ces trois tests affirmaient l'inverse jusqu'au 2026-08-15 : ils
        vérifiaient qu'``AuthRequiredError`` était une ``HTTPException``
        de statut 401 — ce qui était vrai, et sans effet, parce que cette
        classe-là n'était **jamais levée**. Ils passaient au vert sur un
        homonyme mort pendant qu'un ``except AuthRequiredError``
        utilisateur n'attrapait rien.
        """
        from bretzel.core.errors import AuthRequiredError as Core
        from bretzel.state.registry import AuthRequiredError as FromState

        assert AuthRequiredError is Core is FromState

    def test_auth_required_is_not_a_bretzel_error(self) -> None:
        """401 ≠ 500 : le dispatcher route les deux différemment.

        Un ``except BretzelError`` signifie « bug du framework → 500 ». Un
        visiteur anonyme sur un ``UserState`` n'est pas un bug.
        """
        assert not issubclass(AuthRequiredError, BretzelError)

    def test_auth_required_carries_no_http_dependency(self) -> None:
        """Elle vit en Layer 0, que ``state`` importe — donc sans Starlette."""
        assert not issubclass(AuthRequiredError, HTTPException)
        assert issubclass(AuthRequiredError, RuntimeError)


# ───────────────────────────────────────────────────────────────────────────
# abort
# ───────────────────────────────────────────────────────────────────────────


class TestAbort:
    def test_raises_http_exception(self) -> None:
        with pytest.raises(HTTPException) as exc:
            abort(404, "not here")
        assert exc.value.status_code == 404
        assert exc.value.detail == "not here"

    def test_default_detail_empty(self) -> None:
        with pytest.raises(HTTPException) as exc:
            abort(403)
        assert exc.value.detail == ""


# ───────────────────────────────────────────────────────────────────────────
# default_error_page — minimal HTML5
# ───────────────────────────────────────────────────────────────────────────


class TestDefaultErrorPage:
    def test_status_in_title(self) -> None:
        page = default_error_page(404)
        assert "<title>404" in page
        assert "Page not found" in page

    def test_doctype_present(self) -> None:
        page = default_error_page(500)
        assert page.startswith("<!doctype html>")

    def test_self_contained_styles(self) -> None:
        # No external CSS — page must work even when theme.css 404s.
        page = default_error_page(500)
        assert "<style>" in page
        # No <link> to external stylesheets.
        assert 'rel="stylesheet"' not in page

    def test_known_status_messages(self) -> None:
        for status, expected in (
            (400, "Bad request"),
            (401, "Authentication required"),
            (403, "Forbidden"),
            (404, "Page not found"),
            (500, "Server error"),
        ):
            assert expected in default_error_page(status)

    def test_unknown_status_falls_back(self) -> None:
        page = default_error_page(418)
        # Generic title for unmapped statuses.
        assert "<title>418" in page
        assert "Error" in page

    def test_custom_message_overrides(self) -> None:
        page = default_error_page(500, message="Custom blurb here")
        assert "Custom blurb here" in page

    def test_custom_title_overrides(self) -> None:
        page = default_error_page(404, title="Nope")
        assert "<title>404 — Nope</title>" in page

    def test_back_to_home_link(self) -> None:
        page = default_error_page(404)
        assert 'href="/"' in page
