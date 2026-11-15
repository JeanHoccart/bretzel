"""The neutral steps — the greys every component shares, computed.

One chooses eleven colours; the theme derives everything in between. The
colour bridges (``bridges.py``) derive the steps of each vivid colour;
this module derives the NEUTRAL ones, from the text and the three
grounds: a line, a hover, a pressed row, a track, a placeholder…

Each is the text (or the muted text) at a dose, laid over whatever is
beneath (``transparent``): a line drawn on a panel and on a field's grey
is the same line. The dose starts from the one components wrote by hand
(``border-text/10``…) and climbs only where it does not read — over the
page, a panel AND a field's grey, in each mode — the « minimum
guaranteed » of the colour steps. Two steps are fixed, not measured: the
backdrop behind a dialog and the translucent bar, whose job is to let
through what is beneath.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from functools import lru_cache
from typing import Final

from bretzel.theme.bridges import (
    _APART,
    _FROM_GROUND,
    _NEUTRAL_CEILING,
    _RING_FROM_GROUND,
    _STATE_GAP,
    RGB,
    _grounds,
    _least,
    _mix,
    _rgb,
    _seen_over,
)
from bretzel.theme.palette import Palette, _contrast_ratio, _distance

#: ``(step, source, starting dose, rule, target)``. Rules: ``seen`` — the
#: step laid on each ground is told from it by ``target`` (OKLab ΔE ×
#: 100); ``after:<step>`` — told from that step, laid on a panel;
#: ``read`` — a contrast of ``target`` on each ground (WCAG 1.4.11, 3:1,
#: for a hint or an affordance).
NEUTRAL_STEPS: Final[tuple[tuple[str, str, int, str, float], ...]] = (
    ("line", "text", 10, "seen", 6.0),
    ("line-strong", "text", 20, "after:line", _APART),
    ("track", "text", 10, "seen", 6.0),
    ("hover", "text", 5, "seen", 3.0),
    ("pressed", "text", 10, "after:hover", _APART),
    ("tint", "text", 5, "seen", _FROM_GROUND),
    ("stripe", "text", 2, "seen", 2.0),
    ("ring", "text", 30, "seen", _RING_FROM_GROUND),
    ("placeholder", "muted", 60, "read", 3.0),
    ("faint", "text", 40, "read", 3.0),
)
#: Not measured: they let through what is beneath, by design.
FIXED_STEPS: Final[dict[str, str]] = {
    "backdrop": "color-mix(in srgb, rgb(0 0 0) 50%, transparent)",
    "glass": "color-mix(in srgb, var(--color-surface) 95%, transparent)",
}


def neutral_reads(rule: str, src: RGB, target: float, grounds: Sequence[RGB],
                  before: int | None = None) -> Callable[[int], bool]:
    """Whether a neutral step reads at a dose — the rule of
    :data:`NEUTRAL_STEPS`, for the solver and for the gate that judges
    the emitted CSS. ``before`` is the dose of the step an ``after:``
    follows."""
    if rule == "seen":
        return lambda p: _seen_over(src, p, grounds) >= target
    if rule == "read":
        return lambda p: min(_contrast_ratio(_mix(src, g, p), g) for g in grounds) >= target
    surface = grounds[1]
    ahead = _mix(src, surface, before or 0)
    return lambda p: _distance(_mix(src, surface, p), ahead) >= target


@lru_cache(maxsize=32)
def neutral_percentages(palette: Palette, mode: str = "light") -> dict[str, int]:
    """Each measured neutral step's dose in ``mode``."""
    grounds = _grounds(palette, mode)
    doses: dict[str, int] = {}
    for step, source, start, rule, target in NEUTRAL_STEPS:
        before = doses.get(rule.removeprefix("after:"))
        if before is not None:
            start = max(start, before + _STATE_GAP)
        reads = neutral_reads(rule, _rgb(palette, source, mode), target, grounds, before)
        doses[step] = _least(start, reads, _NEUTRAL_CEILING)
    return doses


def neutral_lines(palette: Palette, mode: str = "light") -> Iterable[str]:
    """The ``--color-<step>`` declarations of ``mode`` — every step, so a
    ``.dark`` subtree recomputes them from its own text and grounds."""
    sources = {step: source for step, source, *_ in NEUTRAL_STEPS}
    for step, dose in neutral_percentages(palette, mode).items():
        yield (f"--color-{step}: color-mix(in srgb, var(--color-{sources[step]}) "
               f"{dose}%, transparent);")
    for step, value in FIXED_STEPS.items():
        yield f"--color-{step}: {value};"
