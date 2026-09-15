"""Shared documentation layout and navigation."""

from __future__ import annotations

from bretzel import Screen, layout, ui
from bretzel.state import ClientState, field
from bretzel.theme import ColorScheme

THEME_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("light", "Light theme", "sun"),
    ("dark", "Dark theme", "moon"),
    ("system", "System theme", "monitor"),
)


class DocsNavigation(ClientState):
    """Client-side query for the documentation navigation."""

    query: str = field(default="")


# (section, [(label, href, icon, description)])
NAV = [
    ("GET STARTED", [
        ("Introduction", "/", "compass", ""),
        ("Start in 5 minutes", "/quickstart", "rocket", ""),
        ("Understanding Bretzel", "/how", "book-open", ""),
        ("Describe the UI", "/describe", "layout-template", ""),
        ("Check your code", "/check", "shield-check", ""),
    ]),
    ("THE LOOP", [
        ("Server state", "/state-server", "database", ""),
        ("Client state", "/state-client", "monitor", ""),
        ("Server actions", "/actions-server", "mouse-pointer-click", ""),
        ("Client actions", "/actions-client", "terminal", ""),
        ("Server reactivity", "/reactivity-server", "zap", ""),
        ("Client reactivity", "/reactivity-client", "activity", ""),
    ]),
    ("BUILD", [
        ("Application structure", "/structure", "layers", ""),
        ("Application map", "/app-map", "network", ""),
        ("Theming", "/theme", "palette", ""),
    ]),
    ("GUIDES", [
        ("Lists and tables", "/lists", "table", ""),
        ("Forms", "/forms", "clipboard-list", ""),
        ("Drag and drop", "/drag", "move", ""),
        ("Charts", "/charts", "chart-line", ""),
        ("Scheduling", "/cadence", "timer", ""),
        ("Scrolling", "/scrolling", "scroll", ""),
        ("Languages", "/languages", "languages", ""),
        ("Authentication", "/auth", "key-round", ""),
        ("The browser", "/browser", "smartphone", ""),
        ("Common pitfalls", "/traps", "triangle-alert", ""),
    ]),
    ("REFERENCE", [
        ("Configuration", "/config", "settings", ""),
        ("Capabilities", "/capabilities", "sparkles", ""),
        ("ui.* catalog", "/components", "shapes", ""),
        ("Client runtime", "/runtime", "cpu", ""),
        ("Framework tree", "/tree", "folder-tree", ""),
        ("Cheat sheet", "/cheatsheet", "list", ""),
    ]),
]


@layout
def shell() -> None:
    with ui.viewport():
        mobile = Screen().is_mobile
        navigation = DocsNavigation()
        sidebar = ui.sidebar(
            collapsible="overlay" if mobile else "rail",
            open=not mobile,
            width="lg",
        )
        with sidebar:
            ui.sidebar_title(
                "Bretzel Docs",
                icon=ui.icon("book-open", color="primary", size="lg"),
            )
            ui.input(
                value=navigation.query,
                placeholder="Search documentation…",
                icon_left="search",
                clearable=True,
                size="sm",
                classes="my-2 group-data-[open=false]/sidebar:hidden",
            )
            for section, items in NAV:
                with ui.sidebar_section(label=section):
                    for label, path, icon, _description in ui.filter_each(
                        items,
                        query=navigation.query,
                        text=lambda item: f"{section} {item[0]}",
                        key=lambda item: item[1],
                    ):
                        ui.sidebar_item(label, icon=icon, href=path)
            with ui.sidebar_footer(
                name="Bretzel",
                subtitle="v0.1.0a1 · Early alpha",
            ):
                for value, label, icon in THEME_ITEMS:
                    ui.sidebar_footer_item(
                        label=label,
                        icon_left=icon,
                        on_click=ColorScheme.set(value),
                    )
                ui.sidebar_footer_item(
                    label="GitHub",
                    icon_left="github",
                    href="https://github.com/JeanHoccart/bretzel",
                )
        with ui.pane(
            gap="none",
            padding="lg",
            classes="min-w-0 max-md:px-4 max-md:pt-20 2xl:px-12",
        ):
            if mobile:
                with ui.hstack(
                    align="center",
                    gap="sm",
                    classes=(
                        "fixed inset-x-0 top-0 z-30 h-16 px-4 "
                        "bg-background/95 backdrop-blur border-b border-text/10"
                    ),
                ):
                    ui.sidebar_trigger(sidebar, icon="menu", size="sm")
                    ui.text("Bretzel Docs", weight="bold")
            ui.outlet()
