"""``week_start=`` on ``ui.scheduler``, the word ``ui.calendar`` already uses."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from bretzel.components import ui
from bretzel.components.base import ComponentUsageError
from bretzel.components.base.testing import render_isolated

WEDNESDAY = date(2026, 7, 1)


def _days(**kw):
    with render_isolated():
        with ui.scheduler(view="week", date=WEDNESDAY, **kw) as s:
            pass
        return s._days(s._placed() if hasattr(s, "_placed") else [])


def test_monday_stays_the_default() -> None:
    assert _days()[0] == date(2026, 6, 29)
    assert len(_days()) == 5


def test_a_week_can_start_on_sunday() -> None:
    days = _days(week_start=0, weekend=True)
    assert days[0] == date(2026, 6, 28) and days[-1] == date(2026, 7, 4)


def test_the_unused_weekend_stays_hidden_whatever_the_start() -> None:
    assert [d.weekday() for d in _days(week_start=0)] == [0, 1, 2, 3, 4]


def test_an_impossible_start_is_refused() -> None:
    with render_isolated(), pytest.raises(ComponentUsageError, match="week_start"):
        ui.scheduler(view="week", date=datetime(2026, 7, 1), week_start=9)
