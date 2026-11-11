"""The catalogue — data only: which page shows which component, in which group.

Each entry is ``(slug, label, icon)``. The slug is both the URL
(``/<slug>``) and the module ``features/components/<slug>.py``, which
exposes ``SUMMARY`` and ``page``. ``routes.py`` mounts every entry and
the shell lists them, so adding a page is one line here and one file.
"""

CATALOG: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("Actions", [
        ("button", "Button", "mouse-pointer-click"),
        ("icon-button", "Icon button", "circle-plus"),
        ("link", "Link", "link"),
    ]),
    ("Forms", [
        ("form", "Form", "clipboard-list"),
        ("input", "Input", "text-cursor-input"),
        ("textarea", "Textarea", "align-left"),
        ("number-input", "Number input", "hash"),
        ("select", "Select", "chevrons-up-down"),
        ("combobox", "Combobox", "search"),
        ("checkbox", "Checkbox", "square-check"),
        ("switch", "Switch", "toggle-right"),
        ("radio", "Radio group", "circle-dot"),
        ("toggle-group", "Toggle group", "rows-3"),
        ("slider", "Slider", "sliders-horizontal"),
        ("color-picker", "Color picker", "pipette"),
        ("file-upload", "File upload", "upload"),
        ("signature-pad", "Signature pad", "pen-line"),
        ("message", "Message", "messages-square"),
    ]),
    ("Dates & time", [
        ("calendar", "Calendar", "calendar"),
        ("date-picker", "Date picker", "calendar-days"),
        ("date-range-picker", "Date range picker", "calendar-range"),
        ("week-picker", "Week picker", "calendar-clock"),
        ("month-picker", "Month picker", "calendar-fold"),
        ("time-picker", "Time picker", "clock"),
    ]),
    ("Feedback", [
        ("alert", "Alert", "circle-alert"),
        ("banner", "Banner", "megaphone"),
        ("badge", "Badge", "tag"),
        ("avatar", "Avatar", "circle-user"),
        ("progress", "Progress", "loader"),
        ("spinner", "Spinner", "loader-circle"),
        ("skeleton", "Skeleton", "rectangle-horizontal"),
        ("empty-state", "Empty state", "inbox"),
        ("notification", "Notification", "bell"),
    ]),
    ("Overlays", [
        ("dialog", "Dialog", "app-window"),
        ("drawer", "Drawer", "panel-right"),
        ("dropdown", "Dropdown", "chevron-down"),
        ("popover", "Popover", "message-square"),
        ("tooltip", "Tooltip", "message-circle"),
    ]),
    ("Navigation", [
        ("tabs", "Tabs", "folders"),
        ("breadcrumb", "Breadcrumb", "chevrons-right"),
        ("pagination", "Pagination", "ellipsis"),
        ("stepper", "Stepper", "list-ordered"),
        ("navbar", "Navbar", "panel-top"),
        ("sidebar", "Sidebar", "panel-left"),
        ("bottom-bar", "Bottom bar", "panel-bottom"),
    ]),
    ("Layout", [
        ("card", "Card", "square"),
        ("stack", "Stack & flex", "rows-3"),
        ("grid", "Grid", "layout-grid"),
        ("container", "Container", "frame"),
        ("divider", "Divider", "minus"),
        ("resizable", "Resizable", "columns-2"),
        ("carousel", "Carousel", "gallery-horizontal"),
        ("viewport", "Viewport & pane", "monitor"),
        ("drag-and-drop", "Drag and drop", "grip-vertical"),
    ]),
    ("Data", [
        ("table", "Table", "table"),
        ("datatable", "Data table", "sheet"),
        ("tree", "Tree", "list-tree"),
        ("accordion", "Accordion", "list-collapse"),
        ("diagram", "Diagram", "workflow"),
        ("scheduler", "Scheduler", "calendar-clock"),
        ("lists", "Lists", "list"),
    ]),
    ("Charts", [
        ("bar-chart", "Bar chart", "chart-column"),
        ("histogram", "Histogram", "chart-no-axes-column"),
        ("line-chart", "Line chart", "chart-line"),
        ("pie-chart", "Pie chart", "chart-pie"),
        ("scatter-chart", "Scatter chart", "chart-scatter"),
        ("sparkline", "Sparkline", "activity"),
        ("stat", "Stat", "gauge"),
    ]),
    ("Content", [
        ("text", "Text", "type"),
        ("heading", "Heading", "heading"),
        ("icon", "Icon", "smile"),
        ("image", "Image", "image"),
        ("video", "Video", "video"),
        ("audio", "Audio", "volume-2"),
        ("iframe", "Iframe", "frame"),
        ("code", "Code", "code"),
        ("markdown", "Markdown", "file-text"),
        ("html", "HTML", "file-code"),
    ]),
    ("Utilities", [
        ("interval", "Interval", "timer"),
        ("page-utilities", "Page utilities", "file-cog"),
    ]),
]


def module_name(slug: str) -> str:
    """The module that renders ``/<slug>``."""
    return f"examples.showcase.features.components.{slug.replace('-', '_')}"
