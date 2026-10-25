"""ACTIONS — Server actions.

The server side of actions: wiring a handler onto an event, what may be
passed to it, passing arguments, reading the form. Facts checked in
``server/handlers.py`` + ``server/routing/actions.py``.
"""

from bretzel import page, ui

from examples.docs.features.shell import shell


@page("/actions-server", layout=shell, title="Server actions · Bretzel docs",
      description="Server actions in Bretzel: pass a Python handler to on_<event>= and mutate the typed state on the server in one signed round trip.")
def actions_server_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Server actions", level=1, size="3xl")
            ui.text(
                'The server side of actions: when an interaction changes '
                'the truth, `on_<event>=` receives a Python function — a '
                'handler. One round trip, and the truth mutates server '
                'side.',
                color="muted", size="lg",
            )

            # ── Brancher ─────────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Wiring a handler', level=2)
                    ui.text(
                        'Every interactive component exposes events '
                        '(`click`, `change`, `input`, `focus`, `blur`, '
                        '`submit`, …). One wires a function with '
                        '`on_<event>=`.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        "def save() -> None:\n"
                        "    ...\n"
                        "\n"
                        'ui.button("Save", on_click=save)\n',
                        lang="python",
                    )

            # ── What may be passed ───────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('What can be passed to on_<event>=', level=2)
                    ui.text(
                        'The handler is found again by its import path '
                        '(`module::function`), with no per-page table '
                        'stored. So it must be addressable.',
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("forme", label="Form"),
                            ui.column("ok", label='Accepted?'),
                        ],
                        rows=[
                            {"forme": "Module-level function "
                                      "(on_click=save)", "ok": "Yes"},
                            {"forme": "@staticmethod / @classmethod",
                             "ok": "Yes"},
                            {"forme": "functools.partial(handler, arg)",
                             "ok": 'Yes — to pass an argument'},
                            {"forme": "Lambda (on_click=lambda: …)",
                             "ok": "No — error at render"},
                            {"forme": 'A closure (a function defined '
                                      'inside a function)', "ok": "No — error at render"},
                            {"forme": 'Instance method',
                             "ok": "No — not addressable"},
                        ],
                        size="sm",
                    )
                    ui.text(
                        'A lambda or a closure has no stable import path, '
                        'hence the refusal at render time.',
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text(
                            'This is the server route (a function). '
                            '`on_<event>=` also accepts a string, '
                            'evaluated client side with no handler — cf.',
                            color="muted", size="sm",
                        )
                        ui.link("Client actions", href="/actions-client")
                        ui.text(".", color="muted", size="sm")

            # ── Passer un argument ───────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Passing an argument — functools.partial', level=2)
                    ui.text(
                        'To give the handler an argument (typically a '
                        "row's id), one uses `partial`. The arguments "
                        'travel with the request.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        'from functools import partial\n\ndef delete_item(item_id: str) -> None:\n    ...\n\n# one row per item, each with its own id:\nui.icon_button("trash-2",\n               on_click=partial(delete_item, item_id))\n',
                        lang="python",
                    )
                    ui.text(
                        'The arguments must be JSON-serialisable: str, '
                        'int, float, bool, None, list, dict.',
                        color="muted", size="sm",
                    )

            # ── Reading the form data ───────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Reading the form's data", level=2)
                    ui.text(
                        'Three ways, depending on the need:',
                        color="muted", size="sm",
                    )
                    ui.code(
                        'from bretzel.state import get\n\n# 1. a parameter named like a field → forwarded\ndef submit(title: str) -> None:\n    ...\n\n# 2. a State-typed parameter → hydrated from the form\ndef save(form: Draft) -> None:\n    # form.title, form.price … already filled + validated\n    ...\n\n# 3. get() → one raw field, occasionally\ndef other() -> None:\n    note = get("note")\n',
                        lang="python",
                    )
                    ui.text(
                        'No `name=` to write by hand: '
                        '`ui.input(value=draft.title)` derives the `title`'
                        ' field automatically (cf. the Components '
                        'chapter).',
                        color="muted", size="sm",
                    )

            # ── Busy state ──────────────────────────────────────────
            with ui.card(), ui.vstack(gap="sm"):
                ui.heading('Showing that an action is running', level=2)
                ui.text(
                    'Nothing to write: a control whose action is still '
                    'unanswered after 200 ms shows it — a spinner in a '
                    'button (its width stays), at the end of a field, a '
                    'pulse on a checkbox, a dimmed link or zone. A '
                    'faster answer shows nothing.',
                    color="muted", size="sm",
                )
                ui.code(
                    'ui.button("Save", on_click=save)        # by itself\n'
                    'ui.button("Ping", on_click=ping,\n'
                    '          loading=False)                # never\n'
                    'with ui.hstack(loading=False):          # nor inside\n'
                    '    ...\n'
                    '\n'
                    '# your own indicator, e.g. a skeleton in a panel:\n'
                    'ui.skeleton(visible=ui.pending(load_report))\n',
                    lang="python",
                )

            # ── @idempotent ──────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Avoiding double submits — @idempotent',
                               level=2)
                    ui.text(
                        'On a sensitive action (payment, creation), '
                        '`@idempotent` makes a double send of the same '
                        'render run only once; the second receives a 204.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        "from bretzel import idempotent\n"
                        "\n"
                        "@idempotent\n"
                        "def charge_card() -> None:\n"
                        "    ...\n",
                        lang="python",
                    )

            # ── Boundary ────────────────────────────────────────────
            with ui.card(color="surface"):
                with ui.vstack(gap="xs"):
                    ui.heading("What next", level=3)
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text('What re-renders after the handler:',
                                color="muted", size="sm")
                        ui.link('Server reactivity →', href="/reactivity-server")
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text('Acting with no round trip:',
                                color="muted", size="sm")
                        ui.link("Client actions →", href="/actions-client")
