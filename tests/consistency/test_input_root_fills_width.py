"""Gate : a form-control input must FILL its container, never size to content.

The bug (date_picker / date_range_picker) : their root was ``inline-flex …
w-fit h-fit`` while every sibling form input (input / number_input / select /
combobox …) is ``w-full``. In a constrained parent — a ``grid`` cell, a
``form_field`` — ``w-fit`` sized the root to its content's max-content (the
``<input>`` + icon buttons), so it grew PAST the cell : +5px empty, +38px once
a value revealed the ``×`` clear button. The field stretched the whole row.

Root cause : both are composite inputs that embed a ``calendar``. The calendar
is legitimately ``w-fit`` (a popover grid widget that sizes to its content) —
and the pickers copied its root sizing instead of the form-control convention
(``w-full``, the caller's parent owns the width). This gate pins the
convention so the copy-from-the-wrong-ancestor slip can't recur.

Signal (per-THEME-file, like ``test_truncate_needs_width``) : a FILL control's
root must carry NO intrinsic-shrink token — no ``w-fit``, no ``inline-flex`` /
``inline-block`` / ``inline-grid``. It fills via ``w-full`` or a plain block /
flex box (``radio_group`` / ``form`` fill without a literal ``w-full``, so we
forbid the shrink tokens rather than require ``w-full``).

Self-evolving : every ``*_THEME`` under ``bretzel/components/inputs`` must be
classified FILL or INTRINSIC. A NEW input component (or a new theme constant)
that nobody classified fails the completeness check — forcing the author to
decide "does this fill its cell?" at review time, which is exactly the
question the date pickers got wrong.
"""

from __future__ import annotations

import importlib
import pkgutil
import re

import pytest

import bretzel.components.inputs as _inputs_pkg

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "classe chaque racine de champ puis vérifie l'absence de jetons de "
    "rétrécissement dans une liste FERMÉE de quatre — un jeton renommé "
    "ferait rougir `test_every_input_theme_is_classified`"
)

# ── Classification ────────────────────────────────────────────────────
# FILL : form controls dropped into a form_field / grid cell — the parent
# owns the width, so the root must fill it and never overflow.
_FILL = {
    "INPUT_THEME", "TEXTAREA_THEME", "SELECT_THEME", "NUMBER_INPUT_THEME",
    "COMBOBOX_THEME", "SLIDER_THEME", "FILE_UPLOAD_THEME",
    "DATE_PICKER_THEME", "DATE_RANGE_PICKER_THEME", "TIME_PICKER_THEME",
    "MONTH_PICKER_THEME", "WEEK_PICKER_THEME", "COLOR_PICKER_THEME",
    # Un pad de signature est une SURFACE : il remplit la place qu'on lui
    # donne, et n'a aucune largeur intrinsèque à laquelle se réduire (un
    # ``<canvas>`` n'en a pas du tout).
    "SIGNATURE_PAD_THEME",
    "RADIO_GROUP_THEME",              # a flex row of radios — block, fills
    "FORM_THEME", "FORM_FIELD_THEME",  # layout wrappers, fill their parent
}
# INTRINSIC : deliberately content-sized / inline — a single toggle sits
# inline with its label ; a segmented control / calendar grid sizes to its
# cells. These are EXEMPT from the fill rule (documented, on purpose).
_INTRINSIC = {
    "CHECKBOX_THEME", "SWITCH_THEME", "RADIO_THEME",  # single inline toggles
    "TOGGLE_GROUP_THEME",                             # segmented control (w-fit)
    "CALENDAR_THEME",                                 # popover grid widget (w-fit)
}

# Tokens that make a box size to its content instead of filling its parent.
# Presence of ANY on a FILL root is the exact regression the date pickers hit.
_SHRINK_TOKENS = ("w-fit", "inline-flex", "inline-block", "inline-grid")


def _discover_theme_roots() -> dict[str, str]:
    """Map every ``*_THEME`` constant under components/inputs → its root slot
    class string. Walks the package so a new component is picked up with zero
    edits here (the completeness test then forces its classification)."""
    roots: dict[str, str] = {}
    for mod in pkgutil.walk_packages(_inputs_pkg.__path__,
                                     _inputs_pkg.__name__ + "."):
        if not mod.name.endswith(".theme"):
            continue
        module = importlib.import_module(mod.name)
        for attr in dir(module):
            if not attr.endswith("_THEME"):
                continue
            theme = getattr(module, attr)
            root = (theme.get("slots", {}) or {}).get("root")
            if isinstance(root, str):
                roots[attr] = root
    return roots


_ROOTS = _discover_theme_roots()


def test_every_input_theme_is_classified() -> None:
    """Completeness : no ``*_THEME`` root escapes classification. A new input
    forces a FILL-vs-INTRINSIC decision here — the review question the date
    pickers answered wrong."""
    discovered = set(_ROOTS)
    classified = _FILL | _INTRINSIC
    unclassified = discovered - classified
    stale = classified - discovered
    assert not unclassified, (
        f"unclassified input theme(s): {sorted(unclassified)} — add each to "
        f"_FILL (fills its form_field / grid cell) or _INTRINSIC (content-sized "
        f"on purpose, like a single toggle or the calendar grid)."
    )
    assert not stale, (
        f"classified theme(s) no longer found: {sorted(stale)} — remove from "
        f"_FILL / _INTRINSIC (renamed or deleted)."
    )


@pytest.mark.parametrize("theme_name", sorted(_FILL))
def test_fill_input_root_has_no_shrink_token(theme_name: str) -> None:
    root = _ROOTS.get(theme_name)
    if root is None:
        pytest.skip(f"{theme_name} not discovered (covered by completeness test)")
    hits = [t for t in _SHRINK_TOKENS if re.search(rf"(?<![\w-]){re.escape(t)}(?![\w-])", root)]
    assert not hits, (
        f"{theme_name} root carries intrinsic-shrink token(s) {hits}: {root!r}\n"
        f"A form control must FILL its cell (w-full / block / flex), never size "
        f"to content — else it overflows a constrained grid / form_field cell "
        f"(the date_picker w-fit bug). Drop the token, or move it to _INTRINSIC "
        f"if this component is genuinely content-sized on purpose."
    )


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : les racines de champ découvertes sont toujours là."""
    assert len(_ROOTS) >= 15, (
        f"seulement {len(_ROOTS)} racines de thème découvertes (21 le "
        f"2026-08-19) — ``_discover_theme_roots`` ne trouve plus rien."
    )
