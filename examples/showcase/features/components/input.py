"""``/input`` — the single-line text field."""

from bretzel import refreshable, ui
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("One line of text, in every HTML type — with icons, prefixes, a "
           "clear button, and keystrokes that can reach Python.")


def sign_in() -> None:
    with ui.vstack(gap="md", classes="w-full max-w-sm"):
        with ui.form_field(label="Email"):
            ui.input(type="email", icon_left="mail", placeholder="you@company.com",
                     autocomplete="email")
        with ui.form_field(label="Password"):
            ui.input(type="password", icon_left="lock",
                     autocomplete="current-password")
        ui.button("Sign in", classes="w-full")


def prefix_suffix() -> None:
    with ui.vstack(gap="md", classes="w-full max-w-sm"):
        with ui.form_field(label="Website"):
            ui.input(prefix="https://", placeholder="northwind.com")
        with ui.form_field(label="Hourly rate"):
            ui.input(prefix="€", suffix="/ hour", value="85")
        with ui.form_field(label="Team handle"):
            ui.input(suffix=".bretzel.app", placeholder="design-team")


def sizes() -> None:
    with ui.vstack(gap="sm", classes="w-full max-w-sm"):
        for size in ("xs", "sm", "md", "lg", "xl"):
            ui.input(size=size, placeholder=f"Search projects ({size})",
                     icon_left="search")


CUSTOMERS = [
    ("Northwind Traders", "Seattle", "Enterprise"),
    ("Lumen Studio", "Lisbon", "Team"),
    ("Atlas Freight", "Rotterdam", "Enterprise"),
    ("Kinfolk & Co", "Copenhagen", "Starter"),
    ("Harbor Health", "Boston", "Team"),
    ("Pine & Ledger", "Toronto", "Starter"),
    ("Orbit Robotics", "Munich", "Enterprise"),
]


class CustomerSearch(PageState):
    query: str = field(default="")


def search_customers(search: CustomerSearch) -> None:
    """The typed parameter receives the input's value; the list follows."""


@refreshable
def customer_results() -> None:
    needle = CustomerSearch().query.strip().lower()
    hits = [c for c in CUSTOMERS if needle in c[0].lower() or needle in c[1].lower()]
    with ui.vstack(gap="xs"):
        for name, city, plan in hits:
            with ui.hstack(gap="sm", justify="between"):
                with ui.hstack(gap="sm"):
                    ui.avatar(name=name, size="xs", color="secondary")
                    ui.text(name, weight="medium")
                    ui.text(city, color="muted", size="sm")
                ui.badge(plan, variant="soft", size="sm")
        if not hits:
            ui.text(f"No customer matches “{needle}”.", color="muted")


def live_search() -> None:
    with ui.vstack(gap="md", classes="w-full max-w-md"):
        ui.input(value=CustomerSearch().query, placeholder="Filter customers…",
                 icon_left="search", clearable=True, debounce=250,
                 on_input=search_customers)
        customer_results()


def states() -> None:
    with ui.vstack(gap="md", classes="w-full max-w-sm"):
        with ui.form_field(label="API key", hint="Read-only — rotate it from "
                                                  "the security tab."):
            ui.input(value="bz_live_4f9a…c21e", readonly=True, icon_left="key-round")
        with ui.form_field(label="Organisation ID"):
            ui.input(value="org_83kd02", disabled=True)
        with ui.form_field(label="Coupon"):
            ui.input(value="SPRING-25", clearable=True, color="success")


def page() -> None:
    page_header("input", "Input", SUMMARY)
    example("A sign-in form", sign_in,
            note="type= is the HTML type: the browser brings the right "
                 "keyboard, autofill and masking.")
    example("Prefix and suffix", prefix_suffix,
            note="Fixed text on either side of the value — the unit, the "
                 "scheme, the domain — so nobody has to type it.")
    example("Sizes", sizes)
    example("Filter as you type", live_search,
            uses=[CustomerSearch, search_customers, customer_results],
            note="on_input sends the value to Python, debounced by 250 ms; only "
                 "the result list re-renders.")
    example("Read-only, disabled, clearable", states,
            note="Read-only can still be selected and copied; disabled is out "
                 "of the form entirely. color= tints the focus ring.")
