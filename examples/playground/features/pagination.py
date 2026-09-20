"""``Pagination`` test bench.

Ten visual cards : full gabarit. ``BINDABLE_PROPS = ("value",
"disabled")`` — current page + lock flag ; ``total_pages`` and
``max_visible`` restructure the window, so they stay design-time
(a ``@refreshable`` re-renders them).

Six props : ``value`` (autoname-from) / ``total_pages`` /
``max_visible`` / ``disabled`` / ``color`` / ``size``. One event :
``change``. Imperative API : ``.set(page)`` / ``.next()`` /
``.prev()``.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/pagination"


SIZES  = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]


class PaginationPlayground(PageState):
    value:       int  = field(default=5)
    total_pages: int  = field(default=20)
    max_visible: int  = field(default=7)
    name:        str  = field(default="")
    color:       str  = field(default="primary")
    size:        str  = field(default="md")
    disabled:    bool = field(default=False)
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


class PaginationEvents(PageState):
    log: list = field(default_factory=list)


# Drives the server-events demo Pagination. ``value=state.value``
# (a binding) → AUTONAME_FROM="value" derives ``name="value"`` from
# the binding's field_name → the hidden input carries it → the
# dispatcher's payload matches the handler's ``value=`` kwarg. No
# manual ``name="value"`` anywhere — that's CLAUDE.md rule 4.
class PaginationServerEvents(ClientState, persist="memory"):
    value: int = field(default=3)


class PaginationClient(ClientState, persist="memory"):
    value:       int  = field(default=1)
    disabled:    bool = field(default=False)


class PaginationClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


# Drives the form-integration demo (Card 4). Same autoname idiom :
# binding's ``page`` field_name flows through as the form-data key,
# no manual ``name="page"`` needed.
class PaginationFormDemo(ClientState, persist="memory"):
    page: int = field(default=3)


# Card 10, mode 2: the page is read by a neighbour (the label), so it
# needs a ClientState. Mode 1 just above does without.
class PaginationImperative(ClientState, persist="memory"):
    page: int = field(default=1)


def log(name: str) -> None:
    state = PaginationEvents()
    state.log = [*state.log, name]


def log_change(value: int = 0) -> None:
    log(f"change(value={value!r})")


def clear_log() -> None:
    state = PaginationEvents()
    state.log = []


def server_changed(state: PaginationPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    # deps=[PaginationPlayground] re-renders server_panel automatically.
    pass


def playground_change_handler(value: int = 0) -> None:
    log(f"playground-server-change(value={value!r})")


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


def build_preview(state: PaginationPlayground):
    # ⚠️ ``state.value`` IS PASSED AS IS, with no ``int()``.
    #
    # A value read on a ``PageState`` carries a stamp (the original
    # field's name). Two mechanisms depend on it, and ``int()`` killed
    # both at once — hence "only the value does not work, and there is
    # not even a name":
    #
    #   1. ``_serverSync``: the value key is only re-seeded if the server
    #      owns it, which the stamp attests. Without it, the component is
    #      deemed client-owned and the scope keeps its page from the
    #      first mount (the guard exists so as not to overwrite a user
    #      click at every neighbouring refresh — it is right, it was the
    #      bench lying about the provenance).
    #   2. autoname: ``names_field=True`` derives ``name=`` from the
    #      stamp's field name. No stamp → no name → no hidden input.
    #
    # Measured: ``value=state.value`` → ``_serverSync: ['active',
    # '_total', '_maxVisible']`` + ``name="value"``;
    # ``value=int(state.value)`` → ``['_total', '_maxVisible']`` + no
    # name.
    #
    # ``total_pages`` / ``max_visible`` keep their ``int()``: they are
    # design-time props, their re-sync depends on no stamp.
    kwargs: dict = {
        "value": state.value,
        "total_pages": int(state.total_pages or 1),
        "max_visible": int(state.max_visible or 7),
        "color": state.color,
        "size": state.size,
        "disabled": state.disabled,
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
    return ui.pagination(**kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[PaginationPlayground])
def server_panel() -> None:
    state = PaginationPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("value (current page)"):
            ui.number_input(value=state.value,
                     on_change=server_changed)
        with control("total_pages"):
            ui.number_input(value=state.total_pages,
                     on_change=server_changed)
        with control("max_visible (page buttons)"):
            ui.number_input(value=state.max_visible,
                     on_change=server_changed)
        with control("name (overrides autoname)"):
            ui.input(value=state.name, placeholder="page",
                     on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled,
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!gap-1",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-pagination",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Project pages",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="margin: 1rem",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=pagination",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Page navigation",
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

    with ui.flex(justify="center", align="center"):
        build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


@refreshable(deps=[PaginationEvents])
def events_panel() -> None:
    state = PaginationEvents()

    ui.text(
        "Pagination fires ``change`` when the user picks a new "
        "page — the new value is the kwarg.",
        color="muted", size="sm",
    )

    with ui.flex(justify="center"):
        # Binding-driven value → AUTONAME_FROM="value" derives
        # ``name="value"`` from the binding's field_name. The
        # dispatcher's payload key matches the handler's ``value=``
        # kwarg automatically. No manual ``name=`` (CLAUDE.md rule 4).
        ev_state = PaginationServerEvents()
        ui.pagination(value=ev_state.value, total_pages=10,
                      on_change=log_change)

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
                        color="muted", size="sm", classes="font-mono")
    else:
        ui.text("(no events yet — pick a different page above)",
                color="muted", size="sm")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (Pagination with on_change handler)",
        serialize_html(
            ui.pagination(value=ev_state.value, total_pages=10,
                          on_change=log_change)
        ),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Pagination", level=1)
            ui.text(
                "Page-navigation widget : *Prev* — N page numbers — "
                "*Next* with ellipsis when total exceeds "
                "``max_visible``. Page list computed client-side "
                "from ``value / total_pages / max_visible`` — wire "
                "``value=client_state.page`` for live re-rendering "
                "with zero server round-trip.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Basic (5 pages, no ellipsis)", level=3)
                    with ui.flex(justify="center"):
                        ui.pagination(value=2, total_pages=5)

                    ui.heading("Many pages (ellipsis)", level=3)
                    with ui.vstack():
                        ui.text("active=1 / 20", color="muted",
                                size="xs")
                        with ui.flex(justify="center"):
                            ui.pagination(value=1, total_pages=20)
                        ui.text("active=10 / 20", color="muted",
                                size="xs")
                        with ui.flex(justify="center"):
                            ui.pagination(value=10, total_pages=20)
                        ui.text("active=20 / 20", color="muted",
                                size="xs")
                        with ui.flex(justify="center"):
                            ui.pagination(value=20, total_pages=20)

                    ui.heading("max_visible (window width)", level=3)
                    for mv in (5, 7, 9, 11):
                        ui.text(f"max_visible={mv}",
                                color="muted", size="xs")
                        with ui.flex(justify="center"):
                            ui.pagination(value=10, total_pages=20,
                                          max_visible=mv)

                    ui.heading("Sizes", level=3)
                    for s in SIZES:
                        ui.text(f"size={s}",
                                color="muted", size="xs")
                        with ui.flex(justify="center"):
                            ui.pagination(value=3, total_pages=10,
                                          size=s)

                    ui.heading("Colors (active page)", level=3)
                    for c in COLORS:
                        with ui.flex(justify="center"):
                            ui.pagination(value=3, total_pages=10,
                                          color=c)

                    ui.heading("Disabled", level=3)
                    with ui.flex(justify="center"):
                        ui.pagination(value=3, total_pages=10,
                                      disabled=True)

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "No content slots — Pagination is "
                        "fully data-driven. Reactive surface : "
                        "``value`` / ``total_pages`` / "
                        "``disabled`` all accept ClientBinding "
                        "(see Client playground).",
                        color="muted", size="sm",
                    )

                    ui.text(
                        "``value`` / ``total_pages`` / ``disabled`` "
                        "accept ClientBinding — see Card 8 (Client "
                        "playground) below for the live binding demo.",
                        color="muted", size="sm",
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs the algorithm clamps.",
                            color="muted", size="sm")

                    ui.heading("total_pages=1 (single page)", level=3)
                    with ui.flex(justify="center"):
                        ui.pagination(value=1, total_pages=1)

                    ui.heading("total_pages=0 (empty)", level=3)
                    with ui.flex(justify="center"):
                        ui.pagination(value=1, total_pages=0)

                    ui.heading("value > total_pages", level=3)
                    ui.text("Clamps visually — the active "
                            "indicator stays within bounds.",
                            color="muted", size="xs")
                    with ui.flex(justify="center"):
                        ui.pagination(value=99, total_pages=5)

                    ui.heading("max_visible smaller than 5 (clamped)",
                               level=3)
                    with ui.flex(justify="center"):
                        ui.pagination(value=3, total_pages=10,
                                      max_visible=2)

                    ui.heading("Huge total_pages (1000)", level=3)
                    with ui.flex(justify="center"):
                        ui.pagination(value=500, total_pages=1000)

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Pagination in common contexts.",
                            color="muted", size="sm")

                    ui.heading("Below a table (footer)", level=3)
                    with ui.card():
                        with ui.vstack():
                            ui.text("[Table rows would render here]",
                                    color="muted", size="sm")
                            ui.divider()
                            with ui.flex(justify="between",
                                         align="center"):
                                ui.text("Showing 21–30 of 200",
                                        color="muted", size="sm")
                                ui.pagination(value=3,
                                              total_pages=20,
                                              size="sm")

                    ui.heading("Inside ui.card (search results)",
                               level=3)
                    with ui.card():
                        with ui.vstack():
                            ui.heading("Search results", level=3)
                            ui.text("[Result list…]",
                                    color="muted", size="sm")
                            ui.divider()
                            with ui.flex(justify="center"):
                                ui.pagination(value=2,
                                              total_pages=8)

                    ui.heading("Inside ui.form (submit on pick)",
                               level=3)
                    ui.text(
                        "When bound via ``value=`` and placed in "
                        "a form, picking a page rides into form "
                        "data via the hidden ``<input>``.",
                        color="muted", size="xs",
                    )
                    # Binding-driven : the ``page`` field_name of
                    # PaginationFormDemo flows through autoname →
                    # the form payload key is ``page`` automatically.
                    form_state = PaginationFormDemo()
                    with ui.form():
                        with ui.flex(justify="center"):
                            ui.pagination(value=form_state.page,
                                          total_pages=10)

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Root emits ``<nav>`` semantics ; each "
                        "page button is a native ``<button>`` so "
                        "keyboard works out of the box. The "
                        "active page carries ``aria-current="
                        "\"page\"`` so screen readers announce "
                        "the user's location. Pair with "
                        "``aria_label=`` to describe what the "
                        "pagination paginates (results, comments, "
                        "etc.).",
                        color="muted", size="sm",
                    )
                    with ui.flex(justify="center"):
                        ui.pagination(value=3, total_pages=10,
                                      aria_label="Project pages")

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every prop AND every escape hatch is "
                        "wired to a control ; the preview AND the "
                        "emitted HTML both refresh on every "
                        "change.",
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
                        "Mirror of Pagination's ``BINDABLE_PROPS = "
                        "('value', 'disabled')`` contract. Picking a "
                        "page mutates the bound state ; the active "
                        "highlight + the current-page label below stay "
                        "in sync without a network round-trip. "
                        "``total_pages`` is design-time (it restructures "
                        "the range).",
                        color="muted", size="sm",
                    )
                    client = PaginationClient()
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("value (bound)"):
                            ui.number_input(value=client.value)
                        with control("disabled"):
                            ui.switch(checked=client.disabled)

                    ui.divider()

                    with ui.flex(justify="center"):
                        ui.pagination(value=client.value,
                                      total_pages=10,
                                      disabled=client.disabled,
                                      color="primary")

                    ui.divider()

                    with ui.flex(justify="center"):
                        ui.text(
                            ClientExpression(
                                "'Active : ' + ($bz.state."
                                "PaginationClient.default.value"
                                " || '?') + ' / 10'"
                            ),
                            color="muted", size="sm",
                            classes="font-mono",
                        )

                    ui.divider()

                    preview = ui.pagination(
                        value=client.value,
                        total_pages=10,
                        disabled=client.disabled,
                        color="primary",
                    )
                    emitted_html_block(
                        "Emitted HTML — the page-button rail "
                        "computes the visible range from the "
                        "bound state via the bz-data "
                        "getter.",
                        serialize_html(preview),
                    )

            # ── Card 9 — External controls (imperative API) ────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes",
                               level=2)
                    ui.text(
                        "``.set(page)`` / ``.next()`` / ``.prev()`` — "
                        "same cut as Stepper and Carousel. ``.next()`` "
                        "and ``.prev()`` ALWAYS dispatch a DOM command, "
                        "binding or not : where the page lands depends "
                        "on the live value and on ``total_pages``, "
                        "neither of which the server knows at render "
                        "time. ``.set(page)`` writes through the "
                        "binding when there is one. Bounds AND the "
                        "``disabled`` lock live in the single mutator, "
                        "so every imperative entry is guarded — the "
                        "rendered buttons already had their "
                        "``bz-attr:disabled``, an external caller had "
                        "nothing.",
                        color="muted", size="sm",
                    )

                    ui.heading("Mode 1 — Imperative only (default)",
                               level=3)
                    ui.text(
                        "No ClientState. The pagination owns its page "
                        "in client scope. **Use this by default when "
                        "nothing else needs to read the position.**",
                        color="muted", size="sm",
                    )
                    with ui.flex(justify="center"):
                        pager = ui.pagination(value=1, total_pages=8)
                    with ui.hstack(gap="sm", justify="center"):
                        ui.button("Prev", variant="outline",
                                  on_click=pager.prev())
                        ui.button("Next", on_click=pager.next())
                        ui.button("Last", variant="ghost",
                                  on_click=pager.set(8))
                        ui.button("Restart", variant="ghost",
                                  on_click=pager.set(1))

                    ui.divider()

                    ui.heading("Mode 2 — ClientBinding (a neighbour "
                               "reads the page)", level=3)
                    ui.text(
                        "Use this when **another component needs to "
                        "read the position** — here the label below. "
                        "``.set()`` writes through the binding ; "
                        "``.next()`` / ``.prev()`` still dispatch.",
                        color="muted", size="sm",
                    )
                    imp = PaginationImperative()
                    with ui.flex(justify="center"):
                        bound_pager = ui.pagination(value=imp.page,
                                                    total_pages=8)
                    with ui.hstack(gap="sm", justify="center"):
                        ui.button("Prev", variant="outline",
                                  on_click=bound_pager.prev())
                        ui.button("Next", on_click=bound_pager.next())
                        ui.button("Restart", variant="ghost",
                                  on_click=bound_pager.set(1))
                    with ui.flex(justify="center"):
                        ui.text(
                            ClientExpression(
                                "'Page ' + ($bz.state."
                                "PaginationImperative.default.page"
                                " || '?') + ' / 8'"
                            ),
                            color="muted", size="sm",
                            classes="font-mono",
                        )

                    ui.divider()

                    ui.heading("Mode 3 — Both (write-through)", level=3)
                    ui.text(
                        "A binding AND the imperative methods, on the "
                        "same instance. The buttons move the SAME cell "
                        "the number input writes and the mirror reads — "
                        "one source of truth, three ways to write it. "
                        "This is the mode to reach for when a rail and "
                        "a « go to page » field must never disagree.",
                        color="muted", size="sm",
                    )
                    both = PaginationImperative(key="both")
                    with ui.flex(justify="center"):
                        both_pager = ui.pagination(value=both.page,
                                                   total_pages=8)
                    with ui.hstack(gap="sm", justify="center",
                                   align="center"):
                        ui.button("Prev", variant="outline",
                                  on_click=both_pager.prev())
                        ui.button("Next", on_click=both_pager.next())
                        ui.button("Jump to 4", variant="ghost",
                                  on_click=both_pager.set(4))
                        with ui.flex(classes="w-24"):
                            ui.number_input(value=both.page, min=1, max=8)

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — the root carries "
                        "``bz-on:bz-set`` / ``bz-on:bz-next`` / "
                        "``bz-on:bz-prev``, the three receivers the "
                        "imperative methods dispatch to. Bounds and the "
                        "``disabled`` lock live in the single mutator, "
                        "so an external caller is guarded exactly like "
                        "the rendered buttons.",
                        serialize_html(
                            ui.pagination(value=both.page, total_pages=8)
                        ),
                    )
            # ── Card 10 — Client events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text("change event wired to a client "
                            "expression that pushes the new value "
                            "onto a ClientState list. Zero network.",
                            color="muted", size="sm")
                    cevents = PaginationClientEvents()
                    _new_value = ClientExpression("$event.target.value")
                    with ui.flex(justify="center"):
                        ui.pagination(
                            value=1, total_pages=10,
                            on_change=cevents.log.push(_new_value),
                        )

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive)",
                                color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    ui.divider()

                    log_text = ClientExpression(
                        '($bz.state.PaginationClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — @change relocated onto the "
                        "hidden input ; setActive dispatches change, "
                        "the client expression pushes the new page "
                        "number (as string).",
                        serialize_html(
                            ui.pagination(
                                value=1, total_pages=10,
                                on_change=cevents.log.push(_new_value),
                            )
                        ),
                    )

