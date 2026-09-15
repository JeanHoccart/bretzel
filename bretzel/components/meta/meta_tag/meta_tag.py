"""``MetaTag`` — ``<meta>`` injection into the document ``<head>``.

Adds ``<meta>`` elements to the rendered ``<head>`` for SEO, social
cards, viewport, and HTTP-equiv hints. Render-time side-effect : the
component contributes nothing to the body, just appends an
:class:`Element` to ``RenderContext.head_extras`` which the pipeline
serializes into the document head.

Usage ::

    ui.meta_tag(name="description", content="Internal tools for Acme")
    ui.meta_tag(property="og:title",  content="Dashboard — Acme")
    ui.meta_tag(property="og:image",  content="https://acme.com/og.png")
    ui.meta_tag(name="twitter:card",  content="summary_large_image")
    ui.meta_tag(http_equiv="refresh", content="30; url=/logout")

Pick exactly ONE identifier kwarg (``name=`` / ``property=`` /
``http_equiv=``) per call — passing two raises. ``content=`` is
required. ``charset=`` and ``viewport=`` are NOT exposed : the
framework ships those in :mod:`bretzel.render.shell` for every page,
and overriding them via a component would only invite drift.

No auto-dedup : the app is responsible for not emitting multiple
``<meta name="description">`` tags. The pipeline appends every call
verbatim in source order.

No reactive support : the document head is SSR-only.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component
from bretzel.core.tree import Element
from bretzel.core.tree import FragmentNode as FragmentNode
from bretzel.render.context import maybe_current_context

# The three valid identifier kwargs for a ``<meta>`` tag. ``charset``
# and ``viewport`` deliberately omitted (framework-owned per shell.py).
_IDENTIFIER_KWARGS: tuple[str, ...] = ("name", "property", "http_equiv")


class MetaTag(Component):
    """``<meta>`` element pushed into the request's head_extras."""

    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    def __init__(
        self,
        *,
        name: str | None = None,
        property: str | None = None,
        http_equiv: str | None = None,
        content: str,
        **kwargs: Any,
    ) -> None:
        if kwargs:
            raise TypeError(
                f"MetaTag accepts only ``name=`` / ``property=`` / "
                f"``http_equiv=`` / ``content=`` — got extras : "
                f"{sorted(kwargs)}."
            )
        provided = [
            (key, val) for key, val in (
                ("name", name),
                ("property", property),
                ("http_equiv", http_equiv),
            ) if val is not None
        ]
        if not provided:
            raise TypeError(
                "MetaTag needs exactly one of name= / property= / "
                "http_equiv= — none provided. A <meta> tag without "
                "an identifier is invalid HTML."
            )
        if len(provided) > 1:
            keys = ", ".join(k for k, _ in provided)
            raise TypeError(
                f"MetaTag accepts only ONE identifier kwarg — got "
                f"multiple : {keys}. Pick the one that matches the "
                f"semantics : ``name=`` (description / robots / "
                f"twitter:*), ``property=`` (Open Graph og:*), or "
                f"``http_equiv=`` (refresh / X-UA-Compatible)."
            )
        if not isinstance(content, str):
            raise TypeError(
                f"MetaTag content must be a str — got "
                f"{type(content).__name__}."
            )
        super().__init__()
        self._identifier_key, self._identifier_value = provided[0]
        self._content = content

    def render(self) -> FragmentNode:  # type: ignore[override]
        """Append a ``<meta>`` Element to the request's head_extras.

        Returns an empty :class:`FragmentNode` — the tag lives in the
        document head, not the body.
        """
        ctx = maybe_current_context()
        if ctx is None:
            raise RuntimeError(
                "ui.meta_tag(...) must be called inside a render scope "
                "(a @page or @layout handler). It writes to "
                "the request's RenderContext, which doesn't exist "
                "outside of one."
            )
        # ``http_equiv`` kwarg → ``http-equiv`` HTML attribute (Python
        # snake_case → HTML kebab-case is the standard Bretzel norm).
        attr_name = self._identifier_key.replace("_", "-")
        meta_element = Element(
            tag="meta",
            attrs={attr_name: self._identifier_value, "content": self._content},
            children=(),
        )
        ctx.head_extras.append(meta_element)
        return FragmentNode(children=())


__all__ = ["MetaTag"]
