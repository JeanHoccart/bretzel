"""``/file-upload`` — a dropzone, and the files dropped on it."""

from bretzel import refreshable, ui
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A dropzone and the list under it — tiles, chips or a grid — with type, size "
           "and count checked before anything leaves the browser.")


def product_photos() -> None:
    with ui.vstack(gap="xs", classes="w-full max-w-xl"):
        ui.file_upload(label="Product photos", multiple=True, max_files=6,
                       accept="image/*", max_size_mb=10)
        ui.text("PNG or JPG, up to 10 MB each. The first photo becomes the "
                "cover.", color="muted", size="sm")


def gallery() -> None:
    with ui.vstack(gap="xs", classes="w-full max-w-xl"):
        ui.file_upload(label="Moodboard", display="grid", multiple=True,
                       accept="image/*", paste=True)
        ui.text("Large tiles that wrap. Paste a screenshot with Ctrl+V.",
                color="muted", size="sm")


def contract_documents() -> None:
    with ui.grid(min_col="16rem", gap="md", classes="w-full"):
        with ui.form_field(label="Signed contract", required=True):
            ui.file_upload(display="chips", accept=".pdf", max_size_mb=5,
                           color="success", size="sm", label="Drop the PDF")
        with ui.form_field(label="Supporting documents",
                           hint="Up to 3 files, PDF or DOCX."):
            ui.file_upload(display="chips", multiple=True, max_files=3,
                           accept=[".pdf", ".docx"], size="sm",
                           label="Quotes, minutes…")
        with ui.form_field(label="Company logo",
                           hint="Uploads are paused during the migration."):
            ui.file_upload(display="chips", accept="image/*", disabled=True,
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
                       max_size_mb=2, display="chips",
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
    example("A gallery", gallery,
            note="display=\"grid\" shows large tiles that wrap. A compact "
                 "button that attaches is ui.attachments and any button with "
                 "on_click=pieces.pick().")
    example("Documents in a form", contract_documents,
            note="Chips in narrow columns, a colour and a size, and a "
                 "disabled picker.")
    example("Import a CSV", csv_import,
            uses=[ImportResult, import_contacts, import_summary],
            note="Inside a form, the file is posted with it: the handler "
                 "receives it by its name= and reads it.")
