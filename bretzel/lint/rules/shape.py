"""Rule: a theme override that keeps the NAME and changes the SHAPE.

The silence it closes
---------------------

``unknown-theme-vocabulary`` refuses the names nothing reads, but it
**deliberately exempts** the groups addressed by a value (``sizes``,
``variants``, ``paddings``…): adding a key there is the supported way of
declaring one's own variant, and reporting it would condemn the only
clean way of deviating from the shipped theme.

This rule goes through that hole without reopening the door. It only
judges the keys that **already exist** in the shipped theme, and one
thing only: their shape. A new key stays exempt — it has no shipped
counterpart, so there is nothing to contradict.

The two directions, measured on 2026-09-10
------------------------------------------

They do not behave alike, and that is what makes the first one a
priority ::

    # `button.sizes.md` ships as a STRING — one writes a dict
    Theme(components={"button": {"sizes": {"md": {"root": "h-8 px-3"}}}})

The button loses **all** its size tokens. Measured on its ``class=``:
``h-10 px-4 text-sm gap-2`` before, nothing after. The page renders 200,
the HTML is valid, no test turns red — the button is simply bare, at its
content's size. That is the family ``check`` exists to catch.

::

    # `select.sizes.md` ships as a DICT — one writes a string
    Theme(components={"select": {"sizes": {"md": "h-8 px-3"}}})

That one raises: ``AttributeError: 'str' object has no attribute 'get'``.
Loud, hence less urgent — but the raise happens at RENDER time, so on a
rarely exercised page it waits for production, and it names neither the
theme, nor the component, nor the key. A static finding is better than a
stack trace.

What it does not read, and stays quiet about
--------------------------------------------

A value a static read cannot classify — a variable, a call, a
``**spread``, a computed key — is ignored without noise. Same refusal as
in :mod:`bretzel.lint.rules.theme`: reporting what cannot be read
produces noise on correct code.

A **scalar** group has no entries, so no shape to compare:
:func:`~bretzel.introspect.theme_shapes` does not describe it, and the
rule has nothing to say about it.

The shipped shape comes from :func:`~bretzel.introspect.theme_shapes` —
never from a table written here. A table of names in a linter drifts from
the code it claims to judge; it is the same refusal ``variant`` and
``sizes`` make, and the reason ``theme_vocabulary`` was centralised on
2026-08-16.

⚠️ Debt noted, not paid: this is the **third** rule to read a literal
``Theme(components={…})`` (with ``theme`` and ``variant``), and each
carries its version of the same two AST helpers. The package's convention
is "a rule is pure, it knows neither corpus nor floor", so it was
followed rather than refactoring two rules that work; the extraction is
recorded in ``.claude/work/todo.md``.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding
from bretzel.lint.rules._theme_calls import component_maps, dict_items

RULE = "theme-step-changed-shape"

#: What a value we can classify returns. ``None`` = unreadable.
_DICT = "dict"
_STR = "str"


def _written_shape(node: ast.expr) -> str | None:
    """A WRITTEN value's shape, or ``None`` when it is unreadable.

    ``ast.JoinedStr`` (an f-string) and concatenation count as strings:
    they produce a string for certain, whatever their content. It is the
    shape that is judged, not the value — so there is no need to know
    what the interpolation will be worth.
    """
    if isinstance(node, ast.Dict):
        return _DICT
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _STR
    if isinstance(node, ast.JoinedStr):
        return _STR
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _written_shape(node.left)
        return left if left == _STR and _written_shape(node.right) == _STR else None
    return None


def _consequence(shipped: str, written: str) -> tuple[str, str]:
    """What the fault really produces — short message, long hint."""
    if shipped == _STR and written == _DICT:
        return (
            "the step loses ALL its tokens",
            "The theme ships a class string here. A dict replaces it, and "
            "the component composes nothing any more: it renders at its "
            "content's size, in 200, with no error. Write the whole string.",
        )
    return (
        "the render RAISES",
        "The theme ships a table of sub-slots here. A string replaces it, "
        "and the component raises `AttributeError: 'str' object has no "
        "attribute 'get'` at render time. Override the sub-slots you "
        "change — the merge is deep, the others stay at the shipped theme.",
    )


def check(module: Module) -> list[Finding]:
    """The theme overrides whose shape contradicts the shipped theme."""
    calls = list(component_maps(module.tree))
    if not calls:
        return []

    from bretzel.introspect import theme_shapes

    shapes = theme_shapes()
    findings: list[Finding] = []
    for components in calls:
        for comp_name, _, comp_value in dict_items(components):
            groups = shapes.get(comp_name)
            if groups is None:
                # `unknown-theme-vocabulary` already says it, and better.
                continue
            for group, _, group_value in dict_items(comp_value):
                entries = groups.get(group)
                if entries is None:
                    continue
                for key, key_node, value_node in dict_items(group_value):
                    shipped = entries.get(key)
                    if shipped is None:
                        # A NEW key — that is an extension, not a fault.
                        continue
                    written = _written_shape(value_node)
                    if written is None or written == shipped:
                        continue
                    short, hint_text = _consequence(shipped, written)
                    findings.append(
                        Finding(
                            rule=RULE,
                            path=module.path,
                            line=key_node.lineno,
                            message=(
                                f"`{comp_name}.{group}.{key}` ships as "
                                f"`{shipped}` and is overridden as "
                                f"`{written}` — "
                                f"{short}."
                            ),
                            hint=(
                                f"{hint_text} "
                                f"`bretzel describe {comp_name}` names its groups."
                            ),
                        )
                    )
    return findings
