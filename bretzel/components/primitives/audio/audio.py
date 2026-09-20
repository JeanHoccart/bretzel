"""``Audio`` — the thinnest of the media family, and it owns it.

Unlike its siblings, this component brings almost nothing an
``<audio controls>`` tag does not already do:

- no ``ratio`` — an audio player has a FIXED height, known before
  loading, so it causes no page jump;
- no ``poster``, no ``fit`` — there is no image;
- no theme worth the name — the bar is drawn by the browser.

It exists for two reasons, both honest:

1. **the family's symmetry** — somebody who found ``ui.video`` will look
   for ``ui.audio``, and its absence would cost them a detour through
   ``ui.html`` for a trivial tag;
2. **``controls=True`` by default** — an ``<audio>`` with no controls is
   invisible AND inaudible. The platform's default (no controls) is a
   trap for everybody except whoever drives the playback in JS.

⚠️ **No ``tracks=``, unlike ``ui.video`` — measured, not assumed.**
``ui.video`` got subtitles on 2026-08-31 and the family's symmetry would
want ``ui.audio`` to follow. It does not follow, because the track would
be INERT here: an ``<audio>``'s native controls have no CC button.
Checked in Chromium on 2026-08-31 by photographing two players side by
side, one with a subtitle track and the other without — **both captures
are byte for byte identical** (2,637 bytes, same digest). The element
does load the track (``textTracks.length === 1``, mode ``showing``, one
cue read), so a home-made JS player could use it; but this component
decided at framing time that it is not one. A prop that displays nothing
and is called ``tracks=`` would promise subtitles and deliver an
attribute — exactly the half-delivery this repository hunts. An audio
file's accessible output therefore remains the **transcript placed
beside it, as real text**, which its bench's *A11y* card shows.

⚠️ **No ``autoplay`` → ``muted`` guard, unlike ``ui.video``, and it is
not an oversight.** On a video, forcing silence saves the automatic
playback: the picture stays, and that was the point. On sound, silence
removes *everything* the playback brought — we would ship a player
running for nothing. An automatic audio playback is blocked anyway until
the user has interacted with the page; it is a browser policy no
attribute gets around. So we emit ``autoplay`` as asked, and we say so.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.primitives.audio.theme import AUDIO_THEME
from bretzel.core.tree import Element


class Audio(Component):
    """Render a native audio player with visible controls by default."""

    THEME: ClassVar[dict[str, Any]] = AUDIO_THEME
    THEME_KEY: ClassVar[str] = "audio"
    DEFAULT_TAG: ClassVar[str] = "audio"
    IS_CONTAINER: ClassVar[bool] = False

    src: str | None = reactive_prop(default=None, emit_attr=False, never_code=True)
    controls: bool = reactive_prop(default=True, emit_attr=False)
    autoplay: bool = reactive_prop(default=False, emit_attr=False)
    loop: bool = reactive_prop(default=False, emit_attr=False)
    muted: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        src: str | None = None,
        *,
        controls: bool | None = None,
        autoplay: bool | None = None,
        loop: bool | None = None,
        muted: bool | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            src=src, controls=controls, autoplay=autoplay,
            loop=loop, muted=muted, **kwargs,
        )

    def render(self) -> Element:
        values = self._reactive_values

        # ``classes=`` is set by the metaclass wrap — not here (duplicate).
        root_class = self.slot_class("root")

        attrs = self.emit_attrs()
        attrs["class"] = root_class
        # ``src`` omitted rather than empty — a ``src=""`` is resolved
        # against the document's URL, so the browser re-downloads the
        # page believing it is loading the sound. Cf. the 2026-08-14 fix
        # on image/video.
        if values.get("src"):
            attrs["src"] = values["src"]
        if values.get("controls"):
            attrs["controls"] = True
        # No muted guard here: cf. the module's docstring. Forcing
        # silence on sound would remove everything the playback brings.
        if values.get("autoplay"):
            attrs["autoplay"] = True
        if values.get("muted"):
            attrs["muted"] = True
        if values.get("loop"):
            attrs["loop"] = True
        return Element(tag=self._tag, attrs=attrs, children=())
