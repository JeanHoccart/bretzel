"""``Select`` test bench.

Ten visual cards : full gabarit. ``BINDABLE_PROPS = ("value",
"disabled")`` — selected option + lock are bindable ; size / color
/ placeholder / options stay design-time.

Eight props : ``options`` (positional) / ``value`` (autoname-from) /
``name`` / ``placeholder`` / ``disabled`` / ``required`` / ``color``
/ ``size``. Three events : ``change`` / ``focus`` / ``blur``.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/select"


SIZES  = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]

FRUITS = [
    ("apple",      "Apple"),
    ("pear",       "Pear"),
    ("plum",       "Plum"),
    ("strawberry", "Strawberry"),
    ("watermelon", "Watermelon"),
]

COUNTRIES = [
    ("fr", "France"),
    ("de", "Germany"),
    ("it", "Italy"),
    ("es", "Spain"),
    ("uk", "United Kingdom"),
    ("us", "United States"),
]


class SelectPlayground(PageState):
    value:         str  = field(default="")
    name:          str  = field(default="")
    multiple:      bool = field(default=False)
    bulk_actions:  bool = field(default=False)
    placeholder:   str  = field(default="Pick a fruit…")
    color:         str  = field(default="primary")
    size:          str  = field(default="md")
    disabled:      bool = field(default=False)
    required:      bool = field(default=False)
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifiers.
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")
    # Event-handler shape.
    on_change_mode: str = field(default="none")


class SelectEvents(PageState):
    log: list = field(default_factory=list)


class SelectClient(ClientState, persist="memory"):
    """Mirror of Select's BINDABLE_PROPS = ('value', 'disabled')."""

    value:    str  = field(default="apple")
    disabled: bool = field(default=False)


class SelectClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


def log(name: str) -> None:
    state = SelectEvents()
    state.log = [*state.log, name]


def log_change(value: str = "") -> None:
    log(f"change(value={value!r})")


def log_focus()   -> None: log("focus")
def log_blur()    -> None: log("blur")


def clear_log() -> None:
    state = SelectEvents()
    state.log = []


def server_changed(state: SelectPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
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


def build_preview(state: SelectPlayground):
    kwargs: dict = {
        "value": ([state.value] if state.value else []) if state.multiple
                 else state.value,
        "placeholder": state.placeholder,
        "color": state.color,
        "size": state.size,
        "disabled": state.disabled,
        "required": state.required,
        "multiple": state.multiple,
    }
    if state.multiple:
        kwargs["bulk_actions"] = state.bulk_actions
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
    return ui.select(FRUITS, **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[SelectPlayground])
def server_panel() -> None:
    state = SelectPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("value (selected fruit key)"):
            ui.select(value=state.value,
                      options=[("", "(none)")]
                              + FRUITS,
                      on_change=server_changed)
        with control("name (overrides autoname)"):
            ui.input(value=state.name, placeholder="fruit",
                     on_change=server_changed)
        with control("multiple"):
            ui.switch(checked=state.multiple, on_change=server_changed)
        with control("bulk_actions (multiple only)"):
            ui.switch(checked=state.bulk_actions,
                      on_change=server_changed)
        with control("placeholder"):
            ui.input(value=state.placeholder,
                     placeholder="Pick a fruit…",
                     on_change=server_changed)
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
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!w-64",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-select",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Fruit picker",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="max-width: 240px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=select",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Pick a fruit",
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

    with ui.flex(justify="center", align="center"):
        build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML (trigger + popover panel)",
        serialize_html(build_preview(state)),
    )


@refreshable(deps=[SelectEvents])
def events_panel() -> None:
    state = SelectEvents()

    with ui.hstack(wrap=True, gap="lg", justify="center"):
        ui.select(FRUITS, placeholder="change handler",
                  on_change=log_change)
        ui.select(FRUITS, placeholder="focus handler",
                  on_focus=log_focus)
        ui.select(FRUITS, placeholder="blur handler",
                  on_blur=log_blur)

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
        ui.text("(no events yet — pick / focus / blur one of the "
                "selects above)",
                color="muted", size="sm")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (representative — the 'change' select)",
        serialize_html(
            ui.select(FRUITS, placeholder="change handler",
                      on_change=log_change)
        ),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Select", level=1)
            ui.text(
                "Custom popover-based combobox — replaces the native "
                "``<select>`` with a fully-styled trigger + dropdown "
                "panel. Keyboard accessibility built-in (Tab + "
                "Space/Enter to open, arrows to highlight, Enter to "
                "pick, Escape to close). The Server playground card "
                "stress-tests every prop ; the emitted HTML is "
                "shown live underneath.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Basic (no value yet)", level=3)
                    ui.select(FRUITS, placeholder="Pick a fruit…")

                    ui.heading("Pre-selected value", level=3)
                    ui.select(COUNTRIES, value="fr",
                              placeholder="Pick a country")

                    ui.heading("render= — le corps de l'option", level=3)
                    with ui.vstack():
                        ui.text("Le composant garde l'enveloppe : data-value, "
                                "le clic, aria-selected. Le rappel remplit "
                                "l'interieur.",
                                color="muted", size="xs")
                        ui.select(FRUITS, placeholder="Pick a fruit…",
                                  render=lambda v, l: ui.badge(
                                      label=l, color="primary"))
                        ui.text("Limite : le declencheur affiche le label "
                                "TEXTE — une carte JS ne porte pas de "
                                "balisage.",
                                color="muted", size="xs")

                    ui.heading("Sizes", level=3)
                    with ui.vstack():
                        for s in SIZES:
                            ui.select(FRUITS, size=s,
                                      placeholder=f"size={s}")

                    ui.heading("Colors (focus ring)", level=3)
                    with ui.vstack():
                        for c in COLORS:
                            ui.select(FRUITS, color=c,
                                      placeholder=f"color={c}")

                    ui.heading("State", level=3)
                    with ui.vstack():
                        ui.select(FRUITS, placeholder="Enabled")
                        ui.select(FRUITS, placeholder="Disabled",
                                  disabled=True)
                        ui.select(FRUITS, placeholder="Required *",
                                  required=True)
                        ui.select(FRUITS, value="apple",
                                  placeholder="Disabled with value",
                                  disabled=True)

                    ui.heading("Options with disabled item", level=3)
                    ui.select(
                        [
                            {"value": "free", "label": "Free"},
                            {"value": "pro",  "label": "Pro"},
                            {"value": "team", "label": "Team",
                             "disabled": True},
                        ],
                        placeholder="Plan…",
                    )

                    ui.heading(
                        "Multi mode (no search — use Combobox for "
                        "that)",
                        level=3,
                    )
                    ui.text(
                        "``multiple=True`` switches the trigger to "
                        "a focusable ``<div>`` hosting pills + clear "
                        "× + chevron. The panel adds a sticky header "
                        "showing the picks above the options. "
                        "``bulk_actions=True`` adds Select all / "
                        "Clear in the header. For search-as-you-type "
                        "use ``ui.combobox`` instead.",
                        color="muted", size="sm",
                    )
                    ui.select(FRUITS, multiple=True,
                              value=["apple", "plum"],
                              placeholder="Pick fruits")

                    ui.heading(
                        "Multi + bulk_actions",
                        level=3,
                    )
                    ui.select(FRUITS, multiple=True,
                              value=["apple"],
                              bulk_actions=True,
                              placeholder="Pick fruits")

                    ui.heading(
                        "Multi — imperative .set / .select_all "
                        "/ .deselect_all",
                        level=3,
                    )
                    sm = ui.select(FRUITS, multiple=True,
                                   placeholder="External driven")
                    with ui.hstack(gap="sm", wrap=True):
                        ui.button("Set ['apple', 'plum']",
                                  on_click=sm.set(["apple", "plum"]))
                        ui.button("Select all", color="success",
                                  on_click=sm.select_all())
                        ui.button("Clear", variant="outline",
                                  color="error",
                                  on_click=sm.clear())

                    ui.heading(
                        "Basic — external controls via .set() / "
                        ".clear() / .focus() / .blur()",
                        level=3,
                    )
                    ui.text(
                        "Capture the instance via ``s = "
                        "ui.select(...)`` and call ``s.set('apple')`` "
                        "/ ``s.clear()`` / ``s.focus()`` / "
                        "``s.blur()`` from sibling buttons. The "
                        "imperative API is the default style when "
                        "you want to drive selection from the "
                        "outside without declaring a "
                        "``ClientState`` — useful for preset "
                        "buttons, reset actions, or programmatic "
                        "focus on the trigger.",
                        color="muted", size="sm",
                    )
                    s = ui.select(FRUITS, placeholder="External "
                                                     "controls drive me…")
                    with ui.hstack(gap="sm", wrap=True):
                        ui.button("Set 'apple'",
                                  on_click=s.set("apple"))
                        ui.button("Set 'plum'",
                                  on_click=s.set("plum"))
                        ui.button("Clear", variant="outline",
                                  on_click=s.clear())
                        ui.button("Focus", variant="ghost",
                                  on_click=s.focus())
                        ui.button("Blur", variant="ghost",
                                  on_click=s.blur())

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "``options`` accepts plain strings, "
                        "``(value, label)`` tuples, or full dicts "
                        "(``{\"value\": ..., \"label\": ..., "
                        "\"disabled\": ...}``). Mix shapes freely.",
                        color="muted", size="sm",
                    )

                    ui.heading("Plain strings (value == label)",
                               level=3)
                    ui.select(["draft", "published", "archived"],
                              placeholder="Status…")

                    ui.heading("(value, label) tuples", level=3)
                    ui.select(FRUITS, placeholder="Fruit (tuples)")

                    ui.heading("Dicts (with per-item disabled)",
                               level=3)
                    ui.select(
                        [
                            {"value": "fr", "label": "France"},
                            {"value": "de", "label": "Germany",
                             "disabled": True},
                            {"value": "it", "label": "Italy"},
                        ],
                        placeholder="Country (dicts)",
                    )

                    ui.text(
                        "value / disabled = ClientBinding — see "
                        "Client playground",
                        color="muted", size="sm",
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs that historically break.",
                            color="muted", size="sm")

                    ui.heading("Empty options list", level=3)
                    ui.select([], placeholder="No options available")

                    ui.heading("Single option", level=3)
                    ui.select([("only", "Only option")],
                              placeholder="Single")

                    ui.heading("Many options (40)", level=3)
                    ui.select(
                        [(str(i), f"Option {i}") for i in range(1, 41)],
                        placeholder="Many…",
                    )

                    ui.heading("Very long label (truncated)", level=3)
                    ui.select(
                        [("long",
                          "A very long option label that should "
                          "wrap or truncate")],
                        placeholder="Long label",
                    )

                    ui.heading("HTML-special characters (XSS escape)",
                               level=3)
                    ui.text(
                        "Framework escapes labels — the script "
                        "renders as literal text instead of "
                        "executing.",
                        color="muted", size="xs",
                    )
                    ui.select(
                        [("xss", "<script>alert(1)</script>")],
                        placeholder="XSS",
                    )

                    ui.heading("value not in options (placeholder shown)",
                               level=3)
                    ui.select(FRUITS, value="not-a-fruit",
                              placeholder="(fallback to placeholder)")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Select in common contexts.",
                            color="muted", size="sm")

                    ui.heading("Inside ui.form (with hidden input)",
                               level=3)
                    ui.text(
                        "Passing ``name=`` adds a hidden "
                        "``<input>`` so the value reaches the "
                        "server on submit.",
                        color="muted", size="xs",
                    )
                    with ui.form():
                        with ui.vstack():
                            ui.select(COUNTRIES, name="country",
                                      placeholder="Country…")
                            ui.button("Save", type="submit",
                                      color="primary")

                    ui.heading("Inside ui.grid (two-column form)",
                               level=3)
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        ui.select(COUNTRIES, name="country2",
                                  placeholder="Country")
                        ui.select(FRUITS, name="fruit",
                                  placeholder="Favourite fruit")

                    ui.heading("Inside ui.tooltip", level=3)
                    with ui.tooltip("Choose your home country"):
                        ui.select(COUNTRIES, placeholder="Country…")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "The custom trigger emits "
                        "``role=\"combobox\"`` plus "
                        "``aria-expanded`` and ``aria-controls`` "
                        "wired to the panel ; options carry "
                        "``role=\"option\"``. Keyboard works out "
                        "of the box : Tab to focus, Space/Enter/↓ "
                        "to open, arrows to highlight, Enter to "
                        "select, Escape to close.",
                        color="muted", size="sm",
                    )
                    ui.select(COUNTRIES, placeholder="Tab + Space + ↓",
                              aria_label="Country picker",
                              on_change=log_change)

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every prop AND every escape hatch is wired "
                        "to a control ; the preview AND the emitted "
                        "HTML both refresh on every change.",
                        color="muted", size="sm",
                    )
                    server_panel()

            # ── Card 7 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    ui.text("Three events on Select (change / focus "
                            "/ blur). Each one wires a module-level "
                            "server callable that appends a line to "
                            "the live log.",
                            color="muted", size="sm")
                    events_panel()

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of Select's ``BINDABLE_PROPS = "
                        "('value', 'disabled')`` contract. The picked "
                        "fruit and the lock both flip live via "
                        "client-side directives — no network "
                        "round-trip. Size / color / placeholder / "
                        "options stay design-time.",
                        color="muted", size="sm",
                    )
                    client = SelectClient(key="playground")
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("value"):
                            ui.select(FRUITS, value=client.value,
                                      placeholder="Pick a fruit…")
                        with control("disabled"):
                            ui.switch(checked=client.disabled)

                    ui.divider()

                    with ui.flex(justify="center", align="center"):
                        ui.select(FRUITS, value=client.value,
                                  disabled=client.disabled,
                                  placeholder="Pick a fruit…")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — bz-attr:value on the hidden "
                        "input (plus the trigger's baked label map) "
                        "for value, bz-attr:disabled for disabled.",
                        serialize_html(
                            ui.select(FRUITS, value=client.value,
                                      disabled=client.disabled,
                                      placeholder="Pick a fruit…")
                        ),
                    )

            # ── Card 9 — External controls — the 3 modes ────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes",
                               level=2)
                    ui.text(
                        "Same scenario (external buttons drive a "
                        "Select) played three ways. Pick the mode "
                        "that fits your need : imperative for "
                        "one-off writes, binding when another "
                        "component must read or react to the "
                        "value, both together when you want "
                        "write-through with a reactive observer.",
                        color="muted", size="sm",
                    )

                    # ── Mode 1 — Imperative only ────────────────────
                    ui.heading(
                        "Mode 1 — Imperative only (default for "
                        "one-off writes)",
                        level=3,
                    )
                    ui.text(
                        "No ClientState. The Select owns its own "
                        "the runtime value ; ``.set('apple')`` / "
                        "``.clear()`` dispatch ``bz-set`` / "
                        "``bz-clear`` events caught by the wrapper. "
                        "The listener reuses Select's internal "
                        "``_pick`` setter so the displayed label "
                        "swaps AND fires ``change`` on the hidden "
                        "input. ``.focus()`` / ``.blur()`` are pure "
                        "DOM commands that target the trigger "
                        "button. **Use this by default when you "
                        "just need to preset / reset / focus the "
                        "Select from a sibling button — no observer "
                        "needed.**",
                        color="muted", size="sm",
                    )
                    m1 = ui.select(FRUITS,
                                   placeholder="Imperative — no binding")
                    with ui.hstack(gap="sm", wrap=True):
                        # ⚠️ `open` / `close` / `toggle` ajoutés le
                        # 2026-09-03, en dernier des huit composants de
                        # cette forme — un panneau ancré qui porte une
                        # valeur. Select n'avait que la moitié champ ;
                        # les six pickers et Combobox l'ont reçue le même
                        # jour. Même nature, même surface.
                        ui.button("Ouvrir", on_click=m1.open())
                        ui.button("Fermer", variant="outline",
                                  on_click=m1.close())
                        ui.button("Basculer", variant="outline",
                                  on_click=m1.toggle())
                        ui.button("Set 'apple'",
                                  on_click=m1.set("apple"))
                        ui.button("Set 'plum'",
                                  on_click=m1.set("plum"))
                        ui.button("Clear", variant="outline",
                                  on_click=m1.clear())
                        ui.button("Focus", variant="ghost",
                                  on_click=m1.focus())
                        ui.button("Blur", variant="ghost",
                                  on_click=m1.blur())

                    ui.divider()

                    # ── Mode 2 — ClientBinding only ─────────────────
                    ui.heading(
                        "Mode 2 — ClientBinding only (when another "
                        "component must read or react)",
                        level=3,
                    )
                    ui.text(
                        "Use this when **another component needs "
                        "to read the value live** — a sibling that "
                        "echoes the picked option, a button visible "
                        "only when a fruit is picked, an enabled / "
                        "disabled gate on the rest of the form. "
                        "``value=binding`` lands as the binding "
                        "path so the picked option writes back to "
                        "the reactive store ; siblings reading the "
                        "same store update via client reactivity, "
                        "no round-trip.",
                        color="muted", size="sm",
                    )
                    bound = SelectClient(key="binding_only")
                    with ui.hstack(gap="md", align="center"):
                        ui.select(FRUITS, value=bound.value,
                                  placeholder="Pick a fruit…")
                        ui.text(
                            ClientExpression(
                                "'Picked: ' + "
                                "($bz.state.SelectClient."
                                "binding_only.value || '(none)')"
                            ),
                            color="muted", size="sm",
                            classes="font-mono",
                        )

                    ui.divider()

                    # ── Mode 3 — Both : write-through ───────────────
                    ui.heading(
                        "Mode 3 — Both (write-through)",
                        level=3,
                    )
                    ui.text(
                        "Binding fournie ET on appelle ``.set(...)`` "
                        "/ ``.clear()`` sur l'instance. Le framework "
                        "détecte la binding et délègue à "
                        "``binding.set(value)`` — **le DOM dispatch "
                        "n'est pas utilisé**, single source of truth "
                        "préservée. L'observer (à droite) voit les "
                        "écritures imperatives ET les clicks "
                        "manuels via le même store.",
                        color="muted", size="sm",
                    )
                    both = SelectClient(key="both")
                    m3 = ui.select(FRUITS, value=both.value,
                                   placeholder="Bound + imperative…")
                    with ui.hstack(gap="md", align="center"):
                        ui.text(
                            ClientExpression(
                                "'Picked: ' + "
                                "($bz.state.SelectClient.both.value "
                                "|| '(none)')"
                            ),
                            color="muted", size="sm",
                            classes="font-mono",
                        )
                    with ui.hstack(gap="sm", wrap=True):
                        ui.button("Set 'apple'",
                                  on_click=m3.set("apple"))
                        ui.button("Set 'plum'",
                                  on_click=m3.set("plum"))
                        ui.button("Clear", variant="outline",
                                  on_click=m3.clear())
                        ui.button("Focus", variant="ghost",
                                  on_click=m3.focus())
                        ui.button("Blur", variant="ghost",
                                  on_click=m3.blur())

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — Mode 2 (binding only) : "
                        "the trigger label tracks the bound value "
                        "via a baked map ; the hidden input "
                        "carries ``:value`` bound to the path.",
                        serialize_html(
                            ui.select(FRUITS, value=bound.value,
                                      placeholder="Pick a fruit…")
                        ),
                    )

            # ── Card 10 — Client events ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text("Three selects — each event wires an "
                            "client expression that pushes onto a "
                            "ClientState list. Zero network ; the "
                            "log below re-renders via bz-text on "
                            "every push.",
                            color="muted", size="sm")
                    cevents = SelectClientEvents()
                    _new_value = ClientExpression("$event.target.value")
                    with ui.hstack(wrap=True, gap="lg", justify="center"):
                        ui.select(FRUITS, placeholder="change",
                                  on_change=cevents.log.push(_new_value))
                        ui.select(FRUITS, placeholder="focus",
                                  on_focus=cevents.log.push("focus"))
                        ui.select(FRUITS, placeholder="blur",
                                  on_blur=cevents.log.push("blur"))

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive — no "
                                "refresh)", color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    ui.divider()

                    log_text = ClientExpression(
                        '($bz.state.SelectClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML (representative — the "
                        "'change' select). @change relocated onto "
                        "the hidden input ; the client expression "
                        "pushes the picked value.",
                        serialize_html(
                            ui.select(FRUITS, placeholder="change",
                                      on_change=cevents.log.push(_new_value))
                        ),
                    )
