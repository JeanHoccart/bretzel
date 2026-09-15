"""Bench for the hoverable-card regressions (port 8962).

Two guarded regressions :

1. The hoverable variant gated its lift on ``aria-enabled:hover:*`` —
   but ``aria-enabled`` is not a Tailwind variant and the Card never
   emits that attribute, so the lift silently never compiled (flat
   cards). Fixed to plain ``hover:*`` + ``aria-disabled:hover:*``
   neutralisers.
2. The lift must stay a POSITION offset (``relative top-0
   hover:-top-0.5``), never a ``translate`` — a transform would make
   the card the containing block of its descendants' ``fixed`` overlay
   panels. Cf. traps.md § « Hover lift en translate » (2026-07-15).

Run :  py tests/probes/bench_card_hover.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-card-hover-bench-secret-key",
    title="Bretzel · Card hover bench",
    mode="dev",
)


@page("/")
def home() -> None:
    with ui.hstack(gap="lg", align="start", classes="p-8"):
        with ui.card(id="static-card"):
            ui.text("Static (default)")
        with ui.card(hoverable=True, id="hover-card"):
            ui.text("Hover me — lifts 1 px")
        # Locked surface : app marks it aria-disabled → must NOT lift.
        with ui.card(hoverable=True, id="locked-card",
                     attrs={"aria-disabled": "true"}):
            ui.text("Locked (aria-disabled)")


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8962))
