"""``DatePicker`` test bench.

Eight visual cards (no slots → skip card 2) : Reference / Edge cases /
Composability / A11y / Server playground / Server events / Client
playground / Client events. DatePicker's reactive surface :
``BINDABLE_PROPS = ("value", "min", "max", "disabled")`` ;
``EVENTS = ("change", "focus", "blur")`` ;
``AUTONAME_FROM = "value"``.

The component is a popover-wrapped editable input : the field accepts
free-form typing (normalised to ISO on blur via ``new Date(val)``) and
the calendar icon button (inside the focus-within frame) opens a
``<bz-calendar mode="picker">``. Cf. ``bretzel/components/inputs/
date_picker/date_picker.py`` for the architecture.
"""

from __future__ import annotations

import datetime as dt

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression

from examples.playground.features.inspection import emitted_html_block
from examples.playground.features.date_picker.state import (
    COLORS,
    DatePickerClient,
    DatePickerPlayground,
    LOCALES,
    MONTHS_FR,
    SIZES,
    WEEKDAYS_FR,
)
from examples.playground.features.date_picker.logic import (
    clear_log,
    log_blur,
    log_change,
    log_focus,
    server_changed,
)


PATH = "/date_picker"

TODAY = dt.date.today()
#: Le 1er du mois courant. Les demos de ``marks=`` s'y ancrent : la
#: grille n'affiche QUE le mois courant, donc ``TODAY + 11 jours``
#: un 25 tombe dans le mois suivant et la demo ne montre aucune
#: pastille. Tout mois a au moins 28 jours, donc ces decalages-la
#: sont toujours dedans.
MONTH_START = TODAY.replace(day=1)


# ─────────────────────────────────────────────────────────────────
# Module-level helpers (per playground-pattern.md § 6.3)
# ─────────────────────────────────────────────────────────────────


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: DatePickerPlayground):
    """Map the Server-playground state → ``ui.date_picker(**kwargs)``.

    Empty strings collapse to missing kwargs ; the visibility / tooltip
    universal modifiers + escape hatches are wired here so the
    preview reflects every axis exposed in the controls grid.
    """
    kwargs: dict = {
        "placeholder": state.placeholder or "YYYY-MM-DD",
        "color": state.color,
        "size": state.size,
        "weekstart": state.weekstart,
        "clearable": state.clearable == "on",
        "close_on_pick": state.close_on_pick == "on",
    }
    if state.value:
        kwargs["value"] = state.value
    if state.name:
        kwargs["name"] = state.name
    if state.min:
        kwargs["min"] = state.min
    if state.max:
        kwargs["max"] = state.max
    if state.disabled_dates:
        kwargs["disabled_dates"] = [
            d.strip() for d in state.disabled_dates.split(",") if d.strip()
        ]
    if state.marks:
        # La forme LISTE de ``marks=`` : « ces jours-la ont quelque
        # chose ». La forme dict (date -> compte) est demontree sur la
        # page ``calendar``, qui est le composant proprietaire.
        kwargs["marks"] = [
            d.strip() for d in state.marks.split(",") if d.strip()
        ]
    if state.locale == "fr":
        kwargs["weekday_names"] = list(WEEKDAYS_FR)
        kwargs["month_names"] = list(MONTHS_FR)
    if state.disabled == "on":
        kwargs["disabled"] = True
    if state.required == "on":
        kwargs["required"] = True
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
    return ui.date_picker(**kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


# ─────────────────────────────────────────────────────────────────
# Refreshable panels — Server playground + Server events
# ─────────────────────────────────────────────────────────────────


@refreshable(deps=[DatePickerPlayground])
def server_panel() -> None:
    state = DatePickerPlayground()
    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
        with control("value (YYYY-MM-DD, empty = none)"):
            ui.input(value=state.value, placeholder="2026-07-17",
                     on_change=server_changed)
        with control("name (overrides autoname)"):
            ui.input(value=state.name, placeholder="deadline",
                     on_change=server_changed)
        with control("min (YYYY-MM-DD, empty = none)"):
            ui.input(value=state.min, placeholder="2026-01-01",
                     on_change=server_changed)
        with control("max (YYYY-MM-DD, empty = none)"):
            ui.input(value=state.max, placeholder="2026-12-31",
                     on_change=server_changed)
        with control("disabled_dates (comma-separated ISO)"):
            ui.input(value=state.disabled_dates,
                     placeholder="2026-07-04,2026-07-14",
                     on_change=server_changed)
        with control("marks (comma-separated ISO)"):
            ui.input(value=state.marks,
                     placeholder="2026-07-08,2026-07-09",
                     on_change=server_changed)
        with control("placeholder"):
            ui.input(value=state.placeholder,
                     placeholder="YYYY-MM-DD",
                     on_change=server_changed)
        with control("color (7 paliers)"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size (xs/sm/md/lg/xl)"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
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
                      options=[("0", "0 (Sunday)"),
                               ("1", "1 (Monday)")],
                      on_change=server_changed)
        with control("locale"):
            ui.select(value=state.locale,
                      options=[("en", "English (default)"),
                               ("fr", "French (custom names)")],
                      on_change=server_changed)
        with control("clearable"):
            ui.select(value=state.clearable,
                      options=[("on", "on (default)"), ("off", "off")],
                      on_change=server_changed)
        with control("close_on_pick"):
            ui.select(value=state.close_on_pick,
                      options=[("on", "on (default)"), ("off", "off")],
                      on_change=server_changed)
        with control("disabled"):
            ui.select(value=state.disabled,
                      options=[("off", "off"), ("on", "on")],
                      on_change=server_changed)
        with control("required"):
            ui.select(value=state.required,
                      options=[("off", "off"), ("on", "on")],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="ring-2 ring-offset-2",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id,
                     placeholder="my-date-picker",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Pick a deadline",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="min-width: 14rem",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=dp",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Pick a deadline",
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
        "Emitted HTML (truncated — the wrapper carries the open / val "
        "runtime state + the bz-effect that syncs val → calendar)",
        serialize_html(build_preview(state)),
    )


@refreshable(deps=[DatePickerPlayground])
def events_panel() -> None:
    state = DatePickerPlayground()
    with ui.vstack(gap="sm"):
        with ui.hstack(gap="sm"):
            ui.button("Clear log", on_click=clear_log,
                      variant="ghost", size="sm")
        if not state.log:
            ui.text("No events yet — interact with the picker above.",
                    color="muted", size="sm")
        else:
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"#{i}  {evt}", size="sm", color="muted")


# ─────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("DatePicker", level=1)
            ui.text(
                "Single-date input with an inline calendar popover. "
                "UX modeled on native ``<input type=\"date\">`` : the "
                "field accepts free-form typing (normalised to ISO on "
                "blur via ``new Date(val)``) and the calendar icon "
                "button lives inside the same focus-within frame. "
                "``BINDABLE_PROPS = (value, min, max, disabled)`` ; "
                "``EVENTS = (change, focus, blur)`` ; "
                "``AUTONAME_FROM = \"value\"``.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text(
                        "Visual scan of every prop. Each axis demoed "
                        "inline so the Tailwind dev scanner compiles "
                        "every class the Server playground might swap "
                        "to later (no safelist required).",
                        color="muted", size="sm",
                    )

                    ui.heading("Empty (default placeholder)", level=3)
                    with ui.flex(justify="start"):
                        ui.date_picker()

                    ui.heading("Pre-selected value", level=3)
                    with ui.flex(justify="start"):
                        ui.date_picker(TODAY + dt.timedelta(days=3))

                    ui.heading("Custom placeholder", level=3)
                    with ui.flex(justify="start"):
                        ui.date_picker(placeholder="Pick a deadline")

                    ui.heading("color (7 paliers)", level=3)
                    with ui.flex(wrap=True, gap="md", align="start"):
                        for c in COLORS:
                            with ui.vstack(gap="xs", align="center"):
                                ui.text(c, color="muted", size="xs")
                                ui.date_picker(
                                    TODAY + dt.timedelta(days=2),
                                    color=c, size="sm",
                                )

                    ui.heading("size (xs/sm/md/lg/xl)", level=3)
                    with ui.flex(wrap=True, gap="md", align="start"):
                        for s in SIZES:
                            with ui.vstack(gap="xs", align="center"):
                                ui.text(s, color="muted", size="xs")
                                ui.date_picker(
                                    TODAY + dt.timedelta(days=2),
                                    size=s,
                                )

                    ui.heading("weekstart (0=Sun, 1=Mon)", level=3)
                    with ui.flex(wrap=True, gap="md", align="start"):
                        with ui.vstack(gap="xs", align="center"):
                            ui.text("0 (Sunday-first)",
                                    color="muted", size="xs")
                            ui.date_picker(weekstart=0)
                        with ui.vstack(gap="xs", align="center"):
                            ui.text("1 (Monday-first, default)",
                                    color="muted", size="xs")
                            ui.date_picker(weekstart=1)

                    ui.heading("min + max bounds", level=3)
                    ui.text("Calendar days outside [today, today+30] "
                            "are disabled.", color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.date_picker(
                            min=TODAY,
                            max=TODAY + dt.timedelta(days=30),
                        )

                    ui.heading("disabled_dates", level=3)
                    ui.text("Specific dates skipped (holidays etc.).",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.date_picker(
                            disabled_dates=[
                                TODAY + dt.timedelta(days=i)
                                for i in (1, 2, 8, 9, 15, 16)
                            ],
                        )

                    ui.heading("marks (day load)", level=3)
                    ui.text("A dot under the day, and the count in the cell's accessible name. Two call shapes : a list of dates, or a mapping date to int.", color="muted", size="xs")
                    with ui.flex(justify="start", gap="lg", wrap=True):
                        ui.date_picker(marks=[
                            MONTH_START + dt.timedelta(days=i)
                            for i in (2, 9, 16, 23)
                        ])
                        ui.date_picker(marks={
                            MONTH_START + dt.timedelta(days=2): 1,
                            MONTH_START + dt.timedelta(days=9): 5,
                            MONTH_START + dt.timedelta(days=16): 12,
                        })

                    ui.heading("disabled (whole picker)", level=3)
                    with ui.flex(justify="start"):
                        ui.date_picker(
                            TODAY + dt.timedelta(days=3),
                            disabled=True,
                        )

                    ui.heading("required", level=3)
                    with ui.flex(justify="start"):
                        ui.date_picker(required=True)

                    ui.heading("close_on_pick=False (keep popover open)",
                               level=3)
                    ui.text("Useful for tight grids where the user "
                            "wants to compare days before commit.",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.date_picker(close_on_pick=False)

                    ui.heading("clearable=False", level=3)
                    ui.text("No × button — the value can only change "
                            "via re-pick or typing.",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.date_picker(
                            TODAY + dt.timedelta(days=3),
                            clearable=False,
                        )

                    ui.heading("FR locale (custom names)", level=3)
                    ui.text(
                        "Pattern for an FR app : module-level constants "
                        "``WEEKDAYS_FR`` / ``MONTHS_FR`` + "
                        "``functools.partial(ui.date_picker, "
                        "weekday_names=WEEKDAYS_FR, "
                        "month_names=MONTHS_FR)``.",
                        color="muted", size="xs",
                    )
                    with ui.flex(justify="start"):
                        ui.date_picker(
                            placeholder="Choisir une date",
                            weekday_names=list(WEEKDAYS_FR),
                            month_names=list(MONTHS_FR),
                        )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Pathological inputs ; every prop's "
                            "happy-path lives in Reference.",
                            color="muted", size="sm")

                    ui.heading("min == max (single allowed day)",
                               level=3)
                    with ui.flex(justify="start"):
                        ui.date_picker(min=TODAY, max=TODAY)

                    ui.heading("Pre-selected outside [min, max]",
                               level=3)
                    ui.text("Value is past the max — the calendar shows "
                            "it selected but it's also disabled. "
                            "Picker doesn't auto-clear ; user discovers "
                            "the constraint on next open.",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.date_picker(
                            TODAY + dt.timedelta(days=20),
                            min=TODAY,
                            max=TODAY + dt.timedelta(days=10),
                        )

                    ui.heading("disabled_dates with out-of-month dates",
                               level=3)
                    ui.text("Past dates passed in disabled_dates ; the "
                            "underlying calendar ignores them (no crash).",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.date_picker(disabled_dates=[
                            dt.date(2020, 1, 1),
                            dt.date(2020, 1, 2),
                        ])

                    ui.heading("Empty placeholder", level=3)
                    ui.text("``placeholder=\"\"`` renders an empty hint ; "
                            "no format prompt for the typer.",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.date_picker(placeholder="")

                    ui.heading("Long placeholder", level=3)
                    ui.text("The field's intrinsic width follows the "
                            "placeholder ; long hints stretch the row.",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.date_picker(
                            placeholder="Please pick a date by next "
                            "Friday at the latest",
                        )

                    ui.heading("Free-form typing tolerance", level=3)
                    ui.text(
                        "Type unusual formats in this field, then blur "
                        "(Tab away or click outside) : "
                        "``07/19/2018`` → ``2018-07-19`` ; "
                        "``July 19 2018`` → ``2018-07-19`` ; "
                        "``garbage`` → cleared. The blur normaliser "
                        "runs ``new Date(val)`` and rewrites in ISO, "
                        "or wipes the field if unparseable.",
                        color="muted", size="xs",
                    )
                    with ui.flex(justify="start"):
                        ui.date_picker()

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text(
                        "DatePicker inside common containers. The "
                        "popover panel is repositioned "
                        "``position: fixed`` when it opens, so it "
                        "escapes Card's ``overflow-hidden`` natively "
                        "— nothing to declare.",
                        color="muted", size="sm",
                    )

                    ui.heading("Inside ui.card (this one !)", level=3)
                    with ui.card():
                        with ui.vstack(gap="sm"):
                            ui.text("Pick a deadline",
                                    color="muted", size="sm")
                            ui.date_picker()

                    ui.heading("Inside ui.form", level=3)
                    ui.text("Form-data carrier : the hidden input "
                            "rides ISO ``YYYY-MM-DD``. "
                            "``AUTONAME_FROM = \"value\"`` derives "
                            "the ``name=`` attribute automatically "
                            "from a bound field.",
                            color="muted", size="xs")
                    with ui.form():
                        with ui.vstack(gap="md"):
                            with ui.flex(justify="start"):
                                ui.date_picker(name="due_date")
                            with ui.hstack(gap="sm"):
                                ui.button("Submit", type="submit")
                                ui.button("Reset", type="reset",
                                          variant="outline")

                    ui.heading("Side-by-side (hstack)", level=3)
                    ui.text("Two pickers in a row — pattern for "
                            "start/end (though for proper ranges, "
                            "prefer ``ui.date_range_picker``).",
                            color="muted", size="xs")
                    with ui.hstack(gap="md", align="start"):
                        ui.date_picker(placeholder="Departure")
                        ui.date_picker(placeholder="Return")

                    ui.heading("Inside ui.dialog", level=3)
                    ui.text("Schedule-a-meeting flow : a Dialog hosts "
                            "the DatePicker, the popover floats over "
                            "the modal overlay.",
                            color="muted", size="xs")
                    schedule_dialog = ui.dialog(
                        title="Schedule meeting", width="sm",
                    )
                    with schedule_dialog:
                        with ui.vstack(gap="sm"):
                            ui.text("Pick a date for the meeting :",
                                    color="muted", size="sm")
                            ui.date_picker()
                    ui.button("Open scheduler",
                              icon_left="calendar",
                              variant="outline",
                              on_click=schedule_dialog.open())

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "The editable field exposes a typed-date hint "
                        "via ``placeholder`` + ``aria-label`` (default "
                        "mirrors the placeholder so screen readers "
                        "announce the expected format). The calendar "
                        "trigger has "
                        "``aria-label=\"Open date picker\"`` + "
                        "``:aria-expanded`` toggling with the popover. "
                        "The clear × button has "
                        "``aria-label=\"Clear date\"`` and is hidden "
                        "(``bz-show=\"val\"``) when no value is set so "
                        "screen readers don't announce it. Inside the "
                        "calendar : each day cell is a focusable "
                        "``<button>`` with ``data-date`` / "
                        "``aria-disabled`` / reactive ``:tabindex``.",
                        color="muted", size="sm",
                    )
                    with ui.flex(justify="start"):
                        ui.date_picker(
                            TODAY + dt.timedelta(days=3),
                        )

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Toggle every axis ; live preview + emitted "
                        "HTML refresh on every change. The escape "
                        "hatches (``classes`` / ``id`` / ``aria-label`` "
                        "/ ``style`` / ``extra_attrs``) live here per "
                        "``playground-pattern.md`` § 4.",
                        color="muted", size="sm",
                    )
                    server_panel()

            # ── Card 7 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    ui.text(
                        "Each event dispatches into a Python handler "
                        "via ``bz-event:<event>=<action-id>``. "
                        "``change`` fires on date pick (calendar or "
                        "field commit) ; ``focus`` / ``blur`` fire on "
                        "the typeable field. One instance per event "
                        "below — a single DatePicker carries only "
                        "one server ``hx-post``. Pick a date or click "
                        "an input then tab away to populate the log.",
                        color="muted", size="sm",
                    )
                    with ui.flex(wrap=True, gap="md", justify="start"):
                        ui.date_picker(on_change=log_change)
                        ui.date_picker(on_focus=log_focus)
                        ui.date_picker(on_blur=log_blur)
                    ui.divider()
                    events_panel()
                    ui.divider()
                    emitted_html_block(
                        "Emitted HTML (representative — change event)",
                        serialize_html(ui.date_picker(
                            on_change=log_change,
                        )),
                    )

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "``value=`` accepts a ``ClientBinding``. "
                        "the runtime writes through on every pick AND on "
                        "every typed-in commit — zero network round-"
                        "trip. The ``ui.text`` below echoes the bound "
                        "value live ; it sits OUTSIDE the picker yet "
                        "updates as you interact.",
                        color="muted", size="sm",
                    )
                    client = DatePickerClient()
                    with ui.vstack(gap="md", align="center"):
                        ui.date_picker(client.picked)
                        with ui.hstack(gap="sm", align="center"):
                            ui.text("Picked:", color="muted",
                                    size="sm")
                            ui.text(client.picked,
                                    size="sm", weight="medium")
                    ui.divider()
                    emitted_html_block(
                        "Emitted HTML — no watcher : the text field "
                        "carries ``bz-model`` on "
                        "``$bz.state.DatePickerClient.default.picked`` "
                        "(two-way), the wrapper a ``bz-effect`` that "
                        "pushes that value into the ``<bz-calendar>``, "
                        "and the calendar a ``bz-on:change`` that "
                        "writes the pick back — so external state "
                        "mutations reflect in the field.",
                        serialize_html(ui.date_picker(client.picked)),
                    )

            # ── Card 9 — Client events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    # ── External controls — the 3 modes ────────────────────
                    with ui.card():
                        with ui.vstack():
                            ui.heading("External controls — the 3 modes", level=2)
                            ui.text(
                                "Les sept méthodes arrivées le 2026-09-03. Un picker "
                                "est DEUX natures à la fois : un panneau ancré (comme "
                                "`dialog`) et un champ qui porte une valeur (comme "
                                "`input`). Sa surface est donc l'union des deux "
                                "vocabulaires déjà fixés par ses voisins — rien "
                                "d'inventé.",
                                color="muted", size="sm",
                            )

                            # ── Mode 1 — Impératif seul ─────────────────────
                            ui.heading("Mode 1 — Imperative only (default for "
                                       "one-off writes)", level=3)
                            ui.text(
                                "Aucun ClientState. `.open()` / `.close()` / "
                                "`.toggle()` dispatchent `bz-open` / `bz-close` / "
                                "`bz-toggle`, que la racine rattrape ; `.set()` "
                                "dispatche `bz-set`. `.focus()` vise le champ "
                                "VISIBLE — pas le porteur caché, qui est le premier "
                                "`<input>` du composant et ne prend pas le focus.",
                                color="muted", size="sm",
                            )
                            m1 = ui.date_picker()
                            with ui.hstack(gap="sm", wrap=True):
                                ui.button("Ouvrir", on_click=m1.open())
                                ui.button("Fermer", variant="outline",
                                          on_click=m1.close())
                                ui.button("Basculer", variant="outline",
                                          on_click=m1.toggle())
                                ui.button("Set 2026-09-15", on_click=m1.set("2026-09-15"))
                                ui.button("Clear", variant="ghost",
                                          on_click=m1.clear())
                                ui.button("Focus", variant="ghost",
                                          on_click=m1.focus())
                                ui.button("Blur", variant="ghost",
                                          on_click=m1.blur())

                            ui.divider()

                            # ── Mode 2 — ClientBinding seule ────────────────
                            ui.heading("Mode 2 — ClientBinding only (when another "
                                       "component must read or react)", level=3)
                            ui.text(
                                "`value=binding` : la valeur vit dans le store, "
                                "donc un voisin la lit sans aller-retour.",
                                color="muted", size="sm",
                            )
                            lie = DatePickerClient(key="ext_binding")
                            with ui.hstack(gap="md", align="center"):
                                ui.date_picker(value=lie.picked)
                                ui.text(
                                    ClientExpression(
                                        "'Valeur : ' + ($bz.state.DatePickerClient"
                                        ".ext_binding.picked || '(aucune)')"
                                    ),
                                    color="muted", size="sm", classes="font-mono",
                                )

                            ui.divider()

                            # ── Mode 3 — Les deux ───────────────────────────
                            ui.heading("Mode 3 — Both (write-through)", level=3)
                            ui.text(
                                "Binding fournie ET méthodes appelées. `.set()` "
                                "détecte la binding et écrit DEDANS — le dispatch "
                                "DOM n'est pas utilisé, la source de vérité reste "
                                "unique. `.open()` reste un dispatch : le panneau "
                                "n'est pas une valeur.",
                                color="muted", size="sm",
                            )
                            deux = DatePickerClient(key="ext_both")
                            m3 = ui.date_picker(value=deux.picked)
                            with ui.hstack(gap="sm", wrap=True, align="center"):
                                ui.button("Ouvrir", size="xs", on_click=m3.open())
                                ui.button("Set 2026-09-15", size="xs",
                                          on_click=m3.set("2026-09-15"))
                                ui.button("Clear", size="xs", variant="ghost",
                                          on_click=m3.clear())
                                ui.text(
                                    ClientExpression(
                                        "'Store : ' + ($bz.state.DatePickerClient"
                                        ".ext_both.picked || '(vide)')"
                                    ),
                                    color="muted", size="sm", classes="font-mono",
                                )

                    ui.heading("Client events", level=2)
                    ui.text(
                        "Bind a ``ClientState.client_log`` to the same "
                        "events — the runtime pushes onto the array without "
                        "a round-trip. Useful for purely client-side "
                        "reactions (UI counter, hint tooltip, "
                        "debounced search, …) without burning a "
                        "server hop.",
                        color="muted", size="sm",
                    )
                    cevents = DatePickerClient()
                    with ui.flex(justify="start"):
                        ui.date_picker(
                            on_change=cevents.client_log.push("change"),
                            on_focus=cevents.client_log.push("focus"),
                            on_blur=cevents.client_log.push("blur"),
                        )
                    ui.divider()
                    with ui.hstack(gap="sm"):
                        ui.button("Clear",
                                  on_click=cevents.client_log.clear(),
                                  variant="ghost", size="sm")
                    _log_path = cevents.client_log.binding_path()
                    with ui.hstack(gap="sm", align="center"):
                        ui.text("Log size:", color="muted", size="sm")
                        ui.text(cevents.client_log.length(),
                                size="sm", weight="medium")
                    ui.text(
                        ClientExpression(
                            f"({_log_path} || []).join(' | ') "
                            f"|| '(empty)'"
                        ),
                        size="sm", color="muted",
                    )
                    ui.divider()
                    emitted_html_block(
                        "Emitted HTML — note "
                        "``@change=\"$bz.state.DatePickerClient.default"
                        ".client_log.push(...)\"`` (pure client-side, no "
                        "``hx-post``).",
                        serialize_html(ui.date_picker(
                            on_change=cevents.client_log.push("change"),
                        )),
                    )
