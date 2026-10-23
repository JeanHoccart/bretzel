"""A checkable control without a label sits on the middle of its line.

The root of a checkbox, a radio or a switch is an ``inline-flex``
``<label>``. Without text, its baseline is the BOTTOM of the box, and the
default ``vertical-align: baseline`` set it on the text baseline: in a
table cell the box stood 3 px above the middle of the row, next to a
centred ID and subject (measured 2026-10-23 on the python-ui-shootout
helpdesk). ``align-middle`` puts it where the eye expects it, with or
without a label.

The population: every public component whose render wraps a checkable
``<input>`` in a ``<label>`` — found by rendering, not by name, so a new
checkable control joins the sweep on its own.
"""

from __future__ import annotations

from bretzel.core.tree import Element
from tests.consistency._discovery import (
    public_component_classes,
    rendered_node_of,
    ui_name_of,
    walk_elements,
)

_CHECKABLE = {"checkbox", "radio"}


def checkable_labels(node: Element) -> list[Element]:
    """The ``<label>`` elements that wrap a checkbox or radio ``<input>``."""
    return [
        el for el in walk_elements(node)
        if el.tag == "label" and any(
            c.tag == "input" and c.attrs.get("type") in _CHECKABLE
            for c in walk_elements(el)
        )
    ]


def off_the_middle(label: Element) -> bool:
    return "align-middle" not in str(label.attrs.get("class", "")).split()


def population() -> dict[str, list[Element]]:
    out: dict[str, list[Element]] = {}
    for cls in public_component_classes():
        node = rendered_node_of(cls)
        if node is not None and (labels := checkable_labels(node)):
            out[ui_name_of(cls)] = labels
    return out


def test_the_sweep_finds_the_checkable_controls() -> None:
    found = set(population())
    assert {"checkbox", "radio", "radio_group", "switch"} <= found, found


def test_every_checkable_control_sits_mid_line() -> None:
    bad = sorted(name for name, labels in population().items()
                 if any(off_the_middle(label) for label in labels))
    assert not bad, (
        f"{bad}: the root <label> has no `align-middle`; without a label its "
        "baseline is the bottom of the box, and it sits above the middle of "
        "a table row or a line of text."
    )


def test_the_detector_still_bites() -> None:
    def label(classes: str) -> Element:
        box = Element(tag="input", attrs={"type": "checkbox"})
        return Element(tag="label", attrs={"class": classes}, children=(box,))

    root = Element(tag="div", children=(label("inline-flex items-center"),))
    assert len(checkable_labels(root)) == 1
    assert off_the_middle(label("inline-flex items-center"))
    assert not off_the_middle(label("inline-flex items-center align-middle"))
    # A text input in a label is not a checkable control.
    text = Element(tag="label", children=(Element(tag="input", attrs={"type": "text"}),))
    assert not checkable_labels(text)
