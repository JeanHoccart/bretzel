"""Drift gate — the six BRAND semantic colours must stay perceptually
distinct.

The visual sweep flagged ~60 "these two colours look identical" fails whose
root cause was the palette itself : ``secondary``≈``warning`` (both amber,
ΔE 17.7) and ``primary``≈``success`` (both green, ΔE 29) — a SHARED-token
collision that propagated to every component. Retuning the six hues fixed it
once, at the source. This gate keeps it fixed : it recomputes the pairwise
perceptual distance and fails if any brand pair drifts back into confusable
range — so a future palette edit can't silently re-introduce the bug.

CIE76 ΔE in CIELab (the metric the audit used). Threshold 30 : comfortably
below the shipped worst-pair (~36) yet far above the old collisions (17.7).
"""

from __future__ import annotations

import itertools
import math

from bretzel.theme.palette import DEFAULT_SEMANTIC_LIGHT

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "calcule un ΔE entre couleurs et le compare à un seuil ; un calcul "
    "numérique ne devient pas aveugle"
)

# The colour-carrying semantic slots (NOT the neutral chrome slots
# background/surface/interface/text/muted, which are meant to be close).
_BRAND = ("primary", "secondary", "success", "error", "warning", "info")

_MIN_DELTA_E = 30.0


def _hex_to_lab(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def _lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = _lin(r), _lin(g), _lin(b)
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def _f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = _f(x), _f(y), _f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _delta_e(h1: str, h2: str) -> float:
    a, b = _hex_to_lab(h1), _hex_to_lab(h2)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def test_brand_colors_are_perceptually_distinct() -> None:
    offenders = [
        (a, b, round(_delta_e(DEFAULT_SEMANTIC_LIGHT[a],
                              DEFAULT_SEMANTIC_LIGHT[b]), 1))
        for a, b in itertools.combinations(_BRAND, 2)
        if _delta_e(DEFAULT_SEMANTIC_LIGHT[a],
                    DEFAULT_SEMANTIC_LIGHT[b]) < _MIN_DELTA_E
    ]
    assert not offenders, (
        f"brand colours too close (ΔE < {_MIN_DELTA_E}): {offenders}. "
        "Two semantic colours that look alike make every component's variant "
        "matrix ambiguous — spread the hues in palette.py."
    )


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : les couleurs de marque comparées existent encore.

    « Toutes distinctes » est vrai sur une palette d'une seule couleur.
    """
    assert len(_BRAND) >= 6, (
        f"seulement {len(_BRAND)} couleurs de marque comparées (6 le "
        f"2026-08-19) — la palette a rétréci, la distinction ne prouve rien."
    )
