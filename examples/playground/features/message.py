"""``Message`` test bench.

Nine cards. ``EVENTS = ("retry",)`` — Server events and Client events.
``BINDABLE_PROPS = ("text", "writing")`` — the Client playground.
``IMPERATIVE = ()`` — no External controls. Slots : none named — the
children go under the text, shown in the Slots card.

Props : ``text`` (first) / ``side`` (``"start"`` | ``"end"``) /
``author`` / ``avatar`` (initials, or a component) / ``variant``
(``"bubble"`` | ``"plain"``) / ``markdown`` / ``files`` / ``time`` /
``status`` (``"sending"`` | ``"error"``) / ``writing`` / ``copyable`` /
``on_retry``.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/message"

SIDES = ["start", "end"]
VARIANTS = ["bubble", "plain"]
STATUSES = ["", "sending", "error"]
ANSWER = ("Revenue grew **12 %** over the quarter.\n\n"
          "- Churn fell to 2.1 %\n- Two regions missed their target\n\n"
          "| Region | Target |\n|---|---|\n| North | 96 % |\n| South | 88 % |")


def ai():
    """The assistant's avatar: an icon — the message makes it a chip."""
    return ui.icon("sparkles")


class MessagePlayground(PageState):
    text:        str  = field(default="Revenue grew **12 %** over the quarter.")
    side:        str  = field(default="start")
    author:      str  = field(default="Marie")
    avatar:      str  = field(default="MA")
    variant:     str  = field(default="bubble")
    markdown:    bool = field(default=True)
    files:       str  = field(default="")
    time:        str  = field(default="14:02")
    status:      str  = field(default="")
    writing:     bool = field(default=False)
    copyable:    bool = field(default=True)
    retry:       bool = field(default=False)
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifiers.
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")


class MessageEvents(PageState):
    log: list = field(default_factory=list)


class MessageClient(ClientState, persist="memory"):
    """Mirror of Message's BINDABLE_PROPS."""

    text:    str  = field(default="An answer written slice by slice")
    writing: bool = field(default=True)


class MessageClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


def log_retry() -> None:
    state = MessageEvents()
    state.log = [*state.log, "retry"]


def clear_log() -> None:
    MessageEvents().log = []


def server_changed(state: MessagePlayground) -> None:
    pass


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: MessagePlayground):
    kwargs: dict = {"side": state.side, "variant": state.variant, "markdown": state.markdown,
                    "writing": state.writing, "copyable": state.copyable}
    names = [n.strip() for n in state.files.split(",") if n.strip()]
    if names:
        kwargs["files"] = names
    for key in ("author", "avatar", "time", "status"):
        if getattr(state, key):
            kwargs[key] = getattr(state, key)
    if state.retry:
        kwargs["on_retry"] = log_retry
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
    return ui.message(state.text, **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable
def server_panel() -> None:
    state = MessagePlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("text"):
            ui.input(value=state.text, on_change=server_changed)
        with control("side"):
            ui.select(value=state.side, options=[(s, s) for s in SIDES],
                      on_change=server_changed)
        with control("variant"):
            ui.select(value=state.variant, options=[(v, v) for v in VARIANTS],
                      on_change=server_changed)
        with control("author"):
            ui.input(value=state.author, placeholder="Marie", on_change=server_changed)
        with control("avatar (initials)"):
            ui.input(value=state.avatar, placeholder="MA", on_change=server_changed)
        with control("files (names, comma separated)"):
            ui.input(value=state.files, placeholder="q3-report.pdf, chart.png",
                     on_change=server_changed)
        with control("time"):
            ui.input(value=state.time, placeholder="14:02", on_change=server_changed)
        with control("status"):
            ui.select(value=state.status, options=[(s, s or "(none)") for s in STATUSES],
                      on_change=server_changed)
        with control("markdown"):
            ui.switch(checked=state.markdown, on_change=server_changed)
        with control("writing"):
            ui.switch(checked=state.writing, on_change=server_changed)
        with control("copyable"):
            ui.switch(checked=state.copyable, on_change=server_changed)
        with control("on_retry"):
            ui.switch(checked=state.retry, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="max-w-md", on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="answer-1", on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Answer of the assistant",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="opacity: .8", on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=2, placeholder="data-test=msg",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Sent at 14:02",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"), ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()
    with ui.vstack(classes="w-full max-w-xl mx-auto"):
        build_preview(state)
    ui.divider()
    emitted_html_block("Emitted HTML", serialize_html(build_preview(state)))


@refreshable
def events_panel() -> None:
    state = MessageEvents()
    with ui.vstack(classes="w-full max-w-xl"):
        ui.message("Not sent — retry it", side="end", status="error", on_retry=log_retry)
        ui.message("An answer to regenerate", avatar=ai(), variant="plain",
                   on_retry=log_retry)
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
        ui.text("(no events yet — click a « Retry »)", color="muted", size="sm")
    ui.divider()
    emitted_html_block(
        "Emitted HTML (representative — retry relayed by $dispatch to the root)",
        serialize_html(ui.message("x", status="error", on_retry=log_retry)),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Message", level=1)
            ui.text(
                "One message of a conversation, whoever says it — a person or an "
                "AI. side= says where it sits (start: the others, end: mine), "
                "author= and avatar= who said it ; variant= a bubble or the plain "
                "width ; markdown= whether the text is read as markdown.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop. No size nor colour : mine "
                            "take the accent, the others a neutral tint.",
                            color="muted", size="sm")
                    with ui.vstack(gap="md", classes="w-full max-w-xl"):
                        ui.heading("side — start (default), end", level=3)
                        ui.message("Can we meet on Thursday?")
                        ui.message("Yes, at 10.", side="end")

                        ui.heading("author, avatar, time", level=3)
                        ui.message("I'll bring the reports.", author="Marie", avatar="MA",
                                   time="14:02")

                        ui.heading("variant=plain + markdown — an AI's answer", level=3)
                        ui.message(ANSWER, avatar=ai(), variant="plain", markdown=True)

                        ui.heading("files", level=3)
                        ui.message("Here are the two exports.", side="end",
                                   files=["q3-report.pdf", "chart.png"])

                        ui.heading("status — sending, error", level=3)
                        ui.message("On its way", side="end", status="sending")
                        ui.message("The network dropped", side="end", status="error",
                                   on_retry=log_retry)

                        ui.heading("writing — still being written", level=3)
                        ui.message("Looking at the regions", avatar=ai(), variant="plain",
                                   writing=True)

                        ui.heading("copyable, on_retry — the answer's actions", level=3)
                        ui.message("A paragraph to copy or regenerate.", avatar=ai(),
                                   variant="plain", copyable=True, on_retry=log_retry)

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text("No named slot : what goes in the ``with`` lands under "
                            "the text, in the same column.", color="muted", size="sm")
                    with ui.vstack(gap="md", classes="w-full max-w-xl"):
                        with ui.message("I added the 24 pupils.", avatar=ai(),
                                        variant="plain"):
                            with ui.accordion(collapsible=True):
                                with ui.accordion_item("steps", label="2 steps",
                                                       icon="list-checks"):
                                    ui.text("Read the list · Read the class",
                                            color="muted", size="sm")
                            with ui.card(padding="sm"):
                                with ui.hstack(justify="between", align="center"):
                                    ui.text("24 pupils added", size="sm")
                                    ui.button("Undo", variant="ghost", size="xs")

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    with ui.vstack(gap="md", classes="w-full max-w-xl"):
                        ui.heading("No text — only files", level=3)
                        ui.message(side="end", files=["only-a-file.pdf"])

                        ui.heading("No text, writing — the spinner alone", level=3)
                        ui.message(avatar=ai(), variant="plain", writing=True)

                        ui.heading("A word longer than the bubble", level=3)
                        ui.message("x" * 160, side="end")

                        ui.heading("A long URL and a code block in an answer", level=3)
                        ui.message("See https://example.com/" + "a" * 90 + "\n\n```\n"
                                   + "print('a long line of code that does not fit')" * 3
                                   + "\n```", avatar=ai(), variant="plain", markdown=True)

                        ui.heading("HTML-special characters (XSS escape)", level=3)
                        ui.message("<script>alert(1)</script>", side="end")
                        ui.message("<script>alert(1)</script>", markdown=True)

                        ui.heading("A long author name", level=3)
                        ui.message("Hello", author="Marie-Charlotte de La Fontaine-Dubois",
                                   avatar="MC")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.heading("In a narrow grid cell", level=3)
                    with ui.grid(cols=3, gap="md"):
                        with ui.vstack(gap="sm"):
                            ui.message("A narrow question", side="end")
                            ui.message("A narrow answer, in **markdown**.", avatar=ai(),
                                       variant="plain", markdown=True)
                        ui.text("A neighbour", color="muted", size="sm")
                        ui.text("Another", color="muted", size="sm")
                    ui.heading("In a ui.message_list — grouped by author", level=3)
                    with ui.card(padding="none", classes="h-80"):
                        with ui.message_list(classes="px-4"):
                            ui.message("Hi all", author="Marie", avatar="MA")
                            ui.message("The meeting moves to 11.", author="Marie",
                                       avatar="MA")
                            ui.message("Fine by me", side="end")
                            ui.message("Same", author="Paul", avatar="PA")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Each message is named for a screen reader — « Message de "
                        "Marie », « Votre message » ; the avatar is decorative "
                        "(aria-hidden) ; an answer being written is a polite live "
                        "region ; an error is an alert ; the actions are named "
                        "buttons (Copier, Réessayer).",
                        color="muted", size="sm",
                    )
                    with ui.vstack(gap="md", classes="w-full max-w-xl"):
                        ui.message("Read aloud with its author.", author="Marie",
                                   avatar="MA")
                        ui.message("Announced as it arrives", avatar=ai(),
                                   variant="plain", writing=True)

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text("Every prop AND every escape hatch is wired to a "
                            "control.", color="muted", size="sm")
                    server_panel()

            # ── Card 7 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    ui.text("retry — « Réessayer » under a message.", color="muted",
                            size="sm")
                    events_panel()

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of BINDABLE_PROPS = ('text', 'writing'). Bound, the "
                        "text is plain (markdown needs the server) and follows its "
                        "field by bz-text ; writing shows the spinner by bz-show.",
                        color="muted", size="sm",
                    )
                    client = MessageClient(key="playground")
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("text (type here)"):
                            ui.input(value=client.text)
                        with control("writing"):
                            ui.switch(checked=client.writing)
                    ui.divider()
                    with ui.vstack(classes="w-full max-w-xl"):
                        ui.message(client.text, avatar=ai(), variant="plain",
                                   writing=client.writing)
                    ui.divider()
                    emitted_html_block(
                        "Emitted HTML — bz-text on the text, bz-show on the spinner.",
                        serialize_html(ui.message(client.text, writing=client.writing)),
                    )

            # ── Card 9 — Client events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text("retry as a client expression — zero network.",
                            color="muted", size="sm")
                    cevents = MessageClientEvents()
                    with ui.vstack(classes="w-full max-w-xl"):
                        ui.message("Retry pushes a line", side="end", status="error",
                                   on_retry=cevents.log.push("retry"))
                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive — no refresh)",
                                color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())
                    ui.text(ClientExpression(
                        '($bz.state.MessageClientEvents.default.log || []).join("\\n")'
                        ' || "(no events yet)"'), color="muted", size="sm",
                        classes="font-mono whitespace-pre")
                    emitted_html_block(
                        "Emitted HTML (representative)",
                        serialize_html(ui.message("x", status="error",
                                                  on_retry=cevents.log.push("retry"))),
                    )
