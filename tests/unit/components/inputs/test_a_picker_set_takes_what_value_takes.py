"""``.set()`` on a picker takes what ``value=`` takes: a ``date``, a ``time``."""

from __future__ import annotations

import datetime as dt

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.date_picker.date_picker import DatePicker
from bretzel.components.inputs.date_range_picker.date_range_picker import DateRangePicker
from bretzel.components.inputs.month_picker.month_picker import MonthPicker
from bretzel.components.inputs.time_picker.time_picker import TimePicker
from bretzel.components.inputs.week_picker.week_picker import WeekPicker

_DAY = dt.date(2026, 11, 9)


@pytest.mark.parametrize(
    ("cls", "value", "expected"),
    [
        (DatePicker, _DAY, '"2026-11-09"'),
        (WeekPicker, _DAY, '"2026-11-09"'),
        (MonthPicker, _DAY, '"2026-11"'),
        (TimePicker, dt.time(9, 5), '"09:05"'),
        (DateRangePicker, (_DAY, _DAY), '["2026-11-09", "2026-11-09"]'),
        (DatePicker, "2026-11-09", '"2026-11-09"'),
    ],
)
def test_set_carries_the_iso_form(cls: type, value: object, expected: str) -> None:
    with render_isolated():
        command = cls().set(value)
    assert expected in command


def test_a_range_refuses_what_is_not_a_pair() -> None:
    with render_isolated(), pytest.raises(ComponentUsageError, match="pair"):
        DateRangePicker().set(_DAY)
