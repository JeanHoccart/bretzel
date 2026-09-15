"""Unit tests for :class:`bretzel.components.feedback.banner.Banner`."""

from __future__ import annotations

from functools import partial

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.feedback.banner import Banner
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding


def _on_close() -> None: ...


class TestStructure:
    def test_renders_root_status(self) -> None:
        with render_isolated():
            out = serialize(Banner("Test message").render())
        assert 'role="status"' in out

    def test_message_text_visible(self) -> None:
        with render_isolated():
            out = serialize(Banner("Trial expires soon").render())
        assert "Trial expires soon" in out

    def test_title_renders_in_bold_span(self) -> None:
        with render_isolated():
            out = serialize(
                Banner("Try it now", title="What's new").render()
            )
        assert "What" in out
        assert "Try it now" in out

    def test_full_width_layout(self) -> None:
        """Banner spans edge-to-edge — ``w-full`` on the root, plus
        the coloured left bar that's the semantic accent."""
        with render_isolated():
            out = serialize(Banner("msg").render())
        assert "w-full" in out
        # border-l-(length:--bz-stroke-accent) carries the coloured accent.
        assert "border-l-(length:--bz-stroke-accent)" in out


class TestAutoIcons:
    @pytest.mark.parametrize(
        ("color", "icon"),
        [
            ("info", "lucide:info"),
            ("success", "lucide:check-circle-2"),
            ("warning", "lucide:alert-triangle"),
            ("error", "lucide:octagon-alert"),
        ],
    )
    def test_semantic_color_auto_icon(
        self, color: str, icon: str,
    ) -> None:
        with render_isolated():
            out = serialize(Banner("msg", color=color).render())
        assert icon in out

    def test_non_semantic_color_no_auto_icon(self) -> None:
        """Neutral colors (``muted`` / ``primary``) ship no auto-icon
        — the caller passes one explicitly if they want."""
        with render_isolated():
            out = serialize(Banner("msg", color="muted").render())
        assert "lucide:info" not in out
        assert "lucide:check-circle-2" not in out

    def test_explicit_icon_overrides_auto(self) -> None:
        """When the user passes ``icon=``, the auto-pick is
        skipped — only the explicit one renders."""
        with render_isolated():
            out = serialize(
                Banner("msg", color="info", icon="zap").render()
            )
        assert "lucide:zap" in out
        # Auto-icon for info is ``info`` — must NOT also render.
        assert "lucide:info" not in out


class TestVariants:
    @pytest.mark.parametrize(
        ("color", "marker"),
        [
            ("info", "border-info"),
            ("success", "border-success"),
            ("warning", "border-warning"),
            ("error", "border-error"),
            ("muted", "border-text/30"),
            ("primary", "border-primary"),
        ],
    )
    def test_variant_border(self, color: str, marker: str) -> None:
        with render_isolated():
            out = serialize(Banner("X", color=color).render())
        assert marker in out


class TestSizes:
    @pytest.mark.parametrize(
        ("size", "marker"),
        [("sm", "py-2"), ("md", "py-3"), ("lg", "py-4")],
    )
    def test_size_padding(self, size: str, marker: str) -> None:
        with render_isolated():
            out = serialize(Banner("X", size=size).render())
        assert marker in out


class TestDismissible:
    def test_no_close_button_without_dismissible(self) -> None:
        with render_isolated():
            out = serialize(Banner("X").render())
        assert 'aria-label="Dismiss"' not in out

    def test_dismissible_emits_close_button(self) -> None:
        with render_isolated():
            out = serialize(
                Banner("X", dismissible=True).render()
            )
        assert 'aria-label="Dismiss"' in out

    def test_dismissible_wires_local_open_state(self) -> None:
        """Dismissible Banner manages a local ``bz-data`` ``open``
        flag so the close button can flip it to false without a
        round-trip."""
        with render_isolated():
            out = serialize(
                Banner("X", dismissible=True).render()
            )
        # Local bz-data scope with open: true.
        assert "bz-data=" in out
        assert "open: true" in out
        # Root has bz-show=open so the dismiss hides the banner.
        assert 'bz-show="open"' in out

    def test_close_handler_wires_root_listener(self) -> None:
        """Server-side ``on_close`` (callable) fires after the
        client-side close — V3 wiring : the root carries
        ``hx-trigger="close"`` + ``hx-post``, and the × button's
        ``$dispatch('close')`` bubbles up to it."""
        with render_isolated():
            out = serialize(
                Banner(
                    "X",
                    dismissible=True,
                    on_close=_on_close,
                ).render()
            )
        # Server wiring stays on the root (single hx-post host).
        assert 'hx-trigger="close"' in out
        assert 'hx-post="/_bretzel/action/' in out
        # The × button dispatches the bubbling close CustomEvent.
        button_block = out[out.index("<button"):out.index("</button>")]
        assert "$dispatch('close')" in button_block


class TestActionSlot:
    def test_with_body_renders_actions_row(self) -> None:
        from bretzel.components.actions.button import Button

        with render_isolated():
            b = Banner("Try it")
            with b:
                Button("Open")
            out = serialize(b.render())
        assert "Open" in out
        # Actions row class — ``ms-`` (logique) depuis le 2026-09-02.
        assert "ms-auto" in out

    def test_no_body_no_actions_row(self) -> None:
        with render_isolated():
            out = serialize(Banner("Just info").render())
        # No empty actions wrapper.
        assert "ms-auto" not in out


class TestReactiveText:
    def test_binding_title_emits_bz_text(self) -> None:
        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="title", value="Heads up",
        )
        with render_isolated():
            out = serialize(Banner("body", title=binding).render())
        assert "$bz.state.UI.default.title" in out

    def test_binding_message_emits_bz_text(self) -> None:
        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="msg", value="hello",
        )
        with render_isolated():
            out = serialize(Banner(binding).render())
        assert "$bz.state.UI.default.msg" in out


class TestBindableSurface:
    def test_bindable_props(self) -> None:
        # dismissible coupé 2026-07-16 (règle « driver client, sinon
        # serveur » : ∅). Seuls les slots de texte live restent bindables.
        assert set(Banner.BINDABLE_PROPS) == {"title", "message"}

    def test_events(self) -> None:
        assert Banner.EVENTS == ("close",)

    def test_is_container(self) -> None:
        assert Banner.IS_CONTAINER is True
