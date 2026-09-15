"""Bench for the Text-align probe (port 8958).

Reproduces the playground's preview wrapper exactly : each Text sits in
a ``flex justify-center`` row (``examples/playground/features/text.py``
renders the preview inside ``ui.flex(justify='center', align='center')``).
Before the fix, ``align=`` landed ``text-right`` on the default inline
``<span>`` — a content-width box, so ``text-align`` was a silent no-op
and the flex wrapper centred every variant identically.

Run :  py tests/probes/bench_text_align.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-text-align-bench-secret-key",
    title="Bretzel · Text align bench",
    mode="dev",
)

ALIGNS = ["left", "center", "right", "justify"]


@page("/")
def home() -> None:
    with ui.vstack(gap="xl", align="start", classes="p-8 w-full"):
        ui.text("Text align bench", size="2xl", weight="bold")
        # Each preview row mirrors the playground's centred flex wrapper.
        for a in ALIGNS:
            with ui.flex(
                justify="center", align="center", classes="w-full",
                id=f"row-{a}",
            ):
                ui.text("Fox", align=a, id=f"t-{a}", size="2xl")


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8958))
