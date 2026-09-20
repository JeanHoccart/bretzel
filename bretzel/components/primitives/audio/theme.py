"""Default :class:`Audio` theme — the repository's thinnest, and rightly so.

An ``<audio controls>`` is drawn entirely by the browser: its bar, its
buttons, its height. A theme claiming to style it would lie —
``background``, ``border-radius`` and ``width`` are about all that gets
through.

No ratio here, unlike ``image`` / ``video`` / ``iframe``: an audio player
has a FIXED height, known before loading. So it causes no page jump, and
the prop would have nothing to reserve.
"""

from __future__ import annotations

from typing import Any

AUDIO_THEME: dict[str, Any] = {
    "slots": {
        # ``w-full``: the native player otherwise takes an arbitrary
        # width (~300 px) that matches no column.
        "root": "block w-full",
    },
}
