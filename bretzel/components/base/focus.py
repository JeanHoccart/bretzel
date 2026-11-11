"""Where a component takes the focus — one declaration, two readers.

A component declares :attr:`Component.FOCUS_TARGET`; from it come

- ``autofocus=True`` (any component that declares it): the element
  carrying the id is stamped :data:`DATA_BZ_AUTOFOCUS`, and the runtime
  focuses the target when that element ENTERS the page (rules in
  ``$bz.helpers.autofocus``, ``helpers.js``);
- ``.focus()`` / ``.blur()`` (the fields, through :class:`FocusCommands`).

Before, each field wrote its selector inside its own ``focus()`` — eight
hand-written copies plus the six pickers' ``focus_selector=``, and four
fields had none at all. A selector moved in one render and not in its
``focus()`` failed silently: ``querySelector`` returns ``null``.

Why the buttons have ``autofocus=`` and not ``.focus()``
--------------------------------------------------------
``.focus()`` finds its element by ``id``, and a component exposing an
imperative method carries an ``id`` on EVERY render
(``Component._needs_identity``). A button has none today; giving one to
every button of every page to serve a method nobody calls is not worth
it. ``autofocus=`` needs no id: the marker sits on the element itself.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.core.tree import Element, Node
from bretzel.runtime.protocol import DATA_BZ_AUTOFOCUS


def _selectors(cls: type) -> str:
    return json.dumps(list(cls.FOCUS_TARGET or ()))


def accept_autofocus(component: Any, value: Any) -> bool:
    """``autofocus=`` checked at construction: a bool known on the server
    — a literal, or a server state's field (``autofocus=form.in_error``,
    a stamped bool) — on a component that has a place to put the focus.

    Not a CLIENT binding: the mark is decided at render, and a client
    value can change with no render at all."""
    if getattr(value, "_is_bound_bool", False):
        value = bool(value)
    if value is False or value is None:
        return False
    name = type(component).__name__
    if value is not True:
        raise ComponentUsageError(
            f"{name}(autofocus={value!r}): True or False, known on the "
            "server (a literal or a server state's field). The focus goes "
            "to the field when its mark appears; to give it from the "
            "browser, call the field's ``.focus()`` in a handler."
        )
    if type(component).FOCUS_TARGET is None:
        raise ComponentUsageError(
            f"{name}(autofocus=True): {name} declares no place to put the "
            "focus (``FOCUS_TARGET``). ``autofocus=`` goes on a field "
            "(``ui.input``, ``ui.select``…), on the group that holds the "
            "choices (``ui.radio_group``, ``ui.toggle_group``) or on a "
            "button — `bretzel describe` lists who accepts it."
        )
    return True


def stamp_autofocus(component: Any, node: Element) -> Element:
    """``node`` with the autofocus marker on the element carrying the
    component's id — the root when no element carries it.

    On the id, not the root: the ``<input>`` of an iconed field, not its
    frame. A morph pairs that element by id, so a field the zone merely
    redraws keeps its node and is not focused again (the runtime's
    "entered the page" is "a node it has not seen")."""
    value = _selectors(type(component))
    stamped = _stamp_by_id(node, component.id, value)
    if stamped is not None:
        return stamped
    return Element(node.tag, {**node.attrs, DATA_BZ_AUTOFOCUS: value}, node.children)


def _stamp_by_id(node: Node, ident: str, value: str) -> Element | None:
    if not isinstance(node, Element):
        return None
    if node.attrs.get("id") == ident:
        return Element(node.tag, {**node.attrs, DATA_BZ_AUTOFOCUS: value}, node.children)
    for i, child in enumerate(node.children):
        stamped = _stamp_by_id(child, ident, value)
        if stamped is not None:
            children = (*node.children[:i], stamped, *node.children[i + 1:])
            return Element(node.tag, node.attrs, children)
    return None


class FocusCommands:
    """``.focus()`` / ``.blur()`` read from ``FOCUS_TARGET``.

    Mixed into the fields (before :class:`Component` in the bases).
    ``.blur()`` blurs whatever has the focus INSIDE the component — a
    toggle group's second button, a date range's end field — not the
    target, which may not be the focused one.
    """

    FOCUS_TARGET: ClassVar[tuple[str, ...] | None] = ()
    id: str

    def focus(self) -> str:
        return f"$bz.helpers.focusIn('{self.id}', {_selectors(type(self))})"

    def blur(self) -> str:
        return f"$bz.helpers.blurIn('{self.id}')"
