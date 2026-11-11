"""``/file-upload`` — drop files, or pick them from a compact button."""

from bretzel import refreshable, ui
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A dropzone or a compact button, tiles or chips, with type, size "
           "and count checked before anything leaves the browser.")


def product_photos() -> None:
    with ui.vstack(gap="xs", classes="w-full max-w-xl"):
        ui.file_upload(label="Product photos", multiple=True, max_files=6,
                       accept="image/*", max_size_mb=10)
        ui.text("PNG or JPG, up to 10 MB each. The first photo becomes the "
                "cover.", color="muted", size="sm")


def composer() -> None:
    with ui.card(padding="md", classes="w-full max-w-xl"), ui.form(), \
            ui.vstack(gap="sm"):
        ui.textarea(placeholder="Reply to Lumen Studio…", rows=3, size="sm")
        with ui.hstack(gap="sm", justify="between", align="start"):
            ui.file_upload(variant="button", list="chips", multiple=True,
                           max_files=5, paste=True, size="sm", label="Attach")
            ui.button("Send reply", type="button", icon_right="send", size="sm",
                      classes="shrink-0")


def contract_documents() -> None:
    with ui.grid(min_col="16rem", gap="md", classes="w-full"):
        with ui.form_field(label="Signed contract", required=True):
            ui.file_upload(list="chips", accept=".pdf", max_size_mb=5,
                           color="success", size="sm", label="Drop the PDF")
        with ui.form_field(label="Supporting documents",
                           hint="Up to 3 files, PDF or DOCX."):
            ui.file_upload(list="chips", multiple=True, max_files=3,
                           accept=[".pdf", ".docx"], size="sm",
                           label="Quotes, minutes…")
        with ui.form_field(label="Company logo",
                           hint="Uploads are paused during the migration."):
            ui.file_upload(variant="button", accept="image/*", disabled=True,
                           size="sm", label="Choose a logo")


class ImportResult(PageState):
    file_name: str = field(default="")
    rows: int = field(default=0)


def import_contacts(contacts=None) -> None:
    """``contacts`` is the file_upload's ``name=``: the upload arrives here."""
    if contacts is None or not hasattr(contacts, "read"):
        ui.notification("Drop a CSV file first.", color="warning")
        return
    text = contacts.file.read().decode("utf-8", errors="replace")
    result = ImportResult()
    result.file_name = contacts.filename
    result.rows = max(len(text.splitlines()) - 1, 0)


@refreshable
def import_summary() -> None:
    result = ImportResult()
    if result.file_name:
        ui.alert(f"{result.rows} contacts ready to import.",
                 title=result.file_name, color="success", icon="file-check")


def csv_import() -> None:
    with ui.card(padding="md", classes="w-full max-w-xl"), \
            ui.form(on_submit=import_contacts), ui.vstack(gap="md"):
        ui.heading("Import contacts", level=3, size="md")
        ui.file_upload(name="contacts", accept=".csv", max_files=1,
                       max_size_mb=2, list="chips",
                       label="Drop a CSV export from your CRM")
        with ui.hstack(justify="end"):
            ui.button("Import", type="submit", icon_left="upload")
        import_summary()


def page() -> None:
    page_header("file_upload", "File upload", SUMMARY)
    example("Product photos", product_photos,
            note="The default dropzone: drop or click, with a thumbnail tile "
                 "per image. accept, max_size_mb and max_files are checked "
                 "on the spot.")
    example("Attach to a message", composer,
            note="variant=\"button\" keeps the composer compact; list=\"chips\" "
                 "lines files up inline. paste=True turns a Ctrl+V of a "
                 "screenshot into an attachment.")
    example("Documents in a form", contract_documents,
            note="Chips in narrow columns, a colour and a size, and a "
                 "disabled picker.")
    example("Import a CSV", csv_import,
            uses=[ImportResult, import_contacts, import_summary],
            note="Inside a form, the file is posted with it: the handler "
                 "receives it by its name= and reads it.")
