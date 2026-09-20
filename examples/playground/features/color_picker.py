"""``ColorPicker`` test bench.

Nine cards, `.claude/bretzel/playground-pattern.md`'s template.
``ColorPicker.BINDABLE_PROPS = ("value", "disabled")`` — the colour and
the lock; ``clearable`` / ``placeholder`` / ``color`` / ``size`` stay
design-time. ``EVENTS = ("change", "focus", "blur")``. No imperative API,
so no §7 card — like the three date pickers.

⚠️ This component has **no** ``swatches=``: its grid comes from the
theme's palette. The bench shows it rather than saying it — it is
``Theme(palette=…)`` that decides, and therefore the same grid
everywhere.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/color_picker"


SIZES  = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]


class ColorPickerPlayground(PageState):
    value:       str  = field(default="#2f5fd0")
    placeholder: str  = field(default="#rrggbb")
    color:       str  = field(default="primary")
    size:        str  = field(default="md")
    disabled:    bool = field(default=False)
    required:    bool = field(default=False)
    clearable:   bool = field(default=True)
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


class ColorPickerEvents(PageState):
    log: list = field(default_factory=list)


class ColorPickerClient(ClientState, persist="memory"):
    picked: str  = field(default="#8e4ec6")
    locked: bool = field(default=False)


class ColorPickerClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


class ColorPickerServerEvents(ClientState, persist="memory"):
    picked: str = field(default="#30a46c")


def log(name: str) -> None:
    state = ColorPickerEvents()
    state.log = [*state.log, name]


def log_change(picked: str = "") -> None:
    log(f"change(picked={picked!r})")


def log_focus(picked: str = "") -> None:
    log("focus()")


def log_blur(picked: str = "") -> None:
    log("blur()")


def clear_log() -> None:
    state = ColorPickerEvents()
    state.log = []


def server_changed(state: ColorPickerPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed control's value
    # into ``state`` (coerced + persisted). ``server_panel`` declares
    # deps=[ColorPickerPlayground], so it re-renders on its own.
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


def build_preview(state: ColorPickerPlayground) -> dict:
    kwargs: dict = {
        "value": state.value,
        "placeholder": state.placeholder,
        "color": state.color,
        "size": state.size,
        "disabled": state.disabled,
        "required": state.required,
        "clearable": state.clearable,
    }
    # An empty string = do not pass the kwarg, otherwise the component's
    # default is never the one being tested.
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


@refreshable(deps=[ColorPickerPlayground])
def server_panel() -> None:
    state = ColorPickerPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("value"):
            ui.input(value=state.value, placeholder="#2f5fd0",
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
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control("required"):
            ui.switch(checked=state.required, on_change=server_changed)
        with control("clearable"):
            ui.switch(checked=state.clearable, on_change=server_changed)
        with control("name (overrides autoname)"):
            ui.input(value=state.name, placeholder="brand",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="!max-w-xs",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-color",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Couleur de marque",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="max-width: 200px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=color",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Quelle teinte ?",
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
        ui.color_picker(**kwargs)

    ui.divider()

    emitted_html_block(
        "Emitted HTML (ColorPicker)",
        serialize_html(ui.color_picker(**kwargs)),
    )


@refreshable(deps=[ColorPickerEvents])
def events_panel() -> None:
    state = ColorPickerEvents()

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
            'form-data carrier), so it fires on a swatch click just as much '
            'as on typing; ``focus`` and ``blur`` are relocated onto the '
            'editable field — the root is a non-focusable ``<div>``, and '
            'those two events DO NOT BUBBLE, so a handler left there could '
            'structurally never fire.',
        color="muted", size="sm",
    )

    picked = ColorPickerServerEvents()
    with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
        with control("on_change"):
            ui.color_picker(value=picked.picked, on_change=log_change)
        with control("on_focus"):
            ui.color_picker("#e5484d", on_focus=log_focus)
        with control("on_blur"):
            ui.color_picker("#f76b15", on_blur=log_blur)

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)",
                color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)

    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}",
                        color="muted", size="sm", classes="font-mono")
    else:
        ui.text('(no events yet — click the field, then a swatch)',
                color="muted", size="sm")

    ui.divider()

    emitted_html_block(
        'Emitted HTML (ColorPicker with on_change) — the hx-* bundle is '
            'relocated onto the hidden input by relocate_server_action, which'
            ' reads hx-trigger to pick the carrier: an on_focus= would leave '
            'from the editable field, the only element that receives focus.',
        serialize_html(
            ui.color_picker(value=picked.picked, on_change=log_change)
        ),
    )


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Color picker", level=1)
        ui.text(
            'A colour field: a swatch rendering the value, an editable '
                "hex code, and a panel offering the theme's palette. The "
                'value is a "#rrggbb" string — what a Theme(semantic=…) '
                'expects and what form data carries as is. No native widget: '
                'an <input type="color"> cannot be themed, changes shape from'
                ' browser to browser, and does not know the palette — which '
                'is precisely what one wants to pick nine times out of ten.',
            color="muted",
        )

        # ── Card 1 — Reference ──────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Reference", level=2)
            ui.text("Visual scan of every prop.",
                    color="muted", size="sm")

            ui.heading("Basic", level=3)
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                ui.color_picker("#2f5fd0")
                ui.color_picker()              # vide → le damier
                ui.color_picker("#ffe629")

            ui.heading("placeholder", level=3)
            ui.text(
                "The component's only text, and it serves twice: the "
                    "empty field's prompt AND its fallback ``aria-label``. "
                    '"#rrggbb" by default, because it states the expected '
                    'SHAPE.',
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text('default', color="muted", size="xs")
                    ui.color_picker()
                with ui.vstack(gap="xs"):
                    ui.text('placeholder="Pick a shade…"',
                            color="muted", size="xs")
                    ui.color_picker(placeholder='Pick a shade…')

            ui.heading("Sizes", level=3)
            with ui.grid(cols={"base": 1, "md": 5}, gap="md"):
                for s in SIZES:
                    with ui.vstack(gap="xs"):
                        ui.text(f"size={s}", color="muted", size="xs")
                        ui.color_picker("#8e4ec6", size=s)

            ui.heading("Colors", level=3)
            ui.text(
                '``color=`` does NOT change the chosen colour — it is the'
                    " component's accent: the focus ring, the hover border, "
                    'the outline of the selected swatch. The value itself is '
                    'visible in the swatch.',
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 4}, gap="md"):
                for c in COLORS:
                    with ui.vstack(gap="xs"):
                        ui.text(c, color="muted", size="xs")
                        ui.color_picker("#12a594", color=c)

            ui.heading("disabled / required / clearable", level=3)
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("disabled", color="muted", size="xs")
                    ui.color_picker("#0090ff", disabled=True)
                with ui.vstack(gap="xs"):
                    ui.text("required", color="muted", size="xs")
                    ui.color_picker("#0090ff", required=True)
                with ui.vstack(gap="xs"):
                    ui.text('clearable=True (the × when filled)',
                            color="muted", size="xs")
                    ui.color_picker("#0090ff", clearable=True)

            ui.heading("name", level=3)
            ui.text(
                'The name of the hidden field that carries the colour in '
                    'form data. Bound to a state it derives itself; ``name=``'
                    ' is the escape hatch for a literal value.',
                color="muted", size="xs",
            )
            with ui.flex(classes="max-w-xs"):
                ui.color_picker("#d6409f", name="brand")

        # ── Card 2 — Slots ──────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Slots", level=2)
            ui.text(
                'The component has no slot in the ``with`` sense: it '
                    'receives no children, and its only textual surface is '
                    'the placeholder. What stays adjustable is its eleven '
                    'THEME slots — ``slots={…}`` overrides them per instance,'
                    ' ``Theme(components={"color_picker": …})`` for the whole'
                    ' app.',
                color="muted", size="sm",
            )
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text('default', color="muted", size="xs")
                    ui.color_picker("#e93d82")
                with ui.vstack(gap="xs"):
                    ui.text("slots={'swatch': 'rounded-none w-10'}",
                            color="muted", size="xs")
                    ui.color_picker(
                        "#e93d82",
                        slots={"swatch": "rounded-none w-10"},
                    )

            ui.divider()

            ui.text(
                'There is NO ``swatches=``, and that is deliberate: the '
                    "grid is the theme's palette, so every picker in an app "
                    'offers the same one. A brand is declared once — '
                    '``Theme(palette={"brand": "#…"})`` — and the field stays'
                    ' free for everything else: any hex value can be typed by'
                    ' hand.',
                color="muted", size="sm",
            )

        # ── Card 3 — Edge cases ─────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Edge cases", level=2)
            ui.text("Edge inputs and exotic combinations.",
                    color="muted", size="sm")

            ui.heading("Valeur vide", level=3)
            ui.text(
                "The theme's chequerboard shows through. A WHITE swatch "
                    'and a swatch with NO colour would look the same — hence '
                    'the chequerboard rather than a neutral background.',
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                ui.color_picker()
                ui.color_picker("")

            ui.heading('What is not a hex value', level=3)
            ui.text(
                'The field does not refuse it, and that is a choice: it '
                    'is editable, so the user necessarily types intermediate '
                    'states ("#2f"). The swatch stays empty as long as the '
                    'browser cannot read the value.',
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                for raw in ("#2f", "rebeccapurple", 'not a colour'):
                    with ui.vstack(gap="xs"):
                        ui.text(repr(raw), color="muted", size="xs")
                        ui.color_picker(raw)

            ui.heading('Case and short form', level=3)
            ui.text(
                'The selected swatch is compared lower-cased on BOTH '
                    'sides, so "#8E4EC6" does tick the same cell as '
                    '"#8e4ec6". The three-digit form displays, but no cell '
                    'recognises itself in it — the panel does not normalise.',
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("\"#8E4EC6\" (majuscules)",
                            color="muted", size="xs")
                    ui.color_picker("#8E4EC6")
                with ui.vstack(gap="xs"):
                    ui.text("\"#abc\" (forme courte)",
                            color="muted", size="xs")
                    ui.color_picker("#abc")

            ui.heading('Pure white on a white background', level=3)
            ui.text('The swatch keeps its border, otherwise it would vanish into '
                'the surface.',
                    color="muted", size="xs")
            with ui.flex(classes="max-w-xs"):
                ui.color_picker("#ffffff")

            ui.heading('Inside a narrow cell', level=3)
            with ui.grid(cols={"base": 1, "md": 4}, gap="md"):
                ui.color_picker("#2f5fd0")
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
                with ui.form_field(label="Couleur de marque",
                                   hint="Sert d'accent partout"):
                    ui.color_picker("#2f5fd0")
                with ui.form_field(label="Couleur d'alerte"):
                    ui.color_picker("#e5484d", clearable=True)

            ui.heading('A light / dark pair', level=3)
            ui.text(
                'The real use case — it is exactly what ``/theme-studio``'
                    ' does for its twenty-two tokens. Nothing ties the two '
                    'fields together: they are two independent values, side '
                    'by side.',
                color="muted", size="xs",
            )
            with ui.hstack(gap="sm", align="center"):
                ui.color_picker("#2f5fd0", size="sm")
                ui.text("→", color="muted")
                ui.color_picker("#7da3f0", size="sm")

            ui.heading('explicit name= (escape hatch)', level=3)
            ui.text(
                'Autoname covers the bound case (``value=state.brand`` '
                    'derives ``name="brand"``). For a picker with a literal '
                    'value that must still post, ``name=`` is the only way to'
                    ' have a form carrier without a binding.',
                color="muted", size="xs",
            )
            with ui.flex(classes="max-w-xs"):
                ui.color_picker("#30a46c", name="accent")

            ui.heading('Inside a ui.dialog', level=3)
            with ui.dialog(title="Personnaliser", width="md") as dlg, \
                            ui.vstack():
                with ui.form_field(label="Quelle teinte ?"):
                    ui.color_picker("#6e56cf")
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
                'The field stays a real ``<input type=text>``: a hex '
                    'value can be typed from the keyboard without ever '
                    'opening the panel, which is the fastest route for anyone'
                    ' who knows their code. Every swatch in the panel is a '
                    'real ``<button>`` labelled by its value — hence '
                    'reachable with Tab and announced as “#8e4ec6”, not '
                    '“button”. The trigger carries ``aria-expanded``; Escape '
                    'and a click outside close it.',
                color="muted", size="sm",
            )
            ui.text(
                'The swatch grid cannot be the ONLY way of telling two '
                    'choices apart — that is the point of the text field '
                    'beside it: the value is always readable in plain '
                    'characters.',
                color="muted", size="sm",
            )
            with ui.flex(classes="max-w-xs"):
                ui.color_picker("#2f5fd0",
                                aria_label='Brand colour')

        # ── Card 6 — Server playground ──────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server playground", level=2)
            ui.text(
                "Every ColorPicker prop AND every escape hatch is wired "
                "to a control ; the preview AND the emitted HTML both "
                "refresh on every change.",
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
                    'colour is bound to a ClientState: the field, the swatch,'
                    ' the panel and the mirror below all read the SAME store '
                    'cell, with no round trip.',
                color="muted", size="sm",
            )
            client = ColorPickerClient()
            with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                with control("value (bound)"):
                    ui.color_picker(value=client.picked)
                with control("disabled (bound)"):
                    ui.switch(checked=client.locked, label="Verrouiller")

            ui.divider()

            with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                with control('the same one, driven by the switch'):
                    ui.color_picker(value=client.picked,
                                    disabled=client.locked)
                with control("miroir"):
                    ui.text(
                        ClientExpression(
                            "'value: ' + "
                            "($bz.state.ColorPickerClient"
                            ".default.picked || '(empty)')"
                        ),
                        color="muted", size="sm",
                        classes="font-mono",
                    )

            ui.divider()

            emitted_html_block(
                'Emitted HTML — everything addresses the store cell '
                    'directly: the field through bz-model, the hidden input '
                    'through bz-attr:value, the leading swatch through bz-'
                    'attr:style, and every cell of the panel through a bz-'
                    'on:click that WRITES into that same cell.',
                serialize_html(
                    ui.color_picker(value=client.picked,
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
                    m1 = ui.color_picker()
                    with ui.hstack(gap="sm", wrap=True):
                        ui.button("Ouvrir", on_click=m1.open())
                        ui.button("Fermer", variant="outline",
                                  on_click=m1.close())
                        ui.button("Basculer", variant="outline",
                                  on_click=m1.toggle())
                        ui.button("Set #27754a", on_click=m1.set("#27754a"))
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
                    lie = ColorPickerClient(key="ext_binding")
                    with ui.hstack(gap="md", align="center"):
                        ui.color_picker(value=lie.picked)
                        ui.text(
                            ClientExpression(
                                "'Valeur : ' + ($bz.state.ColorPickerClient"
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
                    deux = ColorPickerClient(key="ext_both")
                    m3 = ui.color_picker(value=deux.picked)
                    with ui.hstack(gap="sm", wrap=True, align="center"):
                        ui.button("Ouvrir", size="xs", on_click=m3.open())
                        ui.button("Set #27754a", size="xs",
                                  on_click=m3.set("#27754a"))
                        ui.button("Clear", size="xs", variant="ghost",
                                  on_click=m3.clear())
                        ui.text(
                            ClientExpression(
                                "'Store : ' + ($bz.state.ColorPickerClient"
                                ".ext_both.picked || '(empty)')"
                            ),
                            color="muted", size="sm", classes="font-mono",
                        )

            ui.heading("Client events", level=2)
            ui.text('change wired to a client expression that pushes the new '
                'colour onto a ClientState. Zero network.',
                    color="muted", size="sm")
            cevents = ColorPickerClientEvents()
            _new_value = ClientExpression("$event.target.value")
            with ui.flex(classes="max-w-xs"):
                ui.color_picker(
                    "#00a2c7",
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
                    '($bz.state.ColorPickerClientEvents.default.log'
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
                    ui.color_picker(
                        "#00a2c7",
                        on_change=cevents.log.push(_new_value),
                    )
                ),
            )
