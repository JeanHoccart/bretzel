"""``Stepper`` (+ ``Step``, ``StepPanel``) test bench.

Ten visual cards : full gabarit. ``Stepper.BINDABLE_PROPS = ("value",)``
— the current index is bindable ; orientation / clickable / size / color
stay design-time. ``Stepper`` event : ``change``. Imperative API :
``.set(i)`` / ``.next()`` / ``.prev()``.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/stepper"


SIZES        = ["xs", "sm", "md", "lg", "xl"]
COLORS       = ["primary", "secondary", "success", "warning",
                "error", "info", "muted"]
ORIENTATIONS = ["horizontal", "vertical"]


class StepperPlayground(PageState):
    value:       int  = field(default=1)
    orientation: str  = field(default="horizontal")
    clickable:   bool = field(default=False)
    size:        str  = field(default="md")
    color:       str  = field(default="primary")
    name:        str  = field(default="")
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifiers.
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")
    # Event-handler shape.
    on_change_mode: str = field(default="none")


class StepperEvents(PageState):
    log: list = field(default_factory=list)


class StepperClient(ClientState, persist="memory"):
    step: int = field(default=0)


class StepperClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


# Drives the server-events demo. ``value=step_state.step`` → autoname
# derives ``name="step"`` from the binding's field_name → the handler
# ``log_change(step=...)`` receives it. No manual ``name=`` anywhere.
class StepperServerEvents(ClientState, persist="memory"):
    step: int = field(default=0)


def log(name: str) -> None:
    state = StepperEvents()
    state.log = [*state.log, name]


def log_change(step: str = "") -> None:
    log(f"change(step={step!r})")


def clear_log() -> None:
    state = StepperEvents()
    state.log = []


def server_changed(state: StepperPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    pass


def playground_change_handler(step: str = "") -> None:
    log(f"playground-server-change(step={step!r})")


_CLIENT_CHANGE_EXPR = "$el.classList.toggle('ring-4')"


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: StepperPlayground) -> dict:
    kwargs: dict = {
        "value": state.value,
        "orientation": state.orientation,
        "clickable": state.clickable,
        "size": state.size,
        "color": state.color,
    }
    if state.name:
        kwargs["name"] = state.name
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
    if state.on_change_mode == "server":
        kwargs["on_change"] = playground_change_handler
    elif state.on_change_mode == "client":
        kwargs["on_change"] = _CLIENT_CHANGE_EXPR
    elif state.on_change_mode == "both":
        kwargs["on_change"] = [playground_change_handler,
                               _CLIENT_CHANGE_EXPR]
    return kwargs


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[StepperPlayground])
def server_panel() -> None:
    state = StepperPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("value (current index, 0-based)"):
            ui.select(value=state.value,
                      options=[(0, "0 — Account"), (1, "1 — Address"),
                               (2, "2 — Payment"), (3, "3 — done screen")],
                      on_change=server_changed)
        with control("orientation"):
            ui.select(value=state.orientation,
                      options=[(o, o) for o in ORIENTATIONS],
                      on_change=server_changed)
        with control("clickable"):
            ui.switch(checked=state.clickable, on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("name (overrides autoname)"):
            ui.input(value=state.name, placeholder="step",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="!gap-10",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-stepper",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Checkout progress",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="max-width: 520px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=stepper",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Where you are",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)
        with control("on_change mode"):
            ui.select(value=state.on_change_mode,
                      options=[("none", "None (no handler)"),
                               ("server", "Server callable"),
                               ("client", "Client string"),
                               ("both", "Both (list)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    with ui.stepper(**kwargs):
        ui.step("Account", description="Email and password", icon="user")
        ui.step("Address", description="Where we ship")
        ui.step("Payment", description="Card details")
        with ui.step_panel():
            ui.text("Panel 0 — account fields.")
        with ui.step_panel():
            ui.text("Panel 1 — address fields.")
        with ui.step_panel():
            ui.text("Panel 2 — payment fields.")
        with ui.step_panel():
            ui.text("Panel 3 — the extra panel : the done screen, "
                    "reached by one more .next().")

    ui.divider()

    preview = ui.stepper(**kwargs)
    with preview:
        ui.step("One")
        ui.step("Two")
        with ui.step_panel():
            ui.text("1")
        with ui.step_panel():
            ui.text("2")
    emitted_html_block(
        "Emitted HTML (Stepper + Step + StepPanel)",
        serialize_html(preview),
    )


@refreshable(deps=[StepperEvents])
def events_panel() -> None:
    state = StepperEvents()

    ui.text(
        "Stepper fires a single ``change`` event when the current index "
        "moves — the new index is the kwarg. It fires for a pastille "
        "click AND for an imperative ``.next()`` / ``.prev()``, because "
        "both write the same value and the hidden input re-dispatches "
        "``change`` on every move.",
        color="muted", size="sm",
    )

    # ``value=step_state.step`` (binding) → AUTONAME_FROM="value" derives
    # ``name="step"`` from the binding's field_name → the hidden input
    # carries it → the dispatcher's payload matches the handler's
    # ``step=`` kwarg. NO manual ``name=``.
    step_state = StepperServerEvents()
    with ui.vstack():
        with ui.stepper(value=step_state.step, clickable=True,
                        on_change=log_change) as wiz:
            ui.step("Cart")
            ui.step("Shipping")
            ui.step("Payment")

        with ui.hstack(gap="sm"):
            ui.button("Previous", variant="outline", on_click=wiz.prev())
            ui.button("Next", on_click=wiz.next())

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)", color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)

    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}",
                        color="muted", size="sm", classes="font-mono")
    else:
        ui.text("(no events yet — click a pastille or Next above)",
                color="muted", size="sm")

    ui.divider()

    representative = ui.stepper(value=step_state.step, on_change=log_change)
    with representative:
        ui.step("A")
        ui.step("B")
    emitted_html_block(
        "Emitted HTML (Stepper with on_change handler)",
        serialize_html(representative),
    )


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Stepper", level=1)
        ui.text(
            "Ordered progress. ``Stepper`` owns the current index "
            "(literal, server-resolved, or bound to ClientState) ; "
            "``Step`` declares each stage ; ``StepPanel`` holds the "
            "matching content, paired by declaration order. Each "
            "step's status is DERIVED from the index — done, "
            "current, upcoming — so there is nothing to declare.",
            color="muted",
        )

        # ── Card 1 — Reference ──────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Reference", level=2)
            ui.text("Visual scan of every prop.",
                    color="muted", size="sm")

            ui.heading("Basic", level=3)
            with ui.stepper(value=1):
                ui.step("Account")
                ui.step("Address")
                ui.step("Payment")

            ui.heading("Orientations", level=3)
            for o in ORIENTATIONS:
                ui.text(f"orientation={o}", color="muted", size="xs")
                with ui.stepper(value=1, orientation=o):
                    ui.step("Account", description="Sign in")
                    ui.step("Address", description="Shipping")
                    ui.step("Payment", description="Card")

            ui.heading("Sizes", level=3)
            for s in SIZES:
                ui.text(f"size={s}", color="muted", size="xs")
                with ui.stepper(value=1, size=s):
                    ui.step("One", description="First")
                    ui.step("Two", description="Second")
                    ui.step("Three", description="Third")

            ui.heading("Colors", level=3)
            for c in COLORS:
                with ui.stepper(value=1, color=c):
                    ui.step(f"{c.title()} one")
                    ui.step(f"{c.title()} two")
                    ui.step(f"{c.title()} three")

            ui.heading("clickable", level=3)
            ui.text(
                "``clickable=False`` (default) renders plain "
                "``<span>`` pastilles — nothing in the tab "
                "order, nothing announced as actionable. "
                "``clickable=True`` turns them into buttons.",
                color="muted", size="xs",
            )
            with ui.stepper(value=1, clickable=True):
                ui.step("Click me")
                ui.step("Or me")
                ui.step("Or me too")

            ui.heading("status + disabled", level=3)
            with ui.stepper(value=2, clickable=True):
                ui.step("Uploaded")
                ui.step("Validation", status="error")
                ui.step("Publish")
                ui.step("Archive", disabled=True)

        # ── Card 2 — Slots ──────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Slots", level=2)
            ui.text(
                "``Step`` declares ``label`` (positional) + "
                "optional ``description`` and ``icon``. "
                "``StepPanel`` is a container — children inside "
                "the ``with`` block are the panel content.",
                color="muted", size="sm",
            )

            ui.heading("Step with icon", level=3)
            ui.text(
                "An explicit icon replaces BOTH the number and "
                "the check — in all four statuses.",
                color="muted", size="xs",
            )
            with ui.stepper(value=1):
                ui.step("Profile", icon="user")
                ui.step("Security", icon="shield")
                ui.step("Billing", icon="credit-card")

            ui.heading("Step with description", level=3)
            with ui.stepper(value=1, orientation="vertical"):
                ui.step("Create account",
                        description="Takes about a minute")
                ui.step("Verify email",
                        description="We just sent you a link")
                ui.step("Invite your team",
                        description="Optional, you can skip")

            ui.heading("StepPanel = rich layout", level=3)
            with ui.stepper(value=0):
                ui.step("Details")
                ui.step("Review")
                with ui.step_panel(), ui.vstack():
                    ui.heading("Project Aurora", level=3)
                    ui.text("Multi-line body, with a field "
                            "below.", color="muted")
                    with ui.form_field(label="Display name"):
                        ui.input(placeholder="Ada")
                with ui.step_panel():
                    ui.text("Review panel.", color="muted")

            ui.text(
                "``value`` accepts ClientBinding — see the "
                "Client playground card below.",
                color="muted", size="sm",
            )

        # ── Card 3 — Edge cases ─────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Edge cases", level=2)
            ui.text("Edge inputs and exotic combinations.",
                    color="muted", size="sm")

            ui.heading("Single step", level=3)
            with ui.stepper(value=0):
                ui.step("The only one")

            ui.heading("Many steps", level=3)
            with ui.stepper(value=4):
                for i in range(1, 11):
                    ui.step(f"S{i}")

            ui.heading("Very long labels", level=3)
            with ui.stepper(value=1):
                ui.step("A long step label that has to truncate",
                        description="And a description that is "
                                    "also far too long to fit")
                ui.step("Another long-ish label")
                ui.step("Short")

            ui.heading("value beyond the last step", level=3)
            ui.text(
                "Every step reads as done — that is the "
                "« completed » state, and it is exactly "
                "what the extra panel below is for.",
                color="muted", size="xs",
            )
            with ui.stepper(value=3):
                ui.step("One")
                ui.step("Two")
                ui.step("Three")
                with ui.step_panel():
                    ui.text("Panel 0")
                with ui.step_panel():
                    ui.text("Panel 1")
                with ui.step_panel():
                    ui.text("Panel 2")
                with ui.step_panel():
                    ui.empty_state("All done", icon="party-popper",
                                   description="The 4th panel for "
                                               "3 steps.")

            ui.heading("No panels at all", level=3)
            ui.text("A pure progress indicator — legitimate, and "
                    "the smallest useful shape.",
                    color="muted", size="xs")
            with ui.stepper(value=1):
                ui.step("Ordered")
                ui.step("Shipped")
                ui.step("Delivered")

            ui.heading("HTML-special label (XSS escape)", level=3)
            with ui.stepper(value=0):
                ui.step("<script>alert(1)</script>")
                ui.step("Safe")

        # ── Card 4 — Composability ──────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Composability", level=2)
            ui.text("Stepper in common contexts.",
                    color="muted", size="sm")

            ui.heading("Checkout (inside Card)", level=3)
            with ui.card(), ui.vstack():
                with ui.stepper(value=1, clickable=True) as checkout:
                    ui.step("Cart", icon="shopping-cart")
                    ui.step("Shipping", icon="truck")
                    ui.step("Payment", icon="credit-card")
                    with ui.step_panel():
                        ui.text("Your cart is ready.", color="muted")
                    with ui.step_panel(), ui.form_field(label="Address"):
                        ui.input(placeholder="221B Baker Street")
                    with ui.step_panel():
                        ui.text("Payment details.", color="muted")
                with ui.hstack(gap="sm"):
                    ui.button("Back", variant="outline",
                              on_click=checkout.prev())
                    ui.button("Continue", on_click=checkout.next())

            ui.heading("Vertical, in a narrow column", level=3)
            ui.text(
                "The constrained-context check : a vertical "
                "stepper in one cell of a grid must not overflow "
                "its column.",
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                with ui.stepper(value=1, orientation="vertical",
                                size="sm"):
                    ui.step("Draft", description="Written")
                    ui.step("Review", description="In progress")
                    ui.step("Published", description="Not yet")
                ui.text("Neighbouring cell.", color="muted")
                ui.text("Another neighbour.", color="muted")

            ui.heading("Inside ui.dialog", level=3)
            with ui.dialog(title="Onboarding", width="lg") as dlg, ui.vstack():
                with ui.stepper(value=0) as onboarding:
                    ui.step("Welcome")
                    ui.step("Preferences")
                    with ui.step_panel():
                        ui.text("Glad you're here.", color="muted")
                    with ui.step_panel():
                        ui.switch(label="Email digest", checked=True)
                ui.button("Next", on_click=onboarding.next())
            ui.button("Open onboarding dialog", on_click=dlg.open())

        # ── Card 5 — A11y ───────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("A11y", level=2)
            ui.text(
                "The rail is an ``<ol>`` of ``<li>`` — the "
                "ordering is native, not simulated with ARIA. "
                "The current step carries ``aria-current=\"step\"`` "
                "(SSR-rendered, then reactive) ; the connectors "
                "are ``aria-hidden`` decoration. With "
                "``clickable=False`` there is no focusable "
                "element at all, which is the point : a read-"
                "only indicator should not be in the tab order. "
                "With ``clickable=True`` each pastille is a real "
                "``<button>``, and a ``disabled`` step is "
                "genuinely disabled.",
                color="muted", size="sm",
            )
            with ui.stepper(value=1, clickable=True,
                            aria_label="Demo progress"):
                ui.step("Alpha", description="Done")
                ui.step("Beta", description="You are here")
                ui.step("Gamma", description="Later")
                ui.step("Delta", disabled=True)

        # ── Card 6 — Server playground ──────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server playground", level=2)
            ui.text(
                "Every Stepper prop AND every escape hatch is "
                "wired to a control ; the preview AND the "
                "emitted HTML both refresh on every change.",
                color="muted", size="sm",
            )
            server_panel()

        # ── Card 7 — Server events ──────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server events", level=2)
            events_panel()

        # ── Card 8 — Client playground ──────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Client playground", level=2)
            ui.text(
                "Mirror of Stepper's ``BINDABLE_PROPS = "
                "('value',)`` contract. The current index is "
                "bound to a ClientState ; an external control "
                "drives the stepper with no round-trip.",
                color="muted", size="sm",
            )
            client = StepperClient()
            with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                with control("value (bound)"):
                    ui.select(value=client.step,
                              options=[(0, "0"), (1, "1"),
                                       (2, "2"), (3, "3 — done")])

            ui.divider()

            with ui.stepper(value=client.step, color="primary"):
                ui.step("Pick", description="Choose a plan")
                ui.step("Pay", description="Enter a card")
                ui.step("Ship", description="Confirm address")
                with ui.step_panel():
                    ui.text("Bound panel 0")
                with ui.step_panel():
                    ui.text("Bound panel 1")
                with ui.step_panel():
                    ui.text("Bound panel 2")
                with ui.step_panel():
                    ui.text("Bound panel 3 — done")

            ui.divider()

            preview = ui.stepper(value=client.step)
            with preview:
                ui.step("A")
                ui.step("B")
                with ui.step_panel():
                    ui.text("A")
                with ui.step_panel():
                    ui.text("B")
            emitted_html_block(
                "Emitted HTML — every directive reads the bound "
                "store cell directly ; the status of each step "
                "and the visible panel both follow it without a "
                "round-trip.",
                serialize_html(preview),
            )

        # ── Card 9 — External controls — the 3 modes ────────────
        with ui.card(), ui.vstack():
            ui.heading("External controls — the 3 modes", level=2)
            ui.text(
                "The same wizard (Back / Next buttons outside "
                "the stepper) played three ways. ``.next()`` and "
                "``.prev()`` ALWAYS dispatch a DOM command, "
                "binding or not : where the index lands depends "
                "on the live value and on the upper bound, "
                "neither of which the server knows at render "
                "time. ``.set(i)`` writes through the binding "
                "when there is one.",
                color="muted", size="sm",
            )

            # ── Mode 1 — Imperative only ────────────────────
            ui.heading("Mode 1 — Imperative only (default)",
                       level=3)
            ui.text(
                "No ClientState. The stepper owns its index in "
                "client scope. **Use this by default for a "
                "wizard whose position nothing else needs to "
                "read.**",
                color="muted", size="sm",
            )
            with ui.stepper() as m1:
                ui.step("First")
                ui.step("Second")
                ui.step("Third")
                with ui.step_panel():
                    ui.text("Panel one.")
                with ui.step_panel():
                    ui.text("Panel two.")
                with ui.step_panel():
                    ui.text("Panel three.")
            with ui.hstack(gap="sm"):
                ui.button("Back", variant="outline",
                          on_click=m1.prev())
                ui.button("Next", on_click=m1.next())
                ui.button("Restart", variant="ghost",
                          on_click=m1.set(0))

            ui.divider()

            # ── Mode 2 — ClientBinding only ─────────────────
            ui.heading("Mode 2 — ClientBinding only", level=3)
            ui.text(
                "Use this when **another component needs to "
                "read the position** — a heading that names the "
                "current step, a button disabled on the last "
                "one, server awareness on the next render.",
                color="muted", size="sm",
            )
            bound = StepperClient(key="binding_only")
            with ui.stepper(value=bound.step, clickable=True):
                ui.step("First")
                ui.step("Second")
                ui.step("Third")
            ui.text(
                ClientExpression(
                    "'Current index : ' + "
                    "($bz.state.StepperClient.binding_only.step ?? 0)"
                ),
                color="muted", size="sm",
            )

            ui.divider()

            # ── Mode 3 — Both (write-through) ───────────────
            ui.heading("Mode 3 — Both (write-through)", level=3)
            ui.text(
                "A binding AND the imperative methods. The "
                "buttons move the SAME cell the mirror below "
                "reads — one source of truth, two ways to "
                "write it.",
                color="muted", size="sm",
            )
            both = StepperClient(key="both")
            with ui.stepper(value=both.step, clickable=True) as m3:
                ui.step("Draft")
                ui.step("Review")
                ui.step("Published")
            with ui.hstack(gap="sm", align="center"):
                ui.button("Back", variant="outline",
                          on_click=m3.prev())
                ui.button("Next", on_click=m3.next())
                ui.button("Jump to review", variant="ghost",
                          on_click=m3.set(1))
                ui.text(
                    ClientExpression(
                        "'bound = ' + "
                        "($bz.state.StepperClient.both.step ?? 0)"
                    ),
                    color="muted", size="sm",
                    classes="font-mono",
                )

            ui.divider()

            imperative_preview = ui.stepper(value=both.step)
            with imperative_preview:
                ui.step("A")
                ui.step("B")
            emitted_html_block(
                "Emitted HTML — the root carries "
                "``bz-on:bz-set`` / ``bz-on:bz-next`` / "
                "``bz-on:bz-prev``, the three receivers the "
                "imperative methods dispatch to.",
                serialize_html(imperative_preview),
            )

        # ── Card 10 — Client events ─────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Client events", level=2)
            ui.text("change event wired to a client expression "
                    "that pushes the new index onto a "
                    "ClientState list. Zero network.",
                    color="muted", size="sm")
            cevents = StepperClientEvents()
            _new_value = ClientExpression("$event.target.value")
            with ui.stepper(value=0, clickable=True,
                            on_change=cevents.log.push(_new_value)):
                ui.step("A")
                ui.step("B")
                ui.step("C")

            ui.divider()

            with ui.hstack(justify="between", align="center"):
                ui.text("Live log (client-reactive)",
                        color="muted", size="sm")
                ui.button("Clear", variant="ghost", size="xs",
                          on_click=cevents.log.clear())

            ui.divider()

            log_text = ClientExpression(
                '($bz.state.StepperClientEvents.default.log'
                ' || []).join("\\n") || "(no events yet)"'
            )
            ui.text(log_text,
                    color="muted", size="sm",
                    classes="font-mono whitespace-pre")

            ui.divider()

            preview = ui.stepper(
                value=0,
                on_change=cevents.log.push(_new_value),
            )
            with preview:
                ui.step("A")
                ui.step("B")
            emitted_html_block(
                "Emitted HTML — the ``bz-on:change`` handler is "
                "relocated onto the hidden input ; the pastille "
                "click only moves the index, and the input's "
                "``bz-effect`` re-fires ``change`` on every "
                "move.",
                serialize_html(preview),
            )
