"""STATE — Client state.

The client side of state: it lives in the browser, mirrored by the
runtime, with no round trip. Useful for pure UI (filters, display
preferences) that does not need the server. `persist=` decides survival.
Modes checked in ``state/scopes/client.py``.
"""

from __future__ import annotations

from bretzel import page, ui
from bretzel.render import serialize_html
from bretzel.state import ClientState, field
from examples.docs.features.shell import shell
from examples.docs.lib.blocks import emitted_html_block, state_mirror

PATH = "/state-client"


class EchoClient(ClientState, persist="local"):
    """Browser state — mirrored by the runtime, zero round trips."""

    text: str = field(default='')


def echo_demo() -> None:
    echo = EchoClient()
    with ui.vstack(gap="sm"):
        ui.input(value=echo.text, placeholder="Type here…")
        with ui.hstack(align="center", gap="sm"):
            ui.text("Live echo:", color="muted", size="sm")
            ui.text(echo.text, weight="bold", classes="font-mono")


@page(PATH, layout=shell, title="Client state · Bretzel docs",
      description="Client state in Bretzel: typed state that lives in the browser for pure UI such as open panels, filters and preferences.")
def state_client_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading('Client state', level=1, size="3xl")
            ui.text(
                'A client state lives in the browser — the runtime '
                'reflects it, without ever touching the server. It is the '
                'right choice for pure UI: a panel open or closed, a '
                'display filter, a local preference.',
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Declaring, and persistence', level=2)
                    ui.text(
                        'One inherits from `ClientState`. `persist=` '
                        'decides one thing only: how long the value '
                        'survives.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        "class FilterUI(ClientState, persist=\"local\"):\n"
                        "    sort_by: str = \"date\"\n",
                        lang="python",
                    )
                    ui.table(
                        columns=[
                            ui.column("persist", label="persist="),
                            ui.column("survie", label="Survives"),
                            ui.column('for', label='What for'),
                        ],
                        rows=[
                            {"persist": '"memory" (default)',
                             "survie": 'throwaway — lost on reload (F5) '
                                       'and on close',
                             'for': 'a UI flag (menu open)'},
                            {"persist": "\"session\"",
                             "survie": 'survives a reload, lost on close',
                             'for': 'a filter, a wizard step'},
                            {"persist": "\"local\"",
                             "survie": 'survives everything; another open '
                                       'tab sees it on its next load',
                             'for': 'a real preference (theme, sort)'},
                        ],
                        size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Demo — the client mirror, zero round trips',
                               level=2)
                    ui.text(
                        'The input writes into a ClientState; the text '
                        'below reflects it through `bz-text`. No network —'
                        ' the runtime swaps the text on every keystroke.',
                        color="muted", size="sm",
                    )
                    echo_demo()
                    emitted_html_block(
                        'The `<span bz-text>` bound to '
                        '$bz.state.EchoClient.default.text',
                        serialize_html(
                            ui.text(EchoClient().text, weight="bold",
                                    classes="font-mono")
                        ),
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading('Summary', level=2)
                    with ui.card():
                        state_mirror(EchoClient)
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text('Driving that state from an event:',
                                color="muted", size="sm")
                        ui.link("Client actions →", href="/actions-client")
                        ui.text('· the live reflection in detail:',
                                color="muted", size="sm")
                        ui.link('Client reactivity →', href="/reactivity-client")
