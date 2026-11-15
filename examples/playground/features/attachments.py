"""``Attachments`` test bench — the list of files, and any button that fills it.

Nine cards, the 7-section gabarit (no slots). ``BINDABLE_PROPS =
("disabled",)`` — the Client playground; ``IMPERATIVE = ("pick",
"clear")`` — External controls; ``EVENTS = ("change", "upload_start",
"upload_complete", "upload_error", "remove")`` — Server and Client events.

Two kinds of files, one look: picked in the browser (``.pick()`` on any
button, a paste, a drop), and held by the server (``files=``, with a ×
when ``on_remove=`` is given). The « Joined at once » card is the Gmail
way: ``on_change`` outside any form carries the file to the server, which
keeps it and shows it back through ``files=``.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/attachments"

DISPLAYS = ("chips", "strip", "grid")
SIZES = ("xs", "sm", "md", "lg", "xl")
COLORS = ("primary", "secondary", "success", "warning", "error", "info", "muted")

#: A picture the server « holds », inline so the bench needs no file.
PICTURE = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' "
           "viewBox='0 0 160 112'><rect width='160' height='112' fill='%23c7d2fe'/>"
           "<circle cx='52' cy='44' r='16' fill='%236366f1'/>"
           "<path d='M0 112 L56 64 L96 96 L120 76 L160 112 Z' fill='%234f46e5'/></svg>")

#: What a mail received carries: the server knows them, nothing is picked.
RECEIVED = [
    {"name": "devis-2026-114.pdf", "size": 48213, "type": "application/pdf"},
    {"name": "plan-du-site.png", "size": 1_532_811, "type": "image/png", "href": PICTURE},
    {"name": "compte-rendu.docx", "size": 20_480,
     "type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
]


class AttachmentsPlayground(PageState):
    display:       str  = field(default="chips")
    name:          str  = field(default="")
    multiple:      bool = field(default=True)
    accept:        str  = field(default="")
    max_size_mb:   int  = field(default=0)
    max_files:     int  = field(default=0)
    paste:         bool = field(default=True)
    drop:          str  = field(default="self")
    held:          bool = field(default=True)
    show_previews: bool = field(default=True)
    upload_url:    str  = field(default="")
    disabled:      bool = field(default=False)
    required:      bool = field(default=False)
    color:         str  = field(default="primary")
    size:          str  = field(default="md")
    # Escape hatches.
    classes:       str  = field(default="")
    custom_id:     str  = field(default="")
    aria_label:    str  = field(default="")
    style:         str  = field(default="")
    extra_attrs:   str  = field(default="")
    # Universal modifiers.
    visible:       str  = field(default="on")
    tooltip:       str  = field(default="")


class AttachmentsEvents(PageState):
    log: list = field(default_factory=list)


class AttachmentsHeld(PageState):
    """What the server keeps — the files joined at once, then shown back."""

    files: list = field(default_factory=list)
    received: list = field(default_factory=lambda: [dict(f) for f in RECEIVED])
    a11y: list = field(default_factory=lambda: [dict(f) for f in RECEIVED[:2]])


class AttachmentsClient(ClientState, persist="memory"):
    """Mirror of Attachments' BINDABLE_PROPS."""

    is_disabled: bool = field(default=False)
    client_log:  list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
# Handlers
# ─────────────────────────────────────────────────────────────────


def as_list(value) -> list:
    if value is None or isinstance(value, str):
        return []
    return list(value) if isinstance(value, list) else [value]


def log(line: str) -> None:
    state = AttachmentsEvents()
    state.log = ([*state.log, line])[-12:]


def log_change(pieces=None) -> None:
    names = [f.filename for f in as_list(pieces)]
    log(f"change — the handler received {len(names)} file(s): {', '.join(names) or '—'}")


def log_upload_start() -> None:
    log("upload_start")


def log_upload_complete() -> None:
    log("upload_complete")


def log_upload_error() -> None:
    log("upload_error")


def log_remove(key: str) -> None:
    log(f"remove — {key}")


def clear_log() -> None:
    AttachmentsEvents().log = []


def server_changed(state: AttachmentsPlayground) -> None:
    pass


def join_at_once(pieces=None) -> None:
    """Outside any form: the file arrives the moment it is chosen. The
    server keeps what it needs (here its name and size) and the list shows
    it back through ``files=``."""
    held = AttachmentsHeld()
    kept = list(held.files)
    for upload in as_list(pieces):
        data = upload.file.read()
        kept.append({"name": upload.filename, "size": len(data),
                     "type": upload.content_type or "",
                     "key": f"{len(kept)}-{upload.filename}"})
    held.files = kept
    log(f"joined at once — {len(as_list(pieces))} file(s) kept by the server")


def drop_held(key: str) -> None:
    held = AttachmentsHeld()
    held.files = [f for f in held.files if f["key"] != key]


def drop_received(key: str) -> None:
    held = AttachmentsHeld()
    held.received = [f for f in held.received if f["name"] != key]


def drop_a11y(key: str) -> None:
    held = AttachmentsHeld()
    held.a11y = [f for f in held.a11y if f["name"] != key]


def restore_received() -> None:
    AttachmentsHeld().received = [dict(f) for f in RECEIVED]


def send_reply(pieces=None) -> None:
    names = [f.filename for f in as_list(pieces)]
    ui.notification(f"Sent with {len(names)} file(s): {', '.join(names) or 'none'}.",
                    color="success")


# ─────────────────────────────────────────────────────────────────
# Server playground
# ─────────────────────────────────────────────────────────────────


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        key, sep, value = raw.strip().partition("=")
        if sep:
            result[key.strip()] = value.strip()
    return result


def build_preview(state: AttachmentsPlayground):
    kwargs: dict = {
        "display": state.display, "multiple": state.multiple, "paste": state.paste,
        "show_previews": state.show_previews, "color": state.color, "size": state.size,
    }
    if state.drop:
        kwargs["drop"] = state.drop
    if state.held:
        kwargs["files"] = RECEIVED
    for key in ("name", "accept", "upload_url", "classes", "style", "tooltip"):
        if getattr(state, key):
            kwargs[key] = getattr(state, key)
    if state.max_size_mb:
        kwargs["max_size_mb"] = state.max_size_mb
    if state.max_files:
        kwargs["max_files"] = state.max_files
    if state.disabled:
        kwargs["disabled"] = True
    if state.required:
        kwargs["required"] = True
    if state.custom_id:
        kwargs["id"] = state.custom_id
    attrs = parse_extra_attrs(state.extra_attrs)
    if state.aria_label:
        attrs["aria-label"] = state.aria_label
    if attrs:
        kwargs["attrs"] = attrs
    if state.visible == "off":
        kwargs["visible"] = False
    return ui.attachments(**kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable
def server_panel() -> None:
    state = AttachmentsPlayground()
    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("display"):
            ui.select(value=state.display, options=[(d, d) for d in DISPLAYS],
                      on_change=server_changed)
        with control("drop (empty: none)"):
            ui.select(value=state.drop, options=[("", "None"), ("self", "self"),
                                                 ("form", "form")],
                      on_change=server_changed)
        with control("files= (three held by the server)"):
            ui.switch(checked=state.held, on_change=server_changed)
        with control("name (default 'files')"):
            ui.input(value=state.name, placeholder="files", on_change=server_changed)
        with control("accept"):
            ui.input(value=state.accept, placeholder="image/*,.pdf", on_change=server_changed)
        with control("max_size_mb (0 = none)"):
            ui.number_input(value=state.max_size_mb, on_change=server_changed)
        with control("max_files (0 = none)"):
            ui.number_input(value=state.max_files, on_change=server_changed)
        with control("upload_url (async mode)"):
            ui.input(value=state.upload_url, placeholder="/api/upload",
                     on_change=server_changed)
        with control("color"):
            ui.select(value=state.color, options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size (the ×)"):
            ui.select(value=state.size, options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("multiple"):
            ui.switch(checked=state.multiple, on_change=server_changed)
        with control("paste"):
            ui.switch(checked=state.paste, on_change=server_changed)
        with control("show_previews (pictures, in strip / grid)"):
            ui.switch(checked=state.show_previews, on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control("required"):
            ui.switch(checked=state.required, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="p-2", on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-pieces", on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="max-width: 30rem",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=2, placeholder="data-test=pieces",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"), ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()
    pieces = build_preview(state)
    # The button is the app's: switched off with the list, it says so.
    with ui.hstack(gap="sm", align="center"):
        ui.button("Join a file", icon_left="paperclip", variant="soft", size="sm",
                  disabled=state.disabled, on_click=pieces.pick())
        ui.button("Clear", variant="ghost", size="sm", disabled=state.disabled,
                  on_click=pieces.clear())
    ui.divider()
    emitted_html_block("Emitted HTML", serialize_html(build_preview(state)))


# ─────────────────────────────────────────────────────────────────
# Server events + the Gmail way
# ─────────────────────────────────────────────────────────────────


@refreshable
def joined_at_once() -> None:
    held = AttachmentsHeld()
    with ui.vstack(gap="sm", classes="w-full max-w-xl"):
        pieces = ui.attachments(name="pieces", multiple=True, max_size_mb=25,
                                files=held.files, on_change=join_at_once,
                                on_remove=drop_held, paste=True, drop="self")
        with ui.hstack():
            ui.button("Join a file", icon_left="paperclip", variant="soft", size="sm",
                      on_click=pieces.pick())
        ui.text(f"The server holds {len(held.files)} file(s).", color="muted", size="xs")


@refreshable
def received_mail() -> None:
    held = AttachmentsHeld()
    with ui.vstack(gap="sm", classes="w-full max-w-xl"):
        ui.attachments(files=held.received, display="strip", on_remove=drop_received)
        with ui.hstack():
            ui.button("Restore the three files", variant="ghost", size="xs",
                      on_click=restore_received, disabled=len(held.received) == 3)


@refreshable
def a11y_list() -> None:
    held = AttachmentsHeld()
    with ui.vstack(gap="sm"):
        pieces = ui.attachments(files=held.a11y, accept=".pdf", on_remove=drop_a11y)
        with ui.hstack():
            ui.button("Joindre", icon_left="paperclip", size="sm", variant="soft",
                      on_click=pieces.pick())


@refreshable
def events_panel() -> None:
    state = AttachmentsEvents()
    with ui.vstack(classes="w-full max-w-xl"):
        ui.text("change — picked files go to the handler (outside a form, then emptied)",
                color="muted", size="sm")
        pieces = ui.attachments(name="pieces", multiple=True, on_change=log_change)
        with ui.hstack():
            ui.button("Pick for change", icon_left="paperclip", size="sm", variant="soft",
                      on_click=pieces.pick())
        ui.text("upload_start / upload_complete — upload_url= mode", color="muted",
                size="sm")
        uploads = ui.attachments(name="async", upload_url="/_demo/upload",
                                 on_upload_start=log_upload_start,
                                 on_upload_complete=log_upload_complete)
        with ui.hstack():
            ui.button("Pick for upload_start / complete", icon_left="upload", size="sm",
                      variant="soft", on_click=uploads.pick())
        ui.text("upload_error — a route that answers 500 on purpose", color="muted",
                size="sm")
        failing = ui.attachments(name="failing", upload_url="/_demo/upload-fail",
                                 on_upload_error=log_upload_error)
        with ui.hstack():
            ui.button("Pick for upload_error", icon_left="upload", size="sm", variant="soft",
                      on_click=failing.pick())
        ui.text("remove — the × of a file the server holds", color="muted", size="sm")
        ui.attachments(files=RECEIVED[:1], on_remove=log_remove)

    ui.divider()
    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first)", color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs", on_click=clear_log,
                  disabled=not state.log)
    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log), 1):
                ui.text(f"{i}. {evt}", color="muted", size="sm", classes="font-mono")
    else:
        ui.text("(no events yet)", color="muted", size="sm")
    ui.divider()
    emitted_html_block(
        "Emitted HTML (representative — on_change outside a form: multipart, "
        "its own signed token)",
        serialize_html(ui.attachments(name="pieces", on_change=log_change)),
    )


# ─────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────


def page() -> None:
    client = AttachmentsClient()
    with ui.container():
        with ui.vstack():
            ui.heading("Attachments", level=1)
            ui.text(
                "The files joined to something, shown where you want. Any "
                "button fills the list with .pick() — a paperclip, a « Joindre » "
                "button, a menu entry. It takes no room while it is empty. "
                "files= shows the files the server holds, with the same look.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Three presentations, the same files (held by the "
                            "server, so they show without picking). Pick more "
                            "with the button beside each.", color="muted", size="sm")
                    for display in DISPLAYS:
                        ui.heading(f'display="{display}"', level=3)
                        pieces = ui.attachments(display=display, multiple=True,
                                                files=RECEIVED)
                        with ui.hstack():
                            ui.button("Join a file", icon_left="paperclip", variant="soft",
                                      size="sm", on_click=pieces.pick())

                    ui.heading("Any button picks — a paperclip, a button, a menu entry",
                               level=3)
                    pieces = ui.attachments(multiple=True, paste=True)
                    with ui.hstack(gap="sm", align="center"):
                        ui.icon_button("paperclip", variant="ghost", tooltip="Joindre",
                                       aria_label="Joindre", on_click=pieces.pick())
                        ui.button("Joindre", icon_left="paperclip", variant="outline",
                                  size="sm", on_click=pieces.pick())
                        with ui.dropdown(trigger=ui.button("Ajouter", icon_right="chevron-down",
                                                           size="sm", variant="soft")):
                            ui.dropdown_item("Depuis l'ordinateur", icon_left="monitor",
                                             on_click=pieces.pick())
                        ui.button("Tout retirer", variant="ghost", size="sm",
                                  on_click=pieces.clear())

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.heading("Empty: no room taken — the row below never moves",
                               level=3)
                    with ui.vstack(gap="sm", classes="rounded-box border border-dashed "
                                                         "border-text/20 p-2"):
                        empty = ui.attachments(multiple=True)
                        with ui.hstack(gap="sm", align="center"):
                            ui.button("Envoyer", icon_left="send", size="sm")
                            ui.icon_button("paperclip", variant="ghost", size="sm",
                                           aria_label="Joindre", on_click=empty.pick())
                    ui.heading("Limits — one PDF, 1 MB: the refusals show in the list",
                               level=3)
                    strict = ui.attachments(accept=".pdf", max_size_mb=1)
                    with ui.hstack():
                        ui.button("Pick (try a picture, or a big file)", size="sm",
                                  variant="soft", on_click=strict.pick())
                    ui.heading("max_files=2", level=3)
                    two = ui.attachments(multiple=True, max_files=2)
                    with ui.hstack():
                        ui.button("Pick up to two", size="sm", variant="soft",
                                  on_click=two.pick())
                    ui.heading("A long name, in a narrow column", level=3)
                    with ui.vstack(classes="w-48"):
                        ui.attachments(files=[{
                            "name": "un-nom-de-fichier-vraiment-tres-long-2026.pdf",
                            "size": 4096}])
                    ui.heading("disabled=True — dimmed, nothing answers; its button "
                               "is turned off with it", level=3)
                    off = ui.attachments(disabled=True, files=RECEIVED[:1])
                    with ui.hstack():
                        ui.button("Pick", size="sm", variant="soft", disabled=True,
                                  on_click=off.pick())

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("A reply: the list above the row, the paperclip beside "
                            "Envoyer, files dropped anywhere on the form or pasted "
                            "in the text. They leave with the form, then the list "
                            "empties.", color="muted", size="sm")
                    with ui.form(on_submit=send_reply):
                        with ui.vstack(gap="sm"):
                            ui.textarea(name="text", rows=3, placeholder="Votre réponse…")
                            pieces = ui.attachments(name="pieces", multiple=True,
                                                    max_size_mb=25, paste=True, drop="form")
                            with ui.hstack(gap="xs", align="center"):
                                ui.button("Envoyer", icon_left="send", size="sm",
                                          type="submit")
                                ui.icon_button("paperclip", variant="ghost", size="sm",
                                               tooltip="Joindre un fichier",
                                               aria_label="Joindre un fichier",
                                               on_click=pieces.pick())
                    ui.heading("Joined at once — the Gmail way", level=3)
                    ui.text("No form: on_change carries the file to the server the "
                            "moment it is chosen; the server keeps it and the list "
                            "shows it back through files=. The × asks the server.",
                            color="muted", size="sm")
                    joined_at_once()
                    ui.heading("A mail received — files= only, no form", level=3)
                    received_mail()

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text("The list is a list (role=list, « Attached files »); "
                            "each × says « Remove file »; the hidden input is out "
                            "of the tab order — the button that picks is the "
                            "focus stop. A refusal is announced (role=alert).",
                            color="muted", size="sm")
                    a11y_list()

            # ── Card 5 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    server_panel()

            # ── Card 6 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    events_panel()

            # ── Card 7 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text("disabled= bound to a ClientState: the switch turns the "
                            "picking off with no round trip.", color="muted", size="sm")
                    ui.switch(checked=client.is_disabled, label="disabled")
                    bound = ui.attachments(disabled=client.is_disabled, multiple=True)
                    with ui.hstack():
                        ui.button("Join a file", icon_left="paperclip", size="sm",
                                  variant="soft", disabled=client.is_disabled,
                                  on_click=bound.pick())
                    emitted_html_block("Emitted HTML",
                                       serialize_html(ui.attachments(
                                           disabled=client.is_disabled)))

            # ── Card 8 — External controls ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes", level=2)
                    ui.text(".pick() and .clear() are DOM commands (mode 1). No "
                            "binding carries the files, so modes 2 and 3 do not "
                            "apply: a FileList is not a state.", color="muted",
                            size="sm")
                    target = ui.attachments(multiple=True)
                    with ui.hstack(gap="sm"):
                        ui.button(".pick()", size="sm", on_click=target.pick())
                        ui.button(".clear()", size="sm", variant="outline",
                                  on_click=target.clear())
                    emitted_html_block("Emitted command", target.pick())

            # ── Card 9 — Client events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    listened = ui.attachments(
                        multiple=True, upload_url="/_demo/upload",
                        on_change=client.client_log.push("change"),
                        on_upload_start=client.client_log.push("upload_start"),
                        on_upload_complete=client.client_log.push("upload_complete"),
                        on_upload_error=client.client_log.push("upload_error"),
                    )
                    with ui.hstack():
                        ui.button("Join a file", icon_left="paperclip", size="sm",
                                  variant="soft", on_click=listened.pick())
                    ui.attachments(files=RECEIVED[:1],
                                   on_remove=client.client_log.push("remove"))
                    with ui.hstack():
                        ui.button("Clear the log", variant="ghost", size="xs",
                                  on_click=client.client_log.clear())
                    ui.text(ClientExpression(
                        f"({client.client_log.binding_path()} || []).join(' · ') "
                        "|| '(empty)'"), color="muted", size="sm", classes="font-mono")
