"""``MessageInput`` test bench — and ``MessageInputTool``, its bar's child.

Ten cards : the full 7-section gabarit (S2 split into 4 visual cards).
``BINDABLE_PROPS = ("value", "loading")`` — both get the Client playground;
``IMPERATIVE = ("set", "clear", "focus")`` — External controls.
``EVENTS = ("submit", "stop")`` — Server events and Client events.

Props : ``value`` (autoname-from) / ``placeholder`` / ``loading`` /
``voice`` / ``files`` / ``disabled`` / ``name``. Children : any badge at
the top of the box, ``ui.message_input_tool`` in its bar (``label`` /
``icon`` / ``disabled`` / ``on_click``). Slots : none named — the
children ARE the composition, shown in the Slots card.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/message_input"


class MessageInputPlayground(PageState):
    value:       str  = field(default="")
    placeholder: str  = field(default="Ask, dictate, drop a file…")
    loading:        bool = field(default=False)
    voice:       bool = field(default=True)
    files:       str  = field(default=".pdf, image/*")
    max_files:   int  = field(default=0)
    max_size_mb: int  = field(default=0)
    max_length:  int  = field(default=0)
    disabled:    bool = field(default=False)
    name:        str  = field(default="")
    badge:       str  = field(default="Q3 report")
    tool:        bool = field(default=True)
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
    on_submit_mode: str = field(default="server")


class MessageInputEvents(PageState):
    log: list = field(default_factory=list)


class MessageInputClient(ClientState, persist="memory"):
    """Mirror of MessageInput's BINDABLE_PROPS."""

    value: str  = field(default="Typed here, or in the field beside")
    loading:  bool = field(default=False)


class MessageInputClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


def log(line: str) -> None:
    state = MessageInputEvents()
    state.log = [*state.log, line]


def log_submit(message: str = "", files=None) -> None:
    names = [f.filename for f in (files if isinstance(files, list) else [files])
             if hasattr(f, "filename")]
    log(f"submit(message={message[:40]!r}, files={names})")


def echo(message: str = "", files=None) -> None:
    """The demos send somewhere: a box with no on_submit sends nothing."""
    names = [f.filename for f in (files if isinstance(files, list) else [files])
             if hasattr(f, "filename")]
    ui.notification(f"Sent: {message[:60]!r}" + (f" + {len(names)} file(s)" if names else ""),
                    color="success", duration_ms=2500)


def log_stop() -> None:
    log("stop")


def log_tool() -> None:
    log("tool click")


def clear_log() -> None:
    MessageInputEvents().log = []


def server_changed(state: MessageInputPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed control's value.
    pass


def playground_submit(files=None) -> None:
    log("playground-server-submit")


CLIENT_SUBMIT_EXPR = "$el.classList.toggle('ring-4')"


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: MessageInputPlayground):
    kwargs: dict = {
        "value": state.value,
        "placeholder": state.placeholder,
        "loading": state.loading,
        "voice": state.voice,
        "disabled": state.disabled,
        "on_stop": log_stop,
    }
    accepted = [p.strip() for p in state.files.split(",") if p.strip()]
    if accepted:
        kwargs["files"] = accepted
    for key in ("max_files", "max_size_mb", "max_length"):
        if int(getattr(state, key) or 0) > 0:
            kwargs[key] = int(getattr(state, key))
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
    if state.on_submit_mode == "server":
        kwargs["on_submit"] = playground_submit
    elif state.on_submit_mode == "client":
        kwargs["on_submit"] = CLIENT_SUBMIT_EXPR
    elif state.on_submit_mode == "both":
        kwargs["on_submit"] = [playground_submit, CLIENT_SUBMIT_EXPR]
    box = ui.message_input(**kwargs)
    with box:
        if state.badge:
            ui.badge(state.badge, variant="soft", icon_left="at-sign", dismissible=True)
        if state.tool:
            ui.message_input_tool("Insert a template", icon="file-text", on_click=log_tool)
    return box


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable
def server_panel() -> None:
    state = MessageInputPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("value"):
            ui.input(value=state.value, placeholder="A draft", on_change=server_changed)
        with control("placeholder"):
            ui.input(value=state.placeholder, on_change=server_changed)
        with control("files (accepted, comma separated — empty: no clip)"):
            ui.input(value=state.files, placeholder=".pdf, image/*",
                     on_change=server_changed)
        with control("name (overrides autoname)"):
            ui.input(value=state.name, placeholder="question", on_change=server_changed)
        with control("max_files (0 = none)"):
            ui.number_input(value=state.max_files, on_change=server_changed)
        with control("max_size_mb (0 = none)"):
            ui.number_input(value=state.max_size_mb, on_change=server_changed)
        with control("max_length (0 = none)"):
            ui.number_input(value=state.max_length, on_change=server_changed)
        with control("badge (a child at the top — empty: none)"):
            ui.input(value=state.badge, on_change=server_changed)
        with control("tool (a ui.message_input_tool in the bar)"):
            ui.switch(checked=state.tool, on_change=server_changed)
        with control("loading (Envoyer becomes Arrêter)"):
            ui.switch(checked=state.loading, on_change=server_changed)
        with control("voice"):
            ui.switch(checked=state.voice, on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="max-w-md", on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-box", on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Ask the assistant",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="max-width: 30rem",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=2, placeholder="data-test=box",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Your question",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"), ("off", "False (skip render)")],
                      on_change=server_changed)
        with control("on_submit mode"):
            ui.select(value=state.on_submit_mode,
                      options=[("none", "None (no handler)"),
                               ("server", "Server callable"),
                               ("client", "Client string"),
                               ("both", "Both (list)")],
                      on_change=server_changed)

    ui.divider()
    with ui.vstack(classes="w-full max-w-xl mx-auto"):
        build_preview(state)
    ui.divider()
    emitted_html_block("Emitted HTML", serialize_html(build_preview(state)))


@refreshable
def events_panel() -> None:
    state = MessageInputEvents()

    with ui.vstack(classes="w-full max-w-xl"):
        ui.text("submit — Enter or the round button ; a file joined travels with it.",
                color="muted", size="sm")
        ui.message_input(on_submit=log_submit, files=(".pdf", "image/*"),
                         placeholder="Write, then Enter")
        ui.text("stop — the box is busy : the round button is « Arrêter ».",
                color="muted", size="sm")
        ui.message_input(on_submit=log_submit, loading=True, on_stop=log_stop,
                         placeholder="An answer is being written")
        ui.text("click — a tool of one's own.", color="muted", size="sm")
        with ui.message_input(on_submit=log_submit):
            ui.message_input_tool("Log a click", icon="mouse-pointer-click",
                                  on_click=log_tool)

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)", color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs", on_click=clear_log,
                  disabled=not state.log)
    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}", color="muted", size="sm", classes="font-mono")
    else:
        ui.text("(no events yet — send, stop, or click the tool)", color="muted",
                size="sm")

    ui.divider()
    emitted_html_block(
        "Emitted HTML (representative — the busy box : submit on the form, "
        "stop relayed by a hidden carrier)",
        serialize_html(ui.message_input(on_submit=log_submit, loading=True,
                                        on_stop=log_stop)),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Message input", level=1)
            ui.text(
                "Where a message is written — to an AI, or to anyone. One "
                "rounded box : the children that are not tools at its top, the "
                "joined files, the text, then one bar (the clip, the "
                "microphone, your tools, the round button). Enter sends, "
                "Shift+Enter breaks the line ; the box empties itself once "
                "the message has left ; it never sends twice while busy.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop. No size, colour nor "
                            "variant : one box, its look set by the theme.",
                            color="muted", size="sm")

                    ui.heading("Plain", level=3)
                    ui.message_input(on_submit=echo, placeholder="Write a message")

                    ui.heading("files= — the clip, the chips, paste and drop", level=3)
                    ui.message_input(on_submit=echo, files=(".pdf", "image/*"),
                                     placeholder="Join a PDF or a picture")

                    ui.heading("voice=True — the browser's dictation", level=3)
                    ui.text("The microphone only shows in a browser that can "
                            "dictate (Chrome, Edge, Safari).", color="muted", size="xs")
                    ui.message_input(on_submit=echo, voice=True, placeholder="Dictate, or type")

                    ui.heading("loading=True — Envoyer becomes Arrêter", level=3)
                    ui.message_input(on_submit=echo, loading=True, on_stop=log_stop,
                                     placeholder="An answer is being written")

                    ui.heading("max_length — a counter in the bar", level=3)
                    ui.message_input(on_submit=echo, max_length=280, value="A short message",
                                     placeholder="280 characters at most")

                    ui.heading("max_files, max_size_mb — the picker's checks", level=3)
                    ui.message_input(on_submit=echo, files=(".pdf", "image/*"), max_files=2, max_size_mb=5,
                                     placeholder="Two files, 5 MB each, at most")

                    ui.heading("disabled=True", level=3)
                    ui.message_input(on_submit=echo, disabled=True, files=(".pdf",), voice=True,
                                     placeholder="Nothing can be written now")

                    ui.heading("value= — pre-filled", level=3)
                    ui.message_input(on_submit=echo, value="A draft kept from last time")

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text("No named slot : the children ARE the composition. "
                            "A tool goes to the bar, anything else to the top.",
                            color="muted", size="sm")

                    ui.heading("A badge at the top — what the message is about",
                               level=3)
                    with ui.message_input(on_submit=echo, ):
                        ui.badge("5e1 · Liste", variant="soft", icon_left="at-sign",
                                 dismissible=True)

                    ui.heading("Tools in the bar — label, icon, disabled", level=3)
                    with ui.message_input(on_submit=echo, voice=True):
                        ui.message_input_tool("Insert a template", icon="file-text",
                                              on_click=log_tool)
                        ui.message_input_tool("Not available yet", icon="calendar",
                                              disabled=True)
                    ui.heading("A menu of tools — a dropdown whose trigger is a tool", level=3)
                    with ui.message_input(on_submit=echo):
                        with ui.dropdown(trigger=ui.message_input_tool("Add", icon="plus")):
                            ui.dropdown_item("Insert a template", icon_left="file-text",
                                             on_click=log_tool)
                            ui.dropdown_item("Attach a document", icon_left="folder-open",
                                             on_click=log_tool)

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Inputs that historically break.", color="muted", size="sm")

                    ui.heading("A long text — the field grows, then scrolls", level=3)
                    ui.message_input(on_submit=echo, value=("A line of a long message.\n" * 14).strip())

                    ui.heading("HTML-special characters (XSS escape)", level=3)
                    ui.message_input(on_submit=echo, value="<script>alert(1)</script>")

                    ui.heading("Many badges in a narrow box — they wrap", level=3)
                    with ui.message_input(on_submit=echo, classes="max-w-xs"):
                        for code in ("6e2", "5e1", "5e3", "4e2", "3e1", "3e4", "2de3"):
                            ui.badge(code, variant="soft", dismissible=True)

                    ui.heading("No handler — Enter does nothing to the server",
                               level=3)
                    ui.message_input(placeholder="No on_submit")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("In the places it breaks : a narrow cell, the foot of "
                            "a pane of bounded height under a thread.",
                            color="muted", size="sm")

                    ui.heading("In a narrow grid cell", level=3)
                    with ui.grid(cols=3, gap="md"):
                        ui.message_input(on_submit=echo, files=(".pdf",), voice=True,
                                         placeholder="Narrow")
                        ui.text("A neighbour", color="muted", size="sm")
                        ui.text("Another", color="muted", size="sm")

                    ui.heading("At the foot of a bounded pane, under a thread",
                               level=3)
                    with ui.card(padding="none", classes="h-96"):
                        with ui.vstack(gap="none", classes="h-full"):
                            with ui.message_list(classes="px-4"):
                                for n in range(4):
                                    ui.message(f"Question {n + 1}", side="end")
                                    ui.message(f"Answer {n + 1}, in **markdown**.",
                                               variant="plain", markdown=True)
                            with ui.vstack(classes="p-3"):
                                ui.message_input(on_submit=echo, placeholder="The next question")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "The box is a <form> ; every icon button has an "
                        "accessible name (Joindre un fichier, Dicter, Envoyer, "
                        "Arrêter, and a tool's label) ; the microphone says "
                        "aria-pressed while it listens. Tab moves from the text "
                        "to the bar ; Enter sends, Shift+Enter breaks the line.",
                        color="muted", size="sm",
                    )
                    ui.message_input(on_submit=echo, files=(".pdf",), voice=True,
                                     attrs={"aria-label": "Ask the assistant"},
                                     placeholder="Tab here, then Tab to the bar")

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text("Every prop AND every escape hatch is wired to a "
                            "control ; the preview AND the emitted HTML refresh "
                            "on every change.", color="muted", size="sm")
                    server_panel()

            # ── Card 7 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    ui.text("submit (the message and its files), stop (the "
                            "answer interrupted), and a tool's click.",
                            color="muted", size="sm")
                    events_panel()

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of BINDABLE_PROPS = ('value', 'loading'). The text "
                        "two-ways through bz-model ; loading flips Envoyer and "
                        "Arrêter by bz-show — no round trip.",
                        color="muted", size="sm",
                    )
                    client = MessageInputClient(key="playground")
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("value (the same field)"):
                            ui.input(value=client.value)
                        with control("loading"):
                            ui.switch(checked=client.loading)
                    ui.divider()
                    ui.message_input(on_submit=echo, value=client.value, loading=client.loading,
                                     on_stop=client.loading.set(False))
                    ui.divider()
                    emitted_html_block(
                        "Emitted HTML — bz-model on the textarea, bz-show on "
                        "the two round buttons.",
                        serialize_html(ui.message_input(on_submit=echo, value=client.value,
                                                        loading=client.loading)),
                    )

            # ── Card 9 — External controls — the 3 modes ────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes", level=2)
                    ui.text("The same scenario — set, clear, focus the box from "
                            "outside — three ways.", color="muted", size="sm")

                    ui.heading("Mode 1 — Imperative only (default)", level=3)
                    m1 = ui.message_input(on_submit=echo, placeholder="Imperative — no ClientState")
                    with ui.hstack(gap="sm"):
                        ui.button("Set", on_click=m1.set("Set via Mode 1."))
                        ui.button("Clear", variant="outline", on_click=m1.clear())
                        ui.button("Focus", variant="ghost", on_click=m1.focus())

                    ui.divider()
                    ui.heading("Mode 2 — ClientBinding only", level=3)
                    bound = MessageInputClient(key="binding_only")
                    ui.message_input(on_submit=echo, value=bound.value)
                    with ui.hstack(gap="sm"):
                        ui.button("Set via binding.set(...)",
                                  on_click=bound.value.set("Set via the binding."))
                        ui.button("Clear via binding.set('')", variant="outline",
                                  on_click=bound.value.set(""))

                    ui.divider()
                    ui.heading("Mode 3 — Both (write-through)", level=3)
                    both = MessageInputClient(key="both")
                    with control("mirror (also bound)"):
                        ui.input(value=both.value)
                    m3 = ui.message_input(on_submit=echo, value=both.value)
                    with ui.hstack(gap="sm"):
                        ui.button("Set via box.set(...)", on_click=m3.set("Mode 3."))
                        ui.button("Clear via box.clear()", variant="outline",
                                  on_click=m3.clear())
                        ui.button("Focus", variant="ghost", on_click=m3.focus())

                    ui.divider()
                    emitted_html_block(
                        "Emitted HTML — Mode 2 : bz-model reads the bound path.",
                        serialize_html(ui.message_input(on_submit=echo, value=bound.value)),
                    )

            # ── Card 10 — Client events ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text("submit and stop as client expressions, pushed onto a "
                            "ClientState list — zero network.", color="muted",
                            size="sm")
                    cevents = MessageInputClientEvents()
                    said = ClientExpression(
                        "'submit: ' + $el.querySelector('textarea').value")
                    with ui.vstack(classes="w-full max-w-xl"):
                        ui.message_input(on_submit=cevents.log.push(said),
                                         placeholder="Enter pushes a line")
                        ui.message_input(on_submit=echo, loading=True, on_stop=cevents.log.push("stop"),
                                         placeholder="The square pushes « stop »")
                        with ui.message_input(on_submit=echo, ):
                            ui.message_input_tool("Push a line", icon="plus",
                                                  on_click=cevents.log.push("tool"))
                    ui.divider()
                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive — no refresh)",
                                color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())
                    log_text = ClientExpression(
                        '($bz.state.MessageInputClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text, color="muted", size="sm",
                            classes="font-mono whitespace-pre")
                    ui.divider()
                    emitted_html_block(
                        "Emitted HTML (representative — the submit box)",
                        serialize_html(ui.message_input(
                            on_submit=cevents.log.push(said))),
                    )
