"""Unit tests for ``bretzel.theme.slots``."""

from __future__ import annotations

import pytest

from bretzel.theme.palette import (
    DEFAULT_PALETTE,
    DEFAULT_SEMANTIC_LIGHT,
    Palette,
    ThemeError,
)
from bretzel.theme.slots import merge_component_themes


@pytest.fixture
def palette() -> Palette:
    return Palette(DEFAULT_SEMANTIC_LIGHT, palette_light=DEFAULT_PALETTE)


# ───────────────────────────────────────────────────────────────────────────


class TestMergeComponentThemes:
    def test_top_level_replace(self) -> None:
        base = {"slots": {"root": "p-4"}}
        over = {"slots": {"root": "p-8"}}
        out = merge_component_themes(base, over)
        assert out["slots"]["root"] == "p-8"

    def test_deep_merge_preserves_unmentioned(self) -> None:
        base = {
            "slots": {"root": "...", "icon": "..."},
            "variants": {"solid": "..."},
        }
        over = {"slots": {"root": "rounded-full ..."}}
        out = merge_component_themes(base, over)
        assert out == {
            "slots": {"root": "rounded-full ...", "icon": "..."},
            "variants": {"solid": "..."},
        }

    def test_does_not_mutate_inputs(self) -> None:
        base = {"slots": {"root": "p-4", "icon": "h-4"}}
        over = {"slots": {"root": "p-8"}}
        merge_component_themes(base, over)
        assert base == {"slots": {"root": "p-4", "icon": "h-4"}}
        assert over == {"slots": {"root": "p-8"}}

    def test_lists_replaced_wholesale(self) -> None:
        # Lists aren't recursed into — the override replaces the base
        # list entirely (the simple, predictable rule).
        base = {"sizes": ["sm", "md"]}
        over = {"sizes": ["lg"]}
        assert merge_component_themes(base, over) == {"sizes": ["lg"]}

    def test_override_only_keys_added(self) -> None:
        base = {"slots": {"root": "..."}}
        over = {"variants": {"solid": "..."}}
        out = merge_component_themes(base, over)
        assert out == {
            "slots": {"root": "..."},
            "variants": {"solid": "..."},
        }

    def test_empty_override_returns_copy(self) -> None:
        base = {"slots": {"root": "p-4"}}
        out = merge_component_themes(base, {})
        # Deep-copied so callers can mutate safely.
        out["slots"]["root"] = "modified"
        assert base["slots"]["root"] == "p-4"

    def test_empty_base(self) -> None:
        over = {"slots": {"root": "p-4"}}
        out = merge_component_themes({}, over)
        assert out == over
        # Still a deep copy.
        out["slots"]["root"] = "modified"
        assert over["slots"]["root"] == "p-4"

    def test_nested_three_levels(self) -> None:
        base = {
            "slots": {"root": "...", "header": {"text": "fw-bold"}},
        }
        over = {
            "slots": {"header": {"text": "fw-semibold"}},
        }
        out = merge_component_themes(base, over)
        assert out["slots"]["root"] == "..."
        assert out["slots"]["header"]["text"] == "fw-semibold"
