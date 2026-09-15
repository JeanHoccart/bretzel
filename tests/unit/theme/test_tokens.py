"""Unit tests for ``bretzel.theme.tokens``."""

from __future__ import annotations

from bretzel.theme.tokens import (
    DEFAULT_PALETTE_NAMES,
    FOREGROUND_SUFFIX,
    PALETTE_CLASS_PREFIX,
    SEMANTIC_COLOR_NAMES,
)


class TestSemantic:
    def test_count(self) -> None:
        # The framework grammar contracts on 11 fixed slots : 2 brand
        # (primary / secondary) + 4 status + 5 neutrals. ``accent`` was
        # dropped (2026-06-22) — it duplicated ``info`` and no component
        # depended on it.
        assert len(SEMANTIC_COLOR_NAMES) == 11

    def test_unique(self) -> None:
        assert len(set(SEMANTIC_COLOR_NAMES)) == len(SEMANTIC_COLOR_NAMES)

    def test_known_slots_present(self) -> None:
        # Spot-check the slots components rely on.
        for slot in (
            "primary",
            "secondary",
            "success",
            "error",
            "background",
            "surface",
            "text",
            "muted",
        ):
            assert slot in SEMANTIC_COLOR_NAMES


class TestPalette:
    def test_default_count(self) -> None:
        # Spec prose says "30" but the actual catalogue is 29 named
        # colors plus black/white = 31. We pin the real count here so a
        # reorder has to be intentional, not silent.
        assert len(DEFAULT_PALETTE_NAMES) == 31

    def test_unique(self) -> None:
        assert len(set(DEFAULT_PALETTE_NAMES)) == len(DEFAULT_PALETTE_NAMES)

    def test_no_overlap_with_semantic(self) -> None:
        # Reserved-name discipline : palette must not shadow the semantic
        # grammar (CR-suggestion in spec § *Open questions*).
        overlap = set(DEFAULT_PALETTE_NAMES) & set(SEMANTIC_COLOR_NAMES)
        assert overlap == set()

    def test_known_colors_present(self) -> None:
        for color in ("red", "blue", "green", "tomato", "indigo", "amber"):
            assert color in DEFAULT_PALETTE_NAMES


class TestNamingConstants:
    def test_palette_prefix(self) -> None:
        assert PALETTE_CLASS_PREFIX == "ui-"

    def test_foreground_suffix(self) -> None:
        assert FOREGROUND_SUFFIX == "-foreground"
