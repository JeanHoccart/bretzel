"""``EmptyState`` test bench — "nothing here yet" placeholder.

Six visual cards : Reference / Use cases / A11y / Server playground
/ Client playground. ``BINDABLE_PROPS = ("title", "description")`` ;
``IS_CONTAINER`` for the optional action slot.

Placeholder for empty lists / filter misses / no-data surfaces.
Replaces the ad-hoc "Nothing here" strings that used to scatter
across list-rendering components.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/empty_state"

SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]


# ── State ─────────────────────────────────────────────────────────────


class EmptyStatePlayground(PageState):
    title:       str  = field(default="No tasks yet")
    icon:        str  = field(default="inbox")
    description: str  = field(default="Create your first task to get started.")
    size:        str  = field(default="md")
    color:       str  = field(default="muted")
    has_action:  bool = field(default=True)
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")


class EmptyStateClient(ClientState, persist="memory"):
    """Mirror of EmptyState's BINDABLE_PROPS = ('title', 'description')."""

    title:       str = field(default="Live title")
    description: str = field(default="Type below to update.")


def server_changed(state: EmptyStatePlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    # deps=[EmptyStatePlayground] re-renders server_panel automatically.
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


def build_preview(state: EmptyStatePlayground) -> dict:
    kwargs: dict = {
        "icon": state.icon if state.icon else None,
        "description": state.description if state.description else None,
        "size": state.size,
        "color": state.color,
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


# ── Refreshable ───────────────────────────────────────────────────────


@refreshable(deps=[EmptyStatePlayground])
def server_panel() -> None:
    state = EmptyStatePlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("title"):
            ui.input(value=state.title, on_change=server_changed)
        with control("icon (Lucide name)"):
            ui.input(value=state.icon, placeholder="inbox / search",
                     on_change=server_changed)
        with control("description"):
            ui.textarea(value=state.description, rows=2,
                        on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("has_action"):
            ui.switch(checked=state.has_action,
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!min-h-[200px]",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id,
                     placeholder="empty-tasks",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="No tasks placeholder",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="opacity: 0.8",
                     on_change=server_changed)
        with control("extra_attrs (key=value per line)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=empty",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Empty section hint",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    # LIVE preview — rendered into the page DOM.
    kwargs = build_preview(state)
    live = ui.empty_state(state.title, **kwargs)
    if state.has_action:
        with live:
            ui.button("Primary action", icon_left="plus",
                      color="primary")
            ui.button("Secondary", variant="outline")

    ui.divider()

    # Separate instance for serialize_html (which detaches its
    # argument from the parent context — without a second instance
    # the live preview above would be un-rendered from the page).
    snap = ui.empty_state(state.title, **kwargs)
    if state.has_action:
        with snap:
            ui.button("Primary action", icon_left="plus",
                      color="primary")
            ui.button("Secondary", variant="outline")
    emitted_html_block(
        "Emitted HTML — the controls grid drives this snapshot live",
        serialize_html(snap),
    )


# ── Page ──────────────────────────────────────────────────────────────


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("EmptyState", level=1)
            ui.text(
                "Placeholder for empty lists / filter misses / "
                "no-data views. Centered icon + title + description "
                "+ optional action(s) via ``with`` body. The "
                "replacement for the ad-hoc \"Nothing here\" strings "
                "that used to scatter across list-rendering "
                "components (Combobox empty filter, Table empty "
                "rows, your custom zones).",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)

                    ui.heading("Minimal — title only", level=3)
                    ui.empty_state("Nothing here yet")

                    ui.heading("With icon", level=3)
                    ui.empty_state("No tasks", icon="inbox")

                    ui.heading("With description", level=3)
                    ui.empty_state(
                        "No matching countries",
                        icon="search",
                        description=(
                            "Try a different spelling or clear "
                            "your filter."
                        ),
                    )

                    ui.heading(
                        "With action — IS_CONTAINER with block",
                        level=3,
                    )
                    with ui.empty_state(
                        "No issues",
                        icon="ticket",
                        description=(
                            "Create your first issue to track "
                            "work here."
                        ),
                    ):
                        ui.button("New issue", icon_left="plus",
                                  color="primary")

                    ui.heading("With multiple actions", level=3)
                    with ui.empty_state(
                        "Welcome to your dashboard",
                        icon="rocket",
                        description=(
                            "Add a widget to start tracking metrics, "
                            "or watch a tutorial first."
                        ),
                    ):
                        ui.button("Add widget", icon_left="plus",
                                  color="primary")
                        ui.button("Watch tutorial", variant="outline",
                                  icon_left="play")

                    ui.heading("Sizes (xs → xl)", level=3)
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        for s in ui.each(SIZES):
                            with ui.card():
                                ui.empty_state(
                                    f"Size {s}",
                                    icon="circle-dot",
                                    description=(
                                        "Standard 5-palier scale."
                                    ),
                                    size=s,
                                )

                    ui.heading("Colors", level=3)
                    with ui.grid(cols={"base": 1, "sm": 2, "md": 4}, gap="md"):
                        for c in ui.each(COLORS):
                            with ui.card():
                                ui.empty_state(
                                    c.title(),
                                    icon="circle-dot",
                                    size="sm",
                                    color=c,
                                )

            # ── Card 2 — Use cases ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Common use cases", level=2)

                    ui.heading(
                        "Inside a Table — empty rows", level=3,
                    )
                    with ui.card():
                        ui.empty_state(
                            "No results",
                            icon="table-2",
                            description="Adjust your filters.",
                            size="sm",
                        )

                    ui.heading(
                        "Inside a card — first-time onboarding",
                        level=3,
                    )
                    with ui.card():
                        with ui.empty_state(
                            "Welcome",
                            icon="hand",
                            description=(
                                "Click the action below to start."
                            ),
                            size="lg",
                        ):
                            ui.button("Get started",
                                      icon_left="arrow-right",
                                      color="primary")

                    ui.heading("Error / not found page", level=3)
                    with ui.empty_state(
                        "Page not found",
                        icon="search-x",
                        description=(
                            "The link may have changed or expired."
                        ),
                    ):
                        ui.button("Go home", icon_left="home")

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)

                    ui.heading("No icon", level=3)
                    ui.empty_state(
                        "Bare title and description",
                        description=(
                            "No icon kwarg → no icon box rendered "
                            "at all (saves vertical space)."
                        ),
                    )

                    ui.heading(
                        "Very long title + description", level=3,
                    )
                    ui.empty_state(
                        "A very long empty-state title that may wrap on narrow widths",
                        icon="info",
                        description=(
                            "And a very long description that "
                            "exceeds the comfortable measure of "
                            "the max-w-sm wrapper — it should "
                            "wrap to multiple lines and stay "
                            "centred within the column."
                        ),
                    )

                    ui.heading(
                        "HTML special chars (XSS escape)", level=3,
                    )
                    ui.empty_state(
                        "<script>alert(1)</script>",
                        description="<em>Escaped</em> too.",
                    )

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "``role=\"status\"`` + ``aria-live=\"polite\"`` "
                        "so screen readers announce the empty "
                        "message without interrupting. Title is an "
                        "``<h3>`` (anchored in the page outline), "
                        "description is a ``<p>``. The action slot "
                        "is the user's composition — buttons keep "
                        "their own a11y semantics.",
                        color="muted", size="sm",
                    )
                    ui.empty_state(
                        "Keyboard test",
                        icon="keyboard",
                        description=(
                            "Tab through the actions below — they "
                            "stay focusable in declared order."
                        ),
                    )

            # ── Card 5 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every prop AND every escape hatch wired "
                        "to a control ; preview AND emitted HTML "
                        "both refresh on every change.",
                        color="muted", size="sm",
                    )
                    server_panel()

            # ── Card 6 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "``title`` and ``description`` accept a "
                        "``ClientBinding`` — the copy follows live "
                        "state without a server round-trip. Type "
                        "in the inputs below to see the "
                        "EmptyState update.",
                        color="muted", size="sm",
                    )
                    cstate = EmptyStateClient(key="live")
                    with ui.vstack(gap="sm"):
                        ui.input(value=cstate.title,
                                 placeholder="Live title…")
                        ui.input(value=cstate.description,
                                 placeholder="Live description…")
                    ui.empty_state(
                        cstate.title,
                        icon="rocket",
                        description=cstate.description,
                    )
