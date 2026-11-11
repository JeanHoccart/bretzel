"""``MessageList`` test bench.

Five cards. ``EVENTS = ()``, ``BINDABLE_PROPS = ()``, ``IMPERATIVE = ()``
— no events, Client playground nor External controls cards. No prop of
its own : its children ARE the thread (any component ; the messages of
the same author and side in a row are grouped). The Server playground
adds a message to watch the list follow it — and not follow it once you
scrolled up.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/message_list"


class ListPlayground(PageState):
    said: int = field(default=6)
    writing: bool = field(default=False)
    # Escape hatches.
    classes:     str = field(default="px-4")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")


class Chat(PageState):
    said: list = field(default_factory=list)


def server_changed(state: ListPlayground) -> None:
    pass


def ask(message: str = "") -> None:
    """A question in, an answer out — the list follows them."""
    chat = Chat()
    chat.said = [*chat.said, message.strip(),
                 f"You asked {len(message.split())} word(s) — noted."]


@refreshable
def live_thread() -> None:
    with ui.message_list(classes="px-4"):
        thread(8)
        for n, text in enumerate(Chat().said):
            if n % 2:
                ui.message(text, avatar=ai(), variant="plain")
            else:
                ui.message(text, side="end")


def add_one() -> None:
    ListPlayground().said += 2


def reset() -> None:
    ListPlayground().said = 6


def ai():
    return ui.icon("sparkles")


def thread(n: int, writing: bool = False) -> None:
    for i in range(n // 2):
        ui.message(f"Question {i + 1}", side="end")
        ui.message(f"Answer {i + 1} — a paragraph long enough to wrap on a narrow "
                   "screen, in **markdown**.", avatar=ai(), variant="plain",
                   markdown=True)
    if writing:
        ui.message("Still writing", avatar=ai(), variant="plain", writing=True)


def build_preview(state: ListPlayground):
    kwargs: dict = {}
    if state.classes:
        kwargs["classes"] = state.classes
    if state.custom_id:
        kwargs["id"] = state.custom_id
    if state.style:
        kwargs["style"] = state.style
    if state.aria_label:
        kwargs["attrs"] = {"aria-label": state.aria_label}
    if state.visible == "off":
        kwargs["visible"] = False
    box = ui.message_list(**kwargs)
    with box:
        thread(state.said, state.writing)
    return box


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable
def server_panel() -> None:
    state = ListPlayground()
    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("messages"):
            with ui.hstack(gap="sm"):
                ui.button("Add a question and its answer", icon_left="plus",
                          on_click=add_one)
                ui.button("Reset", variant="ghost", on_click=reset)
        with control("writing (an answer at the end)"):
            ui.switch(checked=state.writing, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="px-4", on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="thread", on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Conversation with Marie",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="background: …",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"), ("off", "False (skip render)")],
                      on_change=server_changed)
    ui.divider()
    ui.text("Add messages : the list follows. Scroll up, add one : it stays where "
            "you read, and « back to the latest message » appears.",
            color="muted", size="sm")
    with ui.card(padding="none", classes="h-80 w-full max-w-xl mx-auto"):
        build_preview(state)
    ui.divider()
    emitted_html_block("Emitted HTML", serialize_html(build_preview(state)))


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Message list", level=1)
            ui.text(
                "A conversation's thread. It scrolls itself and follows its "
                "newest message — a new one, an answer that grows — unless the "
                "reader scrolled up ; then « back to the latest message » "
                "appears. A message that follows one of the same author and side "
                "is grouped : its name and avatar are not repeated.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("A person-to-person chat, then an AI's — the same list.",
                            color="muted", size="sm")
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.card(padding="none", classes="h-80"):
                            with ui.message_list(classes="px-4"):
                                ui.message("Hi all", author="Marie", avatar="MA",
                                           time="09:01")
                                ui.message("The meeting moves to 11.", author="Marie",
                                           avatar="MA")
                                ui.message("Fine by me", side="end", time="09:03")
                                ui.message("Same", author="Paul", avatar="PA")
                                ui.message("See you there", author="Paul", avatar="PA")
                        with ui.card(padding="none", classes="h-80"):
                            with ui.message_list(classes="px-4"):
                                thread(6)

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("Empty — the button stays hidden", color="muted",
                                    size="sm")
                            with ui.card(padding="none", classes="h-40"):
                                ui.message_list()
                        with ui.vstack(gap="xs"):
                            ui.text("One message", color="muted", size="sm")
                            with ui.card(padding="none", classes="h-40"):
                                with ui.message_list(classes="px-4"):
                                    ui.message("Alone", side="end")
                        with ui.vstack(gap="xs"):
                            ui.text("A long thread — starts at its bottom", color="muted",
                                    size="sm")
                            with ui.card(padding="none", classes="h-40"):
                                with ui.message_list(classes="px-4"):
                                    thread(30)

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("The chat as an app writes it : the list takes the room, "
                            "the box sits under it.", color="muted", size="sm")
                    ui.text("Write and press Enter : the question and its answer "
                            "join the thread, which follows them.", color="muted",
                            size="sm")
                    with ui.card(padding="none", classes="h-96 max-w-xl"):
                        with ui.vstack(gap="none", classes="h-full"):
                            live_thread()
                            with ui.vstack(classes="p-3"):
                                ui.message_input(placeholder="The next question",
                                                 voice=True, on_submit=ask)

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "The list is a log (role=\"log\", named « Conversation ») : "
                        "what is added is read out politely. « Revenir au dernier "
                        "message » is a named button, reachable with Tab when it "
                        "shows. Each message is named for its author.",
                        color="muted", size="sm",
                    )
                    with ui.card(padding="none", classes="h-48 max-w-xl"):
                        with ui.message_list(classes="px-4"):
                            thread(10)

            # ── Card 5 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    server_panel()
