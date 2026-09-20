"""``Viewport`` + ``Pane`` — the frozen-screen bench.

The two components of the "frozen document, scrolling regions" model.
They go together and are tested together: a ``pane`` with no height above
it does not scroll, and a ``viewport`` with no ``pane`` clips its
content.

⚠️ **The viewport cannot be mounted IN this page**, and it is a property
of the component, not a limit of the bench: it is ``fixed inset-0``, so
it would cover the sidebar and the whole page. It is demonstrated in two
honest ways — its emitted HTML, readable here, and a **separate route**
(``/screen-demo``, with no shell) where it IS the screen. It is the
playground's only place where "putting the component in a card" makes no
sense.

``BINDABLE_PROPS = ()`` for both: pure layout, nothing a client driver
would have to drive.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/screen"
DEMO_PATH = "/screen-demo"

PADDINGS = ["none", "xs", "sm", "md", "lg", "xl"]
GAPS = ["none", "xs", "sm", "md", "lg", "xl"]
ALIGNS = ["start", "center", "end", "stretch", "baseline"]
JUSTIFIES = ["start", "center", "end", "between", "around", "evenly"]
DIRECTIONS = ["row", "col"]


class ScreenPlayground(PageState):
    # Pane
    gap: str = field(default="sm")
    padding: str = field(default="none")
    align: str = field(default="stretch")
    justify: str = field(default="start")
    # Viewport
    direction: str = field(default="row")
    frame_align: str = field(default="stretch")
    frame_gap: str = field(default="none")


def server_changed(state: ScreenPlayground) -> None:
    # The dispatcher hydrates the changed control's value into
    # ``state``; ``deps=[ScreenPlayground]`` re-renders the panel.
    pass


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


def filler(count: int, prefix: str = "Ligne") -> None:
    """Enough content for the pane to overflow — otherwise nothing
    scrolls and the bench shows nothing."""
    for i in range(count):
        with ui.card(padding="sm"):
            ui.text(f"{prefix} {i + 1}", size="sm", color="muted")


@refreshable(deps=[ScreenPlayground])
def pane_panel() -> None:
    state = ScreenPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 4}, gap="md"):
        with control("gap"):
            ui.select(value=state.gap, options=[(g, g) for g in GAPS],
                      on_change=server_changed)
        with control("padding"):
            ui.select(value=state.padding,
                      options=[(p, p) for p in PADDINGS],
                      on_change=server_changed)
        with control("align"):
            ui.select(value=state.align, options=[(a, a) for a in ALIGNS],
                      on_change=server_changed)
        with control("justify"):
            ui.select(value=state.justify,
                      options=[(j, j) for j in JUSTIFIES],
                      on_change=server_changed)

    ui.divider()

    # The bounded height is SET BY THE BENCH, never by the pane: it is
    # the component's whole contract — it takes what its parent leaves
    # it.
    with ui.card(padding="none", classes="h-72 flex flex-col"):
        with ui.pane(gap=state.gap, padding=state.padding,
                     align=state.align, justify=state.justify):
            filler(14)

    ui.divider()

    preview = ui.pane(gap=state.gap, padding=state.padding,
                      align=state.align, justify=state.justify)
    with preview:
        ui.text("Contenu")
    emitted_html_block('Emitted HTML (a pane with a single text)',
                       serialize_html(preview))


@refreshable(deps=[ScreenPlayground])
def viewport_panel() -> None:
    state = ScreenPlayground()

    with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
        with control("direction"):
            ui.select(value=state.direction,
                      options=[(d, d) for d in DIRECTIONS],
                      on_change=server_changed)
        with control("align"):
            ui.select(value=state.frame_align,
                      options=[(a, a) for a in ALIGNS],
                      on_change=server_changed)
        with control("gap"):
            ui.select(value=state.frame_gap,
                      options=[(g, g) for g in GAPS],
                      on_change=server_changed)

    ui.divider()

    frame = ui.viewport(direction=state.direction, align=state.frame_align,
                        gap=state.frame_gap)
    with frame, ui.pane(padding="md"):
        ui.text('A scrolling region')
    emitted_html_block('Emitted HTML (viewport + one pane)',
                       serialize_html(frame))

    with ui.hstack(gap="sm", align="center", wrap=True):
        ui.text('See it really mounted:', color="muted", size="sm")
        ui.button("Ouvrir /screen-demo", href=DEMO_PATH, variant="outline",
                  size="sm")


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Viewport + Pane", level=1)
        ui.text(
            'The two components of the “frozen document” model: a frame '
                'that takes the screen and never scrolls, and the regions '
                'that scroll inside it. Bretzel keeps the other model by '
                'DEFAULT — a page with no shell scrolls normally; this one is'
                ' written explicitly.',
            color="muted",
        )

        # ── Card 1 — Reference: the pane ─────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading('Reference — pane', level=2)
            ui.text(
                'Every box below is a fixed-height card. The pane takes '
                    'the remaining space and scrolls; it is the PARENT that '
                    'gives the height, never the pane.',
                color="muted", size="sm",
            )
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                for padding in ("none", "md"):
                    with ui.vstack(gap="xs"):
                        ui.text(f"padding={padding}", size="xs",
                                color="muted")
                        with ui.card(padding="none",
                                     classes="h-64 flex flex-col"):
                            with ui.pane(gap="sm", padding=padding):
                                filler(10)

        # ── Card 2 — The two height regimes ──────────────────────────
        with ui.card(), ui.vstack():
            ui.heading('The two height regimes', level=2)
            ui.text(
                'A pane carries `flex-1` AND `h-full`, because its parent'
                    ' can have two shapes. On the left a flex column — `flex-'
                    'basis` wins, the pane takes the space left under the '
                    'header. On the right a block with a defined height — '
                    '`flex-1` is inert, `h-full` renders. Both scroll.',
                color="muted", size="sm",
            )
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text('parent = a flex column (+ a header)',
                            size="xs", color="muted")
                    with ui.card(padding="none",
                                 classes="h-64 flex flex-col"):
                        with ui.hstack(classes="shrink-0 px-3 py-2 "
                                               "border-b border-text/10"):
                            ui.text('Pinned header', size="sm",
                                    weight="semibold")
                        with ui.pane(gap="sm", padding="sm"):
                            filler(10)
                with ui.vstack(gap="xs"):
                    ui.text('parent = a block with a defined height', size="xs",
                            color="muted")
                    with ui.card(padding="none", classes="h-64"):
                        with ui.pane(gap="sm", padding="sm"):
                            filler(10)

        # ── Card 3 — Two independent panes ───────────────────────────
        with ui.card(), ui.vstack():
            ui.heading('Two regions that scroll on their own', level=2)
            ui.text(
                'This is THE reason the frozen model exists, and what the'
                    ' "scrolling document" model cannot do: two columns side '
                    'by side, each with its own scroll position. A master-'
                    'detail, a kanban, a message thread next to a list.',
                color="muted", size="sm",
            )
            with ui.card(padding="none", classes="h-72"):
                with ui.hstack(gap="none", align="stretch",
                               classes="h-full divide-x divide-text/10"):
                    with ui.pane(gap="xs", padding="sm"):
                        filler(12, "Liste")
                    with ui.pane(gap="xs", padding="sm"):
                        filler(12, "Fiche")

        # ── Carte 4 — Le viewport ────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Viewport", level=2)
            ui.text(
                'It is not mounted here, and that is on purpose: `fixed '
                    'inset-0` would cover the sidebar and this page. Its HTML'
                    ' is readable below, and the `/screen-demo` route mounts '
                    'it for real, with no shell.',
                color="muted", size="sm",
            )
            viewport_panel()

        # ── Card 5 — The pane's server bench ─────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Banc serveur — pane", level=2)
            ui.text(
                'Every prop is wired to a control; the preview and the '
                    'emitted HTML both refresh on every change.',
                color="muted", size="sm",
            )
            pane_panel()


def full_demo() -> None:
    """The viewport MOUNTED — a page with no shell, it is the screen.

    Two regions: a fixed column that does not scroll, and a pane that
    does. Nothing else moves, and the document has no bar of its own: it
    is exactly what the model promises.
    """
    with ui.viewport(direction="row", align="stretch", gap="none"):
        with ui.vstack(gap="sm", classes="w-56 shrink-0 p-4 "
                                         "border-r border-text/10"):
            ui.heading("Colonne fixe", level=3, size="sm")
            ui.text('It does not scroll, however long the region on the right is.', color="muted", size="xs")
            ui.button("← Retour au banc", href=PATH, variant="outline",
                      size="sm")
        with ui.pane(gap="sm", padding="lg"):
            ui.heading('A scrolling region', level=2)
            ui.text('The document itself has no scrollbar at all.',
                    color="muted", size="sm")
            filler(40, "Contenu")
