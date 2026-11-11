"""The imperative commands shared across component families.

Each method returns a client expression for an ``on_*``: it writes through
the binding when there is one, else dispatches a DOM command the component
listens to (``Component._value_command`` / ``_dispatch_command``).

Mixed in before :class:`Component` in the bases; each command still appears
in the component's ``IMPERATIVE``. What a single family shares lives at the
root of that family (``inputs/_wiring.py``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base.field_wiring import coerce_index


class ValueCommands:
    """``.set(value)`` / ``.clear()`` of a component that carries a value."""

    #: What ``.clear()`` writes.
    EMPTY_VALUE: ClassVar[Any] = ""

    _value_command: Callable[..., str]

    def _command_value(self, value: Any) -> Any:
        """What ``value`` becomes on its way to the client.

        A component whose ``value=`` takes a Python object (a ``date``, a
        ``time``) overrides it, so ``.set()`` accepts what ``value=`` accepts.
        """
        return value

    def set(self, value: Any) -> str:
        return self._value_command(self._command_value(value))

    def clear(self) -> str:
        return self.set(self.EMPTY_VALUE)


class IndexCommands:
    """``.set(index)`` / ``.next()`` / ``.prev()`` of a bounded index.

    ``.next()`` and ``.prev()`` always dispatch, binding or not: the
    destination depends on the live value and on bounds the server does not
    know at render. A write-through would bake ``index + 1`` and overrun.
    """

    _value_command: Callable[..., str]
    _dispatch_command: Callable[..., str]

    def set(self, index: int) -> str:
        """Go to ``index``. Write-through binding if there is one."""
        return self._value_command(coerce_index(index, minimum=0))

    def next(self) -> str:
        return self._dispatch_command("bz-next")

    def prev(self) -> str:
        return self._dispatch_command("bz-prev")
