"""Render — refreshable panels + page assembly for the Scheduler feature.

Seven cards. ``EVENTS = ("select", "move", "resize", "create")``, no
``BINDABLE_PROPS``, no imperative API, no named slot. Reference / Edge
cases / Composability / A11y show the component; Server playground wires
every prop to a control; Server events is the live week — drag, pull,
click, and the server accepts, refuses (past 18:00) or asks first (a
repeating lesson); Client events wires the three events to client
expressions.
"""

import datetime as dt

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression
from examples.playground.features.inspection import emitted_html_block
from examples.playground.features.scheduler.logic import (
    agenda_changed,
    agenda_next,
    agenda_previous,
    agenda_today,
    cancel_move,
    clear_log,
    create_event,
    log_only_move,
    move_event,
    move_this_one,
    reset_week,
    resize_event,
    select_event,
    server_changed,
)
from examples.playground.features.scheduler.state import (
    CALENDAR_OF,
    CALENDARS,
    COLORS,
    FRENCH_DAYS,
    LESSONS,
    MONDAY,
    TUESDAY,
    VIEWS,
    SchedulerAgenda,
    SchedulerClientEvents,
    SchedulerEvents,
    SchedulerPlayground,
    SchedulerQuestion,
    SchedulerWeek,
    lesson,
    month_events,
    week_events,
)


def at(day: int, hhmm: str) -> dt.datetime:
    return dt.datetime.combine(MONDAY + dt.timedelta(days=day), dt.time.fromisoformat(hhmm))


def live_events() -> list[dict]:
    moved = SchedulerWeek().moved
    events = week_events()
    for event in events:
        if event["id"] in moved:
            event["start"], event["end"] = (dt.datetime.fromisoformat(v)
                                            for v in moved[event["id"]])
    for index, (start, end) in enumerate(SchedulerWeek().created):
        events.append({"id": f"new-{index}", "title": "New event", "color": "primary",
                       "start": start, "end": end})
    return events


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        key, sep, value = raw.partition("=")
        if sep and key.strip():
            result[key.strip()] = value.strip()
    return result


def build_preview(state: SchedulerPlayground) -> dict:
    kwargs: dict = {
        "events": live_events() if state.view != "month" else month_events(),
        "date": dt.date.fromisoformat(state.date) if state.date else MONDAY,
        "view": state.view,
        "snap": int(state.snap),
    }
    if state.weekend != "auto":
        kwargs["weekend"] = state.weekend == "on"
    if state.first_hour and state.last_hour:
        kwargs["hours"] = (int(state.first_hour), int(state.last_hour))
    if state.weekday_names == "fr":
        kwargs["weekday_names"] = FRENCH_DAYS
    if state.on_item_click_mode == "server":
        kwargs["on_item_click"] = select_event
    elif state.on_item_click_mode == "client":
        kwargs["on_item_click"] = "$el.classList.toggle('ring-4')"
    if state.on_move_mode == "server":
        kwargs["on_move"] = move_event
        kwargs["on_resize"] = resize_event
    elif state.on_move_mode == "client":
        kwargs["on_move"] = "console.log($event.target.value)"
    if state.classes:
        kwargs["classes"] = state.classes
    if state.custom_id:
        kwargs["id"] = state.custom_id
    if state.style:
        kwargs["style"] = state.style
    if attrs := parse_extra_attrs(state.extra_attrs):
        kwargs["attrs"] = attrs
    if state.visible == "off":
        kwargs["visible"] = False
    return kwargs


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable
def server_panel() -> None:
    state = SchedulerPlayground()
    hours = [("", "auto")] + [(str(h), f"{h}:00") for h in range(0, 25)]
    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("view"):
            ui.select(value=state.view, options=[(v, v) for v in VIEWS],
                      on_change=server_changed)
        with control("date"):
            ui.date_picker(value=state.date, on_change=server_changed)
        with control("weekend"):
            ui.select(value=state.weekend,
                      options=[("auto", "None (when used)"), ("on", "True"), ("off", "False")],
                      on_change=server_changed)
        with control("hours — first"):
            ui.select(value=state.first_hour, options=hours, on_change=server_changed)
        with control("hours — last"):
            ui.select(value=state.last_hour, options=hours, on_change=server_changed)
        with control("snap (minutes)"):
            ui.select(value=state.snap,
                      options=[(m, m) for m in ("1", "5", "10", "15", "30")],
                      on_change=server_changed)
        with control("weekday_names"):
            ui.select(value=state.weekday_names,
                      options=[("", "None (from the browser)"), ("fr", "French list")],
                      on_change=server_changed)
        with control("on_item_click mode"):
            ui.select(value=state.on_item_click_mode,
                      options=[("none", "None"), ("server", "Server callable"),
                               ("client", "Client string")],
                      on_change=server_changed)
        with control("on_move / on_resize mode"):
            ui.select(value=state.on_move_mode,
                      options=[("none", "None (no gesture)"), ("server", "Server callables"),
                               ("client", "Client string (move only)")],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="max-w-xl", on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-week", on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="max-width: 600px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=2, placeholder="data-test=week",
                        on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"), ("off", "False (skip render)")],
                      on_change=server_changed)
    ui.divider()
    server_preview()
    ui.divider()
    # On SchedulerPlayground only: a drag moves the preview, not the code
    # it was built from — there is nothing new to show here.
    emitted_html_block("Emitted HTML (Scheduler)",
                       serialize_html(ui.scheduler(**build_preview(state))))


@refreshable
def server_preview() -> None:
    ui.scheduler(**build_preview(SchedulerPlayground()))


@refreshable
def live_week() -> None:
    ui.scheduler(events=live_events(), date=MONDAY, on_item_click=select_event,
                 on_move=move_event, on_resize=resize_event, on_create=create_event)


# Not SchedulerWeek: the week must not redraw when the question opens —
# the dropped card would jump back under it.
@refreshable
def question_dialog() -> None:
    with ui.dialog(open=bool(SchedulerQuestion().pending), title="Move this lesson?",
                   persistent=True), ui.vstack(gap="md"):
        ui.text("It repeats every week. Move only this one?")
        with ui.hstack(gap="sm", justify="end"):
            ui.button("Cancel", variant="ghost", on_click=cancel_move)
            ui.button("This one only", on_click=move_this_one)


@refreshable
def events_log() -> None:
    lines = SchedulerEvents().log
    with ui.hstack(justify="between", align="center"):
        ui.text("Live log", color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs", on_click=clear_log)
    ui.text("\n".join(lines[-12:]) or "(no events yet)", color="muted", size="sm",
            classes="font-mono whitespace-pre")


@refreshable
def agenda() -> None:
    """A whole agenda, assembled: the scheduler draws the grid, the rest is
    ui.heading, ui.button, ui.toggle_group — no option of the scheduler."""
    state = SchedulerAgenda()
    shown = dt.date.fromisoformat(state.date)
    events = [e for e in month_events()
              if CALENDAR_OF.get(e["id"].split("+")[0], "school") in state.calendars]
    with ui.hstack(justify="between", align="center", wrap=True, gap="md"):
        ui.heading(f"{shown:%B %Y}", level=3)
        with ui.hstack(gap="xs", align="center"):
            ui.icon_button("chevron-left", variant="ghost", tooltip="Previous",
                           on_click=agenda_previous)
            ui.button("Today", variant="outline", size="sm", on_click=agenda_today)
            ui.icon_button("chevron-right", variant="ghost", tooltip="Next",
                           on_click=agenda_next)
    with ui.hstack(justify="between", align="center", wrap=True, gap="md"):
        ui.toggle_group(value=state.view, options=[(v, v) for v in VIEWS],
                        size="sm", on_change=agenda_changed)
        ui.toggle_group(value=state.calendars, options=CALENDARS, multiple=True,
                        size="sm", on_change=agenda_changed)
    ui.scheduler(events=events, date=shown, view=state.view, on_item_click=select_event)


def page() -> None:
    with ui.container(), ui.vstack(gap="lg"):
        ui.heading("Scheduler", level=1)
        ui.text(
            "Events posed on a grid of time, to the minute — day, 3 days, week, "
            "month. The app writes the loop (ui.scheduler_item) and what each card "
            "shows; the scheduler places them and carries the gesture. The real "
            "test bench is the Server playground card; the live week is under "
            "Server events.",
            color="muted",
        )

        with ui.card(), ui.vstack():
            ui.heading("Reference", level=2)
            ui.text("Visual scan of every prop. A week of lessons: 55 minutes, "
                    "starting at 8:05 or on a quarter hour; two that overlap on "
                    "Wednesday; holidays across Thursday and Friday; a meeting from "
                    "17:00 to 20:00.", color="muted", size="sm")
            ui.heading('view="week" (default)', level=3)
            ui.scheduler(events=week_events(), date=MONDAY)
            ui.heading('view="3days" — date and the two days after it', level=3)
            ui.scheduler(events=week_events(), date=TUESDAY, view="3days")
            ui.heading('view="day" — the phone', level=3)
            ui.scheduler(events=week_events(), date=TUESDAY, view="day")
            ui.heading('view="month" — chips in their day, bars across the week',
                       level=3)
            ui.scheduler(events=month_events(), date=MONDAY, view="month")
            ui.heading("week_start=0 — the week starts on Sunday", level=3)
            ui.scheduler(events=week_events(), date=MONDAY, week_start=0, weekend=True)
            ui.heading("hours=(10, 16)", level=3)
            ui.scheduler(events=week_events(), date=MONDAY, hours=(10, 16))
            ui.heading("weekend=True / weekend=False", level=3)
            with ui.grid(cols={"base": 1, "lg": 2}, gap="md"):
                ui.scheduler(events=week_events(), date=MONDAY, hours=(8, 11), weekend=True)
                ui.scheduler(events=[lesson(5, "09:00", 60, "Open day", "Hall", "green")],
                             date=MONDAY, hours=(8, 11), weekend=False)
            ui.heading("weekday_names= (rendered by the server)", level=3)
            ui.scheduler(events=week_events(), date=MONDAY, hours=(8, 11),
                         weekday_names=FRENCH_DAYS)
            ui.heading("color= of an item — any palette name", level=3)
            # One colour per slot, spread over the week: none overlaps, so
            # each card takes its column's width and the colours compare.
            with ui.scheduler(date=MONDAY, hours=(8, 11)):
                for index, color in enumerate(COLORS):
                    start = at(index % 5, "08:00") + dt.timedelta(hours=index // 5)
                    ui.scheduler_item(key=f"color-{color}", title=color, color=color,
                                      start=start, end=start + dt.timedelta(minutes=55))
            ui.heading("subtitle= / all_day= / editable=False / snap=15", level=3)
            with ui.scheduler(date=MONDAY, hours=(8, 12), snap=15, on_move=log_only_move):
                ui.scheduler_item(key="sub", title="4e2", subtitle="C209",
                                  start=at(0, "08:05"), end=at(0, "09:00"), color="violet")
                ui.scheduler_item(key="fixed", title="Assembly (still)", subtitle="Hall",
                                  start=at(1, "09:00"), end=at(1, "10:00"), color="slate",
                                  editable=False)
                ui.scheduler_item(key="trip", title="School trip", all_day=True,
                                  start=MONDAY + dt.timedelta(days=2),
                                  end=MONDAY + dt.timedelta(days=4), color="sky")

        with ui.card(), ui.vstack():
            ui.heading("Edge cases", level=2)
            ui.heading("No event — the grid still shows 8:00 to 18:00", level=3)
            ui.scheduler(events=[], date=MONDAY, hours=(8, 10))
            ui.heading("Five at once — five lanes, none spills out", level=3)
            ui.scheduler(
                events=[lesson(0, "09:00", 90, "Council", "B12", "sky"),
                        lesson(0, "09:15", 60, "4e2", "C209", "violet"),
                        lesson(0, "09:30", 55, "Phone call", "", "amber"),
                        lesson(0, "09:45", 30, "Parent", "", "pink"),
                        lesson(0, "10:00", 45, "Visit", "", "teal")],
                date=MONDAY, view="day", hours=(8, 12),
            )
            ui.heading("A very long title, and HTML in it", level=3)
            ui.scheduler(
                events=[lesson(0, "09:00", 55, "Conseil pédagogique extraordinaire de fin "
                               "de trimestre avec la direction", "Salle polyvalente", "indigo"),
                        lesson(1, "09:00", 55, "<b>4e2</b> & <script>x</script>", "C209",
                               "pink")],
                date=MONDAY, hours=(8, 11),
            )
            ui.heading("A Saturday event — the weekend appears", level=3)
            ui.scheduler(events=[lesson(5, "09:00", 120, "Open day", "Hall", "green")],
                         date=MONDAY, hours=(8, 12))
            ui.heading("Early and late — the grid grows to 7:00 and 21:00", level=3)
            ui.scheduler(events=[lesson(0, "07:30", 30, "Duty", "Gate", "teal"),
                                 lesson(0, "20:00", 45, "Concert", "", "purple")],
                         date=MONDAY, view="day")
            ui.heading("Past midnight — one card per day, shown, not dragged", level=3)
            ui.scheduler(events=[lesson(0, "22:00", 240, "Night shift", "Lab", "indigo")],
                         date=MONDAY, hours=(0, 24), view="3days", on_move=log_only_move)
            ui.heading("hours=(9, 12) — clipped to the grid, the 8:00 one not drawn, a "
                       "5-minute one still visible", level=3)
            ui.scheduler(events=[lesson(0, "08:00", 30, "Too early", "", "slate"),
                                 lesson(0, "08:30", 90, "Clipped", "C209", "amber"),
                                 lesson(0, "10:30", 5, "5 minutes", "", "pink")],
                         date=MONDAY, view="day", hours=(9, 12))
            ui.heading("A busy month day — three chips, then +N", level=3)
            ui.scheduler(events=[lesson(0, f"{8 + h:02d}:00", 50, f"Lesson {h + 1}", "",
                                        COLORS[h]) for h in range(6)],
                         date=MONDAY, view="month")

        with ui.card(), ui.vstack():
            ui.heading("Composability", level=2)
            ui.heading("Cards drawn by the app — the loop and the content are yours",
                       level=3)
            ui.text("Each ui.scheduler_item says when; its children say what the card "
                    "shows. title= is what a screen reader announces with the day and "
                    "the hours.", color="muted", size="sm")
            with ui.scheduler(date=MONDAY, hours=(8, 12), on_item_click=select_event):
                for day, hhmm, minutes, title, room, color, _ in LESSONS[:3]:
                    start = at(day, hhmm)
                    with ui.scheduler_item(key=f"rich-{title}-{hhmm}", title=title,
                                           start=start,
                                           end=start + dt.timedelta(minutes=minutes),
                                           color=color), ui.vstack(gap="xs"):
                        with ui.hstack(gap="xs", align="center"):
                            ui.icon("users", size="xs")
                            ui.text(title, weight="bold", size="sm")
                        ui.badge(room, size="xs", color="gray")
                with ui.scheduler_item(key="rich-trip", title="School trip", all_day=True,
                                       start=MONDAY + dt.timedelta(days=2),
                                       end=MONDAY + dt.timedelta(days=4), color="sky"), \
                        ui.hstack(gap="xs", align="center"):
                    ui.icon("bus", size="xs")
                    ui.text("School trip", weight="semibold", size="sm")
            ui.heading("A whole agenda, assembled around it", level=3)
            ui.text("Navigation, the view, the calendars: ui.button, ui.toggle_group — "
                    "the app passes the scheduler only the events of the ticked "
                    "calendars.", color="muted", size="sm")
            agenda()

        with ui.card(), ui.vstack():
            ui.heading("A11y", level=2)
            ui.text("Every card is focusable, in the order of the days then the hours; "
                    "Enter selects it. Its accessible name says the title, the place, "
                    "the day and the hours: « 4e2, C209, 2026-10-19, 08:05 – 09:00 ». "
                    "Tab onto a card below and press Enter: the Server events log "
                    "gains a line.", color="muted", size="sm")
            ui.scheduler(events=[lesson(0, "08:05", 55, "4e2", "C209", "violet"),
                                 lesson(1, "09:00", 55, "3e1", "C209", "amber")],
                         date=MONDAY, hours=(8, 11), on_item_click=select_event)

        with ui.card(), ui.vstack():
            ui.heading("Server playground", level=2)
            ui.text("The real test bench: every prop and every escape hatch wired to a "
                    "control; the preview and the emitted HTML refresh on every change.",
                    color="muted", size="sm")
            server_panel()

        with ui.card(), ui.vstack():
            ui.heading("Server events", level=2)
            ui.text("Drag a card, pull its bottom edge, click it, or trace a new event "
                    "on the empty grid. Past 18:00 the server "
                    "refuses by changing nothing: the card goes back. A lesson repeats, "
                    "so the server asks first — the card waits at its new place, and "
                    "goes back on Cancel.", color="muted", size="sm")
            with ui.hstack(justify="end"):
                ui.button("Reset the week", variant="ghost", size="sm", on_click=reset_week)
            live_week()
            question_dialog()
            ui.divider()
            events_log()

        with ui.card(), ui.vstack():
            ui.heading("Client events", level=2)
            ui.text("on_item_click, on_move and on_resize wired to client expressions. Zero "
                    "network: nobody moves the card for real, so it goes back.",
                    color="muted", size="sm")
            client_log = SchedulerClientEvents()
            client_week = ui.scheduler(
                events=[lesson(0, "09:00", 55, "4e2", "C209", "violet"),
                        lesson(1, "10:15", 55, "3e1", "C209", "amber")],
                date=MONDAY, hours=(8, 13),
                on_item_click=client_log.log.push(ClientExpression("'select ' + $el.dataset.bzEvent")),
                on_move=client_log.log.push(ClientExpression("'move ' + $event.target.value")),
                on_resize=client_log.log.push(ClientExpression("'resize ' + $event.target.value")),
            )
            ui.text(
                ClientExpression(
                    "($bz.state.SchedulerClientEvents.default.log"
                    " || []).join(String.fromCharCode(10)) || '(no events yet)'"
                ),
                color="muted", size="sm", classes="font-mono whitespace-pre",
            )
            ui.divider()
            emitted_html_block("Emitted HTML — the client expressions sit on the "
                               "cards and on the hidden carriers.",
                               serialize_html(client_week))
