"""Bench reproducing the "Client events" demo bug (port 8961).

Mirrors ``examples/playground/features/button/ui.py`` § Client events :
buttons whose ``on_*`` wire a client expression ``state.log.push(evt)``
onto a ClientState list, with a bound log text. The bug : ``.push()``
mutated the array IN PLACE, and V3 signals are identity-compared, so the
signal never fired and the log stayed "(no events yet)". Fixed by making
``ClientBinding.push`` reassign with a fresh array.

Run :  py tests/probes/bench_clientevent.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import ClientExpression

app = Bretzel(
    secret_key="dev-clientevent-bench-secret-key",
    title="Bretzel · Client events bench",
    mode="dev",
)


class Events(ClientState, persist="memory"):
    log: list = field(default_factory=list)


@page("/")
def home() -> None:
    ev = Events()
    with ui.vstack(gap="lg", align="start", classes="p-8"):
        ui.text("Client events bench", size="2xl", weight="bold")
        with ui.hstack(gap="md", wrap=True):
            ui.button("click", variant="outline",
                      on_click=ev.log.push("click"), id="btn-click")
            ui.button("enter", variant="outline",
                      on_mouseenter=ev.log.push("enter"), id="btn-enter")
            ui.button("Clear", variant="ghost",
                      on_click=ev.log.clear(), id="btn-clear")
        log_text = ClientExpression(
            '($bz.state.Events.default.log || [])'
            '.join(", ") || "(no events yet)"'
        )
        ui.text(log_text, color="muted", size="sm",
                classes="font-mono", id="log")


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8961))
