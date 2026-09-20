"""``Video`` — a dressed ``<video>``, not a player.

Scope settled at framing time (2026-08-14): **the controls stay the
browser's**. This component draws no progress bar, no volume and no
speed — the day that becomes a need, it is ANOTHER component, not one
more prop here.

What it brings beyond the bare tag, and what justifies its existing
rather than leaving it to ``ui.html``:

- **``ratio=``** reserves the room. A video is the worst case of page
  jump: the browser only knows its dimensions after a network round
  trip, so without a ratio everything that follows shifts a second after
  display.
- **``autoplay=True`` forces ``muted``.** Every browser blocks automatic
  playback with sound; without the guard, the video simply does not
  start, with no error and no log. It is THE trap this component exists
  to absorb.
- **``playsinline`` is always emitted**, and it is not a prop. Without
  it, iOS takes the video out of the flow and goes full screen as soon
  as it plays — never what one wants in an application. A setting whose
  right value is always the same is not a choice to expose.
- **``poster=``** avoids the black rectangle before playback.
- **``tracks=``** carries the subtitles, shipped on 2026-08-31 ::

      ui.video(
          "demo.mp4",
          tracks=[ui.track("fr.vtt", srclang="fr", label="Français",
                           default=True)],
      )

  A correct ``<track>`` wants three attributes (``src`` + ``srclang`` +
  ``label``): a single-string prop would have looked complete without
  being so, hence a typed descriptor that requires all three. The
  component stays a LEAF — the tracks are data, not children. Cf.
  :mod:`bretzel.components.primitives.video.track`.

What it does **not** have, and why:

- no multiple sources (``<source>`` per format): a single ``src``. When
  the need comes up, it comes up with its shape — and it will be a
  ``sources=`` on the model of ``tracks=``, not opening the component to
  children.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    ComponentUsageError,
    reactive_prop,
)
from bretzel.components.primitives.video.theme import VIDEO_THEME
from bretzel.components.primitives.video.track import TRACK_KINDS, Track
from bretzel.core.tree import Element


class Video(Component):
    """Render a native video player with reserved layout space."""

    THEME: ClassVar[dict[str, Any]] = VIDEO_THEME
    THEME_KEY: ClassVar[str] = "video"
    DEFAULT_TAG: ClassVar[str] = "video"
    IS_CONTAINER: ClassVar[bool] = False
    #: The component walks ``tracks=`` itself, and the author has
    #: nothing to add to it: a track is made of ATTRIBUTES, it carries no
    #: markup. Neither children nor a content callback would have a
    #: recipient — hence ``"data"`` rather than ``"component"``. Cf.
    #: ``Component.COLLECTION_OWNER``.
    COLLECTION_OWNER: ClassVar[str | None] = "data"

    # No bindable surface, same reason as ``image``: a media source
    # changes when the server's data changes (a ``@refreshable``
    # re-render), never under a client driver.
    src: str | None = reactive_prop(default=None, emit_attr=False, never_code=True)
    poster: str | None = reactive_prop(default=None, emit_attr=False, never_code=True)
    ratio: str | None = reactive_prop(default=None, emit_attr=False)
    fit: str = reactive_prop(default="contain", emit_attr=False)
    controls: bool = reactive_prop(default=True, emit_attr=False)
    autoplay: bool = reactive_prop(default=False, emit_attr=False)
    loop: bool = reactive_prop(default=False, emit_attr=False)
    muted: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        src: str | None = None,
        *,
        poster: str | None = None,
        ratio: str | None = None,
        fit: str | None = None,
        controls: bool | None = None,
        autoplay: bool | None = None,
        loop: bool | None = None,
        muted: bool | None = None,
        tracks: Iterable[Track] = (),
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            src=src, poster=poster, ratio=ratio, fit=fit,
            controls=controls, autoplay=autoplay, loop=loop, muted=muted,
            **kwargs,
        )
        self._tracks = list(tracks)
        self._reject_ambiguous_default()

    def _reject_ambiguous_default(self) -> None:
        """Two ``default=True`` tracks of the same ``kind``: we raise.

        HTML only allows one per ``kind``. Beyond that, the document is
        invalid and the browser keeps one **without saying which**: the
        author believes they chose the track shown by default, and chose
        nothing. Same reason to be as
        ``Table._reject_datatable_columns`` — a setting ignored in
        silence costs more than a refusal.
        """
        for kind in TRACK_KINDS:
            clashing = [t for t in self._tracks if t.kind == kind and t.default]
            if len(clashing) > 1:
                names = ", ".join(t.label for t in clashing)
                raise ComponentUsageError(
                    f"ui.video: {len(clashing)} ``{kind}`` tracks are "
                    f"marked default=True ({names}). HTML only allows one "
                    f"per kind; the browser would pick one without saying "
                    f"so. Keep default=True on the one you want active."
                )

    def render(self) -> Element:
        theme = self._resolved_theme()
        values = self._reactive_values

        # ``classes=`` is set by the metaclass wrap — not here (duplicate).
        root_class = self.slot_class(
            "root",
            theme.get("ratios", {}).get(values.get("ratio"), ""),
            theme.get("fits", {}).get(values.get("fit"), ""),
        )

        attrs = self.emit_attrs()
        attrs["class"] = root_class
        # ``src`` OMITTED when there is no source, never ``src=""``.
        # The HTML spec requires "a valid non-empty URL"; an empty
        # attribute is resolved against the document's URL, so the
        # browser downloads THE CURRENT PAGE as media — one useless
        # request per element, invisible unless you read the server's
        # logs. That is exactly how we found it.
        if values.get("src"):
            attrs["src"] = values["src"]
        if values.get("poster"):
            attrs["poster"] = values["poster"]

        autoplay = values.get("autoplay")

        if values.get("controls"):
            attrs["controls"] = True
        if autoplay:
            attrs["autoplay"] = True
        # THE guard. An unmuted ``autoplay`` is blocked by every
        # browser: the video does not start, and nothing says so —
        # neither error, nor log, nor visual clue. We force rather than
        # emit an inert attribute.
        if values.get("muted") or autoplay:
            attrs["muted"] = True
        if values.get("loop"):
            attrs["loop"] = True
        # Always, never a prop: without it iOS takes the video out of
        # the flow and goes full screen as soon as it plays. A setting
        # whose right value is always the same is not a choice to
        # expose.
        attrs["playsinline"] = True
        return Element(tag=self._tag, attrs=attrs, children=self._track_nodes())

    def _track_nodes(self) -> tuple[Element, ...]:
        """The ``<track>``, in declaration order.

        The component stays a leaf: those children are ITS OWN, not a
        ``with``'s — ``IS_CONTAINER`` keeps the author's door shut (cf.
        ``Component.add_child``).

        ``default`` is only emitted if true: the HTML spec makes it a
        boolean, so ``default="false"`` ENABLES the track. It is the
        classic boolean-attribute trap, and it only shows on screen for
        somebody who was not expecting subtitles.
        """
        nodes: list[Element] = []
        for t in self._tracks:
            attrs: dict[str, Any] = {
                "kind": t.kind,
                "src": t.src,
                "srclang": t.srclang,
                "label": t.label,
            }
            if t.default:
                attrs["default"] = True
            nodes.append(Element(tag="track", attrs=attrs))
        return tuple(nodes)
