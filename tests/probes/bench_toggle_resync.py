"""Bench : ToggleGroup value adopted on @refreshable swap (:8973).

Mirrors the playground "Server playground" : a ToggleGroup whose
``value`` comes from a PageState, inside a @refreshable panel, plus a
separate button that mutates the server value and refreshes. The group's
``picked`` scope signal must adopt the new server value on the swap —
like NumberInput/Slider/Select/Combobox do via ``_serverSync``.

Run :  py tests/probes/bench_toggle_resync.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, refresh, refreshable, ui
from bretzel.state import PageState, field

app = Bretzel(
    secret_key="dev-toggle-resync-bench-secret-key",
    title="Bretzel · toggle resync bench",
    mode="dev",
)

OPTS = [("all", "All"), ("active", "Active"), ("done", "Done")]


class Srv(PageState):
    single: str = field(default="active")
    multi: list = field(default_factory=lambda: ["active"])
    bump: int = field(default=0)


def set_single_done() -> None:
    Srv().single = "done"
    refresh(panel)


def set_multi_done() -> None:
    Srv().multi = ["done"]
    refresh(panel)


@refreshable
def panel() -> None:
    s = Srv()
    with ui.vstack(gap="md", align="start"):
        ui.text(f"bump={s.bump} single={s.single!r} multi={s.multi!r}", id="state")

        ui.text("single (value=Srv.single)")
        ui.toggle_group(options=OPTS, value=s.single, multiple=False,
                        id="tg-single")

        ui.text("multiple (value=Srv.multi — list field, _BoundList)")
        ui.toggle_group(options=OPTS, value=s.multi, multiple=True,
                        id="tg-multi")

        # Playground pattern : a multi group fed a WRAPPED scalar field
        # ([state.single]) — list whose element carries the stamp.
        ui.text("multiple (value=[Srv.single] — wrapped scalar)")
        ui.toggle_group(options=OPTS, value=[s.single], multiple=True,
                        id="tg-wrap")


@page("/")
def home() -> None:
    with ui.vstack(gap="lg", align="start", classes="p-8 w-[520px]"):
        ui.text("toggle resync bench", size="2xl", weight="bold")
        ui.button("server: single -> done", on_click=set_single_done,
                  id="btn-single")
        ui.button("server: multi -> done", on_click=set_multi_done,
                  id="btn-multi")
        panel()


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8973))
