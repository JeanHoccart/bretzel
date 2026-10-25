"""REACTIVITY — Server reactivity.

The server side of reactivity: what re-renders after an action. A zone
declares the states it reads; mutating one of them re-renders it
automatically. Plus the manual trigger (`refresh`) and real time
(`broadcast=[…]` / SSE). API checked in
``render/decorators/refreshable.py`` (only ``refreshable`` and
``refresh`` are exported).
"""

from bretzel import page, ui
from examples.docs.features.shell import shell


@page("/reactivity-server", layout=shell, title="Server reactivity · Bretzel docs",
      description="Server reactivity in Bretzel: a @refreshable(deps=[...]) zone re-renders automatically when a handler mutates the state it reads.")
def reactivity_server_page() -> None:
    with ui.container(width="xl"), ui.vstack(gap="lg"):
        ui.heading('Server reactivity', level=1, size="3xl")
        with ui.hstack(align="baseline", gap="sm", wrap=True):
            ui.text(
                'Once a handler has changed the state (cf.',
                color="muted", size="lg",
            )
            ui.link("Server actions", href="/actions-server")
            ui.text('), here is what re-renders on screen, and how to '
                    'control it.', color="muted", size="lg")

        # ── @refreshable(deps=) ──────────────────────────────────
        with ui.card(), ui.vstack(gap="sm"):
            ui.heading('The automatic re-render', level=2)
            ui.text(
                'A `@refreshable(deps=[…])` zone declares the states it '
                'reads. When a handler mutates one of them, the zone is '
                're-rendered automatically — no refresh to call.',
                color="muted", size="sm",
            )
            ui.code(
                '@refreshable(deps=[Cart])\ndef cart_summary() -> None:\n    ui.text(f"{len(Cart().items)} items")\n\n\ndef add_to_cart(product_id: str) -> None:\n    Cart().items.append(product_id)\n    # cart_summary re-renders: Cart is in its deps\n',
                lang="python",
            )

        # ── Mutation = re-render ─────────────────────────────────
        with ui.card(), ui.vstack(gap="sm"):
            ui.heading("Mutation = re-render", level=2)
            ui.text(
                'At the end of an action, the server compares the state '
                'before and after — including in-place modifications '
                '(`items.append(...)`, `d[k] = v`). Every zone whose '
                '`deps=` changed is re-rendered and sent back to the '
                'browser.',
                color="muted", size="sm",
            )
            ui.text(
                'Conversely, if a handler changes no state declared in a '
                '`deps=`, no zone is re-rendered — the round trip brings '
                'back nothing to refresh.',
                color="muted", size="sm",
            )

        # ── refresh() ────────────────────────────────────────────
        with ui.card(), ui.vstack(gap="sm"):
            ui.heading('Triggering by hand — refresh()', level=2)
            ui.text(
                "`refresh(zone)` forces a zone's re-render. Useful when "
                'the change does not come from a declared state, or from '
                'somewhere that is not an action handler. It can also be '
                'addressed by its `name`.',
                color="muted", size="sm",
            )
            ui.code(
                'from bretzel import refresh\n\ndef reload_prices() -> None:\n    fetch_latest()\n    refresh(price_table)          # by the zone\n    # or: refresh("price_table")  # by its name=\n',
                lang="python",
            )

        # ── refresh(rows=) ───────────────────────────────────────
        with ui.card(), ui.vstack(gap="sm"):
            ui.heading('One row only — refresh(zone, rows=[…])', level=2)
            ui.text(
                'A re-rendered zone already sends only the elements that '
                'changed. When an action changes a few rows of a keyed '
                '`ui.table`, name them too: the zone then RENDERS only '
                'those rows, and the other tabs of a broadcast zone fetch '
                'only them.',
                color="muted", size="sm",
            )
            ui.code(
                '@refreshable(deps=[Filters], broadcast=[TableChanged])\n'
                'def tickets() -> None:\n'
                '    ui.table(columns=COLUMNS, rows=db.list_tickets(),\n'
                '             row_key="id")\n'
                '\n'
                'def set_status(ticket_id: int, status: str) -> None:\n'
                '    db.update(ticket_id, status=status)\n'
                '    refresh(tickets, rows=[ticket_id])\n',
                lang="python",
            )
            ui.text(
                'A row that enters, a new order, or a whole refresh in the '
                'same action: the zone is re-rendered whole, by itself. A '
                'row that left the list is removed.',
                color="muted", size="xs",
            )

        # ── broadcast ────────────────────────────────────────────
        with ui.card(), ui.vstack(gap="sm"):
            ui.heading('Realtime between clients — broadcast', level=2)
            ui.text(
                '`deps` and `broadcast` are two ORTHOGONAL lists, and the '
                'question they ask is the same: who changes this state?',
                color="muted", size="sm",
            )
            with ui.vstack(gap="xs", classes="pl-4"):
                ui.text(
                    '• ME → `deps`. The zone is re-rendered in the '
                    "action's response: one round trip, one swap.",
                    color="muted", size="sm",
                )
                ui.text(
                    '• THE OTHERS → `broadcast`. An SSE signal, then a '
                    'refetch: two round trips, but the tab that did '
                    'nothing follows.',
                    color="muted", size="sm",
                )
                ui.text(
                    '• BOTH → both lists. It is not a redundancy: it says '
                    '“instant for me, pushed to the others”.',
                    color="muted", size="sm",
                )
            ui.code(
                '@refreshable(deps=[Cart])                     # local\n@refreshable(broadcast=[Queue])               # I never\n                                              # change it\n@refreshable(deps=[Presence], broadcast=[Presence],\n             name="online_users")             # both\n',
                lang="python",
            )
            ui.text(
                'What crosses is only a SIGNAL: every client refetches in '
                'its own context, no data passes from one client to '
                'another. `name=` gives a stable address for '
                '`refresh("…")`.',
                color="muted", size="xs",
            )

        # ── Boundary ─────────────────────────────────────────────
        with ui.card(color="surface"), ui.vstack(gap="xs"):
            ui.heading("What next", level=3)
            with ui.hstack(align="baseline", gap="sm", wrap=True):
                ui.text(
                    'The reactivity that lives in the browser, with no '
                    'round trip:',
                    color="muted", size="sm",
                )
                ui.link('Client reactivity →', href="/reactivity-client")
