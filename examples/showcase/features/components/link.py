"""``/link`` — an anchor that looks the part."""

from bretzel import ui
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Three ways to look like a link, every semantic colour, and the "
           "details handled: new tabs, downloads, disabled.")


def variants() -> None:
    with ui.hstack(gap="lg", wrap=True, justify="center"):
        ui.link("Pricing", href="#", variant="hover")
        ui.link("Changelog", href="#", variant="underline")
        ui.link("System status", href="#", variant="text")


def colors() -> None:
    with ui.hstack(gap="lg", wrap=True, justify="center"):
        ui.link("View invoice", href="#", color="primary")
        ui.link("Switch workspace", href="#", color="secondary")
        ui.link("All checks passed", href="#", color="success")
        ui.link("2 warnings", href="#", color="warning")
        ui.link("Payment failed", href="#", color="error")
        ui.link("What's new", href="#", color="info")


def in_a_sentence() -> None:
    with ui.hstack(gap="xs", wrap=True, justify="center"):
        ui.text("By creating an account you agree to our", color="muted")
        ui.link("Terms of Service", href="#", variant="underline")
        ui.text("and", color="muted")
        ui.link("Privacy Policy", href="#", variant="underline")


def external_and_disabled() -> None:
    with ui.vstack(gap="sm", align="start"):
        ui.link("Open the API reference", href="https://docs.bretzel-py.dev",
                external=True)
        with ui.link(href="#", color="primary"), ui.hstack(gap="xs"):
            ui.icon("book-open")
            ui.text("Read the getting-started guide")
        ui.link("Resend the code (available in 30 s)", href="#",
                disabled=True)


FOOTER = {
    "Product": ["Features", "Pricing", "Integrations", "Changelog"],
    "Company": ["About", "Customers", "Careers", "Contact"],
    "Resources": ["Documentation", "API status", "Community", "Security"],
}


def site_footer() -> None:
    with ui.grid(min_col="12rem", gap="lg"):
        for section, pages in FOOTER.items():
            with ui.vstack(gap="sm", align="start"):
                ui.text(section, weight="semibold", size="sm")
                for label in pages:
                    ui.link(label, href="#", variant="text", color="muted")


def page() -> None:
    page_header("link", "Link", SUMMARY)
    example("Variants", variants,
            note="hover underlines on hover, underline always does, text "
                 "never does — for navigation where the context already "
                 "says it is clickable.")
    example("Colours", colors)
    example("Inside a sentence", in_a_sentence)
    example("New tab, disabled", external_and_disabled,
            note="external opens a new tab with rel=noopener; disabled drops "
                 "the href so nothing can follow it.")
    example("A site footer", site_footer, full=True)
