"""``/ladder`` — every control, side by side, at each size step.

The component pages show one component at a time, and a component alone
always looks right. What goes wrong is the NEIGHBOURHOOD: a search field
at 11 px beside its 13 px button, a combobox 8 px taller than the select
next to it, a message at the browser's 16 px under a 14 px heading. None
of that shows on a component's own page; all of it shows on an app.

So this page lays the controls out the way an app does — one row per
step, everything on it — and adds the text nobody sizes (a bare
``ui.text``, a link). ``tests/probes/probe_ladder.py`` measures
it: one height and one text size per row, and no text off the theme's
scale. The theme tables are gated by
``tests/consistency/test_control_height_ladder.py``; this page is what
proves the tables become the same pixels in a browser.

Each measured element carries ``data-ladder="<component>"``, and each row
``data-ladder-row="<step>"``.
"""

from bretzel import ui

PATH = "/ladder"

SIZES = ("xs", "sm", "md", "lg", "xl")

OPTIONS = ["Alpha", "Beta", "Gamma"]


def row(step: str) -> None:
    """One step: the fields side by side, then a toolbar mixing a field
    with buttons — the two neighbourhoods an app actually has.

    The fields sit in a grid: each is ``w-full``, so in a wrapping
    ``hstack`` each took the whole line and nothing stood side by side
    (``traps.md`` § « Un champ `w-full` dans un hstack avec wrap forme une
    pile »).

    ONE gap for the whole row — the label, the grid's lines, the toolbar,
    the choices: the grid at ``sm`` under a row at ``xs`` gave two
    different spaces between three lines of fields (seen by Jean on
    ``xs``). ``probe_ladder.py`` ⑤ measures it.
    """
    with ui.vstack(gap="sm", attrs={"data-ladder-row": step}):
        ui.text(f"size=\"{step}\"", size="xs", color="muted")
        with ui.grid(cols=5, gap="sm"):
            ui.input(placeholder="Search…", size=step, icon_left="search",
                     attrs={"data-ladder": "input"})
            ui.number_input(value=12, size=step,
                            attrs={"data-ladder": "number_input", "aria-label": "Quantity"})
            ui.select(options=OPTIONS, value="Alpha", size=step,
                      attrs={"data-ladder": "select"})
            ui.combobox(options=OPTIONS, placeholder="Pick…", size=step,
                        attrs={"data-ladder": "combobox"})
            ui.color_picker(value="#4338ca", size=step,
                            attrs={"data-ladder": "color_picker"})
            ui.date_picker(size=step, attrs={"data-ladder": "date_picker"})
            ui.time_picker(size=step, attrs={"data-ladder": "time_picker"})
            ui.month_picker(size=step, attrs={"data-ladder": "month_picker"})
            ui.week_picker(size=step, attrs={"data-ladder": "week_picker"})
            ui.date_range_picker(size=step, attrs={"data-ladder": "date_range_picker"})
            # With values: their tags are the field's step. Two columns,
            # so the tags fit on the one line the ladder measures (a tags
            # input wraps, by design, when they do not).
            ui.tags_input(OPTIONS, value=["Alpha", "Beta"], size=step, classes="col-span-2",
                          attrs={"data-ladder": "tags_input", "aria-label": "Tags"})
            ui.combobox(options=OPTIONS, value=["Alpha", "Beta", "Gamma"],
                        multiple=True, size=step, classes="col-span-2",
                        attrs={"data-ladder": "combobox", "aria-label": "Picks"})
        with ui.hstack(gap="sm", align="center", wrap=True):
            with ui.flex(classes="w-56"):
                ui.input(placeholder="Filter…", size=step,
                         attrs={"data-ladder": "input"})
            with ui.toggle_group(value="list", size=step,
                                 attrs={"data-ladder": "toggle_group"}):
                ui.toggle_button("list", label="List")
                ui.toggle_button("board", label="Board")
            ui.button("Save", color="primary", size=step,
                      attrs={"data-ladder": "button"})
            ui.button("Cancel", variant="soft", size=step,
                      attrs={"data-ladder": "button"})
            ui.icon_button("ellipsis", variant="ghost", size=step, tooltip="More",
                           attrs={"data-ladder": "icon_button"})
            ui.pagination(value=2, total_pages=4, size=step,
                          attrs={"data-ladder": "pagination"})
        # The choice controls have a size scale too, but no field height:
        # shown to the eye, not measured (not in ``CONTROLS``).
        with ui.hstack(gap="md", align="center", wrap=True):
            ui.checkbox(label="Checkbox", checked=True, size=step)
            ui.switch(label="Switch", checked=True, size=step)
            with ui.radio_group(value="one", direction="row", size=step):
                ui.radio("one", label="One")
                ui.radio("two", label="Two")
            with ui.flex(classes="w-40"):
                ui.slider(value=40, size=step)


def running_text() -> None:
    """What an app writes without a size: it must land on ``text-base``."""
    with ui.card(padding="md"):
        with ui.vstack(gap="sm", attrs={"data-ladder-row": "base"}):
            ui.heading("Running text", level=3, size="lg")
            ui.text("A sentence with no size= — it inherits the page's step.",
                    attrs={"data-ladder": "text"})
            ui.link("A link with no size", href="#", attrs={"data-ladder": "link"})
            # Not measured: an alert CHOOSES its size (``text-sm``), it
            # does not inherit one.
            ui.alert("An alert sets its own text size.", color="info")


def page() -> None:
    with ui.vstack(gap="lg"):
        with ui.vstack(gap="xs"):
            ui.heading("Size ladder", level=1, size="2xl")
            ui.text("Every control at each step, on one row: one height and "
                    "one text size per row.", color="muted")
        with ui.card(padding="md"):
            with ui.vstack(gap="lg"):
                for step in SIZES:
                    row(step)
        # ``variant="ghost"`` beside ``surface``: no frame, the SAME height —
        # measured as the ``md`` row.
        with ui.card(padding="md"), ui.vstack(gap="sm", attrs={"data-ladder-row": "md"}):
            ui.text('variant="ghost", size="md"', size="xs", color="muted")
            with ui.grid(cols=5, gap="sm"):
                ui.input(placeholder="Search…", variant="ghost", icon_left="search",
                         attrs={"data-ladder": "input"})
                ui.select(options=OPTIONS, value="Alpha", variant="ghost",
                          attrs={"data-ladder": "select"})
                ui.combobox(options=OPTIONS, placeholder="Pick…", variant="ghost",
                            attrs={"data-ladder": "combobox"})
                ui.tags_input(OPTIONS, value=["Alpha"], variant="ghost", classes="col-span-2",
                              attrs={"data-ladder": "tags_input", "aria-label": "Tags"})
            with ui.hstack(gap="sm", align="center"):
                with ui.flex(classes="w-56"):
                    ui.input(placeholder="Filter…", variant="ghost",
                             attrs={"data-ladder": "input"})
                ui.button("Save", color="primary", attrs={"data-ladder": "button"})
        with ui.card(padding="md"):
            with ui.vstack(gap="sm"):
                ui.text("Fields without a fixed height", weight="medium")
                with ui.hstack(gap="sm", align="start", wrap=True):
                    for step in SIZES:
                        ui.textarea(placeholder=f"textarea {step}", rows=1, size=step,
                                    attrs={"data-ladder": "textarea",
                                           "data-ladder-step": step})
                # One format, no size scale: its text is a field's at ``md``.
                with ui.flex(classes="w-full max-w-xl"):
                    ui.editor(value="Du texte **mis en forme**, une liste :\n\n- un\n- deux",
                              attrs={"data-ladder": "editor", "data-ladder-step": "md"})
                for step in SIZES:
                    with ui.tabs(value="a", size=step,
                                 attrs={"data-ladder": "tabs",
                                        "data-ladder-step": step}):
                        ui.tab("a", label=f"Tabs {step}")
                        ui.tab("b", label="Other")
        running_text()
