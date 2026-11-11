"""TOPIC — Keeping a page alive without anybody clicking.

``ui.interval`` is an INVISIBLE component: it draws nothing, it fires. An
`on_tick` every N seconds, and a flag that stops it.

What is worth writing down, because it is the design choice: the cadence
lives in the PAGE, not in a server task. A closed tab stops ticking on
its own — there is nothing to cancel, no life cycle to hold, and an app
that restarts leaves no orphan timer.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell

PATH = "/cadence"


@page(PATH, layout=shell, title="The cadence · Bretzel docs",
      description="Keep a Bretzel page alive with no click: periodic refresh, countdowns and task polling with one invisible component.")
def cadence_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading('Keeping a page alive without anybody clicking',
                       level=1, size="3xl")
            ui.text(
                'A dashboard that refreshes, a counter going down, polling'
                ' a running task. An invisible component is enough.',
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Three parameters, and that is all', level=2)
                    ui.table(
                        columns=[
                            ui.column("p", label='Parameter'),
                            ui.column("q", label="What it does"),
                        ],
                        rows=[
                            {"p": "on_tick",
                             "q": 'what fires — a server handler, or a '
                                  'string evaluated in place'},
                            {"p": "seconds",
                             "q": 'the interval, in seconds (1.0 by '
                                  'default)'},
                            {"p": "active",
                             "q": 'a boolean OR a `ClientBinding` — that '
                                  'is what makes the cadence stoppable'},
                        ],
                        size="sm",
                    )
                    ui.code(
                        '# Server: the zone re-renders every 5 s.\n@refreshable\ndef board() -> None:\n    ui.text(f"{Metrics().running} running")\n\ndef sample() -> None:\n    Metrics().running = count()\n\nboard()\nui.interval(on_tick=sample, seconds=5)\n',
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Stopping it — with no task to cancel', level=2)
                    ui.text(
                        '`active=` accepts a `ClientBinding`. A switch '
                        'writes into the client state, the interval reads '
                        'it, and the cadence stops — with no round trip, '
                        'and with no server lifecycle needing to exist.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        'class Monitoring(ClientState):\n    running: bool = field(default=True)\n\nm = Monitoring()\nui.switch(value=m.running, label="Refresh")\nui.interval(on_tick=sample, seconds=5,\n            disabled=~m.running)\n',
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Without touching the server', level=2)
                    ui.text(
                        '`on_tick=` is polymorphic, like every `on_*`: a '
                        'callable leaves as a signed POST, a STRING is '
                        'evaluated in place. So a countdown needs no '
                        'request at all.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        "class Countdown(ClientState):\n"
                        "    left: int = field(default=60)\n"
                        "\n"
                        "c = Countdown()\n"
                        "ui.text(c.left)\n"
                        "ui.interval(on_tick=c.left.decrement(1),\n"
                        "            seconds=1, disabled=c.left <= 0)\n",
                        lang="python",
                    )
                    ui.text(
                        '`disabled=c.left <= 0` is an expression of the '
                        'client algebra: it becomes JavaScript, re-'
                        'evaluated on every change. So the timer stops by '
                        'itself at zero.',
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("What to know before using it",
                               level=2)
                    ui.alert(
                        'The cadence lives in the PAGE. A closed tab stops'
                        ' running — which is exactly what one wants for a '
                        'screen refresh, and exactly what one does not '
                        'want for work that must finish. For that, it is '
                        '`@background` — it survives the response, hence '
                        "the visitor's departure.",
                        color="warning",
                        title='This is NOT a background task',
                    )
                    ui.alert(
                        'Every tick of a server `on_tick=` is a request. A'
                        ' one-second interval across fifty open tabs makes'
                        ' fifty requests a second. When the data comes '
                        'from the server and changes rarely, a '
                        '`@refreshable` zone reading it costs less: it is '
                        'the server that pushes, when it has something to '
                        'say.',
                        color="warning", title='The cost, in requests',
                    )

            with ui.card(color="surface"):
                with ui.hstack(gap="sm", wrap=True, align="baseline"):
                    ui.text('The zone that re-renders, and realtime:',
                            color="muted", size="sm")
                    ui.link('Server reactivity →',
                            href="/reactivity-server")
                    ui.link('Client reactivity →',
                            href="/reactivity-client")
