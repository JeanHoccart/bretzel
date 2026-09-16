"""Validator declarations for typed state.

Two flavours of validator are supported on a State subclass :

- **Single-field** (``@validator("name")``) : runs whenever the field is
  written via :py:meth:`Field.__set__`. The function receives the host
  instance and the incoming value, and returns the (possibly transformed)
  value to store. Raising aborts the assignment.

- **Whole-instance** (``@validator``, no argument) : runs after any field
  has been set, to enforce multi-field invariants. The function receives
  the host instance and returns ``None``. Raising rolls the most recent
  mutation back and re-raises.

Validators raise standard :class:`ValueError` (or any subclass) on
failure ; per-field handler conventions then route the message to the
matching ``state.errors[field_name]`` key. For *cross-field* failures
(whole-instance validators that don't belong to any single field — e.g.
"passwords don't match"), raise :class:`FormError` instead so the
calling form-submit handler can route the message to a form-level key
like ``state.errors["_"]`` — la clé réservée est un underscore SEUL, pas
    ``"_form"`` (`server/routing/actions.py` écrit `errors["_"]`) — and
    display it via ``ui.alert`` at the
top of the form rather than under a specific field.

This module provides only the *declarations* — the actual invocation is
the responsibility of :class:`~bretzel.state.fields.descriptor.Field` and
the State metaclass, which collects validators into ``cls.__validators__``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, overload


class FormError(ValueError):
    """Report a validation error for an entire state instance."""


class Validator:
    """Wrapper around a validator callable.

    Captured as a class attribute on a State subclass. The metaclass
    registers it under ``cls.__validators__[target]`` (with ``target=None``
    for whole-instance validators) and the descriptor invokes it on every
    matching mutation.

    The wrapper itself is callable so that user code can still use the
    function directly if desired (e.g., ``CartState.normalize_coupon(...)``
    would behave like the underlying function).
    """

    # ``__doc__`` cannot be a slot — it's already a class variable holding
    # the docstring of ``Validator`` itself. We let ``__doc__`` live on the
    # ordinary instance dict instead.
    __slots__ = ("__dict__", "__name__", "__qualname__", "fn", "target")

    def __init__(
        self,
        target: str | None,
        fn: Callable[..., Any],
    ) -> None:
        self.target = target
        self.fn = fn
        self.__name__ = getattr(fn, "__name__", "<validator>")
        self.__qualname__ = getattr(fn, "__qualname__", self.__name__)
        self.__doc__ = getattr(fn, "__doc__", None)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.fn(*args, **kwargs)

    def __repr__(self) -> str:
        scope = "instance" if self.target is None else f"field={self.target!r}"
        return f"Validator({scope}, fn={self.__qualname__})"


# ───────────────────────────────────────────────────────────────────────────
# Decorator API — overloaded for the two call shapes
# ───────────────────────────────────────────────────────────────────────────


@overload
def validator(arg: str) -> Callable[[Callable[..., Any]], Validator]: ...


@overload
def validator(arg: Callable[..., Any]) -> Validator: ...


def validator(
    arg: str | Callable[..., Any],
) -> Validator | Callable[[Callable[..., Any]], Validator]:
    """Mark a function as a validator.

    Two shapes :

    - ``@validator("field_name")`` — single-field validator. The decorated
      function ``(self, value) -> new_value`` runs on every assignment to
      ``field_name``.
    - ``@validator`` — whole-instance validator. The decorated function
      ``(self) -> None`` runs after any field mutation. Raise to abort.
    """
    if isinstance(arg, str):
        target = arg

        def deco(fn: Callable[..., Any]) -> Validator:
            return Validator(target=target, fn=fn)

        return deco

    if callable(arg):
        return Validator(target=None, fn=arg)

    raise TypeError(
        "@validator must decorate a function or be called with a field name."
    )
