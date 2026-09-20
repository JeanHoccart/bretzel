"""``Dialog`` test bench.

Ten cards : full 7-section gabarit (S2 split into 4 visual cards,
Triggers standing in for Slots on this container). ``BINDABLE_PROPS =
("open",)`` — the open flag gets a dedicated Client playground card ;
title / width / dismissible / persistent stay design-time.

Five props : ``open`` / ``title`` / ``width`` / ``dismissible`` /
``persistent``. Two events : ``open`` / ``close``. The dialog is
purely visual — open it from outside via the imperative API
(``.open()`` / ``.close()`` / ``.toggle()``) or by binding ``open=``
to a ``ClientState`` field. Header / body / footer are composed
inside the ``with`` block.
"""

from functools import partial

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/dialog"


WIDTHS = ["sm", "md", "lg", "xl", "full"]


# ── Per-row imperative demo state ──────────────────────────────────────
# A simple in-memory list — illustrates the imperative `.open()` /
# `.close()` API where the per-row confirm dialog needs zero
# ClientState declaration (the dialog instance owns its open flag in
# client scope). Each row's Delete button calls ``dlg.open()`` and the
# dialog body calls ``dlg.close()`` — single-source DOM events under
# the hood. Cf. `.claude/bretzel/imperative-api.md`.

class DeletedRows(PageState):
    """Server-side log of which rows have been 'deleted'."""

    log: list = field(default_factory=list)


def delete_row(row_id: int) -> None:
    state = DeletedRows()
    state.log = [*state.log, row_id]


def reset_deleted() -> None:
    DeletedRows().log = []


class DialogPlayground(PageState):
    title:       str  = field(default="Confirm action")
    width:       str  = field(default="md")
    dismissible: bool = field(default=True)
    persistent:  bool = field(default=False)
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifiers.
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")


class DialogEvents(PageState):
    log: list = field(default_factory=list)


class DialogClient(ClientState, persist="memory"):
    """Mirror of Dialog's BINDABLE_PROPS = ('open',)."""

    open: bool = field(default=False)


# Drives the "Nested form inside the dialog" demo in Composability.
# ``email`` field_name flows through AUTONAME_FROM="value" → form-data
# key is ``email``. No manual ``name=`` anywhere.
class DialogFormDemo(ClientState, persist="memory"):
    email: str = field(default="")


class DialogClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


def log(name: str) -> None:
    state = DialogEvents()
    state.log = [*state.log, name]


def log_open()  -> None: log("open")
def log_close() -> None: log("close")


def clear_log() -> None:
    state = DialogEvents()
    state.log = []


def server_changed(state: DialogPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    pass


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: DialogPlayground) -> dict:
    kwargs: dict = {
        "title": state.title,
        "width": state.width,
        "dismissible": state.dismissible,
        "persistent": state.persistent,
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


@refreshable(deps=[DialogPlayground])
def server_panel() -> None:
    state = DialogPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("title"):
            ui.input(value=state.title,
                     placeholder="Confirm action",
                     on_change=server_changed)
        with control("width"):
            ui.select(value=state.width,
                      options=[(w, w) for w in WIDTHS],
                      on_change=server_changed)
        with control("dismissible (ESC + backdrop)"):
            ui.switch(checked=state.dismissible,
                      on_change=server_changed)
        with control("persistent (overrides dismissible)"):
            ui.switch(checked=state.persistent,
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!max-w-xl",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-dialog",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Confirm dialog",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="--bz-overlay-z: 100",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=dialog",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Open the dialog",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    with ui.flex(justify="center"):
        with ui.dialog(**kwargs) as preview_dlg:
            ui.text("This is the dialog body. Toggle the controls "
                    "above to see how the preview reshapes.",
                    color="muted")
        ui.button("Open the preview dialog", color="primary",
                  on_click=preview_dlg.open())

    ui.divider()

    preview = ui.dialog(**kwargs)
    with preview:
        ui.text("Body", color="muted")
    emitted_html_block(
        "Emitted HTML (Dialog with body only — open via .open())",
        serialize_html(preview),
    )


@refreshable(deps=[DialogEvents])
def events_panel() -> None:
    state = DialogEvents()

    ui.text(
        "Dialog exposes two events : ``on_open`` and ``on_close`` — "
        "both wired to the server on the SAME dialog (the close handler "
        "rides a hidden carrier). Open / close below and watch the log "
        "update on both.",
        color="muted", size="sm",
    )

    with ui.flex(justify="center"):
        with ui.dialog(
            title="Event-logging dialog",
            on_open=log_open,
            on_close=log_close,
        ) as logger_dlg:
            ui.text("Close me via the × button or click outside. "
                    "Both fire ``on_close``.",
                    color="muted")
        ui.button("Open + close logger", color="primary",
                  on_click=logger_dlg.open())

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
        ui.text("(no events yet — open and close the dialog above)",
                color="muted", size="sm")

    ui.divider()

    representative = ui.dialog(
        title="Sample",
        on_open=log_open,
        on_close=log_close,
    )
    with representative:
        ui.text("Body")
    emitted_html_block(
        "Emitted HTML (Dialog with on_open + on_close — the close "
        "carrier is the hidden div with hx-trigger=\"close from:#…\")",
        serialize_html(representative),
    )


@refreshable(deps=[DeletedRows])
def imperative_per_row() -> None:
    """Per-row confirm pattern using the imperative `.open()` /
    `.close()` API — zero ClientState declaration for the dialogs
    themselves, the only state is the server-side log of which row
    got 'deleted' (PageState, drives the refresh)."""

    state = DeletedRows()
    rows = [
        {"id": 1, "name": "Alpha"},
        {"id": 2, "name": "Beta"},
        {"id": 3, "name": "Gamma"},
    ]

    ui.text(
        "Each row owns its confirm dialog. The Delete button on the "
        "row calls ``dlg.open()`` ; the buttons inside the dialog "
        "call ``dlg.close()``. No ``ClientState`` declared for the "
        "dialogs — they're client-local. The 'deleted' log below is "
        "the only ``PageState``, and it drives this section's refresh.",
        color="muted", size="sm",
    )

    with ui.vstack(gap="sm"):
        for row in ui.each(rows, key="id"):
            deleted = row["id"] in state.log
            with ui.hstack(align="center", justify="between"):
                ui.text(
                    f"{row['name']}{' (deleted)' if deleted else ''}",
                    color="muted" if deleted else "text",
                )
                confirm = ui.dialog(title=f"Delete {row['name']} ?")
                with confirm:
                    ui.text(
                        f"Permanently delete row #{row['id']} "
                        f"({row['name']}) ? This is irreversible.",
                        color="muted",
                    )
                    with ui.hstack(justify="end", gap="sm"):
                        ui.button(
                            "Cancel",
                            variant="ghost",
                            on_click=confirm.close(),
                        )
                        ui.button(
                            "Delete",
                            color="error",
                            on_click=[
                                partial(delete_row, row["id"]),
                                confirm.close(),
                            ],
                            disabled=deleted,
                        )
                ui.button(
                    "Delete",
                    color="error",
                    variant="ghost",
                    size="sm",
                    on_click=confirm.open(),
                    disabled=deleted,
                )

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text(
            f"Deleted so far : {len(state.log)}",
            color="muted", size="sm",
        )
        ui.button(
            "Reset", variant="ghost", size="xs",
            on_click=reset_deleted, disabled=not state.log,
        )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Dialog", level=1)
            ui.text(
                "Centered modal with backdrop, escape, and scroll "
                "lock. Two ways to drive the open state : ``as dlg`` "
                "+ ``dlg.open()`` (imperative API — default for "
                "purely-visual overlays) or ``open=ClientBinding`` "
                "(when another component needs to read or react to "
                "the state). The 2 modes are compared side-by-side "
                "in Card 9.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Click each trigger to see the dialog.",
                            color="muted", size="sm")

                    ui.heading(
                        "Basic — external trigger via .open()",
                        level=3,
                    )
                    ui.text(
                        "Capture the instance via ``as dlg`` and call "
                        "``dlg.open()`` / ``dlg.close()`` / "
                        "``dlg.toggle()`` from a sibling button. "
                        "client-local state, no ClientState declared. "
                        "The imperative API is the default style for "
                        "purely-visual overlays.",
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="center", gap="md"):
                        with ui.dialog(title="A dialog") as basic_dlg:
                            ui.text("Triggered from the sibling button.")
                            ui.button(
                                "Close from inside",
                                variant="ghost",
                                on_click=basic_dlg.close(),
                            )
                        ui.button(
                            "Open via .open()",
                            on_click=basic_dlg.open(),
                        )
                        ui.button(
                            "Toggle via .toggle()",
                            variant="outline",
                            on_click=basic_dlg.toggle(),
                        )

                    ui.heading("Widths", level=3)
                    with ui.hstack(wrap=True):
                        for w in WIDTHS:
                            with ui.dialog(
                                title=f"Width {w}",
                                width=w,
                            ) as width_dlg:
                                ui.text(f"This dialog uses "
                                        f"width={w}.")
                            ui.button(w.upper(),
                                      on_click=width_dlg.open())

                    ui.heading("Dismissible vs persistent", level=3)
                    with ui.hstack():
                        with ui.dialog(title="Dismissible") as dismiss_dlg:
                            ui.text("Click backdrop or press "
                                    "ESC to close.",
                                    color="muted")
                        ui.button("Dismissible (default)",
                                  on_click=dismiss_dlg.open())
                        with ui.dialog(
                            title="Persistent",
                            persistent=True,
                        ) as persist_dlg:
                            ui.text("Backdrop + ESC are inert. "
                                    "Only an explicit close button "
                                    "dismisses.",
                                    color="muted")
                        ui.button("Persistent", color="error",
                                  on_click=persist_dlg.open())

                    ui.heading("With footer (composed in body)",
                               level=3)
                    with ui.hstack():
                        with ui.dialog(
                            title="Save changes?",
                        ) as footer_dlg:
                            ui.text("Footer is just any layout at "
                                    "the end of the ``with`` block "
                                    "— typically an ``hstack`` of "
                                    "buttons.",
                                    color="muted")
                            with ui.hstack(justify="end", gap="sm"):
                                ui.button("Cancel", variant="ghost",
                                          on_click=footer_dlg.close())
                                ui.button("Save", color="primary",
                                          on_click=footer_dlg.close())
                        ui.button("With footer", variant="outline",
                                  on_click=footer_dlg.open())

            # ── Card 2 — Triggers ───────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Triggers", level=2)
                    ui.text(
                        "Dialog is purely visual — any clickable "
                        "component can open it via the imperative "
                        "``.open()`` API. Capture the dialog instance "
                        "with ``as dlg`` then wire ``on_click=dlg."
                        "open()`` on the trigger of your choice.",
                        color="muted", size="sm",
                    )

                    ui.heading("Trigger = Button", level=3)
                    with ui.dialog(
                        title="Plain button trigger",
                    ) as btn_dlg:
                        ui.text("Most common shape.")
                    ui.button("Open via Button",
                              on_click=btn_dlg.open())

                    ui.heading("Trigger = IconButton", level=3)
                    with ui.dialog(title="Settings") as icon_dlg:
                        ui.text("Icon-only trigger.")
                    ui.icon_button("settings", variant="ghost",
                                   aria_label="Settings",
                                   on_click=icon_dlg.open())

                    ui.heading("Trigger = ghost Button", level=3)
                    with ui.dialog(
                        title="Advanced options",
                    ) as link_dlg:
                        ui.text("Any clickable Component works. "
                                "``Link`` itself is navigation-only "
                                "(href, no ``on_click``) — for a "
                                "link-styled trigger use "
                                "``ui.button(variant='ghost')``.")
                    ui.button("Open advanced options",
                              variant="ghost",
                              on_click=link_dlg.open())

                    ui.heading(
                        "open = ClientBinding — see Card 9 mode 2",
                        level=3,
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs and exotic combinations.",
                            color="muted", size="sm")

                    ui.heading('dismissible=False — there is no way OUT any more',
                               level=3)
                    ui.text(
                        'Neither Escape nor a click on the veil closes '
                            'it: all that is left is what the box offers '
                            'itself. To be kept for the choice that cannot be'
                            ' postponed — a destructive confirmation — '
                            'because it is also the surest way to trap '
                            'somebody.',
                        color="muted", size="xs",
                    )
                    with ui.dialog(title="Supprimer ce projet ?",
                                   dismissible=False) as locked_dlg:
                        ui.text('This action cannot be undone.')
                        with ui.hstack(gap="sm"):
                            ui.button("Annuler", variant="outline",
                                      on_click=locked_dlg.close())
                            ui.button("Supprimer", color="error",
                                      on_click=locked_dlg.close())
                    ui.button("dismissible=False",
                              on_click=locked_dlg.open())

                    ui.heading("No title (close button only)", level=3)
                    with ui.dialog() as notitle_dlg:
                        ui.text("Just body content, no header.")
                    ui.button("No title",
                              on_click=notitle_dlg.open())

                    ui.heading("Very long title (60 chars)", level=3)
                    with ui.dialog(
                        title="A very long dialog title that may "
                              "wrap on narrow widths",
                    ) as longtitle_dlg:
                        ui.text("Body content.")
                    ui.button("Long title",
                              on_click=longtitle_dlg.open())

                    ui.heading("Long scrolling body", level=3)
                    with ui.dialog(title="Lots of text") as scroll_dlg:
                        for i in range(1, 21):
                            ui.text(f"Paragraph {i} — Lorem ipsum "
                                    f"dolor sit amet, consectetur "
                                    f"adipiscing elit.",
                                    color="muted")
                    ui.button("Scrolling body",
                              on_click=scroll_dlg.open())

                    ui.heading("Nested form inside the dialog",
                               level=3)
                    # ``value=binding`` → AUTONAME_FROM="value" derives
                    # ``name="email"`` from the binding's field_name.
                    # No manual ``name=`` — canonical Bretzel pattern.
                    nested_form_state = DialogFormDemo()
                    with ui.dialog(title="Subscribe") as form_dlg:
                        with ui.form():
                            with ui.vstack():
                                with ui.form_field(label="Email"):
                                    ui.input(value=nested_form_state.email, type="email")
                                with ui.hstack(justify="end"):
                                    ui.button("Submit", type="submit",
                                              color="primary")
                    ui.button("Open form dialog",
                              on_click=form_dlg.open())

                    ui.heading("HTML-special characters in title "
                               "(XSS escape)", level=3)
                    with ui.dialog(
                        title="<script>alert(1)</script>",
                    ) as xss_dlg:
                        ui.text("Framework escapes the title.")
                    ui.button("XSS title",
                              on_click=xss_dlg.open())

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Common dialog patterns.",
                            color="muted", size="sm")

                    ui.heading("Confirm-destructive (red action)",
                               level=3)
                    with ui.dialog(
                        title="Delete your account?",
                    ) as destroy_dlg:
                        ui.text(
                            "This is irreversible. All projects, "
                            "data, and shared access will be lost.",
                            color="muted",
                        )
                        with ui.hstack(justify="end", gap="sm"):
                            ui.button("Cancel", variant="ghost",
                                      on_click=destroy_dlg.close())
                            ui.button("Delete forever", color="error",
                                      on_click=destroy_dlg.close())
                    ui.button("Delete account", variant="outline",
                              color="error", icon_left="trash-2",
                              on_click=destroy_dlg.open())

                    ui.heading("Image preview (full-width)", level=3)
                    with ui.dialog(
                        title="Photo",
                        width="full",
                    ) as image_dlg:
                        ui.skeleton(width="100%", height="320px")
                    ui.button("Preview image",
                              on_click=image_dlg.open())

                    ui.heading("Setting tweaker (form + footer)",
                               level=3)
                    with ui.dialog(
                        title="Notification preferences",
                    ) as settings_dlg:
                        with ui.vstack():
                            ui.switch(label="Email",
                                      checked=True)
                            ui.switch(label="Slack")
                            ui.switch(label="SMS")
                        with ui.hstack(justify="end"):
                            ui.button("Save", color="primary",
                                      on_click=settings_dlg.close())
                    ui.button("Settings", icon_left="settings",
                              on_click=settings_dlg.open())

                    ui.heading(
                        "Per-row confirm — imperative API "
                        "(.open() / .close())",
                        level=3,
                    )
                    imperative_per_row()

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Panel emits ``role=\"dialog\"`` + "
                        "``aria-modal=\"true\"``. When ``title=`` "
                        "is set, ``aria-labelledby`` points at the "
                        "title id. The close × button carries an "
                        "explicit ``aria-label=\"Close\"``. Focus "
                        "lands on the first interactive child via "
                        "``$nextTick`` auto-focus — keyboard users "
                        "can immediately act.",
                        color="muted", size="sm",
                    )
                    with ui.dialog(
                        title="Keyboard test",
                    ) as a11y_dlg:
                        ui.text("Tab to cycle through. Press "
                                "Escape to close.",
                                color="muted")
                        with ui.form_field(label="First field"):
                            ui.input(placeholder="Auto-focused")
                    ui.button("A11y demo dialog", icon_left="keyboard",
                              on_click=a11y_dlg.open())

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
                        "Mirror of Dialog's ``BINDABLE_PROPS = "
                        "('open',)`` contract. The switch below is "
                        "bound to the SAME flag the dialog reads — "
                        "toggling it opens/closes the dialog with no "
                        "network round-trip, no ``.open()``/``.close()`` "
                        "call involved. Title / width / dismissible / "
                        "persistent stay design-time.",
                        color="muted", size="sm",
                    )
                    client = DialogClient(key="playground")
                    with ui.flex(justify="center", align="center"):
                        ui.switch(label="Open", checked=client.open)

                    ui.divider()

                    with ui.flex(justify="center"):
                        with ui.dialog(open=client.open,
                                       title="Client-bound dialog"):
                            ui.text(
                                "Bound to the switch above via "
                                "ClientBinding — close via ESC, "
                                "backdrop, or flipping the switch.",
                                color="muted",
                            )

                    ui.divider()

                    preview = ui.dialog(open=client.open,
                                        title="Client-bound dialog")
                    with preview:
                        ui.text("Body", color="muted")
                    emitted_html_block(
                        "Emitted HTML — bz-show reads the bound "
                        "open path directly ; the switch writes "
                        "through it, no round-trip.",
                        serialize_html(preview),
                    )

            # ── Card 9 — External controls — the 3 modes ────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes",
                               level=2)
                    ui.text(
                        "Same scenario (a button opens the dialog, an "
                        "inner button closes it) played three ways. "
                        "Pick the mode that fits your need : imperative "
                        "for purely-visual triggers, binding when "
                        "another component needs to read the open "
                        "state, both together when you want write-"
                        "through.",
                        color="muted", size="sm",
                    )

                    # ── Mode 1 — Imperative only (default style) ────
                    ui.heading(
                        "Mode 1 — Imperative only (default)",
                        level=3,
                    )
                    ui.text(
                        "No ClientState. The dialog owns its open "
                        "flag in client scope. ``.open()`` / "
                        "``.close()`` / ``.toggle()`` dispatch DOM "
                        "events caught by the dialog root. **Use "
                        "this by default for overlays — it's the "
                        "natural style for purely-visual state.**",
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="center", gap="md"):
                        with ui.dialog(title="Imperative") as m1:
                            ui.text("client-local, zero ClientState.",
                                    color="muted")
                            ui.button("Close",
                                      variant="ghost",
                                      on_click=m1.close())
                        ui.button("Open", on_click=m1.open())
                        ui.button("Toggle",
                                  variant="outline",
                                  on_click=m1.toggle())

                    ui.divider()

                    # ── Mode 2 — ClientBinding only ─────────────────
                    ui.heading("Mode 2 — ClientBinding only",
                               level=3)
                    ui.text(
                        "Use this when **another component needs to "
                        "read or react to the open state** — a switch "
                        "that mirrors it, a badge that shows when "
                        "it's open, server-side awareness on the "
                        "next render. The binding is the single "
                        "source of truth multi-composant.",
                        color="muted", size="sm",
                    )
                    bound = DialogClient(key="binding_only")
                    with ui.hstack(align="center", gap="md"):
                        ui.switch(checked=bound.open)
                        with ui.dialog(open=bound.open,
                                       title="Bound"):
                            ui.text("The switch above is the binding "
                                    "in action — it reads + writes "
                                    "the same flag this dialog reads.",
                                    color="muted")
                            ui.button("Close from inside",
                                      variant="ghost",
                                      on_click=bound.open.set(False))
                        ui.button("Open via binding.set(True)",
                                  on_click=bound.open.set(True))

                    ui.divider()

                    # ── Mode 3 — Both : write-through ───────────────
                    ui.heading(
                        "Mode 3 — Both (write-through)",
                        level=3,
                    )
                    ui.text(
                        'A binding supplied AND ``.open()`` called on the'
                            ' instance. The framework detects the binding and'
                            ' delegates to ``binding.set(True)`` — **the DOM '
                            'dispatch is not used**, the single source of '
                            'truth is preserved. The switch and the '
                            'imperative buttons converge on the same flag.',
                        color="muted", size="sm",
                    )
                    both = DialogClient(key="both")
                    with ui.hstack(align="center", gap="md"):
                        ui.switch(checked=both.open)
                        with ui.dialog(open=both.open,
                                       title="Both") as m3:
                            ui.text("Both paths converge on the "
                                    "binding.",
                                    color="muted")
                            ui.button("Close via dlg.close()",
                                      variant="ghost",
                                      on_click=m3.close())
                        ui.button("Open via dlg.open()",
                                  on_click=m3.open())
                        ui.button("Toggle via dlg.toggle()",
                                  variant="outline",
                                  on_click=m3.toggle())

                    ui.divider()

                    preview = ui.dialog(open=bound.open,
                                        title="Bound dialog")
                    with preview:
                        ui.text("Body")
                    emitted_html_block(
                        "Emitted HTML — Mode 2 (binding only) : "
                        "bz-show reads the bound path ; toggle / set "
                        "on the binding write back without a round-"
                        "trip.",
                        serialize_html(preview),
                    )

            # ── Card 10 — Client events ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text("Open / close events wired to client "
                            "expressions that push onto a "
                            "ClientState list. Zero network ; the "
                            "log below re-renders via bz-text on "
                            "every push.",
                            color="muted", size="sm")
                    cevents = DialogClientEvents()
                    with ui.flex(justify="center"):
                        with ui.dialog(
                            title="Client events demo",
                            on_open=cevents.log.push("open"),
                            on_close=cevents.log.push("close"),
                        ) as cevents_dlg:
                            ui.text("Close me to fire 'close' on "
                                    "the client log.",
                                    color="muted")
                        ui.button("Open client-event logger",
                                  on_click=cevents_dlg.open())

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive — no "
                                "refresh)", color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    ui.divider()

                    log_text = ClientExpression(
                        '($bz.state.DialogClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    preview = ui.dialog(
                        title="Client events demo",
                        on_open=cevents.log.push("open"),
                        on_close=cevents.log.push("close"),
                    )
                    with preview:
                        ui.text("Body")
                    emitted_html_block(
                        "Emitted HTML — @bz-opened / @bz-closed "
                        "listeners on the root ; client expressions "
                        "push the event name onto the bound list.",
                        serialize_html(preview),
                    )
