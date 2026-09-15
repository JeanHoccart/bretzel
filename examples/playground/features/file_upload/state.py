"""``FileUpload`` test-bench state classes + axis constants."""

from __future__ import annotations

from bretzel.state import ClientState, PageState, field


VARIANTS = ("dropzone", "button")
COLORS = (
    "primary", "secondary", "success", "warning", "error", "info", "muted",
)
SIZES = ("xs", "sm", "md", "lg", "xl")


class FileUploadPlayground(PageState):
    """Drives the Server playground card."""

    # ── Component-public props ────────────────────────────────────
    variant:         str = field(default="dropzone")
    label:           str = field(default="")
    name:            str = field(default="")
    multiple:        str = field(default="off")
    accept:          str = field(default="")
    max_size_mb:     str = field(default="")
    max_files:       str = field(default="")
    color:           str = field(default="primary")
    size:            str = field(default="md")
    disabled:        str = field(default="off")
    required:        str = field(default="off")
    show_previews:   str = field(default="on")
    upload_url:      str = field(default="")  # async mode opt-in

    # ── Escape hatches (per playground-pattern.md § 4) ────────────
    classes:         str = field(default="")
    custom_id:       str = field(default="")
    aria_label:      str = field(default="")
    style:           str = field(default="")
    extra_attrs:     str = field(default="")

    # ── Universal modifiers ───────────────────────────────────────
    visible:         str = field(default="on")
    tooltip:         str = field(default="")

    # ── Server-events card ────────────────────────────────────────
    log:             list = field(default_factory=list)


class FileUploadClient(ClientState, persist="memory"):
    """Drives the Client playground + Client events cards.

    ``disabled`` is the only really useful binding to demo — the
    others (``multiple`` / ``accept``) work too but are rarer in
    practice (you usually know the upload's shape at design time).
    """

    is_disabled:     bool = field(default=False)
    client_log:      list = field(default_factory=list)
