"""Bench reproducing the Link full-width hit-area bug (port 8960).

Mirrors the playground's "Quick links" list exactly : three ``ui.link``
as direct children of a ``ui.vstack``. A vstack is ``flex flex-col`` with
the default ``align-items: stretch``, so each ``<a>`` (width auto) gets
stretched to the full column width — the WHOLE row becomes clickable,
not just the text. The user can select/click the link from far right.

Run :  py tests/probes/bench_link.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-link-bench-secret-key",
    title="Bretzel · Link bench",
    mode="dev",
)


@page("/")
def home() -> None:
    with ui.vstack(gap="xl", align="start", classes="p-8 w-full"):
        ui.text("Link bench", size="2xl", weight="bold")
        with ui.card():
            with ui.vstack():
                ui.heading("Quick links", level=3)
                with ui.vstack(gap="sm"):
                    ui.link("• Button reference", href="/button", id="lnk-1")
                    ui.link("• Input reference", href="/input", id="lnk-2")
                    ui.link("• Theme cookbook",
                            href="https://bretzel.dev", external=True,
                            id="lnk-3")

        # Disabled : hover effect must be OFF, cursor stays not-allowed.
        with ui.hstack(gap="lg", align="start"):
            ui.link("Enabled hover", href="/x", variant="hover",
                    id="lnk-enabled")
            ui.link("Disabled hover", href="/x", variant="hover",
                    disabled=True, id="lnk-disabled")
            ui.link("Disabled text", href="/x", variant="text",
                    disabled=True, id="lnk-disabled-text")


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8960))
