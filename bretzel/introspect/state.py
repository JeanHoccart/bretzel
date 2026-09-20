"""The state classes, read live.

Scope / persistence, every field with its type, its default and its
validators, the computed ones. It is the anti-rust mirror of the living
documentation's State chapter: adding a field, wiring a validator or
changing a default is reflected on the next render, with no edit here.

⚠️ This module describes **a given class**. Describing the
``bretzel.state`` *module* itself — the four server scopes, ``field`` /
``computed`` / ``validator``, and which persistence backend serves which
scope — belongs to item 3 of the project and is **not** here. Do not read
the absence of those sections as "this is not introspectable".
"""

from __future__ import annotations

import inspect
import typing
from functools import cache

from bretzel.introspect._signature import REQUIRED_LABEL, type_label
from bretzel.introspect.model import FieldInfo, StateInfo


@cache
def describe_state(cls: type) -> StateInfo:
    """Read a live state subclass.

    Cached on ``cls``: a state class is immutable for the process's
    lifetime, so ``get_type_hints`` (the expensive part) runs once per
    class and not once per render. In dev with ``reload=True``, an edit
    produces a new class object → a new cache key, so the mirror always
    reflects the code as written.
    """
    from bretzel.state import MISSING, ClientState
    from bretzel.state.url import (
        AddressableFieldError,
        addressable_fields,
        would_publish,
    )

    is_client = issubclass(cls, ClientState)

    try:
        hints = typing.get_type_hints(cls)
    except Exception:
        hints = dict(getattr(cls, "__annotations__", {}))

    declared = cls._all_fields()  # {name: Field} — les field(...) seulement
    validators = getattr(cls, "__validators__", {}) or {}
    computed = getattr(cls, "__computed__", {}) or {}

    field_infos: list[FieldInfo] = []
    for name, hint in hints.items():
        # The state metaclass stores its bookkeeping in dunder ClassVars
        # (__validators__, __computed__, __scope__, __persist__) — this
        # single guard drops them all while keeping the user fields.
        if name.startswith("__"):
            continue

        field_infos.append(
            FieldInfo(
                name=name,
                type_label=type_label(hint),
                default_label=_default_label(cls, name, declared, MISSING),
                validators=tuple(v.fn.__name__ for v in validators.get(name, [])),
            )
        )

    persist = getattr(cls, "__persist__", "memory") if is_client else None
    scope_label = f"persist={persist!r}" if is_client else getattr(cls, "__scope__", "?")

    # Addressability reads in TWO steps because it is declared in two
    # steps: ``field(url="sort")`` NAMES, ``addressable=True`` LIGHTS UP.
    # Returning only the effective one would make the names of a
    # non-lit ``DatatableState`` disappear — and that is exactly where a
    # reader looks for them, since its subclass writes none.
    #
    # BOTH reads come from ``state/url.py``, which carries the rule.
    # Copying it here for the "named" half lasted an hour: it skipped
    # the validation, so the card advised a declaration that raises.
    url_error: str | None = None
    try:
        url_params = tuple(addressable_fields(cls).items())
        url_named = tuple(would_publish(cls).items())
    except AddressableFieldError as refusal:
        # A refused declaration raises at render time, so the app does
        # not run — but this is where one comes to understand WHY, and a
        # mute card would read as "this state publishes nothing".
        url_params, url_named, url_error = (), (), str(refusal)

    return StateInfo(
        name=cls.__name__,
        family="ClientState" if is_client else "ServerState",
        scope=scope_label,
        persist=persist,
        doc=inspect.getdoc(cls),
        fields=tuple(field_infos),
        computed=tuple(computed.keys()),
        whole_validators=len(validators.get(None, [])),
        url_params=url_params,
        url_named=url_named,
        url_error=url_error,
    )


def _default_label(cls: type, name: str, declared: dict, missing: object) -> str:
    """A field's default, whether it comes from a ``field(...)`` or from a
    bare annotation whose value lives as a class attribute in the MRO."""
    if name in declared:
        field = declared[name]
        factory = getattr(field, "default_factory", None)
        if factory not in (None, missing):
            return f"{getattr(factory, '__name__', 'factory')}() (factory)"
        if field.default is missing:
            return REQUIRED_LABEL
        return repr(field.default)

    for klass in cls.__mro__:
        if name in vars(klass):
            return repr(vars(klass)[name])
    return REQUIRED_LABEL
