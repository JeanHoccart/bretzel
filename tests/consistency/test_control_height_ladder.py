"""Gate : interactive controls share one height ladder per size token.

A Button next to an Input on the same row must be the same height — and at
``md`` every control already was (``h-10``), which is the tell that
equal-height is the intent. But the action family (button / icon_button /
toggle_group) had drifted to ``lg=h-11 xl=h-12`` while the field family
(input / number_input / select / date pickers) used ``lg=h-12 xl=h-14``, so a
large button sat 4px shy of a large input (bug 1-H, height axis).

Aligned the action family up to the field ladder ``h-7 / h-8 / h-10 / h-12 /
h-14``. This gate pins it : every interactive control resolves the SAME
``h-*`` at each size it defines, so the next size tweak can't silently
reintroduce the misalignment. Heights stay per-component strings (no shared
constant) — only the ladder VALUES are asserted equal.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.actions.button.theme import BUTTON_THEME
from bretzel.components.actions.icon_button.theme import ICON_BUTTON_THEME
from bretzel.components.inputs.date_picker.theme import DATE_PICKER_THEME
from bretzel.components.inputs.date_range_picker.theme import DATE_RANGE_PICKER_THEME
from bretzel.components.inputs.input.theme import INPUT_THEME
from bretzel.components.inputs.number_input.theme import NUMBER_INPUT_THEME
from bretzel.components.inputs.select.theme import SELECT_THEME
from bretzel.components.inputs.toggle_group.theme import TOGGLE_GROUP_THEME

# Canonical ladder (the field family). Value = expected ``h-*`` per size.
_LADDER = {"xs": "h-7", "sm": "h-8", "md": "h-10", "lg": "h-12", "xl": "h-14"}

# Where each component keeps the height-bearing class string for a size key.
# Components that don't define a size simply return None (skipped).
_ACCESSORS = {
    "button": lambda k: BUTTON_THEME["sizes"].get(k),
    "icon_button": lambda k: ICON_BUTTON_THEME["sizes"].get(k),
    "input": lambda k: INPUT_THEME["sizes"].get(k, {}).get("input"),
    "number_input": lambda k: NUMBER_INPUT_THEME["sizes"].get(k, {}).get("shell"),
    "select": lambda k: SELECT_THEME["sizes"].get(k, {}).get("trigger"),
    "toggle_group": lambda k: TOGGLE_GROUP_THEME["sizes"].get(k, {}).get("item"),
    "date_picker": lambda k: DATE_PICKER_THEME["sizes"]["input_field"].get(k),
    "date_range_picker": lambda k: DATE_RANGE_PICKER_THEME["sizes"]["input_field"].get(k),
}

# ⚠️ ``(?<![\w-])`` et pas ``\b`` : apres un tiret, ``\b`` est vrai,
# donc ``\bh-(\d+)`` matche AUSSI dans ``max-h-40`` — le lecteur aurait
# rendu « hauteur 40 » pour une hauteur MAXIMALE. Aucun slot de controle
# n'en porte aujourd'hui (mesure le 2026-08-19), donc c'etait un faux
# positif LATENT : c'est le test de mutation ci-dessous qui l'a trouve,
# en verifiant que la regex epargne les formes legitimes.
_H = re.compile(r"(?<![\w-])h-(\d+)\b")


def _height(size_string: str | None) -> str | None:
    if not size_string:
        return None
    m = _H.search(size_string)
    return f"h-{m.group(1)}" if m else None


@pytest.mark.parametrize("component", sorted(_ACCESSORS))
@pytest.mark.parametrize("size", list(_LADDER))
def test_control_height_matches_ladder(component: str, size: str) -> None:
    height = _height(_ACCESSORS[component](size))
    if height is None:
        pytest.skip(f"{component} defines no '{size}' height")
    assert height == _LADDER[size], (
        f"{component} size='{size}' is {height}, expected {_LADDER[size]} — "
        f"controls on the same row must share a height (bug 1-H). Keep the "
        f"per-component size string, just align the h-* value to the ladder "
        f"{_LADDER}."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : la hauteur d'un contrôle est encore lue.

    L'échelle canonique se vérifie palier par palier. Si ``_H`` cessait
    de matcher, ``_height`` rendrait ``None`` partout et la comparaison
    porterait sur du vide — un bouton 4 px plus court qu'un champ
    passerait, comme avant la gate.
    """
    assert _H.search("inline-flex h-10 px-4").group(1) == "10"
    assert _H.search("h-7").group(1) == "7"
    for licit in ("max-h-10", "h-full", "h-[2.5rem]"):
        assert not _H.search(licit), f"{licit!r} : faux positif"
