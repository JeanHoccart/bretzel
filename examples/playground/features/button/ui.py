"""Render — refreshable panels + page assembly for the Button feature.

Five visual cards (Reference / Slots / Edge cases / Composability /
A11y) document the component at a glance with NO HTML inspection
blocks ; the four stateful cards (Server playground / Server events
/ Client playground / Client events) each carry exactly one
``ui.code(serialize_html(...), lang="html")`` block exposing the
distinctive shape of bindings the framework emits in that mode.

Render helpers and refreshable panels live here ; the side-effecting
state mutators live in ``logic.py``. The two modules import each other
in a loop (logic refreshes panels, ui wires handlers), resolved by
deferred imports inside the logic handlers.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression


from examples.playground.features.button.logic import (
    clear_log,
    log_blur,
    log_click,
    log_focus,
    log_mouseenter,
    log_mouseleave,
    playground_click_handler,
    server_changed,
)
from examples.playground.features.button.state import (
    COLORS,
    SIZES,
    TYPES,
    VARIANTS,
    ButtonClient,
    ButtonClientEvents,
    ButtonEvents,
    ButtonPlayground,
)
from examples.playground.features.inspection import emitted_html_block


def control(label: str):
    """Mini-helper for a labelled control cell : a muted prop-name on
    top of whichever input goes inside the ``with`` block. Used inside
    the responsive controls grid below."""
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


# client expression used when ``on_click_mode`` requests the client
# branch — visible toggle on the button itself so the user can confirm
# the bz-on:click directive landed without devtools.
_CLIENT_CLICK_EXPR = "this.classList.toggle('ring-4')"


def parse_extra_attrs(blob: str) -> dict:
    """Parse the ``extra_attrs`` textarea into a dict.

    Format : one ``key=value`` per line. Blank lines and lines without
    ``=`` are ignored. Surrounding whitespace stripped.
    """
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: ButtonPlayground):
    """Map the playground state to ``ui.button(...)`` kwargs."""
    kwargs: dict = {
        "variant": state.variant,
        "size": state.size,
        "color": state.color,
        "disabled": state.disabled,
        "loading": state.loading,
        "type": state.type,
    }
    if state.icon_left:
        kwargs["icon_left"] = state.icon_left
    if state.icon_right:
        kwargs["icon_right"] = state.icon_right
    if state.classes:
        kwargs["classes"] = state.classes
    if state.custom_id:
        kwargs["id"] = state.custom_id
    if state.style:
        kwargs["style"] = state.style
    # Merge aria-label + the multi-pair extra_attrs textarea into one
    # attrs= kwarg.
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

    # ``on_click`` shape : the framework accepts callable / str / list,
    # and emits very different HTML for each. The control lets you
    # toggle between them so the inspection block shows the difference.
    if state.on_click_mode == "server":
        kwargs["on_click"] = playground_click_handler
    elif state.on_click_mode == "client":
        kwargs["on_click"] = _CLIENT_CLICK_EXPR
    elif state.on_click_mode == "both":
        kwargs["on_click"] = [playground_click_handler, _CLIENT_CLICK_EXPR]

    return ui.button(state.label, **kwargs)


@refreshable(deps=[ButtonPlayground])
def server_panel() -> None:
    state = ButtonPlayground()

    # ── Controls grid : every Button prop + universal escape hatches
    #    (classes / id / aria-label / style / attrs / tooltip / visible)
    #    + the on_click_mode toggle. 17 controls.
    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("label"):
            ui.input(value=state.label, placeholder="Click me",
                     on_change=server_changed)
        with control("variant"):
            ui.select(value=state.variant,
                      options=[(v, v.title()) for v in VARIANTS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c.title()) for c in COLORS],
                      on_change=server_changed)
        with control("type"):
            ui.select(value=state.type,
                      options=[(t, t) for t in TYPES],
                      on_change=server_changed)
        with control("icon_left"):
            ui.input(value=state.icon_left, placeholder="ex: save",
                     on_change=server_changed)
        with control("icon_right"):
            ui.input(value=state.icon_right, placeholder="ex: arrow-right",
                     on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control("loading"):
            ui.switch(checked=state.loading, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!rounded-full !uppercase",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-button",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Save document",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="background: rebeccapurple",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=save\nrole=button",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Save the document",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)
        with control("on_click mode"):
            ui.select(value=state.on_click_mode,
                      options=[("none", "None (no handler)"),
                               ("server", "Server callable"),
                               ("client", "Client string"),
                               ("both", "Both (list)")],
                      on_change=server_changed)

    ui.divider()

    # ── Live preview ─────────────────────────────────────────────────
    with ui.flex(justify="center", align="center"):
        build_preview(state)

    ui.divider()

    # ── Live HTML inspection — the framework's actual output ────────
    #    Re-rendered on every state change so every prop, every escape
    #    hatch, every combination is visible in the HTML below. The
    #    shared inspector toggle (cf. ``features.inspection``) means
    #    flipping any block on any playground page hides them all.
    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


@refreshable(deps=[ButtonEvents])
def events_panel() -> None:
    state = ButtonEvents()

    # One button per event — each wires a single ``on_<event>=`` so
    # firing it is unambiguous in the log.
    with ui.hstack(wrap=True, justify="center"):
        ui.button("click",      variant="outline", on_click=log_click)
        ui.button("focus",      variant="outline", on_focus=log_focus)
        ui.button("blur",       variant="outline", on_blur=log_blur)
        ui.button("mouseenter", variant="outline", on_mouseenter=log_mouseenter)
        ui.button("mouseleave", variant="outline", on_mouseleave=log_mouseleave)

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)",
                color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)

    if state.log:
        with ui.vstack(gap="xs"):
            # Newest-first, capped at the last 10 entries so the card
            # doesn't grow unbounded during a stress test.
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}",
                        color="muted", size="sm", classes="font-mono")
    else:
        ui.text("(no events yet — interact with one of the buttons "
                "above to fire its event)",
                color="muted", size="sm")

    ui.divider()

    # ── Emitted HTML — one representative event button ──────────────
    #    All 5 differ only by the event name (``click`` / ``focus`` /
    #    ``blur`` / ``mouseenter`` / ``mouseleave``) ; the shape stays
    #    the same. Shown here so the reader sees how a server callable
    #    lands on the DOM as a ``hx-post`` + ``hx-trigger="click"``
    #    directive plus framework identity attrs (``id`` / ``bz-id`` /
    #    ``bz-version``).
    emitted_html_block(
        "Emitted HTML (representative — the 'click' button)",
        serialize_html(
            ui.button("click", variant="outline", on_click=log_click)
        ),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Button", level=1)
            ui.text(
                "Action trigger. Quick visual reference below ; the real "
                "stress-testing lives in the Server playground card — "
                "every prop and every escape hatch is wired to a control, "
                "and the emitted HTML is shown live underneath the preview.",
                color="muted",
            )

            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Variants", level=3)
                    with ui.hstack():
                        ui.button("Solid",   variant="solid")
                        ui.button("Soft",    variant="soft")
                        ui.button("Outline", variant="outline")
                        ui.button("Ghost",   variant="ghost")

                    ui.heading("Sizes", level=3)
                    with ui.hstack(align="end"):
                        ui.button("XS", size="xs")
                        ui.button("SM", size="sm")
                        ui.button("MD", size="md")
                        ui.button("LG", size="lg")
                        ui.button("XL", size="xl")

                    ui.heading("Colors", level=3)
                    with ui.hstack(wrap=True):
                        ui.button("Primary",   color="primary")
                        ui.button("Secondary", color="secondary")
                        ui.button("Success",   color="success")
                        ui.button("Warning",   color="warning")
                        ui.button("Error",     color="error")
                        ui.button("Info",      color="info")
                        ui.button("Muted",     color="muted")

                    ui.heading("Disabled", level=3)
                    with ui.hstack():
                        ui.button("Enabled")
                        ui.button("Disabled", disabled=True)

                    ui.heading("Loading", level=3)
                    with ui.hstack():
                        ui.button("Idle")
                        ui.button("In flight", loading=True)
                        ui.button("With icons", loading=True,
                                  icon_left="save",
                                  icon_right="arrow-right")

                    ui.heading("Icon left", level=3)
                    with ui.hstack():
                        ui.button("Save",   icon_left="save")
                        ui.button("Open",   icon_left="folder-open")
                        ui.button("Delete", icon_left="trash-2")

                    ui.heading("Icon right", level=3)
                    with ui.hstack():
                        ui.button("Next", icon_right="arrow-right")
                        ui.button("Open", icon_right="external-link")
                        ui.button("Menu", icon_right="chevron-down")

                    ui.heading("Type (no visual variation — behavioural)",
                               level=3)
                    with ui.hstack():
                        ui.button("Button (default)", type="button")
                        ui.button("Submit", type="submit")
                        ui.button("Reset", type="reset")

                    ui.heading("href — l'habillage d'un bouton, "
                               "la sémantique d'un lien", level=3)
                    ui.text(
                        "Un href rend un <a> : clic-milieu, « ouvrir dans "
                        "un nouvel onglet », et rôle « lien » pour un "
                        "lecteur d'écran. Le type=\"button\" est laissé "
                        "tomber — sur une ancre il désignerait un type "
                        "MIME. Désactivé, la destination est retirée et "
                        "l'état passe par aria-disabled : la pseudo-classe "
                        ":disabled ne matche jamais un <a>.",
                        color="muted", size="sm",
                    )
                    with ui.hstack():
                        ui.button("Voir la doc", href="/link")
                        ui.button("Nouvel onglet", href="https://bretzel.dev",
                                  external=True, variant="outline")
                        ui.button("Indisponible", href="/link", disabled=True,
                                  variant="soft")

            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "Every slot accepts str | ClientBinding | Component. "
                        "Each row exercises one shape — switch the Server "
                        "playground below to see the emitted HTML for any "
                        "combination.",
                        color="muted", size="sm",
                    )

                    ui.heading("Default slot (label)", level=3)
                    with ui.hstack(wrap=True):
                        ui.button("Save")
                        ui.button(ui.text("Custom", color="success",
                                          weight="bold"))

                    ui.heading("icon_left slot", level=3)
                    with ui.hstack(wrap=True):
                        ui.button("Save", icon_left="save")
                        ui.button("Save",
                                  icon_left=ui.icon("save", color="warning"))

                    ui.heading("icon_right slot", level=3)
                    with ui.hstack(wrap=True):
                        ui.button("Next", icon_right="arrow-right")
                        ui.button("Next",
                                  icon_right=ui.icon("arrow-right", size="lg"))

            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text(
                        "Inputs that historically break components "
                        "elsewhere. The Server playground below lets you "
                        "reproduce any of these live AND inspect the HTML.",
                        color="muted", size="sm",
                    )

                    ui.heading("Empty label", level=3)
                    with ui.hstack():
                        ui.button("")

                    ui.heading("Very long label (80 chars)", level=3)
                    with ui.hstack():
                        ui.button("A" * 80)

                    ui.heading("Emoji + multi-script", level=3)
                    with ui.hstack():
                        ui.button("Ship 🚀 — שלום — 中文")

                    ui.heading("HTML-special characters (XSS escape)", level=3)
                    ui.text(
                        "Framework escapes the label — the script "
                        "renders as literal text instead of executing.",
                        color="muted", size="xs",
                    )
                    with ui.hstack():
                        ui.button("<script>alert(1)</script>")

                    ui.heading("Invalid icon name", level=3)
                    with ui.hstack():
                        ui.button("Broken",
                                  icon_left="this-icon-does-not-exist")

                    ui.heading("Loading + disabled together", level=3)
                    with ui.hstack():
                        ui.button("Stuck", loading=True, disabled=True)

            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text(
                        "Button nested inside other Bretzel components.",
                        color="muted", size="sm",
                    )

                    ui.heading("Inside ui.tooltip", level=3)
                    with ui.hstack():
                        with ui.tooltip("Reclaim 30% of your quota"):
                            ui.button("Free up space", icon_left="trash-2")

                    ui.heading("Inside ui.card", level=3)
                    with ui.hstack():
                        with ui.card():
                            with ui.vstack(gap="sm"):
                                ui.text("Wrapper card",
                                        color="muted", size="xs")
                                ui.button("Save", color="primary")

                    ui.heading("Inside ui.form (type='submit')", level=3)
                    with ui.hstack():
                        with ui.form():
                            ui.button("Submit", type="submit",
                                      color="primary")

            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Tab onto the button below, press Space or Enter "
                        "— it should append a line to the Server events "
                        "log further down. Other ARIA tests (aria-label, "
                        "role, …) live in the Server playground via the "
                        "aria-label control.",
                        color="muted", size="sm",
                    )
                    with ui.hstack():
                        ui.button("Press Space to fire",
                                  icon_left="keyboard",
                                  on_click=log_click)

            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "The real test bench. Every prop AND every "
                        "escape hatch is wired to a control ; the preview "
                        "and the emitted HTML both refresh on every "
                        "change. This is where you verify class "
                        "composition, attr flow-through, slot wrapping, "
                        "and edge-case behaviour — without leaving the "
                        "page.",
                        color="muted", size="sm",
                    )
                    server_panel()

            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    ui.text("Every event of the Button (click / focus / "
                            "blur / mouseenter / mouseleave) is wired to "
                            "a module-level callable that appends a line "
                            "to the live log.",
                            color="muted", size="sm")
                    events_panel()

            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of Button's BINDABLE_PROPS contract : "
                        "label / disabled / loading. These are the three "
                        "props that genuinely change during a button's "
                        "lifecycle. Visual configuration (variant / size "
                        "/ color) stays static — set at design time. "
                        "the runtime mutates the store in-browser and the "
                        "button re-renders without a network round-trip.",
                        color="muted", size="sm",
                    )
                    client = ButtonClient()
                    with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                        with control("label"):
                            ui.input(value=client.label,
                                     placeholder="Click me")
                        with control("disabled"):
                            ui.switch(checked=client.disabled)
                        with control("loading"):
                            ui.switch(checked=client.loading)
                    ui.divider()
                    with ui.flex(justify="center", align="center"):
                        ui.button(
                            client.label,
                            disabled=client.disabled,
                            loading=client.loading,
                        )

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — bz-text on the label span, "
                        "bz-attr:disabled on the <button>, "
                        "loading mutex via bz-show + a pre-stamped "
                        "display:none between spinner and icon "
                        "(icon_left is design-time so "
                        "no reactive icon swap here).",
                        serialize_html(
                            ui.button(
                                client.label,
                                disabled=client.disabled,
                                loading=client.loading,
                            )
                        ),
                    )

            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text("Five buttons — each event wires a client "
                            "expression that pushes onto a ClientState "
                            "list. Zero network ; the log below "
                            "re-renders via bz-text on every push.",
                            color="muted", size="sm")
                    cevents = ButtonClientEvents()
                    with ui.hstack(wrap=True, justify="center"):
                        ui.button("click",      variant="outline",
                                  on_click=cevents.log.push("click"))
                        ui.button("focus",      variant="outline",
                                  on_focus=cevents.log.push("focus"))
                        ui.button("blur",       variant="outline",
                                  on_blur=cevents.log.push("blur"))
                        ui.button("mouseenter", variant="outline",
                                  on_mouseenter=cevents.log.push("mouseenter"))
                        ui.button("mouseleave", variant="outline",
                                  on_mouseleave=cevents.log.push("mouseleave"))
                    ui.divider()
                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive — no refresh)",
                                color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())
                    # ``join('\n')`` lets ``whitespace-pre`` on the
                    # text render newline-separated entries cleanly.
                    log_text = ClientExpression(
                        '($bz.state.ButtonClientEvents.default.log || [])'
                        '.join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    # ── Emitted HTML — representative client-event button ──
                    #    Each of the 5 buttons differs only by the event
                    #    name (``click`` / ``focus`` / …). They all wire
                    #    a client expression via ``log.push(...)``, which
                    #    lands on the DOM as ``bz-on:<event>="$bz.state.X.log
                    #    .push(...)"`` — zero round-trip, the runtime fires
                    #    the expression on the native DOM event.
                    emitted_html_block(
                        "Emitted HTML (representative — the 'click' button)",
                        serialize_html(
                            ui.button("click", variant="outline",
                                      on_click=cevents.log.push("click"))
                        ),
                    )
