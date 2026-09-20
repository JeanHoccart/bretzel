"""Rule: a theme that resizes PART of the form controls.

The silence it closes
---------------------

A hand-written size table is a list of the components one thought to
name, and **nothing says it is complete** ::

    Theme(components={
        "input":    {"sizes": {"md": {"input": "h-8 px-3"}}},
        "select":   {"sizes": {"md": {"trigger": "h-8 px-3"}}},
        "combobox": {...},
        # date_picker, number_input, time_picker…: absent
    })

The components named go down, the others keep the default. Measured on
``examples/ecole`` on 2026-09-12: **four text-field heights on one screen
— 30, 32, 36 and 38 px**, and a form of three controls side by side
showed three of them. A user saw it on a screenshot; nothing else could
have said so.

Why the existing rules do not catch it
--------------------------------------

:mod:`bretzel.lint.rules.sizes` compares the ``size=`` **declared at call
sites**: here they are all at the default, and in agreement with each
other. It is the THEME that separates them, downstream. And
``tests/runtime_js/test_form_controls_share_one_height.py`` measures
height parity **with the shipped theme** — an app that sets its own
leaves its scope.

The invariant defended is the same as that gate's, and it is what makes
``size=`` usable: at an equal step, a form control is one height. A
partial override breaks that silently.

What the rule reads
-------------------

The keys of a ``Theme(components={…})`` that carry a ``sizes``, and the
control family **discovered** by
:func:`~bretzel.introspect.describe_components` — never a table written
here. A nineteenth field therefore enters the rule on its own, as it
enters :mod:`bretzel.lint.rules.sizes`.

⚠️ **And the controls the CORPUS actually uses.** That is what separates
an actionable finding from noise: a theme has no reason to resize a
``ui.otp_input`` no screen displays, and holding it against the theme
would turn a useful rule into an endless list. The pass's corpus is read
by :func:`bretzel.lint.corpus.derived`, so once only whatever the number
of modules.

Measured on this repository: without that filter, the rule demands
fourteen components of the kanban's preset; with it, it names two — and
they are exactly the two it displays.

If the theme resizes at least one and forgets at least one the app shows,
that is a finding, and it NAMES the missing ones.

⚠️ What the rule does NOT say
-----------------------------

That everybody must be resized. The recommended way out is the OPPOSITE
— name nobody, and move the scale's BASE: Tailwind's whole spacing scale
derives from ``--spacing``, which ``Theme(spacing=…)`` has carried since
2026-09-13 (before that, one had to go through ``css=``, which is not
what that door is for). One token instead of N tables, hence a coverage
that is no longer a list and can no longer be partial. And the shipped
default is ALREADY a tool's: a size table that only tightens probably no
longer has a reason to exist.

Nor does it judge an override that does not touch ``sizes`` — colours,
radii, slots: those move no height.

Nor the case of a theme WITHOUT a corpus — a rule exercised on a single
module has no usage to read, and then judges the whole family. That is
the safe direction: outside ``run``, one finding too many beats a
silence.
"""

from __future__ import annotations

import ast
import pathlib

from bretzel.lint import corpus
from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

#: The rule's name, as it appears in a finding.
RULE = "half-overridden-size-step"


def _family() -> frozenset[str]:
    """The form controls that must share one height.

    Read live through introspection: the ``inputs`` family restricted to
    what carries a ``size`` vocabulary. It is the same corpus as
    :mod:`bretzel.lint.rules.sizes`, and for the same reason — a table
    copied into a linter drifts from the code it judges.
    """
    from bretzel.introspect import ComponentInfo, describe_components

    return frozenset(
        info.ui_name
        for info in describe_components()
        if isinstance(info, ComponentInfo)
        and info.family == "inputs"
        and info.size_values
    )


def _theme_calls(tree: ast.AST) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "Theme")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "Theme")
        )
    ]


def _module_dicts(tree: ast.AST) -> dict[str, ast.Dict]:
    """The module constants that are a literal dict.

    ``Theme(components=COMPONENTS)`` is this repository's idiom —
    ``examples/``'s two presets wrote it that way until 2026-09-13, when
    the scale moved to the framework and they were removed. A rule that
    only accepts the INLINE dict would be green over the whole real
    corpus, which is the most expensive form of false negative: it looks
    like it works.
    """
    out: dict[str, ast.Dict] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign | ast.AnnAssign):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                out[target.id] = node.value
    return out


def _resized(call: ast.Call, known: dict[str, ast.Dict]) -> tuple[set[str], int]:
    """The components whose ``sizes`` this ``Theme`` redefines."""
    for kw in call.keywords:
        if kw.arg != "components":
            continue
        value_kw = kw.value
        if isinstance(value_kw, ast.Name):
            value_kw = known.get(value_kw.id)
        if not isinstance(value_kw, ast.Dict):
            continue
        names: set[str] = set()
        for key, value in zip(value_kw.keys, value_kw.values, strict=False):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            if not isinstance(value, ast.Dict):
                continue
            if any(
                isinstance(k, ast.Constant) and k.value == "sizes"
                for k in value.keys
            ):
                names.add(key.value)
        return names, call.lineno
    return set(), call.lineno


def _app_root(theme: pathlib.Path) -> pathlib.Path | None:
    """The app folder this theme belongs to, or ``None``.

    Recognised by the presence of a ``main.py`` IN THE CORPUS — not on
    disk: a static rule must discover nothing the pass has not already
    read. We climb from the theme and stop at the first folder carrying
    one.

    ⚠️ Without that split, the rule is useless on a repository with
    several apps: sweeping ``examples/`` in one go puts the playground in
    the same bag, and the playground exercises EVERY component — so any
    theme would have to resize everything. Measured: 14 components
    demanded of the kanban's preset, against 2 once the app is
    delimited. The broad version looked stricter and served nothing.
    """
    folders = {
        m.path.resolve().parent
        for m in corpus.current()
        if m.path.name == "main.py"
    }
    for parent in theme.resolve().parents:
        if parent in folders:
            return parent
    return None


def _used_in_theme(theme: pathlib.Path) -> frozenset[str]:
    """The ``ui.<name>`` called in the app this theme belongs to.

    Derived once per app and per pass (cf.
    :func:`bretzel.lint.corpus.derived`): the rule runs on every module,
    the question does not change.
    """
    root = _app_root(theme)
    if root is None:
        return frozenset()

    def build() -> frozenset[str]:
        return frozenset(
            node.func.attr
            for m in corpus.current()
            if root in m.path.resolve().parents
            for node in ast.walk(m.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "ui"
        )

    return corpus.derived(f"partial_sizes.ui_calls:{root}", build)


def check(module: Module) -> list[Finding]:
    """The themes that resize only part of the family."""
    family = _family()
    if not family:  # pragma: no cover — introspection is gated elsewhere
        return []
    used = _used_in_theme(module.path)
    if used:
        family = frozenset(family & used)

    findings: list[Finding] = []
    known = _module_dicts(module.tree)
    for call in _theme_calls(module.tree):
        resized, line = _resized(call, known)
        touched = resized & family
        if not touched:
            continue
        forgotten = sorted(family - resized)
        if not forgotten:
            continue
        findings.append(
            Finding(
                rule=RULE,
                path=module.path,
                line=line,
                message=(
                    f"this theme resizes {len(touched)} form control(s) "
                    f"and leaves {len(forgotten)} at the default — "
                    f"{', '.join(forgotten[:4])}"
                    + (" …" if len(forgotten) > 4 else "")
                    + "."
                ),
                hint=(
                    "At an equal step, two controls must be one height: "
                    "that is what makes `size=` usable. A partial table "
                    "breaks the invariant without raising anything "
                    "(measured: four field heights on one screen). Rather "
                    "than lengthening the list, move the scale's BASE: "
                    'Theme(spacing="0.1875rem"). Tailwind\'s whole scale '
                    "derives from it, so nothing can be forgotten — and "
                    "the shipped default is already a tool's, so a table "
                    "that only tightens may have become useless."
                ),
            )
        )
    return findings
