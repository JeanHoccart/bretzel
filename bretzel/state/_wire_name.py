"""The ``name`` a bound control sends its field under — and how to read it.

A control bound to a state field (``ui.input(value=Delivery().mode)``)
derives its HTML ``name``, and the field name alone does not say whose
field it is. If two states with a ``mode`` on one page shared the name
``mode``:

- in a form, ``Delivery.mode`` and ``Payment.mode`` would both go as
  ``mode``: ``save(mode)`` would get the last one and lose the other;
- ``save(d: Delivery, p: Payment)`` would get ``d.mode == p.mode`` — the
  payment's value WRITTEN into the delivery, then saved;
- every radio named ``mode`` on the page would form ONE group for the
  browser, so ticking the delivery would untick the payment.

The name therefore says whose field it is: ``Delivery.mode`` for the instance
by default, ``Delivery[paris].mode`` for a keyed one — the class's name
and the key, as the client store addresses it (``$bz.state.Delivery``).

⚠️ Not ``Delivery.default.mode``: three dotted segments with a capital
first are the CLIENT-STATE snapshot the bridge adds to every request
(``parse_client_payload``), which never reaches a handler.

On the server, a handler still asks for what it wants:

- ``def save(d: Delivery)`` reads ``Delivery.<field>`` (or the bare
  ``<field>`` of a control the app named itself);
- ``def save(mode: str)`` reads ``mode`` if the app named a control so,
  else THE one ``<State>.mode`` sent — and refuses two (:func:`lookup`);
- ``**kwargs`` receives the names as they travel.

An explicit ``name="…"`` is the app's own word: never rewritten.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

DEFAULT_KEY = "default"

#: ``Class.field`` or ``Class[key].field`` — one dot, any class name
#: (``_Picks`` and ``draft`` are classes too).
_WIRE = re.compile(r"^([A-Za-z_]\w*)(?:\[([^\]]+)\])?\.(\w+)$")


class AmbiguousFieldError(LookupError):
    """Two states sent a field of the same name, and the handler asked for
    the bare name — which one it means cannot be guessed."""


def wire_name(class_name: str, key: str | None, field: str) -> str:
    """``Delivery.mode`` / ``Delivery[paris].mode``."""
    if key is None or key == DEFAULT_KEY:
        return f"{class_name}.{field}"
    return f"{class_name}[{key}].{field}"


def split_wire_name(name: str) -> tuple[str, str, str] | None:
    """``(class name, key, field)`` of a wire name, else ``None``."""
    found = _WIRE.match(name)
    if found is None:
        return None
    cls, key, field = found.groups()
    return cls, key or DEFAULT_KEY, field


def state_view(form_data: Mapping[str, Any], state_cls: type) -> dict[str, Any]:
    """The submission as ``state_cls``'s default instance reads it:
    ``{field: value}`` — its wire names first, else the bare field names
    of controls the app named itself."""
    view: dict[str, Any] = {}
    for field in state_cls._all_fields():  # type: ignore[attr-defined]
        qualified = wire_name(state_cls.__name__, DEFAULT_KEY, field)
        if qualified in form_data:
            view[field] = form_data[qualified]
        elif field in form_data:
            view[field] = form_data[field]
    return view


def lookup(form_data: Mapping[str, Any], name: str) -> tuple[bool, Any]:
    """``(found, value)`` for a handler parameter or ``form_value(name)``.

    ``name`` itself if sent (a control the app named so), else the ONE
    ``<State>.name`` sent. Two of them raise :class:`AmbiguousFieldError`:
    picking one would be the silent loss this module exists to end.
    """
    if name in form_data:
        return True, form_data[name]
    matches = [
        key for key in form_data
        if (parts := split_wire_name(key)) is not None and parts[2] == name
    ]
    if not matches:
        return False, None
    if len(matches) > 1:
        owners = ", ".join(sorted(matches))
        raise AmbiguousFieldError(
            f"Two controls sent a field named {name!r} ({owners}): asking "
            f"for {name!r} alone cannot say which one. Take the state "
            f"instead — `def handler(d: Delivery)` reads `d.{name}` — or "
            f"give one control its own `name=`."
        )
    return True, form_data[matches[0]]


__all__ = [
    "DEFAULT_KEY",
    "AmbiguousFieldError",
    "lookup",
    "split_wire_name",
    "state_view",
    "wire_name",
]
