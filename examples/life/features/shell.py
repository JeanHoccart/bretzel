"""``shell`` — the app frame : a centered column hosting the outlet and a
theme toggle in the corner."""

from __future__ import annotations

from bretzel import layout, ui
from bretzel.theme import ColorScheme


@layout
def shell() -> None:
    with ui.vstack(
        align="center",
        gap="md",
        classes="relative min-h-screen w-full px-4 py-6",
    ):
        ui.icon_button(
            "sun-moon", variant="ghost", size="sm",
            on_click=ColorScheme.toggle(), tooltip="Light / dark",
            classes="absolute top-4 right-4",
        )
        ui.outlet()
