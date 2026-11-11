"""``/signature-pad`` — sign with a finger or a mouse, get a PNG back."""

from datetime import datetime

from bretzel import refreshable, ui
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A signature drawn with a finger or a mouse, posted with the form "
           "as a PNG — and inked in the text colour, dark mode included.")


def delivery_receipt() -> None:
    with ui.card(padding="md", classes="w-full max-w-md"), ui.vstack(gap="md"):
        with ui.hstack(justify="between"):
            with ui.vstack(gap="none"):
                ui.text("Order #48213 · 3 parcels", weight="medium")
                ui.text("Atlas Freight, 12 Harbour Road", color="muted",
                        size="sm")
            ui.badge("Out for delivery", color="info", variant="soft", size="sm")
        ui.signature_pad(placeholder="Recipient signs here", clear_label="Redo")


def sizes() -> None:
    with ui.vstack(gap="lg", classes="w-full max-w-md"):
        with ui.form_field(label="Initials", hint="On every page, bottom right."):
            ui.signature_pad(size="sm", placeholder="Initial here",
                             name="initials")
        with ui.form_field(label="Witness"):
            ui.signature_pad(disabled=True, placeholder="Locked until the "
                             "tenant has signed", name="witness")
        with ui.form_field(label="Full signature", hint="As it appears on your ID."):
            ui.signature_pad(size="lg", color="secondary", name="full")


class Lease(PageState):
    signature: str = field(default="")
    signed_at: str = field(default="")


def sign_lease(lease: Lease) -> None:
    if not lease.signature:
        ui.notification("Please sign before submitting.", color="warning")
        return
    lease.signed_at = datetime.now().strftime("%B %d, %Y at %H:%M")


@refreshable
def lease_status() -> None:
    lease = Lease()
    if lease.signed_at:
        with ui.hstack(gap="md"):
            ui.image(src=lease.signature, alt="Tenant signature",
                     classes="h-12 w-auto")
            ui.text(f"Signed on {lease.signed_at}", color="success", size="sm")


def sign_and_submit() -> None:
    with ui.card(padding="md", classes="w-full max-w-md"), \
            ui.form(on_submit=sign_lease), ui.vstack(gap="md"):
        with ui.vstack(gap="none"):
            ui.heading("Residential lease — Flat 4B", level=3, size="md")
            ui.text("By signing, you agree to the terms from October 1.",
                    color="muted", size="sm")
        ui.signature_pad(value=Lease().signature)
        with ui.hstack(justify="end"):
            ui.button("Sign the lease", type="submit", icon_left="pen-line")
        lease_status()


def page() -> None:
    page_header("signature_pad", "Signature pad", SUMMARY)
    example("A delivery receipt", delivery_receipt,
            note="A placeholder until the first stroke, and a clear button "
                 "with your own label.")
    example("Sizes and states", sizes,
            note="Three heights, a colour for the frame, and a disabled pad "
                 "waiting its turn.")
    example("Sign and submit", sign_and_submit,
            uses=[Lease, sign_lease, lease_status],
            note="Bound to a server state, the signature is posted with the "
                 "form as a PNG data URL — ready for a PDF or a record.")
