"""The recipes: one complete app per common request, in Markdown.

Each ``<slug>.md`` of this folder is the only copy of its recipe. The docs
serve it twice — raw at ``/recipes/<slug>.md``, the address ``/llms.txt``
gives an assistant, and as a page at ``/recipes/<slug>`` — and the sidebar
lists it. ``tests/consistency/test_a_recipe_is_a_working_app.py`` runs the
app each one holds.

A recipe opens on its ``# Title``, then the need in a ``>`` quote, said
the way a user says it. A file that does not is refused here, at import:
the docs do not start on a recipe they cannot list.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import takewhile
from pathlib import Path

FOLDER = Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class Recipe:
    """One recipe file, read."""

    slug: str
    title: str
    need: str
    text: str


def read_recipe(path: Path) -> Recipe:
    """The recipe in ``path``: its title, its need, and its whole text."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or not lines[0].startswith("# "):
        raise ValueError(f"{path.name}: a recipe opens on its '# Title' line")
    first = next((i for i, line in enumerate(lines) if line.startswith(">")), None)
    if first is None:
        raise ValueError(f"{path.name}: a recipe says its need in a '>' quote")
    quoted = takewhile(lambda line: line.startswith(">"), lines[first:])
    need = " ".join(line.removeprefix(">").strip() for line in quoted)
    return Recipe(slug=path.stem, title=lines[0].removeprefix("# ").strip(),
                  need=need, text=text)


#: Every recipe, in the order of their file names.
RECIPES: tuple[Recipe, ...] = tuple(read_recipe(path) for path in sorted(FOLDER.glob("*.md")))
