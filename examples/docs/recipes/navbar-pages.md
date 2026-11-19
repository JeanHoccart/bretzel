# Pages with a navbar

> Three pages, Home, Projects and Contact, with a navigation bar at the top.

Save it as `app.py`, run `bretzel dev app:app` and open http://127.0.0.1:8000.

```python
"""Three pages that share a navigation bar."""

import sys

from bretzel import Bretzel, layout, page, ui

LINKS = (("Home", "/"), ("Projects", "/projects"), ("Contact", "/contact"))

PROJECTS = (
    ("Ledger", "Bookkeeping for freelancers, one screen per month."),
    ("Roster", "Shift planning for teams of five to fifty."),
    ("Atlas", "A map of every delivery, live."),
)


@layout
def site() -> None:
    with ui.navbar(sticky=True, width="md"):
        with ui.navbar_section(side="left"):
            ui.icon("hexagon", color="primary")
            ui.text("Northwind", weight="semibold")
        with ui.navbar_section(side="right"):
            for label, href in LINKS:
                ui.navbar_item(label, href=href)
    with ui.container(width="md", classes="py-8"):
        ui.outlet()


@page("/", layout=site, title="Home")
def home() -> None:
    with ui.vstack(gap="md"):
        ui.heading("Small tools for small teams", level=1)
        ui.text("We build the software a ten-person company runs on.", color="muted")
        ui.button("See our projects", href="/projects", icon_right="arrow-right")


@page("/projects", layout=site, title="Projects")
def projects() -> None:
    with ui.vstack(gap="md"):
        ui.heading("Projects", level=1)
        for name, summary in PROJECTS:
            with ui.card(), ui.vstack(gap="xs"):
                ui.heading(name, level=2, size="lg")
                ui.text(summary, color="muted")


@page("/contact", layout=site, title="Contact")
def contact() -> None:
    with ui.vstack(gap="md"):
        ui.heading("Contact", level=1)
        ui.text("Write to hello@example.com: we answer within a day.")


app = Bretzel(title="Northwind")
app.include(sys.modules[__name__])
```

## Why it works

- `@layout` is the shared frame and `ui.outlet()` is where each page lands. Every `@page(..., layout=site)` renders inside it; a click on a bar link swaps only the outlet, and the bar stays.
- `ui.navbar_item(label, href=...)` lights up by itself on its page: there is no active flag to keep.
- **The trap: a title is a `ui.heading`.** Each page opens on `ui.heading(..., level=1)`, a real `<h1>` that screen readers and search engines see; `ui.text(size="3xl")` only looks like one.
- The layout is drawn once per page load: a state it reads stays frozen. What changes belongs in the page or in a `@refreshable`.
