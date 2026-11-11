"""``/interval`` — a page that keeps itself up to date."""

import random
from datetime import datetime
from zoneinfo import ZoneInfo

from bretzel import refresh, refreshable, ui
from bretzel.state import ClientState, PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("An invisible timer that calls Python every few seconds — "
           "pausable from the browser, stopped for free when the tab closes.")


def tick() -> None:
    refresh(world_clock)


OFFICES = [("Paris", "Europe/Paris"), ("New York", "America/New_York"),
           ("Tokyo", "Asia/Tokyo")]


@refreshable
def world_clock() -> None:
    with ui.grid(cols=3, gap="md", classes="w-full max-w-lg"):
        for city, zone in OFFICES:
            now = datetime.now(ZoneInfo(zone))
            with ui.card(padding="md"), ui.vstack(gap="none", align="center"):
                ui.text(city, size="sm", color="muted")
                ui.text(now.strftime("%H:%M:%S"), size="2xl", weight="semibold",
                        classes="font-mono tabular-nums")
                ui.text(now.strftime("%a %d %b"), size="xs", color="muted")


def clock_demo() -> None:
    world_clock()
    ui.interval(on_tick=tick, seconds=1)


class Traffic(PageState):
    samples: list[int] = field(default_factory=lambda: [42, 48, 45, 51, 58, 54,
                                                        61, 57, 63, 60])


class Live(ClientState):
    on: bool = field(default=True)


def sample_traffic() -> None:
    traffic = Traffic()
    traffic.samples = [*traffic.samples[1:], random.randint(40, 80)]


@refreshable
def traffic_card() -> None:
    samples = Traffic().samples
    with ui.hstack(gap="lg", justify="between", align="end"):
        with ui.vstack(gap="none"):
            ui.text("Requests / second", size="sm", color="muted")
            ui.text(str(samples[-1]), size="3xl", weight="bold",
                    classes="tabular-nums")
        ui.sparkline(data=samples, color="primary", area_fill=True)


def traffic_demo() -> None:
    live = Live()
    with ui.card(padding="md", classes="w-full max-w-md"), ui.vstack(gap="md"):
        with ui.hstack(justify="between"):
            ui.badge("api-gateway · eu-west", variant="soft", size="sm")
            ui.switch(checked=live.on, label="Live", size="sm")
        traffic_card()
    ui.interval(on_tick=sample_traffic, seconds=2, disabled=~live.on)


class Resend(ClientState):
    left: int = field(default=30)


def countdown_demo() -> None:
    resend = Resend()
    with ui.card(padding="lg", classes="w-full max-w-sm"), ui.vstack(gap="md"):
        ui.heading("Check your inbox", level=3, size="lg")
        ui.text("We sent a 6-digit code to maya@northwind.dev.", color="muted",
                size="sm")
        ui.button((resend.left > 0).then_else("Resend code in " + resend.left + " s",
                                              "Resend code"),
                  variant="outline", disabled=resend.left > 0,
                  on_click=resend.left.set(30))
    ui.interval(on_tick=resend.left.decrement(1), seconds=1, disabled=resend.left <= 0)


def page() -> None:
    page_header("interval", "Interval", SUMMARY)
    example("A world clock", clock_demo, uses=[tick, world_clock],
            note="Every second the browser calls tick(), and only the clock "
                 "zone is re-rendered.")
    example("Live traffic, pausable", traffic_demo,
            uses=[Traffic, Live, sample_traffic, traffic_card],
            note="disabled= takes a ClientState field: the switch stops the timer "
                 "in the browser, with no server task to cancel.")
    example("A countdown with no server at all", countdown_demo, uses=[Resend],
            note="on_tick= also takes a client action. The timer counts down "
                 "in the page and stops itself at zero.")
