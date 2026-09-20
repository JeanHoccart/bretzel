"""The card of a public symbol that is **not** a ``ui.*``.

``describe`` could say everything about ``ui.button`` and nothing about
``@page``. Of the seven modules' 157 public names, it returned only an
index line — name, nature, summary cut at 62 characters — and
``describe page`` answered "``ui.page`` does not exist", which is false
and points at the wrong conclusion. An AI concluded from it that
``@page`` exists without ever being able to call it.

**Nothing is re-listed here.** The population AND its classification come
from :func:`~bretzel.introspect.modules.describe_module` — the same
:class:`~bretzel.introspect.model.SurfaceSymbol` that feeds the index —
and the four detail readings are the existing primitives applied
according to the symbol's nature. This module is a switch, not a fifth
engine.
"""

from __future__ import annotations

import importlib
import inspect
from functools import cache
from types import MappingProxyType

from bretzel.introspect._signature import describe_callable
from bretzel.introspect.algebra import describe_client_algebra
from bretzel.introspect.methods import describe_method_surface, describe_namespace_surface
from bretzel.introspect.model import MethodInfo, SurfaceSymbol, SymbolDetail
from bretzel.introspect.modules import describe_module, module_names, value_summary
from bretzel.introspect.state import describe_state


@cache
def _table() -> MappingProxyType[str, tuple[tuple[str, SurfaceSymbol], ...]]:
    """Public name → ``((module, its index line), …)``, in reading order.

    Reads :func:`describe_module`, so the population, the nature and the
    category are the index's — a single definition of "a covered module's
    public surface". Recomputing them here would have left two
    expressions of the same rule, and a copied classification has already
    drifted once in this repository for exactly that reason.

    Returned read-only: it is a cache shared by every caller, and an
    accidental mutation would corrupt all the following ones.
    """
    rows: dict[str, list[tuple[str, SurfaceSymbol]]] = {}
    for module_name in module_names():
        for symbol in describe_module(module_name).symbols:
            rows.setdefault(symbol.name, []).append((module_name, symbol))
    return MappingProxyType({name: tuple(found) for name, found in rows.items()})


@cache
def symbol_owners() -> MappingProxyType[str, tuple[str, ...]]:
    """Public name → the modules exporting it, in reading order.

    ``page``, ``refresh``, ``Feature`` and the ``*Error`` come out of two
    modules at once — the same object re-exported by the facade. The
    first module in the list is the one it is imported from in practice
    (``bretzel`` heads :data:`~bretzel.introspect.modules.SECTIONS`), the
    following ones are equally valid import paths.
    """
    return MappingProxyType(
        {name: tuple(module for module, _ in rows) for name, rows in _table().items()}
    )


@cache
def symbol_names() -> tuple[str, ...]:
    """Every describable name outside ``ui.*``, sorted."""
    return tuple(sorted(_table()))


def describe_symbol(name: str) -> SymbolDetail:
    """The card of a public symbol of a framework module.

    ``name`` is written bare (``page``) or qualified
    (``bretzel.render.page``) — the qualified form is what a traceback
    shows, requiring one or the other would be needless friction.
    """
    bare, forced = _split(name)
    exported = _table().get(bare, ())
    rows = tuple(row for row in exported if row[0] == forced) if forced else exported
    if not rows:
        raise KeyError(f"`{name}` is not exported by any framework module")

    home, indexed = rows[0]
    value = getattr(importlib.import_module(home), bare)
    is_class = isinstance(value, type)
    # ONE single call: it is also the "is this a constant?" predicate,
    # and its ``repr`` on a large value is not free.
    summary = value_summary(value)

    return SymbolDetail(
        name=bare,
        module=home,
        exported_by=tuple(module for module, _ in exported),
        also_known_as=_also_known_as(bare),
        category=indexed.category,
        kind=indexed.kind,
        # A constant has no docstring: ``inspect.getdoc`` would return
        # its TYPE's, the noise ``value_summary`` already eliminates.
        doc=None if summary is not None else _docstring(value),
        signature=_signature(value),
        methods=_surface(value),
        value_repr=summary,
        algebra=describe_client_algebra(value) if is_class and _is_algebra(value) else (),
        state=_state(value) if is_class else None,
    )


def _also_known_as(bare: str) -> tuple[str, ...]:
    """The other surfaces carrying this name.

    One case today, and it is a trap: ``text`` is the ``ui.text``
    component **and** ``bretzel.render.text``, the framework's word
    rendered in the app's language. Carried by the DATA and not by the
    rendered text, so that both cards say it and the JSON carries it too
    — :mod:`bretzel.introspect.model` promises that text and JSON cannot
    diverge, and a note glued to the rendering would have made that
    promise false by exactly one line.
    """
    from bretzel.introspect.components import ui_symbol_names

    return (f"ui.{bare}",) if bare in ui_symbol_names() else ()


def _split(name: str) -> tuple[str, str | None]:
    """``bretzel.render.page`` → ``("page", "bretzel.render")``.

    The forced module is only kept when it is covered: ``a.b.c`` on an
    unknown module falls back on the bare name, which will give the
    useful error.
    """
    module, _, bare = name.rpartition(".")
    return (bare, module) if module in module_names() else (name, None)


def _docstring(value: object) -> str | None:
    """The WHOLE docstring — that is the difference from the index."""
    doc = inspect.getdoc(value)
    return doc.strip() if doc else None


def _signature(value: object):
    """The live signature, or ``None`` when it teaches nothing.

    Two cases return ``None``. An object whose signature ``inspect``
    cannot read — a module, a constant: an accepted best-effort, the card
    renders without it rather than failing whole. And a signature that is
    **entirely** ``*args, **kwargs``: the five scope classes inherit
    ``object``'s, and showing it under "Parameters" would give ``args``
    and ``kwargs`` as parameter names, which is worse than staying
    silent.

    ``info.params and all(…)``: ``all(())`` is ``True``, so without the
    left operand every function WITHOUT parameters would lose its
    signature — and "zero parameters" is an answer.
    """
    try:
        info = describe_callable(value)
    except (TypeError, ValueError):
        return None
    if info.params and all(p.kind in ("*args", "**kwargs") for p in info.params):
        return None
    return info


def _surface(value: object) -> tuple[MethodInfo, ...]:
    """What can be called ON the symbol.

    A class returns its public methods — except an algebra class, whose
    operators are returned by
    :attr:`~bretzel.introspect.model.SymbolDetail.algebra` with their
    Python form and the JS emitted, which the method surface does not
    carry.

    A module returns its ``__all__``. ``auth`` and ``oauth`` are modules
    exported at the first tier — without this, their card showed the
    docstring and **nothing callable**, although ``auth.login`` is
    exactly what one comes looking for. Reading ``vars()`` instead would
    give 17 names for 6: everything the module imports.
    """
    if isinstance(value, type):
        return () if _is_algebra(value) else describe_method_surface(value)
    if not inspect.ismodule(value):
        return ()
    return describe_namespace_surface(value, getattr(value, "__all__", ()) or ())


def _is_algebra(cls: type) -> bool:
    """Is the class **itself** its operator algebra?

    Derived from inheritance and not from a list of names:
    ``ClientExpression`` descends from ``ClientBinding``. It is the CLASS
    that is passed to
    :func:`~bretzel.introspect.algebra.describe_client_algebra`, and not
    its base — without which ``ClientExpression``'s card announced, with
    JS to back it, the six mutators it redefines to RAISE.
    """
    from bretzel.state import ClientBinding

    return issubclass(cls, ClientBinding)


def _state(cls: type):
    """The scope and the fields, if it is a state class.

    On the five base classes (``PageState``… ``ClientState``) the fields
    are empty and it is the **scope** that carries all the information —
    the question one asks in front of ``UserState`` is "how long does
    this live", not "which fields".
    """
    from bretzel.state import ClientState, ServerState

    return describe_state(cls) if issubclass(cls, ServerState | ClientState) else None
