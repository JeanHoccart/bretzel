"""Foundations — describing the UI."""

from bretzel import page, ui

from examples.docs.features.shell import shell


@page("/describe", layout=shell, title="Describe the UI")
def describe_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Describe the UI", level=1, size="3xl")
            ui.text(
                "Before making anything interactive, describe the interface. In "
                "Bretzel, a UI is a tree of Python components—static until state changes.",
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Compose components with `with`", level=2)
                    ui.text(
                        "`ui.*` components are functions. Containers (stacks, cards, "
                        "grids…) open a `with` block; declare their children inside it.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "with ui.card():\n"
                        "    with ui.vstack(gap=\"sm\"):\n"
                        "        ui.heading(\"Profile\", level=2)\n"
                        "        ui.text(\"Member since 2024\", color=\"muted\")\n"
                        "        ui.button(\"Edit\")\n",
                        lang="python",
                    )
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text("The complete list (inputs, overlays, tables, "
                                "charts…) is in", color="muted", size="sm")
                        ui.link("the catalog", href="/components")
                        ui.text(".", color="muted", size="sm")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("A page", level=2)
                    ui.text(
                        "A page is a function decorated with `@page` and its URL. A "
                        "`@layout` draws the shared frame (a sidebar or header) and "
                        "exposes a region through `ui.outlet()` where pages render.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "@page(\"/profile\", layout=shell)\n"
                        "def profile() -> None:\n"
                        "    ui.heading(\"Profile\", level=1)\n",
                        lang="python",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading("Render from state", level=2)
                    ui.text(
                        "The key idea: the UI is built by reading state. Do not modify "
                        "the display by hand—describe what it should be for the current "
                        "state. When state changes, Bretzel computes the UI again. Data "
                        "flows in one direction: state → UI.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "def cart_summary() -> None:\n"
                        "    cart = Cart()\n"
                        "    ui.text(f\"{len(cart.items)} items\")\n"
                        "    for item in cart.items:\n"
                        "        ui.text(item[\"name\"])\n",
                        lang="python",
                    )
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text("Where does this state come from? Next:",
                                color="muted", size="sm")
                        ui.link("Server state →", href="/state-server")
