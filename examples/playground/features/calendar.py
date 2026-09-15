"""``Calendar`` test bench.

Eight visual cards (no slots → skip card 2) : Reference / Edge cases /
Composability / A11y / Server playground / Server events / Client
playground / Client events. Calendar's reactive surface :
``BINDABLE_PROPS = ("value", "month", "min", "max", "disabled")`` ;
``EVENTS = ("change", "month_change", "focus", "blur")`` ;
``AUTONAME_FROM = "value"``.

Two modes :
- ``picker`` (default) — single date, ``value: date | None``
- ``range`` — start + end, ``value: (date, date) | None``
"""

import datetime as dt
import functools

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/calendar"


COLORS = ("primary", "secondary", "success", "warning", "error", "info", "muted")
SIZES = ("xs", "sm", "md", "lg", "xl")

WEEKDAYS_FR = ("Di", "Lu", "Ma", "Me", "Je", "Ve", "Sa")
MONTHS_FR = (
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
)

TODAY = dt.date.today()
#: Le 1er du mois courant. Les demos de ``marks=`` s'y ancrent : la
#: grille n'affiche QUE le mois courant, donc ``TODAY + 11 jours``
#: un 25 tombe dans le mois suivant et la demo ne montre aucune
#: pastille. Tout mois a au moins 28 jours, donc ces decalages-la
#: sont toujours dedans.
MONTH_START = TODAY.replace(day=1)


class CalendarPlayground(PageState):
    mode:        str = field(default="picker")
    color:       str = field(default="primary")
    size:        str = field(default="md")
    weekstart:   int = field(default=1)
    locale:      str = field(default="en")
    disabled:    str = field(default="off")
    # Escape hatches (per playground-pattern.md § 4).
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")
    log:         list = field(default_factory=list)


class CalendarClient(ClientState, persist="memory"):
    """Drives the Client playground card. Mirrors Calendar's
    BINDABLE_PROPS = ('value', 'month', 'min', 'max', 'disabled') —
    ``picked``/``displayed_month`` back ``value``/``month``."""
    picked:           str = field(default="")
    displayed_month:  str = field(default=TODAY.replace(day=1).isoformat())
    min:              str = field(default="")
    max:              str = field(default="")
    disabled:         bool = field(default=False)
    client_log:       list = field(default_factory=list)


def log(name: str) -> None:
    state = CalendarPlayground()
    state.log = (state.log + [name])[-12:]


log_change = functools.partial(log, "change")
log_month_change = functools.partial(log, "month_change")
log_focus = functools.partial(log, "focus")
log_blur = functools.partial(log, "blur")


def clear_log() -> None:
    state = CalendarPlayground()
    state.log = []


def server_changed(state: CalendarPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    # deps=[CalendarPlayground] on server_panel re-renders automatically.
    pass


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: CalendarPlayground):
    # Calendar is a custom element : its observed attributes change
    # freely via morph + ``attributeChangedCallback`` re-renders the
    # internal grid. No more ``key=`` hack needed — the v1 runtime
    # ``bz-data`` init-once limitation is gone.
    kwargs: dict = {
        "mode": state.mode,
        "color": state.color,
        "size": state.size,
        "weekstart": state.weekstart,
    }
    if state.locale == "fr":
        kwargs["weekday_names"] = list(WEEKDAYS_FR)
        kwargs["month_names"] = list(MONTHS_FR)
    if state.disabled == "on":
        kwargs["disabled"] = True
    if state.classes:
        kwargs["classes"] = state.classes
    if state.custom_id:
        kwargs["id"] = state.custom_id
    if state.style:
        kwargs["style"] = state.style
    attrs: dict = {}
    if state.aria_label:
        attrs["aria-label"] = state.aria_label
    attrs.update(parse_extra_attrs(state.extra_attrs))
    if attrs:
        kwargs["attrs"] = attrs
    if state.tooltip:
        kwargs["tooltip"] = state.tooltip
    if state.visible == "off":
        kwargs["visible"] = False
    return ui.calendar(**kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[CalendarPlayground])
def server_panel() -> None:
    state = CalendarPlayground()
    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
        with control("mode"):
            ui.select(value=state.mode, options=[("picker", "picker"),
                                                  ("range", "range"),
                                                  ("week", "week"),
                                                  ("month", "month")],
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color, options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size (xs/sm/md/lg/xl)"):
            ui.select(value=state.size, options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("weekstart (0=Sun, 1=Mon)"):
            # ``state.weekstart`` SANS ``str()`` : la valeur porte un tampon
            # (le nom du champ) et c'est la seule chose qui atteste « le
            # serveur fait foi ». ``str()`` le déballe → pas de
            # ``_serverSync`` → le contrôle reste figé sur son ancienne
            # valeur après un refresh du panneau. Select normalise déjà en
            # chaîne pour matcher les clés d'options (mesuré : le champ vaut
            # "1" avec ou sans le ``str()``), donc il ne protégeait de rien.
            ui.select(value=state.weekstart,
                      options=[("0", "0 (Sunday)"), ("1", "1 (Monday)")],
                      on_change=server_changed)
        with control("locale (FR override)"):
            ui.select(value=state.locale,
                      options=[("en", "English (default)"),
                               ("fr", "French (custom names)")],
                      on_change=server_changed)
        with control("disabled"):
            ui.select(value=state.disabled,
                      options=[("off", "off"), ("on", "on")],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="ring-2",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-cal",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Pick a date",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="max-width: 360px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=cal",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Pick a date",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()
    with ui.flex(justify="center", align="start"):
        build_preview(state)
    ui.divider()
    emitted_html_block(
        "Emitted HTML (truncated — bz-data carries the whole picker logic)",
        serialize_html(build_preview(state)),
    )


@refreshable(deps=[CalendarPlayground])
def events_panel() -> None:
    state = CalendarPlayground()
    with ui.vstack(gap="sm"):
        with ui.hstack(gap="sm"):
            ui.button("Clear log", on_click=clear_log,
                      variant="ghost", size="sm")
        if not state.log:
            ui.text("No events yet — interact with the calendar below.",
                    color="muted", size="sm")
        else:
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"#{i}  {evt}", size="sm", color="muted")


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Calendar", level=1)
            ui.text(
                "Month-grid date picker, range picker, or read-only "
                "events view. Standalone primitive — the future "
                "``ui.date_picker`` and ``ui.date_range_picker`` "
                "wrap it in a popover. SSR renders the initial month "
                "; the runtime drives every subsequent navigation "
                "(prev / next / pick / range hover) client-side "
                "without round-trips, mirror of the Pagination "
                "pattern. ``BINDABLE_PROPS = (value, month, min, "
                "max, disabled)`` ; ``AUTONAME_FROM = value`` ; "
                "imperative API : "
                "``.set/.clear/.focus/.blur/.next_month/.prev_month``.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text(
                        "Visual scan of every prop. Each axis "
                        "demoed inline so the Tailwind dev scanner "
                        "compiles every class the Server playground "
                        "might swap to later (no need to safelist).",
                        color="muted", size="sm",
                    )

                    ui.heading("mode", level=3)
                    with ui.flex(wrap=True, gap="md", align="start"):
                        with ui.vstack(gap="xs", align="center"):
                            ui.text("picker", color="muted", size="xs")
                            ui.calendar(TODAY, size="sm")
                        with ui.vstack(gap="xs", align="center"):
                            ui.text("range", color="muted", size="xs")
                            ui.calendar(
                                (TODAY + dt.timedelta(days=2),
                                 TODAY + dt.timedelta(days=8)),
                                mode="range", size="sm",
                            )
                        with ui.vstack(gap="xs", align="center"):
                            ui.text("week", color="muted", size="xs")
                            ui.calendar(TODAY, mode="week", size="sm")
                        with ui.vstack(gap="xs", align="center"):
                            ui.text("month", color="muted", size="xs")
                            ui.calendar(f"{TODAY:%Y-%m}", mode="month",
                                        size="sm")

                    ui.text(
                        "En mode ``week``, cliquez N'IMPORTE quel jour : "
                        "c'est sa semaine entière qui se sélectionne, et "
                        "la valeur rendue est son PREMIER jour (selon "
                        "``weekstart``). Deux clics dans la même semaine "
                        "donnent donc la même valeur. Le surlignage "
                        "réutilise la bande du mode ``range`` — une "
                        "semaine EST une plage fermée de sept jours.",
                        color="muted", size="xs",
                    )

                    ui.text(
                        "Le mode ``month`` est le seul qui ne rend pas "
                        "des jours : une grille d'ANNÉE de 12 cellules, "
                        "et une valeur en \"2026-08\". Les flèches y "
                        "avancent d'un AN, et le sélecteur de mois du "
                        "header disparaît — la grille EST le sélecteur "
                        "de mois, le garder ferait deux chemins pour le "
                        "même geste.",
                        color="muted", size="xs",
                    )

                    ui.heading("month × bornes", level=3)
                    ui.text(
                        "``min`` / ``max`` sont tronqués au mois : un "
                        "``min`` au 15 mars n'interdit PAS « mars », "
                        "puisqu'une partie du mois reste permise.",
                        color="muted", size="xs",
                    )
                    with ui.flex(wrap=True, gap="md", align="start"):
                        with ui.vstack(gap="xs", align="center"):
                            ui.text("min=2026-03-15  max=2026-09-30",
                                    color="muted", size="xs")
                            ui.calendar("2026-06", mode="month", size="sm",
                                        min=dt.date(2026, 3, 15),
                                        max=dt.date(2026, 9, 30))
                        with ui.vstack(gap="xs", align="center"):
                            ui.text("sans valeur", color="muted", size="xs")
                            ui.calendar(mode="month", size="sm")

                    ui.heading("week × weekstart", level=3)
                    ui.text(
                        "La même date n'appartient pas à la même semaine "
                        "selon le jour de départ. À comparer côte à côte.",
                        color="muted", size="xs",
                    )
                    with ui.flex(wrap=True, gap="md", align="start"):
                        for ws, label in ((1, "weekstart=1 (lundi)"),
                                          (0, "weekstart=0 (dimanche)")):
                            with ui.vstack(gap="xs", align="center"):
                                ui.text(label, color="muted", size="xs")
                                ui.calendar(TODAY, mode="week",
                                            weekstart=ws, size="sm")

                    ui.heading("color (7 paliers)", level=3)
                    with ui.flex(wrap=True, gap="md", align="start"):
                        for c in COLORS:
                            with ui.vstack(gap="xs", align="center"):
                                ui.text(c, color="muted", size="xs")
                                ui.calendar(TODAY, color=c, size="sm")

                    ui.heading("size (5 paliers xs/sm/md/lg/xl)",
                               level=3)
                    with ui.flex(wrap=True, gap="md", align="start"):
                        for s in SIZES:
                            with ui.vstack(gap="xs", align="center"):
                                ui.text(s, color="muted", size="xs")
                                ui.calendar(TODAY, size=s)

                    ui.heading("weekstart (0=Sun, 1=Mon)", level=3)
                    with ui.flex(wrap=True, gap="md", align="start"):
                        with ui.vstack(gap="xs", align="center"):
                            ui.text("0 (Sunday-first)",
                                    color="muted", size="xs")
                            ui.calendar(size="sm", weekstart=0)
                        with ui.vstack(gap="xs", align="center"):
                            ui.text("1 (Monday-first, default)",
                                    color="muted", size="xs")
                            ui.calendar(size="sm", weekstart=1)

                    ui.heading("min / max bounds", level=3)
                    ui.text("Days outside [today, today+14] disabled.",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.calendar(size="sm",
                                    min=TODAY,
                                    max=TODAY + dt.timedelta(days=14))

                    ui.heading("disabled_dates", level=3)
                    ui.text("Specific dates skipped (holidays etc.).",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.calendar(size="sm", disabled_dates=[
                            TODAY + dt.timedelta(days=i)
                            for i in (1, 2, 3, 8, 9, 10)
                        ])

                    ui.heading("marks (day load)", level=3)
                    ui.text(
                        "A dot under the number, and the count in the "
                        "cell's accessible name. Two call shapes : a "
                        "plain list of dates (« something happens "
                        "»), or a mapping date → int. A day "
                        "outside the displayed month is never marked — "
                        "the grid overflows six days each side, and a busy "
                        "31 July seen from August would read as August "
                        "load.",
                        color="muted", size="xs",
                    )
                    with ui.flex(justify="start", gap="lg", wrap=True):
                        ui.calendar(size="sm", marks=[
                            MONTH_START + dt.timedelta(days=i) for i in (2, 9, 16, 23)
                        ])
                        ui.calendar(size="sm", marks={
                            MONTH_START + dt.timedelta(days=2): 1,
                            MONTH_START + dt.timedelta(days=9): 4,
                            MONTH_START + dt.timedelta(days=16): 12,
                        })
                    ui.text(
                        "The same prop reaches ui.date_picker, "
                        "ui.date_range_picker and ui.week_picker — same "
                        "day grid, same cell. NOT ui.month_picker : its "
                        "grid is made of MONTHS, so a dated mark has no "
                        "cell to land on.",
                        color="muted", size="xs",
                    )
                    with ui.flex(justify="start", gap="lg", wrap=True):
                        ui.date_picker(size="sm", marks={
                            MONTH_START + dt.timedelta(days=9): 4,
                        })
                        ui.week_picker(size="sm", marks={
                            MONTH_START + dt.timedelta(days=9): 4,
                        })

                    ui.heading("disabled (whole calendar)", level=3)
                    with ui.flex(justify="start"):
                        ui.calendar(size="sm", disabled=True)

                    ui.heading("month (initial displayed)", level=3)
                    ui.text("Opens on Dec 2026 instead of today's "
                            "month.", color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.calendar(size="sm",
                                    month=dt.date(2026, 12, 1))

                    ui.heading("Pre-selected value", level=3)
                    with ui.flex(wrap=True, gap="md", align="start"):
                        with ui.vstack(gap="xs", align="center"):
                            ui.text("picker", color="muted", size="xs")
                            ui.calendar(
                                TODAY + dt.timedelta(days=7),
                                size="sm")
                        with ui.vstack(gap="xs", align="center"):
                            ui.text("range",
                                    color="muted", size="xs")
                            ui.calendar(
                                (TODAY + dt.timedelta(days=3),
                                 TODAY + dt.timedelta(days=10)),
                                mode="range", size="sm")

                    ui.heading(
                        "weekday_names / month_names (FR locale)",
                        level=3,
                    )
                    ui.text(
                        "``weekday_names=`` and ``month_names=`` "
                        "accept any 7- / 12-tuple. Pattern for an FR "
                        "app : module-level constants + "
                        "``functools.partial(ui.calendar, "
                        "weekday_names=WEEKDAYS_FR, "
                        "month_names=MONTHS_FR)``.",
                        color="muted", size="xs",
                    )
                    with ui.flex(justify="start"):
                        ui.calendar(
                            size="sm",
                            weekday_names=list(WEEKDAYS_FR),
                            month_names=list(MONTHS_FR),
                        )

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Pathological inputs ; every prop's "
                            "happy-path lives in Reference.",
                            color="muted", size="sm")

                    ui.heading("min == max (single allowed day)",
                               level=3)
                    with ui.flex(justify="start"):
                        ui.calendar(size="sm", min=TODAY, max=TODAY)

                    ui.heading("disabled_dates covers most of the "
                               "month", level=3)
                    ui.text("Only weekends clickable.",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.calendar(size="sm", disabled_dates=[
                            TODAY.replace(day=1) + dt.timedelta(days=i)
                            for i in range(28)
                            if (TODAY.replace(day=1)
                                + dt.timedelta(days=i)).weekday() < 5
                        ])

                    ui.heading("disabled_dates with out-of-month "
                               "dates", level=3)
                    ui.text("Past dates passed in disabled_dates ; "
                            "Calendar ignores them (no crash).",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.calendar(size="sm", disabled_dates=[
                            dt.date(2020, 1, 1),
                            dt.date(2020, 1, 2),
                        ])

                    ui.heading("Distant future month", level=3)
                    with ui.flex(justify="start"):
                        ui.calendar(size="sm",
                                    month=dt.date(2099, 12, 1))

                    ui.heading("Distant past month", level=3)
                    with ui.flex(justify="start"):
                        ui.calendar(size="sm",
                                    month=dt.date(1900, 1, 1))

                    ui.heading("Single-char weekday names", level=3)
                    ui.text("Minimal locale — letter-only headers.",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.calendar(size="sm", weekday_names=list(
                            "SMTWTFS"))

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text(
                        "Calendar inside common containers. "
                        "**Note** : the popover-wrapped + input-"
                        "triggered pattern is the job of "
                        "``ui.date_picker`` (separate component) — "
                        "not exercised here to keep the bench "
                        "focused on Calendar's own surface.",
                        color="muted", size="sm",
                    )

                    ui.heading("Inside ui.card", level=3)
                    with ui.card():
                        with ui.vstack(gap="sm"):
                            ui.text("Pick a deadline",
                                    color="muted", size="sm")
                            ui.calendar()

                    ui.heading("Inside ui.dialog (help dialog)", level=3)
                    ui.text("Trigger button opens a dialog hosting a "
                            "Calendar — typical for date selection in "
                            "a settings flow.",
                            color="muted", size="xs")
                    cal_dialog = ui.dialog(title="Pick a date", width="sm")
                    with cal_dialog:
                        ui.calendar()
                    ui.button("Open calendar dialog",
                              icon_left="calendar",
                              variant="outline",
                              on_click=cal_dialog.open())

                    ui.heading("Side-by-side (hstack)", level=3)
                    ui.text("Two calendars in a row — pattern for "
                            "side-by-side day comparison.",
                            color="muted", size="xs")
                    with ui.hstack(gap="md", align="start"):
                        ui.calendar(size="sm")
                        ui.calendar(size="sm",
                                    month=TODAY.replace(day=1)
                                          + dt.timedelta(days=32))

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Each day cell is a focusable ``<button>`` "
                        "with ``data-date`` / ``aria-disabled`` / "
                        "reactive ``:tabindex``. Header nav buttons "
                        "carry ``aria-label='Previous month'`` / "
                        "``'Next month'`` so screen readers announce "
                        "the navigation intent. Disabled days get "
                        "``tabindex=-1`` so Tab skips them.",
                        color="muted", size="sm",
                    )
                    with ui.flex(justify="start"):
                        ui.calendar()

            # ── Card 5 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Toggle every axis ; live preview + emitted "
                        "HTML refresh on every change. The escape "
                        "hatches (``classes`` / ``id`` / "
                        "``aria-label`` / ``style`` / "
                        "``extra_attrs``) live here per "
                        "``playground-pattern.md`` § 4.",
                        color="muted", size="sm",
                    )
                    server_panel()

            # ── Card 6 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    ui.text(
                        "Each event dispatches into a Python handler "
                        "via ``bz-event:<event>=<action-id>``. "
                        "``change`` fires on date pick ; "
                        "``month_change`` on prev/next navigation ; "
                        "``focus`` / ``blur`` on the root. One "
                        "instance per event below — a single "
                        "Calendar carries only one server ``hx-post``.",
                        color="muted", size="sm",
                    )
                    with ui.flex(wrap=True, gap="md", justify="start"):
                        ui.calendar(size="sm", on_change=log_change)
                        ui.calendar(size="sm",
                                    on_month_change=log_month_change)
                        ui.calendar(size="sm", on_focus=log_focus)
                        ui.calendar(size="sm", on_blur=log_blur)
                    ui.divider()
                    events_panel()
                    ui.divider()
                    emitted_html_block(
                        "Emitted HTML (representative — change event)",
                        serialize_html(ui.calendar(
                            on_change=log_change,
                        )),
                    )

            # ── Card 7 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of Calendar's ``BINDABLE_PROPS = "
                        "('value', 'month', 'min', 'max', 'disabled')`` "
                        "contract — all five flip live via "
                        "ClientBinding, zero network round-trip. "
                        "``value=`` / ``month=`` write through on "
                        "every pick / nav ; ``min`` / ``max`` / "
                        "``disabled`` are controlled below. The two "
                        "``ui.text`` under the calendar echo the "
                        "``value``/``month`` binding live ; they sit "
                        "OUTSIDE the calendar yet update as you click.",
                        color="muted", size="sm",
                    )
                    client = CalendarClient()
                    with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                        with control("min (YYYY-MM-DD, empty = none)"):
                            ui.input(value=client.min,
                                     placeholder="2026-01-01")
                        with control("max (YYYY-MM-DD, empty = none)"):
                            ui.input(value=client.max,
                                     placeholder="2026-12-31")
                        with control("disabled"):
                            ui.switch(checked=client.disabled)
                    with ui.vstack(gap="md", align="center"):
                        with control(
                            "value (type a date — two-way, updates "
                            "the calendar)"
                        ):
                            ui.input(value=client.picked,
                                     placeholder="2026-07-15")
                        ui.calendar(client.picked,
                                    month=client.displayed_month,
                                    min=client.min,
                                    max=client.max,
                                    disabled=client.disabled)
                        with ui.hstack(gap="sm"):
                            ui.text("Picked:", color="muted", size="sm")
                            ui.text(client.picked, size="sm",
                                    weight="medium")
                        with ui.hstack(gap="sm"):
                            ui.text("Displayed month:",
                                    color="muted", size="sm")
                            ui.text(client.displayed_month, size="sm",
                                    weight="medium")
                    ui.divider()
                    emitted_html_block(
                        "Emitted HTML — note the write-through "
                        "expressions ``this.picked = iso`` inside "
                        "``pickCell()`` and the ``$watch`` in "
                        "``init()`` that writes the displayed month "
                        "back to its binding ; ``bz-attr:min`` / "
                        "``bz-attr:max`` / ``bz-attr:disabled`` on the "
                        "custom element reflect the other three.",
                        serialize_html(ui.calendar(
                            client.picked,
                            month=client.displayed_month,
                            min=client.min,
                            max=client.max,
                            disabled=client.disabled,
                        )),
                    )

            # ── Card 8 — External controls — the 3 modes ───────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes",
                               level=2)
                    ui.text(
                        "Same scenario (sibling buttons drive the "
                        "picked date and the displayed month) played "
                        "three ways. ``.set()``/``.clear()`` write "
                        "through the ``value`` binding ; "
                        "``.next_month()``/``.prev_month()`` write "
                        "through ``month`` ; ``.focus()``/``.blur()`` "
                        "are pure DOM commands (no binding involved).",
                        color="muted", size="sm",
                    )

                    # ── Mode 1 — Imperative only (default style) ────
                    ui.heading(
                        "Mode 1 — Imperative only (default)",
                        level=3,
                    )
                    ui.text(
                        "No ClientState. The calendar owns value + "
                        "month in client scope. ``.set()``/"
                        "``.clear()``/``.next_month()``/"
                        "``.prev_month()``/``.focus()``/``.blur()`` "
                        "dispatch DOM events (or run a DOM command) "
                        "caught by the calendar root. **Use this by "
                        "default — it's the natural style for "
                        "purely-visual state.**",
                        color="muted", size="sm",
                    )
                    m1 = ui.calendar(size="sm")
                    with ui.hstack(wrap=True, gap="sm"):
                        ui.button("Set today",
                                  on_click=m1.set(TODAY))
                        ui.button("Clear", variant="outline",
                                  on_click=m1.clear())
                        ui.button("Prev month", variant="ghost",
                                  on_click=m1.prev_month())
                        ui.button("Next month", variant="ghost",
                                  on_click=m1.next_month())
                        ui.button("Focus", variant="ghost",
                                  on_click=m1.focus())

                    ui.divider()

                    # ── Mode 2 — ClientBinding only ─────────────────
                    ui.heading("Mode 2 — ClientBinding only", level=3)
                    ui.text(
                        "Use this when **another component needs to "
                        "read or react to the picked date / displayed "
                        "month** — a label that mirrors it, server-side "
                        "awareness on the next render. The binding is "
                        "the single source of truth multi-composant.",
                        color="muted", size="sm",
                    )
                    bound = CalendarClient(key="binding_only")
                    with ui.vstack(gap="sm"):
                        with ui.hstack(gap="sm"):
                            ui.text("Picked:", color="muted", size="sm")
                            ui.text(bound.picked, size="sm",
                                    weight="medium")
                        ui.calendar(bound.picked, month=bound.displayed_month,
                                    size="sm")
                        with ui.hstack(wrap=True, gap="sm"):
                            ui.button(
                                "Set today via binding.set()",
                                on_click=bound.picked.set(
                                    TODAY.isoformat()),
                            )
                            ui.button(
                                "Clear via binding.set('')",
                                variant="outline",
                                on_click=bound.picked.set(""),
                            )

                    ui.divider()

                    # ── Mode 3 — Both : write-through ───────────────
                    ui.heading(
                        "Mode 3 — Both (write-through)",
                        level=3,
                    )
                    ui.text(
                        "Binding fournie ET on appelle les méthodes "
                        "impératives sur l'instance. Le framework "
                        "détecte la binding et délègue à "
                        "``binding.set(...)`` — **le DOM dispatch "
                        "n'est pas utilisé**, single source of truth "
                        "préservée.",
                        color="muted", size="sm",
                    )
                    both = CalendarClient(key="both")
                    m3 = ui.calendar(both.picked, month=both.displayed_month,
                                     size="sm")
                    with ui.hstack(wrap=True, gap="sm"):
                        ui.button("Set today via m3.set()",
                                  on_click=m3.set(TODAY))
                        ui.button("Clear via m3.clear()",
                                  variant="outline",
                                  on_click=m3.clear())
                        ui.button("Next month via m3.next_month()",
                                  variant="ghost",
                                  on_click=m3.next_month())

                    ui.divider()

                    preview = ui.calendar(bound.picked,
                                           month=bound.displayed_month)
                    emitted_html_block(
                        "Emitted HTML — Mode 2 (binding only) : "
                        "bz-attr:value / bz-attr:month read the bound "
                        "paths ; set()/clear()/next_month() write "
                        "back without a round-trip.",
                        serialize_html(preview),
                    )
            # ── Card 9 — Client events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text(
                        "Bind a ``ClientState.log`` to the same "
                        "events — the runtime pushes onto the array "
                        "without a round-trip. Useful for purely "
                        "client-side reactions (UI counter, hint "
                        "tooltip, debounced search, …) without "
                        "burning a server hop.",
                        color="muted", size="sm",
                    )
                    cevents = CalendarClient()
                    with ui.flex(justify="start"):
                        ui.calendar(
                            on_change=cevents.client_log.push("change"),
                            on_month_change=cevents.client_log.push(
                                "month_change"),
                            on_focus=cevents.client_log.push("focus"),
                            on_blur=cevents.client_log.push("blur"),
                        )
                    ui.divider()
                    with ui.hstack(gap="sm"):
                        ui.button("Clear",
                                  on_click=cevents.client_log.clear(),
                                  variant="ghost", size="sm")
                    # Live log display — the runtime pushes events into
                    # ``cevents.client_log`` from the calendar's
                    # ``@event="..."`` listeners. We echo the array
                    # length and the joined contents via reactive
                    # text bindings (the SAME pattern any user
                    # client-side reaction would use).
                    from bretzel.state import ClientExpression
                    _log_path = cevents.client_log.binding_path()
                    with ui.hstack(gap="sm", align="center"):
                        ui.text("Log size:", color="muted", size="sm")
                        ui.text(cevents.client_log.length(),
                                size="sm", weight="medium")
                    ui.text(
                        ClientExpression(
                            f"({_log_path} || []).join(' | ') || '(empty)'"
                        ),
                        size="sm", color="muted",
                    )
                    ui.divider()
                    emitted_html_block(
                        "Emitted HTML — note ``@change=\"$bz.state."
                        "CalendarClient.default.client_log.push(...)\"`` "
                        "(pure client-side, no ``hx-post``).",
                        serialize_html(ui.calendar(
                            on_change=cevents.client_log.push("change"),
                        )),
                    )

