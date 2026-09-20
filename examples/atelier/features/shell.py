"""features/shell — layout: the shell, and the only region the pages fill.

A ``kind="layout"`` feature: it has no route of its own, it EXPOSES a
region (``ui.outlet()``) that the pages come and fill.

A FROZEN document (``ui.viewport`` + ``ui.pane``): it is a tool, not a
document one scrolls. The sidebar stays, only the region changes — so a
navigation does not repaint the whole screen.
"""

from __future__ import annotations

from bretzel import Feature, layout, ui

#: The screens, in the order they are read: first the rhythm (the
#: question asked), then what explains it.
NAV = (
    ("/", "Tasks", "activity"),
    ("/phases", "Phases", "layers"),
    ("/tools", "Tools", "wrench"),
    ("/sessions", "Sessions", "calendar"),
)


@layout
def shell() -> None:
    """Rail on the left, region on the right."""
    with ui.viewport():
        with ui.sidebar(collapsible="rail"):
            ui.sidebar_title("Workshop", icon="activity")
            with ui.sidebar_section(label="Measurements"):
                for href, label, icon in NAV:
                    ui.sidebar_item(label, icon=icon, href=href)
        with ui.pane(classes="flex-1 min-w-0 p-6"):
            ui.outlet()


feature = Feature(name="shell", kind="layout", provides=[shell])
