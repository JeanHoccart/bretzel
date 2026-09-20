"""Rule: a ``variant=`` / ``size=`` value no table carries.

The silence it closes
---------------------

``compose_class`` resolves both props **by their value**, in a theme
table (``bretzel/components/base/component.py``) ::

    variant_template = theme.get("variants", {}).get(variant_value)
    if variant_template:
        parts.append(...)

A gap is not an error: it is a ``None``, an ``if`` that does not take,
and one class fewer. Measured on 2026-08-16 on
``ui.button(variant="does-not-exist")``: the button renders **with no
variant class at all** — no fill, no border, no shadow. It stays in the
flow, it is clickable, it simply no longer looks like a button. No error,
no suspicious attribute in the HTML.

Why these two props, and not the other 24 table groups
------------------------------------------------------

``variant`` and ``size`` are the **only** ones the base layer resolves
itself, for every component, through a single path. ``widths``,
``gaps``, ``paddings``, ``ratios``, ``sides``… are read by each
component's ``render``, with its own prop → group correspondence.
Deriving them from a pluralisation rule would be a hand-written table in
a linter, that is to say the thing that drifts from the code it judges
(same refusal as :mod:`bretzel.lint.rules.kwargs`).

⚠️ ``size=`` cost a detour, and it is worth knowing
----------------------------------------------------

The symmetry with ``variant`` is tempting — ``compose_class`` does
``theme["sizes"].get(size_value)`` — but reading the table's raw keys is
**wrong**: of the catalogue's 44 ``sizes`` tables, 33 are nested, and two
OPPOSITE nestings coexist there —

- ``Checkbox``: ``{"sm": {<slot>: classes}}`` — keys = sizes;
- ``DatePicker``: ``{"input_field": {"sm": classes}}`` — keys = **slots**.

A first version of this rule therefore reported
``ui.date_picker(size="sm")``, which is perfectly correct. The vocabulary
now comes from :attr:`ComponentInfo.size_values`, resolved by
``bretzel.components.base.size_vocabulary`` — which absorbs both tiers by
relying on :data:`~bretzel.components.base.SIZE_SCALE`, the canonical
scale. That scale did not exist in ``bretzel/`` before 2026-08-16: it was
copied five times in ``tests/``, which would have made any read from here
a sixth copy.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence

from bretzel.lint.corpus import Module, current, derived
from bretzel.lint.report import Finding
from bretzel.lint.rules._theme_calls import component_maps, dict_items

RULE = "value-outside-the-table"

#: The props the base layer resolves by their value. Each one's
#: vocabulary comes from ``introspect.prop_vocabulary()``, which knows
#: that ``variant`` reads the keys of ``variants`` whereas ``size``
#: requires resolving both nestings.
_RESOLVED_BY_THE_CORE: tuple[str, ...] = ("variant", "size")

#: The theme group a HOME-MADE value is declared under. Distinct from
#: the vocabulary read: `size` is read resolved (both nestings absorbed)
#: but is declared, like everything else, under `sizes`.
_GROUP_OF: dict[str, str] = {"variant": "variants", "size": "sizes"}


def _shipped() -> dict[str, dict[str, frozenset[str]]]:
    """``THEME_KEY`` → ``variant`` / ``size`` → shipped values.

    Read from :func:`bretzel.introspect.prop_vocabulary`, indexed by PROP
    and not by theme group — the two do not coincide, ``size`` requiring
    both nestings to be resolved. The per-group counterpart
    (:func:`~bretzel.introspect.theme_vocabulary`) serves
    :mod:`bretzel.lint.rules.theme` and the startup validation.

    Indexed by ``THEME_KEY`` so as to join without friction with the
    vocabulary the app declares, which is written under that key.

    ⚠️ For THIS rule, indexing by key is today **indistinguishable** from
    indexing by ``ui.*`` name, and the mutation that inverts it turns red
    nowhere — measured on 2026-08-16 rather than assumed. Of the 8
    components carrying a ``variants`` table, only one has a key
    different from its name (``navbar_section`` → ``navbar``), and its
    sibling ``navbar`` already fills that entry with the **same**
    ``THEME`` object.

    It is written down and not fixed with a contrived test: the
    distinction becomes load-bearing the day a component with variants is
    written under a key no sibling owns — and that day, indexing by name
    would give a false positive on each of its call sites.
    """
    from bretzel.introspect import prop_vocabulary

    return prop_vocabulary()


def _ui_name_to_theme_key() -> dict[str, str]:
    """``ui.<name>`` → its theme key. Eight components differ."""
    from bretzel.introspect import ComponentInfo, describe_components

    return {
        info.ui_name: info.theme_key
        for info in describe_components()
        if isinstance(info, ComponentInfo) and info.theme_key
    }


def _declared_in(tree: ast.Module) -> dict[str, dict[str, set[str]]]:
    """What this tree's literal ``Theme(components={…})`` add.

    The key's node, the second element ``dict_items`` returns, is unused
    here: this rule aggregates a VOCABULARY and locates nothing.
    """
    out: dict[str, dict[str, set[str]]] = {}
    for components in component_maps(tree):
        for theme_key, _, comp_value in dict_items(components):
            groups = out.setdefault(theme_key, {})
            for group, _, group_value in dict_items(comp_value):
                groups.setdefault(group, set()).update(
                    key for key, _, _ in dict_items(group_value)
                )
    return out


def _merge(
    into: dict[str, dict[str, set[str]]], trees: Sequence[ast.Module]
) -> dict[str, dict[str, set[str]]]:
    """Pour ``trees``'s declarations into ``into`` (mutated and returned)."""
    for tree in trees:
        for theme_key, groups in _declared_in(tree).items():
            target = into.setdefault(theme_key, {})
            for group, keys in groups.items():
                target.setdefault(group, set()).update(keys)
    return into


def _declared_everywhere(module: Module) -> dict[str, dict[str, set[str]]]:
    """The union of the pass's corpus theme declarations.

    The current module is included explicitly: outside ``run`` the corpus
    is empty, and a rule called on its own must stay correct about what it
    sees.

    The union is the SAME for a pass's N modules, so it is derived once
    (:func:`~bretzel.lint.corpus.derived`) and not once per module —
    without which the rule is quadratic, which it was until 2026-08-27 for
    56 s over ``examples/``. The only case that leaves the memo is a
    module ABSENT from the corpus: we then start from a copy, so as not to
    pollute the shared derivation with a tree that is not part of it.
    """
    corpus = current()
    if not corpus:
        return _merge({}, [module.tree])

    shared = derived(
        f"{RULE}.declared", lambda: _merge({}, [m.tree for m in current()])
    )
    if any(m.tree is module.tree for m in corpus):
        return shared
    return _merge(
        {key: {g: set(v) for g, v in groups.items()} for key, groups in shared.items()},
        [module.tree],
    )


def check(module: Module) -> list[Finding]:
    """The values no table — shipped or declared — carries."""
    calls = [
        node
        for node in ast.walk(module.tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "ui"
        and any(kw.arg in _RESOLVED_BY_THE_CORE for kw in node.keywords)
    ]
    if not calls:
        return []

    shipped = _shipped()
    keys = _ui_name_to_theme_key()
    declared = _declared_everywhere(module)

    findings: list[Finding] = []
    for call in calls:
        ui_name = call.func.attr  # type: ignore[union-attr]
        theme_key = keys.get(ui_name)
        if theme_key is None:
            continue  # helper, ou symbole inconnu : `unknown-kwarg` s'en charge
        for kw in call.keywords:
            prop = kw.arg or ""
            if prop not in _RESOLVED_BY_THE_CORE:
                continue
            if not isinstance(kw.value, ast.Constant) or not isinstance(
                kw.value.value, str
            ):
                continue  # computed value: out of reach of a static read
            known = shipped.get(theme_key, {}).get(prop, frozenset())
            if not known:
                # No table at all — the component consumes the prop
                # otherwise (`bar_chart`, `file_upload`, `pie_chart` for
                # `variant`, `radio_group` for `size`). We do not judge
                # what we do not understand.
                continue
            group = _GROUP_OF[prop]
            allowed = known | declared.get(theme_key, {}).get(group, set())
            value = kw.value.value
            if value in allowed:
                continue
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=kw.value.lineno,
                    message=(
                        f"`ui.{ui_name}({prop}={value!r})`: no `{value}` "
                        f"entry in the `{group}` table."
                    ),
                    hint=(
                        f"Shipped values: {', '.join(sorted(known))}. "
                        f"The base layer resolves `{prop}=` in `{group}` and "
                        f"IGNORES a gap — the component renders without the "
                        f"class, with no error. For a home-made value, "
                        f"declare it: "
                        f"Theme(components={{{theme_key!r}: {{{group!r}: "
                        f"{{{value!r}: …}}}}}})."
                    ),
                )
            )
    return findings
