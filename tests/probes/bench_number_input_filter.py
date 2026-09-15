"""Bench — number_input keystroke filter + clean on_change (port 8994).

Reproduces the user's report : letters typed into ``ui.number_input``
showed up in the field, and the ``on_change`` (pushing
``$event.target.value`` onto a ClientState log — same wiring as the
playground "Client events" card) logged the dirty raw text ``"4102aaaa"``
instead of the committed numeric value.

Run :  py tests/probes/bench_number_input_filter.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import ClientExpression

app = Bretzel(
    secret_key="dev-number-input-filter-bench-key",
    title="Bretzel · number_input filter bench",
    mode="dev",
)


class Log(ClientState, persist="memory"):
    log: list = field(default_factory=list)


@page("/")
def home() -> None:
    ev = Log()
    new_value = ClientExpression("$event.target.value")
    with ui.vstack(gap="lg", align="start", classes="p-8"):
        ui.text("number_input filter bench", size="2xl", weight="bold")
        ui.number_input(
            value=42,
            step=0.01,  # decimals survive the snap-to-step on commit
            on_change=ev.log.push(new_value),
            id="ni",
        )
        log_text = ClientExpression(
            '($bz.state.Log.default.log || []).join(" | ") '
            '|| "(no events yet)"'
        )
        ui.text(log_text, color="muted", size="sm",
                classes="font-mono", id="log")
        count_text = ClientExpression(
            'String(($bz.state.Log.default.log || []).length)'
        )
        ui.text(count_text, id="count", classes="font-mono")


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8994))
