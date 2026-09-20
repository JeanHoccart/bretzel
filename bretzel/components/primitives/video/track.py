"""``Track`` — a subtitle track described as data.

Why a descriptor and not children
----------------------------------
HTML puts the tracks INSIDE the tag ::

    <video src="demo.mp4" controls>
      <track kind="captions" src="fr.vtt" srclang="fr" label="Français" default>
    </video>

:class:`~bretzel.components.Video` cannot follow that shape without
ceasing to be a **leaf** (``IS_CONTAINER = False``), and that contract is
what today stops anybody slipping a button or a table in there — which
the browser would swallow without a word. A track has no markup to carry
anyway: it is made of attributes, all five known in advance. So we
describe it, as :class:`~bretzel.components.Series` describes a chart
series and ``ui.column`` a table column.

The gain that counts is elsewhere than in the syntax: a typed object
reads back. ``srclang`` and ``label`` are MANDATORY fields here, so a
track with neither language nor menu name cannot be built — whereas a
raw HTML string passed to ``ui.html`` is judged by nobody. It is an
accessibility hole we are closing; closing it halfway would make no
sense.

``kind="metadata"`` is not accepted
------------------------------------
The four values of :data:`TRACK_KINDS` all address a human and are driven
from the browser's controls. ``metadata`` is the only ``kind`` that
addresses JS alone (hover thumbnails, a home-made player's markers) — it
has neither a language nor a menu label to carry, so the two mandatory
fields above would make no sense for it, and ``ui.video`` decided at
framing time that it is not a player. The day the need comes up, it
comes up with its shape.
"""

from __future__ import annotations

from dataclasses import dataclass

from bretzel.components.base import ComponentUsageError

#: The accepted ``kind``. ``metadata`` is deliberately absent — cf. the
#: module's docstring.
TRACK_KINDS: tuple[str, ...] = (
    "captions",
    "subtitles",
    "descriptions",
    "chapters",
)


@dataclass(frozen=True, slots=True)
class Track:
    """Describe a timed media track such as captions, descriptions, or chapters."""

    src: str
    srclang: str
    label: str
    kind: str = "captions"
    default: bool = False

    def __post_init__(self) -> None:
        if self.kind not in TRACK_KINDS:
            raise ComponentUsageError(
                f"ui.track: kind={self.kind!r} unknown — the values are "
                f"{', '.join(TRACK_KINDS)}. ``metadata`` is not accepted: "
                f"it addresses JS alone, and ui.video is not a player (cf. "
                f"its docstring)."
            )
        for field_name in ("src", "srclang", "label"):
            if not getattr(self, field_name).strip():
                raise ComponentUsageError(
                    f"ui.track: {field_name}= is empty. All three are "
                    f"mandatory — a track with neither language nor label "
                    f"cannot be chosen in the menu, and that is precisely "
                    f"what this API exists to prevent."
                )


# Sugar exposed as ``ui.track(...)``, so user code does not have to
# import the dataclass — same gesture as ``ui.column``.
def track(
    src: str,
    *,
    srclang: str,
    label: str,
    kind: str = "captions",
    default: bool = False,
) -> Track:
    """Build a timed media track for ``ui.audio`` or ``ui.video``."""
    return Track(
        src=src, srclang=srclang, label=label, kind=kind, default=default,
    )
