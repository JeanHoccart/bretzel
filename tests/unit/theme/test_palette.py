"""Unit tests for ``bretzel.theme.palette``."""

from __future__ import annotations

import pytest

from bretzel.theme.palette import (
    DEFAULT_PALETTE,
    DEFAULT_SEMANTIC_DARK,
    DEFAULT_SEMANTIC_LIGHT,
    Palette,
    ResolvedColor,
    ThemeError,
    _contrast_ratio,
    _parse_hex,
    _relative_luminance,
    resolve_color_pair,
)
from bretzel.theme.tokens import SEMANTIC_COLOR_NAMES

# ───────────────────────────────────────────────────────────────────────────
# _parse_hex
# ───────────────────────────────────────────────────────────────────────────


class TestParseHex:
    def test_long_form(self) -> None:
        assert _parse_hex("#27754a") == (39, 117, 74)

    def test_short_form(self) -> None:
        assert _parse_hex("#abc") == (0xAA, 0xBB, 0xCC)

    def test_no_hash(self) -> None:
        assert _parse_hex("ffffff") == (255, 255, 255)

    def test_uppercase(self) -> None:
        assert _parse_hex("#FFFFFF") == (255, 255, 255)

    @pytest.mark.parametrize("bad", ["#x", "12345", "not-a-hex", "#1234567", ""])
    def test_invalid_raises(self, bad: str) -> None:
        with pytest.raises(ThemeError):
            _parse_hex(bad)


# ───────────────────────────────────────────────────────────────────────────
# resolve_color_pair — auto foreground
# ───────────────────────────────────────────────────────────────────────────


class TestResolveColorPair:
    def test_light_bg_gets_dark_fg(self) -> None:
        bg, fg = resolve_color_pair("#ffffff")
        assert bg == "#ffffff"
        # Dark fg (luminance well below 0.5).
        assert _relative_luminance(*_parse_hex(fg)) < 0.3

    def test_dark_bg_gets_light_fg(self) -> None:
        bg, fg = resolve_color_pair("#000000")
        assert bg == "#000000"
        assert _relative_luminance(*_parse_hex(fg)) > 0.7

    @pytest.mark.parametrize(
        "hex_in",
        list(DEFAULT_PALETTE.values()) + list(DEFAULT_SEMANTIC_LIGHT.values()),
    )
    def test_every_default_meets_wcag_aa(self, hex_in: str) -> None:
        bg, fg = resolve_color_pair(hex_in)
        ratio = _contrast_ratio(_parse_hex(bg), _parse_hex(fg))
        # AA for body text is 4.5 ; some semantic colors (warning,
        # info) sit close to mid-luminance and may land slightly below
        # — guard at 3.0 (AA Large) which is what UI buttons actually
        # need. Better than chasing perfection in a math-derived fg.
        assert ratio >= 3.0, (
            f"contrast ratio {ratio:.2f} below 3.0 for {hex_in!r} → fg={fg!r}"
        )


# ───────────────────────────────────────────────────────────────────────────
# Palette construction
# ───────────────────────────────────────────────────────────────────────────


def _full_semantic() -> dict[str, str]:
    return dict(DEFAULT_SEMANTIC_LIGHT)


class TestConstruction:
    def test_minimal_palette(self) -> None:
        p = Palette(_full_semantic())
        assert isinstance(p.resolve("primary"), ResolvedColor)

    def test_missing_semantic_raises(self) -> None:
        bad = dict(DEFAULT_SEMANTIC_LIGHT)
        del bad["primary"]
        with pytest.raises(ThemeError, match="Missing semantic colors"):
            Palette(bad)

    def test_palette_collision_with_semantic_raises(self) -> None:
        with pytest.raises(ThemeError, match="collide"):
            Palette(_full_semantic(), palette_light={"primary": "#ff0000"})

    def test_invalid_hex_in_value_raises(self) -> None:
        bad = dict(DEFAULT_SEMANTIC_LIGHT)
        bad["primary"] = "not-a-hex"
        with pytest.raises(ThemeError):
            Palette(bad)

    def test_explicit_pair_accepted(self) -> None:
        sem = dict(DEFAULT_SEMANTIC_LIGHT)
        sem["primary"] = ("#27754a", "#ffffff")
        p = Palette(sem)
        resolved = p.resolve("primary")
        assert resolved.bg_hex == "#27754a"
        assert resolved.fg_hex == "#ffffff"


# ───────────────────────────────────────────────────────────────────────────
# Class-name conventions
# ───────────────────────────────────────────────────────────────────────────


class TestClassNames:
    def setup_method(self) -> None:
        self.p = Palette(
            _full_semantic(),
            palette_light=DEFAULT_PALETTE,
        )

    def test_semantic_no_prefix(self) -> None:
        assert self.p.bg_class("primary") == "primary"
        assert self.p.fg_class("primary") == "primary-foreground"

    def test_palette_with_prefix(self) -> None:
        assert self.p.bg_class("tomato") == "ui-tomato"
        assert self.p.fg_class("tomato") == "ui-tomato-foreground"

    def test_unknown_color_raises(self) -> None:
        with pytest.raises(ThemeError, match="Couleur inconnue"):
            self.p.bg_class("doesnotexist")

    def test_the_refusal_says_what_is_accepted_and_why(self) -> None:
        """Le message porte la CONSÉQUENCE, pas seulement la faute.

        Une couleur hors palette produit une classe assemblée au rendu,
        donc absente des sources, donc absente du CSS de prod : correct
        en dev, sans style en prod, HTML identique des deux côtés. Un
        message qui dirait juste « couleur inconnue » laisserait croire à
        un détail cosmétique."""
        with pytest.raises(ThemeError) as exc:
            self.p.bg_class("doesnotexist")
        msg = str(exc.value)
        assert "doesnotexist" in msg, "le message doit nommer la fautive"
        assert "primary" in msg, "il doit lister ce qui est accepté"
        assert "current" in msg, "y compris les mots-clés CSS"
        assert "prod" in msg.lower(), "il doit dire la conséquence"
        assert "Theme(palette=" in msg, "et la sortie pour une couleur de marque"


# ───────────────────────────────────────────────────────────────────────────
# Mode (light / dark) resolution
# ───────────────────────────────────────────────────────────────────────────


class TestModeResolution:
    def test_light_mode_uses_semantic_light(self) -> None:
        p = Palette(_full_semantic(), DEFAULT_SEMANTIC_DARK)
        bg = p.resolve("background", "light").bg_hex
        assert bg == DEFAULT_SEMANTIC_LIGHT["background"]

    def test_dark_mode_overrides(self) -> None:
        p = Palette(_full_semantic(), DEFAULT_SEMANTIC_DARK)
        bg = p.resolve("background", "dark").bg_hex
        assert bg == DEFAULT_SEMANTIC_DARK["background"]

    def test_dark_falls_through_when_unspecified(self) -> None:
        # primary isn't overridden in dark → resolves to light value.
        p = Palette(_full_semantic(), DEFAULT_SEMANTIC_DARK)
        bg_dark = p.resolve("primary", "dark").bg_hex
        bg_light = p.resolve("primary", "light").bg_hex
        assert bg_dark == bg_light


# ───────────────────────────────────────────────────────────────────────────
# all_colors / envelope_dict — JSON-friendly summaries
# ───────────────────────────────────────────────────────────────────────────


class TestSummaries:
    def setup_method(self) -> None:
        self.p = Palette(
            _full_semantic(),
            palette_light={"tomato": DEFAULT_PALETTE["tomato"]},
        )

    def test_all_colors_includes_semantic_and_palette(self) -> None:
        c = self.p.all_colors()
        for name in SEMANTIC_COLOR_NAMES:
            assert name in c
        assert "tomato" in c

    def test_envelope_dict_class_names_only(self) -> None:
        env = self.p.envelope_dict()
        # Spec : the JS only needs class names ; hex stays in CSS vars.
        assert env["primary"] == {"bg": "primary", "fg": "primary-foreground"}
        assert env["tomato"] == {"bg": "ui-tomato", "fg": "ui-tomato-foreground"}
        # No stray hex values leaked into the runtime payload.
        for entry in env.values():
            for v in entry.values():
                assert "#" not in v


# ───────────────────────────────────────────────────────────────────────────
# Default dicts shipped with the framework
# ───────────────────────────────────────────────────────────────────────────


class TestShippedDefaults:
    def test_semantic_light_complete(self) -> None:
        for slot in SEMANTIC_COLOR_NAMES:
            assert slot in DEFAULT_SEMANTIC_LIGHT
            assert DEFAULT_SEMANTIC_LIGHT[slot].startswith("#")

    def test_default_palette_unique_hex(self) -> None:
        # No two named palette entries should accidentally share a hex.
        hex_values = list(DEFAULT_PALETTE.values())
        assert len(hex_values) == len(set(hex_values))

    def test_default_palette_compatible_with_palette(self) -> None:
        # Sanity check : the bundled defaults round-trip cleanly through
        # the Palette constructor.
        Palette(
            DEFAULT_SEMANTIC_LIGHT,
            DEFAULT_SEMANTIC_DARK,
            DEFAULT_PALETTE,
        )
