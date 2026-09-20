"""``MonthPicker`` test bench.

Sept cartes. ``MonthPicker.BINDABLE_PROPS = ("value", "disabled")``.
``EVENTS = ("change", "focus", "blur")``. Enveloppe mince sur
``_picker_field`` + ``ui.calendar(mode="month")``.
"""

import datetime as dt

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/month_picker"

SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]

TODAY = dt.date.today()
SEED = "2026-08"


class MonthPickerPlayground(PageState):
    value:       str  = field(default=SEED)
    placeholder: str  = field(default="YYYY-MM")
    color:       str  = field(default="primary")
    size:        str  = field(default="md")
    disabled:    bool = field(default=False)
    required:    bool = field(default=False)
    clearable:   bool = field(default=True)
    close_on_pick: bool = field(default=True)
    name:        str  = field(default="")
    minimum:     str  = field(default="")
    maximum:     str  = field(default="")
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")
    on_change_mode: str = field(default="none")


class MonthPickerEvents(PageState):
    log: list = field(default_factory=list)


class MonthPickerClient(ClientState, persist="memory"):
    picked: str = field(default=SEED)
    locked: bool = field(default=False)


class MonthPickerClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


class MonthPickerServerEvents(ClientState, persist="memory"):
    picked: str = field(default=SEED)


def log(name: str) -> None:
    state = MonthPickerEvents()
    state.log = [*state.log, name]


def log_change(picked: str = "") -> None:
    log(f"change(picked={picked!r})")


def log_focus(picked: str = "") -> None:
    log("focus()")


def log_blur(picked: str = "") -> None:
    log("blur()")


def clear_log() -> None:
    state = MonthPickerEvents()
    state.log = []


def server_changed(state: MonthPickerPlayground) -> None:
    # A typed param -> the dispatcher hydrates the changed control's value.
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


def build_preview(state: MonthPickerPlayground) -> dict:
    kwargs: dict = {
        "value": state.value,
        "placeholder": state.placeholder,
        "color": state.color,
        "size": state.size,
        "disabled": state.disabled,
        "required": state.required,
        "clearable": state.clearable,
        "close_on_pick": state.close_on_pick,
    }
    if state.minimum:
        kwargs["min"] = state.minimum
    if state.maximum:
        kwargs["max"] = state.maximum
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


@refreshable(deps=[MonthPickerPlayground])
def server_panel() -> None:
    state = MonthPickerPlayground()
    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("value"):
            ui.input(value=state.value, placeholder=SEED,
                     on_change=server_changed)
        with control("min"):
            ui.input(value=state.minimum, placeholder="2026-03",
                     on_change=server_changed)
        with control("max"):
            ui.input(value=state.maximum, placeholder="2026-12",
                     on_change=server_changed)
        with control("placeholder"):
            ui.input(value=state.placeholder, on_change=server_changed)
        with control("color"):
            ui.select(value=state.color, options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size, options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control("required"):
            ui.switch(checked=state.required, on_change=server_changed)
        with control("clearable"):
            ui.switch(checked=state.clearable, on_change=server_changed)
        with control("close_on_pick"):
            ui.switch(checked=state.close_on_pick, on_change=server_changed)
        with control("name (overrides autoname)"):
            ui.input(value=state.name, placeholder="periode",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="!max-w-xs",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-picker",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="max-width: 220px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=picker",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)
        with control("on_change mode"):
            ui.select(value=state.on_change_mode,
                      options=[("none", "None"), ("server", "Server callable"),
                               ("client", "Client string"),
                               ("both", "Both (list)")],
                      on_change=server_changed)

    ui.divider()
    kwargs = build_preview(state)
    with ui.flex(classes="max-w-xs"):
        ui.month_picker(**kwargs)
    ui.divider()
    emitted_html_block("Emitted HTML (MonthPicker)",
                       serialize_html(ui.month_picker(**kwargs)))


@refreshable(deps=[MonthPickerEvents])
def events_panel() -> None:
    state = MonthPickerEvents()
    ui.text(
        'All three events, on THREE instances: an element carries only '
            'ONE hx-post, so two server handlers on the same picker raise at '
            'construct time. change leaves from the hidden input; focus and '
            'blur are relocated onto the editable field, the root being a '
            'non-focusable <div> those two events do not bubble from.',
        color="muted", size="sm",
    )
    picked = MonthPickerServerEvents()
    with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
        with control("on_change"):
            ui.month_picker(value=picked.picked, on_change=log_change)
        with control("on_focus"):
            ui.month_picker(SEED, on_focus=log_focus)
        with control("on_blur"):
            ui.month_picker(SEED, on_blur=log_blur)

    ui.divider()
    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)", color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)
    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}", color="muted", size="sm",
                        classes="font-mono")
    else:
        ui.text("(no events yet)", color="muted", size="sm")

    ui.divider()
    emitted_html_block(
        "Emitted HTML (MonthPicker with on_change)",
        serialize_html(ui.month_picker(value=picked.picked, on_change=log_change)),
    )


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Month picker", level=1)
        ui.text('A MONTH field: the value is a 2026-08 string, zero-padded hence '
            'sortable as it reads. The panel is a ui.calendar(mode=month) - a'
            ' year grid, not days.', color="muted")

        with ui.card(), ui.vstack():
            ui.heading("Reference", level=2)
            ui.text("Visual scan of every prop.",
                    color="muted", size="sm")

            ui.heading("Basic", level=3)
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                ui.month_picker(SEED)
                ui.month_picker()
                ui.month_picker(SEED, clearable=False)

            ui.heading("min / max", level=3)
            ui.text('min / max are truncated to the month: a min on 15 March does'
                ' NOT forbid March, part of the month staying allowed.', color="muted", size="xs")
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                ui.month_picker(SEED, min="2026-03", max="2026-12")
                ui.month_picker(SEED, max="2026-12")

            ui.heading("Sizes", level=3)
            with ui.grid(cols={"base": 1, "md": 5}, gap="md"):
                for s in SIZES:
                    with ui.vstack(gap="xs"):
                        ui.text(f"size={s}", color="muted", size="xs")
                        ui.month_picker(SEED, size=s)

            ui.heading("Colors", level=3)
            with ui.grid(cols={"base": 1, "md": 4}, gap="md"):
                for c in COLORS:
                    with ui.vstack(gap="xs"):
                        ui.text(c, color="muted", size="xs")
                        ui.month_picker(SEED, color=c)


            ui.heading("i18n + options", level=3)
            ui.text(
                '``month_names`` translates the grid; '
                    '``close_on_pick=False`` keeps the panel open to compare '
                    'several months; ``name=`` is the escape hatch when the '
                    'value is literal and must still be posted.',
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("month_names=FR", color="muted",
                            size="xs")
                    ui.month_picker(SEED, month_names=["Janvier", "Fevrier", "Mars", "Avril", "Mai", "Juin",
          "Juillet", "Aout", "Septembre", "Octobre",
          "Novembre", "Decembre"])
                    with ui.vstack(gap="xs"):
                        ui.text("close_on_pick=False", color="muted",
                                size="xs")
                        ui.month_picker(SEED, close_on_pick=False)
                    with ui.vstack(gap="xs"):
                        ui.text('name="periode"', color="muted",
                                size="xs")
                        ui.month_picker(SEED, name="periode")

                ui.heading("disabled / required", level=3)
                with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                    ui.month_picker(SEED, disabled=True)
                    ui.month_picker(SEED, required=True)

        with ui.card(), ui.vstack():
            ui.heading("Edge cases", level=2)
            ui.text('Type 2026-08, 08/2026 or 2026/08 then leave the field: '
                'everything becomes 2026-08. Anything that is not a month '
                'clears.', color="muted", size="sm")
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("saisie libre", color="muted", size="xs")
                    ui.month_picker(placeholder="tapez 08/2026 puis Tab")
                with ui.vstack(gap="xs"):
                    ui.text("cellule etroite", color="muted",
                            size="xs")
                    ui.month_picker(SEED, size="sm")
                ui.text("Voisine.", color="muted")

        with ui.card(), ui.vstack():
            ui.heading("Composability", level=2)
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.form_field(label="Debut", hint="Periode de facturation"):
                    ui.month_picker(SEED)
                with ui.form_field(label="Fin"):
                    ui.month_picker(SEED)
            ui.heading('Inside a ui.dialog', level=3)
            with ui.dialog(title="Planifier", width="md") as dlg, \
                        ui.vstack():
                with ui.form_field(label="Quand ?"):
                    ui.month_picker(SEED)
                ui.text('The panel is anchored in fixed position, so it escapes '
                    "the dialog's overflow.",
                        color="muted", size="xs")
            ui.button('Open the dialog', on_click=dlg.open())

        with ui.card(), ui.vstack():
            ui.heading("A11y", level=2)
            ui.text('The field stays a real text input: everything can be done '
                'from the keyboard without opening the panel. The 12 cells '
                'are real buttons, hence reachable with Tab and genuinely '
                'disabled out of bounds. Escape and a click outside close it.', color="muted", size="sm")
            with ui.flex(classes="max-w-xs"):
                ui.month_picker(SEED, aria_label="Mois de facturation")

        with ui.card(), ui.vstack():
            ui.heading("Server playground", level=2)
            server_panel()

        with ui.card(), ui.vstack():
            ui.heading("Server events", level=2)
            events_panel()

        with ui.card(), ui.vstack():
            ui.heading("Client playground", level=2)
            ui.text("Mirror of BINDABLE_PROPS = ('value', 'disabled'). Everything"
                ' addresses the same store cell, with no round trip.',
                    color="muted", size="sm")
            client = MonthPickerClient()
            with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                with control("value (bound)"):
                    ui.month_picker(value=client.picked)
                with control("disabled (bound)"):
                    ui.switch(checked=client.locked,
                              label="Verrouiller")
            ui.divider()
            with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                with control('the same one, driven by the switch'):
                    ui.month_picker(value=client.picked,
                               disabled=client.locked)
                with control("miroir"):
                    ui.text(
                        ClientExpression(
                            "'value: ' + "
                            "($bz.state.MonthPickerClient.default.picked "
                            "|| '(empty)')"
                        ),
                        color="muted", size="sm",
                        classes="font-mono",
                    )
            ui.divider()
            emitted_html_block(
                'Emitted HTML - the bound value is read by the field, the'
                    ' hidden input and the internal calendar.',
                serialize_html(ui.month_picker(value=client.picked,
                                          disabled=client.locked)),
            )

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
                    m1 = ui.month_picker()
                    with ui.hstack(gap="sm", wrap=True):
                        ui.button("Ouvrir", on_click=m1.open())
                        ui.button("Fermer", variant="outline",
                                  on_click=m1.close())
                        ui.button("Basculer", variant="outline",
                                  on_click=m1.toggle())
                        ui.button("Set 2026-09", on_click=m1.set("2026-09"))
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
                    lie = MonthPickerClient(key="ext_binding")
                    with ui.hstack(gap="md", align="center"):
                        ui.month_picker(value=lie.picked)
                        ui.text(
                            ClientExpression(
                                "'Valeur : ' + ($bz.state.MonthPickerClient"
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
                    deux = MonthPickerClient(key="ext_both")
                    m3 = ui.month_picker(value=deux.picked)
                    with ui.hstack(gap="sm", wrap=True, align="center"):
                        ui.button("Ouvrir", size="xs", on_click=m3.open())
                        ui.button("Set 2026-09", size="xs",
                                  on_click=m3.set("2026-09"))
                        ui.button("Clear", size="xs", variant="ghost",
                                  on_click=m3.clear())
                        ui.text(
                            ClientExpression(
                                "'Store : ' + ($bz.state.MonthPickerClient"
                                ".ext_both.picked || '(empty)')"
                            ),
                            color="muted", size="sm", classes="font-mono",
                        )

            ui.heading("Client events", level=2)
            ui.text('change wired to a client expression. Zero network.', color="muted", size="sm")
            cevents = MonthPickerClientEvents()
            _new = ClientExpression("$event.target.value")
            with ui.flex(classes="max-w-xs"):
                ui.month_picker(SEED, on_change=cevents.log.push(_new))
            ui.divider()
            with ui.hstack(justify="between", align="center"):
                ui.text("Live log (client-reactive)",
                        color="muted", size="sm")
                ui.button("Clear", variant="ghost", size="xs",
                          on_click=cevents.log.clear())
            ui.divider()
            ui.text(
                ClientExpression(
                    "($bz.state.MonthPickerClientEvents.default.log"
                    " || []).join(String.fromCharCode(10)) || '(no events yet)'"
                ),
                color="muted", size="sm",
                classes="font-mono whitespace-pre",
            )
            ui.divider()
            emitted_html_block(
                'Emitted HTML - the bz-on:change handler lives on the '
                    'hidden input, the only carrier with a name and a value.',
                serialize_html(
                    ui.month_picker(SEED, on_change=cevents.log.push(_new))
                ),
            )
