"""``DateRangePicker`` test-bench state classes + axis constants."""

from __future__ import annotations

from bretzel.state import ClientState, PageState, field


COLORS = (
    "primary", "secondary", "success", "warning", "error", "info", "muted",
)
SIZES = ("xs", "sm", "md", "lg", "xl")

WEEKDAYS_FR = ("Di", "Lu", "Ma", "Me", "Je", "Ve", "Sa")
MONTHS_FR = (
    "Janvier", 'February', "Mars", "Avril", "Mai", "Juin",
    "Juillet", 'August', "Septembre", "Octobre", "Novembre", 'December',
)


class DateRangePickerPlayground(PageState):
    """Drives the Server playground card.

    Same shape as :class:`DatePickerPlayground` but with two
    placeholders (start / end) and a separator field.
    """

    # ── Component-public props ────────────────────────────────────
    min:               str = field(default="")
    max:               str = field(default="")
    disabled_dates:    str = field(default="")  # comma-separated ISO dates
    marks:             str = field(default="")  # comma-separated ISO dates
    placeholder_start: str = field(default="Start")
    placeholder_end:   str = field(default="End")
    separator:         str = field(default="→")
    color:             str = field(default="primary")
    size:              str = field(default="md")
    weekstart:         int = field(default=1)
    locale:            str = field(default="en")
    clearable:         str = field(default="on")
    close_on_close:    str = field(default="on")
    disabled:          str = field(default="off")
    required:          str = field(default="off")

    # ── Escape hatches (per playground-pattern.md § 4) ────────────
    classes:           str = field(default="")
    custom_id:         str = field(default="")
    aria_label:        str = field(default="")
    style:             str = field(default="")
    extra_attrs:       str = field(default="")

    # ── Universal modifiers ───────────────────────────────────────
    visible:           str = field(default="on")
    tooltip:           str = field(default="")

    # ── Server-events card ────────────────────────────────────────
    log:               list = field(default_factory=list)


class DateRangePickerClient(ClientState, persist="memory"):
    """Drives the Client playground + Client events cards."""

    picked_range:  list = field(default_factory=list)
    client_log:    list = field(default_factory=list)
