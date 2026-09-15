"""``Code`` — block code display with optional Pygments highlighting.

Archetype 1 (leaf, no slot, no ``with`` block). Content is a positional
``text`` argument ; ``lang=`` chooses the Pygments lexer (default
``python``).

Reactive contract :

- ``text=str`` : full server-side Pygments highlight, coloured HTML
  inside the wrapper.
- ``text=ClientBinding | ClientExpression`` : delegate to
  :meth:`Component.emit_text_slot` which emits a ``<span bz-text="…">``
  inside our ``<code>``. No highlighting on the reactive path — same
  trade-off as :class:`Text` / :class:`Heading`.

**``text=Component`` is REJECTED** (``ComponentUsageError``), unlike the
generic ``str | Component | ClientBinding`` slot contract most other
components honour. ``text`` is the SOURCE Pygments highlights, not a
content slot — a Component there used to be silently stringified to
its Python ``repr()`` and syntax-highlighted as nonsense (cf. traps.md
§ "Code.text=Component rendait du charabia"). Same class of bug, same
fix shape, as :class:`Markdown`'s ``ComponentUsageError`` on
``ClientBinding``. To compose Code with other components, wrap them :
``with ui.vstack(): ui.code(src) ; ui.button("Copy")``.

The ``.bz-code`` marker class on the wrapper is the hook the global
Pygments stylesheet (injected in :mod:`bretzel.render.shell`) scopes
its colour rules to.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, ClassVar

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

from bretzel.components.base import (
    Component,
    reactive_prop,
    reject_component,
)
from bretzel.components.primitives.code.theme import CODE_THEME
from bretzel.core.escape import escape_html
from bretzel.core.tree import Element, HtmlNode
from bretzel.state.scopes.client import ClientBinding

# Reused across every Code render. ``nowrap=True`` skips Pygments'
# own ``<div class="highlight"><pre>...`` outer shell — we emit our
# own ``<pre><code>`` so the wrapper carries the theme classes.
_FORMATTER = HtmlFormatter(nowrap=True)


@lru_cache(maxsize=256)
def highlight_code(text: str, lang: str) -> str:
    """Pygments highlight with a (text, lang) LRU cache.

    Public helper : reused by :class:`Markdown` for fenced code blocks.
    Static snippets re-rendered every request hit the cache free.
    ``ClassNotFound`` falls back to plain escaped text for unknown languages.
    """
    try:
        lexer = get_lexer_by_name(lang)
    except ClassNotFound:
        return escape_html(text)
    return highlight(text, lexer, _FORMATTER)


class Code(Component):
    """Block code with Pygments syntax highlighting."""

    THEME: ClassVar[dict[str, Any]] = CODE_THEME
    THEME_KEY: ClassVar[str] = "code"
    DEFAULT_TAG: ClassVar[str] = "pre"
    IS_CONTAINER: ClassVar[bool] = False
    # Curated reactive surface — the text content. ``lang`` is design-
    # time. Text is the first positional arg.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("text",)

    lang: str = reactive_prop(default="python", emit_attr=False)

    def __init__(
        self,
        text: str | ClientBinding | None = None,
        *,
        lang: str | None = None,
        **kwargs: Any,
    ) -> None:
        reject_component(
            text,
            owner="Code",
            prop="text",
            because=(
                "``text`` est la SOURCE à syntax-highlighter, une string "
                "passée à Pygments. Un Component y était silencieusement "
                "stringifié en son repr Python et coloré comme si c'était "
                "du code source."
            ),
            instead=(
                "Pour composer du code avec d'autres composants, mets-les "
                "AUTOUR : ``with ui.vstack(): ui.code(src) ; "
                "ui.button('Copy')``."
            ),
        )
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(lang=lang, **kwargs)
        # ``ClientBinding.__bool__`` raises — same pattern as Text /
        # Heading. Keep ``None`` → ``""``. Component already rejected
        # above ; adopt_slot is a pass-through for str/ClientBinding.
        self._text = "" if text is None else Component.adopt_slot(text)

    def render(self) -> Element:
        cls = self.compose_class("root", apply_variant_size_modifiers=False)
        attrs = self.emit_attrs()
        if cls:
            attrs = {**attrs, "class": cls}

        if isinstance(self._text, ClientBinding):
            # ClientExpression is a ClientBinding subclass — the base
            # helper handles both shapes correctly. Returns a <span>
            # we wrap in <code> ; no highlighting on the reactive path.
            text_node = self.emit_text_slot(self._text)
            inner = Element(tag="code", attrs={}, children=(text_node,))
            return Element(tag=self._tag, attrs=attrs, children=(inner,))

        text = str(self._text)
        lang = self._reactive_values.get("lang") or "python"
        inner_html = f"<code>{highlight_code(text, lang)}</code>"
        return Element(tag=self._tag, attrs=attrs, children=(HtmlNode(inner_html),))
