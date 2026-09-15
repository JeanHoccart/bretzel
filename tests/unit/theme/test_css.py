"""Unit tests for ``bretzel.theme.css`` (and ``config``)."""

from __future__ import annotations

import pytest

from bretzel.theme.config import IconConfig, ScrollbarConfig
from bretzel.theme.css import (
    _resolve_color_expression,
    generate_scrollbar_css,
    generate_theme_css_full,
)
from bretzel.theme.palette import (
    DEFAULT_PALETTE,
    DEFAULT_SEMANTIC_DARK,
    DEFAULT_SEMANTIC_LIGHT,
    Palette,
)


@pytest.fixture
def palette() -> Palette:
    return Palette(
        DEFAULT_SEMANTIC_LIGHT,
        DEFAULT_SEMANTIC_DARK,
        palette_light=DEFAULT_PALETTE,
    )


# ───────────────────────────────────────────────────────────────────────────
# config dataclasses
# ───────────────────────────────────────────────────────────────────────────


class TestConfigDefaults:
    def test_icon_defaults(self) -> None:
        c = IconConfig()
        assert c.default_set == "lucide"
        assert c.default_style == "outline"
        assert "w-[1em]" in c.default_size

    def test_scrollbar_defaults(self) -> None:
        c = ScrollbarConfig()
        assert c.width == "4px"
        assert c.thumb == "muted/30"

    def test_frozen(self) -> None:
        import dataclasses

        c = IconConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.default_set = "phosphor"  # type: ignore[misc]


# ───────────────────────────────────────────────────────────────────────────
# Color expression resolver
# ───────────────────────────────────────────────────────────────────────────


class TestResolveColorExpression:
    def test_pure_color_name(self, palette: Palette) -> None:
        # Tailwind v4 stores ``--color-X`` as a full ``rgb(...)``
        # expression — we hand back the bare var so the browser
        # doesn't nest two ``rgb()`` calls (which silently drops the
        # declaration and falls back to ``auto``).
        assert (
            _resolve_color_expression("muted", palette)
            == "var(--color-muted)"
        )

    def test_color_with_opacity(self, palette: Palette) -> None:
        out = _resolve_color_expression("muted/30", palette)
        assert out == "color-mix(in srgb, var(--color-muted) 30%, transparent)"

    def test_palette_color_uses_prefix(self, palette: Palette) -> None:
        out = _resolve_color_expression("tomato", palette)
        assert out == "var(--color-ui-tomato)"

    def test_hex_passes_through(self, palette: Palette) -> None:
        assert _resolve_color_expression("#abcdef", palette) == "#abcdef"

    @pytest.mark.parametrize("value", ["transparent", "currentColor", "inherit"])
    def test_keywords_passthrough(self, value: str, palette: Palette) -> None:
        assert _resolve_color_expression(value, palette) == value

    def test_opacity_clamped(self, palette: Palette) -> None:
        # Spec ``ScrollbarConfig`` documents 0-100 ; we clamp out of band.
        assert "100%" in _resolve_color_expression("muted/200", palette)
        # 0 stays 0.
        assert "0%" in _resolve_color_expression("muted/0", palette)


# ───────────────────────────────────────────────────────────────────────────
# Scrollbar CSS
# ───────────────────────────────────────────────────────────────────────────


class TestScrollbarCss:
    def test_default_shape(self, palette: Palette) -> None:
        css = generate_scrollbar_css(ScrollbarConfig(), palette)
        # WebKit + Firefox properties both present.
        assert "::-webkit-scrollbar" in css
        assert "scrollbar-width: thin" in css
        # Width applied in both axes.
        assert "width: 4px" in css
        assert "height: 4px" in css

    def test_thumb_color_resolved(self, palette: Palette) -> None:
        css = generate_scrollbar_css(ScrollbarConfig(), palette)
        # Default thumb is ``muted/30`` → expanded to a color-mix()
        # expression. We avoid ``rgb(var(--color-X) / pct)`` because
        # Tailwind v4 already stores ``--color-X`` as ``rgb(...)`` —
        # nested ``rgb()`` is invalid and the browser drops the rule.
        assert (
            "color-mix(in srgb, var(--color-muted) 30%, transparent)" in css
        )

    def test_arrows_and_corner_hidden(self, palette: Palette) -> None:
        # User-visible expectation : no OS arrow buttons, no corner
        # frame square. Both pseudo-elements must be explicitly
        # neutralised, otherwise Chromium renders the platform default.
        css = generate_scrollbar_css(ScrollbarConfig(), palette)
        assert "::-webkit-scrollbar-button" in css
        assert "::-webkit-scrollbar-corner" in css

    def test_thumb_visible_with_4px_width(self, palette: Palette) -> None:
        # ``border: Npx solid transparent`` + ``background-clip:
        # content-box`` shrinks the visible thumb by 2*N. With the
        # default 4px width, the border MUST stay at 1px so 2px of
        # thumb actually paints — a 2px border eats the whole bar.
        css = generate_scrollbar_css(ScrollbarConfig(), palette)
        assert "border: 1px solid transparent" in css


# ───────────────────────────────────────────────────────────────────────────
# Full composer
# ───────────────────────────────────────────────────────────────────────────


class TestComposer:
    def test_includes_all_sections(self, palette: Palette) -> None:
        out = generate_theme_css_full(palette, scrollbar=ScrollbarConfig())
        # Safelist directive first (v4 form, not the old comment).
        assert '@source inline("' in out
        # Theme block.
        assert "@import" in out
        assert "@theme {" in out
        # Autofill fix.
        assert "input:-webkit-autofill" in out
        # Transitions.
        assert "transition:" in out
        # Selection highlight tints with --color-text (neutral, OS-like)
        # and overrides autofilled inputs whose box-shadow would
        # otherwise hide the normal ::selection background.
        assert "::selection" in out
        assert "var(--color-text)" in out
        assert ":-webkit-autofill::selection" in out
        # Scrollbar.
        assert "::-webkit-scrollbar" in out

    def test_scrollbar_omitted_when_none(self, palette: Palette) -> None:
        out = generate_theme_css_full(palette, scrollbar=None)
        # The GLOBAL scrollbar rules (track/thumb/button styling) are
        # omitted. We target the thumb/track markers — unique to the
        # global block — rather than any ``::-webkit-scrollbar``, because
        # the collapsed-rail hide (``_RAIL_SCROLL``) is always emitted (a
        # sidebar-component behaviour, independent of the global config)
        # and legitimately carries a scoped ``::-webkit-scrollbar`` rule.
        assert "::-webkit-scrollbar-thumb" not in out
        assert "::-webkit-scrollbar-track" not in out
        # Theme block still there.
        assert "@theme {" in out

    def test_dark_block_propagates(self, palette: Palette) -> None:
        out = generate_theme_css_full(palette)
        assert ".dark {" in out
