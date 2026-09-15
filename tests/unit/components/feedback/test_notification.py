"""Unit tests for the toast helper.

There's no Python ``NotificationContainer`` — V1 idiom. The runtime
owns the visible DOM and auto-mounts it on first ``$bz.notification
.show(...)`` call. Python only ships :

- :func:`notification` — the server-side fire-and-forget helper
  (exported as ``ui.notification``)
- :func:`serialise_pending` — turns the request's queued payloads
  into the OOB-swap fragment the partial response carries back
"""

from __future__ import annotations

import json

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.feedback.notification import (
    notification,
    serialise_pending,
)
from bretzel.render.context import current_context, maybe_current_context


class TestNotificationHelper:
    def test_no_op_outside_render_context(self) -> None:
        # Spec : out-of-context calls degrade gracefully (mirrors how
        # the free ``refresh()`` behaves).
        assert maybe_current_context() is None
        notification("orphan", variant="info")

    def test_appends_to_context_queue(self) -> None:
        with render_isolated():
            notification("hello", variant="success")
            ctx = current_context()
            assert len(ctx.notifications) == 1
            assert ctx.notifications[0]["message"] == "hello"
            assert ctx.notifications[0]["variant"] == "success"

    def test_default_options(self) -> None:
        with render_isolated():
            notification("default")
            opts = current_context().notifications[0]
        assert opts["variant"] == "info"
        assert opts["duration_ms"] == 4000
        assert opts["position"] == "top-right"
        assert opts["dismissible"] is True
        assert "title" not in opts
        assert "icon" not in opts

    def test_full_options(self) -> None:
        with render_isolated():
            notification(
                "full",
                variant="warning",
                title="Heads up",
                duration_ms=8000,
                position="bottom-left",
                dismissible=False,
                icon="bell",
            )
            opts = current_context().notifications[0]
        assert opts["title"] == "Heads up"
        assert opts["duration_ms"] == 8000
        assert opts["position"] == "bottom-left"
        assert opts["dismissible"] is False
        assert opts["icon"] == "bell"

    def test_unknown_variant_raises(self) -> None:
        # API is strict — only the 4 semantic variants defined in
        # notification/theme.py are accepted. A typo surfaces
        # immediately rather than silently rendering a neutral toast.
        with render_isolated(), pytest.raises(
            ValueError, match="Unknown notification variant"
        ):
            notification("oops", variant="primary")

    def test_icon_false_opts_out(self) -> None:
        # ``icon=False`` is the explicit opt-out — the runtime
        # serialises it as an empty string so ``normalise`` on the
        # client side picks the "no icon" branch.
        with render_isolated():
            notification("clean", variant="info", icon=False)
            opts = current_context().notifications[0]
        assert opts["icon"] == ""


class TestSerialisePending:
    def test_empty_queue_returns_empty_string(self) -> None:
        assert serialise_pending([]) == ""

    def test_emits_a_single_bz_patch_tag(self) -> None:
        # V3 : the toast queue rides a single <bz-patch> with the
        # reserved ``_notifications`` key (the bridge forwards each to
        # $bz.notify → the toaster's bz:notify subscription).
        out = serialise_pending([
            {"message": "one", "variant": "info"},
            {"message": "two", "variant": "success"},
        ])
        assert out.count("<bz-patch>") == 1
        assert out.count("</bz-patch>") == 1

    def test_payload_carries_all_toasts_under_notifications_key(self) -> None:
        out = serialise_pending([
            {"message": "hi", "variant": "success"},
            {"message": "bye"},
        ])
        body = out[len("<bz-patch>"):-len("</bz-patch>")]
        payload = json.loads(body.replace("<\\/", "</"))
        assert payload["patches"]["_notifications"] == [
            {"message": "hi", "variant": "success"},
            {"message": "bye"},
        ]

    def test_no_legacy_script_outbox(self) -> None:
        # The V2 #bz-script-outbox inline-<script> injection is gone.
        out = serialise_pending([{"message": "x"}])
        assert "bz-script-outbox" not in out
        assert "<script>" not in out


class TestShellInjection:
    """The shell injects ``window.$bz_theme`` with the notification
    theme so the runtime JS can read class strings from a single
    Python source of truth."""

    def test_theme_injected_into_shell(self) -> None:
        from fastapi.testclient import TestClient

        from bretzel import Bretzel, page

        app = Bretzel(secret_key="x" * 32, mode="dev")

        @page("/_test_shell")
        def shell_page() -> None:
            from bretzel import ui
            ui.text("hello")

        app.include(shell_page)
        with TestClient(app) as client:
            body = client.get("/_test_shell").text

        assert "window.$bz_theme" in body
        # The 4 semantic variants + chrome live in the payload.
        assert '"variants"' in body
        assert '"info"' in body
        assert '"success"' in body
        assert '"warning"' in body
        assert '"error"' in body
