"""``/card`` — the surface everything else sits on."""

from bretzel import ui
from bretzel.state import ClientState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A bordered surface with a padding scale — a link or a click "
           "target when you need one.")


def stat_card(label: str, value: str, delta: str, color: str) -> None:
    with ui.card(padding="md"), ui.vstack(gap="xs"):
        ui.text(label, size="sm", color="muted")
        ui.heading(value, level=3, size="2xl")
        ui.badge(delta, color=color, variant="soft", size="sm")


def metrics() -> None:
    with ui.grid(min_col="12rem", gap="md"):
        stat_card("Monthly revenue", "€48,240", "+12.4% vs August", "success")
        stat_card("Active customers", "1,284", "+36 this week", "info")
        stat_card("Churn", "2.1%", "+0.3 pts", "error")


def article() -> None:
    with ui.card(padding="none", classes="w-full max-w-sm"):
        ui.image(src="https://picsum.photos/seed/harbor/640/320",
                 alt="Boats moored in a harbour at dusk",
                 classes="aspect-[2/1] w-full")
        with ui.vstack(gap="sm", classes="p-5"):
            ui.badge("Case study", color="primary", variant="soft", size="sm")
            ui.heading("How Atlas Freight cut invoice disputes by 40%",
                       level=3, size="md")
            ui.text("Shared delivery proofs and one approval flow replaced "
                    "three spreadsheets and a weekly call.",
                    color="muted", size="sm")
            with ui.hstack(gap="sm"):
                ui.avatar(src="https://i.pravatar.cc/96?u=maya", name="Maya Chen",
                          size="xs")
                ui.text("Maya Chen · 6 min read", size="sm", color="muted")


def resource_card(title: str, text: str, icon: str, href: str) -> None:
    with ui.card(href=href, padding="md"), ui.vstack(gap="sm", align="start"):
        ui.icon(icon, size="lg", color="primary")
        ui.heading(title, level=3, size="md")
        ui.text(text, size="sm", color="muted")


def links() -> None:
    with ui.grid(min_col="12rem", gap="md"):
        resource_card("Quickstart", "Ship your first page in five minutes.",
                      "rocket", "/button")
        resource_card("Components", "Every building block, with its code.",
                      "blocks", "/grid")
        resource_card("Theming", "Repaint the whole app from one object.",
                      "palette", "/studio")


def paddings() -> None:
    with ui.grid(cols={"base": 2, "md": 5}, gap="md"):
        for padding in ("xs", "sm", "md", "lg", "xl"):
            with ui.card(padding=padding, classes="self-start"):
                ui.text(f"padding=\"{padding}\"", size="sm", weight="medium")


PLANS = [
    ("Starter", "€0", "For side projects", "3 projects, 1 seat"),
    ("Team", "€29", "For growing teams", "Unlimited projects, 10 seats"),
    ("Scale", "€99", "For the whole company", "SSO, audit log, SLA"),
]


class ChosenPlan(ClientState):
    name: str = field(default="Team")


def clickable() -> None:
    chosen = ChosenPlan().name
    with ui.grid(min_col="12rem", gap="md"):
        for name, price, tagline, limits in PLANS:
            with ui.card(padding="lg", hoverable=True,
                         on_click=chosen.set(name)), ui.vstack(gap="sm"):
                with ui.hstack(justify="between"):
                    ui.heading(name, level=3, size="md")
                    ui.badge("Selected", color="primary", size="sm",
                             icon_left="check", visible=chosen == name)
                with ui.hstack(gap="xs", align="baseline"):
                    ui.heading(price, level=4, size="3xl")
                    ui.text("/ month", color="muted", size="sm")
                ui.text(tagline, weight="medium")
                ui.text(limits, color="muted", size="sm")
    ui.text("You picked the " + chosen + " plan.", color="muted", size="sm")


def page() -> None:
    page_header("card", "Card", SUMMARY)
    example("Metrics at a glance", metrics, uses=[stat_card], full=True,
            note="The most common card: a label, a number, and what moved.")
    example("An article teaser", article,
            note="padding=\"none\" lets an image run to the edges; the card "
                 "clips it to its own corners.")
    example("Cards that navigate", links, uses=[resource_card], full=True,
            note="Give it an href and the whole card becomes the link, with "
                 "a hover lift to say so.")
    example("Pick a plan", clickable, uses=[ChosenPlan], full=True,
            note="on_click writes the choice to a ClientState: the badge and "
                 "the sentence follow in the browser, with no request.")
    example("Padding scale", paddings, full=True)
