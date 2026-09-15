"""Bench : Switch + RadioGroup server-event bugs (:8972).

Two reports :
 1. Switch — a LOCAL (unbound) switch with ``on_change`` that refreshes a
    panel snaps back to ``false`` after firing (the refresh re-renders it
    unchecked and idiomorph clobbers the live ``.checked``).
 2. RadioGroup — a bound group's ``on_change`` logs ``value=''`` : the
    picked option never reaches the handler as a plain form field.

Each handler records what it RECEIVED into a module list, exposed at
``/calls`` so the probe reads ground truth (no guessing).

Run :  py tests/probes/bench_server_events.py
"""

from __future__ import annotations

import json

from bretzel import Bretzel, page, refresh, refreshable, ui
from bretzel.state import ClientState, PageState, field

app = Bretzel(
    secret_key="dev-server-events-bench-secret-key",
    title="Bretzel · server events bench",
    mode="dev",
)

# Module-level record of every handler invocation : (which, kwargs).
CALLS: list[dict] = []


class SwitchLog(PageState):
    log: list = field(default_factory=list)


class RadioBound(ClientState, persist="memory"):
    value: str = field(default="a")


def switch_change(**kwargs) -> None:
    CALLS.append({"which": "switch_change", "kwargs": _safe(kwargs)})
    s = SwitchLog()
    s.log = [*s.log, f"change({_safe(kwargs)})"]
    refresh(switch_panel)


def radio_change(**form) -> None:
    CALLS.append({"which": "radio_change", "form": _safe(form)})
    picked = next((v for v in form.values() if v), "")
    s = SwitchLog()
    s.log = [*s.log, f"radio({picked!r})"]
    refresh(switch_panel)


def family_change(**kwargs) -> None:
    # Any of checkbox / input / textarea fired → refresh the panel. The
    # local value must survive the morph (the whole point).
    CALLS.append({"which": "family_change", "kwargs": _safe(kwargs)})
    s = SwitchLog()
    s.log = [*s.log, "family"]
    refresh(switch_panel)


def _safe(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        try:
            json.dumps(v)
            out[k] = v
        except TypeError:
            out[k] = str(v)
    return out


@refreshable
def switch_panel() -> None:
    s = SwitchLog()
    with ui.vstack(gap="sm", align="start"):
        ui.text(f"log entries: {len(s.log)}", id="logcount")
        # 1. Local switch — no binding ; on_change refreshes THIS panel.
        ui.switch(label="local change", on_change=switch_change,
                  id="sw-local")
        # 2. Bound radio group — on_change should log the picked value.
        rb = RadioBound()
        with ui.radio_group(value=rb.value, on_change=radio_change,
                            id="rg-bound"):
            ui.radio(value="a", label="A")
            ui.radio(value="b", label="B")
            ui.radio(value="c", label="C")
        # 3. Whole simple family in LOCAL mode — each must keep its value
        #    across the morph triggered by its own on_change.
        ui.checkbox(label="local check", on_change=family_change,
                    id="cb-local")
        ui.input(value="", placeholder="type me", on_change=family_change,
                 id="in-local")
        ui.textarea(value="", placeholder="type me", on_change=family_change,
                    id="ta-local")
        for i, line in enumerate(s.log[-6:]):
            ui.text(line, id=f"log-{i}", classes="font-mono")


@page("/")
def home() -> None:
    with ui.vstack(gap="lg", align="start", classes="p-8 w-[420px]"):
        ui.text("server events bench", size="2xl", weight="bold")
        switch_panel()


@app.fastapi.get("/calls")
async def calls():  # noqa: D401 — probe reads handler ground truth here
    from starlette.responses import JSONResponse
    return JSONResponse(CALLS)


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8972))
