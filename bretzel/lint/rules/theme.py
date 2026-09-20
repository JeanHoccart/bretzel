"""Rule: a ``Theme(components={…})`` name that nothing reads.

The silence it closes
---------------------

The theme layer never refused a key. Measured on 2026-08-16, on
``main``:

- ``Theme(components={"crad": {...}})`` — accepted. The component does
  not exist, the override never reaches anything.
- ``Theme(components={"card": {"slotz": {...}}})`` — accepted. The group
  does not exist.
- ``Theme(components={"card": {"slots": {"rooot": "..."}}})`` — accepted.
  ``Card`` composes ``root``, never ``rooot``.

In all three cases the result is identical: **nothing changes**, with no
error, no warning, no trace in the HTML. It is the symptom one blames on
one's browser cache for half an hour before suspecting one's own typo.

Why a rule and not a raise
--------------------------

Raising at construction would change the behaviour of existing
applications: since the silence is total today, nobody knows whether
their theme carries a dead key. The lint **reports** — it breaks nothing,
and it sees without executing, so it also sees the theme of a module
never imported. Raising stays open, recorded in ``.claude/work/todo.md``.

What it does NOT report, and deliberately
-----------------------------------------

**The unknown keys of the groups addressed by a prop VALUE**
(``variants``, ``sizes``, ``paddings``, ``widths``, ``gaps``…). Adding an
entry there is a **feature**, not a fault: it is the path by which an app
declares its own variant, and it works —
``Theme(components={"button": {"variants": {"brand": "…"}}})`` followed
by ``ui.button(variant="brand")`` renders the variant (verified).
Reporting them would condemn the only clean way of deviating from the
shipped theme.

**The ``slots`` keys, by contrast, are reported**: a slot is not
addressed by a user value but composed by the component's code
(``compose_class("root")``). A name the component never composes is dead
by construction — there is no call that could wake it.

The rule is **pure**: one module, the API index, some findings. It knows
neither corpus nor floor.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding
from bretzel.lint.rules._theme_calls import component_maps, dict_items

RULE = "unknown-theme-vocabulary"

#: The only group whose KEYS are judged. Cf. the docstring: elsewhere, a
#: new key is the supported way of extending the theme.
_KEYED_GROUP = "slots"


def _index() -> dict[str, dict[str, frozenset[str]]]:
    """``THEME_KEY`` → ``group`` → known keys.

    Read from :func:`bretzel.introspect.theme_vocabulary`, the single
    source shared by both theme rules AND the startup validation. A
    hand-written table of names in a linter is exactly what drifts from
    the code it claims to judge — and two parallel derivations are the
    slow version of that.
    """
    from bretzel.introspect import theme_vocabulary

    return theme_vocabulary()


def check(module: Module) -> list[Finding]:
    """The theme names nothing will read."""
    findings: list[Finding] = []
    calls = list(component_maps(module.tree))
    if not calls:
        return findings

    index = _index()
    for components in calls:
        for comp_name, comp_key_node, comp_value in dict_items(components):
            groups = index.get(comp_name)
            if groups is None:
                findings.append(
                    Finding(
                        rule=RULE,
                        path=module.path,
                        line=comp_key_node.lineno,
                        message=(
                            f"`Theme(components={{{comp_name!r}: …}})`: no "
                            f"component has this theme key."
                        ),
                        hint=(
                            "The key is `THEME_KEY`, not always the `ui.*` "
                            "name — `sidebar_section` is written under "
                            "`'sidebar'`. `bretzel describe <name>` gives it."
                        ),
                    )
                )
                continue
            findings.extend(
                _check_groups(module, comp_name, groups, comp_value)
            )
    return findings


def _check_groups(
    module: Module,
    comp_name: str,
    groups: dict[str, tuple[str, ...]],
    comp_value: ast.expr,
) -> list[Finding]:
    findings: list[Finding] = []
    for group, group_key_node, group_value in dict_items(comp_value):
        if group not in groups:
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=group_key_node.lineno,
                    message=(
                        f"`Theme(components={{{comp_name!r}: {{{group!r}: …}}}})` : "
                        f"`{comp_name}` has no `{group}` group."
                    ),
                    hint=(
                        f"Ses groupes : {', '.join(sorted(groups)) or '(aucun)'}. "
                        f"`bretzel describe {comp_name}` les liste."
                    ),
                )
            )
            continue
        if group != _KEYED_GROUP:
            # Elsewhere, a new key extends the theme — that is supported.
            continue
        known = groups[group]
        for slot, slot_key_node, _ in dict_items(group_value):
            if slot not in known:
                findings.append(
                    Finding(
                        rule=RULE,
                        path=module.path,
                        line=slot_key_node.lineno,
                        message=(
                            f"`{comp_name}` composes no `{slot}` slot — "
                            f"the override will reach nothing."
                        ),
                        hint=(
                            f"Its slots: {', '.join(known) or '(none)'}. "
                            f"A slot is composed by the component's code, so "
                            f"a name it does not know is dead: nothing in the "
                            f"app can wake it."
                        ),
                    )
                )
    return findings
