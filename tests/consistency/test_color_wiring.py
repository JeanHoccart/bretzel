"""Gate : ``color=`` reaches every color-driven slot of the date family.

``ui.date_picker`` / ``ui.date_range_picker`` accept ``color=`` and forward
it to the inner ``<bz-calendar>``, but their frame ring + trigger icon slots
used to hardcode ``primary`` — so ``color="success"`` rendered a green
calendar popover with a blue focus ring and blue chevrons (bug 1-G). The
calendar's own header (prev/next IconButtons + month/year dropdown ring) had
the same gap.

Fix : the slots use the ``{bg_color}`` placeholder (same convention as
``ui.input``) resolved at render. This gate locks it — a component that
accepts ``color=`` must, when given a non-default color, emit that color's
tokens and leave NO ``*-primary`` Tailwind token behind (which would be a
slot that forgot the placeholder). Per-component class strings stay
self-contained (no shared style constant) — only the placeholder convention
is shared.
"""

from __future__ import annotations

import re

import pytest

from bretzel import ui
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize

# A Tailwind color utility pinned to ``primary`` : ``text-primary``,
# ``ring-primary/40``, ``border-primary"``. The lookahead stops at the
# token boundary so ``primary-foreground`` (a resolved ``{fg_color}``) and
# the ``primary`` palette *name* elsewhere aren't matched.
_HARDCODED_PRIMARY = re.compile(r"-primary(?=[\s\"/])")

_COLOR = "success"

_CASES = [
    ("date_picker", lambda: ui.date_picker(color=_COLOR).render()),
    ("date_range_picker", lambda: ui.date_range_picker(color=_COLOR).render()),
    ("calendar", lambda: ui.calendar(color=_COLOR).render()),
]


@pytest.mark.parametrize("label,factory", _CASES, ids=[c[0] for c in _CASES])
def test_color_reaches_every_slot(label, factory) -> None:
    with render_isolated():
        out = serialize(factory())
    assert f"-{_COLOR}" in out, (
        f"{label}: color='{_COLOR}' produced no '{_COLOR}' token — the prop "
        f"isn't reaching the themed slots at all."
    )
    stray = _HARDCODED_PRIMARY.search(out)
    assert stray is None, (
        f"{label}: color='{_COLOR}' but a slot still emits a hardcoded "
        f"'primary' Tailwind token (…{out[max(0, stray.start() - 20):stray.end() + 6]}…) "
        f"— that slot forgot the {{bg_color}} placeholder (bug 1-G)."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : la marque ``-primary`` en dur est encore reconnue.

    Le test ci-dessus est une INTERDICTION — « aucun token ``-primary``
    quand ``color=`` n'est pas le défaut ». Si la regex cessait de
    matcher, il passerait sur tout, y compris sur le bug qu'il existe
    pour attraper.
    """
    for offending in ('bg-primary ring-primary/40', 'text-primary"', "border-primary "):
        assert _HARDCODED_PRIMARY.search(offending), (
            f"{offending!r} devrait être reconnu comme un ``-primary`` en dur"
        )
    for licit in ("bg-{bg_color}", "bg-primarylike", "text-ui-primary-500"):
        assert not _HARDCODED_PRIMARY.search(licit), (
            f"{licit!r} ne devrait PAS être reconnu — faux positif"
        )
