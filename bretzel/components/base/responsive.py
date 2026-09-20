"""Responsive prop values — one ``{breakpoint: value}`` dialect, one parser.

A *graded* layout prop (how many columns, how much gap, which axis) can
take a different value per screen width ::

    ui.grid(cols={"base": 1, "md": 3})
    ui.flex(direction={"base": "col", "md": "row"}, gap={"base": "sm", "md": "lg"})

The dict is read « ``base`` applies everywhere, each breakpoint overrides
from that width up » — i.e. Tailwind's mobile-first ladder, spelled in
Python. :func:`responsive_classes` is the ONLY thing that turns it into
classes ; a component never prefixes breakpoints by hand.

**Which props may take a dict.** Only the *graded* ones — those with more
than two useful steps. Anything binary (shown / hidden, sidebar / topbar)
is a **structural** choice and belongs to ``if Screen().is_mobile:`` in
the dev's own layout, not to a prop. That boundary is why Bretzel has no
``visible_from=`` : it would be a second way to say what ``Screen``
already says. Cf. ``.claude/work/todo.md`` § *A-ter*.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.theme.tokens import BREAKPOINTS

# Keys meaning « no prefix — applies at every width ». ``base`` is the
# canonical spelling ; the rest are tolerated aliases (``xs`` reads as
# "smallest", and Tailwind has no ``xs:`` variant to collide with).
BASE_KEYS = frozenset({"base", "xs", "", "default"})

# Tailwind's default breakpoint ladder — RE-EXPORTED from
# ``theme.tokens``, which owns it. A key outside this set would emit a
# prefix Tailwind never generates (a silent no-op): we refuse rather than
# ship dead classes.
# The safelist must close over the same set, hence the single source in
# the theme layer — cf. the comment over there.

_ALLOWED = "base, " + ", ".join(BREAKPOINTS)


def responsive_classes(value: Any, resolve: Callable[[Any], str]) -> str:
    """Resolve ``value`` to a class string, honouring a breakpoint dict.

    ``resolve`` maps ONE scalar value to its class string (a theme-table
    lookup, an f-string, whatever the component uses) and stays unaware of
    breakpoints. A scalar passes straight through it ; a dict resolves each
    entry and prefixes every token of the result — a multi-class entry like
    ``"gap-x-4 gap-y-2"`` becomes ``"md:gap-x-4 md:gap-y-2"``, not the
    broken ``"md:gap-x-4 gap-y-2"``.

    Entries resolving to an empty string are dropped. Class ORDER carries
    no meaning here : Tailwind emits its media queries in ladder order in
    the stylesheet, so dict insertion order cannot change the outcome.
    """
    if not isinstance(value, dict):
        return resolve(value) or ""

    parts: list[str] = []
    for breakpoint_, raw in value.items():
        if breakpoint_ not in BASE_KEYS and breakpoint_ not in BREAKPOINTS:
            raise ComponentUsageError(
                f"unknown breakpoint {breakpoint_!r} in a responsive value — "
                f"it would emit a prefix Tailwind never generates. "
                f"Allowed: {_ALLOWED}."
            )
        resolved = resolve(raw)
        if not resolved:
            continue
        if breakpoint_ in BASE_KEYS:
            parts.append(resolved)
        else:
            parts.append(" ".join(f"{breakpoint_}:{tok}" for tok in resolved.split()))
    return " ".join(parts)


def looks_like_a_breakpoint_dict(value: Any) -> bool:
    """Is this dict a scale of steps, or DATA?

    The question arises because the base layer now refuses a step dict on
    a non-graded prop (:meth:`Component._reject_stray_breakpoints`), and
    it has to do so without ever being wrong about a prop that
    legitimately takes a dict — a table's rows, a map of values, a
    composite attribute.

    Hence the discriminant: **all** the keys are known steps.
    ``{"base": …, "md": …}`` cannot be anything else; ``{"id": 1,
    "name": "x"}`` is never confused with one. An empty dict is not a
    scale either — it says nothing, and refusing it would teach nobody
    anything.

    ⚠️ The expensive side is the LEGITIMATE one: a gate that goes red on
    correct code gets unplugged. That is why the test is not "it is a
    dict" but "it is a dict of steps".
    """
    return (
        isinstance(value, dict)
        and bool(value)
        and all(k in BASE_KEYS or k in BREAKPOINTS for k in value)
    )


def reject_stray_breakpoints(
    owner: str, prop: str, value: Any, responsive_props: frozenset[str]
) -> None:
    """A step dict on a prop that is not graded: we SAY so.

    Without this refusal, the dict carries on to a theme-table lookup and
    dies three frames below on ::

        TypeError: cannot use 'dict' as a dict key (unhashable type: 'dict')

    — which names neither the component, nor the prop, nor the fact that
    a step dict has no place there. Measured on 2026-09-04: **80
    ``Class.prop`` pairs** died like that, listed one by one in
    ``tests/consistency/_not_graded.txt`` because we did not know how to
    repair them in one go.

    Yet the framework ALREADY had the right shape of error —
    ``ui.card(size=…)`` answers "this component does not read ``size``",
    clear and actionable. What was missing was not the message, it was
    that it be REACHED: the old ``reject_responsive`` guard existed but
    was wired only on ``flex`` and ``carousel``, two components out of a
    hundred, one hand-written line per prop. Called from the base layer
    with the ``RESPONSIVE_PROPS`` declaration, it becomes universal with
    no line per prop, and with nothing to forget on a new component.

    ⚠️ The discriminant is :func:`looks_like_a_breakpoint_dict`, not "it
    is a dict": several props legitimately take a dict of DATA, and a
    guard that refused them would be unplugged within the week.
    """
    if prop in responsive_props or not looks_like_a_breakpoint_dict(value):
        return
    graded = sorted(responsive_props)
    what_works = (
        "On this component, "
        + ", ".join(f"``{p}``" for p in graded)
        + (" takes one." if len(graded) == 1 else " take one.")
        if graded
        else "No prop of this component is graded."
    )
    raise ComponentUsageError(
        f"{owner}({prop}=…): ``{prop}`` does not take a step dict. "
        f"{what_works} A choice that is not a GRADUATION is structural "
        f"— branch it in your layout with ``if Screen().is_mobile:``, "
        f"which says the same thing without a second way of saying it."
    )
