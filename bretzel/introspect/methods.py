"""A NAMESPACE's callable surface — the generic primitive.

Some APIs **are** their method surface: ``ClientBinding``'s operator DSL,
a decorator registry, any fluent builder. This primitive reads it live —
name, signature, return, docstring — knowing nothing about what it reads.
The specialised layers enrich it (cf.
:mod:`bretzel.introspect.algebra`).

**A namespace, not a class.** The real subject is "an attribute holder +
a list of names": ``auth`` and ``oauth`` are *modules* exported at the
first tier, and their surface reads exactly like a class's. Writing the
loop a second time for them would have given two :class:`MethodInfo`
construction sites to keep in sync — which is what the first version of
:mod:`bretzel.introspect.symbols` did.

**Reuse it before re-listing anything's callables by hand.**
"""

from __future__ import annotations

import inspect
from collections.abc import Iterable

from bretzel.introspect._signature import describe_callable, type_label
from bretzel.introspect.model import MethodInfo


def describe_method_surface(
    cls: type,
    *,
    include_dunders: frozenset[str] = frozenset(),
    skip: frozenset[str] = frozenset(),
    inherited: bool = False,
) -> tuple[MethodInfo, ...]:
    """Everything callable on ``cls`` as a public API.

    By default it reads ``cls.__dict__`` — the OWN methods, not the
    plumbing inherited from ``object``.

    ``inherited=True`` walks the MRO (``object`` excluded) and returns
    the **effective** surface: what a caller really gets through
    ``getattr``, the most derived definition winning. Without that mode,
    ``ClientExpression`` — which inherits thirty-two operators and
    redefines only six — had a surface of six methods, which is the
    answer to no question anyone asks it.
    """
    return describe_namespace_surface(
        cls,
        _public_names(cls, inherited=inherited),
        include_dunders=include_dunders,
        skip=skip,
    )


def describe_namespace_surface(
    owner: object,
    names: Iterable[str],
    *,
    include_dunders: frozenset[str] = frozenset(),
    skip: frozenset[str] = frozenset(),
) -> tuple[MethodInfo, ...]:
    """The callables of ``names`` read on ``owner``, in that order.

    Keeps the names without an underscore, plus any dunder explicitly
    named in ``include_dunders`` (an operator DSL wants ``__gt__`` in its
    surface), and drops what is in ``skip``. The signatures are read
    through :func:`describe_callable`, so a renamed parameter follows
    with no edit.
    """
    out: list[MethodInfo] = []
    for name in names:
        if name in skip or not _is_wanted(name, include_dunders):
            continue
        attr = getattr(owner, name, None)
        if not callable(attr):
            continue
        try:
            info = describe_callable(attr)
        except (TypeError, ValueError):
            continue
        out.append(
            MethodInfo(
                name=name,
                params=info.params,
                returns_label=return_label(attr),
                doc=info.doc,
            )
        )
    return tuple(out)


def _is_wanted(name: str, include_dunders: frozenset[str]) -> bool:
    if name.startswith("__") and name.endswith("__"):
        return name in include_dunders
    return not name.startswith("_")


def _public_names(cls: type, *, inherited: bool) -> tuple[str, ...]:
    """The names to read on ``cls``, de-duplicated, MRO in order.

    ``dict.fromkeys`` rather than a ``set``: declaration order is the
    card's display order, and the first occurrence walking up the MRO is
    the definition that wins — the same one ``getattr`` will return.
    """
    if not inherited:
        return tuple(vars(cls))
    seen: dict[str, None] = {}
    for klass in cls.__mro__:
        if klass is object:
            continue
        seen.update(dict.fromkeys(vars(klass)))
    return tuple(seen)


def return_label(fn: object) -> str:
    try:
        annotation = inspect.signature(fn).return_annotation
    except (TypeError, ValueError):
        return "—"
    if annotation is inspect.Signature.empty:
        return "—"
    return type_label(annotation)
