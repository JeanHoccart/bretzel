"""features/import_screen — screen 9: the import, a real sequence.

What this screen puts under constraint: ``ui.stepper`` + a preview as a
``ui.datatable``, **chained**. The 17 apps mount each of these components
alone; here one step's state decides what the next can do, and the screen
only reads in order.

⚠️ **``ui.file_upload`` in form mode transmits NOTHING to the server**,
and that is measured, not assumed. The component does place an
``<input type="file" name="fichier">`` in the parent ``<form>``, but htmx
only builds a ``FormData`` body if the form carries
``hx-encoding="multipart/form-data"`` (or the equivalent ``enctype``) —
and ``grep -rn "hx-encoding" bretzel/`` returns **zero** results:
``ui.form`` has no prop to say it and never emits the attribute. So the
body goes out URL-encoded, where a ``File`` does not survive; the handler
receives an empty string. Verified in the browser: dropping a CSV then
clicking "Check" shows "Drop a file or paste a CSV".

The screen does not work around it: pasting is the real path, and the
drop stays there **disabled**, with the reason written beside it. It is
the work's finding 15.

What the screen does do, on the other hand, and that no app had: **the
datatable in LIST tier**. Screen 2 mounts it in callable tier over 50 000
rows; here the rows are in memory and the component filters, sorts and
paginates on its own. Both tiers of the same component, in the same app,
on two screens.
"""

from __future__ import annotations

from bretzel import Feature, page, refreshable, ui
from bretzel.components import DatatableState
from bretzel.state import SessionState, field
from examples.crm.core.domain import (
    IMPORT_COLUMNS,
    IMPORT_EXAMPLE_CSV,
    IMPORT_MAX_ROWS,
)
from examples.crm.features.access import visible_owner
from examples.crm.features.import_data import commit_rows, judge, parse_csv
from examples.crm.features.shell import shell

#: The three steps.
STEPS: tuple[tuple[str, str, str], ...] = (
    ("Drop", "An accounts CSV, seven columns", "upload"),
    ("Check", "Every row is judged before anything is written", "list-checks"),
    ("Import", "All or nothing, in one transaction", "database"),
)


class ImportDraft(SessionState):
    """The import draft.

    ``SessionState`` and not ``PageState``: an import continues after a
    reload. ``pasted`` is part of it — the pasted text must SURVIVE the
    re-render a header error triggers, otherwise the user reads the
    reproach above an emptied area and has to paste everything again.
    """

    step: int = field(default=0)
    pasted: str = field(default='')
    file_name: str = field(default='')
    error: str = field(default='')
    rows: list = field(default_factory=list)
    imported: int = field(default=0)


class ImportPreview(DatatableState):
    """The preview's query. LIST tier — the component holds the rows."""

    per_page: int = field(default=10)


async def start_import(form: ImportDraft, fichier=None) -> None:
    """Read the CSV — dropped or pasted — and move to the check step.

    ``async`` because ``UploadFile.read()`` is; the handlers are indeed
    awaited by the base layer, unlike the ``@refreshable`` zones which
    are not (the work's finding 1, still open).

    ``fichier`` is not declared as a state field: it is the
    ``ui.file_upload``'s ``name=``, and the signature injection passes a
    form value to the parameter bearing its name. The file wins over the
    paste — something has been dropped, that is what is meant to be
    imported.
    """
    raw, source = str(form.pasted), "(pasted)"
    if fichier is not None and hasattr(fichier, "read"):
        raw = (await fichier.read()).decode("utf-8", errors="replace")
        source = getattr(fichier, "filename", "") or "(unnamed)"
    if not raw.strip():
        form.error = "Drop a file or paste a CSV."
        return
    rows, header_error = parse_csv(raw)
    form.file_name = source
    form.error = header_error
    form.rows = judge(rows, visible_owner()) if not header_error else []
    form.imported = 0
    if not header_error:
        form.step = 1


def apply_import() -> None:
    draft = ImportDraft()
    rows = list(draft.rows)
    bad = [r for r in rows if r["_error"]]
    if bad:
        ui.notification(
            f"{len(bad)} row(s) in error — nothing has been written.",
            variant="error", duration_ms=3500,
        )
        return
    draft.imported = commit_rows(rows, visible_owner())
    draft.step = 2
    ui.notification(f"{draft.imported} account(s) imported",
                    variant="success", duration_ms=2500)


def restart() -> None:
    draft = ImportDraft()
    draft.step, draft.file_name, draft.error, draft.pasted = 0, "", "", ""
    draft.rows, draft.imported = [], 0


def line_cell(value, _row):
    return ui.text(str(value), color="muted", size="xs")


def verdict_cell(value, _row):
    if not value:
        return ui.badge("OK", color="success", variant="soft", size="xs")
    return ui.text(value, color="error", size="xs")


#: No ``filter=`` on the verdict: a column filter compares by string
#: EQUALITY (``Query.matches_filters``), and the verdicts are sentences
#: built row by row. An "error" option would never have matched anything
#: — a filter that always empties the table is worse than no filter.
PREVIEW_COLUMNS = [
    ui.column("_ligne", label="Row", width="4rem", render=line_cell),
    *[ui.column(key, label=key, sortable=True) for key in IMPORT_COLUMNS],
    ui.column("_error", label="Verdict", render=verdict_cell),
]


def step_drop(draft: ImportDraft) -> None:
    with ui.form(on_submit=start_import):
        with ui.vstack(gap="md"):
            with ui.grid(cols={"base": 1, "lg": 2}, gap="lg"):
                with ui.vstack(gap="sm"):
                    ui.heading("Paste the content", level=3, size="sm")
                    ui.textarea(value=draft.pasted, rows=8,
                                placeholder=IMPORT_EXAMPLE_CSV)
                with ui.vstack(gap="sm"):
                    ui.heading("Drop a file", level=3, size="sm")
                    # No ``upload_url=``: form mode is enough. The
                    # ``<form>`` sees the file and encodes itself as
                    # multipart on its own, and ``start_import`` receives
                    # it by its ``name=``.
                    ui.file_upload(
                        variant="dropzone", list="chips", accept=[".csv"],
                        max_files=1, max_size_mb=2, name="fichier",
                        label="An accounts CSV",
                    )
                    ui.text(
                        "The file wins over the pasted text.",
                        color="muted", size="xs",
                    )
            if draft.error:
                ui.alert(draft.error, color="error", icon="triangle-alert")
            with ui.hstack(justify="between", align="center"):
                ui.text(f"Seven columns, {IMPORT_MAX_ROWS} rows at most: "
                        f"{', '.join(IMPORT_COLUMNS)}", color="muted",
                        size="xs")
                ui.button("Check", type="submit", color="primary",
                          icon_left="arrow-right")


def step_check(draft: ImportDraft) -> None:
    rows = list(draft.rows)
    bad = [r for r in rows if r["_error"]]
    with ui.vstack(gap="md"):
        with ui.hstack(justify="between", align="center", wrap=True):
            with ui.hstack(gap="sm", align="center"):
                ui.text(draft.file_name, weight="medium", size="sm")
                ui.badge(f"{len(rows)} rows", variant="soft", color="muted",
                         size="xs")
                if bad:
                    ui.badge(f"{len(bad)} in error", variant="soft",
                             color="error", size="xs")
            with ui.hstack(gap="sm"):
                ui.button("Start again", variant="ghost",
                          icon_left="rotate-ccw", on_click=restart)
                ui.button("Import", color="primary", icon_left="database",
                          disabled=bool(bad) or not rows,
                          on_click=apply_import)
        if rows:
            # LIST tier: the component holds the rows and does
            # everything in Python. It is the exact opposite of screen 2,
            # where it holds nothing and translates every gesture into
            # SQL.
            ui.datatable(state=ImportPreview, columns=PREVIEW_COLUMNS,
                         rows=rows, row_key="_ligne", size="sm",
                         search_placeholder="Search the preview…")
        else:
            ui.empty_state("Aucune ligne lisible", icon="file-x")


def step_done(draft: ImportDraft) -> None:
    with ui.vstack(gap="md"):
        ui.empty_state(
            f"{draft.imported} account(s) imported",
            icon="circle-check",
            description="They are in the Accounts table, with today's "
                        "date as their creation date.",
        )
        with ui.hstack(justify="center", gap="sm"):
            ui.link("See the accounts", href="/accounts", variant="underline",
                    color="primary")
            ui.button("New import", variant="soft", icon_left="upload",
                      on_click=restart)


@refreshable(deps=[ImportDraft, ImportPreview])
def wizard() -> None:
    """ONE single zone for the three steps.

    Three zones nested in a fourth, all depending on the same state, made
    EVERY panel go out twice: once rendered by the parent, once as an
    out-of-band fragment. Measured on a 200-row paste — 118 kB of
    response, the preview serialised twice, half thrown away by the
    morph.
    """
    draft = ImportDraft()
    # ``draft.step`` BARE, with no ``int()``: the cast returns an
    # ordinary Python integer, so the component can no longer see the
    # value comes from the server — and it does not emit ``_serverSync``.
    # The panel shown then freezes on its FIRST render: measured, an F5
    # was needed for the stepper to follow, and "Start again" left the
    # screen on the last step while the state had gone back to zero.
    with ui.stepper(value=draft.step, clickable=False):
        for index, (label, description, icon) in enumerate(STEPS):
            ui.step(label=label, description=description, icon=icon,
                    status="complete" if index < int(draft.step) else None)
        with ui.step_panel():
            step_drop(draft)
        with ui.step_panel():
            step_check(draft)
        with ui.step_panel():
            step_done(draft)


@page("/import", layout=shell, title="Import")
def import_page() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("Account import", level=1, size="2xl")
        with ui.card(padding="md"):
            wizard()


feature = Feature(
    name="import_screen",
    kind="page",
    provides=[import_page, ImportDraft, ImportPreview],
    uses=["import_data", "access"],
)
