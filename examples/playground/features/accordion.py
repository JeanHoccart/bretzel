"""``Accordion`` test bench — full 10-card gabarit.

Five props : ``value`` / ``type`` / ``collapsible`` / ``size`` /
``color``. One event : ``change`` (fires when the expansion state
changes). ``BINDABLE_PROPS = ("value",)`` — the expansion state is
bindable so external state can drive the accordion ; type /
collapsible / size / color stay design-time. The Client playground
card gives ``value`` its own dedicated ClientBinding demo, separate
from the External controls card's imperative-method demo.
"""

from functools import partial

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/accordion"


TYPES = ["single", "multiple"]
SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]


# ── Imperative per-row demo state ──────────────────────────────────────
# Tracks which FAQ items have been viewed — illustrates the per-row
# imperative pattern where each row owns its own accordion expansion
# without declaring a ClientState. A page-level log records which
# items got opened (server-side, for the refreshable log below).


class FAQViewLog(PageState):
    """Server-side record of which FAQ items the user opened."""

    log: list = field(default_factory=list)


def log_view(item_id: str) -> None:
    state = FAQViewLog()
    state.log = [*state.log, item_id]


def reset_view_log() -> None:
    FAQViewLog().log = []


# ── Playground state ──────────────────────────────────────────────────


class AccordionPlayground(PageState):
    type:        str  = field(default="single")
    collapsible: bool = field(default=True)
    size:        str  = field(default="md")
    color:       str  = field(default="primary")
    initial:     str  = field(default="general")
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifiers.
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")


class AccordionEvents(PageState):
    log: list = field(default_factory=list)


# Drives the server-events demo Accordion. ``value=ses.value`` →
# autoname derives ``name="value"`` from the binding's field_name →
# the handler ``log_change(value=...)`` receives the new id via
# FormData. No manual ``name="value"`` on the Accordion anywhere —
# that's the CLAUDE.md rule. Same idiom Tabs / Pagination / Select
# use in their events_panel.
class AccordionServerEvents(ClientState, persist="memory"):
    value: str = field(default="")


class AccordionClient(ClientState, persist="memory"):
    """Mirror of Accordion's BINDABLE_PROPS = ('value',)."""

    expanded: str = field(default="general")


class AccordionMultiClient(ClientState, persist="memory"):
    expanded: list = field(default_factory=lambda: ["a"])


class AccordionClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


# ── Handlers ──────────────────────────────────────────────────────────


def log(name: str) -> None:
    state = AccordionEvents()
    state.log = [*state.log, name]


def log_change(value: str = "") -> None:
    log(f"change(value={value!r})")


def clear_log() -> None:
    AccordionEvents().log = []


def server_changed(state: AccordionPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    pass


# ── Helpers ───────────────────────────────────────────────────────────


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: AccordionPlayground) -> dict:
    is_multi = state.type == "multiple"
    kwargs: dict = {
        "multiple": is_multi,
        "collapsible": state.collapsible,
        "size": state.size,
        "color": state.color,
        "value": (
            [v.strip() for v in state.initial.split(",") if v.strip()]
            if is_multi
            else state.initial
        ),
    }
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
    return kwargs


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


def three_items_into(parent) -> None:
    """Standard 3-item filler used by most reference demos."""
    with parent:
        with ui.accordion_item("general", label="General"):
            ui.text("Default behaviour, naming, locale — your core "
                    "configuration.", color="muted")
        with ui.accordion_item("security", label="Security",
                               icon="shield"):
            ui.text("Password rules, 2FA, session timeouts.",
                    color="muted")
        with ui.accordion_item("billing", label="Billing",
                               icon="credit-card"):
            ui.text("Subscription tier, payment method, invoices.",
                    color="muted")


# ──────────────────────────────────────────────────────────────────────
# Refreshable panels
# ──────────────────────────────────────────────────────────────────────


@refreshable(deps=[AccordionPlayground])
def server_panel() -> None:
    state = AccordionPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("type"):
            ui.select(value=state.type,
                      options=[(t, t) for t in TYPES],
                      on_change=server_changed)
        with control("collapsible (single only)"):
            ui.switch(checked=state.collapsible,
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control(
            "initial open (single: 'a' / multiple: 'a,b')"
        ):
            ui.input(value=state.initial,
                     placeholder="general",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!shadow-lg",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-acc",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Settings accordion",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="--bz-radius: 12px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=acc",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Configure the app",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    with ui.vstack(gap="sm"):
        ui.text("Live preview — items defined statically below.",
                color="muted", size="xs")
        three_items_into(ui.accordion(**kwargs))

    ui.divider()

    preview = ui.accordion(**kwargs)
    three_items_into(preview)
    emitted_html_block(
        "Emitted HTML — the controls grid drives this snapshot live",
        serialize_html(preview),
    )


@refreshable(deps=[AccordionEvents])
def events_panel() -> None:
    state = AccordionEvents()

    ui.text(
        "Accordion exposes one event : ``on_change``. The handler "
        "receives the new expansion ``value=`` via FormData — wired "
        "automatically by binding ``value=ses.value`` (AUTONAME "
        "derives ``name=\"value\"`` on the hidden input).",
        color="muted", size="sm",
    )

    ses = AccordionServerEvents()
    with ui.flex(justify="center"):
        with ui.accordion(value=ses.value, on_change=log_change):
            with ui.accordion_item("a", label="Toggle me"):
                ui.text("Each open/close fires change.", color="muted")
            with ui.accordion_item("b", label="And me"):
                ui.text("Multi-toggle = multi-events.", color="muted")

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)",
                color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)

    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}",
                        color="muted", size="sm",
                        classes="font-mono")
    else:
        ui.text("(no events yet — open or close an item above)",
                color="muted", size="sm")

    ui.divider()

    representative = ui.accordion(value=ses.value,
                                   on_change=log_change)
    with representative:
        with ui.accordion_item("a", label="Sample"):
            ui.text("Body")
    emitted_html_block(
        "Emitted HTML (Accordion with value-binding + on_change)",
        serialize_html(representative),
    )


@refreshable(deps=[FAQViewLog])
def faq_imperative() -> None:
    """Per-row 'view-tracker' pattern using the imperative API.

    Each FAQ section has its own accordion instance with zero
    ClientState — only a server-side log of which items got viewed
    drives this section's refresh. Each ``Open from outside`` button
    calls ``acc.expand(id)`` ; the Accordion handles the rest.
    """

    state = FAQViewLog()
    sections = [
        {"id": "shipping", "title": "Shipping",
         "body": "Most orders ship within 24 hours."},
        {"id": "returns", "title": "Returns",
         "body": "30 days, no questions asked."},
        {"id": "billing", "title": "Billing",
         "body": "We accept all major cards + invoicing for teams."},
    ]

    ui.text(
        "Each card owns its own accordion. The 'View this section' "
        "button calls ``acc.expand(<id>)``. The log below records "
        "every view server-side and drives this section's refresh.",
        color="muted", size="sm",
    )

    with ui.vstack(gap="md"):
        for section in ui.each(sections, key="id"):
            with ui.card():
                with ui.vstack(gap="sm"):
                    acc = ui.accordion()
                    with acc:
                        with ui.accordion_item(section["id"],
                                               label=section["title"]):
                            ui.text(section["body"], color="muted")
                    with ui.hstack(justify="end"):
                        ui.button(
                            "View this section",
                            variant="ghost",
                            size="sm",
                            on_click=[
                                partial(log_view, section["id"]),
                                acc.expand(section["id"]),
                            ],
                        )

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text(f"Views so far : {len(state.log)} "
                f"({', '.join(state.log[-5:]) if state.log else '—'})",
                color="muted", size="sm")
        ui.button("Reset", variant="ghost", size="xs",
                  on_click=reset_view_log, disabled=not state.log)


# ──────────────────────────────────────────────────────────────────────
# Page
# ──────────────────────────────────────────────────────────────────────


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Accordion", level=1)
            ui.text(
                "Stack of collapsible panels — one opinionated frame "
                "(bordered, with a divider between items). Two ``type`` "
                "modes (single / multiple), five sizes. The expansion "
                "state is the only bindable prop — drive it via "
                "``value=ClientBinding`` or via the imperative "
                "``acc.expand(v)`` / ``collapse(v)`` / ``toggle(v)`` "
                "/ ``expand_all()`` / ``collapse_all()`` API.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every size.",
                            color="muted", size="sm")

                    ui.heading("Sizes (xs → xl)", level=3)
                    with ui.vstack(gap="md"):
                        for s in ui.each(SIZES):
                            with ui.vstack(gap="xs"):
                                ui.text(s, color="muted", size="xs")
                                with ui.accordion(size=s, value="a"):
                                    with ui.accordion_item(
                                        "a", label=f"Size {s}",
                                    ):
                                        ui.text("Body at size " + s,
                                                color="muted")

                    ui.heading("Single vs multiple", level=3)
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("multiple=False (default)",
                                    color="muted", size="xs")
                            with ui.accordion(value="a"):
                                with ui.accordion_item(
                                    "a", label="First",
                                ):
                                    ui.text("Only one at a time",
                                            color="muted")
                                with ui.accordion_item(
                                    "b", label="Second",
                                ):
                                    ui.text("Open this → first closes",
                                            color="muted")
                                with ui.accordion_item(
                                    "c", label="Third",
                                ):
                                    ui.text("Same here", color="muted")
                        with ui.vstack(gap="xs"):
                            ui.text("multiple=True",
                                    color="muted", size="xs")
                            with ui.accordion(multiple=True,
                                              value=["a", "b"]):
                                with ui.accordion_item(
                                    "a", label="First",
                                ):
                                    ui.text("Independent", color="muted")
                                with ui.accordion_item(
                                    "b", label="Second",
                                ):
                                    ui.text("of the others",
                                            color="muted")
                                with ui.accordion_item(
                                    "c", label="Third",
                                ):
                                    ui.text("All can be open at once",
                                            color="muted")

                    ui.heading("Collapsible (single only)", level=3)
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("collapsible=True (default)",
                                    color="muted", size="xs")
                            with ui.accordion(value="a"):
                                with ui.accordion_item(
                                    "a", label="Can close",
                                ):
                                    ui.text("Click the open one to close.",
                                            color="muted")
                                with ui.accordion_item(
                                    "b", label="Or open this",
                                ):
                                    ui.text("And switch.", color="muted")
                        with ui.vstack(gap="xs"):
                            ui.text("collapsible=False",
                                    color="muted", size="xs")
                            with ui.accordion(value="a",
                                              collapsible=False):
                                with ui.accordion_item(
                                    "a", label="Always one open",
                                ):
                                    ui.text("Cannot close — click another.",
                                            color="muted")
                                with ui.accordion_item(
                                    "b", label="Click me",
                                ):
                                    ui.text("First closes when this opens.",
                                            color="muted")

                    ui.heading("With icons + disabled", level=3)
                    with ui.accordion(value="active"):
                        with ui.accordion_item(
                            "active", label="Active section",
                            icon="check-circle-2",
                        ):
                            ui.text("Body content.", color="muted")
                        with ui.accordion_item(
                            "warn", label="Warning section",
                            icon="alert-triangle",
                        ):
                            ui.text("Body content.", color="muted")
                        with ui.accordion_item(
                            "off", label="Disabled section",
                            icon="ban", disabled=True,
                        ):
                            ui.text("Won't open.", color="muted")

                    ui.heading("Colors", level=3)
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        for c in ui.each(COLORS):
                            with ui.vstack(gap="xs"):
                                ui.text(c, color="muted", size="xs")
                                with ui.accordion(color=c, value="a"):
                                    with ui.accordion_item(
                                        "a", label=f"{c.title()} selected",
                                    ):
                                        ui.text("Body content.",
                                                color="muted")

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs and exotic combinations.",
                            color="muted", size="sm")

                    ui.heading("Empty body", level=3)
                    with ui.accordion(value="a"):
                        with ui.accordion_item("a", label="Empty"):
                            pass

                    ui.heading("Very long label (90 chars)", level=3)
                    with ui.accordion():
                        with ui.accordion_item(
                            "long",
                            label=(
                                "A very long accordion item label that "
                                "should probably wrap or truncate on "
                                "narrow widths depending on theme"
                            ),
                        ):
                            ui.text("Body.", color="muted")

                    ui.heading("Emoji + multi-script", level=3)
                    with ui.accordion():
                        with ui.accordion_item(
                            "emoji",
                            label="Ship 🚀 — שלום — 中文",
                        ):
                            ui.text("Body.", color="muted")

                    ui.heading(
                        "HTML-special chars in label (XSS escape)",
                        level=3,
                    )
                    with ui.accordion():
                        with ui.accordion_item(
                            "xss",
                            label="<script>alert(1)</script>",
                        ):
                            ui.text("Framework escapes the label.",
                                    color="muted")

                    ui.heading("Single item only", level=3)
                    with ui.accordion(value="alone"):
                        with ui.accordion_item("alone",
                                               label="The only one"):
                            ui.text("Body.", color="muted")

                    ui.heading("Very long scrolling body", level=3)
                    with ui.accordion():
                        with ui.accordion_item(
                            "scroll", label="20 paragraphs",
                        ):
                            for i in range(1, 11):
                                ui.text(
                                    f"Paragraph {i} — Lorem ipsum "
                                    f"dolor sit amet.",
                                    color="muted",
                                )

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Common patterns that mix Accordion with "
                            "other components.",
                            color="muted", size="sm")

                    ui.heading("FAQ inside a Card", level=3)
                    with ui.card():
                        with ui.accordion():
                            with ui.accordion_item(
                                "q1",
                                label="How do refunds work ?",
                            ):
                                ui.text("Within 30 days, full refund.",
                                        color="muted")
                            with ui.accordion_item(
                                "q2", label="Can I downgrade ?",
                            ):
                                ui.text("Anytime, no penalty.",
                                        color="muted")

                    ui.heading("Form fields inside items", level=3)
                    with ui.accordion(multiple=True):
                        with ui.accordion_item(
                            "account", label="Account",
                        ):
                            with ui.vstack():
                                with ui.form_field(label="Display name"):
                                    ui.input(value="Jean")
                                with ui.form_field(label="Email"):
                                    ui.input(value="jean@example.com")
                        with ui.accordion_item(
                            "notifications", label="Notifications",
                        ):
                            with ui.vstack():
                                ui.switch(label="Email digest",
                                          checked=True)
                                ui.switch(label="Push")
                                ui.switch(label="SMS")

                    ui.heading(
                        "Per-row accordion (imperative pattern)",
                        level=3,
                    )
                    faq_imperative()

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Each header is a ``<button type=\"button\">`` "
                        "with ``aria-expanded`` reactive against the "
                        "expansion state and ``aria-controls`` pointing "
                        "at its body's ``id``. The body wears "
                        "``role=\"region\"`` + ``aria-labelledby`` "
                        "linking back to the header. Disabled items "
                        "emit ``disabled`` HTML attr and skip the "
                        "toggle click.",
                        color="muted", size="sm",
                    )
                    with ui.accordion(value="kbd"):
                        with ui.accordion_item(
                            "kbd", label="Keyboard test",
                        ):
                            ui.text(
                                "Tab to focus a header, Space / Enter "
                                "to toggle. Disabled items are "
                                "skipped by Tab.",
                                color="muted",
                            )
                        with ui.accordion_item(
                            "skip", label="Skip via Tab",
                            disabled=True,
                        ):
                            ui.text("This one is disabled.",
                                    color="muted")

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every prop AND every escape hatch is wired "
                        "to a control ; the preview AND the emitted "
                        "HTML both refresh on every change.",
                        color="muted", size="sm",
                    )
                    server_panel()

            # ── Card 7 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    events_panel()

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of Accordion's ``BINDABLE_PROPS = "
                        "('value',)`` contract. Clicking a header "
                        "writes straight through the binding — no "
                        "network round-trip. type / collapsible / "
                        "size / color stay design-time.",
                        color="muted", size="sm",
                    )
                    client = AccordionClient(key="playground")
                    with ui.hstack(align="center", gap="sm"):
                        ui.text("Current selection :",
                                color="muted", size="sm")
                        ui.code(client.expanded, lang="text")
                    three_items_into(ui.accordion(value=client.expanded))

                    ui.divider()

                    preview = ui.accordion(value=client.expanded)
                    three_items_into(preview)
                    emitted_html_block(
                        "Emitted HTML — bz-data reads the bound "
                        "value path directly ; clicking a header "
                        "writes through it, no round-trip.",
                        serialize_html(preview),
                    )

            # ── Card 9 — External controls — the 3 modes ────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes",
                               level=2)
                    ui.text(
                        "Same scenario (a sidebar trigger drives the "
                        "accordion) played three ways. Pick the mode "
                        "that fits your need.",
                        color="muted", size="sm",
                    )

                    # ── Mode 1 — Imperative only ────────────────────
                    ui.heading(
                        "Mode 1 — Imperative only (default)", level=3,
                    )
                    ui.text(
                        "No ClientState. The accordion owns its "
                        "expansion in client scope. Sibling buttons "
                        "call ``acc.expand(v)`` / ``.collapse(v)`` "
                        "/ ``.toggle(v)`` — DOM events caught by "
                        "the accordion root. **Use this by default "
                        "for purely-visual state.**",
                        color="muted", size="sm",
                    )
                    m1 = ui.accordion()
                    with m1:
                        with ui.accordion_item("a", label="Section A"):
                            ui.text("Body A.", color="muted")
                        with ui.accordion_item("b", label="Section B"):
                            ui.text("Body B.", color="muted")
                        with ui.accordion_item("c", label="Section C"):
                            ui.text("Body C.", color="muted")
                    with ui.hstack(wrap=True, gap="sm"):
                        ui.button("Open A", on_click=m1.expand("a"))
                        ui.button("Open B", on_click=m1.expand("b"))
                        ui.button("Toggle C", variant="outline",
                                  on_click=m1.toggle("c"))
                        ui.button("Collapse all", variant="ghost",
                                  on_click=m1.collapse_all())

                    ui.divider()

                    # ── Mode 2 — ClientBinding only ─────────────────
                    ui.heading("Mode 2 — ClientBinding only", level=3)
                    ui.text(
                        "Use this when **another component reads or "
                        "reacts to the expansion state** — a sidebar "
                        "that mirrors it, a badge that shows the open "
                        "section, server-side awareness on the next "
                        "render. The binding is the single source of "
                        "truth multi-component.",
                        color="muted", size="sm",
                    )
                    bound = AccordionClient(key="binding_only")
                    with ui.vstack(gap="sm"):
                        with ui.hstack(align="center", gap="sm"):
                            ui.text("Current selection :",
                                    color="muted", size="sm")
                            ui.code(bound.expanded, lang="text")
                        with ui.accordion(value=bound.expanded):
                            with ui.accordion_item("general",
                                                   label="General"):
                                ui.text("Body.", color="muted")
                            with ui.accordion_item("security",
                                                   label="Security"):
                                ui.text("Body.", color="muted")
                            with ui.accordion_item("billing",
                                                   label="Billing"):
                                ui.text("Body.", color="muted")
                        with ui.hstack(wrap=True, gap="sm"):
                            ui.button(
                                "Open General",
                                on_click=bound.expanded.set("general"),
                            )
                            ui.button(
                                "Open Security",
                                on_click=bound.expanded.set("security"),
                            )
                            ui.button(
                                "Open Billing",
                                on_click=bound.expanded.set("billing"),
                            )
                            ui.button(
                                "Clear", variant="ghost",
                                on_click=bound.expanded.set(""),
                            )

                    ui.divider()

                    # ── Mode 3 — Both : write-through ───────────────
                    ui.heading("Mode 3 — Both (write-through)",
                               level=3)
                    ui.text(
                        'A binding supplied AND ``.expand()`` called on '
                            'the instance. For single, the framework detects '
                            'the binding and delegates to ``binding.set(v)`` '
                            '— single source of truth preserved. Sibling '
                            'buttons + binding-aware components converge on '
                            'the same flag.',
                        color="muted", size="sm",
                    )
                    both = AccordionClient(key="both")
                    m3 = ui.accordion(value=both.expanded)
                    with m3:
                        with ui.accordion_item("a", label="Section A"):
                            ui.text("Body A.", color="muted")
                        with ui.accordion_item("b", label="Section B"):
                            ui.text("Body B.", color="muted")
                    with ui.hstack(wrap=True, gap="sm"):
                        ui.button("Open A via acc.expand()",
                                  on_click=m3.expand("a"))
                        ui.button("Open B via binding.set()",
                                  on_click=both.expanded.set("b"))
                        ui.button("Toggle A via acc.toggle()",
                                  variant="outline",
                                  on_click=m3.toggle("a"))

                    ui.divider()

                    # ── Mode 4 — Multiple binding ───────────────────
                    ui.heading(
                        "Bonus — multiple with array binding",
                        level=3,
                    )
                    ui.text(
                        "Same idea with ``multiple=True`` : the "
                        "binding holds a list of open ids. "
                        "``expand_all()`` / ``collapse_all()`` are "
                        "where multiple really shines.",
                        color="muted", size="sm",
                    )
                    multi = AccordionMultiClient(key="multi")
                    mult_acc = ui.accordion(multiple=True,
                                            value=multi.expanded)
                    with mult_acc:
                        with ui.accordion_item("a", label="Alpha"):
                            ui.text("Alpha body.", color="muted")
                        with ui.accordion_item("b", label="Bravo"):
                            ui.text("Bravo body.", color="muted")
                        with ui.accordion_item("c", label="Charlie"):
                            ui.text("Charlie body.", color="muted")
                    with ui.hstack(wrap=True, gap="sm"):
                        ui.button("Expand all",
                                  on_click=mult_acc.expand_all())
                        ui.button("Collapse all", variant="outline",
                                  on_click=mult_acc.collapse_all())

                    ui.divider()

                    preview = ui.accordion(value=bound.expanded)
                    with preview:
                        with ui.accordion_item("general", label="G"):
                            ui.text("body")
                    emitted_html_block(
                        "Emitted HTML — Mode 2 (binding only) : "
                        "bz-data ``get expanded`` reads the bound "
                        "path ; sibling ``binding.set()`` writes "
                        "back without a round-trip.",
                        serialize_html(preview),
                    )

            # ── Card 10 — Client events ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text(
                        "``on_change`` wired to a client expression "
                        "that pushes onto a ClientState list. Zero "
                        "network ; the log below re-renders via "
                        "bz-text on every change.",
                        color="muted", size="sm",
                    )
                    cevents = AccordionClientEvents()
                    # change fires on the hidden input ; its value is
                    # the JSON-stringified open-items list (multi) or
                    # the single open id. Push as-is.
                    _new_value = ClientExpression("$event.target.value")
                    with ui.flex(justify="center"):
                        with ui.accordion(
                            on_change=cevents.log.push(_new_value),
                        ):
                            with ui.accordion_item("a",
                                                   label="Toggle me"):
                                ui.text("Each open/close pushes once.",
                                        color="muted")
                            with ui.accordion_item("b",
                                                   label="Or me"):
                                ui.text("Same here.", color="muted")

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text(
                            "Live log (client-reactive — no refresh)",
                            color="muted", size="sm",
                        )
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    ui.divider()

                    log_text = ClientExpression(
                        '($bz.state.AccordionClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    preview = ui.accordion(
                        on_change=cevents.log.push(_new_value),
                    )
                    with preview:
                        with ui.accordion_item("a", label="A"):
                            ui.text("A body")
                        with ui.accordion_item("b", label="B"):
                            ui.text("B body")
                    emitted_html_block(
                        "Emitted HTML — @change relocated onto the "
                        "hidden input ; _emitChange dispatches change "
                        "after every open/close, the client "
                        "expression pushes the new open list.",
                        serialize_html(preview),
                    )
