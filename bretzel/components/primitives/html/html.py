"""``Html`` — the way out: injecting verbatim markup.

The escape node has existed from the start —
:class:`bretzel.core.tree.Html`, whose docstring says it is "the only
legitimate way to inject markup that the framework did not produce".
Four components use it (``code``, ``markdown``, ``draggable``'s SVG, the
calendar's SSR). It simply was **not open to application code**: an app
with a third-party embed, already sanitised CMS content or a map
``<iframe>`` had no path, short of writing a component.

Why ``ui.html`` and not ``ui.raw_html``: the name joins the family of
content primitives — ``ui.text``, ``ui.markdown``, ``ui.code``, all
named after what they display. Naming it after its risk would make it
the only exception, and above all a frightening name only warns one
person, once, at the moment they write it. What warns at every addition,
for ever, is the ``tests/consistency/test_ui_html_call_sites_are_listed.py``
gate, which freezes the repository's calls: adding one makes it go red.

⚠️ **It is an XSS sink.** Everything that goes in comes out verbatim in
the page. The rule is simple: the content must be **either a literal you
wrote**, or a value passed through a sanitiser (bleach, nh3, …) just
before. Never a string from the user as is. If you hesitate, it is
``ui.markdown`` you want: it escapes embedded HTML and rewrites
dangerous URLs.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    ComponentUsageError,
    reject_component,
)
from bretzel.components.primitives.html.theme import HTML_THEME
from bretzel.core.tree import Element, HtmlNode
from bretzel.state.scopes.client import ClientBinding


class Html(Component):
    """Inject trusted HTML verbatim without escaping it."""

    THEME: ClassVar[dict[str, Any]] = HTML_THEME
    THEME_KEY: ClassVar[str] = "html"
    IS_CONTAINER: ClassVar[bool] = False
    # No reactive surface, and it is not an oversight: a binding path on
    # raw HTML would mean "the runtime writes markup from client state",
    # so a client-driven XSS sink. The constructor REJECTS, it does not
    # degrade silently.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    def __init__(
        self,
        text: str | None = None,
        **kwargs: Any,
    ) -> None:
        if isinstance(text, ClientBinding):
            raise ComponentUsageError(
                "ui.html does not accept a ClientBinding for ``text=`` — "
                "making the runtime write raw markup from client state is "
                "a client-driven XSS sink, and the server can no longer "
                "guarantee anything about what lands in the page. For HTML "
                "that changes, keep the source in a PageState and re-render "
                "the zone (@refreshable + refresh): the server stays the "
                "markup's author."
            )
        reject_component(
            text,
            owner="ui.html",
            prop="text",
            because=(
                "``text`` is a markup STRING. A Component would be "
                "stringified there as its Python repr and injected as is."
            ),
            instead=(
                "To compose, put the components AROUND: "
                "``with ui.vstack(): ui.html(src) ; ui.badge(…)``."
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
        # The wrapper exists so the universal kwargs (``classes``,
        # ``id``, ``attrs``, ``visible``, ``tooltip``) have somewhere to
        # land — same reason as at ``markdown`` and ``code``. ``tag=``
        # changes it (``span`` in an inline context); nothing removes it,
        # and that is accepted: with no carrier, half the universal API
        # would fall into the void without saying so.
        return Element(
            tag=self._tag, attrs=attrs, children=(HtmlNode(self._text),)
        )
