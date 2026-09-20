"""``Resizable`` test bench.

Ten cards. ``Resizable.BINDABLE_PROPS = ("sizes",)`` — the panels' split
is bindable; orientation / disabled / size / color stay design-time, and
``min_size`` (on the panel) is a constraint. Event: ``change``.
Imperative: ``.set([30, 70])`` / ``.reset()``.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/resizable"


SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]
ORIENTATIONS = ["horizontal", "vertical"]

# The splits the ``sizes`` control offers. STRINGS because a select
# posts text; ``build_preview`` re-parses them.
SPLITS = ["", "50,50", "25,75", "70,30", "20,60,20"]

TINTS = ["primary", "success", "warning", "error", "info",
         "secondary", "muted"]


def panel_block(index: int, height: str = "h-40") -> None:
    """A demo panel — a tinted block carrying its number.

    At module scope because it serves in all ten cards; it is the
    template's threshold (a block repeated ten times becomes a function).

    It carries WIDE content on purpose: it is what proves ``min-w-0``
    does its job. Without it, flexbox refuses to go below the content's
    width and the handle blocks well before the declared minimum —
    without anything failing.
    """
    tint = TINTS[index % len(TINTS)]
    # ⚠️ ``bz-c-<tint>`` + the STEP, and above all not an
    # ``f"bg-{tint}/15"``. An assembled class only exists under the dev
    # compiler, which scans the live DOM; in production the compiler only
    # reads the sources, it will never see ``bg-info/15``. The bridge,
    # for its part, is a complete class.
    with ui.resizable_panel():
        with ui.flex(justify="center", align="center",
                     classes=f"{height} w-full bg-(--bz-bg) bz-c-{tint}"):
            ui.heading(str(index + 1), level=3, color=tint)


class ResizablePlayground(PageState):
    split: str = field(default="")
    orientation: str = field(default="horizontal")
    disabled: bool = field(default=False)
    size: str = field(default="md")
    color: str = field(default="primary")
    name: str = field(default="")
    panels: int = field(default=2)
    min_size: int = field(default=0)
    # Escape hatches.
    classes: str = field(default="")
    custom_id: str = field(default="")
    aria_label: str = field(default="")
    style: str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible: str = field(default="on")
    tooltip: str = field(default="")
    # Event-handler shape.
    on_change_mode: str = field(default="none")


class ResizableEvents(PageState):
    log: list = field(default_factory=list)


class ResizableClient(ClientState, persist="memory"):
    split: list = field(default_factory=lambda: [30, 70])


class ResizableClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


# ⚠️ The state that makes the bench's ``change`` READABLE, and it is not
# decorative. With neither a binding nor a ``name=``, the component sets
# NO ``name`` on its hidden input — it is the base layer's deliberate
# choice (``hidden_carrier_attrs``: sticking a name on by default would
# inject a stray field into every enclosing form). So the handler leaves
# with an empty FormData and receives its default value, that is
# ``change(sizes='')``. The field MUST be called ``split``: autoname
# derives it from the binding, and it is the one ``log_change``'s
# parameter carries.
class ResizableServerEvents(ClientState, persist="memory"):
    split: list = field(default_factory=lambda: [50, 50])


# ``persist="local"`` and not "memory": it is THE use case that put
# ``resizable`` on the roadmap — finding one's column width again after a
# reload. Nothing more to declare on the component side.
class ResizableRemembered(ClientState, persist="local"):
    split: list = field(default_factory=lambda: [50, 50])


def log(name: str) -> None:
    state = ResizableEvents()
    state.log = [*state.log, name]


def log_change(split: str = "") -> None:
    log(f"change(sizes={split!r})")


def clear_log() -> None:
    state = ResizableEvents()
    state.log = []


def server_changed(state: ResizablePlayground) -> None:
    # Typed param → the dispatcher hydrates the changed control's value
    # into ``state`` (coerced + persisted).
    pass


def playground_change_handler(split: str = "") -> None:
    log(f"playground-server-change(sizes={split!r})")


_CLIENT_CHANGE_EXPR = "$el.classList.toggle('ring-4')"


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: ResizablePlayground) -> dict:
    kwargs: dict = {
        "orientation": state.orientation,
        "disabled": state.disabled,
        "size": state.size,
        "color": state.color,
    }
    # An empty string = do not pass the kwarg (sizes=None = equal
    # parts).
    if state.split:
        kwargs["sizes"] = [float(p) for p in state.split.split(",")]
    if state.name:
        kwargs["name"] = state.name
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
    if state.on_change_mode == "server":
        kwargs["on_change"] = playground_change_handler
    elif state.on_change_mode == "client":
        kwargs["on_change"] = _CLIENT_CHANGE_EXPR
    elif state.on_change_mode == "both":
        kwargs["on_change"] = [playground_change_handler,
                               _CLIENT_CHANGE_EXPR]
    return kwargs


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[ResizablePlayground])
def server_panel() -> None:
    state = ResizablePlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control('sizes (the weights, empty = equal shares)'):
            ui.select(value=state.split,
                      options=[(s, s or 'None (equal shares)')
                               for s in SPLITS],
                      on_change=server_changed)
        with control("panels (combien en rendre)"):
            ui.select(value=state.panels,
                      options=[(i, str(i)) for i in (1, 2, 3, 4)],
                      on_change=server_changed)
        with control('min_size (on EVERY panel, in %)'):
            ui.select(value=state.min_size,
                      options=[(i, f"{i} %") for i in (0, 10, 20, 30)],
                      on_change=server_changed)
        with control("orientation"):
            ui.select(value=state.orientation,
                      options=[(o, o) for o in ORIENTATIONS],
                      on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control('size (handle thickness)'):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("name (overrides autoname)"):
            ui.input(value=state.name, placeholder="split",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="!max-w-md",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-split",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Editor split",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="height: 240px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=split",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder='Drag the handle',
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)
        with control("on_change mode"):
            ui.select(value=state.on_change_mode,
                      options=[("none", "None (no handler)"),
                               ("server", "Server callable"),
                               ("client", "Client string"),
                               ("both", "Both (list)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    with ui.resizable(**kwargs):
        for i in range(state.panels):
            tint = TINTS[i % len(TINTS)]
            with ui.resizable_panel(min_size=state.min_size):
                with ui.flex(justify="center", align="center",
                             classes=f"h-40 w-full bg-(--bz-bg) bz-c-{tint}"):
                    ui.heading(str(i + 1), level=3, color=tint)

    ui.divider()

    preview = ui.resizable(**kwargs)
    with preview:
        with ui.resizable_panel(min_size=state.min_size):
            ui.text("A")
        with ui.resizable_panel():
            ui.text("B")
    emitted_html_block(
        'Emitted HTML (Resizable + its panels + the derived handle)',
        serialize_html(preview),
    )


@refreshable(deps=[ResizableEvents])
def events_panel() -> None:
    state = ResizableEvents()

    ui.text(
        'Resizable emits ONE ``change`` when the handle is released, '
            'never during the gesture — otherwise it is one POST per pixel. '
            'Drag the handle below and let go: a single line appears in the '
            'log, with the complete list of weights.',
        color="muted", size="sm",
    )

    split_state = ResizableServerEvents()
    with ui.vstack():
        with ui.resizable(sizes=split_state.split,
                          on_change=log_change) as group:
            panel_block(0, height="h-28")
            panel_block(1, height="h-28")

        with ui.hstack(gap="sm"):
            ui.button("20 / 80", variant="outline",
                      on_click=group.set([20, 80]))
            ui.button('Equal shares', on_click=group.reset())

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)", color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)

    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}",
                        color="muted", size="sm", classes="font-mono")
    else:
        ui.text('(no events yet — drag the handle above)',
                color="muted", size="sm")

    ui.divider()

    ui.text(
        'Autoname covers the bound case (``sizes=state.split`` derives '
            '``name="split"``) — that is the group above. For a group with a '
            'LITERAL value that must still post its split, ``name=`` is the '
            'escape hatch, and the ONLY way: with neither, the component sets'
            ' no ``name`` at all, so the handler leaves with an empty '
            "FormData and receives ``sizes=''``. That is deliberate in the "
            'base layer — a default ``name`` would inject a stray field into '
            'every enclosing form.',
        color="muted", size="sm",
    )
    with ui.resizable(name="chosen_split", on_change=log_change):
        panel_block(0, height="h-20")
        panel_block(1, height="h-20")

    ui.divider()

    representative = ui.resizable(on_change=log_change)
    with representative:
        with ui.resizable_panel():
            ui.text("A")
        with ui.resizable_panel():
            ui.text("B")
    emitted_html_block(
        "Emitted HTML (Resizable with on_change handler)",
        serialize_html(representative),
    )


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Resizable", level=1)
        ui.text(
            'Panels that share their space out again, separated by '
                'derived handles. The share lives in WEIGHTS, not pixels: the'
                ' group keeps its proportions as it shrinks, without '
                'listening to a single resize. This is NOT the corner-handle '
                'box — CSS does that one natively with resize: both.',
            color="muted",
        )

        # ── Card 1 — Reference ──────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Reference", level=2)
            ui.text("Visual scan of every prop.",
                    color="muted", size="sm")

            ui.heading('Basic (equal shares)', level=3)
            with ui.resizable():
                panel_block(0)
                panel_block(1)

            ui.heading("sizes", level=3)
            ui.text(
                'A list of weights. [1, 3] and [25, 75] give the same '
                    'thing — it is the RATIO that counts, not the unit.',
                color="muted", size="xs",
            )
            for split in ([50, 50], [25, 75], [70, 30], [20, 60, 20]):
                ui.text(f"sizes={split}", color="muted", size="xs")
                with ui.resizable(sizes=split):
                    for i in range(len(split)):
                        panel_block(i, height="h-24")

            ui.heading("orientation", level=3)
            ui.text(
                'horizontal = panels SIDE BY SIDE, hence a vertical bar. '
                    "The name describes the group's layout, not the bar's.",
                color="muted", size="xs",
            )
            for o in ORIENTATIONS:
                ui.text(f"orientation={o}", color="muted", size="xs")
                with ui.resizable(orientation=o, style="height: 200px"):
                    panel_block(0, height="h-full")
                    panel_block(1, height="h-full")

            ui.heading('Sizes (handle thickness)', level=3)
            for s in SIZES:
                ui.text(f"size={s}", color="muted", size="xs")
                with ui.resizable(size=s):
                    panel_block(0, height="h-20")
                    panel_block(1, height="h-20")

            ui.heading("Colors (survol + appui + anneau de focus)",
                       level=3)
            for c in COLORS:
                with ui.resizable(color=c):
                    panel_block(0, height="h-16")
                    panel_block(1, height="h-16")

            ui.heading("disabled", level=3)
            ui.text(
                'The handle stays DRAWN — it still separates something — '
                    'but leaves the tab order, carries aria-disabled and the '
                    'forbidden cursor.',
                color="muted", size="xs",
            )
            with ui.resizable(disabled=True):
                panel_block(0, height="h-24")
                panel_block(1, height="h-24")

        # ── Card 2 — Slots ──────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Slots", level=2)
            ui.text(
                'A single sub-component: ui.resizable_panel. The handles,'
                    ' for their part, are not declared — there is exactly one'
                    ' fewer than there are panels, so writing them would only'
                    ' add one more chance to get it wrong.',
                color="muted", size="sm",
            )

            ui.heading('min_size — the stop', level=3)
            ui.text(
                'The first panel does not go below 30 %, the second not '
                    'below 20 %. Drag: the handle stops.',
                color="muted", size="xs",
            )
            with ui.resizable():
                with ui.resizable_panel(min_size=30):
                    with ui.flex(justify="center", align="center",
                                 classes="h-32 w-full bg-primary/15"):
                        ui.text("min_size=30")
                with ui.resizable_panel(min_size=20):
                    with ui.flex(justify="center", align="center",
                                 classes="h-32 w-full bg-success/15"):
                        ui.text("min_size=20")

            ui.heading('max_size — the ceiling', level=3)
            ui.text(
                "min_size's symmetrical twin, in the same unit: "
                    'percentage points. The first panel never goes past 45 %,'
                    ' however you drag.',
                color="muted", size="xs",
            )
            with ui.resizable():
                with ui.resizable_panel(min_size=20, max_size=45):
                    with ui.flex(justify="center", align="center",
                                 classes="h-32 w-full bg-primary/15"):
                        ui.text("20 % ≤ moi ≤ 45 %")
                with ui.resizable_panel():
                    with ui.flex(justify="center", align="center",
                                 classes="h-32 w-full bg-success/15"):
                        ui.text('the rest')

            ui.heading('collapsible — folding a panel away', level=3)
            ui.text(
                'Double-click the handle (or press Enter when it has '
                    'focus): the panel folds away and gives its space back to'
                    ' its neighbour. Do it again to get it back at its '
                    'previous size. Folding overrides min_size — it is an '
                    'explicit gesture, not a drag that slipped.',
                color="muted", size="xs",
            )
            with ui.resizable(gap="sm"):
                with ui.resizable_panel(min_size=25, collapsible=True):
                    with ui.flex(justify="center", align="center",
                                 classes="h-32 w-full bg-primary/15"):
                        ui.text("range-moi")
                with ui.resizable_panel():
                    with ui.flex(justify="center", align="center",
                                 classes="h-32 w-full bg-success/15"):
                        ui.text('I take the space')

            ui.heading('gap — the gutter around the handle', level=3)
            ui.text(
                'The same six-step scale as ui.flex / ui.hstack / '
                    'ui.grid, because it is the same space. It belongs to the'
                    " GROUP: a parent's padding cannot create space inside, "
                    'between a panel and the handle.',
                color="muted", size="xs",
            )
            with ui.resizable(gap="lg"):
                with ui.resizable_panel():
                    with ui.flex(justify="center", align="center",
                                 classes="h-24 w-full rounded-xl "
                                         "bg-primary/15"):
                        ui.text("gap=lg")
                with ui.resizable_panel():
                    with ui.flex(justify="center", align="center",
                                 classes="h-24 w-full rounded-xl "
                                         "bg-success/15"):
                        ui.text('24 px on each side')

            ui.heading("Panneaux riches", level=3)
            with ui.resizable(sizes=[35, 65], style="height: 260px"):
                with ui.resizable_panel(min_size=20):
                    with ui.vstack(gap="sm", classes="p-4"):
                        ui.heading("Projets", level=3)
                        for name, icon in (("Aurora", "rocket"),
                                           ("Borealis", "telescope"),
                                           ("Cascade", "archive")):
                            with ui.hstack(gap="sm", align="center"):
                                ui.icon(icon, size="sm", color="primary")
                                ui.text(name)
                with ui.resizable_panel():
                    with ui.vstack(gap="sm", classes="p-4"):
                        ui.heading("Aurora", level=3)
                        ui.text('The main project.', color="muted")
                        ui.button("Ouvrir", variant="outline", size="sm")

        # ── Card 3 — Edge cases ─────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Edge cases", level=2)
            ui.text("Edge inputs and exotic combinations.",
                    color="muted", size="sm")

            ui.heading('A single panel', level=3)
            ui.text('No handle: there is nothing to share out.',
                    color="muted", size="xs")
            with ui.resizable():
                panel_block(0, height="h-20")

            ui.heading("Aucun panneau", level=3)
            ui.text('An empty group — not an error.',
                    color="muted", size="xs")
            ui.resizable()

            ui.heading('sizes shorter than the number of panels',
                       level=3)
            ui.text(
                'Completed into equal shares, never raised: the panels '
                    'often come from the data, so their number changes '
                    'without the persisted value knowing.',
                color="muted", size="xs",
            )
            with ui.resizable(sizes=[50]):
                for i in range(3):
                    panel_block(i, height="h-20")

            ui.heading('absurd sizes (negative, text)', level=3)
            ui.text('Every broken entry falls back to an equal share, panel by '
                'panel — none disappears.',
                    color="muted", size="xs")
            with ui.resizable(sizes=[-10, "nope", 40]):
                for i in range(3):
                    panel_block(i, height="h-20")

            ui.heading('Two minimums that do not fit', level=3)
            ui.text(
                '60 + 60 > 100: the handle freezes instead of violating '
                    'one of the two.',
                color="muted", size="xs",
            )
            with ui.resizable():
                with ui.resizable_panel(min_size=60):
                    with ui.flex(justify="center", align="center",
                                 classes="h-20 w-full bg-error/15"):
                        ui.text("min 60")
                with ui.resizable_panel(min_size=60):
                    with ui.flex(justify="center", align="center",
                                 classes="h-20 w-full bg-warning/15"):
                        ui.text("min 60")

            ui.heading('Very wide content in a narrow panel',
                       level=3)
            ui.text(
                'The min-w-0 test: the panel must SHRINK below its '
                    "content's width, not brace against it.",
                color="muted", size="xs",
            )
            with ui.resizable(sizes=[20, 80]):
                with ui.resizable_panel():
                    ui.text('AVeryLongWordThatRefusesToBreakAtAll',
                            classes="whitespace-nowrap")
                with ui.resizable_panel():
                    ui.text("voisin", color="muted")

        # ── Card 4 — Composability ──────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Composability", level=2)
            ui.text('Resizable in its usual contexts.',
                    color="muted", size="sm")

            ui.heading('Nested (column + vertical split)', level=3)
            ui.text(
                'The “editor / preview” case: a vertical group INSIDE a '
                    'panel of a horizontal group. Each has its own scope, and'
                    " the runtime's ``:scope >`` guarantees the parent does "
                    "not see the child's panels.",
                color="muted", size="xs",
            )
            with ui.resizable(sizes=[30, 70], style="height: 300px"):
                panel_block(0, height="h-full")
                with ui.resizable_panel():
                    with ui.resizable(orientation="vertical",
                                      classes="h-full"):
                        panel_block(1, height="h-full")
                        panel_block(2, height="h-full")

            ui.heading('A BARE child becomes a panel', level=3)
            ui.text(
                'Every direct child is a panel — ui.resizable_panel is '
                    'not a toll gate, it is the opt-in for giving a min_size.'
                    ' That is what lets a @refreshable or a ui.fragment '
                    'compose without ceremony: their nodes attach to the '
                    'current parent like any component, and a version that '
                    'refused them made the group unusable with them.',
                color="muted", size="xs",
            )
            with ui.resizable(sizes=[40, 60]):
                ui.text('a bare child, with no resizable_panel',
                        classes="p-4 bg-info/10")
                with ui.resizable_panel(min_size=25):
                    with ui.flex(justify="center", align="center",
                                 classes="h-24 w-full bg-success/15"):
                        ui.text('a declared panel (min_size=25)')

            ui.heading('In a grid cell (constrained context)',
                       level=3)
            ui.text(
                'The test that counts: a group in a narrow column must '
                    'neither overflow nor push the page.',
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                with ui.card(), ui.resizable(size="sm"):
                    panel_block(0, height="h-24")
                    panel_block(1, height="h-24")
                ui.text("Cellule voisine.", color="muted")
                ui.text("Autre voisine.", color="muted")

            ui.heading('Two independent groups', level=3)
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.resizable(color="success"):
                    panel_block(0, height="h-24")
                    panel_block(1, height="h-24")
                with ui.resizable(color="error"):
                    panel_block(2, height="h-24")
                    panel_block(3, height="h-24")

        # ── Card 5 — A11y ───────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("A11y", level=2)
            ui.text(
                'Every handle is a focusable role="separator" carrying '
                    'aria-valuenow / valuemin / valuemax and an aria-controls'
                    ' pointing at the panel it resizes. The ← → arrows (or ↑ '
                    '↓ when vertical) move it in steps of 2 points: a handle '
                    'that only obeys the pointer is unusable without a mouse.'
                    " ⚠️ The declared aria-orientation is the BAR's, hence "
                    "the OPPOSITE of the group's — the classic confusion of "
                    'this pattern.',
                color="muted", size="sm",
            )
            with ui.resizable(aria_label="Demo split"):
                panel_block(0, height="h-28")
                panel_block(1, height="h-28")

        # ── Card 6 — Server playground ──────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server playground", level=2)
            ui.text(
                "Every Resizable prop AND every escape hatch is "
                "wired to a control ; the preview AND the emitted "
                "HTML both refresh on every change.",
                color="muted", size="sm",
            )
            server_panel()

        # ── Card 7 — Server events ──────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server events", level=2)
            events_panel()

        # ── Card 8 — Client playground ──────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Client playground", level=2)
            ui.text(
                "Mirror of Resizable's BINDABLE_PROPS = ('sizes',). The "
                    'split is bound to a ClientState: dragging the handle '
                    'pushes it back up, and the buttons write it — with no '
                    'round trip.',
                color="muted", size="sm",
            )
            client = ResizableClient()
            with ui.hstack(gap="sm"):
                ui.button("30 / 70", variant="outline", size="sm",
                          on_click=client.split.set([30, 70]))
                ui.button("50 / 50", variant="outline", size="sm",
                          on_click=client.split.set([50, 50]))
                ui.button("80 / 20", variant="outline", size="sm",
                          on_click=client.split.set([80, 20]))

            ui.divider()

            with ui.resizable(sizes=client.split):
                panel_block(0)
                panel_block(1)

            ui.text(
                ClientExpression(
                    "'poids courants : ' + JSON.stringify("
                    "$bz.state.ResizableClient.default.split ?? [])"
                ),
                color="muted", size="sm", classes="font-mono",
            )

            ui.divider()

            ui.heading("Persistance — persist=\"local\"", level=3)
            ui.text(
                'The use case that put this component on the roadmap. '
                    'Drag the handle, reload the page (F5): the split is '
                    'there. No persistence prop on the component — the '
                    'ClientState decides that, and there is no flash on load '
                    '(the root carries a bz-data, so it waits for html.bz-'
                    'ready, which boot only sets AFTER re-reading '
                    'localStorage).',
                color="muted", size="sm",
            )
            remembered = ResizableRemembered()
            with ui.resizable(sizes=remembered.split):
                panel_block(2, height="h-28")
                panel_block(3, height="h-28")

            ui.divider()

            preview = ui.resizable(sizes=client.split)
            with preview:
                with ui.resizable_panel():
                    ui.text("A")
                with ui.resizable_panel():
                    ui.text("B")
            emitted_html_block(
                'Emitted HTML — the directives read the store cell '
                    'directly; the panels settle again when it moves, and the'
                    ' gesture pushes it back up on release.',
                serialize_html(preview),
            )

        # ── Card 9 — External controls — the 3 modes ────────────
        with ui.card(), ui.vstack():
            ui.heading("External controls — the 3 modes", level=2)
            ui.text(
                '.reset() ALWAYS dispatches a DOM event, binding or not: '
                    'the equal share depends on the NUMBER of live panels, '
                    'which the server no longer knows after a morph has added'
                    ' some. .set([…]) writes into the binding when there is '
                    'one.',
                color="muted", size="sm",
            )

            ui.heading("Mode 1 — Imperative only (default)", level=3)
            with ui.resizable() as m1:
                panel_block(0, height="h-28")
                panel_block(1, height="h-28")
            with ui.hstack(gap="sm"):
                ui.button("20 / 80", variant="outline",
                          on_click=m1.set([20, 80]))
                ui.button("80 / 20", variant="outline",
                          on_click=m1.set([80, 20]))
                ui.button('Equal shares', variant="ghost",
                          on_click=m1.reset())

            ui.divider()

            ui.heading("Mode 2 — ClientBinding only", level=3)
            ui.text(
                'To be used when ANOTHER component has to read the split '
                    '— a counter, a panel that folds away when its share '
                    'drops too low.',
                color="muted", size="sm",
            )
            bound = ResizableClient(key="binding_only")
            with ui.resizable(sizes=bound.split):
                panel_block(0, height="h-28")
                panel_block(1, height="h-28")
            ui.text(
                ClientExpression(
                    "'gauche : ' + Math.round(("
                    "$bz.state.ResizableClient.binding_only.split "
                    "?? [50])[0]) + ' %'"
                ),
                color="muted", size="sm",
            )

            ui.divider()

            ui.heading("Mode 3 — Both (write-through)", level=3)
            both = ResizableClient(key="both")
            with ui.resizable(sizes=both.split) as m3:
                panel_block(0, height="h-28")
                panel_block(1, height="h-28")
            with ui.hstack(gap="sm", align="center"):
                ui.button("25 / 75", variant="outline",
                          on_click=m3.set([25, 75]))
                ui.button('Equal shares', on_click=m3.reset())
                ui.text(
                    ClientExpression(
                        "'bound = ' + JSON.stringify("
                        "$bz.state.ResizableClient.both.split ?? [])"
                    ),
                    color="muted", size="sm", classes="font-mono",
                )

            ui.divider()

            imperative_preview = ui.resizable(sizes=both.split)
            with imperative_preview:
                with ui.resizable_panel():
                    ui.text("A")
                with ui.resizable_panel():
                    ui.text("B")
            emitted_html_block(
                'Emitted HTML — the root carries bz-on:bz-set and bz-'
                    'on:bz-reset, the two receivers the imperative methods '
                    'dispatch to.',
                serialize_html(imperative_preview),
            )

        # ── Card 10 — Client events ─────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Client events", level=2)
            ui.text("change wired to a client expression that pushes "
                    "the new split onto a ClientState list. Zero "
                    "network.",
                    color="muted", size="sm")
            cevents = ResizableClientEvents()
            _new_value = ClientExpression("$event.target.value")
            with ui.resizable(on_change=cevents.log.push(_new_value)):
                panel_block(0, height="h-28")
                panel_block(1, height="h-28")

            ui.divider()

            with ui.hstack(justify="between", align="center"):
                ui.text("Live log (client-reactive)",
                        color="muted", size="sm")
                ui.button("Clear", variant="ghost", size="xs",
                          on_click=cevents.log.clear())

            ui.divider()

            log_text = ClientExpression(
                '($bz.state.ResizableClientEvents.default.log'
                ' || []).join("\\n") || "(no events yet)"'
            )
            ui.text(log_text,
                    color="muted", size="sm",
                    classes="font-mono whitespace-pre")

            ui.divider()

            preview = ui.resizable(
                on_change=cevents.log.push(_new_value),
            )
            with preview:
                with ui.resizable_panel():
                    ui.text("A")
                with ui.resizable_panel():
                    ui.text("B")
            emitted_html_block(
                'Emitted HTML — the bz-on:change handler is relocated '
                    'onto the hidden input, whose bz-effect re-fires a change'
                    ' every time a handle is released.',
                serialize_html(preview),
            )
