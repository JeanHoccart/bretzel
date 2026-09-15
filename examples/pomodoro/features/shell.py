"""``shell`` — the app frame (a feature) : a centered column hosting the
outlet + a theme toggle. A layout is a feature that draws chrome and
exposes a region via ``ui.outlet()``.
"""

from __future__ import annotations

from bretzel import layout, ui
from bretzel.theme import ColorScheme


@layout
def shell() -> None:
    with ui.vstack(
        align="center",
        gap="md",
        justify="center",
        classes="relative min-h-screen w-full px-4 py-10",
    ):
        with ui.hstack(gap="xs", classes="absolute top-4 right-4"):
            ui.icon_button(
                "moon", variant="ghost", size="sm",
                on_click=ColorScheme.toggle(), tooltip="Dark mode",
                classes="dark:!hidden",
            )
            ui.icon_button(
                "sun", variant="ghost", size="sm",
                on_click=ColorScheme.toggle(), tooltip="Light mode",
                classes="!hidden dark:!inline-flex",
            )
        ui.outlet()
