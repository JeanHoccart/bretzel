"""``EventPayload`` — a typed value object a component sends with an action.

Some components need to hand their handler something a form field cannot
express: a drag reports *which* item moved, from where, to where. Bretzel
already has the shape for "the handler declares a type and the framework
fills it in" — ``def save(form: MyForm)``, ``def load(q: Query)``. This is
that shape for **event payloads**, which differ from both:

- a ``ServerState`` is *persisted* state, hydrated from named form fields;
- a ``Query`` is built by the component and passed as a plain argument;
- an ``EventPayload`` is produced by the **runtime**, in the browser, and
  travels as one JSON blob in a single hidden field.

Declaring one is a frozen dataclass plus the wire field name ::

    @dataclasses.dataclass(frozen=True)
    class Move(EventPayload):
        WIRE_FIELD: ClassVar[str] = "bz_move"
        item_key: str = ""
        from_index: int = -1

    def reorder(m: Move) -> None:      # the server layer fills it in
        ...

**Why a base class and not a special case for ``Move``.** The injection
rule in ``server/routing/actions.py`` recognises *this type*, so it never
learns the vocabulary of any one component. The next component with a
payload — a resize reporting its new dimensions, a canvas reporting a
stroke — subclasses this and is injected for free, instead of reopening the
same discussion in the dispatch path.

Coercion is deliberately narrow: the declared annotation is applied when
it is one of ``str`` / ``int`` / ``float`` / ``bool``, and anything else is
passed through untouched. The wire is JSON written by our own runtime, not
user input, so this is a *typing* convenience — the security boundary is
the HMAC on the action, not this function.
"""

from __future__ import annotations

import dataclasses
import json
import typing
from typing import Any, ClassVar, TypeVar

from bretzel.core.errors import BretzelError

T = TypeVar("T", bound="EventPayload")

_SCALARS: tuple[type, ...] = (str, int, float, bool)


@dataclasses.dataclass(frozen=True)
class EventPayload:
    """Base for the typed payloads a component's runtime sends to a handler."""

    #: The form field the runtime writes the JSON blob into. Subclasses
    #: MUST override it — the default is deliberately invalid so that a
    #: subclass which forgets fails loudly at decode time rather than
    #: silently receiving nothing.
    WIRE_FIELD: ClassVar[str] = ""

    @classmethod
    def from_wire(cls: type[T], raw: str) -> T:
        """Build an instance from the JSON blob the runtime wrote.

        Unknown keys are ignored rather than raising: the runtime may
        legitimately be newer than the server it talks to (a cached
        ``runtime.js`` after a deploy), and dropping a field the handler
        never declared is the harmless half of that skew.
        """
        if not cls.WIRE_FIELD:
            raise BretzelError(
                f"{cls.__name__} does not declare WIRE_FIELD — the server "
                f"cannot know which form field carries it."
            )
        try:
            data = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise BretzelError(
                f"{cls.__name__}: the {cls.WIRE_FIELD!r} field did not "
                f"contain JSON ({exc}). This blob is written by the Bretzel "
                f"runtime, so a malformed one means the client and server "
                f"disagree on the wire format."
            ) from exc
        if not isinstance(data, dict):
            raise BretzelError(
                f"{cls.__name__}: expected a JSON object in "
                f"{cls.WIRE_FIELD!r}, got {type(data).__name__}."
            )

        hints = typing.get_type_hints(cls)
        kwargs: dict[str, Any] = {}
        for f in dataclasses.fields(cls):
            if f.name not in data:
                continue
            kwargs[f.name] = _coerce(data[f.name], hints.get(f.name))
        return cls(**kwargs)


#: What a wire string means when a field is declared ``bool``.
#: ⚠️ ``bool("false")`` is **True** — every non-empty string is truthy, so
#: the naive ``annotation(value)`` silently inverts a flag instead of
#: raising like ``int("abc")`` would. No ``Move`` field is a bool today,
#: but this base class exists precisely so the next component subclasses
#: it, and a silently-inverted guard is the worst kind of latent bug.
_FALSEY = frozenset({"", "false", "0", "no", "off", "null", "none"})


def _coerce(value: Any, annotation: Any) -> Any:
    """Apply the declared scalar type, or pass the value through."""
    if annotation is bool and isinstance(value, str):
        return value.strip().lower() not in _FALSEY
    if annotation in _SCALARS and not isinstance(value, annotation):
        try:
            return annotation(value)
        except (TypeError, ValueError):
            # Keep the raw value: a handler reading a surprising type is
            # easier to debug than one that never ran.
            return value
    return value
