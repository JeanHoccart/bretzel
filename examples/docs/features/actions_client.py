"""ACTIONS — Client actions (no round trip).

The client side of actions: what runs in the browser, without touching
the server. `on_<event>=` accepts a client expression (a string); it is
rarely written by hand — methods generate it. Three ways, one single
mechanism. Imperative contract checked: imperative-api.md + dialog.py;
the string path: button.py (str → bz-on:click).
"""

from bretzel import page, ui

from examples.docs.features.shell import shell


@page("/actions-client", layout=shell, title="Client actions · Bretzel docs",
      description="Client actions in Bretzel: run a purely visual interaction in the browser with a client expression on on_<event>=, with no server round trip.")
def actions_client_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Client actions", level=1, size="3xl")
            with ui.hstack(align="baseline", gap="sm", wrap=True):
                ui.text(
                    'For a purely visual interaction, one stays in the '
                    'browser — no round trip (cf.',
                    color="muted", size="lg",
                )
                ui.link("How Bretzel works", href="/how")
                ui.text('). `on_<event>=` then accepts a client expression.',
                        color="muted", size="lg")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Three ways, a single mechanism', level=2)
                    ui.text(
                        'All produce the same thing: an expression '
                        'evaluated client side, with no request. The first'
                        ' two write it for you; the third one is you.',
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("faux", label='Way'),
                            ui.column("quand", label="When"),
                        ],
                        rows=[
                            {"faux": '1. Imperative methods (.open / '
                                     '.close / .toggle)',
                             "quand": 'driving a component, with no state '
                                      'to declare'},
                            {"faux": '2. Binding methods (.set / .toggle /'
                                     ' .clear …)',
                             "quand": 'a client state that is readable / '
                                      'shareable / persistable'},
                            {"faux": '3. Raw string (on_click="…")',
                             "quand": 'the escape hatch: an expression by '
                                      'hand'},
                        ],
                        size="sm",
                    )

            # ── 1. Imperative ────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('1. Imperative methods', level=2)
                    ui.text(
                        'Write-only: they return the client string, to be '
                        'given to `on_click=`. Overlays: `.open()` '
                        '`.close()` `.toggle()`. Value-carrying fields: '
                        '`.set(v)` `.clear()`. Some components add '
                        'semantic aliases — for example '
                        '`.expand()/.collapse()` on the accordion.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        '# container: with … as\nwith ui.dialog() as confirm:\n    ui.text("Delete this item?")\n    ui.button("OK", on_click=delete)\n\nui.button("Delete", on_click=confirm.open())\n\n# simple: direct assignment\naccept = ui.checkbox()\nui.button("Accept all", on_click=accept.set(True))\n',
                        lang="python",
                    )
                    ui.text(
                        'Ideal for repetitive overlays (one confirmation '
                        'dialog per row): the instance drives itself, with'
                        ' no state to declare. No reading (`.value`, '
                        '`.is_open`) — to read, go through a binding.',
                        color="muted", size="sm",
                    )

            # ── 2. Binding ───────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('2. Binding methods', level=2)
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text(
                            'When client state has to be readable, shared '
                            'or persistent, one declares it (a '
                            'ClientState) and drives it through its '
                            'binding. The methods are the same return '
                            'shapes. Detail in',
                            color="muted", size="sm",
                        )
                        ui.link('Client state', href="/state-client")
                        ui.text(".", color="muted", size="sm")
                    ui.code(
                        'class PanelUI(ClientState):\n    open: bool = field(default=False)\n\npanel = PanelUI()\nui.button("Show", on_click=panel.open.toggle())\nwith ui.card(visible=panel.open):\n    ui.text("Zero round trips.")\n',
                        lang="python",
                    )

            # ── 3. Porte de sortie ───────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('3. Escape hatch — a raw string', level=2)
                    ui.text(
                        'Passing a string to `on_<event>=` emits it as a '
                        'client expression evaluated in the browser (`bz-'
                        'on:click`). It is the escape hatch for the rare '
                        'case where no shorthand fits — to be kept, '
                        'precisely, for the rare cases.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        'ui.button("Back to top", on_click="window.scrollTo(0, 0)")\n',
                        lang="python",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="xs"):
                    ui.heading('To remember', level=3)
                    ui.text(
                        'Client side = no round trip. A shorthand when one'
                        ' exists, a binding when the state has to be read,'
                        ' the string as a last resort. As soon as the '
                        'truth changes, one goes back to the server '
                        '(Handlers & actions).',
                        color="muted", size="sm",
                    )
