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
(:func:`contains_file_input`). A prop would be a second way of saying
what the tree already says — and an occasion to forget it, which would
make ``ui.file_upload``'s form mode entirely mute.

**A form signs the names of the controls it renders.** The same reading
gives :func:`named_controls`, carried by a hidden input whose value only
the server can sign: a handler ``def save(form: Account)`` is hydrated
with those fields and no others, whatever the client adds to the body
(:func:`bretzel.server.handlers.writable_fields`).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component
from bretzel.components.base.events import posted_action
from bretzel.components.base.field_wiring import trigger_event
from bretzel.components.inputs.form.theme import FORM_THEME
from bretzel.core.tree import Element, Node
from bretzel.render.context import maybe_current_context

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


def upload_limits(
    nodes: tuple[Node, ...] | list[Node],
    declared: dict[int, tuple[Any, dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """What each ``ui.file_upload`` under these nodes declared to the render
    it accepts, by field name — the only file fields the server will take
    (``ui.input`` refuses ``type="file"``)."""
    found: dict[str, dict[str, Any]] = {}
    for node in nodes:
        entry = declared.get(id(node))
        if entry is not None and entry[0] is node:
            found[str(node.attrs["name"])] = entry[1]
        found.update(upload_limits(getattr(node, "children", None) or (), declared))
    return found


def named_controls(nodes: tuple[Node, ...] | list[Node]) -> set[str]:
    """The ``name`` of every control under these nodes — what the form
    will send. Wire fields (``_``-prefixed) are not controls; a ``name``
    inside raw HTML is not read: the framework did not render it."""
    names: set[str] = set()
    for node in nodes:
        attrs = getattr(node, "attrs", None) or {}
        name = attrs.get("name")
        if isinstance(name, str) and name and not name.startswith("_"):
            names.add(name)
        names |= named_controls(getattr(node, "children", None) or ())
    return names


def rendered_actions(attrs: dict[str, Any], nodes: tuple[Node, ...] | list[Node]) -> set[str]:
    """The action ids posted from this form: its own ``hx-post`` and its
    controls'. They go into its token, which then vouches for its fields
    only when one of THEM is posted (:func:`~bretzel.server.handlers.form_token`)."""
    own = posted_action(attrs)
    found: set[str] = {own} if own else set()
    for node in nodes:
        found |= rendered_actions(getattr(node, "attrs", None) or {},
                                  getattr(node, "children", None) or ())
    return found


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
        attrs = self.emit_attrs()
        cls_string = self.compose_class("root")
        if cls_string:
            attrs = {**attrs, "class": cls_string}
        return form_element(self._tag, attrs, self._render_children())


def form_element(tag: str, attrs: dict[str, Any], children_nodes: tuple[Node, ...]
                 ) -> Element:
    """A ``<form>`` around rendered children: the signed list of its
    controls, its own submit semantics, and multipart when a file is in it.

    Shared by :class:`Form` and every component that IS a form
    (:class:`~bretzel.components.inputs.message_input.MessageInput`): a
    form is one mechanism, and a second copy of these lines would be the
    one that forgets the multipart, and loses the file."""
    ctx = maybe_current_context()
    token = ctx.fields_input(
        named_controls(children_nodes),
        upload_limits(children_nodes, ctx.upload_limits),
        actions=rendered_actions(attrs, children_nodes),
    ) if ctx else None
    if token is not None:
        children_nodes = (*children_nodes, token)
    attrs = dict(attrs)
    # Opt out of the document-level ``hx-boost`` (shell.py) : a form's
    # submit must keep its native / explicit semantics, not get
    # AJAX-swapped into the page outlet. It speaks for the submit
    # only: the bridge gives the form's links their boost back
    # (``bridge.js``, ``beforeProcessNode``).
    attrs.setdefault("hx-boost", "false")
    # Validation lives on the state: the server's messages are the
    # contract. Left on, the browser's constraint validation cancels
    # the submit of an invalid ``type="email"`` in silence — no
    # request, so no message, only a native bubble the app cannot
    # style or word.
    # ``required`` / ``type=`` still serve assistive tech and mobile
    # keyboards; ``attrs={"novalidate": False}`` restores the browser.
    attrs.setdefault("novalidate", True)
    # A submit handled IN the page (a client gesture, no server action
    # answering the ``submit``) must not also leave natively: the browser
    # would GET the page again and wipe what the gesture did. htmx
    # prevents it for a server action; nothing else does for a client
    # gesture alone.
    gesture = attrs.get("bz-on:submit")
    if gesture and trigger_event(attrs) != "submit":
        attrs["bz-on:submit"] = f"$event.preventDefault(); {gesture}"
    if contains_file_input(children_nodes):
        # ``hx-encoding`` is what htmx reads; ``enctype`` is what the
        # browser reads if the submission leaves natively. Both say
        # the same thing to two different readers — it is not the
        # same mechanism written twice.
        attrs.setdefault("hx-encoding", "multipart/form-data")
        attrs.setdefault("enctype", "multipart/form-data")
    return Element(tag=tag, attrs=attrs, children=children_nodes)
