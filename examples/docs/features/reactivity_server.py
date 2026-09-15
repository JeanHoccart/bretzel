"""Reactivity — server-side rendering updates."""

from bretzel import page, ui
from examples.docs.features.shell import shell


@page("/reactivity-server", layout=shell, title="Server reactivity")
def reactivity_server_page() -> None:
    with ui.container(width="xl"), ui.vstack(gap="lg"):
        ui.heading("Server reactivity", level=1, size="3xl")
        with ui.hstack(align="baseline", gap="sm", wrap=True):
            ui.text(
                "Once a handler has changed state (see",
                color="muted", size="lg",
            )
            ui.link("Server actions", href="/actions-server")
            ui.text("), here is what renders again and how to control it.",
                    color="muted", size="lg")

        with ui.card(), ui.vstack(gap="sm"):
            ui.heading("Automatic re-rendering", level=2)
            ui.text(
                "A `@refreshable(deps=[…])` region declares the state it reads. "
                "When a handler changes one of those states, the region renders "
                "again automatically—no `refresh` call is needed.",
                color="muted", size="sm",
            )
            ui.code(
                "@refreshable(deps=[Cart])\n"
                "def cart_summary() -> None:\n"
                '    ui.text(f"{len(Cart().items)} items")\n'
                "\n"
                "\n"
                "def add_to_cart(product_id: str) -> None:\n"
                "    Cart().items.append(product_id)\n"
                "    # cart_summary renders again: Cart is in its deps\n",
                lang="python",
            )

        with ui.card(), ui.vstack(gap="sm"):
            ui.heading("Mutation = re-render", level=2)
            ui.text(
                "At the end of an action, the server compares state before and "
                "after—including in-place changes (`items.append(...)`, `d[k] = v`). "
                "Every region whose `deps=` changed renders again and is sent to the browser.",
                color="muted", size="sm",
            )
            ui.text(
                "Conversely, if a handler changes no state declared in `deps=`, no "
                "region renders again—the round trip has nothing to refresh.",
                color="muted", size="sm",
            )

        with ui.card(), ui.vstack(gap="sm"):
            ui.heading("Trigger manually — refresh()", level=2)
            ui.text(
                "`refresh(region)` forces a region to render again. Use it when a "
                "change does not come from declared state or from an action handler. "
                "You can also address a region by its `name`.",
                color="muted", size="sm",
            )
            ui.code(
                "from bretzel import refresh\n"
                "\n"
                "def reload_prices() -> None:\n"
                "    fetch_latest()\n"
                "    refresh(price_table)          # by region\n"
                '    # or: refresh("price_table")   # by name=\n',
                lang="python",
            )

        with ui.card(), ui.vstack(gap="sm"):
            ui.heading("Real time across clients — broadcast", level=2)
            ui.text(
                "`deps` and `broadcast` are independent lists. They answer the "
                "same question: who changes this state?",
                color="muted", size="sm",
            )
            with ui.vstack(gap="xs", classes="pl-4"):
                ui.text(
                    "• ME → `deps`. The region renders again in the action response: "
                    "one round trip, one swap.",
                    color="muted", size="sm",
                )
                ui.text(
                    "• OTHERS → `broadcast`. An SSE signal, then a refetch: two "
                    "round trips, but inactive tabs stay in sync.",
                    color="muted", size="sm",
                )
                ui.text(
                    "• BOTH → both lists. That is not redundant: immediate for me, "
                    "pushed to everyone else.",
                    color="muted", size="sm",
                )
            ui.code(
                "@refreshable(deps=[Cart])                     # local\n"
                "@refreshable(broadcast=[WaitingFile])         # I never\n"
                "                                              # change it\n"
                "@refreshable(deps=[Presence], broadcast=[Presence],\n"
                '             name="online_users")             # both\n',
                lang="python",
            )
            ui.text(
                "Only a signal crosses the wire: each client refetches in its own "
                "context and no data moves from one client to another. `name=` gives "
                "a stable address for `refresh(\"…\")`.",
                color="muted", size="xs",
            )

        with ui.card(color="surface"), ui.vstack(gap="xs"):
            ui.heading("Next", level=3)
            with ui.hstack(align="baseline", gap="sm", wrap=True):
                ui.text(
                    "Reactivity that lives in the browser, without a round trip:",
                    color="muted", size="sm",
                )
                ui.link("Client reactivity →", href="/reactivity-client")
