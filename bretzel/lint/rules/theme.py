"""Rule: a ``Theme(components={…})`` name that nothing reads.

What it reports
---------------

- ``Theme(components={"crad": {...}})`` — the component does not exist.
- ``Theme(components={"card": {"slotz": {...}}})`` — the group does not
  exist.
- ``Theme(components={"card": {"slots": {"rooot": "..."}}})`` — ``Card``
  composes ``root``, never ``rooot``.

Each of these overrides reaches nothing.

Why a rule as well as the startup refusal
-----------------------------------------

``server/lifecycle._validate_theme`` refuses the same names when an
application starts, against the same vocabulary. A ``Theme`` built on its
own stays valid. The lint sees without executing: it reports the mistake
before anything runs, and it also sees the theme of a module never
imported, which no startup reaches.

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

from bretzel.lint.corpus import Module, derived
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

    return derived(f"{RULE}.index", theme_vocabulary)


def check(module: Module) -> list[Finding]:
    """The theme names nothing will read."""
    findings: list[Finding] = []
    calls = list(component_maps(module))
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
                        f"Its groups: {', '.join(sorted(groups)) or '(none)'}. "
                        f"`bretzel describe {comp_name}` lists them."
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
