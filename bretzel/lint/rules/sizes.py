"""Rule: SIBLING form controls at different sizes.

The silence it closes
---------------------

Nothing breaks. No class is missing, no attribute is inert, the page
renders 200 and the app works. Two fields side by side simply do not have
the same height ::

    with ui.grid(cols=2):
        with ui.form_field(label="Period"):
            ui.date_range_picker(size="sm")     # h-8 → 32 px
        with ui.form_field(label="Type"):
            ui.select(...)                       # default md → 40 px

Eight pixels. It is the kind of gap a code review does not see — both
lines are correct taken separately, and the flaw only exists in their
*neighbourhood*.

What the rule considers a neighbourhood
---------------------------------------

The **row** containers: ``ui.grid``, ``ui.hstack``, ``ui.form``. Not
``ui.vstack``: it is this repository's PAGE container, so a group would
swallow a whole bench card — controls that never touch each other on
screen. A neighbourhood that contains the whole page is not a
neighbourhood.

The sweep does not descend into a nested container: two distinct rows are
two groups, not one.

Why the defaults are RESOLVED
-----------------------------

``ui.select(size="md")`` and ``ui.select()`` render the same HTML.
Treating "absent" as a value in its own right would produce a finding on
correct code — that is the half that costs (cf.
``test_lint_rules_are_not_vacuous``). The default is therefore read from
the **class**, through the ``reactive_prop`` descriptor, never guessed.

A computed size (``size=state.size``) is out of a static read's reach:
the control is ignored, it counts neither as agreeing nor as disagreeing.

The family judged
-----------------

The components of the ``inputs`` family that carry a ``size`` vocabulary
— **discovered** by :func:`~bretzel.introspect.describe_components`,
never listed here. A new field enters on its own. It is the same
refusal :mod:`bretzel.lint.rules.variant` makes to hand-written tables in
a linter: they drift from the code they judge.

⚠️ What the rule does NOT say
-----------------------------

That an equal ``size=`` gives an equal height. That is a fact of the
rendering engine, not of the text — a control can render taller **while
writing the same token** as the others. No linter can see that; it is
``tests/runtime_js/test_form_controls_share_one_height.py`` that guards
it.

And it has no escape hatch. A deliberate mix — a bench comparing two
sizes side by side — is frozen in ``test_lint_baseline_on_examples``,
with its reason, like the playground's non-literal ``ui.html`` calls.
"""

from __future__ import annotations

import ast
import collections

from bretzel.lint.corpus import Module, catalogue
from bretzel.lint.report import Finding

RULE = "mixed-sizes"

#: The ROW containers. Why these three: cf. the docstring.
_ROW_CONTAINERS: frozenset[str] = frozenset({"grid", "hstack", "form"})


def _judged() -> dict[str, str]:
    """``ui.<name>`` → its default size, for the ``inputs`` family.

    Read live: the family comes from introspection, the default from the
    ``reactive_prop`` descriptor carried by the class. Nothing is copied
    here, so nothing can drift from the catalogue.
    """
    from bretzel.components import ui as ui_ns
    from bretzel.components.base.component import Component
    from bretzel.introspect import ComponentInfo

    out: dict[str, str] = {}
    for info in catalogue().values():
        if not isinstance(info, ComponentInfo):
            continue
        if info.family != "inputs" or not info.size_values:
            continue
        cls = getattr(ui_ns, info.ui_name, None)
        if not (isinstance(cls, type) and issubclass(cls, Component)):
            continue
        for base in cls.__mro__:
            descriptor = vars(base).get("size")
            default = getattr(descriptor, "default", None)
            if isinstance(default, str):
                out[info.ui_name] = default
                break
    return out


def _ui_name(node: ast.AST) -> str | None:
    """``ui.input(...)`` → ``"input"``, sinon ``None``."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "ui"
    ):
        return func.attr
    return None


def _resolved_size(call: ast.Call, ui_name: str, defaults: dict[str, str]) -> str | None:
    """This call's EFFECTIVE size, or ``None`` when unreadable."""
    for kw in call.keywords:
        if kw.arg != "size":
            continue
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
        return None  # computed: out of reach of a static read
    return defaults.get(ui_name)


def _opens_a_row(node: ast.AST) -> bool:
    """``with ui.hstack(...):`` — a nested row, whose BODY is another group.

    The ``Call`` check above only sees ``ui.hstack(...)`` as an expression;
    written as a ``with``, the container is an ``ast.With`` whose
    ``_ui_name`` is ``None``, and its body would be swept as part of the
    row above: a textarea and the file picker in the ``hstack`` UNDER it
    would be judged neighbours.
    """
    return isinstance(node, ast.With) and any(
        _ui_name(item.context_expr) in _ROW_CONTAINERS for item in node.items
    )


def _controls_in(
    nodes: list[ast.AST], judged: dict[str, str]
) -> list[tuple[ast.Call, str]]:
    """THIS neighbourhood's controls — without descending into a nested
    container, which is another row and therefore another group.

    Takes the row's BODY, and judges each statement of it before looking
    inside. Looking only at a statement's CHILDREN would miss a ``with
    ui.hstack():`` written directly in a row's body: its fields would
    count as the outer row's neighbours, against the message's own
    promise (« a nested container is another neighbourhood »).
    """
    found: list[tuple[ast.Call, str]] = []
    for node in nodes:
        name = _ui_name(node)
        if name in judged:
            found.append((node, name))  # type: ignore[arg-type]
            continue
        if name in _ROW_CONTAINERS or _opens_a_row(node):
            continue
        found.extend(_controls_in(list(ast.iter_child_nodes(node)), judged))
    return found


def check(module: Module) -> list[Finding]:
    """One finding per neighbourhood whose controls do not agree."""
    rows = [node for node in module.nodes if _opens_a_row(node)]
    if not rows:
        return []

    judged = _judged()
    findings: list[Finding] = []

    for row in rows:
        found = _controls_in(list(row.body), judged)
        sized = [
            (call, name, size)
            for call, name in found
            if (size := _resolved_size(call, name, judged)) is not None
        ]
        if len(sized) < 2:
            continue
        tally = collections.Counter(size for _, _, size in sized)
        if len(tally) < 2:
            continue

        # Who is at fault? Only when there is a STRICT majority. On a
        # 1–1 tie, naming a culprit is arbitrary: `most_common` returns
        # the first inserted, which may be the correct field. We then
        # name both and let the author decide.
        ranked = tally.most_common()
        strict = len(ranked) > 1 and ranked[0][1] > ranked[1][1]

        if strict:
            majority = ranked[0][0]
            guilty = [(c, n, sz) for c, n, sz in sized if sz != majority]
            line = guilty[0][0].lineno
            named = ", ".join(f"`ui.{n}`={sz!r}" for _, n, sz in guilty[:3])
            message = (
                f"{named} neighbour(s) {tally[majority]} control(s) at "
                f"{majority!r} in the same container."
            )
        else:
            line = sized[0][0].lineno
            seen: list[str] = []
            for _, n, sz in sized:
                label = f"`ui.{n}`={sz!r}"
                if label not in seen:
                    seen.append(label)
            message = (
                "sibling controls do not have the same size: "
                + ", ".join(seen[:4])
                + ("…" if len(seen) > 4 else "")
                + "."
            )

        findings.append(
            Finding(
                rule=RULE,
                path=module.path,
                line=line,
                message=message,
                hint=(
                    "Sibling fields at different sizes do not align: "
                    "each step is a distinct height, and the gap only "
                    "shows on the rendered page. Put them at the same "
                    "size — or separate them, a nested container is "
                    "another neighbourhood. A default counts as its "
                    "value: "
                    f"`ui.{sized[0][1]}()` is "
                    f"{judged.get(sized[0][1], '?')!r}."
                ),
            )
        )
    return findings
