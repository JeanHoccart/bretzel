"""``DatePicker`` test-bench state classes + axis constants."""

from __future__ import annotations

from bretzel.state import ClientState, PageState, field


# Axis constants — used both for the Reference card and the Server
# playground select options. Keep in one place so a new color / size
# palier auto-propagates everywhere.
COLORS = (
    "primary", "secondary", "success", "warning", "error", "info", "muted",
)
SIZES = ("xs", "sm", "md", "lg", "xl")
LOCALES = ("en", "fr")

WEEKDAYS_FR = ("Di", "Lu", "Ma", "Me", "Je", "Ve", "Sa")
MONTHS_FR = (
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
)


class DatePickerPlayground(PageState):
    """Drives the Server playground card.

    One field per component prop + per universal escape hatch
    (``classes`` / ``custom_id`` / ``aria_label`` / ``style`` /
    ``extra_attrs``) + per universal modifier (``visible`` /
    ``tooltip``) + the event log used by the Server events card.
    """

    # ── Component-public props ────────────────────────────────────
    value:          str = field(default="")
    name:           str = field(default="")
    min:            str = field(default="")
    max:            str = field(default="")
    disabled_dates: str = field(default="")  # comma-separated ISO dates
    marks:          str = field(default="")  # comma-separated ISO dates
    placeholder:    str = field(default="YYYY-MM-DD")
    color:          str = field(default="primary")
    size:           str = field(default="md")
    weekstart:      int = field(default=1)
    locale:         str = field(default="en")
    clearable:      str = field(default="on")
    close_on_pick:  str = field(default="on")
    disabled:       str = field(default="off")
    required:       str = field(default="off")

    # ── Escape hatches (per playground-pattern.md § 4) ────────────
    classes:        str = field(default="")
    custom_id:      str = field(default="")
    aria_label:     str = field(default="")
    style:          str = field(default="")
    extra_attrs:    str = field(default="")

    # ── Universal modifiers ───────────────────────────────────────
    visible:        str = field(default="on")
    tooltip:        str = field(default="")

    # ── Server-events card ────────────────────────────────────────
    log:            list = field(default_factory=list)


class DatePickerClient(ClientState, persist="memory"):
    """Drives the Client playground + Client events cards."""

    picked:      str = field(default="")
    client_log:  list = field(default_factory=list)
