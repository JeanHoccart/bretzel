"""Default :class:`Pagination` theme.

The visual language — rounded squares, subtle hover, scale-up on the
active page — is the design-system identity.

Slots :
- ``root``     : the ``<nav>`` flex container, items + ellipsis spaced
- ``item``     : the page-number / prev / next buttons
- ``active``   : extra classes layered on the currently-selected page
- ``ellipsis`` : the "…" pseudo-buttons (non-interactive)
- ``nav``      : the prev / next chevron buttons (extra padding)

Per-size dicts carry one entry per slot that needs its own dimension —
``item`` and ``nav``. **Pas** ``ellipsis`` : cette couche est composée
PAR-DESSUS ``item``, qui porte déjà la taille.

⚠️ Les couches ``active`` / ``ellipsis`` ne doivent JAMAIS répéter un
token de ``item``. Elles partent en ``bz-class`` sur le même ``<button>``
que la couche statique, et le runtime ne retire que ce que l'expression
cesse de produire : un token partagé est retiré du ``class=`` statique en
même temps. ``ellipsis`` re-déclarait ``flex items-center justify-center``
+ ``w-10 text-sm`` — le bouton qui cessait d'être une ellipse s'effondrait
de 40 px à 8 px, hauteur intacte. Le runtime protège désormais sa baseline
(``02_directives.js``), et ``test_bz_class_never_repeats_static_tokens``
garde la règle côté thème.
"""

from __future__ import annotations

from typing import Any

PAGINATION_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            "flex items-center justify-center gap-1.5 select-none"
        ),
        "item": (
            "flex items-center justify-center rounded-field font-medium "
            "transition-all duration-200 ease-out cursor-pointer "
            "not-disabled:hover:bg-text/5 not-disabled:active:scale-95 "
            "focus-visible:ring-2 focus-visible:ring-offset-2 "
            "focus-visible:ring-offset-background "
            "focus-visible:ring-(--bz-focus) "
            "disabled:opacity-50 disabled:cursor-not-allowed"
        ),
        "active": (
            "bg-(--bz-solid) text-(--bz-on-solid) shadow-sm scale-110 z-10 "
            "not-disabled:hover:!bg-(--bz-solid)/80"
        ),
        # Composé par-dessus ``item`` : ni flex/centrage ni taille ici.
        "ellipsis": "text-muted pointer-events-none",
        "nav": "text-text/70 not-disabled:hover:text-(--bz-text)",
    },
    "sizes": {
        "xs": {
            "item": "w-7 h-7 text-[10px]",
            "nav": "p-1",
        },
        "sm": {
            "item": "w-8 h-8 text-xs",
            "nav": "p-1.5",
        },
        "md": {
            "item": "w-10 h-10 text-sm",
            "nav": "p-2",
        },
        "lg": {
            "item": "w-12 h-12 text-base",
            "nav": "p-2.5",
        },
        "xl": {
            "item": "w-14 h-14 text-lg",
            "nav": "p-3",
        },
    },
}
