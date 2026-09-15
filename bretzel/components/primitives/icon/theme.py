"""Default :class:`Icon` theme.

``inline-flex shrink-0 align-middle`` + ``transition-colors`` so the icon's
colour can animate with the surrounding component (button hover, link focus).
Sizing is via ``font-size`` because ``<iconify-icon>`` sizes itself in ``1em``.
Default colour ``current`` → the ``bz-c-current`` bridge, whose
``--bz-text`` is ``currentColor`` : the icon inherits its parent's text
colour unless ``color=`` overrides.

⚠️ Le slot écrit ``text-(--bz-text)`` et non ``text-(--bz-text)`` : c'est
un PALIER, posé par la classe-pont que le socle tamponne sur la racine
(cf. :mod:`bretzel.theme.bridges`). La différence n'est pas cosmétique —
``text-(--bz-text)`` est une demi-classe que le compilateur Tailwind ne
voit pas et qu'il faut donc clôturer couleur par couleur, alors que
``text-(--bz-text)`` est une classe complète et littérale.
"""

from __future__ import annotations

from typing import Any

ICON_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            "inline-flex shrink-0 justify-center items-center align-middle "
            "transition-colors duration-150 text-(--bz-text)"
        ),
    },
    "sizes": {
        "xs": "text-xs",
        "sm": "text-sm",
        "md": "text-lg",  # default — slightly bigger than text for readability
        "lg": "text-2xl",
        "xl": "text-4xl",
        "2xl": "text-6xl",
    },
    # Default Iconify set + style. Apps override at theme registration
    # time to swap the icon library globally.
    "set": "lucide",
    "style": None,  # Phosphor / Tabler can pass "bold" / "filled" etc.
}
