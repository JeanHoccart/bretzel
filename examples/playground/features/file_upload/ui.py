"""``FileUpload`` test bench.

Eight visual cards (no slots → skip card 2) : Reference / Edge cases /
Composability / A11y / Server playground / Server events / Client
playground / Client events. FileUpload's reactive surface :
``BINDABLE_PROPS = ("disabled", "multiple", "accept")`` ;
``EVENTS = ("change", "upload_start", "upload_complete",
"upload_error", "focus", "blur")``.

Two variants : ``dropzone`` (default, large dashed area) and
``button`` (compact inline trigger). State + behaviour delegated to
``$bz.fileUpload.makeScope({...opts})`` factory in
``bretzel/runtime/_src/08_file_upload.js``.

Two upload modes : form (hidden ``<input type="file">``, submitted
with the parent form) and async (``upload_url=`` opt-in, XHR per
file with progress events). Image previews via
``URL.createObjectURL`` for ``image/*`` files.
"""

from __future__ import annotations

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression

from examples.playground.features.inspection import emitted_html_block
from examples.playground.features.file_upload.state import (
    COLORS,
    FileUploadClient,
    FileUploadPlayground,
    SIZES,
    VARIANTS,
)
from examples.playground.features.file_upload.logic import (
    clear_log,
    log_blur,
    log_change,
    log_focus,
    log_upload_complete,
    log_upload_error,
    log_upload_start,
    server_changed,
)


PATH = "/file_upload"


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: FileUploadPlayground):
    kwargs: dict = {
        "variant": state.variant,
        "color": state.color,
        "size": state.size,
        "multiple": state.multiple == "on",
        "show_previews": state.show_previews == "on",
    }
    if state.label:
        kwargs["label"] = state.label
    if state.name:
        kwargs["name"] = state.name
    if state.accept:
        kwargs["accept"] = state.accept
    if state.max_size_mb:
        try:
            kwargs["max_size_mb"] = float(state.max_size_mb)
        except ValueError:
            pass
    if state.max_files:
        try:
            kwargs["max_files"] = int(state.max_files)
        except ValueError:
            pass
    if state.upload_url:
        kwargs["upload_url"] = state.upload_url
    if state.disabled == "on":
        kwargs["disabled"] = True
    if state.required == "on":
        kwargs["required"] = True
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
    return ui.file_upload(**kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


# ─────────────────────────────────────────────────────────────────
# Refreshable panels
# ─────────────────────────────────────────────────────────────────


@refreshable(deps=[FileUploadPlayground])
def server_panel() -> None:
    state = FileUploadPlayground()
    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
        with control("variant"):
            ui.select(value=state.variant,
                      options=[(v, v) for v in VARIANTS],
                      on_change=server_changed)
        with control("label"):
            ui.input(value=state.label,
                     placeholder="(use default)",
                     on_change=server_changed)
        with control("name (default 'files')"):
            ui.input(value=state.name, placeholder="files",
                     on_change=server_changed)
        with control("color (7 paliers)"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size (xs/sm/md/lg/xl)"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("multiple"):
            ui.select(value=state.multiple,
                      options=[("off", "off"), ("on", "on")],
                      on_change=server_changed)
        with control("accept (MIME / extension list)"):
            ui.input(value=state.accept,
                     placeholder="image/*,.pdf",
                     on_change=server_changed)
        with control("max_size_mb"):
            ui.input(value=state.max_size_mb,
                     placeholder="5",
                     on_change=server_changed)
        with control("max_files (multi-only)"):
            ui.input(value=state.max_files,
                     placeholder="4",
                     on_change=server_changed)
        with control("disabled"):
            ui.select(value=state.disabled,
                      options=[("off", "off"), ("on", "on")],
                      on_change=server_changed)
        with control("required"):
            ui.select(value=state.required,
                      options=[("off", "off"), ("on", "on")],
                      on_change=server_changed)
        with control("show_previews (image thumbnails)"):
            ui.select(value=state.show_previews,
                      options=[("on", "on (default)"), ("off", "off")],
                      on_change=server_changed)
        with control("upload_url (async mode opt-in)"):
            ui.input(value=state.upload_url,
                     placeholder="/api/upload",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="ring-2 ring-offset-2",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id,
                     placeholder="my-upload",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Attach a document",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="max-width: 32rem",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=upload",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Drop a CSV here",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()
    with ui.flex(justify="center", align="start"):
        build_preview(state)
    ui.divider()
    emitted_html_block(
        "Emitted HTML (the wrapper carries the bz-data factory scope ; "
        "the hidden native input is the form-data carrier)",
        serialize_html(build_preview(state)),
    )


@refreshable(deps=[FileUploadPlayground])
def events_panel() -> None:
    state = FileUploadPlayground()
    with ui.vstack(gap="sm"):
        with ui.hstack(gap="sm"):
            ui.button("Clear log", on_click=clear_log,
                      variant="ghost", size="sm")
        if not state.log:
            ui.text("No events yet — drop or pick files above.",
                    color="muted", size="sm")
        else:
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"#{i}  {evt}", size="sm", color="muted")


# ─────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("FileUpload", level=1)
            ui.text(
                "Dropzone or compact-button file picker. Drop OR click "
                "to browse, multi-file with per-card list, image "
                "thumbnails via ``URL.createObjectURL``, validation "
                "(``accept`` filter + ``max_size_mb`` + ``max_files``), "
                "and an opt-in async upload mode (``upload_url=``) "
                "with per-file XHR progress. State + behaviour live in "
                "``$bz.fileUpload.makeScope({...opts})`` "
                "(``bretzel/runtime/_src/08_file_upload.js``) ; the "
                "Python component just renders the markup. "
                "``BINDABLE_PROPS = (disabled, multiple, accept)`` ; "
                "``EVENTS = (change, upload_start, upload_complete, "
                "upload_error, focus, blur)``.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text(
                        "Visual scan of every prop. Each axis demoed "
                        "inline so the Tailwind scanner compiles "
                        "every class the Server playground might swap "
                        "to.",
                        color="muted", size="sm",
                    )

                    ui.heading("variant (dropzone / button)", level=3)
                    with ui.flex(wrap=True, gap="md", align="start"):
                        with ui.vstack(gap="xs", align="start"):
                            ui.text("dropzone (default)",
                                    color="muted", size="xs")
                            ui.file_upload()
                        with ui.vstack(gap="xs", align="start"):
                            ui.text("button (compact inline)",
                                    color="muted", size="xs")
                            ui.file_upload(variant="button")

                    ui.heading("list (tiles / chips)", level=3)
                    ui.text('An axis INDEPENDENT of variant=: this one dresses '
                        'the list of dropped files, not the trigger. Drop a '
                        'file in each to see the difference.',
                            color="muted", size="xs")
                    with ui.flex(wrap=True, gap="md", align="start"):
                        with ui.vstack(gap="xs", align="start"):
                            ui.text("tiles (defaut) — vignette, taille, "
                                    "x en badge de coin",
                                    color="muted", size="xs")
                            ui.file_upload(multiple=True)
                        with ui.vstack(gap="xs", align="start"):
                            ui.text('chips — icon, name, inline x, wrapping onto '
                                'several lines',
                                    color="muted", size="xs")
                            ui.file_upload(multiple=True, list="chips")
                    ui.text('The composer shape: a compact trigger and pills '
                        'under the field.',
                            color="muted", size="xs")
                    ui.file_upload(variant="button", multiple=True,
                                   list="chips", label="Joindre")

                    ui.heading("color (7 paliers)", level=3)
                    with ui.flex(wrap=True, gap="md", align="start"):
                        for c in COLORS:
                            with ui.vstack(gap="xs", align="center"):
                                ui.text(c, color="muted", size="xs")
                                ui.file_upload(
                                    variant="button", color=c,
                                    label=c,
                                )

                    ui.heading("size (xs/sm/md/lg/xl) — dropzone",
                               level=3)
                    ui.text(
                        "Each palier scales padding + icon size + "
                        "font weight, mirror of Input / Button / "
                        "Slider scaling.",
                        color="muted", size="xs",
                    )
                    with ui.flex(wrap=True, gap="md", align="start"):
                        for s in SIZES:
                            with ui.vstack(gap="xs", align="start"):
                                ui.text(s, color="muted", size="xs")
                                ui.file_upload(size=s)

                    ui.heading("size (xs/sm/md/lg/xl) — button",
                               level=3)
                    with ui.flex(wrap=True, gap="md", align="start"):
                        for s in SIZES:
                            with ui.vstack(gap="xs", align="start"):
                                ui.text(s, color="muted", size="xs")
                                ui.file_upload(
                                    variant="button", size=s, label=s,
                                )

                    ui.heading("multiple + max_files", level=3)
                    with ui.flex(wrap=True, gap="md", align="start"):
                        with ui.vstack(gap="xs", align="start"):
                            ui.text("single (default)",
                                    color="muted", size="xs")
                            ui.file_upload()
                        with ui.vstack(gap="xs", align="start"):
                            ui.text("multiple",
                                    color="muted", size="xs")
                            ui.file_upload(multiple=True)
                        with ui.vstack(gap="xs", align="start"):
                            ui.text("multiple, max 4 files",
                                    color="muted", size="xs")
                            ui.file_upload(multiple=True, max_files=4)

                    ui.heading("accept (filter MIME / extension)",
                               level=3)
                    ui.text(
                        "``accept=`` accepts either a comma string "
                        "(``\"image/*,.pdf\"``) or a list of tokens "
                        "(``[\"image/*\", \".pdf\"]``). The hint "
                        "renders in the dropzone subtitle.",
                        color="muted", size="xs",
                    )
                    with ui.flex(wrap=True, gap="md", align="start"):
                        with ui.vstack(gap="xs", align="start"):
                            ui.text("images only",
                                    color="muted", size="xs")
                            ui.file_upload(accept="image/*")
                        with ui.vstack(gap="xs", align="start"):
                            ui.text("PDF only",
                                    color="muted", size="xs")
                            ui.file_upload(accept=".pdf")
                        with ui.vstack(gap="xs", align="start"):
                            ui.text("images + PDF (list)",
                                    color="muted", size="xs")
                            ui.file_upload(
                                accept=["image/*", ".pdf"], multiple=True,
                            )

                    ui.heading("max_size_mb (per-file cap)", level=3)
                    with ui.flex(justify="start"):
                        ui.file_upload(max_size_mb=2, multiple=True)

                    ui.heading("disabled (whole picker)", level=3)
                    with ui.flex(wrap=True, gap="md", align="start"):
                        with ui.vstack(gap="xs", align="start"):
                            ui.text("dropzone disabled",
                                    color="muted", size="xs")
                            ui.file_upload(disabled=True)
                        with ui.vstack(gap="xs", align="start"):
                            ui.text("button disabled",
                                    color="muted", size="xs")
                            ui.file_upload(
                                variant="button", disabled=True,
                            )

                    ui.heading("required", level=3)
                    with ui.flex(justify="start"):
                        ui.file_upload(required=True)

                    ui.heading("upload_url (async mode opt-in)", level=3)
                    ui.text(
                        "Switches to XHR-per-file async mode instead "
                        "of native form submission.",
                        color="muted", size="xs",
                    )
                    with ui.flex(justify="start"):
                        ui.file_upload(upload_url="/_demo/upload")

                    ui.heading("Custom label", level=3)
                    with ui.flex(wrap=True, gap="md", align="start"):
                        with ui.vstack(gap="xs", align="start"):
                            ui.text("dropzone custom label",
                                    color="muted", size="xs")
                            ui.file_upload(
                                label="Drop your CSV here",
                                accept=".csv",
                            )
                        with ui.vstack(gap="xs", align="start"):
                            ui.text("button custom label",
                                    color="muted", size="xs")
                            ui.file_upload(
                                variant="button",
                                label="Attach a file",
                            )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Pathological inputs.",
                            color="muted", size="sm")

                    ui.heading("Tiny max_size_mb (rejects most files)",
                               level=3)
                    ui.text("``max_size_mb=0.01`` ≈ 10 KB ceiling — "
                            "try dropping anything bigger, the error "
                            "panel flashes.",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.file_upload(max_size_mb=0.01)

                    ui.heading("Single-mode + drop multiple files",
                               level=3)
                    ui.text(
                        "Drop two files on this dropzone — only the "
                        "first is accepted, the error panel notes the "
                        "rejection.",
                        color="muted", size="xs",
                    )
                    with ui.flex(justify="start"):
                        ui.file_upload()

                    ui.heading("max_files=1 in multiple mode", level=3)
                    ui.text("Functionally equivalent to single mode but "
                            "keeps the multi-file storyboard wiring.",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.file_upload(multiple=True, max_files=1)

                    ui.heading("Very restrictive accept (.xyz)",
                               level=3)
                    ui.text("Custom extension — most files rejected.",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.file_upload(accept=".xyz")

                    ui.heading("show_previews=False (icon-only)",
                               level=3)
                    ui.text("Disables ``URL.createObjectURL`` calls — "
                            "image files render with the generic file "
                            "icon. Useful when uploads are large or "
                            "sensitive.",
                            color="muted", size="xs")
                    with ui.flex(justify="start"):
                        ui.file_upload(
                            accept="image/*", multiple=True,
                            show_previews=False,
                        )

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text(
                        "FileUpload inside common containers. The "
                        "file-list strip wraps below the trigger in "
                        "the natural flow (no popover, nothing to "
                        "escape).",
                        color="muted", size="sm",
                    )

                    ui.heading("Inside ui.card", level=3)
                    with ui.card():
                        with ui.vstack(gap="sm"):
                            ui.text("Resume", color="muted", size="sm")
                            ui.file_upload(
                                accept=".pdf,.doc,.docx",
                                max_size_mb=10,
                            )

                    ui.heading("Inside ui.form (with hidden input)",
                               level=3)
                    ui.text(
                        "Form-data carrier rides the hidden "
                        "``<input type=\"file\">``. The browser POSTs "
                        "all picked files as multipart on submit. "
                        "Pass ``name=`` to control the form field "
                        "(default ``files``).",
                        color="muted", size="xs",
                    )
                    with ui.form():
                        with ui.vstack(gap="md"):
                            ui.file_upload(
                                name="attachments",
                                multiple=True,
                                accept="image/*,.pdf",
                                max_size_mb=5,
                            )
                            with ui.hstack(gap="sm"):
                                ui.button("Submit", type="submit")
                                ui.button("Reset", type="reset",
                                          variant="outline")

                    ui.heading("Inside ui.dialog (modal upload)",
                               level=3)
                    upload_dialog = ui.dialog(
                        title="Upload files", width="md",
                    )
                    with upload_dialog:
                        with ui.vstack(gap="md"):
                            ui.text("Drop or pick up to 4 files :",
                                    color="muted", size="sm")
                            ui.file_upload(
                                multiple=True, max_files=4,
                            )
                    ui.button("Open upload modal",
                              icon_left="upload",
                              variant="outline",
                              on_click=upload_dialog.open())

                    ui.heading("Side-by-side (button + dropzone)",
                               level=3)
                    ui.text("Common in detail pages : a primary "
                            "dropzone + a compact button for quick "
                            "attachments.",
                            color="muted", size="xs")
                    with ui.hstack(gap="md", align="start"):
                        with ui.vstack(gap="xs", align="start"):
                            ui.text("Drag area",
                                    color="muted", size="xs")
                            ui.file_upload(multiple=True)
                        with ui.vstack(gap="xs", align="start"):
                            ui.text("Quick browse",
                                    color="muted", size="xs")
                            ui.file_upload(
                                variant="button",
                                label="Attach",
                            )

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "The wrapper is the focus host : "
                        "``tabindex=\"0\"`` (or ``\"-1\"`` when "
                        "disabled), ``role=\"button\"``, "
                        "``aria-label=`` defaults to the picker's "
                        "label. Enter / Space open the system file "
                        "picker (so keyboard users don't need to "
                        "tab through to the sr-only native input). "
                        "The error panel has ``role=\"alert\"`` so "
                        "screen readers announce validation messages "
                        "as they appear. Each per-file remove button "
                        "has ``aria-label=\"Remove file\"`` ; the "
                        "progress bar (async mode) has "
                        "``role=\"progressbar\"`` + reactive "
                        "``:aria-valuenow``.",
                        color="muted", size="sm",
                    )
                    with ui.flex(justify="start"):
                        ui.file_upload(accept="image/*", multiple=True)

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Toggle every axis ; live preview + emitted "
                        "HTML refresh on every change.",
                        color="muted", size="sm",
                    )
                    server_panel()

            # ── Card 7 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    ui.text(
                        "``change`` fires when the file list mutates "
                        "(picked / dropped / removed). ``focus`` / "
                        "``blur`` relay the focusable wrapper. In "
                        "async mode (``upload_url=``), ``upload_start`` "
                        "fires per file on request kickoff and "
                        "``upload_error`` fires on any non-2xx "
                        "response — both genuinely fire below against "
                        "the placeholder URL, since this playground "
                        "ships no real upload backend. "
                        "``upload_complete`` needs an actual 2xx "
                        "response, so it won't fire here — a "
                        "documented gap, not a wiring bug (no "
                        "``upload_progress`` server hop either — that "
                        "would melt the wire). Drop files to populate "
                        "the log.",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "One instance per event — a single FileUpload "
                        "carries only one server ``hx-post``.",
                        color="muted", size="xs",
                    )
                    with ui.flex(wrap=True, gap="md"):
                        ui.file_upload(variant="button", label="change",
                                       multiple=True,
                                       on_change=log_change)
                        ui.file_upload(variant="button",
                                       label="upload_start",
                                       upload_url="/_demo/upload",
                                       on_upload_start=log_upload_start)
                        ui.file_upload(variant="button",
                                       label="upload_complete",
                                       upload_url="/_demo/upload",
                                       on_upload_complete=log_upload_complete)
                        # A target answering 500 on purpose:
                        # ``upload_error`` only fires on a non-2xx, so the
                        # target that succeeds would make it
                        # undemonstrable.
                        ui.file_upload(variant="button",
                                       label="upload_error",
                                       upload_url="/_demo/upload-fail",
                                       on_upload_error=log_upload_error)
                        ui.file_upload(variant="button", label="focus",
                                       on_focus=log_focus)
                        ui.file_upload(variant="button", label="blur",
                                       on_blur=log_blur)
                    ui.divider()
                    events_panel()
                    ui.divider()
                    emitted_html_block(
                        "Emitted HTML (representative — change event)",
                        serialize_html(ui.file_upload(
                            on_change=log_change,
                        )),
                    )

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "``disabled`` accepts ``ClientBinding`` — the "
                        "runtime flips it live without a network "
                        "round-trip. The switch below mutates "
                        "``ClientState`` ; the picker reflects the "
                        "change instantly. ``multiple`` / ``accept`` "
                        "are design-time (they change the picker's "
                        "structure, not just an attribute).",
                        color="muted", size="sm",
                    )
                    client = FileUploadClient()
                    with ui.vstack(gap="md"):
                        with ui.hstack(gap="md", align="center"):
                            ui.switch(
                                label="Disabled",
                                checked=client.is_disabled,
                            )
                        ui.file_upload(
                            disabled=client.is_disabled,
                            multiple=True,
                            accept="image/*,.pdf",
                        )
                    ui.divider()
                    emitted_html_block(
                        "Emitted HTML — note the ``bz-attr:disabled`` "
                        "propagating the binding's reactive path to the "
                        "native input.",
                        serialize_html(ui.file_upload(
                            disabled=client.is_disabled,
                        )),
                    )

            # ── Card 9 — Client events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text(
                        "Bind a ``ClientState.client_log`` array to "
                        "the events — the runtime pushes without a server "
                        "round-trip. Pure-client validation + UI "
                        "reactions live here. ``upload_start`` / "
                        "``upload_error`` genuinely fire against the "
                        "placeholder ``upload_url=`` below (any "
                        "non-2xx response counts as an error) ; "
                        "``upload_complete`` needs a real backend this "
                        "playground doesn't ship, so it stays silent.",
                        color="muted", size="sm",
                    )
                    cevents = FileUploadClient()
                    with ui.flex(justify="start"):
                        ui.file_upload(
                            multiple=True,
                            upload_url="/_demo/upload",
                            on_change=cevents.client_log.push("change"),
                            on_focus=cevents.client_log.push("focus"),
                            on_blur=cevents.client_log.push("blur"),
                            on_upload_start=cevents.client_log.push(
                                "upload_start"),
                            on_upload_complete=cevents.client_log.push(
                                "upload_complete"),
                            on_upload_error=cevents.client_log.push(
                                "upload_error"),
                        )
                    ui.divider()
                    with ui.hstack(gap="sm"):
                        ui.button("Clear",
                                  on_click=cevents.client_log.clear(),
                                  variant="ghost", size="sm")
                    _log_path = cevents.client_log.binding_path()
                    with ui.hstack(gap="sm", align="center"):
                        ui.text("Log size:", color="muted", size="sm")
                        ui.text(cevents.client_log.length(),
                                size="sm", weight="medium")
                    ui.text(
                        ClientExpression(
                            f"({_log_path} || []).join(' | ') "
                            f"|| '(empty)'"
                        ),
                        size="sm", color="muted",
                    )
                    ui.divider()
                    emitted_html_block(
                        "Emitted HTML — pure client-side "
                        "``@change=\"...client_log.push(...)\"``, no "
                        "``hx-post`` round-trip.",
                        serialize_html(ui.file_upload(
                            on_change=cevents.client_log.push("change"),
                        )),
                    )
