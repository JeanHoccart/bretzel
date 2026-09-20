"""``Image`` — show an image, with its room reserved.

What this component brings beyond a bare ``<img>`` tag, and what
justifies its existing:

- **``ratio=``** reserves the room BEFORE the image arrives. Without it,
  the page jumps on load (each image pushes the content below). It is
  the main gain, not a refinement.
- **``alt=`` mandatory.** Like ``ui.iframe``'s ``title``, and for the
  same reason: a decorative image declares ``alt=""``, explicitly.
  Forgetting an ``alt`` is silent, invisible in the render, and only
  shows to the screen reader — exactly the failure mode this repository
  gates elsewhere.
- **``fit=``** says how the image fills the ratio. Without it, an image
  whose natural ratio differs would be stretched.

What it does **not** have, deliberately:

- no ``skeleton=`` nor ``fallback=`` — both states are the image's own
  background, cf. ``theme.py``;
- no ``width=`` / ``height=`` — ``ratio`` replaces them, and ``attrs=``
  is still there for intrinsic dimensions;
- no ``rounded=`` — that is ``classes=``;
- no caption: that asks for ``<figure>`` / ``<figcaption>``, so another
  component, if the need comes up.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.primitives.image.theme import IMAGE_THEME
from bretzel.core.tree import Element


class Image(Component):
    """Render an image and optionally reserve its layout with ``ratio=``."""

    THEME: ClassVar[dict[str, Any]] = IMAGE_THEME
    THEME_KEY: ClassVar[str] = "image"
    DEFAULT_TAG: ClassVar[str] = "img"
    IS_CONTAINER: ClassVar[bool] = False

    # ``src`` stays design-time, as in ``avatar`` and for the same
    # reason: an image changes when the server's data changes (so at a
    # ``@refreshable``'s re-render), not under a client driver. No
    # binding is justified here — the bindable rule asks for a
    # client-side driver, there is none.
    src: str | None = reactive_prop(default=None, emit_attr=False, never_code=True)
    alt: str = reactive_prop(default="", emit_attr=False)
    ratio: str | None = reactive_prop(default=None, emit_attr=False)
    fit: str = reactive_prop(default="cover", emit_attr=False)

    def __init__(
        self,
        src: str | None = None,
        *,
        alt: str,
        ratio: str | None = None,
        fit: str | None = None,
        **kwargs: Any,
    ) -> None:
        # ``alt`` is keyword-only with NO default: omitting it is a
        # ``TypeError`` at the call, not a silently inaccessible render.
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(src=src, alt=alt, ratio=ratio, fit=fit, **kwargs)

    def render(self) -> Element:
        theme = self._resolved_theme()
        values = self._reactive_values

        # ``slot_class`` composes the root slot and discards the empty
        # ones — it is the charter's route, the one ``markdown`` /
        # ``code`` already take. It costs 1.6 µs more than the hand-made
        # join (measured, alternating A/B): 0.05 ms on a gallery of 30
        # images, against three different dialects among five sibling
        # components.
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
        # browser re-downloads THE CURRENT PAGE believing it is loading
        # an image. Found on ``ui.video`` while reading the dev server's
        # logs — the defect was identical here.
        if values.get("src"):
            attrs["src"] = values["src"]
        # Always emitted, even empty: an ``<img>`` with NO ``alt``
        # attribute is announced by its URL to the screen reader, whereas
        # an ``alt=""`` makes it ignored — which is the intended
        # behaviour for a decorative image. The two are not equivalent.
        # ``alt`` only makes sense on an image: on another ``tag=``, it
        # announces nothing to anybody. Same reason as ``menu_item``'s
        # ``type`` — set AFTER ``emit_attrs``, so outside the central
        # guard.
        if self._tag in ("img", "area", "input"):
            attrs["alt"] = values.get("alt") or ""
        # ``setdefault``: ``attrs={"loading": "eager"}`` must win. The
        # real case is the header image, which lazy delays to the LCP's
        # detriment.
        attrs.setdefault("loading", "lazy")
        attrs.setdefault("decoding", "async")
        return Element(tag=self._tag, attrs=attrs, children=())
