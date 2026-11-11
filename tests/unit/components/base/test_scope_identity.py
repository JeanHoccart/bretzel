"""``_ensure_scope_identity`` — stable id for bz-data overlays.

Overlays build their ``bz-data`` scope inside ``render()`` (after
``_needs_identity`` already ran), so without this stamp the runtime would
assign a counter-based ``bz-id`` that changes every re-render — breaking
scope continuity (and teleported panels) inside a ``@refreshable``.
"""

from __future__ import annotations

from bretzel import ui
from bretzel.components.base.universals import _ensure_scope_identity
from bretzel.components.base.testing import render_isolated
from bretzel.core.tree import Element


def test_stamps_stable_id_on_bzdata_root() -> None:
    with render_isolated():
        c = ui.button("trigger")          # any component with an allocated id
        node = Element(tag="div", attrs={"bz-data": "{ open: false }"},
                       children=())
        out = _ensure_scope_identity(c, node)
    assert out.attrs["id"] == c.id
    assert out.attrs["bz-id"] == c.id


def test_noop_when_id_already_present() -> None:
    with render_isolated():
        c = ui.button("trigger")
        node = Element(tag="div", attrs={"bz-data": "{}", "id": "keep"},
                       children=())
        out = _ensure_scope_identity(c, node)
    assert out.attrs["id"] == "keep"
    assert "bz-id" not in out.attrs           # untouched


def test_noop_without_bzdata() -> None:
    with render_isolated():
        c = ui.button("trigger")
        node = Element(tag="div", attrs={"class": "x"}, children=())
        out = _ensure_scope_identity(c, node)
    assert "id" not in out.attrs


def test_an_overlay_renders_with_an_id() -> None:
    # End-to-end : a real overlay's rendered root carries id + bz-id. It was
    # the tooltip until 2026-10-27; the tooltip has no scope any more (a
    # ``data-bz-tip`` wrapper and the page's shared panel).
    with render_isolated():
        tip = ui.popover(trigger=ui.button("trigger"))
        with tip:
            ui.text("HINT")
        node = tip.render()
    assert node.attrs.get("id")
    assert node.attrs.get("bz-id") == node.attrs.get("id")
    assert "bz-data" in node.attrs
