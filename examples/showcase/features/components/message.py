"""``/message`` — a conversation: messages, and the box they are written in."""

from bretzel import refreshable, ui
from bretzel.state import ClientState, PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A conversation in three components, for people or an AI: "
           "ui.message shows one message, ui.message_list the thread that follows "
           "its newest, ui.message_input the box the next one is written in — "
           "files, voice and your own tools inside it.")


def two_shapes() -> None:
    with ui.vstack(gap="md", classes="w-full max-w-xl"):
        ui.message("Can you summarise the quarterly report?", side="end",
                   files=["q3-report.pdf"])
        ui.message("Revenue grew **12 %** over the quarter, driven by the new "
                   "subscriptions.\n\n- Churn fell to 2.1 %\n- Two regions missed "
                   "their target", avatar=ui.icon("sparkles"),
                   variant="plain", markdown=True, copyable=True)
        ui.message("Thinking about the regions", avatar=ui.icon("sparkles"),
                   variant="plain", writing=True)
        ui.message("And the team chat?", author="Marie", avatar="MA", time="14:02")


class Thread(PageState):
    said: list = field(default_factory=list)


class Draft(ClientState):
    text: str = field(default="")


def reply(files=None) -> None:
    """The message as it left: the text from the draft, the files posted
    with it — answered here by an echo, by an AI elsewhere."""
    text = (Draft().text or "").strip()
    names = [f.filename for f in (files if isinstance(files, list) else [files])
             if hasattr(f, "filename")]
    thread = Thread()
    thread.said = [*thread.said, {"role": "user", "text": text, "files": names},
                   {"role": "assistant",
                    "text": f"You wrote {len(text.split())} word(s)"
                            + (f" and joined {len(names)} file(s)." if names else ".")}]


@refreshable
def conversation() -> None:
    with ui.message_list(classes="px-1"):
        for one in Thread().said:
            ui.message(one["text"], side="end" if one["role"] == "user" else "start",
                       files=one.get("files"))
        if not Thread().said:
            ui.text("Nothing said yet.", color="muted", size="sm")


def write_and_send() -> None:
    with ui.vstack(gap="lg", classes="w-full max-w-xl h-96"):
        conversation()
        with ui.message_input(value=Draft().text, on_submit=reply, voice=True,
                              files=(".pdf", "image/*"),
                              placeholder="Ask, dictate, drop a file…"):
            ui.badge("Q3 report", variant="soft", icon_left="at-sign", dismissible=True)
            ui.message_input_tool("Insert a template", icon="file-text",
                                  on_click="alert('A dialog of templates would open here.')")


def page() -> None:
    page_header("message", "Message", SUMMARY)
    example("Two shapes, one thread", two_shapes,
            note="The user's bubble sized to its words; the answer behind its "
                 "mark, in markdown, still being written.")
    example("Write and send", write_and_send, uses=[Thread, Draft, reply, conversation],
            note="Enter sends, Shift+Enter breaks the line; the box empties "
                 "itself once the message has left.")
