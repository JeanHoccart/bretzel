"""``/markdown`` — prose written in Markdown, typeset by the theme."""

from bretzel import refreshable, ui
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Headings, lists, links, tables and code from a Markdown string — "
           "rendered on the server, styled by the theme.")


def release_notes() -> None:
    ui.markdown("""\
## Version 2.4 — September 2026

**Recurring invoices** are here. Set a schedule once and Northwind sends,
chases and reconciles every month.

- Invoices now support **multiple currencies** per customer
- Faster exports: a 50,000-row CSV takes *under two seconds*
- The `/v1/invoices` endpoint accepts an `idempotency_key`

Read the [migration guide](https://docs.bretzel-py.dev) before upgrading.
""", classes="w-full max-w-2xl")


def help_article() -> None:
    ui.markdown("""\
### Which plan is right for my team?

> Most teams start on **Team** and move to Business when they need SSO.

| Plan     | Seats     | SSO | Support        |
|----------|-----------|-----|----------------|
| Starter  | up to 3   | —   | Community      |
| Team     | up to 50  | —   | Email, 24 h    |
| Business | unlimited | Yes | Priority, 1 h  |

1. Open **Settings → Billing**
2. Pick a plan and confirm
3. The new seats are available immediately
""", classes="w-full max-w-2xl")


def comment() -> None:
    with ui.card(padding="md", classes="w-full max-w-xl"), ui.hstack(gap="md", align="start"):
        ui.avatar(name="Lena Novak", src="https://i.pravatar.cc/96?u=Lena", size="sm")
        with ui.vstack(gap="xs", classes="min-w-0"):
            with ui.hstack(gap="sm"):
                ui.text("Lena Novak", weight="semibold", size="sm")
                ui.text("2 hours ago", color="muted", size="xs")
            ui.markdown("Reproduced on **Safari 18** only. The date picker "
                        "closes before the click lands — see `onBlur` in "
                        "the trigger. Fix in ~~#412~~ #418.")


class Note(PageState):
    text: str = field(default="## Standup — Monday\n\n"
                              "- **Maya**: shipped the export dialog\n"
                              "- **Idris**: fixing the *Safari* date bug\n\n"
                              "Next review on `Thursday`.")


def note_changed(note: Note) -> None:
    """Typing hydrates ``Note.text``; the preview re-renders."""


@refreshable
def note_preview() -> None:
    ui.markdown(Note().text)


def live_editor() -> None:
    with ui.grid(cols={"base": 1, "md": 2}, gap="md", classes="w-full"):
        ui.textarea(value=Note().text, rows=9, on_input=note_changed, debounce=250,
                    classes="font-mono")
        with ui.card(padding="md"):
            note_preview()


def page() -> None:
    page_header("markdown", "Markdown", SUMMARY)
    example("Release notes", release_notes,
            note="Headings, emphasis, lists, inline code and links, each styled "
                 "by the theme.")
    example("A help-centre article", help_article,
            note="Tables, blockquotes and numbered lists come out typeset too.")
    example("A user comment", comment,
            note="Stored as Markdown, shown as prose. HTML in the source is "
                 "escaped, so user text is safe to render.")
    example("A live preview", live_editor, full=True,
            uses=[Note, note_changed, note_preview],
            note="Type on the left: the server renders the Markdown and only "
                 "the preview zone is swapped.")
