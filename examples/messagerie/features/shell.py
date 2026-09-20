"""messagerie/shell — the frozen frame, the search, and **no sidebar**.

Writing ``ui.viewport()`` is choosing a scrolling model. Bretzel keeps
the web's by default — the document scrolls under a fixed chrome — and
this is the other one: the document NEVER moves, the regions scroll, each
its own. It is the tools' model (VS Code, Slack), and a mail client is
exactly that case: the message list scrolls without taking the folder
column along, and a long message's body scrolls without taking the list
along.

The price is a continuous chain of heights from the root to the region,
hence the ``flex-1 min-h-0`` on the outlet: ``ui.outlet`` renders a block
``<main>`` with no height, inheriting no constraint (cf.
``examples/chat``'s shell, which carries the measurement).

**No ``ui.sidebar``, and that is deliberate.** Almost every other demo in
the repository has one; here the folder column IS the navigation. A
sidebar on top would make two levels of menu for an app with one page.
"""

from __future__ import annotations

from bretzel import layout, ui
from bretzel.theme import ColorScheme
from examples.messagerie.features.state import Filter


@layout
def shell() -> None:
    with ui.viewport(direction="col"):
        with ui.hstack(
            align="center",
            gap="md",
            classes="px-4 py-2.5 border-b border-text/10 shrink-0",
        ):
            with ui.hstack(align="center", gap="sm", classes="w-52 shrink-0"):
                ui.icon("mail", color="primary", size="lg")
                ui.heading("Mail", level=1, size="md")

            # No ``on_input``, no ``debounce``, no zone to re-render:
            # ``Filter`` is a ``ClientState``, and the list iterates with
            # ``ui.filter_each``. Typing filters IN the browser, without
            # a single request. The previous version POSTed at every
            # debounced keystroke — it worked, but it rewrote a framework
            # primitive by hand.
            ui.input(
                value=Filter().q,
                placeholder="Search the messages",
                icon_left="search",
                size="sm",
                clearable=True,
                classes="flex-1 max-w-2xl",
            )

            with ui.hstack(align="center", gap="xs", classes="shrink-0"):
                # ⚠️ No "clear" button here. `clearable=True` on the
                # input already places one, CLIENT SIDE. A second, gated
                # on `visible=Filter().q != ""`, would have been stillborn:
                # `Filter` is a SERVER state, so the expression is a
                # Python boolean evaluated once when the shell renders —
                # and the shell is not a refreshable zone. It would never
                # have appeared nor disappeared.
                #
                # The light/dark toggle. Two buttons and not one:
                # Tailwind's ``dark:`` variants always hide one, so the
                # visible icon is the destination's. ``ColorScheme``
                # belongs to the framework — the app never instantiates
                # it, it calls its class helpers.
                ui.icon_button(
                    "moon", variant="ghost", size="sm",
                    on_click=ColorScheme.toggle(), tooltip="Switch to dark",
                    classes="dark:!hidden",
                )
                ui.icon_button(
                    "sun", variant="ghost", size="sm",
                    on_click=ColorScheme.toggle(), tooltip="Switch to light",
                    classes="!hidden dark:!inline-flex",
                )

        ui.outlet(classes="flex-1 min-h-0 flex")
