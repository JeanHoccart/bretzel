"""Bench : Select change handler that refreshes its OWN panel (:8972).

Reproduces the user report — an UNBOUND ``ui.select(opts, on_change=fn)``
sitting inside a ``@refreshable`` whose handler refreshes that same
panel. Symptom : picking an option logs a DOUBLE change event and the
trigger loses its value (resets to the placeholder).

The live log is rendered into ``#evlog`` (one ``<li>`` per event, newest
first) so the probe can count events + read their serialised value.

Run :  py tests/probes/bench_select_events.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, refresh, refreshable, ui
from bretzel.state import PageState, field

app = Bretzel(
    secret_key="dev-select-events-bench-secret-key",
    title="Bretzel · Select events bench",
    mode="dev",
)

FRUITS = ["apple", "banana", "cherry"]


class Ev(PageState):
    log: list = field(default_factory=list)


def log_change(value: str = "") -> None:
    s = Ev()
    s.log = [*s.log, f"change(value={value!r})"]
    refresh(panel)


@refreshable
def panel() -> None:
    s = Ev()
    with ui.vstack(gap="md", align="start"):
        ui.select(FRUITS, placeholder="change handler",
                  on_change=log_change, id="se")

        # Newest first, like the playground.
        with ui.vstack(gap="xs", id="evlog"):
            for i, evt in enumerate(reversed(s.log[-10:]), 1):
                ui.text(f"{i}. {evt}", size="sm", classes="font-mono evt")


@page("/")
def home() -> None:
    with ui.vstack(gap="lg", align="start", classes="p-8 w-96"):
        ui.text("Select events bench", size="2xl", weight="bold")
        panel()


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8972))
