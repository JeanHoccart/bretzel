"""``Radio`` + ``RadioGroup`` test bench.

Ten cards : full gabarit. ``RadioGroup.BINDABLE_PROPS =
("value", "disabled")`` — selected option + group lock are bindable ;
both get a dedicated Client playground card ; direction / color /
size stay design-time. Individual Radio items inherit name / color /
size from the group ; their only per-item bindable is ``disabled``.

Eight RadioGroup props (``name`` / ``value`` / ``direction`` /
``color`` / ``size`` / ``disabled`` / ``required`` + Radio's
``label`` / ``value`` per item). One group event : ``change``.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/radio"


DIRECTIONS = ["col", "row"]
SIZES      = ["xs", "sm", "md", "lg", "xl"]
COLORS     = ["primary", "secondary", "success", "warning",
              "error", "info", "muted"]


class RadioPlayground(PageState):
    value:       str  = field(default="b")
    direction:   str  = field(default="col")
    color:       str  = field(default="primary")
    size:        str  = field(default="md")
    disabled:    bool = field(default=False)
    required:    bool = field(default=False)
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


class RadioEvents(PageState):
    log: list = field(default_factory=list)


class RadioClient(ClientState, persist="memory"):
    """Mirror of RadioGroup's BINDABLE_PROPS = ('value', 'disabled')."""

    value:    str  = field(default="b")
    disabled: bool = field(default=False)


# Drives the server-events RadioGroup demo. ``value=state.value``
# binding → AUTONAME_FROM="value" derives ``name="value"`` from
# field_name → handler ``log_change(value=...)`` matches. No manual
# ``name=`` (CLAUDE.md rule 4).
class RadioServerEvents(ClientState, persist="memory"):
    value: str = field(default="a")


class RadioClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


def log(name: str) -> None:
    state = RadioEvents()
    state.log = [*state.log, name]


def log_change(**form) -> None:
    # The radio group passes its ``name=`` to each child <input>, so the
    # form data arrives keyed by the GROUP name (``"evt_group"`` or
    # ``"evt_repr"`` here). Use ``**form`` to receive whichever field
    # name the dispatcher sent ; pick the first non-empty value for the
    # log line.
    picked = next((v for v in form.values() if v), "")
    log(f"change(value={picked!r})")


def log_focus() -> None:
    log("focus()")


def log_blur() -> None:
    log("blur()")


def clear_log() -> None:
    state = RadioEvents()
    state.log = []


def server_changed(state: RadioPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    pass


def playground_change_handler(value: str = "") -> None:
    log(f"playground-server-change(value={value!r})")


_CLIENT_CHANGE_EXPR = "$el.parentElement.classList.toggle('ring-4')"


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: RadioPlayground):
    kwargs: dict = {
        "value": state.value,
        "direction": state.direction,
        "color": state.color,
        "size": state.size,
        "disabled": state.disabled,
        "required": state.required,
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
    # Server-playground preview : the props matrix drives this
    # instance. No binding (value is a PageState scalar), so we
    # provide ``name=`` explicitly — the radios need a shared name
    # to function as a group (HTML semantic, not autoname-related).
    group = ui.radio_group(name="preview", **kwargs)
    with group:
        ui.radio(value="a", label="Option A")
        ui.radio(value="b", label="Option B")
        ui.radio(value="c", label="Option C")
    return group


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[RadioPlayground])
def server_panel() -> None:
    state = RadioPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("value (selected option)"):
            ui.select(value=state.value,
                      options=[("a", "Option A"),
                               ("b", "Option B"),
                               ("c", "Option C")],
                      on_change=server_changed)
        with control("direction"):
            ui.select(value=state.direction,
                      options=[(d, d) for d in DIRECTIONS],
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
        with control("required"):
            ui.switch(checked=state.required, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!gap-4",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-radio-group",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Plan selection",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="margin-top: 4px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=radio-group",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Choose your plan",
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
        "Emitted HTML (RadioGroup + three Radio items)",
        serialize_html(build_preview(state)),
    )


@refreshable(deps=[RadioEvents])
def events_panel() -> None:
    state = RadioEvents()

    ui.text(
        "RadioGroup exposes a single ``change`` event ; individual "
        "Radio items each carry ``change`` / ``focus`` / ``blur``. "
        "The group-level event is the common one — it fires when "
        "the user picks any option, with the new value as the "
        "kwarg.",
        color="muted", size="sm",
    )

    evt_state = RadioServerEvents()
    with ui.radio_group(value=evt_state.value, on_change=log_change):
        ui.radio(value="a", label="Group on_change → log change(a)")
        ui.radio(value="b", label="Group on_change → log change(b)")
        ui.radio(value="c", label="Group on_change → log change(c)")

    ui.divider()

    # The PER-ITEM events. The text above already announced them with
    # none demonstrated — only the group's ``change`` was. One instance
    # per event: a component carries only one ``hx-post``.
    #
    # ``focus`` / ``blur`` land on the ``<input type="radio">``, not on
    # the root ``<label>``. The input is ``sr-only`` — visually hidden
    # but STILL focusable, which is precisely this technique's point over
    # ``display:none``. From the keyboard: Tab to enter the group, arrows
    # to move around.
    ui.text(
        "Per-item events — Tab into the group to fire focus, Tab out "
        "for blur.",
        color="muted", size="sm",
    )
    with ui.hstack(gap="md"):
        with ui.radio_group(name="evt_focus", value="a"):
            ui.radio(value="a", label="on_focus", on_focus=log_focus)
        with ui.radio_group(name="evt_blur", value="a"):
            ui.radio(value="a", label="on_blur", on_blur=log_blur)

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
        ui.text("(no events yet — pick a different radio above)",
                color="muted", size="sm")

    ui.divider()

    representative = ui.radio_group(name="evt_repr", value="a",
                                    on_change=log_change)
    with representative:
        ui.radio(value="a", label="A")
        ui.radio(value="b", label="B")
    emitted_html_block(
        "Emitted HTML (representative — group with on_change)",
        serialize_html(representative),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Radio", level=1)
            ui.text(
                "Single-choice picker. Radios live inside a "
                "``RadioGroup`` ``with`` block ; the group owns the "
                "``name`` and the bound ``value``. Each Radio reads "
                "those at render time and emits the matching "
                "``<input type=\"radio\">`` + styled fake-circle. "
                "The Server playground card stress-tests every prop "
                "; the emitted HTML is shown live underneath.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Basic group", level=3)
                    with ui.radio_group(name="ref_basic", value="b"):
                        ui.radio(value="a", label="Option A")
                        ui.radio(value="b", label="Option B (selected)")
                        ui.radio(value="c", label="Option C")

                    ui.heading("Direction", level=3)
                    ui.text("``direction='col'`` (default) stacks ; "
                            "``'row'`` lines them up.",
                            color="muted", size="xs")
                    with ui.radio_group(name="ref_dir_col",
                                        value="left", direction="col"):
                        ui.radio(value="left",   label="Left")
                        ui.radio(value="center", label="Center")
                        ui.radio(value="right",  label="Right")
                    with ui.radio_group(name="ref_dir_row",
                                        value="left", direction="row"):
                        ui.radio(value="left",   label="Left")
                        ui.radio(value="center", label="Center")
                        ui.radio(value="right",  label="Right")

                    ui.heading("Sizes", level=3)
                    for s in SIZES:
                        ui.text(f"size={s}", color="muted", size="xs")
                        with ui.radio_group(name=f"ref_size_{s}",
                                            value="a", size=s):
                            ui.radio(value="a", label=f"A ({s})")
                            ui.radio(value="b", label=f"B ({s})")

                    ui.heading("Colors (when selected)", level=3)
                    for c in COLORS:
                        with ui.radio_group(name=f"ref_color_{c}",
                                            value="a", color=c):
                            ui.radio(value="a",
                                     label=f"{c.title()} selected")
                            ui.radio(value="b", label="Other")

                    ui.heading("Disabled radio inside enabled group",
                               level=3)
                    with ui.radio_group(name="ref_per_item_dis",
                                        value="a"):
                        ui.radio(value="a", label="Available")
                        ui.radio(value="b", label="Available")
                        ui.radio(value="c", label="Locked",
                                 disabled=True)

                    ui.heading("Disabled whole group", level=3)
                    with ui.radio_group(name="ref_group_dis",
                                        value="b", disabled=True):
                        ui.radio(value="a", label="All locked")
                        ui.radio(value="b", label="All locked")
                        ui.radio(value="c", label="All locked")

                    ui.heading("Required", level=3)
                    with ui.radio_group(name="ref_required", required=True):
                        ui.radio(value="a", label="Option A")
                        ui.radio(value="b", label="Option B")

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "RadioGroup is a container (``with`` block "
                        "holds the Radio items). Each Radio's "
                        "``label`` slot is a str. Reactive "
                        "``value`` / ``disabled`` on the group ride "
                        "through ``BINDABLE_PROPS``.",
                        color="muted", size="sm",
                    )

                    ui.heading("Plain string labels", level=3)
                    with ui.radio_group(name="slot_str", value="a"):
                        ui.radio(value="a", label="Plain string A")
                        ui.radio(value="b", label="Plain string B")

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

                    ui.heading("Empty labels", level=3)
                    with ui.radio_group(name="edge_empty", value="a"):
                        ui.radio(value="a", label="")
                        ui.radio(value="b", label="")

                    ui.heading("Very long labels (100 chars)", level=3)
                    with ui.radio_group(name="edge_long", value="a"):
                        ui.radio(value="a", label="A" * 100)
                        ui.radio(value="b", label="B" * 100)

                    ui.heading("Emoji + multi-script labels", level=3)
                    with ui.radio_group(name="edge_emoji", value="a"):
                        ui.radio(value="a", label="🚀 Rocket")
                        ui.radio(value="b", label="שלום Hello")
                        ui.radio(value="c", label="中文 Chinese")

                    ui.heading("HTML-special characters (XSS escape)",
                               level=3)
                    ui.text(
                        "Framework escapes the labels — the script "
                        "renders as literal text instead of "
                        "executing.",
                        color="muted", size="xs",
                    )
                    with ui.radio_group(name="edge_xss", value="a"):
                        ui.radio(value="a",
                                 label="<script>alert(1)</script>")
                        ui.radio(value="b", label="Safe")

                    ui.heading("value matches no option (none selected)",
                               level=3)
                    ui.text(
                        "Bind a value that doesn't appear among the "
                        "options — the group renders with nothing "
                        "checked. Useful for 'pristine' / unselected "
                        "form state.",
                        color="muted", size="xs",
                    )
                    with ui.radio_group(name="edge_none",
                                        value="non-existent"):
                        ui.radio(value="a", label="A")
                        ui.radio(value="b", label="B")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Radio groups in common contexts.",
                            color="muted", size="sm")

                    ui.heading("Inside ui.form", level=3)
                    with ui.form():
                        with ui.vstack():
                            ui.text("Choose a plan", weight="bold")
                            with ui.radio_group(name="plan",
                                                value="pro"):
                                ui.radio(value="free", label="Free")
                                ui.radio(value="pro",  label="Pro")
                                ui.radio(value="team", label="Team")
                            ui.button("Continue", type="submit",
                                      color="primary")

                    ui.heading("Inside ui.card (settings)", level=3)
                    with ui.card():
                        with ui.vstack():
                            ui.heading("Theme", level=4)
                            with ui.radio_group(name="theme",
                                                value="auto"):
                                ui.radio(value="light",
                                         label="Light")
                                ui.radio(value="dark",
                                         label="Dark")
                                ui.radio(value="auto",
                                         label="Match system")

                    ui.heading("Row direction (toolbar-style)", level=3)
                    with ui.radio_group(name="align", value="left",
                                        direction="row"):
                        ui.radio(value="left",   label="Left")
                        ui.radio(value="center", label="Center")
                        ui.radio(value="right",  label="Right")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "RadioGroup emits ``role=\"radiogroup\"`` so "
                        "screen readers announce it as one cluster ; "
                        "individual ``<input type=\"radio\">``s carry "
                        "the native semantic and keyboard works "
                        "out of the box (arrow keys cycle between "
                        "options). Pair with ``aria_label=`` (or a "
                        "neighbouring text label) so the group has "
                        "an accessible name.",
                        color="muted", size="sm",
                    )
                    ui.text("Plan selection",
                            color="muted", size="sm")
                    with ui.radio_group(name="a11y_plan", value="pro",
                                        aria_label="Plan selection"):
                        ui.radio(value="free", label="Free")
                        ui.radio(value="pro",  label="Pro")
                        ui.radio(value="team", label="Team")

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
                        "Mirror of RadioGroup's ``BINDABLE_PROPS = "
                        "('value', 'disabled')`` contract. Both flip "
                        "live via ``bz-model`` / ``bz-attr:disabled`` "
                        "— no network round-trip. Direction / color / "
                        "size stay design-time.",
                        color="muted", size="sm",
                    )
                    client = RadioClient(key="playground")
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("value"):
                            with ui.radio_group(value=client.value):
                                ui.radio(value="a", label="Option A")
                                ui.radio(value="b", label="Option B")
                                ui.radio(value="c", label="Option C")
                        with control("disabled"):
                            ui.switch(checked=client.disabled)

                    ui.divider()

                    with ui.flex(justify="center", align="center"):
                        with ui.radio_group(value=client.value,
                                            disabled=client.disabled):
                            ui.radio(value="a", label="Option A")
                            ui.radio(value="b", label="Option B")
                            ui.radio(value="c", label="Option C")

                    ui.divider()

                    preview = ui.radio_group(value=client.value,
                                             disabled=client.disabled)
                    with preview:
                        ui.radio(value="a", label="Option A")
                        ui.radio(value="b", label="Option B")
                        ui.radio(value="c", label="Option C")
                    emitted_html_block(
                        "Emitted HTML — bz-model on each "
                        "&lt;input type=\"radio\"&gt; (value), "
                        "bz-attr:disabled stamped on each (disabled).",
                        serialize_html(preview),
                    )

            # ── Card 9 — External controls — the 3 modes ────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes",
                               level=2)
                    ui.text(
                        "Same scenario (external buttons set the "
                        "selected radio) played three ways. Pick the "
                        "mode that fits your need : imperative for "
                        "purely-visual triggers, binding when another "
                        "component needs to read or react to the "
                        "value, both together when you want "
                        "write-through.",
                        color="muted", size="sm",
                    )

                    # ── Mode 1 — Imperative only (default style) ────
                    ui.heading(
                        "Mode 1 — Imperative only (default)",
                        level=3,
                    )
                    ui.text(
                        "No ClientState. The group owns its selected "
                        "value in the DOM. ``.set(value)`` dispatches "
                        "a DOM event caught by the wrapper's own "
                        "``@bz-set`` listener, which flips ``checked`` "
                        "on the matching child radio. **Use this by "
                        "default for purely-visual write-only control "
                        "— no other component needs the value.**",
                        color="muted", size="sm",
                    )
                    m1 = ui.radio_group(name="mode1_imperative",
                                        value="a")
                    with m1:
                        ui.radio(value="a", label="Option A")
                        ui.radio(value="b", label="Option B")
                        ui.radio(value="c", label="Option C")
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
                        "on the next render. The binding is the "
                        "single source of truth multi-composant.",
                        color="muted", size="sm",
                    )
                    bound = RadioClient(key="binding_only")
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("value (bound)"):
                            with ui.radio_group(name="mode2_binding",
                                                value=bound.value):
                                ui.radio(value="a", label="Option A")
                                ui.radio(value="b", label="Option B")
                                ui.radio(value="c", label="Option C")
                        with control("sibling reads the bound value"):
                            ui.text(bound.value, color="muted",
                                    classes="font-mono")
                    with ui.hstack(gap="sm"):
                        ui.button(
                            'Set "a" via binding.set(...)',
                            on_click=bound.value.set("a"),
                        )
                        ui.button(
                            'Set "b" via binding.set(...)',
                            variant="outline",
                            on_click=bound.value.set("b"),
                        )

                    ui.divider()

                    # ── Mode 3 — Both : write-through ───────────────
                    ui.heading(
                        "Mode 3 — Both (write-through)",
                        level=3,
                    )
                    ui.text(
                        'A binding supplied AND ``.set()`` called on the '
                            'instance. The framework detects the binding and '
                            'delegates to ``binding.set(...)`` — **the DOM '
                            'dispatch is not used**, single source of truth '
                            'preserved. The imperative buttons and the '
                            'sibling mirror converge on the same field.',
                        color="muted", size="sm",
                    )
                    both = RadioClient(key="both")
                    with control("mirror (also bound)"):
                        ui.text(both.value, color="muted",
                                classes="font-mono")
                    m3 = ui.radio_group(name="mode3_both",
                                        value=both.value)
                    with m3:
                        ui.radio(value="a", label="Option A")
                        ui.radio(value="b", label="Option B")
                        ui.radio(value="c", label="Option C")
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

                    preview = ui.radio_group(name="client_emit",
                                             value=bound.value,
                                             color="primary")
                    with preview:
                        ui.radio(value="a", label="A")
                        ui.radio(value="b", label="B")
                        ui.radio(value="c", label="C")
                    emitted_html_block(
                        "Emitted HTML — Mode 2 (binding only) : "
                        "bz-model on each &lt;input type=\"radio\"&gt; "
                        "reads the bound path ; binding.set writes "
                        "back without a round-trip.",
                        serialize_html(preview),
                    )

            # ── Card 10 — Client events ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text("Group on_change wired to a client "
                            "expression that pushes the new value "
                            "onto a ClientState list. Zero network ; "
                            "the log below re-renders via bz-text "
                            "on every push.",
                            color="muted", size="sm")
                    cevents = RadioClientEvents()
                    # change bubbles from the picked radio up to the
                    # group ; $event.target.value reads the input's
                    # value attribute = the new group selection.
                    _new_value = ClientExpression("$event.target.value")
                    with ui.radio_group(
                        name="client_events",
                        value="a",
                        on_change=cevents.log.push(_new_value),
                    ):
                        ui.radio(value="a", label="Option A")
                        ui.radio(value="b", label="Option B")
                        ui.radio(value="c", label="Option C")

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive — no "
                                "refresh)", color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    ui.divider()

                    log_text = ClientExpression(
                        '($bz.state.RadioClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    preview = ui.radio_group(
                        name="client_events_preview",
                        value="a",
                        on_change=cevents.log.push(_new_value),
                    )
                    with preview:
                        ui.radio(value="a", label="A")
                        ui.radio(value="b", label="B")
                    emitted_html_block(
                        "Emitted HTML — @change on the group ; the "
                        "bubbled event from the picked radio carries "
                        "its value, the client expression pushes it.",
                        serialize_html(preview),
                    )
