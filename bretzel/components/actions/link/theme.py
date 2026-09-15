"""Default :class:`Link` theme.

Three variants :
- ``hover``     : underlines on hover only
- ``underline`` : always underlined (CMS-content style)
- ``text``      : no underline, opacity dim on hover (button-like links)

Focus ring scoped to the link itself. ``aria-disabled`` states styled
separately so disabled links match disabled buttons. The ``group`` class
lets children (e.g. trailing icons) react via ``group-hover:``.
"""

from __future__ import annotations

from typing import Any

LINK_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            # ``w-fit`` pins the box to its content width. Without it a
            # Link dropped straight into a vstack (``flex flex-col``,
            # default ``align-items: stretch``) gets stretched to the
            # full column width — the WHOLE row turns clickable, you can
            # hit the link from far right of the text. ``w-fit`` (width:
            # fit-content, ≠ auto) opts the flex item out of the stretch
            # without touching alignment. Cf. traps.md.
            "group inline-flex w-fit items-center cursor-pointer gap-1 "
            "transition-colors rounded-selector "
            # ``--bz-focus`` and NOT ``--bz-focus-soft`` : the same
            # hue at two strengths, both built by
            # :data:`~bretzel.theme.bridges.COLOR_STEPS`. The soft one
            # belongs to the ``focus:`` / ``focus-within:`` rings of
            # input fields, which stay lit for as long as you type and
            # are dimmed for that reason. A link takes a keyboard-only
            # ring, so it takes the full one.
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus) focus-visible:ring-offset-1 "
            # Disabled visuals. We deliberately do NOT use
            # ``pointer-events-none`` : it would block hover AND the
            # cursor, so ``cursor-not-allowed`` would never show. Instead
            # we keep pointer events (cursor-not-allowed visible) and
            # NEUTRALISE the hover effects by specificity : a stacked
            # ``aria-disabled:hover:*`` compiles to
            # ``&[aria-disabled="true"]:hover`` (0,3,0) which beats the
            # variants' plain ``hover:*`` (0,2,0) deterministically — no
            # ``!important`` needed. So a disabled link stops underlining
            # / brightening on hover but still shows the not-allowed
            # cursor. ``tabindex=-1`` (render()) handles keyboard ; href
            # is stripped so navigation can't follow.
            "aria-disabled:opacity-50 aria-disabled:cursor-not-allowed "
        ),
    },
    "variants": {
        "hover": (
            "hover:underline underline-offset-4 "
            "aria-disabled:hover:no-underline "
            "aria-disabled:hover:opacity-50 "
            "aria-disabled:hover:cursor-not-allowed"
        ),
        "underline": "underline underline-offset-4",
        "text": (
            "hover:opacity-80 transition-opacity "
            "aria-disabled:hover:opacity-50"
        ),
    },
}
