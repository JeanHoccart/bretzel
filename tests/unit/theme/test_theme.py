"""Unit tests for the user-facing :class:`Theme` builder."""

from __future__ import annotations

import dataclasses
import json

import pytest

from bretzel.theme import (
    DEFAULT_SEMANTIC_LIGHT,
    SEMANTIC_COLOR_NAMES,
    IconConfig,
    Palette,
    ScrollbarConfig,
    Theme,
    ThemeError,
)

# ───────────────────────────────────────────────────────────────────────────
# Default theme (no args)
# ───────────────────────────────────────────────────────────────────────────


class TestDefaultTheme:
    def test_no_args_works(self) -> None:
        theme = Theme()
        # Every semantic slot resolves cleanly.
        for slot in SEMANTIC_COLOR_NAMES:
            assert theme.get_palette().resolve(slot).bg_class == slot

    def test_default_palette_present(self) -> None:
        # The bundled palette colors are accessible by name.
        theme = Theme()
        assert theme.get_palette().resolve("tomato").bg_class == "ui-tomato"

    def test_default_scrollbar_and_icons(self) -> None:
        theme = Theme()
        assert isinstance(theme.get_scrollbar(), ScrollbarConfig)
        assert isinstance(theme.get_icons(), IconConfig)


# ───────────────────────────────────────────────────────────────────────────
# Overrides — semantic / palette / dark
# ───────────────────────────────────────────────────────────────────────────


class TestOverrides:
    def test_override_one_semantic(self) -> None:
        theme = Theme(semantic={"primary": "#27754a"})
        # Other semantic slots untouched.
        assert (
            theme.get_palette().resolve("primary").bg_hex == "#27754a"
        )
        assert (
            theme.get_palette().resolve("secondary").bg_hex
            == DEFAULT_SEMANTIC_LIGHT["secondary"]
        )

    def test_override_palette(self) -> None:
        theme = Theme(palette={"brand": "#ff0066"})
        # Default palette still there.
        theme.get_palette().resolve("tomato")
        # Override applied.
        resolved = theme.get_palette().resolve("brand")
        assert resolved.bg_hex == "#ff0066"
        assert resolved.bg_class == "ui-brand"

    def test_override_palette_dark(self) -> None:
        theme = Theme(palette_dark={"brand": "#990033"}, palette={"brand": "#ff0066"})
        light = theme.get_palette().resolve("brand", "light").bg_hex
        dark = theme.get_palette().resolve("brand", "dark").bg_hex
        assert light == "#ff0066"
        assert dark == "#990033"

    def test_override_does_not_mutate_default(self) -> None:
        Theme(semantic={"primary": "#27754a"})
        # Calling Theme() again must not see the override leaked into
        # the bundled default.
        fresh = Theme()
        assert (
            fresh.get_palette().resolve("primary").bg_hex
            == DEFAULT_SEMANTIC_LIGHT["primary"]
        )


# ───────────────────────────────────────────────────────────────────────────
# base= parameter
# ───────────────────────────────────────────────────────────────────────────


class TestBase:
    def test_base_default_is_implicit(self) -> None:
        a = Theme()
        b = Theme(base="default")
        assert a.get_palette().resolve("primary").bg_hex == b.get_palette().resolve("primary").bg_hex

    def test_base_none_requires_complete_semantic(self) -> None:
        with pytest.raises(ThemeError, match="Missing semantic"):
            Theme(base=None, semantic={"primary": "#27754a"})

    def test_base_none_with_full_semantic_works(self) -> None:
        theme = Theme(base=None, semantic=DEFAULT_SEMANTIC_LIGHT)
        # Default palette colors are NOT inherited — base=None means
        # caller takes responsibility for everything.
        with pytest.raises(ThemeError):
            theme.get_palette().resolve("tomato")

    def test_base_other_theme(self) -> None:
        custom_palette = {"brand": "#abcdef"}
        first = Theme(palette=custom_palette)
        # ``second`` builds on ``first`` — must inherit ``brand``.
        second = Theme(base=first, semantic={"primary": "#000000"})
        assert second.get_palette().resolve("brand").bg_hex == "#abcdef"
        assert second.get_palette().resolve("primary").bg_hex == "#000000"

    def test_invalid_base_raises(self) -> None:
        with pytest.raises(ThemeError, match="Unsupported"):
            Theme(base=42)  # type: ignore[arg-type]


# ───────────────────────────────────────────────────────────────────────────
# Components section — deep merge
# ───────────────────────────────────────────────────────────────────────────


class TestComponents:
    def test_get_unknown_component_returns_empty(self) -> None:
        theme = Theme()
        assert theme.get_component_theme("button") == {}

    def test_components_deep_merged(self) -> None:
        base = Theme(
            components={
                "button": {
                    "slots": {"root": "p-4", "icon": "h-4"},
                    "variants": {"solid": "bg-primary"},
                },
            },
        )
        # Override only the root slot.
        custom = Theme(
            base=base,
            components={"button": {"slots": {"root": "p-8"}}},
        )
        merged = custom.get_component_theme("button")
        assert merged["slots"]["root"] == "p-8"
        # Other entries preserved by the deep merge.
        assert merged["slots"]["icon"] == "h-4"
        assert merged["variants"] == {"solid": "bg-primary"}


# ───────────────────────────────────────────────────────────────────────────
# scrollbar / icons coercion
# ───────────────────────────────────────────────────────────────────────────


class TestScrollbarIconsCoercion:
    def test_scrollbar_from_dict(self) -> None:
        theme = Theme(scrollbar={"width": "8px"})
        sb = theme.get_scrollbar()
        assert sb.width == "8px"
        # Other fields fall through to defaults.
        assert sb.thumb == ScrollbarConfig().thumb

    def test_scrollbar_from_dataclass(self) -> None:
        custom = ScrollbarConfig(width="2px", thumb="primary/40")
        theme = Theme(scrollbar=custom)
        assert theme.get_scrollbar() is custom

    def test_scrollbar_none_resets_to_defaults(self) -> None:
        theme = Theme(scrollbar=None)
        assert theme.get_scrollbar() == ScrollbarConfig()

    def test_icons_from_dict(self) -> None:
        theme = Theme(icons={"default_set": "phosphor"})
        assert theme.get_icons().default_set == "phosphor"
        # Style + size fall through.
        assert theme.get_icons().default_style == IconConfig().default_style


# ───────────────────────────────────────────────────────────────────────────
# Generators
# ───────────────────────────────────────────────────────────────────────────


class TestGenerators:
    def test_generate_css_produces_full_stylesheet(self) -> None:
        theme = Theme()
        css = theme.generate_css()
        assert "@import" in css
        assert "@theme {" in css
        assert "::-webkit-scrollbar" in css

    def test_generate_css_cached(self) -> None:
        theme = Theme()
        a = theme.generate_css()
        b = theme.generate_css()
        # Same string instance on repeat calls.
        assert a is b

    # ``test_generate_envelope_dict_shape`` a été retiré le 2026-08-01 avec
    # la méthode : elle rendait ``{palette, icons}`` pour l'envelope, où la
    # palette n'était lue par personne et le ``icons`` n'arrivait même pas
    # (le pipeline n'extrayait que ``palette``).
    def test_dump_json_round_trips(self) -> None:
        theme = Theme(semantic={"primary": "#27754a"})
        text = theme.dump("json")
        decoded = json.loads(text)
        assert decoded["semantic"]["primary"] == "#27754a"
        # Bundled colors survive.
        assert decoded["semantic"]["secondary"] == DEFAULT_SEMANTIC_LIGHT["secondary"]

    def test_dump_python_returns_string(self) -> None:
        theme = Theme()
        text = theme.dump("python")
        assert isinstance(text, str)
        assert "primary" in text


# ───────────────────────────────────────────────────────────────────────────
# Smoke : full bundled defaults compose
# ───────────────────────────────────────────────────────────────────────────


def test_default_theme_is_consistent_with_bundled_palette() -> None:
    theme = Theme()
    p = theme.get_palette()
    assert isinstance(p, Palette)
    # All semantic slots resolve to the bundled hex.
    for slot in SEMANTIC_COLOR_NAMES:
        assert p.resolve(slot).bg_hex == DEFAULT_SEMANTIC_LIGHT[slot]
