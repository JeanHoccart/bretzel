"""``/carousel`` — a row of slides you swipe through."""

from bretzel import ui
from bretzel.state import ClientState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Slides that snap into place under a swipe, the wheel or the "
           "arrows — one at a time, several at once, or on autoplay.")


def gallery() -> None:
    with ui.carousel(classes="w-full max-w-xl"):
        for seed in ("cabin", "lake", "forest", "dunes", "harbor"):
            ui.image(src=f"https://picsum.photos/seed/{seed}/960/540",
                     alt=f"Holiday rental — {seed}", ratio="video")


def products() -> list[tuple[str, str, str]]:
    return [
        ("Linen shirt", "€59", "shirt"),
        ("Canvas tote", "€24", "tote"),
        ("Leather boots", "€149", "boots"),
        ("Wool beanie", "€19", "beanie"),
        ("Denim jacket", "€89", "denim"),
        ("Cotton scarf", "€29", "scarf"),
    ]


def several_at_once() -> None:
    with ui.carousel(per_view={"base": 1, "sm": 2, "lg": 3}, size="sm",
                     color="secondary", classes="[contain:inline-size]"):
        for name, price, seed in products():
            with ui.card(padding="none"):
                ui.image(src=f"https://picsum.photos/seed/{seed}/480/360",
                         alt=name, classes="aspect-[4/3] w-full")
                with ui.hstack(justify="between", classes="p-3"):
                    ui.text(name, weight="medium")
                    ui.text(price, color="muted")


def announcements() -> None:
    with ui.carousel(autoplay=4, classes="w-full max-w-2xl"):
        for title, body, color in (
            ("Dark mode is here", "Every screen, every chart — flip it "
             "from the theme menu.", "primary"),
            ("Invoices in 38 currencies", "Bill your clients in theirs; "
             "we convert at the day's rate.", "success"),
            ("Webinar on Thursday", "How Atlas Freight closes its books "
             "in two days. Seats are limited.", "info"),
        ):
            with ui.card(padding="lg", color=color), ui.vstack(gap="xs"):
                ui.heading(title, level=3, size="lg")
                ui.text(body)


class Tour(ClientState):
    step: int = field(default=0)


def onboarding() -> None:
    tour = Tour()
    screen = tour.step + 1
    with ui.vstack(gap="md", classes="w-full max-w-xl [contain:inline-size]"):
        with ui.carousel(value=tour.step) as slides:
            for icon, title, body in (
                ("folder-plus", "Create a project", "Group boards, files and "
                 "people around one goal."),
                ("user-plus", "Invite your team", "Everyone sees the same board, "
                 "live."),
                ("plug", "Connect your tools", "Slack, GitHub and Google "
                 "Drive in two clicks."),
                ("rocket", "Ship it", "Track the launch from the timeline."),
            ):
                with ui.card(padding="lg"), ui.vstack(gap="sm", align="center"):
                    ui.icon(icon, size="xl", color="primary")
                    ui.heading(title, level=3, size="lg")
                    ui.text(body, color="muted", align="center")
        ui.progress(value=screen, max=4, label="Screen " + screen + " of 4",
                    show_label=True, size="sm")
        with ui.hstack(gap="sm", justify="center"):
            ui.button("Back", variant="ghost", icon_left="arrow-left",
                      on_click=slides.prev())
            ui.button("Next", icon_right="arrow-right", on_click=slides.next())


def page() -> None:
    page_header("carousel", "Carousel", SUMMARY)
    example("A photo gallery", gallery,
            note="Every child is a slide. Arrows and dots appear on their own, "
                 "and the arrows switch off at either end.")
    example("Several at once", several_at_once, uses=[products], full=True,
            note="per_view= takes a number, or one per breakpoint: one card on "
                 "a phone, three on a desktop. With more than one in view, "
                 "the dots step aside.")
    example("Announcements on autoplay", announcements,
            note="autoplay=4 turns the page every four seconds, and stops for "
                 "good the moment the reader touches it.")
    example("An onboarding tour", onboarding,
            uses=[Tour],
            note="The buttons drive the carousel with .prev() and .next(); "
                 "value= is bound to a ClientState, so the bar follows the "
                 "slide in the browser.")
