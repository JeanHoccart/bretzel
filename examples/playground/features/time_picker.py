"""``TimePicker`` test bench.

Nine cards. ``TimePicker.BINDABLE_PROPS = ("value", "disabled")`` — the
value and the lock; ``step`` / ``min`` / ``max`` / ``color`` / ``size``
stay design-time. ``EVENTS = ("change", "focus", "blur")``.
"""

import datetime as dt

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/time_picker"


SIZES  = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]
STEPS  = [1, 5, 10, 15, 30, 60]


class TimePickerPlayground(PageState):
    value:       str  = field(default="09:30")
    step:        int  = field(default=15)
    min:         str  = field(default="")
    max:         str  = field(default="")
    placeholder: str  = field(default="HH:MM")
    color:       str  = field(default="primary")
    size:        str  = field(default="md")
    disabled:    bool = field(default=False)
    required:    bool = field(default=False)
    clearable:   bool = field(default=True)
    close_on_pick: bool = field(default=True)
    hour_label:  str  = field(default="H")
    minute_label: str = field(default="M")
    name:        str  = field(default="")
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifiers.
    visible: str = field(default="on")
    tooltip: str = field(default="")
    # Event-handler shape.
    on_change_mode: str = field(default="none")


class TimePickerEvents(PageState):
    log: list = field(default_factory=list)


class TimePickerClient(ClientState, persist="memory"):
    picked: str = field(default="14:00")
    locked: bool = field(default=False)


class TimePickerClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


class TimePickerServerEvents(ClientState, persist="memory"):
    picked: str = field(default="08:00")


def log(name: str) -> None:
    state = TimePickerEvents()
    state.log = [*state.log, name]


def log_change(picked: str = "") -> None:
    log(f"change(picked={picked!r})")


def log_focus(picked: str = "") -> None:
    log("focus()")


def log_blur(picked: str = "") -> None:
    log("blur()")


def clear_log() -> None:
    state = TimePickerEvents()
    state.log = []


def server_changed(state: TimePickerPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed control's value
    # into ``state`` (coerced + persisted).
    pass


def playground_change_handler(value: str = "") -> None:
    log(f"playground-server-change(value={value!r})")


_CLIENT_CHANGE_EXPR = "$el.classList.toggle('ring-4')"


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: TimePickerPlayground) -> dict:
    kwargs: dict = {
        "value": state.value,
        "step": state.step,
        "placeholder": state.placeholder,
        "color": state.color,
        "size": state.size,
        "disabled": state.disabled,
        "required": state.required,
        "clearable": state.clearable,
        "close_on_pick": state.close_on_pick,
        "hour_label": state.hour_label,
        "minute_label": state.minute_label,
    }
    # An empty string = do not pass the kwarg.
    if state.min:
        kwargs["min"] = state.min
    if state.max:
        kwargs["max"] = state.max
    if state.name:
        kwargs["name"] = state.name
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
    if state.on_change_mode == "server":
        kwargs["on_change"] = playground_change_handler
    elif state.on_change_mode == "client":
        kwargs["on_change"] = _CLIENT_CHANGE_EXPR
    elif state.on_change_mode == "both":
        kwargs["on_change"] = [playground_change_handler,
                               _CLIENT_CHANGE_EXPR]
    return kwargs


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[TimePickerPlayground])
def server_panel() -> None:
    state = TimePickerPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("value"):
            ui.input(value=state.value, placeholder="09:30",
                     on_change=server_changed)
        with control("step (minutes)"):
            ui.select(value=state.step,
                      options=[(s, str(s)) for s in STEPS],
                      on_change=server_changed)
        with control('min (empty = no floor)'):
            ui.input(value=state.min, placeholder="09:00",
                     on_change=server_changed)
        with control('max (empty = no ceiling)'):
            ui.input(value=state.max, placeholder="18:00",
                     on_change=server_changed)
        with control("placeholder"):
            ui.input(value=state.placeholder, on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("hour_label / minute_label"), ui.hstack(gap="xs"):
            ui.input(value=state.hour_label, on_change=server_changed)
            ui.input(value=state.minute_label, on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control("required"):
            ui.switch(checked=state.required, on_change=server_changed)
        with control("clearable"):
            ui.switch(checked=state.clearable, on_change=server_changed)
        with control("close_on_pick"):
            ui.switch(checked=state.close_on_pick, on_change=server_changed)
        with control("name (overrides autoname)"):
            ui.input(value=state.name, placeholder="start_at",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="!max-w-xs",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-time",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder='Start time',
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="max-width: 200px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=time",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Quand ?",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)
        with control("on_change mode"):
            ui.select(value=state.on_change_mode,
                      options=[("none", "None (no handler)"),
                               ("server", "Server callable"),
                               ("client", "Client string"),
                               ("both", "Both (list)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    with ui.flex(classes="max-w-xs"):
        ui.time_picker(**kwargs)

    ui.divider()

    emitted_html_block(
        "Emitted HTML (TimePicker)",
        serialize_html(ui.time_picker(**kwargs)),
    )


@refreshable(deps=[TimePickerEvents])
def events_panel() -> None:
    state = TimePickerEvents()

    ui.text(
        'All three events are wired — but on THREE instances, and that is'
            ' structural: an element carries only ONE ``hx-post``, so two '
            'server handlers on the same picker raise at construct time '
            '(``HandlerError``). To combine several on a single field, the '
            'second one goes through a client expression.',
        color="muted", size="sm",
    )
    ui.text(
        'Where they leave from: ``change`` from the hidden input (the '
            'form-data carrier); ``focus`` and ``blur`` are relocated onto '
            'the editable field — the root is a non-focusable ``<div>``, and '
            'those two events DO NOT BUBBLE, so a handler left there could '
            'structurally never fire.',
        color="muted", size="sm",
    )

    picked = TimePickerServerEvents()
    with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
        with control("on_change"):
            ui.time_picker(value=picked.picked, on_change=log_change)
        with control("on_focus"):
            ui.time_picker(dt.time(10, 0), on_focus=log_focus)
        with control("on_blur"):
            ui.time_picker(dt.time(11, 0), on_blur=log_blur)

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)", color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)

    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}",
                        color="muted", size="sm", classes="font-mono")
    else:
        ui.text('(no events yet — click the field, then a time)',
                color="muted", size="sm")

    ui.divider()

    emitted_html_block(
        'Emitted HTML (TimePicker with on_change) — the hx-* bundle is '
            'relocated onto the hidden input by relocate_server_action, which'
            ' reads hx-trigger to pick the carrier: an on_focus= would leave '
            'from the editable field, the only element that receives focus.',
        serialize_html(
            ui.time_picker(value=picked.picked, on_change=log_change)
        ),
    )


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Time picker", level=1)
        ui.text(
            'A time field: an editable field and a popover with two '
                'snapping columns. The value is an "HH:MM" string — zero-'
                'padded, so it sorts the way it reads. No calendar is '
                'involved, and no native widget either: an <input '
                'type="time"> cannot be themed and changes shape from browser'
                ' to browser.',
            color="muted",
        )

        # ── Card 1 — Reference ──────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Reference", level=2)
            ui.text("Visual scan of every prop.",
                    color="muted", size="sm")

            ui.heading("Basic", level=3)
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                ui.time_picker(dt.time(9, 30))
                ui.time_picker()               # vide
                ui.time_picker(dt.time(23, 45))

            ui.heading("step", level=3)
            ui.text(
                'How many minutes exist. 15 by default — step=1 gives all'
                    ' sixty, and that is when the column really scrolls.',
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                for s in (1, 5, 15):
                    with ui.vstack(gap="xs"):
                        ui.text(f"step={s}", color="muted", size="xs")
                        ui.time_picker(dt.time(10, 0), step=s)

            ui.heading("min / max", level=3)
            ui.text(
                'Out-of-bounds hours are greyed out. A subtlety: an HOUR '
                    'is only excluded if none of its minutes fits — otherwise'
                    ' min="09:30" would grey out the whole of 09 and 09:45 '
                    'would be unreachable.',
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("min=09:00 max=18:00",
                            color="muted", size="xs")
                    ui.time_picker(dt.time(9, 0),
                                   min="09:00", max="18:00")
                with ui.vstack(gap="xs"):
                    ui.text("min=09:30 (09:45 doit rester actif)",
                            color="muted", size="xs")
                    ui.time_picker(dt.time(9, 45), min="09:30")
                with ui.vstack(gap="xs"):
                    ui.text("max=12:00", color="muted", size="xs")
                    ui.time_picker(dt.time(8, 0), max="12:00")

            ui.heading("Sizes", level=3)
            with ui.grid(cols={"base": 1, "md": 5}, gap="md"):
                for s in SIZES:
                    with ui.vstack(gap="xs"):
                        ui.text(f"size={s}", color="muted", size="xs")
                        ui.time_picker(dt.time(14, 15), size=s)

            ui.heading("Colors", level=3)
            with ui.grid(cols={"base": 1, "md": 4}, gap="md"):
                for c in COLORS:
                    with ui.vstack(gap="xs"):
                        ui.text(c, color="muted", size="xs")
                        ui.time_picker(dt.time(14, 15), color=c)

            ui.heading("disabled / required / clearable", level=3)
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("disabled", color="muted", size="xs")
                    ui.time_picker(dt.time(9, 0), disabled=True)
                with ui.vstack(gap="xs"):
                    ui.text("required", color="muted", size="xs")
                    ui.time_picker(dt.time(9, 0), required=True)
                with ui.vstack(gap="xs"):
                    ui.text('clearable=False (no ×)',
                            color="muted", size="xs")
                    ui.time_picker(dt.time(9, 0), clearable=False)

            ui.heading("close_on_pick", level=3)
            ui.text(
                'At True (the default) the panel closes when you click a '
                    'MINUTE, not an hour — the reading order is hour then '
                    'minute, and closing on the hour would cut the gesture in'
                    ' two.',
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("close_on_pick=True", color="muted",
                            size="xs")
                    ui.time_picker(dt.time(9, 0))
                with ui.vstack(gap="xs"):
                    ui.text("close_on_pick=False", color="muted",
                            size="xs")
                    ui.time_picker(dt.time(9, 0),
                                   close_on_pick=False)

        # ── Card 2 — Slots ──────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Slots", level=2)
            ui.text(
                'The component has no slot in the ``with`` sense: its '
                    "only content surface is textual — the field's "
                    'placeholder and the two column headers, for i18n.',
                color="muted", size="sm",
            )
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text('default (H / M)', color="muted",
                            size="xs")
                    ui.time_picker(dt.time(9, 30))
                with ui.vstack(gap="xs"):
                    ui.text('i18n: placeholder + headers',
                            color="muted", size="xs")
                    ui.time_picker(dt.time(9, 30),
                                   placeholder="Heure…",
                                   hour_label="Heures",
                                   minute_label="Min")

        # ── Card 3 — Edge cases ─────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Edge cases", level=2)
            ui.text("Edge inputs and exotic combinations.",
                    color="muted", size="sm")

            ui.heading('Free typing re-parsed on blur', level=3)
            ui.text(
                'Type 9h30, 9:30, 9.30, 930 or just 9, then leave the '
                    'field — everything becomes 09:30. Anything that is not a'
                    ' time clears.',
                color="muted", size="xs",
            )
            with ui.flex(classes="max-w-xs"):
                ui.time_picker(placeholder="tapez 930 puis Tab")

            ui.heading("Midnight and 23:59", level=3)
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                ui.time_picker(dt.time(0, 0))
                ui.time_picker(dt.time(23, 59), step=1)

            ui.heading('step=60 (a single possible minute)',
                       level=3)
            with ui.flex(classes="max-w-xs"):
                ui.time_picker(dt.time(14, 0), step=60)

            ui.heading('min == max (a single slot)', level=3)
            with ui.flex(classes="max-w-xs"):
                ui.time_picker(dt.time(12, 0),
                               min="12:00", max="12:00")

            ui.heading("Valeur hors bornes", level=3)
            ui.text('The value stays displayed — what the server sent is never '
                'rewritten.',
                    color="muted", size="xs")
            with ui.flex(classes="max-w-xs"):
                ui.time_picker(dt.time(3, 0),
                               min="09:00", max="18:00")

            ui.heading('Inside a narrow cell', level=3)
            with ui.grid(cols={"base": 1, "md": 4}, gap="md"):
                ui.time_picker(dt.time(9, 30))
                ui.text("Voisine.", color="muted")
                ui.text("Voisine.", color="muted")
                ui.text("Voisine.", color="muted")

        # ── Card 4 — Composability ──────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Composability", level=2)
            ui.text('The picker in its usual contexts.',
                    color="muted", size="sm")

            ui.heading('Inside a form_field', level=3)
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.form_field(label='Start time',
                                   hint='Slot opening'):
                    ui.time_picker(dt.time(9, 0), min="08:00")
                with ui.form_field(label="Heure de fin"):
                    ui.time_picker(dt.time(18, 0), max="20:00")

            ui.heading('One slot, two fields', level=3)
            ui.text(
                'The most common use case. Note: the cross constraint '
                    '(end.min = start) is NOT automatic — min/max are not '
                    'bindable here, unlike in the date family.',
                color="muted", size="xs",
            )
            with ui.hstack(gap="sm", align="center"):
                ui.time_picker(dt.time(9, 0), size="sm")
                ui.text("→", color="muted")
                ui.time_picker(dt.time(17, 30), size="sm")

            ui.heading('explicit name= (escape hatch)', level=3)
            ui.text(
                'Autoname covers the bound case (``value=state.x`` '
                    'derives ``name="x"``). For a picker with a literal value'
                    ' that must still post, ``name=`` is the only way to have'
                    ' a form carrier without a binding.',
                color="muted", size="xs",
            )
            with ui.flex(classes="max-w-xs"):
                ui.time_picker(dt.time(9, 0), name="start_at")

            ui.heading('Inside a ui.dialog', level=3)
            with ui.dialog(title="Planifier", width="md") as dlg, \
                            ui.vstack():
                with ui.form_field(label='At what time?'):
                    ui.time_picker(dt.time(14, 0))
                ui.text(
                    'The panel is anchored in fixed position, so it '
                        "escapes the dialog's overflow.",
                    color="muted", size="xs",
                )
            ui.button('Open the dialog', on_click=dlg.open())

        # ── Card 5 — A11y ───────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("A11y", level=2)
            ui.text(
                'The field stays a real ``<input type=text>``: EVERYTHING'
                    ' can be done from the keyboard without ever opening the '
                    'panel, which is the fastest route for anyone who knows '
                    'their time. The two columns are labelled '
                    '``role=listbox``es, and every cell a real ``<button>`` —'
                    ' hence reachable with Tab and genuinely ``disabled`` out'
                    ' of bounds, not merely greyed. Escape and a click '
                    'outside close it.',
                color="muted", size="sm",
            )
            with ui.flex(classes="max-w-xs"):
                ui.time_picker(dt.time(9, 30),
                               min="09:00", max="18:00",
                               aria_label='Appointment time')

        # ── Card 6 — Server playground ──────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server playground", level=2)
            ui.text(
                "Every TimePicker prop AND every escape hatch is "
                "wired to a control ; the preview AND the "
                "emitted HTML both refresh on every change.",
                color="muted", size="sm",
            )
            server_panel()

        # ── Card 7 — Server events ──────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server events", level=2)
            events_panel()

        # ── Card 8 — Client playground ──────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Client playground", level=2)
            ui.text(
                "Mirror of BINDABLE_PROPS = ('value', 'disabled'). The "
                    'value is bound to a ClientState: the field, the panel '
                    'and the mirror below all read the SAME store cell, with '
                    'no round trip.',
                color="muted", size="sm",
            )
            client = TimePickerClient()
            with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                with control("value (bound)"):
                    ui.time_picker(value=client.picked)
                with control("disabled (bound)"):
                    ui.switch(checked=client.locked,
                              label="Verrouiller")

            ui.divider()

            with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                with control('the same one, driven by the switch'):
                    ui.time_picker(value=client.picked,
                                   disabled=client.locked)
                with control("miroir"):
                    ui.text(
                        ClientExpression(
                            "'value: ' + "
                            "($bz.state.TimePickerClient"
                            ".default.picked || '(empty)')"
                        ),
                        color="muted", size="sm",
                        classes="font-mono",
                    )

            ui.divider()

            emitted_html_block(
                'Emitted HTML — everything addresses the store cell '
                    'directly: the field through bz-model, the hidden input '
                    'through bz-attr:value, and the 28 cells through the '
                    "scope's _read/_write.",
                serialize_html(
                    ui.time_picker(value=client.picked,
                                   disabled=client.locked)
                ),
            )

        # ── Card 9 — Client events ──────────────────────────────
        with ui.card(), ui.vstack():
            # ── External controls — the 3 modes ────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes", level=2)
                    ui.text(
                        'The seven methods that arrived on 2026-09-03. A '
                            'picker is TWO natures at once: an anchored panel'
                            ' (like `dialog`) and a field carrying a value '
                            '(like `input`). Its surface is therefore the '
                            'union of the two vocabularies its neighbours '
                            'already fixed — nothing invented.',
                        color="muted", size="sm",
                    )

                    # ── Mode 1 — Imperative only ────────────────────
                    ui.heading("Mode 1 — Imperative only (default for "
                               "one-off writes)", level=3)
                    ui.text(
                        'No ClientState. `.open()` / `.close()` / '
                            '`.toggle()` dispatch `bz-open` / `bz-close` / '
                            '`bz-toggle`, which the root catches; `.set()` '
                            'dispatches `bz-set`. `.focus()` targets the '
                            'VISIBLE field — not the hidden carrier, which is'
                            " the component's first `<input>` and never takes"
                            ' focus.',
                        color="muted", size="sm",
                    )
                    m1 = ui.time_picker()
                    with ui.hstack(gap="sm", wrap=True):
                        ui.button("Ouvrir", on_click=m1.open())
                        ui.button("Fermer", variant="outline",
                                  on_click=m1.close())
                        ui.button("Basculer", variant="outline",
                                  on_click=m1.toggle())
                        ui.button("Set 14:30", on_click=m1.set("14:30"))
                        ui.button("Clear", variant="ghost",
                                  on_click=m1.clear())
                        ui.button("Focus", variant="ghost",
                                  on_click=m1.focus())
                        ui.button("Blur", variant="ghost",
                                  on_click=m1.blur())

                    ui.divider()

                    # ── Mode 2 — ClientBinding only ─────────────────
                    ui.heading("Mode 2 — ClientBinding only (when another "
                               "component must read or react)", level=3)
                    ui.text(
                        '`value=binding`: the value lives in the store, '
                            'so a neighbour reads it with no round trip.',
                        color="muted", size="sm",
                    )
                    lie = TimePickerClient(key="ext_binding")
                    with ui.hstack(gap="md", align="center"):
                        ui.time_picker(value=lie.picked)
                        ui.text(
                            ClientExpression(
                                "'Valeur : ' + ($bz.state.TimePickerClient"
                                ".ext_binding.picked || '(aucune)')"
                            ),
                            color="muted", size="sm", classes="font-mono",
                        )

                    ui.divider()

                    # ── Mode 3 — Both ───────────────────────────────
                    ui.heading("Mode 3 — Both (write-through)", level=3)
                    ui.text(
                        'A binding supplied AND the methods called. '
                            '`.set()` detects the binding and writes INTO it '
                            '— the DOM dispatch is not used, the source of '
                            'truth stays single. `.open()` stays a dispatch: '
                            'the panel is not a value.',
                        color="muted", size="sm",
                    )
                    deux = TimePickerClient(key="ext_both")
                    m3 = ui.time_picker(value=deux.picked)
                    with ui.hstack(gap="sm", wrap=True, align="center"):
                        ui.button("Ouvrir", size="xs", on_click=m3.open())
                        ui.button("Set 14:30", size="xs",
                                  on_click=m3.set("14:30"))
                        ui.button("Clear", size="xs", variant="ghost",
                                  on_click=m3.clear())
                        ui.text(
                            ClientExpression(
                                "'Store : ' + ($bz.state.TimePickerClient"
                                ".ext_both.picked || '(empty)')"
                            ),
                            color="muted", size="sm", classes="font-mono",
                        )

            ui.heading("Client events", level=2)
            ui.text('change wired to a client expression that pushes the new time'
                ' onto a ClientState. Zero network.',
                    color="muted", size="sm")
            cevents = TimePickerClientEvents()
            _new_value = ClientExpression("$event.target.value")
            with ui.flex(classes="max-w-xs"):
                ui.time_picker(
                    dt.time(9, 0),
                    on_change=cevents.log.push(_new_value),
                )

            ui.divider()

            with ui.hstack(justify="between", align="center"):
                ui.text("Live log (client-reactive)",
                        color="muted", size="sm")
                ui.button("Clear", variant="ghost", size="xs",
                          on_click=cevents.log.clear())

            ui.divider()

            ui.text(
                ClientExpression(
                    '($bz.state.TimePickerClientEvents.default.log'
                    ' || []).join("\\n") || "(no events yet)"'
                ),
                color="muted", size="sm",
                classes="font-mono whitespace-pre",
            )

            ui.divider()

            emitted_html_block(
                'Emitted HTML — the bz-on:change handler lives on the '
                    'hidden input, the only carrier that exposes a name and a'
                    ' value.',
                serialize_html(
                    ui.time_picker(
                        dt.time(9, 0),
                        on_change=cevents.log.push(_new_value),
                    )
                ),
            )
