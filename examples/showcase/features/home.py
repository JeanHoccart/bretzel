"""``/`` — the front door: what Bretzel looks like, and under which identity."""

from bretzel import ui
from bretzel.introspect import ComponentInfo, describe_components
from examples.showcase.app.catalog import CATALOG
from examples.showcase.lib.identities import IDENTITIES, Identity
from examples.showcase.lib.preview import sample_screen

SUMMARY = ("Every Bretzel component in real uses, with its Python code, "
           "under a theme you can switch and tune live.")


def component_count() -> int:
    """The components ``bretzel describe`` lists."""
    return sum(isinstance(info, ComponentInfo) for info in describe_components())


def swatches(identity: Identity) -> None:
    with ui.hstack(gap="none"):
        for color in identity.swatches():
            ui.hstack(classes="size-5 -mr-1.5 rounded-full border-2 border-(--color-surface)",
                      style=f"background: {color}")


def identity_card(identity: Identity) -> None:
    with ui.card(padding="md", hoverable=True, on_click=identity.apply(),
                 classes="cursor-pointer"), ui.vstack(gap="sm"):
        with ui.hstack(justify="between"):
            ui.text(identity.name, weight="semibold")
            swatches(identity)
        ui.text(identity.tagline, size="sm", color="muted")


def page() -> None:
    with ui.vstack(gap="md"):
        ui.badge(f"{component_count()} components · zero npm", color="primary", variant="soft",
                 icon_left="sparkles")
        ui.heading("Components for Python web apps", level=1, size="4xl")
        ui.text(
            "Every piece of Bretzel's UI, shown in real uses with the Python "
            "that renders it. Pick an identity below and the whole catalogue "
            "repaints — or open the studio and make your own.",
            size="lg", color="muted", classes="max-w-2xl",
        )
        with ui.hstack(gap="sm", wrap=True):
            ui.button("Browse the components", icon_right="arrow-right",
                      href="/button")
            ui.button("Open the theme studio", icon_left="palette",
                      variant="outline", href="/studio")

    with ui.vstack(gap="sm"):
        ui.heading("Pick an identity", level=2, size="xl")
        ui.text("A whole theme each — colours in both modes, corners, "
                "stroke, density and type. One click repaints every page.",
                color="muted")
        with ui.grid(min_col="16rem", gap="md"):
            for identity in IDENTITIES:
                identity_card(identity)

    with ui.vstack(gap="sm"):
        ui.heading("One screen, every layer", level=2, size="xl")
        ui.text("Cards, charts, a form and a table — the same components "
                "you will find page by page below.", color="muted")
        with ui.card(padding="lg"):
            sample_screen()

    with ui.vstack(gap="sm"):
        ui.heading("The catalogue", level=2, size="xl")
        with ui.grid(min_col="16rem", gap="md"):
            for group, entries in CATALOG:
                with ui.card(padding="md"), ui.vstack(gap="xs"):
                    ui.text(group, weight="semibold")
                    for slug, label, _icon in entries:
                        ui.link(label, href=f"/{slug}")
