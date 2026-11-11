"""Server-side handlers of the Scheduler playground.

Every handler is a module-level callable — Bretzel addresses it by
``module::qualname``. They mutate state; the panels reading it redraw.
"""

import datetime as dt

from bretzel.components import Reschedule
from examples.playground.features.scheduler.state import (
    ONE_OFFS,
    TITLES,
    SchedulerAgenda,
    SchedulerEvents,
    SchedulerPlayground,
    SchedulerQuestion,
    SchedulerWeek,
)


def log(line: str) -> None:
    state = SchedulerEvents()
    state.log = [*state.log, line]


def clear_log() -> None:
    SchedulerEvents().log = []


def server_changed(state: SchedulerPlayground) -> None:
    """Typed param — the dispatcher hydrates the changed control's value."""


def apply_move(event_id: str, start: dt.datetime, end: dt.datetime) -> None:
    week = SchedulerWeek()
    week.moved = {**week.moved, event_id: [start.isoformat(), end.isoformat()]}


def select_event(event_id: str) -> None:
    log(f"select({event_id!r})")


def move_event(r: Reschedule) -> None:
    """Accept, refuse past 18:00 (change nothing), or ask first for a
    repeating lesson."""
    log(f"move({r.event_id!r}, {r.start:%a %H:%M} – {r.end:%H:%M})")
    if r.end.time() > dt.time(18, 0) or r.end.date() != r.start.date():
        log("  refused: past 18:00 — nothing changes, the card goes back")
        return
    if TITLES.get(r.event_id) not in ONE_OFFS:
        SchedulerQuestion().pending = [r.event_id, r.start.isoformat(), r.end.isoformat()]
        return
    apply_move(r.event_id, r.start, r.end)


def create_event(r: Reschedule) -> None:
    """A slot traced on the empty grid: ``event_id`` is empty."""
    log(f"create({r.start:%a %H:%M} – {r.end:%H:%M})")
    week = SchedulerWeek()
    week.created = [*week.created, [r.start.isoformat(), r.end.isoformat()]]


def resize_event(r: Reschedule) -> None:
    log(f"resize({r.event_id!r}, until {r.end:%H:%M})")
    apply_move(r.event_id, r.start, r.end)


def log_only_move(r: Reschedule) -> None:
    """A handler that accepts nothing: the card always goes back."""
    log(f"move({r.event_id!r}, {r.start:%a %H:%M}) — logged, not applied")


def move_this_one() -> None:
    question = SchedulerQuestion()
    event_id, start, end = question.pending
    apply_move(event_id, dt.datetime.fromisoformat(start), dt.datetime.fromisoformat(end))
    question.pending = []
    log("  answered: this one only")


def cancel_move() -> None:
    SchedulerQuestion().pending = []
    log("  cancelled — the card goes back")


def reset_week() -> None:
    SchedulerWeek().moved = {}
    SchedulerWeek().created = []
    SchedulerEvents().log = []


# ── The assembled agenda (Composability) ───────────────────────────────

STEP = {"day": 1, "3days": 3, "week": 7}


def agenda_step(direction: int) -> None:
    agenda = SchedulerAgenda()
    shown = dt.date.fromisoformat(agenda.date)
    if agenda.view == "month":
        month = shown.month - 1 + direction
        shown = shown.replace(year=shown.year + month // 12, month=month % 12 + 1, day=1)
    else:
        shown += dt.timedelta(days=STEP[agenda.view] * direction)
    agenda.date = shown.isoformat()


def agenda_previous() -> None:
    agenda_step(-1)


def agenda_next() -> None:
    agenda_step(1)


def agenda_today() -> None:
    SchedulerAgenda().date = dt.date.today().isoformat()


def agenda_changed(state: SchedulerAgenda) -> None:
    """Typed param — the view and the calendars come hydrated."""
