"""Unit tests for ``bretzel.theme.tailwind``."""

from __future__ import annotations

import pytest

from bretzel.theme.palette import (
    DEFAULT_PALETTE,
    DEFAULT_SEMANTIC_DARK,
    DEFAULT_SEMANTIC_LIGHT,
    Palette,
)
from bretzel.theme.tailwind import (
    _hex_to_rgb_value,
    generate_safelist_comment,
    generate_theme_css,
)
from bretzel.theme.tokens import SEMANTIC_COLOR_NAMES


@pytest.fixture
def palette() -> Palette:
    return Palette(
        DEFAULT_SEMANTIC_LIGHT,
        DEFAULT_SEMANTIC_DARK,
        palette_light=DEFAULT_PALETTE,
    )


# ───────────────────────────────────────────────────────────────────────────
# RGB value helper — Tailwind v4 form
# ───────────────────────────────────────────────────────────────────────────


class TestRgbValue:
    def test_long_form(self) -> None:
        assert _hex_to_rgb_value("#27754a") == "rgb(39 117 74)"

    def test_short_form(self) -> None:
        assert _hex_to_rgb_value("#abc") == "rgb(170 187 204)"

    def test_no_hash(self) -> None:
        assert _hex_to_rgb_value("ffffff") == "rgb(255 255 255)"

    def test_uppercase(self) -> None:
        assert _hex_to_rgb_value("#FFFFFF") == "rgb(255 255 255)"


# ───────────────────────────────────────────────────────────────────────────
# generate_theme_css — structural shape
# ───────────────────────────────────────────────────────────────────────────


class TestThemeCss:
    def test_imports_tailwind(self, palette: Palette) -> None:
        out = generate_theme_css(palette)
        assert '@import "tailwindcss";' in out

    def test_has_theme_block(self, palette: Palette) -> None:
        out = generate_theme_css(palette)
        assert "@theme {" in out
        assert "\n}" in out

    def test_dark_custom_variant_redefined(self, palette: Palette) -> None:
        """Tailwind v4 ships with ``@media (prefers-color-scheme: dark)``
        as the default ``dark:`` variant. Bretzel uses class-based
        dark mode (``.dark`` on ``<html>``, written by the FOUC
        script + ``ColorScheme`` ClientState) so the variant MUST be
        redefined to match the class. Without this line every
        ``dark:hidden`` / ``dark:inline-flex`` silently fails to
        react to the user's toggle.
        """
        out = generate_theme_css(palette)
        assert "@custom-variant dark (&:where(.dark, .dark *));" in out

    def test_every_semantic_present(self, palette: Palette) -> None:
        out = generate_theme_css(palette)
        for name in SEMANTIC_COLOR_NAMES:
            assert f"--color-{name}:" in out
            assert f"--color-{name}-foreground:" in out

    def test_palette_colors_prefixed(self, palette: Palette) -> None:
        out = generate_theme_css(palette)
        # ``tomato`` should appear as ``--color-ui-tomato`` only.
        assert "--color-ui-tomato:" in out
        assert "--color-ui-tomato-foreground:" in out
        # And NOT as bare ``--color-tomato`` (which would clash with
        # Tailwind's own utilities).
        assert "--color-tomato:" not in out

    def test_dark_block_present_when_overrides(self, palette: Palette) -> None:
        out = generate_theme_css(palette)
        assert ".dark {" in out

    def test_dark_block_only_overridden_keys(self, palette: Palette) -> None:
        out = generate_theme_css(palette)
        # Find the dark block.
        dark_section = out.split(".dark {", 1)[1].split("}", 1)[0]
        # ``primary`` is NOT overridden in DEFAULT_SEMANTIC_DARK.
        assert "--color-primary:" not in dark_section
        # ``background`` IS overridden.
        assert "--color-background:" in dark_section

    def test_no_dark_block_when_no_overrides(self) -> None:
        # Build a palette with no dark dictionary at all.
        p = Palette(DEFAULT_SEMANTIC_LIGHT)
        out = generate_theme_css(p)
        assert ".dark {" not in out

    def test_rgb_value_format(self, palette: Palette) -> None:
        out = generate_theme_css(palette)
        # Tailwind v4 expects ``--color-X`` to hold an actual CSS
        # colour value — a bare ``39 117 74`` triplet generates
        # invalid output for ``text-primary``. The ``rgb()`` wrapper
        # also lets ``bg-primary/50`` keep working through v4's
        # ``color-mix`` alpha pipeline. Assert the FORMAT, not a specific
        # colour (the palette hues are retuned for distinctness — see
        # tests/consistency/test_palette_distinctness.py).
        import re
        assert re.search(r"--color-primary: rgb\(\d+ \d+ \d+\);", out), out


# ───────────────────────────────────────────────────────────────────────────
# Safelist comment
# ───────────────────────────────────────────────────────────────────────────


class TestSafelist:
    def test_wrapped_in_source_inline_directive(
        self, palette: Palette
    ) -> None:
        s = generate_safelist_comment(palette)
        # v4 syntax : real ``@source inline("…");`` directive, not a
        # CSS comment (the ``/* @source ... */`` form silently no-oped).
        assert s.startswith('@source inline("')
        assert s.endswith('");')

    def test_no_longer_closes_over_colours(self, palette: Palette) -> None:
        """La moitié COULEUR de la safelist a été déposée le 2026-08-30.

        Trois tests vivaient ici — ``bg-primary``, ``bg-ui-tomato``,
        ``bg-primary/10`` — et vérifiaient que chaque gabarit de thème
        était développé sur **toutes** les couleurs de la palette. Cette
        clôture pesait 3 791 classes, 576 Ko sur 717, **80 % de la
        feuille**, et elle n'existait que parce qu'un gabarit
        ``bg-{bg_color}`` n'est pas une classe : le compilateur ne peut
        pas le voir.

        Les thèmes lisent maintenant des PALIERS — ``bg-(--bz-bg)``, une
        classe complète et littérale — et c'est la classe-pont posée sur
        la racine qui dit la couleur. Il n'y a plus rien à clôturer, et
        ce test le VÉRIFIE : une couleur qui reviendrait dans la
        safelist signifierait qu'un gabarit est revenu avec elle.
        """
        s = generate_safelist_comment(palette)
        for gone in ("bg-primary", "bg-ui-tomato", "bg-primary/10",
                     "text-primary-foreground", "hover:bg-primary/90"):
            assert gone not in s, (
                f"{gone!r} est de retour dans la safelist. La clôture "
                "couleur a été déposée : si une couleur y revient, c'est "
                "qu'un gabarit ``{bg_color}`` est revenu avec elle."
            )
