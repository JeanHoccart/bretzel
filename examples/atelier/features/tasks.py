"""features/tasks — page: the RHYTHM, one row per task.

It is the screen that answers the question asked: "where do I break,
where am I slow, why not first time". Every row is a task — a user
message through to the final answer — and carries its strip, its
verification cycles, its errors.

The deciding column is **cycles**: the rule set is "you code everything,
you verify, you correct, you verify one last time". Two cycles, no more.
Three means starting over; ten, using the test suite as a compiler.
"""

from __future__ import annotations

from bretzel import Feature, page, refreshable, ui
from bretzel.components import DatatableState
from bretzel.state import field
from examples.atelier.core.era import MILESTONE_LABEL, MILESTONE_WHY
from examples.atelier.core.phases import (
    COLOUR_BY_LETTER,
    CYCLES_MAX,
    LABELS,
    LETTERS,
)
from examples.atelier.core.scope import short
from examples.atelier.features.shell import shell
from examples.atelier.features.tasks_data import (
    VERDICTS,
    known_scopes,
    load_tasks,
    summary,
)


class TasksTable(DatatableState, scope="session", addressable=True):
    """THIS table's query.

    ``addressable=True``: sorting or searching rewrites the address, so a
    view shares. Pointing somebody at a precise task is exactly what this
    screen is for.
    """

    per_page: int = field(default=25)
    sort_key: str = field(default="started")
    sort_dir: str = field(default="desc")


def cycles_cell(value, _row):
    """The number of cycles, painted by the rule rather than by a round
    threshold."""
    colour = "success" if value <= CYCLES_MAX else "error"
    return ui.badge(str(value), color=colour, variant="soft", size="xs")


def verdict_cell(value, _row):
    colours = {
        "first time": "success",
        "corrected": "warning",
        "back-and-forth": "error",
    }
    return ui.badge(value, color=colours.get(value, "muted"),
                    variant="soft", size="xs")


#: Beyond that, the strip is TRUNCATED in the list. Measured: a 43-cycle
#: task renders a 90-letter strip that wraps onto twenty lines and makes
#: a 201 px row — the table becomes a wall and stops comparing at a
#: glance, which is all we ask of it. The complete unfolding lives on the
#: task's sheet.
#: Measured: at 28 the column weighed 223 px and the table still
#: overflowed its host by 47 px — hence a horizontal bar, the very one
#: just removed elsewhere. At 20, the table FITS.
STRIP_MAX = 20

#: The request, cut. The same defect as the strip, and it was under my
#: nose: 300 characters wrap onto eight lines and make a 130 px row. It
#: is the widest column on the screen, so it is what decides whether the
#: table compares at a glance or not.
REQUEST_MAX = 90


def strip_cell(value, _row):
    """The strip, every letter PAINTED by its phase.

    ⚠️ The colour is not decoration: it is what makes the column readable
    WITHOUT going to find the legend. The user had to ask "what are the
    strips then?" in front of a run of bare letters — a column one has to
    decode elsewhere does not read. Painted, the task doing ping-pong is
    spotted by its blue/orange alternation without reading a single
    character.
    """
    text = value or "—"
    cut = text[:STRIP_MAX].rstrip() if len(text) > STRIP_MAX else text
    with ui.hstack(gap="xs", align="center",
                   classes="font-mono text-xs whitespace-nowrap") as cell:
        # The strip's spaces are dropped: it is the stack's `gap` that
        # separates the letters. A space rendered as a component would
        # need a primitive that does not exist — checked rather than
        # assumed.
        for letter in cut.replace(" ", ""):
            ui.text(letter, size="xs", weight="bold",
                    color=COLOUR_BY_LETTER.get(letter, "muted"))
        if len(text) > STRIP_MAX:
            ui.text(" …", size="xs", color="muted")
    return cell


def request_cell(value, row):
    """The request, on ONE line — and it is IT that opens the sheet.

    ⚠️ A link, not a row click. Both open the same sheet and they do not
    navigate alike: ``on_item_click=`` posts an action, the handler calls
    ``redirect()``, htmx receives ``HX-Redirect`` and does a
    ``window.location``. So the document is DESTROYED and the shell
    repainted, in two requests — measured on 2026-09-12, a marker set on
    ``window`` before the click did not survive it.

    An ``<a>`` is intercepted by the shell's ``hx-boost``: one request,
    only the region changes, the sidebar does not move. It is what
    :func:`bretzel.redirect`'s docstring says — "for a menu, a clickable
    row, a breadcrumb, navigation stays a ``ui.link``" — and which I had
    not read.
    """
    text = (value or "—").replace("\n", " ").strip()
    cut = (
        text[:REQUEST_MAX].rstrip() + " …" if len(text) > REQUEST_MAX else text
    )
    # ⚠️ The constraint lives on the CELL, not on `ui.column(width=)`.
    # Measured: with `width="24rem"` the column was still 662 px and
    # pushed Verdict and Strip off the screen. The table is in
    # `table-layout: auto`, where a `<col width>` is only a SUGGESTION —
    # the content wins. A `max-w` + `truncate` on the text, for its part,
    # really constrains.
    return ui.link(cut, href=f"/task/{row['id']}", variant="hover",
                   classes="block max-w-[22rem] truncate text-sm",
                   tooltip=text if cut != text else None)


#: The months, for a date a human reads. The raw ISO timestamp
#: (``2026-09-12T10:03:46.413Z``) wraps onto two lines and does not
#: compare — and comparing is all we ask of this column.
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def started_cell(value, _row):
    """``2026-09-12T10:03:46Z`` → ``12 Sep 10:03``.

    The sort, for its part, stays on the RAW value: it is the SQL column
    that orders, not what is displayed.
    """
    raw = value or ""
    try:
        month = MONTHS[int(raw[5:7]) - 1]
        return ui.text(f"{int(raw[8:10])} {month} {raw[11:16]}",
                       size="sm", classes="whitespace-nowrap")
    except (ValueError, IndexError):
        return ui.text(raw[:16], size="sm")


def scope_cell(value, _row):
    """The scope, written to be read, and painted if it is an app."""
    is_app = value.startswith("app:")
    return ui.badge(short(value), variant="soft", size="xs",
                    color="primary" if is_app else "muted")


def errors_cell(value, _row):
    if not value:
        return ui.text("—", size="sm", color="muted")
    return ui.badge(str(value), color="error", variant="soft", size="xs")


#: ⚠️ Eight columns fitted badly in 1 136 px: Verdict and Strip went off
#: the screen. `Errors` is gone — the verdict already SUMS it up
#: ("corrected" means there were some), so it paid a column to repeat
#: another. The strip, for its part, is what one comes to read: it
#: stays.
COLUMNS = [
    ui.column("started", label="Start", sortable=True, render=started_cell),
    ui.column("scope", label="Scope", sortable=True,
              filter=known_scopes(), render=scope_cell),
    ui.column("request", label="Request", render=request_cell),
    ui.column("minutes", label="Minutes", sortable=True, align="right"),
    ui.column("calls", label="Calls", sortable=True, align="right"),
    ui.column("cycles", label="Cycles", sortable=True, align="right",
              render=cycles_cell),
    ui.column("verdict", label="Verdict", sortable=True,
              filter=list(VERDICTS), render=verdict_cell),
    ui.column("strip", label="Strip", render=strip_cell),
]


def kpi(label: str, value: str, help_: str = "") -> None:
    """A number and what it means — the label alone is not enough."""
    with ui.card(classes="flex-1 min-w-40"), ui.vstack(gap="xs"):
        ui.text(label, size="xs", color="muted")
        ui.text(value, size="2xl", weight="bold")
        if help_:
            ui.text(help_, size="xs", color="muted")


@page("/", title="Tasks", layout=shell)
def tasks_page() -> None:
    """The rhythm, task by task."""
    apps = summary(apps_only=True)
    everything = summary()

    with ui.vstack(gap="lg", classes="h-full min-h-0"):
        ui.heading("The rhythm", level=1)
        ui.text(
            "One row per task: what you asked for, through to my answer. "
            f"The rule is {CYCLES_MAX} verification cycles at most — you "
            "code everything, you verify, you correct, you verify one "
            "last time. Beyond that, it is trial and error.",
            color="muted",
        )
        # ⚠️ The milestone is SAID, not merely applied. An app showing
        # 67 tasks out of 1 525 without explaining why lies by omission —
        # and it is precisely by not understanding where some rows came
        # from that the user opened this question.
        ui.text(
            f"Reading {MILESTONE_LABEL} — {MILESTONE_WHY}. "
            "The earlier tasks are ingested but not counted: they could "
            "not follow a rule whose tools did not yet exist.",
            size="sm", color="muted",
        )

        # ⚠️ The APPS first, and alone in large type. It is the
        # question asked: building the base layer requires reading it
        # whole and verifying often — healthy work that looks like
        # back-and-forth. Mixing the two makes the figure wrong in both
        # directions.
        ui.text("On the applications", size="sm", weight="medium")
        with ui.hstack(gap="md", wrap=True):
            kpi("App tasks", str(apps["tasks"]),
                f"out of {everything['tasks']} in all")
            kpi("First time", f"{apps['first_time_share']} %",
                f"against {everything['first_time_share']} % across scopes")
            kpi("Mean cycles", str(apps["mean_cycles"]),
                f"the rule allows {CYCLES_MAX}")
            kpi("Read before writing", f"{apps['read_first']} %",
                "time 1 of the rule")

        # ⚠️ The three method gestures in PROSE and not in cards. Seven
        # cards pushed the table below the fold, and the table is what
        # one comes to read. A number one compares deserves a card; a
        # number one merely notes fits in a sentence.
        # The LEGEND, on the screen where the strip reads. It lived only
        # on a task's sheet — hence too late.
        with ui.hstack(gap="md", align="center", wrap=True):
            ui.text("The strip", size="xs", weight="medium")
            for phase, letter in LETTERS.items():
                with ui.hstack(gap="xs", align="center"):
                    ui.text(letter, size="xs", weight="bold",
                            color=COLOUR_BY_LETTER[letter],
                            classes="font-mono")
                    ui.text(LABELS[phase], size="xs", color="muted")

        ui.text(
            f"On those same tasks: `describe` consulted before writing in "
            f"{apps['surface']} % of cases, `check --deep` in "
            f"{apps['contract']} %, for {apps['calls']} tool calls of "
            f"which {apps['errors']} failed.",
            size="sm", color="muted",
        )

        table()


@refreshable(deps=[TasksTable])
def table() -> None:
    """The table, INSIDE a zone that watches its query.

    ⚠️ **No ``ui.pane`` around it.** The shell already places one, and
    two nested ``overflow-y-auto`` regions make TWO scrollbars — one of
    them tiny, because the inner one only overflows by two pixels.
    Measured here: 1024×700 for 4 028 of content outside, 976×3682 for
    3 684 inside. It is the defect the user saw on screen before I did.

    ⚠️ It is not a matter of style: sorting, paginating and searching all
    work by MUTATING ``TasksTable``. Without a zone declaring it in
    ``deps=``, the controls would post and the screen would never move —
    so the framework refuses the mount at render time rather than ship
    that silence.
    """
    ui.datatable(
                state=TasksTable,
                columns=COLUMNS,
                rows=load_tasks,
                search=True,
                search_placeholder="Search the requests…",
                row_key="id",
                empty_text="Nothing to look at.",
                empty_description=(
                    "The database is empty: run "
                    "`py -m examples.atelier.core.ingest`."
                ),
            )


feature = Feature(
    name="tasks",
    kind="page",
    uses=["tasks_data", "shell", "phases", "scope", "era"],
    provides=[tasks_page],
)
