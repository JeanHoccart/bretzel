"""``ui.notification`` test bench.

Five visual cards : Reference / Edge cases / Composability / A11y /
Server playground. Notification is a fire-and-forget helper (not a
rendered Component) so there is NO Slots / Client / Events
infrastructure — the entire surface is fired from server handlers.
The Server playground exposes every prop as a control and fires
the toast with the current state.
"""

from bretzel import refreshable, ui
from bretzel.state import ClientState, PageState, field



PATH = "/notification"


VARIANTS  = ["info", "success", "warning", "error"]
POSITIONS = ["top-left", "top-center", "top-right",
             "bottom-left", "bottom-center", "bottom-right"]


# Drives the "After a form submit" demo in Composability. Field
# name ``title`` flows through AUTONAME_FROM="value" → form-data key
# is ``title`` automatically. No manual ``name="title"``.
class NotificationFormDemo(ClientState, persist="memory"):
    title: str = field(default="")


class NotificationPlayground(PageState):
    message:     str  = field(default="Notification fired.")
    variant:     str  = field(default="info")
    title:       str  = field(default="")
    icon:        str  = field(default="")
    duration_ms: int  = field(default=4000)
    position:    str  = field(default="top-right")
    dismissible: bool = field(default=True)


def server_changed(state: NotificationPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    pass


def fire_from_playground() -> None:
    state = NotificationPlayground()
    kwargs: dict = {
        "message": state.message,
        "variant": state.variant,
        "duration_ms": int(state.duration_ms or 4000),
        "position": state.position,
        "dismissible": state.dismissible,
    }
    if state.title:
        kwargs["title"] = state.title
    if state.icon:
        kwargs["icon"] = state.icon
    ui.notification(**kwargs)


# ── Per-variant fire handlers (used in Reference card) ─────────────
def fire_info()    -> None: ui.notification(message="Info notification fired.",    variant="info")
def fire_success() -> None: ui.notification(message="Success notification fired.", variant="success")
def fire_warning() -> None: ui.notification(message="Warning notification fired.", variant="warning")
def fire_error()   -> None: ui.notification(message="Error notification fired.",   variant="error")


def fire_title() -> None:
    ui.notification(message="Click to dismiss.", title="With title", variant="info")


def fire_icon() -> None:
    ui.notification(message="Custom icon — any Iconify name.",
                    variant="success", icon="rocket")


def fire_no_icon() -> None:
    # Opt out of the auto-icon entirely — clean banner without chrome.
    ui.notification(message="No icon — pass icon=False.",
                    variant="info", icon=False)


def fire_1s() -> None:
    ui.notification(message="Auto-dismiss in 1 second.",
                    variant="success", duration_ms=1000)


def fire_3s() -> None:
    ui.notification(message="Auto-dismiss in 3 seconds.",
                    variant="success", duration_ms=3000)


def fire_10s() -> None:
    ui.notification(message="Auto-dismiss in 10 seconds.",
                    variant="success", duration_ms=10_000)


def fire_persistent() -> None:
    ui.notification(message="Persistent — dismissible only by user.",
                    variant="warning", title="Stays open",
                    duration_ms=0, dismissible=True)


def fire_top_left()      -> None: ui.notification(message="Anchored top-left.",      variant="info", position="top-left")
def fire_top_center()    -> None: ui.notification(message="Anchored top-center.",    variant="info", position="top-center")
def fire_top_right()     -> None: ui.notification(message="Anchored top-right.",     variant="info", position="top-right")
def fire_bottom_left()   -> None: ui.notification(message="Anchored bottom-left.",   variant="info", position="bottom-left")
def fire_bottom_center() -> None: ui.notification(message="Anchored bottom-center.", variant="info", position="bottom-center")
def fire_bottom_right()  -> None: ui.notification(message="Anchored bottom-right.",  variant="info", position="bottom-right")


def fire_long() -> None:
    ui.notification(message="A very long notification message that may wrap "
                            "across several lines to demonstrate how the "
                            "toaster handles overflowing content.",
                    variant="info", title="Long body")


def fire_emoji() -> None:
    ui.notification(message="🚀 Ship — שלום — 中文", variant="success")


def fire_xss() -> None:
    ui.notification(message="<script>alert(1)</script>",
                    title="<script>alert('title')</script>",
                    variant="error")


def fire_five() -> None:
    ui.notification(message="Toast 1", variant="info")
    ui.notification(message="Toast 2", variant="success")
    ui.notification(message="Toast 3", variant="warning")
    ui.notification(message="Toast 4", variant="error")
    ui.notification(message="Toast 5", variant="info")


def submitted_form(**kwargs) -> None:
    if not kwargs:
        ui.notification(message="Form was empty.", variant="warning")
        return
    ui.notification(message=f"Saved : {kwargs}",
                    title="Form submitted",
                    variant="success")


def slow_save() -> None:
    ui.notification(message="Saving…", variant="info", duration_ms=1000)
    ui.notification(message="Saved.", variant="success", icon="check")


def hovered() -> None:
    ui.notification(message="Hovered !", variant="info", duration_ms=1500)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[NotificationPlayground])
def server_panel() -> None:
    state = NotificationPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("message"):
            ui.textarea(value=state.message, rows=2,
                        on_change=server_changed)
        with control("variant"):
            ui.select(value=state.variant,
                      options=[(v, v) for v in VARIANTS],
                      on_change=server_changed)
        with control("title (optional)"):
            ui.input(value=state.title,
                     placeholder="Heads up",
                     on_change=server_changed)
        with control("icon (Iconify name, optional)"):
            ui.input(value=state.icon,
                     placeholder="rocket / bell",
                     on_change=server_changed)
        with control("duration_ms (0 = persistent)"):
            ui.number_input(value=state.duration_ms,
                     on_change=server_changed)
        with control("position"):
            ui.select(value=state.position,
                      options=[(p, p) for p in POSITIONS],
                      on_change=server_changed)
        with control("dismissible"):
            ui.switch(checked=state.dismissible,
                      on_change=server_changed)

    ui.divider()

    with ui.flex(justify="center"):
        ui.button("Fire with the current state",
                  icon_left="bell",
                  color="primary",
                  on_click=fire_from_playground)

    ui.divider()

    ui.text(
        "Notifications are fire-and-forget — there is no live "
        "preview to render server-side. Click the button above "
        "and watch the toast appear in the corner.",
        color="muted", size="xs",
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Notification", level=1)
            ui.text(
                "Fire-and-forget toast — ``ui.notification(...)`` is "
                "called from server handlers (no rendered Component, "
                "no ``with`` block). The runtime drains the queue at "
                "end-of-action, auto-mounts the toaster DOM on first "
                "call, animates the toast in, dismisses it after "
                "``duration_ms``.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Click each button to fire a toast.",
                            color="muted", size="sm")

                    ui.heading("Variants", level=3)
                    ui.text(
                        "Four semantic variants — chrome (bg + border "
                        "+ text + auto-icon) lives in "
                        "``notification/theme.py``, injected into "
                        "the runtime at boot via "
                        "``window.$bz_theme``.",
                        color="muted", size="xs",
                    )
                    with ui.hstack(wrap=True):
                        ui.button("Info",    color="info",
                                  on_click=fire_info)
                        ui.button("Success", color="success",
                                  on_click=fire_success)
                        ui.button("Warning", color="warning",
                                  on_click=fire_warning)
                        ui.button("Error",   color="error",
                                  on_click=fire_error)

                    ui.heading("With title", level=3)
                    ui.button("Fire with title",
                              on_click=fire_title)

                    ui.heading("Icon", level=3)
                    ui.text(
                        "Each variant ships an auto-picked Iconify "
                        "glyph. Override with ``icon=\"…\"`` or opt "
                        "out entirely with ``icon=False``.",
                        color="muted", size="xs",
                    )
                    with ui.hstack(wrap=True):
                        ui.button("Custom rocket icon",
                                  on_click=fire_icon)
                        ui.button("No icon (icon=False)",
                                  variant="outline",
                                  on_click=fire_no_icon)

                    ui.heading("Duration", level=3)
                    with ui.hstack(wrap=True):
                        ui.button("1 second",
                                  on_click=fire_1s)
                        ui.button("3 seconds",
                                  on_click=fire_3s)
                        ui.button("10 seconds",
                                  on_click=fire_10s)
                        ui.button("Persistent (0)",
                                  variant="outline",
                                  color="warning",
                                  on_click=fire_persistent)

                    ui.heading("Position", level=3)
                    with ui.hstack(wrap=True):
                        ui.button("top-left",
                                  on_click=fire_top_left)
                        ui.button("top-center",
                                  on_click=fire_top_center)
                        ui.button("top-right",
                                  on_click=fire_top_right)
                        ui.button("bottom-left",
                                  on_click=fire_bottom_left)
                        ui.button("bottom-center",
                                  on_click=fire_bottom_center)
                        ui.button("bottom-right",
                                  on_click=fire_bottom_right)

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs.",
                            color="muted", size="sm")

                    ui.heading("Very long message", level=3)
                    ui.button("Fire long message", on_click=fire_long)

                    ui.heading("Emoji + multi-script", level=3)
                    ui.button("Fire mixed message",
                              on_click=fire_emoji)

                    ui.heading("HTML-special content (XSS escape)",
                               level=3)
                    ui.text(
                        "Framework escapes message + title — the "
                        "script renders as literal text instead of "
                        "executing.",
                        color="muted", size="xs",
                    )
                    ui.button("Fire XSS attempt",
                              variant="outline",
                              color="error",
                              on_click=fire_xss)

                    ui.heading("Spam (5 toasts at once)", level=3)
                    ui.text(
                        "The toaster stacks multiple toasts in the "
                        "same corner. Older toasts age out as new "
                        "ones arrive.",
                        color="muted", size="xs",
                    )
                    ui.button("Fire 5 toasts", on_click=fire_five)

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text(
                        "Notifications come from server handlers "
                        "anywhere a render context is active — "
                        "actions, refreshable bodies, post-submit "
                        "handlers.",
                        color="muted", size="sm",
                    )

                    ui.heading("After a form submit", level=3)
                    # ``value=binding`` → AUTONAME_FROM="value" derives
                    # ``name="title"`` from field_name. Submit POSTs
                    # the form-data with key "title" → handler's
                    # ``**kwargs`` receives ``{"title": "..."}``.
                    notif_form = NotificationFormDemo()
                    with ui.form(on_submit=submitted_form):
                        with ui.vstack():
                            with ui.form_field(label="Title"):
                                ui.input(value=notif_form.title, placeholder="A title")
                            ui.button("Save", type="submit",
                                      color="primary")

                    ui.heading("Inside a server callable", level=3)
                    ui.button("Save (fires two toasts)",
                              on_click=slow_save,
                              icon_left="save")

                    ui.heading("In response to client events", level=3)
                    ui.text(
                        "Server handlers can fire notifications "
                        "from any event handler.",
                        color="muted", size="xs",
                    )
                    ui.button("Hover me — fires a toast",
                              on_mouseenter=hovered)

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "The toaster DOM emits "
                        "``role=\"region\"`` + "
                        "``aria-live=\"polite\"`` so screen readers "
                        "announce new toasts as they appear. "
                        "Use ``error`` toasts sparingly — they "
                        "auto-pick a more urgent icon but still "
                        "use polite live regions (assertive would "
                        "interrupt the user, which is rarely "
                        "warranted for a fire-and-forget toast).",
                        color="muted", size="sm",
                    )
                    ui.button("Fire a11y demo toast",
                              icon_left="info",
                              on_click=fire_info)

            # ── Card 5 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every prop is wired to a control. Click "
                        "the Fire button to dispatch a toast with "
                        "the current state.",
                        color="muted", size="sm",
                    )
                    server_panel()
