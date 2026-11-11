"""REACTIVITY — Server reactivity.

The server side of reactivity: what re-renders after an action. A zone
follows the states it reads; mutating one of them re-renders it
automatically, in every tab showing it. Plus the manual trigger
(`refresh`). API checked in
``render/decorators/refreshable.py`` (only ``refreshable`` and
``refresh`` are exported).
"""

from bretzel import page, ui
from examples.docs.features.shell import shell


@page("/reactivity-server", layout=shell, title="Server reactivity · Bretzel docs",
      description="Server reactivity in Bretzel: a @refreshable zone re-renders automatically when a handler mutates the state it reads.")
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

        # ── @refreshable ──────────────────────────────────
        with ui.card(), ui.vstack(gap="sm"):
            ui.heading('The automatic re-render', level=2)
            ui.text(
                'A `@refreshable` zone follows the states it reads: '
                'every `MyState()` it obtains while rendering is '
                'recorded. When a handler mutates one of them, the zone '
                'is re-rendered automatically — no list to write, no '
                'refresh to call.',
                color="muted", size="sm",
            )
            ui.code(
                '@refreshable\ndef cart_summary() -> None:\n    ui.text(f"{len(Cart().items)} items")\n\n\ndef add_to_cart(product_id: str) -> None:\n    Cart().items.append(product_id)\n    # cart_summary re-renders: it read Cart\n',
                lang="python",
            )

        # ── Mutation = re-render ─────────────────────────────────
        with ui.card(), ui.vstack(gap="sm"):
            ui.heading("Mutation = re-render", level=2)
            ui.text(
                'At the end of an action, the server compares the state '
                'before and after — including in-place modifications '
                '(`items.append(...)`, `d[k] = v`). Every zone that read '
                'a changed state is re-rendered and sent back to the '
                'browser.',
                color="muted", size="sm",
            )
            ui.text(
                'Conversely, if a handler changes no state that a zone '
                'read, no zone is re-rendered — the round trip brings '
                'back nothing to refresh.',
                color="muted", size="sm",
            )

        # ── Topic ────────────────────────────────────────────────
        with ui.card(), ui.vstack(gap="sm"):
            ui.heading('What is not a state — Topic', level=2)
            ui.text(
                'A database write touches no state, so no zone notices it. '
                'Declare a `Topic` and attach the functions that touch the '
                'data: every zone calling a `@reads` function redraws once '
                'a `@writes` function has returned without an error. '
                'Bretzel never looks at the storage, so a database, a file '
                'or an API all work. `refresh(topic)` redraws them when '
                'nothing was written. Outside a zone, `@reads` does nothing.',
                color="muted", size="sm",
            )
            ui.code(
                'from bretzel.state import Topic, reads, writes\n\n'
                'CONTACTS = Topic("contacts")\n\n\n'
                '@reads(CONTACTS)\n'
                'def search_contacts(needle: str) -> list[dict]:\n'
                '    return query("SELECT ...")\n\n\n'
                '@writes(CONTACTS)\n'
                'def rename(contact_id: int, name: str) -> None:\n'
                '    execute("UPDATE ...")\n',
                lang="python",
            )
        # ── refresh() ────────────────────────────────────────────
        with ui.card(), ui.vstack(gap="sm"):
            ui.heading('Triggering by hand — refresh()', level=2)
            ui.text(
                "`refresh(zone)` forces a zone's re-render. Useful when "
                'the change does not come from a state the zone reads, or from '
                'somewhere that is not an action handler. It can also be '
                'addressed by its `name`.',
                color="muted", size="sm",
            )
            ui.code(
                'from bretzel import refresh\n\ndef reload_prices() -> None:\n    fetch_latest()\n    refresh(price_table)          # by the zone\n',
                lang="python",
            )

        # ── Other tabs ───────────────────────────────────────────
        with ui.card(), ui.vstack(gap="sm"):
            ui.heading('Realtime between tabs', level=2)
            ui.text(
                'A zone is redrawn in every open tab showing it, as far as '
                'the scope of what it read allows. Nothing to declare.',
                color="muted", size="sm",
            )
            with ui.vstack(gap="xs", classes="pl-4"):
                ui.text(
                    '• `PageState` → this tab only, in the action\'s '
                    'response: one round trip, one swap.',
                    color="muted", size="sm",
                )
                ui.text(
                    '• `SessionState` → the other tabs of this session; '
                    '`UserState` → the other tabs of this user.',
                    color="muted", size="sm",
                )
                ui.text(
                    '• `AppState` and `Topic` → every tab. An SSE signal, '
                    'then a refetch: two round trips, but the tab that did '
                    'nothing follows.',
                    color="muted", size="sm",
                )
            ui.code(
                'class Queue(AppState):\n    people: list[str] = field(default_factory=list)\n\n@refreshable\ndef waiting_room() -> None:      # every tab showing it follows\n    for name in Queue().people:\n        ui.text(name)\n',
                lang="python",
            )
            ui.text(
                'What crosses is only a SIGNAL: every client refetches in '
                'its own context, no data passes from one client to '
                'another.',
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
