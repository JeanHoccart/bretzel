"""``Scheduler`` — le placement à la minute, les couloirs, la rangée
journée entière, les refus, et le contrat DOM que les gestes liront."""

from __future__ import annotations

import datetime as dt
import re

import pytest

from bretzel.components.base import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.data.scheduler import SCHEDULER_THEME, Scheduler
from bretzel.components.data.scheduler.scheduler import ALL_DAY_ROW, GAP, PX_PER_MINUTE
from bretzel.core.tree import Element

MONDAY = dt.date(2026, 11, 9)


def _walk(node: object):
    if isinstance(node, Element):
        yield node
        for child in node.children:
            yield from _walk(child)


def _render(**kwargs) -> Element:
    with render_isolated():
        return Scheduler(**kwargs).render()


def _event(eid: str, day: int, start: str, minutes: int, **extra) -> dict:
    begin = dt.datetime.combine(MONDAY + dt.timedelta(days=day), dt.time.fromisoformat(start))
    return {"id": eid, "title": eid, "start": begin,
            "end": begin + dt.timedelta(minutes=minutes), **extra}


def _cards(root: Element) -> dict[str, Element]:
    return {e.attrs["data-bz-event"]: e for e in _walk(root)
            if "data-bz-event" in e.attrs and "data-bz-start" in e.attrs}


def _style(el: Element, prop: str) -> str:
    match = re.search(rf"(?:^|;){prop}:([^;]+)", el.attrs["style"])
    assert match, (prop, el.attrs["style"])
    return match.group(1)


def _days(root: Element) -> list[str]:
    return [e.attrs["data-bz-day"] for e in _walk(root) if "data-bz-day" in e.attrs]


# ── Placement ──────────────────────────────────────────────────────────


def test_a_card_starts_at_its_real_minute() -> None:
    root = _render(events=[_event("a", 0, "08:05", 55)], date=MONDAY)
    card = _cards(root)["a"]
    assert _style(card, "top") == f"{5 * PX_PER_MINUTE + GAP / 2:.0f}px"
    assert _style(card, "height") == f"{55 * PX_PER_MINUTE - GAP:.0f}px"
    assert card.attrs["data-bz-start"] == str(8 * 60 + 5)
    assert card.attrs["data-bz-duration"] == "55"


def test_the_grid_grows_to_fit_the_events() -> None:
    root = _render(events=[_event("early", 0, "07:30", 30), _event("late", 0, "20:00", 45)],
                   date=MONDAY)
    hours = [e for e in _walk(root) if e.attrs.get("class") == SCHEDULER_THEME["slots"]["hour"]]
    labels = [h.children[0].content for h in hours]
    assert labels[0] == "7:00" and labels[-1] == "21:00"


def test_hours_fix_the_grid() -> None:
    root = _render(events=[], date=MONDAY, hours=(9, 12))
    column = next(e for e in _walk(root) if "data-bz-day" in e.attrs)
    assert column.attrs["style"] == f"height:{round(3 * 60 * PX_PER_MINUTE)}px"


# ── Chevauchements ─────────────────────────────────────────────────────


def test_overlapping_events_share_the_column_in_lanes() -> None:
    root = _render(events=[_event("a", 0, "09:00", 55), _event("b", 0, "09:30", 55),
                           _event("c", 0, "10:15", 55)], date=MONDAY)
    cards = _cards(root)
    # a and c take lane 0 (a has ended when c starts), b lane 1: two lanes.
    assert _style(cards["a"], "inset-inline-start") == _style(cards["c"], "inset-inline-start")
    assert _style(cards["b"], "inset-inline-start") != _style(cards["a"], "inset-inline-start")
    for card in cards.values():
        assert _style(card, "width") == f"calc((100% - {GAP}px) / 2 - {GAP}px)"


def test_a_lone_event_takes_the_whole_column() -> None:
    card = _cards(_render(events=[_event("a", 0, "09:00", 55)], date=MONDAY))["a"]
    assert _style(card, "width") == f"calc((100% - {GAP}px) / 1 - {GAP}px)"


# ── Journée entière ────────────────────────────────────────────────────


def test_a_multi_day_event_is_one_bar_across_its_days() -> None:
    root = _render(events=[{"id": "hol", "title": "Holidays", "all_day": True,
                            "start": MONDAY + dt.timedelta(days=3),
                            "end": MONDAY + dt.timedelta(days=5)}], date=MONDAY)
    bars = [e for e in _walk(root) if e.attrs.get("data-bz-event") == "hol"]
    assert len(bars) == 1
    assert _style(bars[0], "inset-inline-start") == f"calc(3 * 100% / 5 + {GAP}px)"
    assert _style(bars[0], "width") == f"calc(2 * 100% / 5 - {2 * GAP}px)"


def test_overlapping_all_day_events_stack_on_rows() -> None:
    root = _render(events=[
        {"id": "a", "title": "A", "all_day": True, "start": MONDAY,
         "end": MONDAY + dt.timedelta(days=3)},
        {"id": "b", "title": "B", "all_day": True, "start": MONDAY + dt.timedelta(days=1)},
    ], date=MONDAY)
    b = next(e for e in _walk(root) if e.attrs.get("data-bz-event") == "b")
    assert _style(b, "top") == f"{ALL_DAY_ROW}px"


# ── Vues et week-end ───────────────────────────────────────────────────


def test_the_week_hides_an_empty_weekend() -> None:
    assert len(_days(_render(events=[], date=MONDAY))) == 5


def test_a_saturday_event_shows_the_weekend_day() -> None:
    days = _days(_render(events=[_event("s", 5, "09:00", 60)], date=MONDAY))
    assert days[-1] == (MONDAY + dt.timedelta(days=5)).isoformat()
    assert len(days) == 6


def test_holidays_running_through_the_weekend_do_not_show_it() -> None:
    days = _days(_render(events=[{"id": "h", "title": "H", "all_day": True,
                                  "start": MONDAY + dt.timedelta(days=4),
                                  "end": MONDAY + dt.timedelta(days=9)}], date=MONDAY))
    assert len(days) == 5


@pytest.mark.parametrize(("weekend", "count"), [(True, 7), (False, 5)])
def test_weekend_forces_the_choice(weekend: bool, count: int) -> None:
    events = [_event("s", 5, "09:00", 60)]
    assert len(_days(_render(events=events, date=MONDAY, weekend=weekend))) == count


def test_the_day_view_shows_one_column() -> None:
    root = _render(events=[_event("a", 1, "09:00", 55)], date=MONDAY + dt.timedelta(days=1),
                   view="day")
    assert _days(root) == [(MONDAY + dt.timedelta(days=1)).isoformat()]
    assert root.attrs["data-bz-view"] == "day"


# ── Couleur, accessibilité, identité ───────────────────────────────────


def test_a_card_carries_its_colour_bridge_and_no_border() -> None:
    card = _cards(_render(events=[_event("a", 0, "09:00", 55, color="violet")],
                          date=MONDAY))["a"]
    classes = card.attrs["class"].split()
    assert "bz-c-violet" in classes and "bg-(--bz-bg)" in classes
    assert not any(c.startswith(("border-s", "border-l")) for c in classes)


def test_a_card_is_focusable_and_says_what_and_when() -> None:
    card = _cards(_render(events=[_event("a", 0, "08:05", 55, subtitle="C209")],
                          date=MONDAY))["a"]
    assert card.attrs["tabindex"] == "0"
    assert card.attrs["aria-label"] == "a, C209, 2026-11-09, 8:05 – 9:00"


def test_a_card_id_holds_no_colon() -> None:
    root = _render(events=[_event("12:2026-11-09", 0, "09:00", 55)], date=MONDAY,
                   id="week")
    card = _cards(root)["12:2026-11-09"]
    assert card.attrs["id"].startswith("week__ev_12-2026-11-09-")
    assert ":" not in card.attrs["id"]


def test_weekday_names_render_on_the_server() -> None:
    names = ["dim", "lun", "mar", "mer", "jeu", "ven", "sam"]
    root = _render(events=[], date=MONDAY, weekday_names=names)
    # No DAY is rewritten by the browser (the hours are, by the clock).
    assert not any("$bz.locale" in e.attrs.get("bz-text", "") for e in _walk(root))
    texts = [c.content for e in _walk(root) for c in e.children if hasattr(c, "content")]
    assert texts[:2] == ["lun", "9"]


def test_by_default_the_browser_names_the_days() -> None:
    root = _render(events=[], date=MONDAY)
    names = [e.attrs["bz-text"] for e in _walk(root) if "bz-text" in e.attrs]
    assert names[0] == "$bz.locale.weekdayLongNames()[1].slice(0, 3)"


# ── Refus ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("kwargs", [
    {"view": "year"},
    {"hours": (18, 8)},
    {"weekday_names": ["a", "b"]},
    {"events": [{"title": "no id", "start": "2026-11-09T09:00", "end": "2026-11-09T10:00"}]},
    {"events": [{"id": "x", "start": "2026-11-09T10:00", "end": "2026-11-09T09:00"}]},
    {"events": [{"id": "x", "start": "tomorrow", "end": "2026-11-09T09:00"}]},
])
def test_refuses_what_it_cannot_draw(kwargs: dict) -> None:
    with render_isolated(), pytest.raises(ComponentUsageError):
        Scheduler(**kwargs).render()


# ── Gestes : le contrat que scheduler.js lit ────────────────────────


def moved(r) -> None:
    """Un handler de module : l'enregistrement d'action refuse les lambdas."""


def picked(event_id: str) -> None:
    """Idem, pour on_item_click."""


def test_without_handlers_nothing_is_draggable() -> None:
    root = _render(events=[_event("a", 0, "09:00", 55)], date=MONDAY)
    card = _cards(root)["a"]
    assert "data-bz-movable" not in card.attrs and "role" not in card.attrs
    assert not any("data-bz-scheduler-carrier" in e.attrs for e in _walk(root))


def test_the_root_says_how_to_turn_a_pointer_into_a_minute() -> None:
    root = _render(events=[], date=MONDAY, hours=(8, 12), snap=15, on_move=moved)
    assert (root.attrs["data-bz-grid-start"], root.attrs["data-bz-grid-end"]) == ("480", "720")
    assert root.attrs["data-bz-px"] == str(PX_PER_MINUTE)
    assert root.attrs["data-bz-snap"] == "15"


def test_on_move_makes_cards_movable_and_posts_from_a_named_carrier() -> None:
    root = _render(events=[_event("a", 0, "09:00", 55),
                           _event("fixed", 0, "11:00", 55, editable=False)],
                   date=MONDAY, on_move=moved, on_resize=moved)
    cards = _cards(root)
    assert "data-bz-movable" in cards["a"].attrs
    assert "data-bz-movable" not in cards["fixed"].attrs
    edges = [e for e in _walk(cards["a"]) if "data-bz-resize" in e.attrs]
    assert len(edges) == 1
    assert not any("data-bz-resize" in e.attrs for e in _walk(cards["fixed"]))
    carriers = {e.attrs["data-bz-scheduler-carrier"]: e for e in _walk(root)
                if "data-bz-scheduler-carrier" in e.attrs}
    assert set(carriers) == {"move", "resize"}
    for event, carrier in carriers.items():
        assert carrier.attrs["name"] == "bz_reschedule"
        assert carrier.attrs["hx-trigger"] == event
        assert "hx-post" in carrier.attrs


def test_a_client_handler_leaves_the_carrier_unnamed() -> None:
    root = _render(events=[_event("a", 0, "09:00", 55)], date=MONDAY,
                   on_move="console.log($event.target.value)")
    carrier = next(e for e in _walk(root) if "data-bz-scheduler-carrier" in e.attrs)
    assert "name" not in carrier.attrs and "hx-post" not in carrier.attrs
    assert carrier.attrs["bz-on:move"] == "console.log($event.target.value)"


def test_on_item_click_posts_from_each_card_but_not_from_its_edge() -> None:
    card = _cards(_render(events=[_event("a", 0, "09:00", 55)], date=MONDAY,
                          on_item_click=picked))["a"]
    assert card.attrs["role"] == "button" and "hx-post" in card.attrs
    assert card.attrs["hx-trigger"].startswith("click[")
    assert "data-bz-resize" in card.attrs["hx-trigger"]
    assert "bz-on:keydown" in card.attrs


def test_reschedule_reads_the_wire() -> None:
    from bretzel.components import Reschedule

    r = Reschedule.from_wire(
        '{"event_id": "12:2026-11-10", "start": "2026-11-12T08:05", "end": "2026-11-12T09:00"}')
    assert r.event_id == "12:2026-11-10"
    assert r.start == dt.datetime(2026, 11, 12, 8, 5)
    assert r.end == dt.datetime(2026, 11, 12, 9, 0)


def test_snap_is_bounded() -> None:
    with render_isolated(), pytest.raises(ComponentUsageError):
        Scheduler(snap=0)


# ── Items : la boucle et le contenu sont à l'app ───────────────────────

from bretzel import ui  # noqa: E402
from bretzel.components.data.scheduler import SchedulerItem  # noqa: E402


def _render_with(build, **kwargs) -> Element:
    with render_isolated():
        scheduler = Scheduler(date=MONDAY, **kwargs)
        with scheduler:
            build()
        return scheduler.render()


def _at(day: int, hhmm: str) -> dt.datetime:
    return dt.datetime.combine(MONDAY + dt.timedelta(days=day), dt.time.fromisoformat(hhmm))


def test_an_item_draws_its_children_in_its_card() -> None:
    def build() -> None:
        with ui.scheduler_item(key="a", title="4e2", start=_at(0, "08:05"), end=_at(0, "09:00")):
            ui.badge("C209")

    card = _cards(_render_with(build))["a"]
    assert card.attrs["aria-label"].startswith("4e2, 2026-11-09, 8:05")
    assert any("C209" in getattr(c, "content", "") for e in _walk(card) for c in e.children)


def test_the_shortcut_materialises_the_same_items() -> None:
    with render_isolated():
        scheduler = Scheduler(events=[_event("a", 0, "09:00", 55)], date=MONDAY)
    assert [type(c) for c in scheduler._children] == [SchedulerItem]


@pytest.mark.parametrize("build", [
    lambda: ui.scheduler_item(title="no key", start=_at(0, "09:00"), end=_at(0, "10:00")),
    lambda: (ui.scheduler_item(key="x", start=_at(0, "09:00"), end=_at(0, "10:00")),
             ui.scheduler_item(key="x", start=_at(1, "09:00"), end=_at(1, "10:00"))),
    lambda: ui.text("not an item"),
])
def test_refuses_what_it_cannot_place(build) -> None:
    with pytest.raises(ComponentUsageError):
        _render_with(build)


@pytest.mark.parametrize("kwargs", [
    {"end": _at(0, "10:00")},                                  # no start
    {"start": _at(0, "09:00")},                                # no end, not all-day
    {"start": _at(0, "09:00"), "end": _at(0, "09:00")},        # zero length
    {"start": _at(0, "09:00").replace(tzinfo=dt.UTC), "end": _at(0, "10:00")},
])
def test_an_item_refuses_missing_or_wrong_times(kwargs: dict) -> None:
    with pytest.raises(ComponentUsageError):
        _render_with(lambda: SchedulerItem(key="x", **kwargs))


def test_an_event_past_midnight_is_one_card_per_day_and_stays_still() -> None:
    def build() -> None:
        ui.scheduler_item(key="night", title="Night", start=_at(0, "22:00"), end=_at(1, "02:00"))

    root = _render_with(build, hours=(0, 24), on_move=moved)
    pieces = [e for e in _walk(root) if e.attrs.get("data-bz-event") == "night"]
    assert [p.attrs["data-bz-duration"] for p in pieces] == ["120", "120"]
    assert not any("data-bz-movable" in p.attrs for p in pieces)


def test_a_fixed_grid_clips_and_drops_what_falls_outside() -> None:
    def build() -> None:
        ui.scheduler_item(key="early", title="early", start=_at(0, "08:00"), end=_at(0, "08:30"))
        ui.scheduler_item(key="clipped", title="clipped", start=_at(0, "08:30"), end=_at(0, "10:00"))

    cards = _cards(_render_with(build, hours=(9, 12), on_move=moved))
    assert "early" not in cards
    assert _style(cards["clipped"], "top") == f"{GAP / 2:.0f}px"
    assert "data-bz-movable" not in cards["clipped"].attrs


def test_a_five_minute_event_keeps_a_visible_card() -> None:
    card = _cards(_render(events=[_event("tiny", 0, "09:00", 5)], date=MONDAY))["tiny"]
    assert _style(card, "height") == "18px"


# ── Vues : 3 jours et mois ─────────────────────────────────────────────


def test_three_days_start_at_the_date() -> None:
    root = _render(events=[], date=MONDAY + dt.timedelta(days=4), view="3days")
    assert _days(root) == [(MONDAY + dt.timedelta(days=d)).isoformat() for d in (4, 5, 6)]


def test_the_month_covers_its_weeks_and_hides_an_empty_weekend() -> None:
    root = _render(events=[], date=MONDAY, view="month")      # 2026-11
    days = _days(root)
    assert days[0] == "2026-10-26" and days[-1] == "2026-12-04"   # Mon .. Fri
    assert len(days) == 6 * 5


def test_a_month_chip_carries_its_time_and_moves_by_day() -> None:
    root = _render(events=[_event("a", 1, "08:05", 55, color="violet")], date=MONDAY,
                   view="month", on_move=moved)
    chip = next(e for e in _walk(root) if e.attrs.get("data-bz-event") == "a")
    assert chip.attrs["data-bz-start"] == "485" and chip.attrs["data-bz-duration"] == "55"
    assert "data-bz-movable" in chip.attrs
    assert not any("data-bz-resize" in e.attrs for e in _walk(root))
    assert chip.attrs["aria-label"].endswith("8:05 – 9:00")


def test_a_busy_month_day_says_how_many_more() -> None:
    events = [_event(f"e{h}", 0, f"{8 + h:02d}:00", 50) for h in range(5)]
    root = _render(events=events, date=MONDAY, view="month")
    texts = [c.content for e in _walk(root) for c in e.children if hasattr(c, "content")]
    assert "+2" in texts
    assert sum(1 for e in _walk(root) if e.attrs.get("data-bz-event", "").startswith("e")) == 3


def test_a_month_all_day_event_is_one_bar_per_week() -> None:
    root = _render(events=[{"id": "h", "title": "H", "all_day": True,
                            "start": MONDAY + dt.timedelta(days=3),
                            "end": MONDAY + dt.timedelta(days=12)}], date=MONDAY, view="month")
    bars = [e for e in _walk(root) if e.attrs.get("data-bz-event") == "h"]
    assert len(bars) == 2          # Thu-Fri of this week, Mon-Thu of the next


def test_a_short_card_is_one_compact_line_with_the_full_text_on_hover() -> None:
    cards = _cards(_render(events=[_event("short", 0, "09:00", 25, subtitle="C209"),
                                   _event("long", 1, "09:00", 55)], date=MONDAY))
    assert "data-compact" in cards["short"].attrs
    # The full text in the page's shared tooltip, not the browser's
    # ``title`` bubble (2026-10-27).
    assert "title" not in cards["short"].attrs
    assert cards["short"].attrs["data-bz-tip"] == cards["short"].attrs["aria-label"]
    assert "data-bz-tip-root" in cards["short"].attrs
    assert "data-compact" not in cards["long"].attrs
    texts = [c.content for e in _walk(cards["short"]) for c in e.children if hasattr(c, "content")]
    assert texts == ["short", "9:00"]


# ── Only today is marked (Jean, 2026-10-26: « seul le jour actuel est
# marqué, partout ») — the day of ``date=`` wore a soft mark for a day ──

TODAY = SCHEDULER_THEME["slots"]["today"]


def _numbers(root: Element) -> dict[str, str]:
    """The day numbers shown, by their text: their classes."""
    return {e.children[0].content: e.attrs.get("class", "") for e in _walk(root)
            if len(e.children) == 1 and str(getattr(e.children[0], "content", "")).isdigit()
            and "rounded-full" in e.attrs.get("class", "")}


@pytest.mark.parametrize("view", ["day", "3days", "week", "month"])
def test_the_chosen_day_wears_no_mark(view) -> None:
    """A day is chosen that is not today, nor in today's month grid: no
    number is marked.

    It was 11 November 2026, until today WAS in its month grid — the
    grid opens on Monday 26 October, and the 28th came (2026-10-28): the
    test went red on a component doing right. 120 days ahead, no grid of
    six weeks reaches back to today."""
    numbers = _numbers(_render(date=dt.date.today() + dt.timedelta(days=120), view=view))
    plain = SCHEDULER_THEME["slots"]["month_number" if view == "month" else "day_number"]
    assert all(c.split() == plain.split() or "text-text/" in c for c in numbers.values()), numbers


class _Wednesday(dt.date):
    @classmethod
    def today(cls) -> dt.date:
        return dt.date(2026, 11, 11)


@pytest.mark.parametrize("view", ["day", "3days", "week", "month"])
def test_today_is_the_one_marked_day(view, monkeypatch) -> None:
    """Today is a Wednesday mid-month, fixed: the week shows Monday to
    Friday, so a real today went red every weekend (Sunday 2026-11-01,
    the grid of Monday 26 October to Friday 30 had no today to mark)."""
    from bretzel.components.data.scheduler import scheduler as module

    monkeypatch.setattr(module, "date_type", _Wednesday)
    today = _Wednesday.today()
    # Another day of the same week, so the chosen day and today differ.
    neighbour = today + dt.timedelta(days=1)
    chosen = neighbour if view in ("week", "month") else today
    numbers = _numbers(_render(date=chosen, view=view))
    assert [n for n, c in numbers.items() if TODAY in c] == [str(today.day)], numbers


# ── Room to pull (a 17:00-20:00 meeting could not be lengthened) ──


def _grid_end(root: Element) -> int:
    return int(next(e.attrs["data-bz-grid-end"] for e in _walk(root) if "data-bz-grid-end" in e.attrs))


def test_a_grown_grid_keeps_an_hour_to_pull_when_cards_move() -> None:
    late = [_event("meeting", 3, "17:00", 180)]
    assert _grid_end(_render(events=late, date=MONDAY, on_resize="noop()")) == 21 * 60


def test_a_card_ending_at_the_default_end_can_still_grow() -> None:
    lesson = [_event("4e2", 0, "17:05", 55)]
    assert _grid_end(_render(events=lesson, date=MONDAY, on_resize="noop()")) == 19 * 60


# ── Hours in the page's language (Jean, 2026-10-25: « 8h », not « 8:00 ») ──


def test_clock_writes_french_hours_the_french_way() -> None:
    from bretzel.components.data.scheduler.scheduler import clock

    assert [clock(m, "fr") for m in (480, 485, 610, 0)] == ["8h", "8h05", "10h10", "0h"]
    assert [clock(m, "fr-CA") for m in (480,)] == ["8h"]
    assert [clock(m, "en") for m in (480, 485)] == ["8:00", "8:05"]


def test_a_french_page_gets_french_hours_and_tells_the_runtime() -> None:
    with render_isolated() as ctx:
        ctx.lang = "fr"
        root = Scheduler(events=[_event("4e2", 0, "08:05", 55)], date=MONDAY,
                         on_move="noop()").render()
    texts = [c.content for e in _walk(root) for c in e.children if hasattr(c, "content")]
    assert "8h" in texts and "8:00" not in texts
    # The browser rewrites each hour with THE clock, the time picker's.
    hours = [e.attrs["bz-text"] for e in _walk(root) if "bz-text" in getattr(e, "attrs", {})
             and "$bz.times.shown" in e.attrs["bz-text"]]
    assert "$bz.times.shown('08:00', true)" in hours
    card = _cards(root)["4e2"]
    assert "8h05 – 9h" in card.attrs["aria-label"]


# ── on_create (Jean, 2026-10-25: a new event traced on the empty grid) ──


def _carriers(root: Element) -> list[str]:
    return [e.attrs["data-bz-scheduler-carrier"] for e in _walk(root)
            if "data-bz-scheduler-carrier" in e.attrs]


def test_on_create_alone_wires_the_grid_a_carrier_and_a_draft() -> None:
    root = _render(events=[], date=MONDAY, on_create="noop()")
    assert _carriers(root) == ["create"]
    assert "data-bz-scheduler" in root.attrs and "data-bz-grid-start" in root.attrs
    drafts = [e for e in _walk(root) if "data-bz-scheduler-draft" in e.attrs]
    assert len(drafts) == 1 and "hidden" in drafts[0].attrs


def test_the_month_view_creates_nothing() -> None:
    root = _render(events=[], date=MONDAY, view="month", on_create="noop()")
    assert _carriers(root) == []
    assert not [e for e in _walk(root) if "data-bz-scheduler-draft" in e.attrs]
