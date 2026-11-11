"""``/notification`` — a toast, fired from a Python handler."""

import functools

from bretzel import ui
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Call ui.notification() in any handler and a toast appears in "
           "the corner — four tones, a title, a place, a lifetime.")


def saved() -> None:
    ui.notification("Your changes have been saved.", color="success")


def synced() -> None:
    ui.notification("12 new contacts were imported from HubSpot.",
                    color="info")


def quota() -> None:
    ui.notification("You have used 90% of this month's email sends.",
                    color="warning")


def failed() -> None:
    ui.notification("The payment provider did not answer. Try again in a "
                    "minute.", color="error")


def variants() -> None:
    with ui.hstack(gap="sm", wrap=True, justify="center"):
        ui.button("Save", color="success", variant="soft", on_click=saved)
        ui.button("Import", color="info", variant="soft", on_click=synced)
        ui.button("Check quota", color="warning", variant="soft",
                  on_click=quota)
        ui.button("Charge card", color="error", variant="soft",
                  on_click=failed)


def invoice_sent() -> None:
    ui.notification("Northwind Traders will receive INV-2042 in a minute.",
                    title="Invoice sent", color="success", icon="send")


def with_title() -> None:
    ui.button("Send invoice", icon_left="send", on_click=invoice_sent)


def show_at(position: str) -> None:
    ui.notification(f"Anchored {position.replace('-', ' ')}.",
                    color="info", position=position, duration_ms=2500)


def positions() -> None:
    with ui.grid(cols=3, gap="sm", classes="w-full max-w-md"):
        for position in ("top-left", "top-center", "top-right",
                         "bottom-left", "bottom-center", "bottom-right"):
            ui.button(position.replace("-", " ").capitalize(), size="sm",
                      variant="outline",
                      on_click=functools.partial(show_at, position))


class Invite(PageState):
    email: str = field(default="")


def send_invite(form: Invite) -> None:
    email = form.email.strip()
    if "@" not in email:
        ui.notification("Enter an email address to send the invitation.",
                        color="warning", duration_ms=3000)
        return
    form.email = ""
    ui.notification(f"{email} can now join the Design workspace.",
                    title="Invitation sent", color="success")


def after_a_form() -> None:
    invite = Invite()
    with (ui.card(padding="md", classes="w-full max-w-md"),
          ui.form(on_submit=send_invite), ui.vstack(gap="md")):
        with ui.form_field(label="Invite a teammate"):
            ui.input(value=invite.email, type="email", icon_left="mail",
                     placeholder="grace@northwind.com")
        ui.button("Send invitation", type="submit", classes="self-end")


def maintenance() -> None:
    ui.notification("A new version is deployed. Reload the page to get it.",
                    title="Update ready", color="info", icon="rocket",
                    duration_ms=0)


def sticky() -> None:
    ui.button("Deploy", icon_left="rocket", variant="outline",
              on_click=maintenance)


def page() -> None:
    page_header("notification", "Notification", SUMMARY)
    example("Four tones", variants, uses=[saved, synced, quota, failed],
            note="Each button runs a Python handler; the toast is queued "
                 "during the request and shown when the response lands.")
    example("With a title and an icon", with_title, uses=[invoice_sent],
            note="A title for the headline; icon= replaces the tone's "
                 "default glyph.")
    example("Where it appears", positions, uses=[show_at],
            note="Six anchors around the viewport; duration_ms= sets how "
                 "long it stays.")
    example("After a form", after_a_form, uses=[Invite, send_invite],
            note="The same handler answers with a warning or a success, "
                 "depending on what it received.")
    example("Until the user closes it", sticky, uses=[maintenance],
            note="duration_ms=0 keeps the toast open until its × is clicked.")
