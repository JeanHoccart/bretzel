"""``Markdown`` — render markdown text to styled HTML.

Archetype 1 (leaf, no slot, no ``with`` block). Uses ``mistune`` 3.x
to parse markdown server-side and emit HTML carrying bretzel
typography classes from :data:`MARKDOWN_THEME`. Fenced code blocks
delegate to :func:`highlight_code` (Pygments) so a snippet looks
identical whether it comes from a standalone ``ui.code(...)`` or
from inside a markdown document.

**Server-rendered only.** Markdown does NOT accept a :class:`ClientBinding`
— a binding path would collapse the mistune structure (h*/p/ul/blockquote/…)
to plain text. ``BINDABLE_PROPS = ()`` ; passing a binding raises
:class:`ComponentUsageError`. For a live preview, bind the source to a
server :class:`PageState` and ``refresh()`` the panel from a change handler.

Security :

- ``escape=True`` on the mistune renderer → embedded HTML tags inside
  the markdown source are escaped to text, not rendered. ``<script>``
  becomes ``&lt;script&gt;``.
- ``safe_url`` (mistune built-in) rewrites ``javascript:``,
  ``vbscript:``, ``file:`` and non-image ``data:`` URLs in links and
  images to ``#harmful-link``.

The ``bz-markdown`` marker class on the wrapper is the hook for user
CSS overrides if the baked typography isn't enough for a specific
context.
"""

from __future__ import annotations

from typing import Any, ClassVar

import mistune
from mistune.util import escape as escape_text
from mistune.util import safe_entity, striptags

from bretzel.components.base import (
    Component,
    ComponentUsageError,
    reject_component,
)
from bretzel.components.primitives.code import CODE_THEME, highlight_code
from bretzel.components.primitives.markdown.theme import MARKDOWN_THEME
from bretzel.core.tree import Element, HtmlNode
from bretzel.state.scopes.client import ClientBinding


class _BretzelMarkdownRenderer(mistune.HTMLRenderer):
    """Mistune renderer that bakes Tailwind classes from the theme.

    Built per-render with the *resolved* theme so user overrides on
    ``app.theme.components.markdown`` propagate. Fenced code blocks
    delegate to :func:`highlight_code` from the Code module so
    server-side Pygments + the ``bz-code`` Pygments stylesheet apply
    transparently.
    """

    def __init__(
        self, theme_slots: dict[str, str], code_root: str = ""
    ) -> None:
        super().__init__(escape=True)
        self._slots = theme_slots
        # ``code_root`` = le slot root RÉSOLU de Code. Le renderer n'est pas un
        # Component → pas de ``_resolved_theme`` : le call-site le passe. Lire
        # ``CODE_THEME`` ici contournerait un ``Theme(components={"code": …})``.
        self._code_root = code_root

    def _cls(self, name: str) -> str:
        v = self._slots.get(name, "")
        return f' class="{v}"' if v else ""

    # ── Block ──────────────────────────────────────────────────────────

    def heading(self, text: str, level: int, **attrs: Any) -> str:
        return f"<h{level}{self._cls(f'h{level}')}>{text}</h{level}>\n"

    def paragraph(self, text: str) -> str:
        return f"<p{self._cls('p')}>{text}</p>\n"

    def list(self, text: str, ordered: bool, **attrs: Any) -> str:
        tag = "ol" if ordered else "ul"
        return f"<{tag}{self._cls(tag)}>\n{text}</{tag}>\n"

    def list_item(self, text: str) -> str:
        return f"<li{self._cls('li')}>{text}</li>\n"

    def block_quote(self, text: str) -> str:
        return f"<blockquote{self._cls('blockquote')}>\n{text}</blockquote>\n"

    def block_code(self, code: str, info: str | None = None) -> str:
        lang = (info or "").strip() or "text"
        inner = highlight_code(code, lang)
        # Code's root slot has no margin-bottom (standalone ``ui.code``
        # is laid out by its parent). Inside markdown a ``mb-3`` is
        # needed so consecutive fenced blocks don't touch.
        wrapper_cls = f"{self._code_root} mb-3"
        return f'<pre class="{wrapper_cls}"><code>{inner}</code></pre>\n'

    def thematic_break(self) -> str:
        return f"<hr{self._cls('hr')}>\n"

    # ── Inline ─────────────────────────────────────────────────────────

    def codespan(self, text: str) -> str:
        # Mistune passes codespan content RAW (unlike strong/em/link, whose
        # children are already rendered). Missing this escape would inject
        # literal ``<script>`` (from `` `<script>` ``) and kill the render.
        return f"<code{self._cls('code')}>{escape_text(text)}</code>"

    def link(self, text: str, url: str, title: str | None = None) -> str:
        href = self.safe_url(url)
        title_attr = f' title="{safe_entity(title)}"' if title else ""
        return f'<a href="{href}"{self._cls("a")}{title_attr}>{text}</a>'

    def image(self, text: str, url: str, title: str | None = None) -> str:
        src = self.safe_url(url)
        # ``text`` arrives pre-rendered (may contain nested ``<strong>``
        # / ``<em>`` tags from a markdown alt like ``![**bold**](…)``).
        # ``striptags`` matches mistune's default — alt attributes are
        # plain text, no formatting.
        alt = striptags(text) if text else ""
        title_attr = f' title="{safe_entity(title)}"' if title else ""
        return f'<img src="{src}" alt="{alt}"{self._cls("img")}{title_attr}>'

    def strong(self, text: str) -> str:
        return f"<strong{self._cls('strong')}>{text}</strong>"

    def emphasis(self, text: str) -> str:
        return f"<em{self._cls('em')}>{text}</em>"

    # ── Table plugin overrides (cf. mistune.plugins.table) ─────────────

    def table(self, text: str) -> str:
        return f"<table{self._cls('table')}>\n{text}</table>\n"

    def table_head(self, text: str) -> str:
        return f"<thead>\n<tr>{text}</tr>\n</thead>\n"

    def table_body(self, text: str) -> str:
        return f"<tbody>\n{text}</tbody>\n"

    def table_row(self, text: str) -> str:
        return f"<tr>{text}</tr>\n"

    def table_cell(
        self, text: str, align: str | None = None, head: bool = False
    ) -> str:
        tag = "th" if head else "td"
        align_attr = f' style="text-align: {align}"' if align else ""
        return f"<{tag}{self._cls(tag)}{align_attr}>{text}</{tag}>\n"

    # ── Strikethrough plugin (emits ``del``) ───────────────────────────

    def strikethrough(self, text: str) -> str:
        return f"<del{self._cls('del')}>{text}</del>"


class Markdown(Component):
    """Block markdown rendering with bretzel typography. Server-only."""

    THEME: ClassVar[dict[str, Any]] = MARKDOWN_THEME
    THEME_KEY: ClassVar[str] = "markdown"
    IS_CONTAINER: ClassVar[bool] = False
    # No reactive surface — see the module docstring. The whole point
    # of Markdown is its structure ; a binding path would collapse
    # that to plain text and silently mislead the user.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    def __init__(
        self,
        text: str | None = None,
        **kwargs: Any,
    ) -> None:
        if isinstance(text, ClientBinding):
            raise ComponentUsageError(
                "Markdown does not accept a ClientBinding for ``text=`` — "
                "the binding path would emit ``<span bz-text>`` and lose all "
                "markdown structure. For a live preview, bind the source "
                "to a PageState field and ``refresh()`` the panel from a "
                "change handler (see the Server playground pattern)."
            )
        reject_component(
            text,
            owner="Markdown",
            prop="text",
            because=(
                "``text`` est la SOURCE markdown, une string parsée par "
                "mistune. Un Component y était silencieusement stringifié "
                "en son repr Python et parsé comme du texte."
            ),
            instead=(
                "Pour composer du markdown avec des composants, mets-les "
                "AUTOUR : ``with ui.vstack(): ui.markdown(src) ; "
                "ui.badge(…)``."
            ),
        )
        super().__init__(**kwargs)
        self._text = "" if text is None else str(text)

    def render(self) -> Element:
        cls = self.compose_class("root", apply_variant_size_modifiers=False)
        attrs = self.emit_attrs()
        if cls:
            attrs = {**attrs, "class": cls}

        if not self._text:
            return Element(tag=self._tag, attrs=attrs, children=())

        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        # Le thème de Code résolu AUSSI : un override de ``code`` doit
        # atteindre les blocs fencés du markdown comme il atteint
        # ``ui.code``.
        code_slots = self._resolved_theme("code", CODE_THEME).get("slots", {})
        renderer = _BretzelMarkdownRenderer(slots, code_slots.get("root", ""))
        md = mistune.create_markdown(
            renderer=renderer,
            plugins=["table", "strikethrough"],
        )
        html = md(self._text)
        return Element(tag=self._tag, attrs=attrs, children=(HtmlNode(html),))
