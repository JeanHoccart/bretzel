"""Default :class:`Code` theme.

Structural styling only — Pygments emits its own ``<span>`` colour
classes inside the wrapper. Theme tokens follow the framework's
semantic palette so light and dark mode both render legibly :
``surface`` for the background, ``text/80`` for the body text,
``text/10`` for the subtle border.
"""

from __future__ import annotations

from typing import Any

CODE_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            "bz-code "                # marker class for the Pygments stylesheet
            "block w-full "
            "p-4 "
            "rounded-box border-(length:--bz-stroke) border-text/10 "
            "bg-surface text-text/80 "
            "font-mono text-xs leading-relaxed "
            # ``whitespace-pre-wrap`` keeps the serializer's newlines AND
            # wraps long tokens at container width (no horizontal scroll) ;
            # ``break-all`` lets the wrap break mid-token.
            "whitespace-pre-wrap break-all"
        ),
    },
}
