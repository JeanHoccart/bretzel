"""Gate : an inline-* root that must HUG its content needs a non-auto width.

The bug (badge, july 2026 — and link, june 2026 before it) : a root class of
``inline-flex`` is content-width in normal flow, BUT as a direct child of a
flex parent (``ui.vstack`` / ``ui.hstack``, whose default is
``align-items: stretch``) the CSS spec BLOCKIFIES ``inline-flex`` → ``flex``
and the ``auto`` cross-axis size then stretches the box to the full column
width. A pill balloons ; an anchored overlay's ``top-full`` / ``left-1/2``
centering is computed off the stretched parent box, not the trigger.

This is the DUAL of ``test_input_root_fills_width`` : that gate forbids
shrink tokens on form controls that must FILL ; this one REQUIRES a shrink
(non-auto width) token on inline components that must HUG. Both pin the same
axis of decision — "does this box own its width, or does its parent?" — from
the two opposite answers.

Fix (the established convention, already on 6 components) : ``w-fit``
(``width: fit-content``, ≠ ``auto``) on the root. A non-auto width opts the
flex item out of the ``align-items: stretch`` on that axis without touching
alignment (unlike ``self-start``, which would hijack ``align-self`` and break
a deliberately-centered hstack). Cf. ``.claude/bretzel/traps.md`` §
"Root inline-flex étirée par un parent flex/grid items-stretch" and §
"Élément inline-flex étiré pleine largeur dans un vstack".

Signal (per-THEME-file, like ``test_truncate_needs_width`` /
``test_input_root_fills_width``) : a HUG root must carry a horizontal
intrinsic-width token — ``w-fit`` / ``w-max`` / an explicit ``w-[…]`` /
``w-<n>``. ``h-fit`` alone does NOT count : the ballooning bug is horizontal.

Self-evolving : every ``*_THEME`` across ``bretzel/components`` whose root is
``inline-flex`` / ``inline-block`` / ``inline-grid`` must be classified HUG or
STRETCH_OK. A NEW inline component (or a renamed theme) that nobody classified
fails the completeness check — forcing the author to answer "does this pill /
chip / anchored overlay hug its content, or is filling the parent fine?" at
review time. That is exactly the question badge got wrong.
"""

from __future__ import annotations

import importlib
import pkgutil
import re

import pytest

import bretzel.components as _components_pkg

# ── Classification ────────────────────────────────────────────────────
# HUG : the root MUST size to its content. A pill / chip / label posed
# directly in a stack, or an overlay root that anchors an ``absolute``
# panel off its own box — both balloon (or mis-centre) when a flex parent
# stretches them. These carry ``w-fit`` (some also ``h-fit``).
_HUG = {
    "BADGE_THEME",          # pill — ballooned in the dismissible demo column
    "LINK_THEME",           # inline link — whole row became a hit-area
    "DROPDOWN_THEME",       # anchored overlay root (relative inline-flex)
    "POPOVER_THEME",        # idem
    "TOOLTIP_THEME",        # idem (inline-block)
    "TOGGLE_GROUP_THEME",   # segmented control — sizes to its cells
}
# STRETCH_OK : inline-* roots for which filling the parent is acceptable or
# intended, OR whose fixed dimensions come from the ``sizes`` slot (``w-8
# h-8`` …) rather than the root — so blockification can't balloon them.
# Documented, on purpose ; EXEMPT from the hug rule.
_STRETCH_OK = {
    "BUTTON_THEME",         # full-width buttons in a vstack are a common, wanted layout
    "ICON_BUTTON_THEME",    # square via the size slot (w-N h-N)
    "AVATAR_THEME",         # fixed via the size slot + shrink-0
    "CHECKBOX_THEME",       # label row — a wider hit-target is fine
    "RADIO_THEME",          # idem
    "SWITCH_THEME",         # idem
    "NAVBAR_ITEM_THEME",    # nav rows fill their bar / column on purpose
    "SPARKLINE_THEME",      # sizes to its inline SVG
    "ICON_THEME",           # leaf glyph — shrink-0, sized by font/size slot
    "SPINNER_THEME",        # leaf — sized by the size slot
    # Déplacé de _HUG le 2026-08-25, et c'est un DURCISSEMENT : sa
    # largeur ne vient plus de son contenu (``w-fit``) mais de sa table
    # de tailles (``w-56`` … ``w-97``), donc cinq déclarations au lieu
    # d'une. Une largeur définie opte hors du ``align-items: stretch``
    # d'un parent flex aussi bien que ``w-fit`` — mieux, même : elle ne
    # dépend plus de ce qu'il y a dedans. Le défaut réparé : le libellé
    # du mois décidait de la largeur, et « septembre » déplaçait la
    # flèche « mois suivant » de 14,8 px entre deux clics dessus.
    # Gardé par ``test_a_size_step_declares_the_same_keys`` (chaque
    # palier déclare bien sa largeur) et
    # ``tests/probes/probe_calendar_width.py`` (elle ne bouge pas).
    "CALENDAR_THEME",
}

# Root is at risk only when it declares an inline display mode (blockified
# by a flex/grid parent). Block/flex roots aren't in scope for this gate.
_INLINE_RE = re.compile(r"(?<![\w-])inline-(?:flex|block|grid)(?![\w-])")
# A horizontal intrinsic-width token : fit-content, max-content, or an
# explicit fixed width. ``w-full`` is FILL, not HUG — excluded on purpose.
_WIDTH_TOKEN_RE = re.compile(r"(?<![\w-])(?:w-fit|w-max|w-\[|w-\d)")


def _discover_inline_roots() -> dict[str, str]:
    """Map every ``*_THEME`` across components whose root slot declares an
    inline display mode → that root class string. Walks the whole package
    so a new inline component is picked up with zero edits here (the
    completeness test then forces its classification)."""
    roots: dict[str, str] = {}
    for mod in pkgutil.walk_packages(_components_pkg.__path__,
                                     _components_pkg.__name__ + "."):
        if not mod.name.endswith(".theme"):
            continue
        module = importlib.import_module(mod.name)
        for attr in dir(module):
            if not attr.endswith("_THEME"):
                continue
            theme = getattr(module, attr)
            root = (theme.get("slots", {}) or {}).get("root")
            if isinstance(root, str) and _INLINE_RE.search(root):
                roots[attr] = root
    return roots


_ROOTS = _discover_inline_roots()


def test_every_inline_root_is_classified() -> None:
    """Completeness : no inline-* root escapes classification. A new pill /
    chip / anchored overlay forces a HUG-vs-STRETCH_OK decision here — the
    review question badge answered wrong."""
    discovered = set(_ROOTS)
    classified = _HUG | _STRETCH_OK
    unclassified = discovered - classified
    stale = classified - discovered
    assert not unclassified, (
        f"unclassified inline-* root theme(s): {sorted(unclassified)} — add each "
        f"to _HUG (must size to content — pill / chip / anchored overlay ; needs "
        f"w-fit) or _STRETCH_OK (filling the parent is fine, or dims come from the "
        f"size slot)."
    )
    assert not stale, (
        f"classified theme(s) no longer found or no longer inline: {sorted(stale)} "
        f"— remove from _HUG / _STRETCH_OK (renamed, deleted, or root is now block)."
    )


@pytest.mark.parametrize("theme_name", sorted(_HUG))
def test_hug_root_has_width_token(theme_name: str) -> None:
    root = _ROOTS.get(theme_name)
    if root is None:
        pytest.skip(f"{theme_name} not discovered (covered by completeness test)")
    assert _WIDTH_TOKEN_RE.search(root), (
        f"{theme_name} root is inline-* but carries no horizontal intrinsic-width "
        f"token (w-fit / w-max / w-[…] / w-<n>): {root!r}\n"
        f"As a direct child of a flex parent the CSS spec blockifies inline-flex → "
        f"flex and align-items: stretch balloons it to the full column width (the "
        f"badge / link bug). Add w-fit, or move this theme to _STRETCH_OK if "
        f"filling the parent is genuinely fine here."
    )


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : les racines inline découvertes sont toujours là."""
    assert len(_ROOTS) >= 12, (
        f"seulement {len(_ROOTS)} racines de thème découvertes (17 le "
        f"2026-08-19) — ``_discover_inline_roots`` ne trouve plus rien."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : les deux regex reconnaissent encore leurs jetons.

    ``_INLINE_RE`` décide QUI est concerné, ``_WIDTH_TOKEN_RE`` décide
    s'il est en règle. Une racine inline non reconnue sort du balayage
    sans un mot ; un jeton de largeur non reconnu accuse un thème juste.
    """
    for offending in ("inline-flex items-center", "inline-block", "inline-grid"):
        assert _INLINE_RE.search(offending), f"{offending!r} devrait être vu inline"
    for licit in ("flex items-center", "inline-flexbox", "not-inline-block"):
        assert not _INLINE_RE.search(licit), f"{licit!r} : faux positif"

    for width in ("w-fit", "w-max", "w-[12rem]", "w-64"):
        assert _WIDTH_TOKEN_RE.search(width), f"{width!r} est bien une largeur"
    for licit in ("max-w-full", "min-w-0", "gap-4"):
        assert not _WIDTH_TOKEN_RE.search(licit), f"{licit!r} : faux positif"
