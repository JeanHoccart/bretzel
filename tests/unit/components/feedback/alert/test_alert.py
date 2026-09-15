"""Unit tests for :class:`bretzel.components.feedback.alert.Alert`."""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.feedback.alert import Alert
from bretzel.core.serialize import serialize


class TestStructure:
    def test_no_auto_alert_role(self) -> None:
        # Spec : we DON'T auto-add ``role="alert"``. ARIA's alert role
        # carries strong interrupt-now semantics inappropriate for a
        # routine info panel ; callers add it themselves when they
        # really mean it.
        with render_isolated():
            a = Alert("oops")
            out = serialize(a.render())
        assert 'role="alert"' not in out

    def test_explicit_role_passes_through(self) -> None:
        with render_isolated():
            a = Alert("oops", role="alert")
            out = serialize(a.render())
        assert 'role="alert"' in out

    def test_message_renders_as_string(self) -> None:
        with render_isolated():
            a = Alert("Saved successfully")
            out = serialize(a.render())
        assert ">Saved successfully<" in out

    def test_title_renders_above_message(self) -> None:
        with render_isolated():
            a = Alert("body line", title="Heads up")
            out = serialize(a.render())
        assert ">Heads up<" in out
        assert out.index(">Heads up<") < out.index(">body line<")


class TestColorAndIcon:
    @pytest.mark.parametrize(
        ("color", "icon_name"),
        [
            ("info", "lucide:info"),
            ("success", "lucide:circle-check"),
            ("warning", "lucide:triangle-alert"),
            ("error", "lucide:octagon-x"),
        ],
    )
    def test_default_icon_per_semantic_color(
        self, color: str, icon_name: str
    ) -> None:
        with render_isolated():
            a = Alert("msg", color=color)
            out = serialize(a.render())
        assert f'icon="{icon_name}"' in out

    @pytest.mark.parametrize(
        "color", ["primary", "muted"],
    )
    def test_no_auto_icon_for_non_semantic_colors(self, color: str) -> None:
        # ``color="primary"`` etc. is a styling choice, not a semantic
        # severity — there's no canonical icon for it, so we render
        # iconless unless the caller passes ``icon=``.
        with render_isolated():
            a = Alert("msg", color=color)
            out = serialize(a.render())
        assert "<iconify-icon" not in out

    def test_color_substitutes_into_root(self) -> None:
        with render_isolated():
            a = Alert("msg", color="success")
            out = serialize(a.render())
        assert "bg-(--bz-bg)" in out
        assert "bz-c-success" in out
        assert "border-(--bz-solid)/20" in out
        assert "{bg_color}" not in out

    def test_arbitrary_theme_color_flows_through(self) -> None:
        # Any theme color works ; the alert styles itself with the
        # paliers posés par son pont, et c'est tout.
        with render_isolated():
            a = Alert("msg", color="primary")
            out = serialize(a.render())
        assert "bg-(--bz-bg)" in out
        assert "bz-c-primary" in out
        assert "border-(--bz-solid)/20" in out

    def test_explicit_icon_string_overrides_default(self) -> None:
        with render_isolated():
            a = Alert("msg", color="info", icon="bell")
            out = serialize(a.render())
        assert 'icon="lucide:bell"' in out
        # The default ``info`` icon must NOT appear once overridden.
        assert 'icon="lucide:info"' not in out

    def test_icon_can_be_added_to_non_semantic_color(self) -> None:
        # ``primary`` doesn't auto-pick an icon, but the caller can
        # always pass one.
        with render_isolated():
            a = Alert("msg", color="primary", icon="lightbulb")
            out = serialize(a.render())
        assert 'icon="lucide:lightbulb"' in out


class TestDismissible:
    def test_no_dismiss_button_by_default(self) -> None:
        with render_isolated():
            a = Alert("msg")
            out = serialize(a.render())
        assert "Dismiss alert" not in out
        assert "bz-data" not in out

    def test_dismissible_renders_button_and_local_open_flag(self) -> None:
        with render_isolated():
            a = Alert("msg", dismissible=True)
            out = serialize(a.render())
        assert 'bz-data="{open: true}"' in out
        assert 'bz-show="open"' in out
        assert 'aria-label="Dismiss alert"' in out
        # The dismiss button writes ``open = false`` on click.
        assert "open = false" in out or "open = false" in out
