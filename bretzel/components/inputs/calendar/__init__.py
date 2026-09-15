"""Re-export the :class:`Calendar` component and its helpers."""

from bretzel.components.inputs.calendar.calendar import (
    DEFAULT_MONTH_NAMES,
    DEFAULT_WEEKDAY_NAMES_SUN_FIRST,
    Calendar,
    compute_month_grid,
    format_month_label,
    rotate_weekday_names,
)
from bretzel.components.inputs.calendar.theme import CALENDAR_THEME

__all__ = [
    "CALENDAR_THEME",
    "Calendar",
    "DEFAULT_MONTH_NAMES",
    "DEFAULT_WEEKDAY_NAMES_SUN_FIRST",
    "compute_month_grid",
    "format_month_label",
    "rotate_weekday_names",
]
