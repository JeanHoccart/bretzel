"""Bench reproducing the user's switch-bound-to-server-var bug (8959).

Three cases, all toggled OFF by the probe :

1. ``server-switch``   — Switch bound to a PageState bool, autoname
   (no explicit ``name=``), ``on_change`` server handler + refresh.
   This is the reported bug : an unchecked checkbox submits nothing,
   so ``false`` never reaches the server and the refresh snaps it back
   on. Fixed by ``force_boolean_form_vals`` (hx-vals js).
2. ``server-checkbox`` — same, but a Checkbox (shares the helper).
3. ``client-switch``   — Switch bound to a ClientState bool. The bridge
   already ships the client store (false included), so NO hx-vals is
   added ; this guards against a regression there.

Run :  py tests/probes/bench_switch_server.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, refresh, refreshable, ui
from bretzel.state import ClientState, PageState, field

app = Bretzel(
    secret_key="dev-switch-server-bench-secret-key",
    title="Bretzel · Switch server bench",
    mode="dev",
)


class Flags(PageState):
    enabled: bool = field(default=False)
    accepted: bool = field(default=False)


class ClientFlags(ClientState, persist="memory"):
    live: bool = field(default=False)


def on_toggle(**kwargs) -> None:
    # Naive user pattern : copy whatever the form delivered onto state.
    state = Flags()
    for key, value in kwargs.items():
        if hasattr(state, key):
            setattr(state, key, value)
    refresh(panel)


@refreshable
def panel() -> None:
    state = Flags()
    with ui.vstack(gap="md", align="start"):
        # 1. server-bound Switch, autoname.
        ui.switch(
            checked=state.enabled, label="Enabled (server switch)",
            on_change=on_toggle, id="server-switch",
        )
        ui.text(f"server: enabled = {state.enabled}", id="readout-switch")

        # 2. server-bound Checkbox, autoname.
        ui.checkbox(
            checked=state.accepted, label="Accepted (server checkbox)",
            on_change=on_toggle, id="server-checkbox",
        )
        ui.text(f"server: accepted = {state.accepted}", id="readout-checkbox")


@page("/")
def home() -> None:
    client = ClientFlags()
    with ui.vstack(gap="xl", align="start", classes="p-8"):
        ui.text("Switch ↔ server var bench", size="2xl", weight="bold")
        panel()

        # 3. client-bound Switch — non-regression. Bound text mirrors it.
        ui.divider()
        ui.switch(
            checked=client.live, label="Live (client switch)",
            id="client-switch",
        )
        ui.text(client.live, id="readout-client")


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8959))
