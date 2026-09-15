"""Bench : server-authoritative value adopted on @refreshable swap (:8970).

The user's report : when a refreshable zone re-renders with a value that
the *server* changed (not the user), the bound input keeps showing the
old value. ``scope.absorb`` skips existing signals to preserve live
client state across morphs ; the fix re-adopts the keys a component
lists in ``_serverSync`` (here : ``value``) at the swap boundary.

Four server-bound (PageState ⇒ LOCAL mode) inputs in a refreshable
panel, plus a SEPARATE button that mutates every server var and
refreshes — so the inputs are never the ones firing the swap. Initial
≠ target so the probe can tell stale from fresh.

Run :  py tests/probes/bench_value_resync.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, refresh, refreshable, ui
from bretzel.state import PageState, field

app = Bretzel(
    secret_key="dev-value-resync-bench-secret-key",
    title="Bretzel · value resync bench",
    mode="dev",
)

FRUITS = ["Apple", "Banana", "Cherry"]
GREEK = ["alpha", "beta", "gamma"]


class Srv(PageState):
    num: float = field(default=7.0)
    sld: float = field(default=30.0)
    sel: str = field(default="Apple")
    cmb: str = field(default="alpha")
    bump: int = field(default=0)


def do_set(**kwargs) -> None:
    # Mutate every value SERVER-SIDE (external change), then refresh.
    s = Srv()
    s.num = 42.0
    s.sld = 80.0
    s.sel = "Cherry"
    s.cmb = "gamma"
    s.bump = s.bump + 1
    refresh(panel)


@refreshable
def panel() -> None:
    s = Srv()
    with ui.vstack(gap="md", align="start"):
        ui.text(f"server bump = {s.bump}", id="bump")

        ui.text("number_input (num)")
        ui.number_input(value=s.num, min=0, max=100, step=1, id="ni")

        ui.text("slider (sld)")
        ui.slider(value=s.sld, min=0, max=100, step=10, id="sl")

        ui.text("select single (sel)")
        ui.select(FRUITS, value=s.sel, placeholder="Pick", id="se")

        ui.text("combobox single (cmb)")
        ui.combobox(GREEK, value=s.cmb, placeholder="Search", id="cb")


@page("/")
def home() -> None:
    with ui.vstack(gap="lg", align="start", classes="p-8 w-96"):
        ui.text("value resync bench", size="2xl", weight="bold")
        ui.button("Set server values + refresh", on_click=do_set,
                  id="set-btn")
        panel()


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8970))
