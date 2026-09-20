"""Rule: a class in ``classes=`` that the SAME prop already sets.

The silence it closes
---------------------

``ui.vstack`` emits ``justify-start`` without being asked: the
``justify`` prop has a default, and a default emits. Writing ::

    ui.vstack(gap="none", align="start", classes="h-full w-full justify-center px-3")

therefore puts **two** ``justify-*`` on the same element ::

    <div class="flex flex-col items-start justify-start gap-0 h-full w-full justify-center px-3">

Both selectors have the same specificity, so it is the Tailwind
**sheet**'s order that settles them — not the order of the ``class``
attribute, which everyone reads first. Measured on 2026-09-06 on
``examples/playground/features/diagram/ui.py``: ``justify-start`` won,
the content stayed stuck at the top although the code said "centre".

It is the repository's favourite failure mode: nothing raises, nothing is
missing from the HTML, and **re-reading the classes shows nothing** —
both are there, both correct, both wanted by somebody. Same mechanics as
the "hover on every other row" of
``bretzel/components/data/table/theme.py`` ("hover vs striped
specificity"), where two rules of equal specificity are settled by the
source.

The fault happened **twice in a row** in the same file (commits
``9cdd7627`` then ``db1b574c``), which is the definition of an easy and
invisible fault.

The prop → family table is DERIVED, never copied
------------------------------------------------

A linter carrying its own ``justify → justify-*`` table would drift from
the code it judges — same refusal as :mod:`bretzel.lint.rules.kwargs` and
:mod:`bretzel.lint.rules.variant`. Here everything comes from the live
component:

- ``THEME_TABLES`` gives **prop → theme group** (declared on
  :class:`~bretzel.components.layout.flex.flex.Flex`, guarded by
  ``test_a_flex_family_declares_every_table``);
- the group gives the **classes actually emitted**, hence the family's
  prefix and the prop value producing each one;
- ``__reactive_props__`` gives the **default**, that is to say what is
  emitted when the call passes nothing.

A prop whose component changes the default therefore changes the rule
with nothing touched: ``HStack.align`` is ``center`` where ``Flex.align``
is ``stretch``, and both are read, not assumed.

⚠️ **Scope: the components that declare ``THEME_TABLES``** — the five of
the flex family (``flex``, ``vstack``, ``hstack``, ``pane``,
``viewport``). The others write the prop → group correspondence in their
``render``, where no static read goes looking for it; ``ui.grid(gap=…)``
and ``ui.carousel(gap=…)`` are therefore out of scope until they declare
it. Written rather than guessed: measured on 2026-09-06, neither
``grid``, nor ``carousel``, nor ``resizable`` has a single ``classes=``
of this family in the repository — the blind spot costs nothing today,
and the day it costs, it is ``THEME_TABLES`` that must be set, not a
table here.

What it does NOT report, and that is the heart of the tuning
------------------------------------------------------------

``classes=`` **is** the legitimate escape hatch, and a rule condemning it
wholesale would be disabled on day one. The family is therefore closed on
what the prop can say: the classes the table emits, plus the prefix
followed by one of its **keys** (that is how ``justify-center`` belongs,
although the theme renders ``[justify-content:safe_center]`` — a ``safe``
centring).

Three measured consequences:

- ``justify-normal`` / ``items-normal``: outside the table, no prop value
  renders them → **never reported**, that is escape-hatch territory;
- ``flex-1`` on a ``ui.flex``: ``direction``'s family is exactly
  ``flex-row|flex-col|flex-row-reverse|flex-col-reverse``, not
  ``flex-*`` → spared (the prefix alone would have made four false
  positives per app);
- ``md:justify-center``, ``justify-center!``, ``[justify-content:…]``:
  **deliberate** departures in specificity or scope, which win for good →
  never reported.

Accepted blind spot: ``gap-3`` (a step outside the table) really does
fight with the default's ``gap-4``, and is not reported — it exists as no
prop's value, so reporting it would amount to refusing the escape hatch.

Measurement before shipping
---------------------------

2026-09-06: **21 findings** over ``examples/``, **0** over
``tests/e2e/apps``, **0** in ``bretzel/``. All 21 were the same pattern —
a ``justify-*`` from ``classes=`` against the default's
``justify-start``, including seven "centred" error pages that were not.
All fixed by moving to the prop; ``examples/`` is at zero and frozen by
``test_lint_baseline_on_examples``.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import cache
from typing import Any

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "class-duplicates-a-prop"

#: The kwargs whose value lands in the ``class`` attribute.
_CLASS_KWARGS = ("classes", "class_")

#: A character that takes a class out of judgement. ``:`` = a variant
#: (``md:``, ``hover:``) hence another scope AND another rank in the
#: sheet; ``[`` / ``]`` = an arbitrary value, written on purpose; ``!`` =
#: Tailwind's important, that is to say an accepted departure that wins.
#: None of the three is the silent duplicate this rule looks for.
_DELIBERATE = "[]:!"


@dataclass(frozen=True)
class _Family:
    """What a prop sets on the element, seen from the classes."""

    prop: str
    #: class → the prop value that renders it. That is the family.
    members: dict[str, str]
    #: prop value → the class (or classes) it renders.
    emits: dict[str, str]
    #: What the prop renders when the call passes nothing. Empty = it
    #: emits nothing by default (``grow``), so no conflict to assume.
    default: str


def _deliberate(token: str) -> bool:
    return any(c in token for c in _DELIBERATE)


def _family_members(table: dict[str, Any]) -> dict[str, str]:
    """The classes ``table`` can render, indexed by prop value.

    The prefix is DERIVED from the emitted classes and must be unique: a
    group mixing two prefixes has no "family" in this rule's sense, and
    we would rather say nothing than say anything.

    The table's keys are then glued back to the prefix, which catches the
    values the theme renders otherwise than as a named utility —
    ``center`` renders ``[justify-content:safe_center]``, but
    ``justify-center`` does belong to the family.
    """
    emitted = {
        token
        for value in table.values()
        for token in str(value).split()
        if "-" in token and not _deliberate(token)
    }
    prefixes = {token.split("-", 1)[0] for token in emitted}
    if len(prefixes) != 1:
        return {}
    prefix = f"{prefixes.pop()}-"

    members: dict[str, str] = {}
    for key, value in table.items():
        for token in str(value).split():
            if token in emitted:
                members.setdefault(token, str(key))
        members.setdefault(f"{prefix}{key}", str(key))
    return members


@cache
def _families_of(cls: type) -> tuple[_Family, ...]:
    """The class families ``cls``'s props drive.

    Empty for any component that does not declare ``THEME_TABLES`` — the
    prop → group correspondence then lives in its ``render``, out of a
    static read's reach.
    """
    tables = getattr(cls, "THEME_TABLES", None)
    theme = getattr(cls, "THEME", None)
    if not isinstance(tables, dict) or not isinstance(theme, dict):
        return ()

    props = getattr(cls, "__reactive_props__", None) or {}
    families: list[_Family] = []
    for prop, group in sorted(tables.items()):
        table = theme.get(group)
        if not isinstance(table, dict):
            # A scalar group (``wrap`` is the string ``flex-wrap``): not
            # a family, and setting the same class twice does nothing.
            continue
        members = _family_members(table)
        if not members:
            continue
        default = getattr(props.get(prop), "default", None)
        families.append(
            _Family(
                prop=prop,
                members=members,
                emits={str(k): str(v) for k, v in table.items()},
                default=default if isinstance(default, str) else "",
            )
        )
    return tuple(families)


def _judged() -> dict[str, tuple[_Family, ...]]:
    """``ui.<name>`` → its families, for the components we can read."""
    from bretzel.components import ui
    from bretzel.components.base.component import Component
    from bretzel.introspect import ui_symbol_names

    out: dict[str, tuple[_Family, ...]] = {}
    for name in ui_symbol_names():
        value = getattr(ui, name, None)
        if not (isinstance(value, type) and issubclass(value, Component)):
            continue
        families = _families_of(value)
        if families:
            out[name] = families
    return out


def _constant_str(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _finding(
    module: Module,
    call: ast.Call,
    ui_name: str,
    family: _Family,
    token: str,
    keywords: dict[str, ast.expr],
) -> Finding | None:
    """The finding, or ``None`` when the prop emits nothing here.

    The ``None`` is load-bearing: a prop whose default is empty
    (``grow``) sets no class as long as the call gives it none, so there
    is nothing to settle. A value that is passed but **computed** falls
    back on the default: whatever it is worth, the base layer renders
    either its class or the default's — in both cases a class of this
    family, so the conflict holds.
    """
    passed = _constant_str(keywords.get(family.prop))
    value = passed or family.default
    if not value:
        return None

    posed = family.emits.get(value, f"la classe de `{family.prop}={value!r}`")
    origin = "passed here" if passed else "its default"
    wanted = family.members[token]

    if posed == token:
        message = (
            f"`ui.{ui_name}(classes=…)` repeats `{token}`: the prop "
            f"`{family.prop}=` already sets it ({origin})."
        )
        hint = (
            f"Remove `{token}` from `classes=` — `{family.prop}={value!r}` "
            f"is enough, and it is what stays true if the theme changes."
        )
    else:
        message = (
            f"`ui.{ui_name}(classes=…)` sets `{token}` on the SAME element "
            f"as the `{family.prop}=` prop, which already emits `{posed}` "
            f"({origin}). Two classes of equal specificity: it is the "
            f"Tailwind SHEET's order that settles it, not the `class` "
            f"attribute's — the HTML carries both and nothing says which "
            f"one won."
        )
        hint = (
            f"Write `{family.prop}={wanted!r}`: it is the value that "
            f"renders `{token}`. `classes=` is only for what no prop "
            f"covers."
        )
    return Finding(
        rule=RULE,
        path=module.path,
        line=call.lineno,
        message=message,
        hint=hint,
    )


def check(module: Module) -> list[Finding]:
    """The ``classes=`` entries a prop of the same call already sets."""
    calls = [
        node
        for node in ast.walk(module.tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "ui"
    ]
    if not calls:
        return []

    judged = _judged()
    findings: list[Finding] = []
    for call in calls:
        ui_name = call.func.attr  # type: ignore[union-attr]
        families = judged.get(ui_name)
        if not families:
            continue
        keywords = {kw.arg: kw.value for kw in call.keywords if kw.arg}
        written = next(
            (
                text
                for name in _CLASS_KWARGS
                if (text := _constant_str(keywords.get(name)))
            ),
            None,
        )
        if not written:
            continue

        for token in written.split():
            if _deliberate(token):
                continue
            for family in families:
                if token not in family.members:
                    continue
                found = _finding(module, call, ui_name, family, token, keywords)
                if found is not None:
                    findings.append(found)
    return findings
