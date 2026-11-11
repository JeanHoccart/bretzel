"""``/stepper`` — a task cut into ordered steps."""

from bretzel import ui
from bretzel.state import ClientState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Ordered steps with their panels — horizontal or vertical, a "
           "failed step in red, and a current step any button can move.")


def checkout() -> None:
    with ui.vstack(gap="lg", classes="w-full"):
        with ui.stepper(value=0, name="checkout") as wizard:
            ui.step("Cart", description="3 items", icon="shopping-cart")
            ui.step("Shipping", description="Where it goes", icon="truck")
            ui.step("Payment", description="Card or transfer", icon="credit-card")
            with ui.step_panel():
                ui.text("Walnut desk organiser, linen notebooks and a brass "
                        "pen — €148.00.", color="muted")
            with ui.step_panel(), ui.form_field(label="Delivery address",
                                                 classes="max-w-md"):
                ui.input(value="12 Harbour Street, Bristol", name="address")
            with ui.step_panel():
                ui.text("You will be charged €148.00 on the card ending 4242.",
                        color="muted")
            with ui.step_panel(), ui.hstack(gap="sm"):
                ui.icon("circle-check", color="success", size="lg")
                ui.text("Order placed. A receipt is on its way.", weight="medium")
        with ui.hstack(gap="sm", justify="end"):
            ui.button("Back", variant="ghost", icon_left="arrow-left",
                      on_click=wizard.prev())
            ui.button("Continue", icon_right="arrow-right", on_click=wizard.next())


def onboarding() -> None:
    with ui.stepper(value=2, orientation="vertical", name="onboarding"):
        ui.step("Create your workspace", description="Northwind · 12 seats")
        ui.step("Invite your team", description="8 of 12 invitations accepted")
        ui.step("Connect your bank", description="Read-only access, revocable")
        ui.step("Send your first invoice", description="Pick a template")


def pipeline() -> None:
    with ui.stepper(value=2, clickable=False, name="pipeline", classes="w-full"):
        ui.step("Build", description="1 min 12 s", icon="hammer")
        ui.step("Unit tests", description="1 482 passed", icon="flask-conical")
        ui.step("Deploy to staging", description="Health check failed",
                icon="server", status="error")
        ui.step("Deploy to production", icon="rocket")


def sizes_and_colors() -> None:
    with ui.vstack(gap="lg", classes="w-full"):
        for size, color in (("sm", "primary"), ("md", "success"), ("lg", "secondary")):
            with ui.stepper(value=1, size=size, color=color, name=f"style-{size}"):
                ui.step("Details")
                ui.step("Review")
                ui.step("Publish")


class DomainSetup(ClientState):
    step: int = field(default=0)


def domain_setup() -> None:
    step = DomainSetup().step
    with ui.vstack(gap="md", classes="w-full"):
        with ui.stepper(value=step, clickable=False):
            ui.step("Domain", description="acme-billing.com")
            ui.step("DNS records", description="3 records to add")
            ui.step("Verification", description="Usually under a minute")
            ui.step("Live", description="Emails sent from your domain")
        with ui.hstack(gap="sm", justify="end"):
            ui.button("Start over", variant="ghost", on_click=step.set(0))
            ui.button("Complete this step", icon_left="check",
                      disabled=step == 3, on_click=step.increment())


def page() -> None:
    page_header("stepper", "Stepper", SUMMARY)
    example("A checkout wizard", checkout, full=True,
            note="Panels pair with steps in order; one extra panel is the "
                 "finished screen. The buttons call wizard.prev() and "
                 "wizard.next(), and a click on a done step goes back to it.")
    example("Vertical onboarding", onboarding,
            note="Steps before the current one are done, the ones after are "
                 "still to come: nothing to declare per step.")
    example("A failed step", pipeline, full=True,
            note="status=\"error\" is the one status you set by hand.")
    example("Sizes and colours", sizes_and_colors, full=True)
    example("Progress driven by a state", domain_setup, full=True,
            uses=[DomainSetup],
            note="value= is bound to a ClientState: each click advances it in "
                 "the browser and the stepper follows. A server state works "
                 "the same, through a zone that re-renders.")
