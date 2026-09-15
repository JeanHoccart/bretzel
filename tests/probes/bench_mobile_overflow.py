"""Bench app for the mobile-overflow probe (port 8995).

Every overlay that carries a HARD dimension, at every ``width=`` step,
so the probe can check that none of them exceeds a 375 px viewport.

Tier-1 user code only. Run :  py tests/probes/bench_mobile_overflow.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-mobile-overflow-bench-secret-key",
    title="Bretzel · mobile overflow bench",
    mode="dev",
)

WIDTHS = ("sm", "md", "lg", "xl", "full")
SIDES = ("left", "right", "top", "bottom")


@page("/", title="Mobile overflow bench")
def home() -> None:
    with ui.vstack(gap="md", align="start"):
        ui.heading("Mobile overflow bench", level=2)

        for side in SIDES:
            for width in WIDTHS:
                with ui.drawer(title=f"drawer {side} {width}", side=side, width=width) as drw:
                    ui.text(f"Content of the {side}/{width} drawer.")
                ui.button(
                    f"open drawer {side} {width}",
                    id=f"drawer-{side}-{width}",
                    on_click=drw.open(),
                )

        for width in WIDTHS:
            with ui.dialog(title=f"dialog {width}", width=width) as dlg:
                ui.text(f"Content of the {width} dialog.")
            ui.button(
                f"open dialog {width}",
                id=f"dialog-{width}",
                on_click=dlg.open(),
            )

        # ── Wide content ────────────────────────────────────────────
        # A flex item cannot shrink below its min-content width
        # (``min-width: auto``), so an unbreakable token is what turns
        # a "flex-shrink handles it" panel back into an overflow. This
        # is the realistic case : UUIDs, URLs, file paths.
        long_token = "bretzel-" + "x" * 180 + "-end"
        with ui.drawer(title="drawer wide", side="left", width="md") as wide_drw:
            ui.text(long_token)
        ui.button("open drawer wide", id="drawer-wide", on_click=wide_drw.open())

        with ui.dialog(title="dialog wide", width="md") as wide_dlg:
            ui.text(long_token)
        ui.button("open dialog wide", id="dialog-wide", on_click=wide_dlg.open())


app.include(home)


if __name__ == "__main__":
    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    app.run(port=bench_port(8995))
