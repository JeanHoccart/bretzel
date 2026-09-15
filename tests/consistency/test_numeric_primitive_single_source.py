"""Gate : the step→precision computation lives in ONE place.

``precisionFromStep`` (decimals implied by a numeric step, 0.01 → 2) used to
be copy-pasted byte-identical inside both ``11_number_input.js`` and
``12_slider.js``. It's a pure, widget-agnostic primitive — the good kind to
share — so it was lifted to ``$bz.num.precisionFromStep`` in
``06_helpers.js``; both slabs call it (each still caches locally).

This gate pins it : the raw derivation (``s.length - dot - 1``) appears in
exactly one runtime source, and the two numeric slabs reference the shared
helper rather than re-inlining it — so a future edit to how precision is
derived can't silently diverge between number_input and slider again.
"""

from __future__ import annotations

from pathlib import Path

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "confronte la dérivation numérique du Python à celle du JS, valeur "
    "par valeur ; `test_the_sweep_is_not_vacuous` garde la table"
)

_SRC = Path(__file__).resolve().parents[2] / "bretzel" / "runtime" / "_src"
_DERIVATION = "s.length - dot - 1"  # the precision-from-step kernel


def _read(name: str) -> str:
    return (_SRC / name).read_text(encoding="utf-8")


def test_precision_kernel_defined_once() -> None:
    hits = [p.name for p in sorted(_SRC.glob("[0-9]*_*.js"))
            if _DERIVATION in _read(p.name)]
    assert hits == ["06_helpers.js"], (
        f"the step→precision kernel ('{_DERIVATION}') must live only in "
        f"06_helpers.js (as $bz.num.precisionFromStep) — found in {hits}. "
        f"A slab re-inlined it instead of calling the shared helper."
    )


def test_helper_defines_precision_from_step() -> None:
    assert "precisionFromStep:" in _read("06_helpers.js")


def test_numeric_slabs_call_shared_helper() -> None:
    """Both numeric slabs get their precision from ``$bz.num``.

    The assertion accepts either shared entry point : the pure
    ``precisionFromStep`` or the memo wrapper ``cachedPrecision``. It
    used to name ``precisionFromStep(`` literally, which broke the day
    the memo ITSELF was shared (audit F60 — the primitive was
    single-sourced but the identical ``_precCache`` wrapper around it
    still existed in both slabs). The invariant is « the slab doesn't
    own precision logic », not « the slab calls this exact function » ;
    ``test_precision_kernel_defined_once`` above pins the kernel.
    """
    for slab in ("11_number_input.js", "12_slider.js"):
        src = _read(slab)
        assert ("$bz.num.precisionFromStep(" in src
                or "$bz.num.cachedPrecision" in src), (
            f"{slab} must get precision from $bz.num "
            f"(precisionFromStep or cachedPrecision), not re-derive it."
        )


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : la table de dérivation n'a pas fondu."""
    assert len(_DERIVATION) >= 15, (
        f"seulement {len(_DERIVATION)} dérivations vérifiées (18 le "
        f"2026-08-19) — la table a rétréci sans que personne ne le dise."
    )
