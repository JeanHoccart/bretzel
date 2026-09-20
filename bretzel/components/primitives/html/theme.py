"""Default :class:`Html` theme — deliberately almost empty.

A single slot, and it carries **no** visual class. That is the point:
``ui.html`` injects markup the framework did not produce, so it has no
business imposing a typography, a spacing or a colour on it. The
contrast with ``ui.markdown`` is intentional — that one OWNS the HTML it
emits (it is the one that made it from the markdown source), so it has
the right and the duty to style it.

``bz-html`` is a **marker** class, not a style class: it gives the app a
CSS hook and the audit probes a stable selector.
"""

from __future__ import annotations

from typing import Any

HTML_THEME: dict[str, Any] = {
    "slots": {
        "root": "bz-html",
    },
}
