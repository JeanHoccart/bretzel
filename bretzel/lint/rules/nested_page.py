"""Rule: a ``@page`` declared in a function body, harvested by nothing.

The silence it closes
---------------------

``@page`` **marks** the function, it registers nothing — that is
anti-rule 4, and it is what makes import order irrelevant. Registration
comes from ``include``, which sweeps a module's **top-level** callables.
A function defined inside another's body is an attribute of no module:
the sweep cannot see it.

::

    def build_app():
        app = Bretzel(...)

        @page("/")                 # marked, never harvested
        def home() -> None:
            ui.text("hello")

        app.include(__name__)      # only sees the top level
        return app

The app starts, says nothing, and returns **404 on all its pages**. And
404 is exactly what a typo in the path returns: one re-reads one's
``@page``, one's prefix, one's ``include`` — and everything is correct.

A real case, in this repository
-------------------------------

``tests/unit/server/test_protocol_compat_gate.py`` has declared a ``/``
page this way since 2026-08-01. Measured on 2026-09-10: ``GET /``
returns **404** and ``home`` is not an attribute of the module. The tests
pass because they POST to the action route and never visit the page — so
nothing has ever reported it.

The three LEGITIMATE forms, and why the rule spares them
--------------------------------------------------------

``include`` accepts three things, and two of them make a nested page
perfectly valid:

1. ``app.include(home)`` — a marked callable, passed directly;
2. ``PAGES.append(home)`` / ``return home`` — the iterable, which its
   docstring describes as the path for "dynamically generated pages that
   cannot be tied to a module name";
3. the module, which is the only case where nesting kills the page.

The rule cannot know what ``include`` does, but it can read one thing:
**is the function's name referenced after its definition?** In forms 1
and 2 it necessarily is — that is how one hands it to somebody. In form 3
it never is. The criterion is therefore not "nested", it is "nested AND
never taken up again": a page no expression names can be harvested by
nobody.

Measured over ``tests/`` (75 nested declarations), that is what separates
the real case above from the vast majority, which pass the function to
``include``.

``error_page`` is judged the same way: ``include`` sweeps it through the
same path, and a mute error page is even more discreet — one only visits
it when something is broken.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "page-declared-in-a-function"

#: The marks ``include`` harvests at a module's top level.
_MARKS = frozenset({"page", "error_page"})

_Func = ast.FunctionDef | ast.AsyncFunctionDef


def _decorator_name(node: ast.expr) -> str | None:
    """``page`` for ``@page``, ``@page("/")``, ``@bretzel.page("/")``."""
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_marked(func: _Func) -> bool:
    return any(_decorator_name(d) in _MARKS for d in func.decorator_list)


def _nested_functions(tree: ast.AST) -> list[tuple[_Func, _Func]]:
    """The ``(nested function, enclosing function)`` pairs.

    A function nested inside a CLASS is not one of them: a method is an
    attribute of its class, not a local, and the case does not arise for
    a page. So we only descend into function bodies.
    """
    couples: list[tuple[_Func, _Func]] = []

    def descend(node: ast.AST, enclosing: _Func | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                if enclosing is not None:
                    couples.append((child, enclosing))
                descend(child, child)
            elif isinstance(child, ast.ClassDef):
                descend(child, None)
            else:
                descend(child, enclosing)

    descend(tree, None)
    return couples


def _is_referenced(name: str, scope: _Func) -> bool:
    """Is the name read anywhere in the enclosing function?

    An ``ast.Name`` in LOAD is enough: ``include(home)``,
    ``PAGES.append(home)``, ``return home`` all produce one. The
    definition itself is not a ``Name`` — so it cannot count itself.
    """
    return any(
        isinstance(node, ast.Name)
        and node.id == name
        and isinstance(node.ctx, ast.Load)
        for node in ast.walk(scope)
    )


def check(module: Module) -> list[Finding]:
    """The marked pages no sweep can reach."""
    findings: list[Finding] = []
    for func, enclosing in _nested_functions(module.tree):
        if not _is_marked(func) or _is_referenced(func.name, enclosing):
            continue
        mark = next(
            n for d in func.decorator_list if (n := _decorator_name(d)) in _MARKS
        )
        findings.append(
            Finding(
                rule=RULE,
                path=module.path,
                line=func.lineno,
                message=(
                    f"`@{mark}` on `{func.name}`, declared inside "
                    f"`{enclosing.name}()` and never taken up again — no "
                    f"`include` can harvest it."
                ),
                hint=(
                    "`@page` MARKS the function; it is `include` that "
                    "registers, by sweeping a module's top level. A local is "
                    "not there, and the app returns 404 without saying "
                    "anything. Move it up to module level, or pass it "
                    "directly: `app.include(" + func.name + ")`."
                ),
            )
        )
    return findings
