"""``Form`` — wraps children in a ``<form>`` tag with submit handling.

Used as a context manager ::

    with ui.form(on_submit=save_handler):
        ui.input(name="label", placeholder="…")
        ui.button("Save", type="submit")

The dispatcher (runtime/_src/05_dispatcher.js) walks up to the
nearest ``<form>`` ancestor on submit and ships the FormData
verbatim — every named child input shows up in
``current_context().form_data`` on the server.

**A form containing a file encodes itself as multipart, by itself.**
htmx only builds a ``FormData`` body if the form tells it to
(``hx-encoding``); otherwise it URL-encodes, and a ``File`` does not
survive that — it leaves as the file's NAME, or as nothing. The form has
no prop to declare it: it renders its children before composing its
attributes, so it KNOWS what it contains
(:func:`contains_file_input`). A prop would have been a second way of
saying what the tree already says — and an occasion to forget it, which
made ``ui.file_upload``'s form mode entirely mute (measured on
2026-08-19 on the CRM's Import screen).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component
from bretzel.components.inputs.form.theme import FORM_THEME
from bretzel.core.tree import Element, Node

#: ``type=file`` in RAW HTML, however it is quoted. It is the only
#: branch that reads markup the framework did not produce: requiring
#: double quotes there would be assuming a convention about precisely
#: what we do not control.
_RAW_FILE_INPUT = re.compile(r"""type\s*=\s*["']?file\b""", re.IGNORECASE)


def contains_file_input(nodes: tuple[Node, ...] | list[Node]) -> bool:
    """Is there an ``<input type="file">`` anywhere under these nodes?

    Extracted to be testable on its own: it is what decides the form's
    encoding, and a walk that missed a level would silently give back a
    URL-encoded form.

    All four shapes of :class:`~bretzel.core.tree.Node` are covered:
    ``Element`` (tag + attrs + children), ``Fragment`` (children with no
    wrapper), ``Text`` (nothing to see) and ``Html`` — whose content is
    raw HTML the framework did not produce, so inspected as a string. The
    error there is ASYMMETRIC and that is what decides: a false positive
    encodes a form as multipart for nothing, a false negative loses a
    file in silence.
    """
    for node in nodes:
        attrs = getattr(node, "attrs", None) or {}
        if getattr(node, "tag", None) == "input" and attrs.get("type") == "file":
            return True
        raw = getattr(node, "html", None)
        if isinstance(raw, str) and _RAW_FILE_INPUT.search(raw):
            return True
        children = getattr(node, "children", None) or ()
        if children and contains_file_input(children):
            return True
    return False


class Form(Component):
    """HTML form wrapper. Children are added via ``with`` block."""

    THEME: ClassVar[dict[str, Any]] = FORM_THEME
    THEME_KEY: ClassVar[str] = "form"
    DEFAULT_TAG: ClassVar[str] = "form"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    EVENTS: ClassVar[tuple[str, ...]] = ("submit",)

    def __init__(
        self,
        *,
        on_submit: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(on_submit=on_submit, **kwargs)

    def render(self) -> Element:
        children_nodes = self._render_children()
        attrs = self.emit_attrs()
        cls_string = self.compose_class("root")
        if cls_string:
            attrs = {**attrs, "class": cls_string}
        # Opt out of the document-level ``hx-boost`` (shell.py) : a form's
        # submit must keep its native / explicit semantics, not get
        # AJAX-swapped into the page outlet.
        attrs.setdefault("hx-boost", "false")
        if contains_file_input(children_nodes):
            # ``hx-encoding`` is what htmx reads; ``enctype`` is what the
            # browser reads if the submission leaves natively. Both say
            # the same thing to two different readers — it is not the
            # same mechanism written twice.
            attrs.setdefault("hx-encoding", "multipart/form-data")
            attrs.setdefault("enctype", "multipart/form-data")
        return Element(tag=self._tag, attrs=attrs, children=children_nodes)
