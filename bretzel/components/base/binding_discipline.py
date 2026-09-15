"""Type discipline for reactive_prop bindings.

A component prop declared as a scalar (``str`` / ``int`` / ``bool`` /
``float``) MUST receive a scalar value at instantiation time — whether
literal or wrapped in a :class:`ClientBinding`. Passing a list or a
dict to a scalar prop is a contract violation that yields confusing
runtime behaviour later (the JS side cannot decide whether to stringify
or to iterate, the SSR composition explodes, etc).

The helpers here run in ``Component.__init__`` (cf. Task 3) and surface
the mistake at the moment of the misuse with a clear message —
``ui.button(label=state.tags)`` becomes ``Button.label expects scalar
str, got list binding state.tags`` rather than a class-string blowing
up three frames later.

Defensive note : the metaclass's annotation resolution may fall back
to raw ``__annotations__``, which under ``from __future__ import
annotations`` (PEP 563) yields plain strings instead of type objects.
``is_scalar_type`` treats anything non-``type`` (and non-Union) as
non-scalar so the discipline silently degrades to permissive instead
of silently bypassing real misuses.
"""

from __future__ import annotations

import typing
from typing import Any

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.state.scopes.client import ClientBinding, ClientExpression

# ───────────────────────────────────────────────────────────────────────────
# is_scalar_type — accepts an annotation and decides "scalar or not"
# ───────────────────────────────────────────────────────────────────────────

_SCALAR_TYPES: tuple[type, ...] = (str, int, float, bool, type(None))


def is_scalar_type(annotation: Any) -> bool:
    """``True`` when the annotation resolves to a scalar (or a union
    of scalars / ``None``). Optional/Union with at least one non-scalar
    arm is treated as non-scalar.

    Strings, parametrised generics (``list[int]``), and anything else
    that isn't a real ``type`` or ``Union`` return ``False`` — the
    framework treats those as "discipline can't determine, skip".
    """
    if annotation in _SCALAR_TYPES:
        return True
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is type(str | None):
        # Both ``Optional[X]`` (Union) and ``X | None`` (PEP 604) land
        # here on Python 3.10+. Inspect every arm.
        return all(is_scalar_type(arg) for arg in typing.get_args(annotation))
    return False


# ───────────────────────────────────────────────────────────────────────────
# validate_scalar_binding — raises ComponentUsageError on misuse
# ───────────────────────────────────────────────────────────────────────────


def validate_scalar_binding(
    prop_name: str,
    *,
    declared_type: Any,
    binding: ClientBinding,
    owner: str,
) -> None:
    """Raise :class:`ComponentUsageError` when ``binding.value`` is a
    list / dict / tuple / set while the prop's declared type is scalar.

    ``declared_type=None`` or a non-scalar annotation (string, generic,
    list[...]) means "the framework cannot determine the contract" —
    discipline silently passes. Better permissive than wrong.

    A :class:`ClientExpression` carries no server value to type-check
    (it is computed client-side from other fields), so it passes too —
    same "cannot determine, stay permissive" rule. Reading ``.value``
    on one raises ``AttributeError`` : this guard is what made
    ``ui.button(disabled=expr)`` crash here, BEFORE the caller's own
    handling. Cf. traps.md § « ClientExpression sur une reactive prop ».
    """
    if isinstance(binding, ClientExpression):
        return
    if declared_type is None or not is_scalar_type(declared_type):
        return
    value = binding.value
    if isinstance(value, (list, dict, tuple, set)):
        raise ComponentUsageError(
            f"{owner}.{prop_name} expects a scalar "
            f"({_friendly_type(declared_type)}), got "
            f"{type(value).__name__} binding "
            f"`{binding.serialize_path()}`. Use a scalar field in your "
            f"ClientState, or wrap a collection in ui.each / @refreshable."
        )


def _friendly_type(annotation: Any) -> str:
    """Compact human-readable form of an annotation for error messages."""
    if annotation in _SCALAR_TYPES:
        return getattr(annotation, "__name__", str(annotation))
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is type(str | None):
        arms = [_friendly_type(a) for a in typing.get_args(annotation)]
        return " | ".join(arms)
    return str(annotation)
