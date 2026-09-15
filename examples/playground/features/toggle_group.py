"""``ToggleGroup`` + ``ToggleButton`` test bench.

Ten cards : full 7-section gabarit (S2 split into 4 visual cards).
``BINDABLE_PROPS = ("value", "disabled")`` — both get a dedicated
Client playground card ; single + multi shapes both covered. One
visual identity — a joined-button bar (no variant axis).
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/toggle_group"


TYPES    = ["single", "multiple"]
SIZES    = ["xs", "sm", "md", "lg", "xl"]
COLORS   = ["primary", "secondary", "success", "warning",
            "error", "info", "muted"]


# ── State : server playground + events + client mirrors ─────────────────


class ToggleGroupPlayground(PageState):
    value:    str  = field(default="active")
    type:     str  = field(default="single")
    name:     str  = field(default="preview")
    color:    str  = field(default="primary")
    size:     str  = field(default="md")
    disabled: bool = field(default=False)
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")
    # Event-handler shape.
    on_change_mode: str = field(default="none")


class ToggleGroupEvents(PageState):
    log: list = field(default_factory=list)


# Drives the Server-events demo. ``AUTONAME_FROM = "value"`` derives
# the hidden input's ``name=`` from ``field_name`` (here ``filter``) ;
# the handler receives ``filter=...``.
class ToggleGroupServerEvents(ClientState, persist="memory"):
    filter: str = field(default="all")


# Bindable surface for the Client cards. ``key=`` lets us spin up
# multiple isolated instances per page (Mode 1 / Mode 2 / Mode 3 etc.).
class ToggleGroupClient(ClientState, persist="memory"):
    value:    str  = field(default="active")
    disabled: bool = field(default=False)


# Multi-mode binding target.
class ToggleGroupMultiClient(ClientState, persist="memory"):
    picks: list = field(default_factory=lambda: ["b", "i"])


class ToggleGroupClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


# ── Handlers ────────────────────────────────────────────────────────────


def log(name: str) -> None:
    state = ToggleGroupEvents()
    state.log = [*state.log, name]


def log_change(**form) -> None:
    """The hidden input ships the live value (or JSON-array in multi).
    AUTONAME_FROM keys it by field_name — pick whichever form value
    actually came through."""
    picked = next((v for v in form.values() if v not in (None, "")), "")
    log(f"change(value={picked!r})")


def log_focus() -> None: log("focus")
def log_blur()  -> None: log("blur")


def clear_log() -> None:
    state = ToggleGroupEvents()
    state.log = []


def server_changed(state: ToggleGroupPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    pass


def playground_change_handler(value: str = "") -> None:
    log(f"playground-server-change(value={value!r})")


_CLIENT_CHANGE_EXPR = "$el.classList.toggle('ring-4')"


# ── Helpers ─────────────────────────────────────────────────────────────


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: ToggleGroupPlayground):
    kwargs: dict = {
        "value": state.value,
        "multiple": state.type == "multiple",
        "color": state.color,
        "size": state.size,
        "disabled": state.disabled,
    }
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
    if state.type == "multiple" and isinstance(kwargs.get("value"), str):
        kwargs["value"] = [kwargs["value"]] if kwargs["value"] else []
    kwargs["name"] = state.name or "preview"
    return ui.toggle_group(
        options=[("all", "All"), ("active", "Active"), ("done", "Done")],
        **kwargs,
    )


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


# ── Server playground panel ─────────────────────────────────────────────


@refreshable(deps=[ToggleGroupPlayground])
def server_panel() -> None:
    state = ToggleGroupPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("value"):
            ui.select(value=state.value,
                      options=[(v, v.title())
                               for v in ("all", "active", "done")],
                      on_change=server_changed)
        with control("type"):
            ui.select(value=state.type,
                      options=[(t, t) for t in TYPES],
                      on_change=server_changed)
        with control("name (hidden input key)"):
            ui.input(value=state.name, placeholder="preview",
                     on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("disabled (whole group)"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="!w-full",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id,
                     placeholder="filter-toggle",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Filter status",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="margin-top: 4px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=toggle-group",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Filter the table",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)
        with control("on_change mode"):
            ui.select(value=state.on_change_mode,
                      options=[("none",   "None (no handler)"),
                               ("server", "Server callable"),
                               ("client", "Client string"),
                               ("both",   "Both (list)")],
                      on_change=server_changed)

    ui.divider()

    with ui.flex(justify="center", align="center"):
        build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


# ── Server-events panel ─────────────────────────────────────────────────


@refreshable(deps=[ToggleGroupEvents])
def events_panel() -> None:
    state = ToggleGroupEvents()

    ui.text(
        "ToggleGroup fires ``change`` on selection (single → scalar "
        "value, multi → JSON-stringified array via the hidden "
        "input), plus ``focus`` / ``blur``. Like other form inputs, "
        "the ``change`` handler receives kwargs keyed by the hidden "
        "input's ``name=`` — AUTONAME_FROM='value' derives that from "
        "the bound field name (here ``filter``). One instance per "
        "event below — a single ToggleGroup carries only one server "
        "``hx-post``.",
        color="muted", size="sm",
    )

    evt_state = ToggleGroupServerEvents()
    _OPTS = [("all", "All"), ("active", "Active"), ("done", "Done")]
    with ui.flex(wrap=True, gap="md"):
        ui.toggle_group(value=evt_state.filter, options=_OPTS,
                        on_change=log_change)
        ui.toggle_group(value="all", options=_OPTS, on_focus=log_focus)
        ui.toggle_group(value="all", options=_OPTS, on_blur=log_blur)

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
                        color="muted", size="sm",
                        classes="font-mono")
    else:
        ui.text("(no events yet — pick a different toggle above)",
                color="muted", size="sm")

    ui.divider()

    repr_state = ToggleGroupServerEvents()
    representative = ui.toggle_group(
        value=repr_state.filter,
        options=[("all", "All"), ("active", "Active")],
        on_change=log_change,
    )
    emitted_html_block(
        "Emitted HTML (representative — group with on_change)",
        serialize_html(representative),
    )


# ── Page ────────────────────────────────────────────────────────────────


def page() -> None:
    ui.title("ToggleGroup — Playground")
    ui.meta_tag(
        name="description",
        content="Multi-button selector cluster — joined-button bar.",
    )

    with ui.container():
        with ui.vstack():
            ui.heading("ToggleGroup", level=1)
            ui.text(
                "Multi-button selector cluster — a joined-button bar "
                "(filters / toolbar). Two modes : ``single`` (scalar "
                "value) and ``multiple`` (list). The Server playground "
                "card stress-tests every prop ; the emitted HTML is "
                "shown live underneath.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Basic", level=3)
                    ui.text(
                        "Joined-button bar. Items share their edges ; "
                        "the selected state is a coloured bg fill "
                        "driven by ``data-selected=\"true\"``.",
                        color="muted", size="xs",
                    )
                    ui.toggle_group(
                        value="active",
                        options=[("all", "All"),
                                 ("active", "Active"),
                                 ("done", "Done"),
                                 ("archived", "Archived")],
                    )

                    ui.heading("multiple=True (with icons)", level=3)
                    ui.text(
                        "Formatting toolbar — multi-select with icons "
                        "via the container API.",
                        color="muted", size="xs",
                    )
                    with ui.toggle_group(
                        value=["b", "i"],
                        multiple=True,
                    ):
                        ui.toggle_button("b", "Bold",      icon="bold")
                        ui.toggle_button("i", "Italic",    icon="italic")
                        ui.toggle_button("u", "Underline", icon="underline")

                    ui.heading("Icon-only (container API)", level=3)
                    ui.text(
                        "Pass ``label=None`` for an icon-only button. "
                        "``tooltip=`` provides the accessible name.",
                        color="muted", size="xs",
                    )
                    with ui.toggle_group(value="grid"):
                        ui.toggle_button("grid",   None, icon="grid-3x3",
                                         tooltip="Grid view")
                        ui.toggle_button("list",   None, icon="list",
                                         tooltip="List view")
                        ui.toggle_button("kanban", None, icon="columns-3",
                                         tooltip="Kanban view")

                    ui.heading("Sizes", level=3)
                    ui.text(
                        "Four sizes share the form-input scale "
                        "(h-7 / h-8 / h-10 / h-11).",
                        color="muted", size="xs",
                    )
                    for s in SIZES:
                        ui.text(f"size={s}", color="muted", size="xs")
                        with ui.hstack(gap="md", align="center"):
                            ui.toggle_group(
                                value="b",
                                options=[("a", "A"), ("b", "B"),
                                         ("c", "C")],
                                size=s,
                            )

                    ui.heading("Colors (when selected)", level=3)
                    for c in COLORS:
                        ui.toggle_group(
                            value="a",
                            options=[("a", f"{c.title()} selected"),
                                     ("b", "Other"),
                                     ("c", "Other")],
                            color=c,
                        )

                    ui.heading("Disabled button inside enabled group",
                               level=3)
                    with ui.toggle_group(value="a"):
                        ui.toggle_button("a", "Available")
                        ui.toggle_button("b", "Available")
                        ui.toggle_button("c", "Locked", disabled=True)

                    ui.heading("Disabled whole group", level=3)
                    ui.toggle_group(
                        value="b",
                        options=[("a", "All locked"),
                                 ("b", "All locked"),
                                 ("c", "All locked")],
                        disabled=True,
                    )

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "ToggleGroup is a container (``with`` block "
                        "holds the ToggleButton items). Each "
                        "ToggleButton's ``label`` slot is a str (or "
                        "``None`` for icon-only). Reactive "
                        "``value`` / ``disabled`` on the group ride "
                        "through ``BINDABLE_PROPS``.",
                        color="muted", size="sm",
                    )

                    ui.heading("Plain string labels", level=3)
                    with ui.toggle_group(value="a"):
                        ui.toggle_button("a", "Plain string A")
                        ui.toggle_button("b", "Plain string B")

                    ui.heading("With icons + tooltip per item", level=3)
                    with ui.toggle_group(value="left"):
                        ui.toggle_button("left",   "Left",
                                         icon="align-left",
                                         tooltip="Align left")
                        ui.toggle_button("center", "Center",
                                         icon="align-center",
                                         tooltip="Align center")
                        ui.toggle_button("right",  "Right",
                                         icon="align-right",
                                         tooltip="Align right")

                    ui.text(
                        "value / disabled = ClientBinding — see "
                        "Client playground (Card 8)",
                        color="muted", size="sm",
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Inputs that historically break.",
                            color="muted", size="sm")

                    ui.heading("Two options (smallest meaningful)",
                               level=3)
                    ui.toggle_group(
                        value="on",
                        options=[("on", "On"), ("off", "Off")],
                    )

                    ui.heading("Lots of options (12)", level=3)
                    ui.toggle_group(
                        value="m07",
                        options=[(f"m{n:02d}", f"M{n}")
                                 for n in range(1, 13)],
                    )

                    ui.heading("Very long labels", level=3)
                    ui.toggle_group(
                        value="long",
                        options=[
                            ("short", "Short"),
                            ("long", "A label that's just way too long"),
                            ("medium", "Medium one"),
                        ],
                    )

                    ui.heading("Emoji + multi-script labels", level=3)
                    ui.toggle_group(
                        value="fr",
                        options=[("fr", "🇫🇷 France"),
                                 ("jp", "🇯🇵 日本"),
                                 ("il", "🇮🇱 שלום")],
                    )

                    ui.heading("HTML-special characters (XSS escape)",
                               level=3)
                    ui.text(
                        "Framework escapes labels — the script "
                        "renders as literal text instead of executing.",
                        color="muted", size="xs",
                    )
                    ui.toggle_group(
                        value="raw",
                        options=[("raw", "<script>alert(1)</script>"),
                                 ("safe", "Safe")],
                    )

                    ui.heading("value matches no option (none selected)",
                               level=3)
                    ui.text(
                        "Bind a value that doesn't appear among the "
                        "options — the group renders with nothing "
                        "selected.",
                        color="muted", size="xs",
                    )
                    ui.toggle_group(
                        value="non-existent",
                        options=[("a", "A"), ("b", "B"), ("c", "C")],
                    )

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Toggle groups in common contexts.",
                            color="muted", size="sm")

                    ui.heading("Inside ui.form (FormData submission)",
                               level=3)
                    with ui.form():
                        with ui.vstack():
                            ui.text("Filter status", weight="bold")
                            ui.toggle_group(
                                value="active",
                                options=[("all", "All"),
                                         ("active", "Active"),
                                         ("done", "Done")],
                                name="filter",
                            )
                            ui.button("Continue", type="submit",
                                      color="primary")

                    ui.heading("Inside ui.card (toolbar)", level=3)
                    with ui.card():
                        with ui.vstack():
                            ui.text("Text alignment", weight="bold")
                            with ui.toggle_group(value="left"):
                                ui.toggle_button("left",   None,
                                                 icon="align-left",
                                                 tooltip="Left")
                                ui.toggle_button("center", None,
                                                 icon="align-center",
                                                 tooltip="Center")
                                ui.toggle_button("right",  None,
                                                 icon="align-right",
                                                 tooltip="Right")

                    ui.heading("Side-by-side groups", level=3)
                    with ui.hstack(gap="md"):
                        ui.toggle_group(
                            value="grid",
                            options=[("grid", "Grid"), ("list", "List")],
                            size="sm",
                        )
                        ui.toggle_group(
                            value="asc",
                            options=[("asc", "↑"), ("desc", "↓")],
                            size="sm",
                        )

                    ui.heading("Inside ui.tooltip (with color)", level=3)
                    with ui.tooltip("Pick your weapon", color="primary"):
                        ui.toggle_group(
                            value="b",
                            options=[("a", "A"), ("b", "B")],
                        )

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "The cluster carries ``role=\"group\"`` ; each "
                        "button has reactive ``aria-pressed`` (string "
                        "``\"true\"`` / ``\"false\"`` per WAI-ARIA). "
                        "Keyboard nav comes from the native "
                        "``<button>`` (Tab + Enter / Space) ; "
                        "arrow-key nav is not implemented v1 (defers "
                        "to the user-agent default focus order). "
                        "Pair with ``aria_label=`` so the group has "
                        "an accessible name.",
                        color="muted", size="sm",
                    )
                    ui.text("Filter status",
                            color="muted", size="sm")
                    ui.toggle_group(
                        value="active",
                        options=[("all", "All"), ("active", "Active"),
                                 ("done", "Done")],
                        aria_label="Filter status",
                    )

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
                    events_panel()

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of ToggleGroup's ``BINDABLE_PROPS = "
                        "('value', 'disabled')`` contract. Both flip "
                        "live via ``bz-data``/click-expr and "
                        "``bz-attr:disabled`` — no network "
                        "round-trip. Visual axes (color / size) stay "
                        "design-time.",
                        color="muted", size="sm",
                    )
                    client = ToggleGroupClient(key="playground")
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("value"):
                            ui.toggle_group(
                                value=client.value,
                                options=[("a", "Option A"),
                                         ("b", "Option B"),
                                         ("c", "Option C")],
                            )
                        with control("disabled"):
                            ui.switch(checked=client.disabled)

                    ui.divider()

                    with ui.flex(justify="center", align="center"):
                        ui.toggle_group(
                            value=client.value,
                            options=[("a", "Option A"),
                                     ("b", "Option B"),
                                     ("c", "Option C")],
                            disabled=client.disabled,
                        )

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — click-expr writes the bound "
                        "value path directly on value, "
                        "bz-attr:disabled on disabled.",
                        serialize_html(
                            ui.toggle_group(
                                value=client.value,
                                options=[("a", "Option A"),
                                         ("b", "Option B"),
                                         ("c", "Option C")],
                                disabled=client.disabled,
                            )
                        ),
                    )

            # ── Card 9 — External controls — the 3 modes ────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes",
                               level=2)
                    ui.text(
                        "Same scenario (external buttons set the "
                        "selection) played three ways. Pick the mode "
                        "that fits your need : imperative for purely-"
                        "visual triggers, binding when another "
                        "component needs to read or react to the "
                        "value, both together when you want "
                        "write-through.",
                        color="muted", size="sm",
                    )

                    # ── Mode 1 — Imperative only ────────────────────
                    ui.heading(
                        "Mode 1 — Imperative only (default)",
                        level=3,
                    )
                    ui.text(
                        "No ClientState. The group owns its selection "
                        "in the DOM. ``.set(value)`` dispatches a DOM "
                        "event caught by the wrapper's own "
                        "``@bz-set`` listener, which writes ``picked``. "
                        "**Use this by default for purely-visual "
                        "write-only control — no other component needs "
                        "the value.**",
                        color="muted", size="sm",
                    )
                    m1 = ui.toggle_group(
                        value="a",
                        options=[("a", "Option A"),
                                 ("b", "Option B"),
                                 ("c", "Option C")],
                    )
                    with ui.hstack(gap="sm"):
                        ui.button("Set A", on_click=m1.set("a"))
                        ui.button("Set B", variant="outline",
                                  on_click=m1.set("b"))
                        ui.button("Set C", variant="outline",
                                  on_click=m1.set("c"))

                    ui.divider()

                    # ── Mode 2 — ClientBinding only ─────────────────
                    ui.heading("Mode 2 — ClientBinding only",
                               level=3)
                    ui.text(
                        "Use this when **another component needs to "
                        "read or react to the value** — a sibling "
                        "text that mirrors it, a client expression "
                        "that derives from it, server-side awareness "
                        "on the next render.",
                        color="muted", size="sm",
                    )
                    bound = ToggleGroupClient(key="binding_only")
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("value (bound)"):
                            ui.toggle_group(
                                value=bound.value,
                                options=[("a", "Option A"),
                                         ("b", "Option B"),
                                         ("c", "Option C")],
                            )
                        with control("sibling reads the bound value"):
                            ui.text(bound.value, color="muted",
                                    classes="font-mono")
                    with ui.hstack(gap="sm"):
                        ui.button('Set "a" via binding.set(...)',
                                  on_click=bound.value.set("a"))
                        ui.button('Set "b" via binding.set(...)',
                                  variant="outline",
                                  on_click=bound.value.set("b"))

                    ui.divider()

                    # ── Mode 3 — Both : write-through ───────────────
                    ui.heading("Mode 3 — Both (write-through)",
                               level=3)
                    ui.text(
                        "Binding provided AND ``.set()`` called on the "
                        "instance. The framework detects the binding "
                        "and delegates to ``binding.set(...)`` — "
                        "**the DOM dispatch isn't used**, single "
                        "source of truth preserved. Imperative "
                        "buttons + sibling mirror converge on the "
                        "same field.",
                        color="muted", size="sm",
                    )
                    both = ToggleGroupClient(key="both")
                    with control("mirror (also bound)"):
                        ui.text(both.value, color="muted",
                                classes="font-mono")
                    m3 = ui.toggle_group(
                        value=both.value,
                        options=[("a", "Option A"),
                                 ("b", "Option B"),
                                 ("c", "Option C")],
                    )
                    with ui.hstack(gap="sm"):
                        ui.button("Set A via m3.set(...)",
                                  on_click=m3.set("a"))
                        ui.button("Set B via m3.set(...)",
                                  variant="outline",
                                  on_click=m3.set("b"))
                        ui.button("Set C via m3.set(...)",
                                  variant="outline",
                                  on_click=m3.set("c"))

                    ui.divider()

                    # ── Multi-mode bonus ────────────────────────────
                    ui.heading(
                        "Multi-mode — bound list[str] + bulk actions",
                        level=3,
                    )
                    ui.text(
                        "Multi-select group bound to a ``list[str]`` ; "
                        "imperative ``.select_all`` / ``.deselect_all`` "
                        "/ ``.set(list)`` / ``.clear()`` exercised via "
                        "sibling buttons.",
                        color="muted", size="sm",
                    )
                    multi = ToggleGroupMultiClient()
                    with ui.hstack(justify="between", align="center",
                                   gap="md"):
                        ui.text("Current picks (live) :",
                                color="muted", size="sm")
                        live = ClientExpression(
                            "JSON.stringify("
                            "$bz.state.ToggleGroupMultiClient.default.picks"
                            " || [])"
                        )
                        ui.text(live, classes="font-mono")
                    gm = ui.toggle_group(
                        value=multi.picks,
                        multiple=True,
                    )
                    with gm:
                        ui.toggle_button("b", "Bold",      icon="bold")
                        ui.toggle_button("i", "Italic",    icon="italic")
                        ui.toggle_button("u", "Underline", icon="underline")
                        ui.toggle_button("s", "Strike",
                                         icon="strikethrough")
                    with ui.hstack(gap="sm"):
                        ui.button("select_all", variant="outline",
                                  size="sm", on_click=gm.select_all())
                        ui.button("deselect_all", variant="outline",
                                  size="sm", on_click=gm.deselect_all())
                        ui.button("set ['b','u']", variant="outline",
                                  size="sm",
                                  on_click=gm.set(["b", "u"]))
                        ui.button("clear", variant="outline",
                                  size="sm", on_click=gm.clear())

                    ui.divider()

                    preview = ui.toggle_group(
                        name="client_emit",
                        value=bound.value,
                        color="primary",
                        options=[("a", "A"), ("b", "B"), ("c", "C")],
                    )
                    emitted_html_block(
                        "Emitted HTML — Mode 2 (binding only) : the "
                        "click handlers write the bound path "
                        "directly ; data-selected on each button "
                        "tracks the bound value via reactive "
                        "``:data-selected``.",
                        serialize_html(preview),
                    )

            # ── Card 10 — Client events ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text(
                        "Group ``change`` / ``focus`` / ``blur`` "
                        "wired to client expressions that push onto "
                        "a ClientState list. Zero network ; the log "
                        "below re-renders via ``bz-text`` on every "
                        "push.",
                        color="muted", size="sm",
                    )
                    cevents = ToggleGroupClientEvents()
                    # ``change`` bubbles from the hidden input ; the
                    # bound value is its ``.value`` property at that
                    # moment.
                    _new_value = ClientExpression("$event.target.value")
                    cstate = ToggleGroupClient(key="client_events")
                    ui.toggle_group(
                        value=cstate.value,
                        options=[("a", "Option A"),
                                 ("b", "Option B"),
                                 ("c", "Option C")],
                        on_change=cevents.log.push(_new_value),
                        on_focus=cevents.log.push("focus"),
                        on_blur=cevents.log.push("blur"),
                    )

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive — no "
                                "refresh)", color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    ui.divider()

                    log_text = ClientExpression(
                        '($bz.state.ToggleGroupClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    preview = ui.toggle_group(
                        name="client_events_preview",
                        value="a",
                        options=[("a", "A"), ("b", "B")],
                        on_change=cevents.log.push(_new_value),
                    )
                    emitted_html_block(
                        "Emitted HTML — @change on the hidden input ; "
                        "the client expression pushes the new value "
                        "onto the bound list.",
                        serialize_html(preview),
                    )
