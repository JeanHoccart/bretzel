"""``Title`` — page-level ``<title>`` override.

The framework's default ``<title>`` value comes from the
``@page(title="…")`` decorator (layout / route level). ``ui.title
("…")`` lets a page body OVERRIDE that decorator value at render
time — useful when the title depends on data the decorator couldn't
know (the current user's name, the loaded record's label, etc.) ::

    @page("/users/{user_id}")
    def user_detail(user_id: int) -> None:
        user = load_user(user_id)
        ui.title(f"{user.name} — Users")        # ← overrides default
        with ui.container():
            ui.heading(user.name)

Render mechanics : ``Title`` is a side-effect-only component. Its
``render()`` writes the string into ``RenderContext.head_title`` and
returns an empty :class:`FragmentNode` — nothing lands in the body. The
pipeline reads ``ctx.head_title`` when assembling the ``<head>`` and
supersedes ``@page(title=…)`` with it when present.

Last call wins : if two ``ui.title()`` calls happen in the same render
scope (a layout-level call + a page-level call, or a page setting a
title then a sub-component overriding it), the LAST one is the value
that ships. There is no auto-template / concatenation — the caller is
fully responsible for the final string shape.

No reactive support : ``<head>`` is rendered server-side at request
time. To make the title follow live state, push the new title via
the ``HX-Trigger`` event ``bretzel:title`` from a server action
(the runtime listens for it and updates ``document.title``).
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component
from bretzel.core.tree import FragmentNode as FragmentNode
from bretzel.render.context import maybe_current_context


class Title(Component):
    """Page-level ``<title>`` override (side-effect component)."""

    IS_CONTAINER: ClassVar[bool] = False
    # No reactive surface — ``<head>`` is SSR-only ; live-update is
    # served by the runtime's ``bretzel:title`` HX-Trigger flow.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    def __init__(
        self,
        text: str,
        **kwargs: Any,
    ) -> None:
        if kwargs:
            raise TypeError(
                f"Title takes only the positional text argument — "
                f"got extras : {sorted(kwargs)}. The ``<title>`` "
                f"element carries no attributes Bretzel uses."
            )
        if not isinstance(text, str):
            raise TypeError(
                f"Title text must be a str — got {type(text).__name__}. "
                f"For data-dependent titles, format the string in "
                f"Python ; reactive titles use the ``bretzel:title`` "
                f"HX-Trigger flow, not this component."
            )
        super().__init__()
        self._text = text

    def render(self) -> FragmentNode:  # type: ignore[override]
        """Write the title into the request's render context.

        Returns an empty :class:`FragmentNode` so the call is invisible
        in the body. The pipeline reads ``ctx.head_title`` separately
        when assembling the document head.
        """
        ctx = maybe_current_context()
        if ctx is None:
            raise RuntimeError(
                "ui.title(...) must be called inside a render scope "
                "(a @page or @layout handler). It writes to "
                "the request's RenderContext, which doesn't exist "
                "outside of one."
            )
        # Empty string is a misuse — skip rather than ship a blank
        # ``<title></title>`` (worse than the default).
        if self._text:
            ctx.head_title = self._text
        return FragmentNode(children=())


__all__ = ["Title"]
