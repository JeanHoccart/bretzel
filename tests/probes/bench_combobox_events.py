"""Bench : Combobox change handler refreshing its OWN panel (:8973).

Mirror of bench_select_events — Combobox shares Select's
``_change_emit_effect`` + ``_serverSync`` wiring, so it had the same
double-event + value-loss bug for an unbound ``on_change`` combobox
inside a ``@refreshable``.

Run :  py tests/probes/bench_combobox_events.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, refresh, refreshable, ui
from bretzel.state import PageState, field

app = Bretzel(
    secret_key="dev-combobox-events-bench-secret-key",
    title="Bretzel · Combobox events bench",
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
        ui.combobox(FRUITS, placeholder="change handler",
                    on_change=log_change, id="cb")

        with ui.vstack(gap="xs", id="evlog"):
            for i, evt in enumerate(reversed(s.log[-10:]), 1):
                ui.text(f"{i}. {evt}", size="sm", classes="font-mono evt")


@page("/")
def home() -> None:
    with ui.vstack(gap="lg", align="start", classes="p-8 w-96"):
        ui.text("Combobox events bench", size="2xl", weight="bold")
        panel()


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8973))
