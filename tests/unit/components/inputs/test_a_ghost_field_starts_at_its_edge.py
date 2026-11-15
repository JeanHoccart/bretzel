"""Un champ ``ghost`` n'a pas de retrait horizontal : son texte, ses
étiquettes, la barre d'un éditeur partent de son bord (les lignes À / Objet
d'un mail). Le retrait vertical reste — même hauteur que ``surface``.
"""

from __future__ import annotations

import re

import pytest

from bretzel import ui
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize

_INLINE = re.compile(r"^p[xse]-\S+$")

#: Each field, and the regex that finds its frame's opening tag.
FRAMES = {
    "input": (lambda v: ui.input(placeholder="x", variant=v), r"<input [^>]*bz-input"),
    "textarea": (lambda v: ui.textarea(variant=v), r"<textarea [^>]*bz-textarea"),
    "select": (lambda v: ui.select(["a"], variant=v), r'<button [^>]*aria-haspopup="listbox"'),
    "combobox": (lambda v: ui.combobox(["a"], variant=v), r'<div [^>]*role="combobox"'),
    "tags_input": (lambda v: ui.tags_input(["a"], variant=v), r'<div [^>]*bz-ref="bztrigger"'),
    "editor": (lambda v: ui.editor(variant=v), r'<div [^>]*role="toolbar"'),
}


def frame_classes(name: str, variant: str) -> list[str]:
    build, opening = FRAMES[name]
    with render_isolated():
        html = serialize(build(variant).render())
    tag = re.search(opening + r"[^>]*>", html) or re.search(opening, html)
    start = tag.start()
    head = html[start:html.index(">", start)]
    return re.search(r'class="([^"]*)"', head).group(1).split()


@pytest.mark.parametrize("name", sorted(FRAMES))
def test_ghost_drops_the_inline_padding(name: str) -> None:
    assert [c for c in frame_classes(name, "surface") if _INLINE.match(c)], (
        f"{name}: the surface frame should have its padding")
    assert not [c for c in frame_classes(name, "ghost") if _INLINE.match(c)], name


def test_the_vertical_padding_stays() -> None:
    assert any(c.startswith("py-") for c in frame_classes("tags_input", "ghost"))
