"""``Iframe`` — a third-party document, bounded by default.

What the component brings beyond the bare tag:

- **``title=`` mandatory.** A screen reader announces a page's frames by
  their title; without it, the user hears "frame", with no idea whether
  it contains a map, a video or a payment form. It is the exact
  counterpart of ``ui.image``'s ``alt``, and it is required for the same
  reason: the omission is invisible on screen.
- **``ratio=``** reserves the height. An embed is the leading cause of
  page jump, and an ``<iframe>`` with no dimensions falls back on a
  300×150 inherited from the nineties.
- **``loading="lazy"``** by default: an off-screen embed does not load.
- **``sandbox=``, with a non-empty default value** — cf. below.

The default sandbox
-------------------

``SANDBOX_BASELINE`` = ``allow-scripts allow-same-origin allow-forms
allow-popups``. The point is not what the list allows, it is what it
**does not** allow: as soon as a ``sandbox`` attribute is present,
``allow-top-navigation`` and ``allow-downloads`` are refused unless you
ask for them. In other words the embedded document can no longer
**change the page under your feet** nor **trigger a download** — the two
vectors that turn an embed into phishing.

The four permissions granted are the ones without which the common
embeds (map, player, payment widget) do not work at all. A default
everybody disables on the first try would teach one thing only: to
disable it.

⚠️ ``allow-scripts`` + ``allow-same-origin`` together, on a document of
**your own origin**, let that document remove its own ``sandbox``
attribute. It has no effect on a third-party embed (a different origin),
which is the use case. To frame a page of your own while really
protecting yourself from it, pass a list without ``allow-same-origin``.

Three ways out, all explicit:

- ``sandbox="allow-scripts"`` — your own list, instead of the baseline.
- ``sandbox=""`` — maximal sandbox (everything refused). Useful for
  static HTML of doubtful trust.
- ``sandbox=None`` — **no** attribute, so no restriction. It is the bare
  web's behaviour; you have to write it to get it.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

from bretzel.components.base import Component, reactive_prop
from bretzel.components.primitives.iframe.theme import IFRAME_THEME
from bretzel.core.tree import Element

#: Blocks top-navigation and downloads, lets the usual embeds work.
#: Cf. the module's docstring for the full reasoning.
SANDBOX_BASELINE: Final[str] = (
    "allow-scripts allow-same-origin allow-forms allow-popups"
)




class Iframe(Component):
    """Embed a titled document with a secure sandbox by default."""

    THEME: ClassVar[dict[str, Any]] = IFRAME_THEME
    THEME_KEY: ClassVar[str] = "iframe"
    DEFAULT_TAG: ClassVar[str] = "iframe"
    IS_CONTAINER: ClassVar[bool] = False

    # No bindable surface: an embed URL changes on a server re-render.
    # And letting a client driver rewrite a sandboxed frame's ``src``
    # would be a convenient way of pointing it elsewhere.
    src: str | None = reactive_prop(default=None, emit_attr=False, never_code=True)
    title: str = reactive_prop(default="", emit_attr=False)
    ratio: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        src: str | None = None,
        *,
        title: str,
        ratio: str | None = None,
        sandbox: str | None = SANDBOX_BASELINE,
        **kwargs: Any,
    ) -> None:
        # ``title`` keyword-only with NO default: omitting it is a
        # TypeError at the call, not an anonymous frame for the screen
        # reader.
        #
        # ``sandbox`` is NOT a ``reactive_prop``: the base layer drops
        # reactive ``None`` kwargs, yet here ``None`` is a VALUE —
        # "remove the attribute". The default therefore lives in the
        # signature, where it is also readable in ``help()`` and in
        # editor tooltips.
        self._sandbox = sandbox
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(src=src, title=title, ratio=ratio, **kwargs)

    def render(self) -> Element:
        theme = self._resolved_theme()
        values = self._reactive_values

        # ``classes=`` is set by the metaclass wrap — not here (duplicate).
        root_class = self.slot_class(
            "root", theme.get("ratios", {}).get(values.get("ratio"), "")
        )

        attrs = self.emit_attrs()
        attrs["class"] = root_class
        # ``src`` omitted rather than empty: a ``src=""`` is resolved
        # against the document's URL, so the frame would load THE
        # CURRENT PAGE inside itself. Found on ``ui.video`` while reading
        # the server's logs, and here the consequence would be worse — a
        # page containing itself, recursively.
        if values.get("src"):
            attrs["src"] = values["src"]
        attrs["title"] = values.get("title") or ""

        # A single branch for the three states: nothing passed → the
        # baseline (signature default), a list → the list, ``""`` →
        # emitted as is because ``"" is not None`` (MAXIMAL sandbox,
        # meaningful), ``None`` → no attribute, no restriction.
        if self._sandbox is not None:
            attrs["sandbox"] = self._sandbox

        attrs.setdefault("loading", "lazy")
        return Element(tag=self._tag, attrs=attrs, children=())
