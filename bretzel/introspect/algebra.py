"""The Python→JS client binding algebra — read AND executed.

``state.x > 3`` becomes ``… > 3`` in a ``bz-show``. That correspondence
lived only in prose, so it could rot. This module reads every operator /
helper of a live ``ClientBinding`` **and runs it against a probe** to
capture the JS actually emitted — that is the anti-rust gain: the example
shown **is** the real output, not a hand-copied string.

``ClientExpression`` inherits the whole surface — but it **redefines the
six mutators to raise**, so reading ``ClientBinding`` alone does not cover
ITS surface: the reading is parameterised by the class, and the operations
a class refuses do not appear in its card.
"""

from __future__ import annotations

import inspect
from functools import cache

from bretzel.introspect.methods import describe_method_surface
from bretzel.introspect.model import CATEGORY_UNCLASSIFIED, AlgebraOp

# name → (category, "how it is written in Python") — display only.
_ALGEBRA_DISPLAY: dict[str, tuple[str, str]] = {
    "__eq__": ("comparison", "x == y"),
    "__ne__": ("comparison", "x != y"),
    "__lt__": ("comparison", "x < y"),
    "__le__": ("comparison", "x <= y"),
    "__gt__": ("comparison", "x > y"),
    "__ge__": ("comparison", "x >= y"),
    "eq": ("comparison", "x.eq(y)"),
    "ne": ("comparison", "x.ne(y)"),
    "lt": ("comparison", "x.lt(y)"),
    "le": ("comparison", "x.le(y)"),
    "gt": ("comparison", "x.gt(y)"),
    "ge": ("comparison", "x.ge(y)"),
    "between": ("comparison", "x.between(lo, hi)"),
    "__add__": ("arithmetic", "x + y"),
    "__radd__": ("arithmetic", "y + x"),
    "__sub__": ("arithmetic", "x - y"),
    "__rsub__": ("arithmetic", "y - x"),
    "__mul__": ("arithmetic", "x * y"),
    "__rmul__": ("arithmetic", "y * x"),
    "__truediv__": ("arithmetic", "x / y"),
    "__floordiv__": ("arithmetic", "x // y"),
    "__mod__": ("arithmetic", "x % y"),
    "__neg__": ("arithmetic", "-x"),
    "__abs__": ("arithmetic", "abs(x)"),
    "__round__": ("arithmetic", "round(x, n)"),
    "to_fixed": ("arithmetic", "x.to_fixed(n)"),
    "__invert__": ("logic", "~x"),
    "__and__": ("logic", "x & y"),
    "__or__": ("logic", "x | y"),
    "not_": ("logic", "x.not_()"),
    "then_else": ("logic", "cond.then_else(a, b)"),
    "length": ("list", "x.length()"),
    "contains": ("list", "x.contains(v)"),
    "join": ("list", "x.join(sep)"),
    "toggle": ("mutation", "x.toggle()"),
    "increment": ("mutation", "x.increment(n)"),
    "decrement": ("mutation", "x.decrement(n)"),
    "set": ("mutation", "x.set(v)"),
    "push": ("mutation", "x.push(v)"),
    "clear": ("mutation", "x.clear()"),
}

_ALGEBRA_DUNDERS = frozenset(n for n in _ALGEBRA_DISPLAY if n.startswith("__"))

# Only the NON-dunder plumbing needs to be dropped explicitly —
# ``describe_method_surface`` already drops every dunder absent from
# ``include_dunders``, so __init__ / __bool__ / __repr__ never reach
# here.
_ALGEBRA_SKIP = frozenset({"serialize_path", "binding_path"})

_CATEGORY_ORDER = {
    "comparison": 0,
    "arithmetic": 1,
    "logic": 2,
    "list": 3,
    "mutation": 4,
    CATEGORY_UNCLASSIFIED: 5,
}

# The two binary operators whose right-hand side must be a BINDING and
# not a literal — ``x & 3`` makes no sense, ``x & y`` does.
_BINARY_ON_BINDINGS = frozenset({"__and__", "__or__"})


def describe_client_algebra(cls: type | None = None) -> tuple[AlgebraOp, ...]:
    """Read a binding class's live Python→JS algebra.

    ``cls`` is ``ClientBinding`` by default — the complete algebra, what
    the living documentation displays.

    **Passing a subclass returns ITS effective surface, and that is
    load-bearing.** ``ClientExpression`` inherits the thirty-four
    operators and **redefines the six mutators to RAISE**
    (``ReactivityError``: an expression has no field to write to). A card
    built on the base class therefore announced ``x.toggle()`` with its
    JS, on the one class that refuses it.

    A method absent from :data:`_ALGEBRA_DISPLAY` comes out as
    :data:`CATEGORY_UNCLASSIFIED` — the view shows it anyway (nothing is
    lost) and ``test_docs_coverage`` turns red, so a maintainer
    classifies the new operator on purpose.
    """
    from bretzel.state import ClientBinding

    return _describe_client_algebra(cls or ClientBinding)


@cache
def _describe_client_algebra(cls: type) -> tuple[AlgebraOp, ...]:
    """A cached worker — keyed on the class, so a dev-reload (a new class
    object) produces a new entry, exactly like :func:`describe_state`'s
    reload-safe cache. Without it, the loop of 40 probes would replay on
    every page render."""
    probe, other = _probes(cls)
    ops = [
        AlgebraOp(
            name=method.name,
            category=category,
            python=python,
            js=js,
            returns_label=method.returns_label,
            doc=method.doc,
        )
        for method in describe_method_surface(
            cls, include_dunders=_ALGEBRA_DUNDERS, skip=_ALGEBRA_SKIP, inherited=True
        )
        for category, python in [
            _ALGEBRA_DISPLAY.get(method.name, (CATEGORY_UNCLASSIFIED, f"x.{method.name}(…)"))
        ]
        # An operation THIS class refuses is not listed. Keeping it
        # without JS would read as "the probe did not know"; keeping it
        # with JS would be a lie. Absence is the only correct reading —
        # and the refusal itself carries its error message, which
        # explains better than we can.
        for js, refused in [_probe_js(probe, other, method.name)]
        if not refused
    ]
    return tuple(sorted(ops, key=lambda o: (_CATEGORY_ORDER.get(o.category, 9), o.name)))


def _probes(cls: type) -> tuple[object, object]:
    """Two instances of ``cls`` to put the operators to.

    The state module's two construction forms are tried in order: a
    binding's (four named fields) then an expression's (a JS source).
    Without this, probing ``ClientExpression`` raised at CONSTRUCTION
    time, outside the probe's ``try``.
    """
    try:
        return (
            cls(class_name="State", instance_key="default", field_name="x", value=0),
            cls(class_name="State", instance_key="default", field_name="y", value=0),
        )
    except TypeError:
        return cls("$bz.state.State.default.x"), cls("$bz.state.State.default.y")


def _probe_js(probe: object, other: object, name: str) -> tuple[str | None, bool]:
    """Call ``name`` on the probe and capture the JS emitted.

    Returns ``(js, refused)``. The arity is read from the live signature
    (no per-method table): a binary logical operator receives a second
    binding, the other binary ones a literal, the ternary ones two
    literals. Best-effort — returns ``None`` when the shape does not fit,
    so a new method never breaks the page, it simply shows without an
    example.

    ``refused`` distinguishes the second case from the first: a class
    that RAISES on purpose (:class:`~bretzel.state.ReactivityError`) does
    not fail the probe, it answers no — and a refused operation has no
    business in the card of the class that refuses it.
    """
    from bretzel.state import ReactivityError

    try:
        method = getattr(probe, name)
        required = [
            p
            for p in inspect.signature(method).parameters.values()
            if p.default is inspect.Parameter.empty
            and p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        if not required:
            result = method()
        elif len(required) == 1:
            result = method(other if name in _BINARY_ON_BINDINGS else 3)
        else:
            result = method(1, 10)
    except ReactivityError:
        return None, True
    except Exception:
        return None, False
    if hasattr(result, "serialize_path"):
        return result.serialize_path(), False
    return (result if isinstance(result, str) else None), False
