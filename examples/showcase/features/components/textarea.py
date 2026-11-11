"""``/textarea`` — text that takes more than one line."""

from datetime import datetime

from bretzel import refreshable, ui
from bretzel.state import ClientState, PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Room for a message, a note or a description — with a live "
           "character count and a submit that reaches Python.")


def feedback() -> None:
    with ui.vstack(gap="md", classes="w-full max-w-md"):
        with ui.form_field(label="What could we do better?",
                           hint="Your answer goes straight to the product team."):
            ui.textarea(rows=4, placeholder="The export to CSV takes too many "
                                            "clicks when…")
        ui.button("Send feedback", icon_left="send", classes="self-end")


class StatusDraft(ClientState):
    text: str = field(default="Shipping the new billing page today 🚀")


def character_count() -> None:
    draft = StatusDraft()
    with ui.vstack(gap="xs", classes="w-full max-w-md"):
        ui.textarea(value=draft.text, rows=3, maxlength=280,
                    placeholder="What are you working on?")
        with ui.hstack(gap="xs", justify="end"):
            ui.text(draft.text.length(), size="sm", color="muted")
            ui.text("/ 280", size="sm", color="muted")


def sizes() -> None:
    with ui.vstack(gap="sm", classes="w-full max-w-md"):
        for size in ("sm", "md", "lg"):
            ui.textarea(size=size, rows=2, placeholder=f"Add a note ({size})")


class Thread(PageState):
    comments: list = field(default_factory=lambda: [
        ["Omar Haddad", "10:12", "Can we move the launch to Thursday?"],
        ["Lucía Romero", "10:40", "Thursday works — I'll tell the three "
                                  "pilot customers."],
    ])
    reply: str = field(default="")


def post_comment(thread: Thread) -> None:
    if thread.reply.strip():
        now = datetime.now().strftime("%H:%M")
        thread.comments = [*thread.comments, ["You", now, thread.reply.strip()]]
    thread.reply = ""


@refreshable
def comment_thread() -> None:
    thread = Thread()
    with ui.vstack(gap="md", classes="w-full max-w-md"):
        for author, time, text in thread.comments:
            with ui.hstack(gap="sm", align="start"):
                ui.avatar(src=f"https://i.pravatar.cc/96?u={author}", name=author,
                          size="sm")
                with ui.vstack(gap="none"):
                    with ui.hstack(gap="sm"):
                        ui.text(author, weight="medium", size="sm")
                        ui.text(time, color="muted", size="xs")
                    ui.text(text)
        with ui.form(on_submit=post_comment), ui.vstack(gap="sm"):
            ui.textarea(value=thread.reply, rows=2, placeholder="Reply to the "
                                                                 "thread…")
            ui.button("Comment", type="submit", size="sm", classes="self-end")


def comments() -> None:
    comment_thread()


def states() -> None:
    with ui.vstack(gap="md", classes="w-full max-w-md"):
        with ui.form_field(label="Release notes", hint="Published — read only."):
            ui.textarea(rows=2, readonly=True,
                        value="Invoices can now be split across two "
                              "cost centres.")
        with ui.form_field(label="Internal note"):
            ui.textarea(rows=2, disabled=True,
                        value="Locked while the invoice is being paid.")


def page() -> None:
    page_header("textarea", "Textarea", SUMMARY)
    example("A feedback form", feedback)
    example("A live character count", character_count, uses=[StatusDraft],
            note="The value is bound to a ClientState: the counter updates in "
                 "the browser, with no request.")
    example("Sizes", sizes)
    example("Post a comment", comments, uses=[Thread, post_comment, comment_thread],
            note="The form posts the reply to Python; the handler appends it "
                 "and the thread re-renders.")
    example("Read-only and disabled", states)
