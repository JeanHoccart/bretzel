"""Universal ``classes=`` must land on every component's true root.

Regression for the systemic drop the matrix reactivity harness caught :
many components compose their root via a non-"root" theme slot (Input's
bare/affix paths, Slider, Badge, Banner, Skeleton, Empty state…), so the
old ``compose_class``-only append silently dropped ``classes=``. The fix
applies it centrally in ``_apply_universal_modifiers`` (the metaclass
render wrap), so the contract holds for the whole catalogue — these cases
span the families that were broken AND the ones that always worked.
"""

from __future__ import annotations

import pytest

from bretzel import ui
from bretzel.components.base.testing import render_isolated
from bretzel.render import serialize_html

MARKER = "zzmark-classes"


def _html(factory) -> str:
    with render_isolated():
        box = ui.vstack()
        with box:
            factory()
        return serialize_html(box)


CASES = {
    # Were broken — root composed via a non-"root" slot.
    "input_bare": lambda: ui.input(classes=MARKER, placeholder="x"),
    "input_icon": lambda: ui.input(classes=MARKER, icon_left="search"),
    "input_affix": lambda: ui.input(classes=MARKER, prefix="$"),
    "slider": lambda: ui.slider(classes=MARKER, value=40),
    "badge": lambda: ui.badge("x", classes=MARKER),
    "banner": lambda: ui.banner("x", classes=MARKER),
    "skeleton": lambda: ui.skeleton(classes=MARKER),
    "empty_state": lambda: ui.empty_state("x", classes=MARKER),
    # Always worked — guard against a regression in the central path.
    "button": lambda: ui.button("x", classes=MARKER),
    "select": lambda: ui.select(options=[("a", "A")], classes=MARKER),
    "textarea": lambda: ui.textarea(classes=MARKER),
    "alert": lambda: ui.alert("x", classes=MARKER),
    "avatar": lambda: ui.avatar(initials="AB", classes=MARKER),
    "progress": lambda: ui.progress(value=30, classes=MARKER),
    "spinner": lambda: ui.spinner(classes=MARKER),
    "badge_layout": lambda: ui.badge("x", classes=MARKER, icon_left="star"),
}


@pytest.mark.parametrize("name", list(CASES))
def test_user_classes_reach_the_dom(name: str) -> None:
    assert MARKER in _html(CASES[name]), f"{name} dropped classes="
