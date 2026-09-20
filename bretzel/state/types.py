"""The business types a state field can carry, and how they travel.

State persists as JSON — that is what the store knows how to write, and
refusing pickle is deliberate (RCE). But the everyday types of a business
app do not fit in it: ``date``, ``Decimal``, ``UUID``, an ``Enum``. This
module says how each one is written and read back.

One table, two uses
-------------------

The same table serves to ENCODE before the write and to DECODE on read,
and decoding is also what coerces a form's string. Two tables would have
diverged at the first added type.

It is indexed by TYPE and not by field: a ``Decimal`` is written the same
way everywhere, so declaring it once is enough. That is also what lets the
annotation carry the information — ``amount: Decimal`` reads without
anything more in ``field()``.

⚠️ Do not confuse it with ``merge=``. The annotation says what the value
IS, ``field()`` says how it BEHAVES: a ``Decimal`` is an amount whatever
its use, whereas an ``int`` is additive or not depending on what the app
makes of it — no standard type can say that.

"""

from __future__ import annotations

import datetime as _dt
import decimal
import types as _pytypes
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, Literal, Union, get_args, get_origin

__all__ = ["register_type"]


@dataclass(frozen=True, slots=True)
class _Codec:
    """How a type is written to JSON and read back.

    ``subclasses`` says this codec also covers the type's HEIRS. Its
    ``decode`` then receives one more argument — the concrete class —,
    the only information the table does not carry.
    """

    encode: Callable[[Any], Any]
    decode: Callable[..., Any]
    subclasses: bool = False


#: The types ``json`` already knows how to write. Nothing to encode.
_JSON_NATIVE: Final[frozenset[type]] = frozenset(
    {str, int, float, bool, type(None), list, dict}
)

#: The SCALAR natives — the ones that leave encoding without even being
#: walked. ``list`` and ``dict`` are excluded: their elements can very
#: well ask for a codec.
_JSON_SCALAR: Final[frozenset[type]] = frozenset(
    {str, int, float, bool, type(None)}
)

#: Type → codec. Populated by :func:`register_type`, including for the
#: six the framework knows out of the box (just below).
_CODECS: dict[type, _Codec] = {}


def register_type(
    cls: type,
    *,
    encode: Callable[[Any], Any],
    decode: Callable[..., Any],
    subclasses: bool = False,
) -> None:
    """Register how ``cls`` is encoded to and decoded from JSON."""
    if not isinstance(cls, type):
        raise TypeError(
            f"register_type expects a CLASS, got {cls!r}. The table is "
            f"indexed by type — that is what lets the annotation carry "
            f"the information, with nothing added in field()."
        )
    _CODECS[cls] = _Codec(encode=encode, decode=decode, subclasses=subclasses)


# ── The six the framework knows ─────────────────────────────────────────
#
# Order does not matter here — the table is indexed by exact type — but
# the remark is worth writing down: a ``datetime`` IS a ``date`` in
# Python. ``encode_value`` walks up the inheritance chain and relies on
# MRO order to find the most precise one; ``decode_value``, which holds
# the DECLARED type, looks for an exact match.
register_type(_dt.datetime, encode=_dt.datetime.isoformat,
              decode=_dt.datetime.fromisoformat)
register_type(_dt.date, encode=_dt.date.isoformat,
              decode=_dt.date.fromisoformat)
register_type(_dt.time, encode=_dt.time.isoformat,
              decode=_dt.time.fromisoformat)
# ``str`` and not ``float``: that is the whole point of ``Decimal``.
# Going through a float would make ``Decimal("0.1")`` differ from itself
# after a round trip, and the registry would rewrite the field on every
# request believing it had changed.
register_type(decimal.Decimal, encode=str, decode=decimal.Decimal)
register_type(uuid.UUID, encode=str, decode=uuid.UUID)
# ``Enum`` is a FAMILY: it is the only one of the six whose declared type
# is an HEIR of the registered one (``hue: Colour``, codec on ``Enum``).
# It therefore goes through ``subclasses=True``, exactly as an app's base
# class would — and is no longer a special case.
register_type(
    Enum,
    encode=lambda member: member.value,
    decode=lambda raw, target: target(raw),
    subclasses=True,
)


def _codec_for_declared(type_: Any) -> _Codec | None:
    """The codec of a DECLARED type, families included.

    Exact first, then inheritance — but an ancestor only counts if it
    declared ``subclasses=True``. Without that condition, declaring a
    ``datetime`` field would fall back on the ``date`` codec (a
    ``datetime`` IS a ``date``) and silently lose the time. MRO order
    does the rest: the most precise one wins.
    """
    if not isinstance(type_, type):
        return None
    codec = _CODECS.get(type_)
    if codec is not None:
        return codec
    for ancestor in type_.__mro__[1:]:
        codec = _CODECS.get(ancestor)
        if codec is not None and codec.subclasses:
            return codec
    return None


def encode_value(value: Any) -> Any:
    """Render ``value`` in a form ``json`` accepts.

    Called by the registry BEFORE handing anything to the store — so once
    only, for both backends. Memory and Redis therefore see the same
    serialised representation.

    It descends into containers, and its twin :func:`decode_value` does
    the same: it is that SYMMETRY which allows writing ``list[date]`` or
    ``dict[str, Decimal]`` with no rule to remember.

    An unknown value passes through untouched: it is up to the store to
    refuse it, with the message that names the field.
    """
    # Fast exit on what ``json`` already writes, and that covers nearly
    # every field. Without it, each value paid an MRO walk before even
    # looking at the table. Measured on 2026-09-06: 381 ns → 168 ns per
    # scalar, and 387 µs → 137 µs on a list of 1 000 strings, where the
    # encoder "that does nothing" cost 6.7 times ``json.dumps`` of the
    # same list.
    if type(value) in _JSON_SCALAR:
        return value
    # ⚠️ Inheritance IS walked here WITHOUT requiring ``subclasses``: at
    # encoding time we hold a concrete value, not a declared type, and
    # the framework builds subclasses of ``date`` itself (``_BoundDate``,
    # set on a value read during a render so it carries its field's
    # name). Copying one date field from another therefore stored an
    # object the table could not find: it went to the store naked, memory
    # accepted it, Redis raised. MRO order gives the right answer with no
    # arbitration.
    for ancestor in type(value).__mro__:
        codec = _CODECS.get(ancestor)
        if codec is not None:
            return codec.encode(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        # ``tuple`` and ``set`` go out as a LIST — json knows only that
        # one. ``decode_value`` rebuilds them from the declared type,
        # which is exactly what makes accepting them possible.
        return [encode_value(v) for v in value]
    if isinstance(value, dict):
        return {encode_value(k): encode_value(v) for k, v in value.items()}
    return value


def decode_value(type_: Any, raw: Any) -> Any:
    """Read ``raw`` back as a ``type_``, or return it unchanged.

    It serves TWO paths at once, and that is on purpose: hydrating from
    the store and writing a form both go through :meth:`Field.__set__`. A
    ``date`` read back and a ``date`` typed in therefore follow exactly
    the same code.

    **It descends into containers**, symmetrically to
    :func:`encode_value`. As long as it did not, a ``list[date]`` was
    written as ``["2026-01-01"]`` and read back as strings: the framework
    had to REFUSE that field at declaration time, and that was one more
    rule to remember. Symmetry removes it.
    """
    if raw is None or type_ is Any:
        # ⚠️ Any is a CLASS since Python 3.11, so it passes the
        # isinstance(type_, type) below and makes isinstance(raw, Any)
        # raise. It is the declared escape hatch: nothing is touched, by
        # definition.
        return raw
    origin = get_origin(type_)

    # ── Containers: decode the ELEMENTS, then rebuild ────────────────
    if origin in (list, set, frozenset, tuple):
        args = [a for a in get_args(type_) if a is not Ellipsis]
        if not isinstance(raw, (list, tuple, set, frozenset)):
            return raw
        if args and len(args) == 1:
            elements = [decode_value(args[0], v) for v in raw]
        elif args and origin is tuple:
            # ``tuple[date, date]`` : un type PAR position.
            elements = [
                decode_value(args[i], v) if i < len(args) else v
                for i, v in enumerate(raw)
            ]
        else:
            elements = list(raw)
        return origin(elements)
    if origin is dict:
        if not isinstance(raw, dict):
            return raw
        args = get_args(type_)
        if len(args) == 2:
            return {
                decode_value(args[0], k): decode_value(args[1], v)
                for k, v in raw.items()
            }
        return raw

    target = _unwrap_optional(type_)
    if target is None:
        return raw
    # "Already the right type, leave it alone" — a handler writing a
    # real ``date`` does not pay a round trip through a string.
    if isinstance(raw, target):
        return raw
    codec = _codec_for_declared(target)
    if codec is None:
        return raw
    # A FAMILY receives the concrete class: it is the only information
    # the table does not carry, and it is what lets ``Enum`` register
    # through the public door instead of being a special case.
    return codec.decode(raw, target) if codec.subclasses else codec.decode(raw)


def _unwrap_optional(type_: Any) -> Any:
    """``T | None`` → ``T``. Any other union returns ``None``.

    Same rule as scalar coercion (``_resolve_scalar_target``): we only
    unwrap when ``None`` is the ONLY other member. A genuine union has no
    single target, so there is nothing to decode.
    """
    if isinstance(type_, type):
        return type_
    origin = get_origin(type_)
    if origin is Union or origin is _pytypes.UnionType:
        others = [a for a in get_args(type_) if a is not type(None)]
        if len(others) == 1 and isinstance(others[0], type):
            return others[0]
    return None


def is_storable(type_: Any) -> bool:
    """Can the declared type REACH the store, AND come back from it?

    Read by the metaclass to refuse AT STARTUP a field that could not
    persist — rather than on the first write, that is to say in
    production, the dev's memory store having let it through.

    **One rule, applied recursively**: a type passes if it has a codec
    (directly or through its family), if it is native to ``json``, if it
    is a container whose elements pass, a union whose members pass, a
    ``Literal`` of constants — or ``Any``, the acknowledged escape hatch,
    where the store arbitrates.

    There is no exception left to remember: ``list[date]``,
    ``dict[str, Decimal]``, ``tuple[date, date]`` and ``set[UUID]`` all
    pass, because encoding and decoding both descend into containers
    since 2026-09-06.
    """
    if type_ is None or type_ is Any:
        return True
    if isinstance(type_, type):
        return type_ in _JSON_NATIVE or _codec_for_declared(type_) is not None
    origin = get_origin(type_)
    if origin is Literal:
        return all(
            v is None or type(v) in _JSON_NATIVE for v in get_args(type_)
        )
    if origin is Union or origin is _pytypes.UnionType:
        return all(is_storable(a) for a in get_args(type_))
    if origin in (list, dict, tuple, set, frozenset):
        # ``tuple`` / ``set`` go out as a LIST and are REBUILT at decode
        # time from the declared type. Refusing them was one more rule
        # with nothing in return.
        return all(
            a is Ellipsis or is_storable(a) for a in get_args(type_)
        )
    return False
