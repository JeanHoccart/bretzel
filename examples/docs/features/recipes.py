"""RECIPES — one complete app per common request, served twice.

The source is ``examples/docs/recipes/*.md`` and nothing else. Each file
is served:

- raw, at ``/recipes/<slug>.md`` (``text/markdown``) — the address
  ``/llms.txt`` lists first, because an assistant learns more from a few
  kilobytes of Markdown read before writing than from a rendered page;
- as a page of the docs, at ``/recipes/<slug>``, through ``ui.markdown``
  in the shell.

``/recipes`` is an index: it lists the files and links to them, with no
prose of its own beyond its heading.

The pages are made one per file, at import, so each one has a fixed route
that the sitemap lists — the same shape as ``stubs.py``.
"""

from __future__ import annotations

from collections.abc import Callable

from starlette.responses import Response

from bretzel import download, page, ui
from examples.docs.features.shell import shell
from examples.docs.recipes import RECIPES, Recipe

PATH = "/recipes"
BY_SLUG = {recipe.slug: recipe for recipe in RECIPES}


def page_url(recipe: Recipe) -> str:
    return f"{PATH}/{recipe.slug}"


def markdown_url(recipe: Recipe) -> str:
    return f"{PATH}/{recipe.slug}.md"


@download(PATH + "/{slug}.md")
def recipe_markdown(slug: str) -> Response:
    """The recipe as it is written — shown by the browser, not saved."""
    recipe = BY_SLUG.get(slug)
    if recipe is None:
        return Response("No such recipe.\n", status_code=404,
                        media_type="text/plain; charset=utf-8")
    return Response(recipe.text, media_type="text/markdown; charset=utf-8")


@page(PATH, layout=shell, title="Recipes · Bretzel docs",
      description="Bretzel recipes: one complete, working app per common request, "
                  "each also served as raw Markdown for AI agents.")
def recipes_page() -> None:
    with ui.container(width="xl"), ui.vstack(gap="lg"):
        ui.heading("Recipes", level=1, size="3xl")
        ui.text(
            "One complete app per common request, with why it works. Each one "
            "is also served as raw Markdown: the form an AI agent reads first.",
            color="muted", size="lg",
        )
        for recipe in RECIPES:
            with ui.card(), ui.vstack(gap="sm"):
                ui.heading(recipe.title, level=2, size="lg")
                ui.text(recipe.need, color="muted")
                with ui.hstack(gap="md", wrap=True):
                    ui.link("Read the recipe", href=page_url(recipe))
                    ui.link("Markdown", href=markdown_url(recipe))


def recipe_body(recipe: Recipe) -> None:
    with ui.container(width="lg"), ui.vstack(gap="md"):
        with ui.hstack(justify="between", align="center", wrap=True):
            with ui.breadcrumb():
                ui.breadcrumb_item("Recipes", href=PATH)
                ui.breadcrumb_item(recipe.title)
            ui.button("Markdown", href=markdown_url(recipe), variant="outline",
                      size="sm", icon_left="file-text")
        ui.markdown(recipe.text)


def make(recipe: Recipe) -> Callable[[], None]:
    def recipe_page() -> None:
        recipe_body(recipe)
    recipe_page.__name__ = recipe_page.__qualname__ = f"recipe_{recipe.slug.replace('-', '_')}"
    return page(page_url(recipe), layout=shell, title=f"{recipe.title} · Bretzel recipes",
                description=recipe.need)(recipe_page)


for _recipe in RECIPES:
    _page = make(_recipe)
    globals()[_page.__name__] = _page
