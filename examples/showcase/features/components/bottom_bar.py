"""``/bottom-bar`` — the tab bar of a phone app."""

from bretzel import ui
from bretzel.state import ClientState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("The tab bar of a phone app: four destinations, a badge on what "
           "needs you, always under the thumb.")


class Phone(ClientState):
    tab: str = field(default="home")


def phone_app() -> None:
    phone = Phone()
    with ui.vstack(gap="none", classes="h-[32rem] w-full max-w-sm overflow-hidden "
                                       "rounded-box border border-text/10"):
        with ui.pane(padding="md", gap="md"):
            with ui.vstack(gap="md", visible=phone.tab == "home"):
                ui.heading("Today", level=3, size="xl")
                for place, when, photo in (
                    ("Café Lumière", "Table for 2 · 19:30", "cafe"),
                    ("Studio Pilates", "Class · Tomorrow 08:00", "yoga"),
                    ("Barber & Co", "Haircut · Friday 17:15", "barber"),
                ):
                    with ui.card(padding="sm"), ui.hstack(gap="sm"):
                        ui.image(src=f"https://picsum.photos/seed/{photo}/96/96",
                                 alt=place, classes="size-12 shrink-0")
                        with ui.vstack(gap="none"):
                            ui.text(place, weight="medium")
                            ui.text(when, color="muted", size="sm")
            with ui.vstack(gap="sm", visible=phone.tab == "search"):
                ui.heading("Search", level=3, size="xl")
                ui.input(placeholder="Restaurants, classes, salons…",
                         icon_left="search")
            with ui.vstack(gap="sm", visible=phone.tab == "inbox"):
                ui.heading("Inbox", level=3, size="xl")
                ui.text("Café Lumière confirmed your table for tonight.",
                        color="muted")
            with ui.vstack(gap="sm", visible=phone.tab == "profile"):
                ui.heading("Profile", level=3, size="xl")
                ui.text("Ada Lovelace · member since 2021", color="muted")
        with ui.bottom_bar():
            ui.bottom_bar_item("Home", icon="house", active=phone.tab == "home",
                               on_click=phone.tab.set("home"))
            ui.bottom_bar_item("Search", icon="search",
                               active=phone.tab == "search",
                               on_click=phone.tab.set("search"))
            ui.bottom_bar_item("Inbox", icon="inbox", badge=2,
                               active=phone.tab == "inbox",
                               on_click=phone.tab.set("inbox"))
            ui.bottom_bar_item("Profile", icon="user",
                               active=phone.tab == "profile",
                               on_click=phone.tab.set("profile"))


def badges_and_states() -> None:
    with ui.vstack(gap="none", classes="w-full max-w-sm overflow-hidden "
                                       "rounded-box border border-text/10"), ui.bottom_bar():
        ui.bottom_bar_item("Shop", icon="store", active=True)
        ui.bottom_bar_item("Orders", icon="package", badge=3)
        ui.bottom_bar_item("Chat", icon="message-circle", badge="9+")
        ui.bottom_bar_item("Wallet", icon="wallet", disabled=True)


class Fitness(ClientState):
    tab: str = field(default="today")


def tab_colours() -> None:
    fit = Fitness()
    with ui.vstack(gap="none", classes="w-full max-w-sm overflow-hidden "
                                       "rounded-box border border-text/10"), ui.bottom_bar():
        ui.bottom_bar_item("Today", icon="sun", color="warning",
                           active=fit.tab == "today",
                           on_click=fit.tab.set("today"))
        ui.bottom_bar_item("Workouts", icon="dumbbell", color="success",
                           active=fit.tab == "workouts",
                           on_click=fit.tab.set("workouts"))
        ui.bottom_bar_item("Sleep", icon="moon", color="info",
                           active=fit.tab == "sleep",
                           on_click=fit.tab.set("sleep"))
        ui.bottom_bar_item("Heart", icon="heart-pulse", color="error",
                           active=fit.tab == "heart",
                           on_click=fit.tab.set("heart"))


class Inbox(ClientState):
    unread: int = field(default=4)


def live_badge() -> None:
    inbox = Inbox()
    with ui.vstack(gap="none", classes="w-full max-w-sm overflow-hidden "
                                       "rounded-box border border-text/10"), ui.bottom_bar():
        ui.bottom_bar_item("Feed", icon="newspaper", active=True)
        ui.bottom_bar_item("Alerts", icon="bell", badge=inbox.unread,
                           on_click=inbox.unread.set(0))
        ui.bottom_bar_item("Account", icon="circle-user")
    ui.button("Simulate an alert", icon_left="plus", variant="soft", size="sm",
              on_click=inbox.unread.increment())


def page() -> None:
    page_header("bottom_bar", "Bottom bar", SUMMARY)
    example("A phone app", phone_app, uses=[Phone],
            note="The bar sits under a ui.pane that scrolls. active= and "
                 "on_click= are tied to a ClientState, so switching tabs "
                 "never waits for the server. In an app, give each item an "
                 "href= instead: the active tab then follows the URL.")
    example("Badges and a disabled tab", badges_and_states,
            note="A badge counts what is waiting; disabled= greys out a tab "
                 "that is not available yet.")
    example("A colour per tab", tab_colours, uses=[Fitness],
            note="color= paints the tab while it is active — try each one.")
    example("A live badge", live_badge, uses=[Inbox],
            note="badge= follows a ClientState field and folds away at zero. "
                 "Open Alerts to mark them read.")
