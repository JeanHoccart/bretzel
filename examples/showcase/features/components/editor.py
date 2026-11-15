"""``/editor`` — text that formats, kept as Markdown."""

from bretzel import refreshable, ui
from bretzel.state import ClientState, PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A text field with bold, italic, lists and links — and a value "
           "that is plain Markdown, ready to store, send or hand to an AI.")


def reply() -> None:
    with ui.vstack(gap="md", classes="w-full max-w-xl"):
        ui.editor(placeholder="Write your reply — Ctrl+B, Ctrl+I, Ctrl+K, "
                              "or start a line with “- ”")
        with ui.hstack(justify="end"):
            ui.button("Send", icon_left="send")


class Draft(ClientState):
    text: str = field(default=(
        "Hi team,\\\n"
        "Here is where we are on the **launch**:\n"
        "\n"
        "- pricing page — *done*\n"
        "- onboarding emails\n"
        "  - copy approved\n"
        "  - design in review\n"
        "\n"
        "Details in [the plan](https://example.org/plan)."
    ))


def markdown_value() -> None:
    draft = Draft()
    with ui.grid(cols={"base": 1, "md": 2}, gap="md", classes="w-full"):
        ui.editor(value=draft.text)
        ui.textarea(value=draft.text, rows=12, classes="font-mono text-xs",
                    attrs={"aria-label": "The Markdown"})


def ask_claude() -> None:
    ui.notification("Your assistant would rewrite the text here.", color="info")


def tools() -> None:
    with ui.vstack(classes="w-full max-w-xl"):
        with ui.editor(placeholder="Your own buttons sit after the formatting ones"):
            ui.editor_tool("Ask the assistant", icon="sparkles", on_click=ask_claude)
            with ui.dropdown(trigger=ui.editor_tool("Insert", icon="plus")):
                ui.dropdown_item("A template", icon_left="file-text")
                ui.dropdown_item("A signature", icon_left="pen-line")


def ghost() -> None:
    with ui.card(padding="none", classes="w-full max-w-xl"):
        with ui.vstack(gap="none"):
            with ui.hstack(classes="px-4 py-3"):
                ui.text("Subject", color="muted", size="sm")
                ui.text("Quarterly review", size="sm", weight="medium")
            ui.divider()
            ui.editor(variant="ghost", placeholder="Write the message…")


class Note(PageState):
    text: str = field(default="")
    saved: str = field(default="")


def save(note: Note) -> None:
    note.saved = note.text


@refreshable
def saved_note() -> None:
    note = Note()
    with ui.vstack(gap="sm", classes="w-full max-w-xl"):
        ui.editor(value=note.text, on_change=save, debounce=800,
                  placeholder="Notes save themselves a moment after you stop")
        ui.text(f"Saved: {len(note.saved)} characters of Markdown" if note.saved
                else "Nothing saved yet", size="sm", color="muted")


def autosave() -> None:
    saved_note()


def page() -> None:
    page_header("editor", "Editor", SUMMARY)
    example("A reply", reply)
    example("The value is Markdown", markdown_value, uses=[Draft],
            note="The editor and the textarea share one ClientState field: edit "
                 "either, the other follows, in the browser.")
    example("Buttons of your own", tools, uses=[ask_claude])
    example("Ghost, inside a mail", ghost,
            note="variant=\"ghost\" drops the background and the frame: the card "
                 "and its lines structure the screen.")
    example("Save as you type", autosave, uses=[Note, save, saved_note],
            note="on_change with debounce=800 posts the Markdown to Python once "
                 "the typing pauses.")
