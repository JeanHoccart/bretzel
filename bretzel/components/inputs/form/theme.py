"""Default :class:`Form` theme — a thin flex column."""

from __future__ import annotations

from typing import Any

FORM_THEME: dict[str, Any] = {
    "slots": {
        "root": "flex flex-col gap-2",
    },
}
