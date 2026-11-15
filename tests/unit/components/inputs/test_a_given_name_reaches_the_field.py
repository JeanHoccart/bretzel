"""Un ``aria-label`` donné par l'app nomme le champ où l'on tape, pas son
enveloppe.

Les champs dont la racine est une ``<div>`` (le focusable est dedans)
déplacent les attributs ARIA de leur ``ui.form_field`` vers le focusable
(``relocate_aria``). ``aria-label`` n'en était pas : posé par
``attrs={"aria-label": …}``, il restait sur la ``<div>``, et le champ
était annoncé sans nom — vu par « every control has a name » du probe sur
la page ``/ladder``.
"""

from __future__ import annotations

import html
import re

import pytest

from bretzel import ui
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize

BUILDERS = {
    "tags_input": lambda **kw: ui.tags_input(["a"], **kw),
    "combobox": lambda **kw: ui.combobox(["a"], multiple=True, **kw),
    "number_input": lambda **kw: ui.number_input(value=1, **kw),
    "select": lambda **kw: ui.select(["a"], **kw),
    "date_picker": lambda **kw: ui.date_picker(**kw),
}


def element_named(out: str) -> str:
    """The tag of the element carrying ``aria-label="Nom"``, and its role."""
    at = out.index('aria-label="Nom"')
    opening = list(re.finditer(r"<(\w+)\s", out[:at]))[-1]
    head = out[opening.start():at]
    role = re.search(r'\srole="(\w+)"', head)
    return opening.group(1) + (f"[role={role.group(1)}]" if role else "")


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_the_name_lands_on_the_focusable(name: str) -> None:
    with render_isolated():
        out = html.unescape(serialize(BUILDERS[name](attrs={"aria-label": "Nom"}).render()))
    assert out.count('aria-label="Nom"') == 1, f"{name}: the name was lost, or doubled"
    # A focusable: a field, a button, or an element with a control's role —
    # never the bare wrapper <div>.
    assert element_named(out) != "div", f"{name}: the name stayed on the wrapper"
