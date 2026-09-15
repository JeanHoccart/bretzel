"""``DateRangePicker`` test bench.

Eight visual cards (no slots → skip card 2). Mirror of the DatePicker
page with two editable fields under one focus ring + the calendar
trigger button. ``BINDABLE_PROPS = ("value", "min", "max",
"disabled")`` ; ``EVENTS = ("change", "focus", "blur")`` ;
``AUTONAME_FROM = "value"``. The bound value is a ``(start, end)``
tuple ; the hidden form-data input rides
``JSON.stringify([vstart, vend])``.
"""

from __future__ import annotations

import datetime as dt

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression

from examples.playground.features.inspection import emitted_html_block
from examples.playground.features.date_range_picker.state import (
    COLORS,
    DateRangePickerClient,
    DateRangePickerPlayground,
    MONTHS_FR,
    SIZES,
    WEEKDAYS_FR,
)
from examples.playground.features.date_range_picker.logic import (
    clear_log,
    log_blur,
    log_change,
    log_focus,
    server_changed,
)


PATH = "/date_range_picker"

TODAY = dt.date.today()
#: Le 1er du mois courant. Les demos de ``marks=`` s'y ancrent : la
#: grille n'affiche QUE le mois courant, donc ``TODAY + 11 jours``
#: un 25 tombe dans le mois suivant et la demo ne montre aucune
#: pastille. Tout mois a au moins 28 jours, donc ces decalages-la
#: sont toujours dedans.
MONTH_START = TODAY.replace(day=1)


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: DateRangePickerPlayground):
    kwargs: dict = {
        "placeholder_start": state.placeholder_start or "Start",
        "placeholder_end": state.placeholder_end or "End",
        "separator": state.separator or "→",
        "color": state.color,
        "size": state.size,
        "weekstart": state.weekstart,
        "clearable": state.clearable == "on",
        "close_on_close": state.close_on_close == "on",
    }
    if state.min:
        kwargs["min"] = state.min
    if state.max:
        kwargs["max"] = state.max
    if state.disabled_dates:
        kwargs["disabled_dates"] = [
            d.strip() for d in state.disabled_dates.split(",") if d.strip()
        ]
    if state.marks:
        # La forme LISTE de ``marks=`` : « ces jours-là ont quelque
        # chose ». La forme dict (date → compte) est démontrée sur la
        # page ``calendar``, qui est le composant propriétaire.
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
    return ui.date_range_picker(**kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[DateRangePickerPlayground])
def server_panel() -> None:
    state = DateRangePickerPlayground()
    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
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
        with control("placeholder_start"):
            ui.input(value=state.placeholder_start,
                     placeholder="Start",
                     on_change=server_changed)
        with control("placeholder_end"):
            ui.input(value=state.placeholder_end,
                     placeholder="End",
                     on_change=server_changed)
        with control("separator (between the two fields)"):
            ui.input(value=state.separator,
                     placeholder="→",
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
        with control("close_on_close (only fires when range closes)"):
            ui.select(value=state.close_on_close,
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
                     placeholder="my-range",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Pick a date range",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="min-width: 22rem",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=drp",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Pick a date range",
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
        "Emitted HTML (the wrapper bz-data holds vstart / vend ; the "
        "bz-effect syncs them to the inner bz-calendar mode=range)",
        serialize_html(build_preview(state)),
    )


@refreshable(deps=[DateRangePickerPlayground])
def events_panel() -> None:
    state = DateRangePickerPlayground()
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


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("DateRangePicker", level=1)
            ui.text(
                "Start + end date input with a shared calendar "
                "popover (``ui.calendar(mode=\"range\")``). Mirror of "
                "DatePicker on the UX shape : two editable fields "
                "(free-form typing, ISO-normalised on blur), one focus "
                "ring around the whole row, the calendar icon button "
                "lives inside. The popover auto-closes when the range "
                "CLOSES (both endpoints set) — clicking the first "
                "endpoint keeps the popover open so the user picks "
                "the second. ``BINDABLE_PROPS = (value, min, max, "
                "disabled)`` ; ``EVENTS = (change, focus, blur)`` ; "
                "``AUTONAME_FROM = \"value\"``.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Empty (default)", level=3)
                    with ui.flex(justify="start"):
                        ui.date_range_picker()

                    ui.heading("Pre-selected range", level=3)
                    with ui.flex(justify="start"):
                        ui.date_range_picker(
                            (TODAY + dt.timedelta(days=2),
                             TODAY + dt.timedelta(days=10)),
                        )

                    ui.heading("Custom separator + placeholders",
                               level=3)
                    with ui.flex(wrap=True, gap="md", align="start"):
                        with ui.vstack(gap="xs", align="center"):
                            ui.text("→ default", color="muted",
                                    size="xs")
                            ui.date_range_picker()
                        with ui.vstack(gap="xs", align="center"):
                            ui.text("From / To with –", color="muted",
                                    size="xs")
                            ui.date_range_picker(
                                placeholder_start="From",
                                placeholder_end="To",
                                separator="–",
                            )
                        with ui.vstack(gap="xs", align="center"):
                            ui.text("to (word)", color="muted",
                                    size="xs")
                            ui.date_range_picker(separator="to")

                    ui.heading("color (7 paliers)", level=3)
                    with ui.flex(wrap=True, gap="md", align="start"):
                        for c in COLORS:
                            with ui.vstack(gap="xs", align="center"):
                                ui.text(c, color="muted", size="xs")
                                ui.date_range_picker(
                                    (TODAY + dt.timedelta(days=1),
                                     TODAY + dt.timedelta(days=5)),
                                    color=c, size="sm",
                                )

                    ui.heading("size (xs/sm/md/lg/xl)", level=3)
                    with ui.flex(wrap=True, gap="md", align="start"):
                        for s in SIZES:
                            with ui.vstack(gap="xs", align="center"):
                                ui.text(s, color="muted", size="xs")
                                ui.date_range_picker(
                                    (TODAY + dt.timedelta(days=1),
                                     TODAY + dt.timedelta(days=5)),
                                    size=s,
                                )

                    ui.heading("weekstart (0=Sun, 1=Mon)", level=3)
                    with ui.flex(wrap=True, gap="md", align="start"):
                        with ui.vstack(gap="xs", align="center"):
                            ui.text("0 (Sunday-first)",
                                    color="muted", size="xs")
                            ui.date_range_picker(weekstart=0)
                        with ui.vstack(gap="xs", align="center"):
                            ui.text("1 (Monday-first, default)",
                                    color="muted", size="xs")
                            ui.date_range_picker(weekstart=1)

                    ui.heading("min + max bounds", level=3)
                    ui.text("Calendar days outside [today, today+60] "
                            "disabled.", color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.date_range_picker(
                            min=TODAY,
                            max=TODAY + dt.timedelta(days=60),
                        )

                    ui.heading("disabled_dates", level=3)
                    ui.text("Specific dates skipped (holidays etc.).",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.date_range_picker(
                            disabled_dates=[
                                TODAY + dt.timedelta(days=i)
                                for i in (3, 4, 10, 11)
                            ],
                        )

                    ui.heading("marks (day load)", level=3)
                    ui.text("A dot under the day, and the count in the cell's accessible name. Two call shapes : a list of dates, or a mapping date to int.", color="muted", size="xs")
                    with ui.flex(justify="start", gap="lg", wrap=True):
                        ui.date_range_picker(marks=[
                            MONTH_START + dt.timedelta(days=i)
                            for i in (2, 9, 16, 23)
                        ])
                        ui.date_range_picker(marks={
                            MONTH_START + dt.timedelta(days=2): 1,
                            MONTH_START + dt.timedelta(days=9): 5,
                        })

                    ui.heading("disabled (whole picker)", level=3)
                    with ui.flex(justify="start"):
                        ui.date_range_picker(
                            (TODAY, TODAY + dt.timedelta(days=5)),
                            disabled=True,
                        )

                    ui.heading("required", level=3)
                    with ui.flex(justify="start"):
                        ui.date_range_picker(required=True)

                    ui.heading("close_on_close=False (keep popover open)",
                               level=3)
                    ui.text("Useful for multi-range comparisons — pick, "
                            "see the bounds materialise, then pick "
                            "again without re-opening.",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.date_range_picker(close_on_close=False)

                    ui.heading("clearable=False", level=3)
                    with ui.flex(justify="start"):
                        ui.date_range_picker(
                            (TODAY, TODAY + dt.timedelta(days=5)),
                            clearable=False,
                        )

                    ui.heading("FR locale (custom names)", level=3)
                    with ui.flex(justify="start"):
                        ui.date_range_picker(
                            placeholder_start="Début",
                            placeholder_end="Fin",
                            weekday_names=list(WEEKDAYS_FR),
                            month_names=list(MONTHS_FR),
                        )

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "``separator`` is slot-shaped (``adopt_slot`` "
                        "accepts str | Component | ClientBinding). "
                        "Every other demo on this page uses a str "
                        "shortcut — this card shows the other two "
                        "shapes.",
                        color="muted", size="sm",
                    )

                    ui.heading("separator=str (the common case)", level=3)
                    with ui.flex(justify="start"):
                        ui.date_range_picker(separator="→")

                    ui.heading("separator=Component", level=3)
                    with ui.flex(justify="start"):
                        ui.date_range_picker(
                            separator=ui.icon("arrow-right",
                                              color="primary"),
                        )

                    ui.text(
                        "separator=ClientBinding : deferred to the "
                        "Client playground card — a live reactive "
                        "separator is a design-time-driven edge case, "
                        "not a common shape.",
                        color="muted", size="xs",
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Pathological inputs.",
                            color="muted", size="sm")

                    ui.heading("Single-day range (start == end)",
                               level=3)
                    ui.text("Picker accepts a zero-length range — "
                            "user clicks the same day twice.",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.date_range_picker((TODAY, TODAY))

                    ui.heading("Pre-selected range outside [min, max]",
                               level=3)
                    ui.text("Bounds violated — the field shows the "
                            "values but the calendar disables them. "
                            "User discovers on next open.",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.date_range_picker(
                            (TODAY + dt.timedelta(days=20),
                             TODAY + dt.timedelta(days=30)),
                            min=TODAY,
                            max=TODAY + dt.timedelta(days=10),
                        )

                    ui.heading("Empty separator", level=3)
                    ui.text("``separator=\"\"`` — the two fields sit "
                            "flush. Edge but works.",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.date_range_picker(separator="")

                    ui.heading("Long separator (multiword)", level=3)
                    with ui.flex(justify="start"):
                        ui.date_range_picker(separator=" through ")

                    ui.heading("Free-form typing tolerance per field",
                               level=3)
                    ui.text(
                        "Each editable input runs its own blur "
                        "normaliser — try typing ``07/19/2018`` in "
                        "the start field, ``August 1 2018`` in the "
                        "end, then tab away. Both normalise to ISO ; "
                        "the bz-calendar receives the JSON pair via "
                        "bz-effect once BOTH endpoints are clean.",
                        color="muted", size="xs",
                    )
                    with ui.flex(justify="start"):
                        ui.date_range_picker()

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text(
                        "DateRangePicker inside common containers. "
                        "The popover is ``position: fixed`` once "
                        "open, so it escapes Card's "
                        "``overflow-hidden`` natively.",
                        color="muted", size="sm",
                    )

                    ui.heading("Inside ui.card", level=3)
                    with ui.card():
                        with ui.vstack(gap="sm"):
                            ui.text("Trip window",
                                    color="muted", size="sm")
                            ui.date_range_picker(
                                placeholder_start="Departure",
                                placeholder_end="Return",
                            )

                    ui.heading("Inside ui.form (with hidden JSON pair)",
                               level=3)
                    ui.text("Form-data carrier rides "
                            "``JSON.stringify([vstart, vend])``. "
                            "AUTONAME derives ``name=\"value\"`` (or "
                            "the bound field name).",
                            color="muted", size="xs")
                    with ui.form():
                        with ui.vstack(gap="md"):
                            with ui.flex(justify="start"):
                                ui.date_range_picker(name="trip_dates")
                            with ui.hstack(gap="sm"):
                                ui.button("Submit", type="submit")
                                ui.button("Reset", type="reset",
                                          variant="outline")

                    ui.heading("Inside ui.dialog", level=3)
                    ui.text("Booking flow : a Dialog hosts the range "
                            "picker, the popover floats over the "
                            "modal overlay.",
                            color="muted", size="xs")
                    booking_dialog = ui.dialog(
                        title="Booking window", width="sm",
                    )
                    with booking_dialog:
                        with ui.vstack(gap="sm"):
                            ui.text("Pick check-in / check-out :",
                                    color="muted", size="sm")
                            ui.date_range_picker()
                    ui.button("Open booking",
                              icon_left="calendar-range",
                              variant="outline",
                              on_click=booking_dialog.open())

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Each editable field carries its own "
                        "``aria-label`` (defaults to the placeholder — "
                        "``\"Start\"`` / ``\"End\"`` by default ; "
                        "customise via ``placeholder_start=`` / "
                        "``placeholder_end=``). The separator is a "
                        "presentational ``<span>`` (``select-none``) "
                        "that screen readers skip. The trigger button "
                        "has ``aria-label=\"Open date range picker\"`` "
                        "+ ``:aria-expanded`` toggling with the "
                        "popover. The clear × button is hidden "
                        "(``bz-show=\"vstart || vend\"``) when no "
                        "endpoint is set.",
                        color="muted", size="sm",
                    )
                    with ui.flex(justify="start"):
                        ui.date_range_picker(
                            (TODAY + dt.timedelta(days=2),
                             TODAY + dt.timedelta(days=10)),
                        )

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Toggle every axis ; live preview + emitted "
                        "HTML refresh on every change.",
                        color="muted", size="sm",
                    )
                    server_panel()

            # ── Card 7 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    ui.text(
                        "``change`` fires when the range CLOSES (both "
                        "endpoints set) ; pre-pick (start set, end "
                        "still empty) doesn't fire ``change`` in range "
                        "mode. ``focus`` / ``blur`` fire on the start "
                        "OR end field. One instance per event below "
                        "— a single DateRangePicker carries only one "
                        "server ``hx-post``.",
                        color="muted", size="sm",
                    )
                    with ui.flex(wrap=True, gap="md", justify="start"):
                        ui.date_range_picker(on_change=log_change)
                        ui.date_range_picker(on_focus=log_focus)
                        ui.date_range_picker(on_blur=log_blur)
                    ui.divider()
                    events_panel()
                    ui.divider()
                    emitted_html_block(
                        "Emitted HTML (representative — change event)",
                        serialize_html(ui.date_range_picker(
                            on_change=log_change,
                        )),
                    )

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "``value=`` accepts a ``ClientBinding`` to a "
                        "``list`` field — the runtime writes through the "
                        "``[start, end]`` pair on every range "
                        "completion. The echo below joins the array "
                        "live.",
                        color="muted", size="sm",
                    )
                    client = DateRangePickerClient()
                    with ui.vstack(gap="md", align="center"):
                        ui.date_range_picker(client.picked_range)
                        with ui.hstack(gap="sm", align="center"):
                            ui.text("Range:", color="muted",
                                    size="sm")
                            _range_path = client.picked_range.binding_path()
                            ui.text(
                                ClientExpression(
                                    f"({_range_path} || []).join(' → ') "
                                    f"|| '(empty)'"
                                ),
                                size="sm", weight="medium",
                            )
                    ui.divider()
                    emitted_html_block(
                        "Emitted HTML — the wrapper's ``bz-data`` "
                        "seeds ``(vstart, vend)`` from "
                        "``$bz.state.DateRangePickerClient.default"
                        ".picked_range``, and its ``bz-effect`` writes "
                        "the pair back : two-way, without a watcher.",
                        serialize_html(
                            ui.date_range_picker(client.picked_range),
                        ),
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
                            m1 = ui.date_range_picker()
                            with ui.hstack(gap="sm", wrap=True):
                                ui.button("Ouvrir", on_click=m1.open())
                                ui.button("Fermer", variant="outline",
                                          on_click=m1.close())
                                ui.button("Basculer", variant="outline",
                                          on_click=m1.toggle())
                                ui.button("Set 2026-09-01", on_click=m1.set("2026-09-01"))
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
                            lie = DateRangePickerClient(key="ext_binding")
                            with ui.hstack(gap="md", align="center"):
                                ui.date_range_picker(value=lie.picked_range)
                                ui.text(
                                    ClientExpression(
                                        "'Valeur : ' + ($bz.state.DateRangePickerClient"
                                        ".ext_binding.picked_range || '(aucune)')"
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
                            deux = DateRangePickerClient(key="ext_both")
                            m3 = ui.date_range_picker(value=deux.picked_range)
                            with ui.hstack(gap="sm", wrap=True, align="center"):
                                ui.button("Ouvrir", size="xs", on_click=m3.open())
                                ui.button("Set 2026-09-01", size="xs",
                                          on_click=m3.set("2026-09-01"))
                                ui.button("Clear", size="xs", variant="ghost",
                                          on_click=m3.clear())
                                ui.text(
                                    ClientExpression(
                                        "'Store : ' + ($bz.state.DateRangePickerClient"
                                        ".ext_both.picked_range || '(vide)')"
                                    ),
                                    color="muted", size="sm", classes="font-mono",
                                )

                    ui.heading("Client events", level=2)
                    ui.text(
                        "Bind a ``ClientState.client_log`` array to "
                        "the events — the runtime pushes without a server "
                        "round-trip.",
                        color="muted", size="sm",
                    )
                    cevents = DateRangePickerClient()
                    with ui.flex(justify="start"):
                        ui.date_range_picker(
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
                        "Emitted HTML — pure client-side "
                        "``@change=\"...client_log.push(...)\"``, "
                        "no ``hx-post``.",
                        serialize_html(ui.date_range_picker(
                            on_change=cevents.client_log.push("change"),
                        )),
                    )
