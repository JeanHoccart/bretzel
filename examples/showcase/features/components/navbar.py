"""``/navbar`` — the bar across the top of an app or a site."""

from bretzel import ui
from bretzel.state import ClientState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A brand on the left, links in the middle, actions on the right — "
           "sticky, lined up with the page, and aware of the page that is open.")


def product_bar() -> None:
    with ui.vstack(gap="none", classes="w-full overflow-hidden rounded-box "
                                       "border border-text/10"), ui.navbar():
        with ui.navbar_section(side="left"):
            ui.icon("wind", color="primary", size="lg")
            ui.heading("Northwind", level=3, size="md")
        with ui.navbar_section(side="center", classes="max-md:hidden"):
            ui.navbar_item("Overview", icon="layout-dashboard", active=True)
            ui.navbar_item("Customers", icon="users")
            ui.navbar_item("Invoices", icon="receipt", badge=3)
            ui.navbar_item("Payroll", icon="banknote", disabled=True)
        with ui.navbar_section(side="right"):
            ui.icon_button("bell", variant="ghost", size="sm",
                           tooltip="Notifications")
            ui.avatar(src="https://i.pravatar.cc/96?u=ada", name="Ada Lovelace",
                      size="sm")


def sticky_bar() -> None:
    with ui.vstack(gap="none", classes="h-80 w-full overflow-hidden rounded-box "
                                       "border border-text/10"), ui.pane():
        with ui.navbar(sticky=True):
            with ui.navbar_section(side="left"):
                ui.heading("The Field Journal", level=3, size="md")
            with ui.navbar_section(side="right"):
                ui.button("Subscribe", size="sm", variant="soft")
        with ui.vstack(gap="md", classes="p-6"):
            ui.heading("Why we moved our warehouse to the coast", level=2,
                       size="xl")
            for _ in range(6):
                ui.text("Shipping times fell by a third the month we moved. "
                        "The rent went up, the fuel bill went down, and the "
                        "team finally stopped driving two hours to meet the "
                        "trucks at the port.", color="muted")


def app_shell() -> None:
    with ui.vstack(gap="none", classes="w-full overflow-hidden rounded-box "
                                       "border border-text/10"):
        with ui.navbar(width="md"):
            with ui.navbar_section(side="left"):
                ui.navbar_item("Helpdesk", icon="life-buoy", active=True)
                ui.navbar_item("Reports", icon="chart-column")
            with ui.navbar_section(side="right"):
                ui.avatar(src="https://i.pravatar.cc/96?u=grace",
                          name="Grace Hopper", size="sm")
        with ui.container(width="md"), ui.vstack(gap="xs"):
            ui.heading("Open tickets", level=2, size="xl")
            ui.text("12 waiting on you, 3 past their deadline.", color="muted")


class Workspace(ClientState):
    view: str = field(default="board")


def switch_views() -> None:
    ws = Workspace()
    with ui.vstack(gap="none", classes="w-full overflow-hidden rounded-box "
                                       "border border-text/10"):
        with ui.navbar(), ui.navbar_section(side="left"):
            ui.navbar_item("Board", icon="kanban", active=ws.view == "board",
                           on_click=ws.view.set("board"))
            ui.navbar_item("Timeline", icon="calendar-range",
                           active=ws.view == "timeline",
                           on_click=ws.view.set("timeline"))
            ui.navbar_item("Files", icon="paperclip", badge=8,
                           active=ws.view == "files",
                           on_click=ws.view.set("files"))
        with ui.vstack(gap="xs", classes="p-6"):
            with ui.vstack(gap="xs", visible=ws.view == "board"):
                ui.heading("Board", level=3, size="lg")
                ui.text("14 cards across To do, Doing and Done.", color="muted")
            with ui.vstack(gap="xs", visible=ws.view == "timeline"):
                ui.heading("Timeline", level=3, size="lg")
                ui.text("Launch is in 23 days; two milestones are at risk.",
                        color="muted")
            with ui.vstack(gap="xs", visible=ws.view == "files"):
                ui.heading("Files", level=3, size="lg")
                ui.text("8 files, last one uploaded by Grace this morning.",
                        color="muted")


def page() -> None:
    page_header("navbar", "Navbar", SUMMARY)
    example("A product's top bar", product_bar, full=True,
            note="Three sections: side= pins them left, centre and right. "
                 "Items take an icon, a badge, and can be disabled.")
    example("Lined up with the page", app_shell, full=True,
            note='width= takes the words of ui.container: the bar and the '
                 "page share their left edge — the first item's text sits "
                 "right above the page title.")
    example("Stays on top while you read", sticky_bar, full=True,
            note="sticky=True pins the bar to the top of whatever scrolls. "
                 "Scroll the article inside the box.")
    example("Switch views without a round trip", switch_views, uses=[Workspace],
            full=True,
            note="active= and on_click= are tied to a ClientState: the view "
                 "changes in the browser, with no request to the server.")
