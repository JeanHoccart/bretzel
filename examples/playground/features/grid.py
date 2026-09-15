"""``Grid`` test bench.

Five visual cards : Reference / Edge cases / Composability / A11y /
Server playground. ``BINDABLE_PROPS = ()`` — Grid is pure layout ;
mutate via ``visible=`` / conditional render.

Two props : ``cols`` (int / dict / str escape hatch), ``gap``. No
events.
"""

import json

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/grid"


GAPS = ["none", "xs", "sm", "md", "lg", "xl"]
#: Les quatre largeurs minimales de colonne — table FERMÉE du thème.
MIN_COLS = ["12rem", "16rem", "20rem", "24rem"]


def swatch(label: str) -> None:
    with ui.card(padding="sm"):
        ui.text(label)


def coerce_cols(blob: str):
    """Parse the ``cols`` textarea : ``"3"`` → 3, JSON dict → dict,
    plain string passes through (raw Tailwind escape hatch)."""
    blob = blob.strip()
    if not blob:
        return None
    if blob.isdigit():
        return int(blob)
    if blob.startswith("{"):
        try:
            return json.loads(blob)
        except json.JSONDecodeError:
            return blob
    return blob


class GridPlayground(PageState):
    cols:        str  = field(default="3")
    #: ``""`` = non demandé, et c'est le défaut : ``min_col=`` est
    #: EXCLUSIF avec ``cols=``, donc le panneau les rend exclusifs aussi.
    min_col:     str  = field(default="")
    gap:         str  = field(default="md")
    item_count:  int  = field(default=6)
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifiers.
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")


def server_changed(state: GridPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    pass


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: GridPlayground) -> dict:
    kwargs: dict = {"gap": state.gap}
    if state.min_col:
        # Les deux posent ``grid-template-columns`` — le composant LÈVE si
        # on donne les deux, donc le panneau laisse min_col gagner plutôt
        # que de rendre une page 500.
        kwargs["min_col"] = state.min_col
    else:
        cols = coerce_cols(state.cols)
        if cols is not None:
            kwargs["cols"] = cols
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
    return kwargs


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[GridPlayground])
def server_panel() -> None:
    state = GridPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("cols (int / JSON dict / raw class)"):
            ui.input(value=state.cols,
                     placeholder='3  or  {"base": 1, "md": 3}',
                     on_change=server_changed)
        with control("min_col (exclusif avec cols)"):
            ui.select(value=state.min_col,
                      options=[("", "— (non demandé)"),
                               *[(w, w) for w in MIN_COLS]],
                      on_change=server_changed)
        with control("gap"):
            ui.select(value=state.gap,
                      options=[(g, g) for g in GAPS],
                      on_change=server_changed)
        with control("item_count (preview only)"):
            ui.number_input(value=state.item_count,
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!auto-rows-fr",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-grid",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Card grid",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="grid-auto-rows: minmax(80px, auto)",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=grid",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Grid container",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    with ui.card(padding="sm"):
        with ui.grid(**kwargs):
            for i in range(int(state.item_count or 0)):
                swatch(f"Cell {i + 1}")

    ui.divider()

    preview = ui.grid(**kwargs)
    with preview:
        for i in range(int(state.item_count or 0)):
            swatch(f"Cell {i + 1}")
    emitted_html_block(
        "Emitted HTML (Grid shell + sample children)",
        serialize_html(preview),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Grid", level=1)
            ui.text(
                "Two-dimensional layout via CSS-grid. ``cols=`` takes "
                "an int (static N), a dict (responsive — keys are "
                "Tailwind breakpoint prefixes), or a raw string "
                "(escape hatch for advanced grid-template-columns). "
                "The Server playground card stress-tests every prop "
                "; the emitted HTML is shown live underneath.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every cols/gap shape.",
                            color="muted", size="sm")

                    ui.heading("Static cols (int)", level=3)
                    with ui.vstack():
                        for n in (2, 3, 4, 6):
                            ui.text(f"cols={n}", color="muted", size="sm")
                            with ui.card(padding="sm"):
                                with ui.grid(cols=n):
                                    for i in range(n):
                                        swatch(f"{i + 1}")

                    ui.heading("Responsive cols (dict)", level=3)
                    ui.text(
                        "Resize the window — base/sm/md/lg "
                        "breakpoints reshape the grid in place.",
                        color="muted", size="xs",
                    )
                    with ui.card(padding="sm"):
                        with ui.grid(cols={"base": 1, "sm": 2,
                                           "md": 3, "lg": 4}):
                            for i in range(8):
                                swatch(f"{i + 1}")

                    ui.heading("min_col — la grille compte elle-même",
                               level=3)
                    ui.text(
                        "``cols=`` déclare COMBIEN de colonnes, par "
                        "palier de fenêtre. ``min_col=`` déclare la "
                        "largeur MINIMALE d'une colonne, et la grille "
                        "en met autant qu'elle peut dans la place "
                        "qu'elle a vraiment. Les deux boîtes ci-dessous "
                        "font 640 px : la fenêtre n'y change rien.",
                        color="muted", size="xs",
                    )
                    with ui.vstack():
                        for width in MIN_COLS:
                            ui.text(f'min_col="{width}"',
                                    color="muted", size="sm")
                            with ui.card(padding="sm"):
                                with ui.vstack(classes="w-[640px] max-w-full"):
                                    with ui.grid(min_col=width):
                                        for i in range(5):
                                            swatch(f"{i + 1}")

                    ui.heading("Gap", level=3)
                    with ui.vstack():
                        for g in GAPS:
                            ui.text(f"gap={g}",
                                    color="muted", size="sm")
                            with ui.card(padding="sm"):
                                with ui.grid(cols=4, gap=g):
                                    for i in range(8):
                                        swatch(f"{i + 1}")

                    ui.heading("Escape hatch (raw class)", level=3)
                    ui.text(
                        "Pass any literal Tailwind class. Here we "
                        "use ``grid-cols-[200px_1fr]`` for a fixed "
                        "sidebar + flex main.",
                        color="muted", size="xs",
                    )
                    with ui.card(padding="sm"):
                        with ui.grid(cols="grid-cols-[200px_1fr]"):
                            swatch("Sidebar")
                            swatch("Main")

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Unusual usage patterns.",
                            color="muted", size="sm")

                    ui.heading("Empty grid (no children)", level=3)
                    with ui.card(padding="sm"):
                        ui.grid(cols=3)

                    ui.heading("Fewer items than cols (incomplete row)",
                               level=3)
                    with ui.card(padding="sm"):
                        with ui.grid(cols=4):
                            swatch("A")
                            swatch("B")

                    ui.heading("More items than fits (auto-rows)",
                               level=3)
                    with ui.card(padding="sm"):
                        with ui.grid(cols=3):
                            for i in range(11):
                                swatch(f"{i + 1}")

                    ui.heading("cols=None (single column fallback)",
                               level=3)
                    ui.text(
                        "Without ``cols=`` the grid renders one "
                        "column — same as ``cols=1`` but expressed "
                        "via omission.",
                        color="muted", size="xs",
                    )
                    with ui.card(padding="sm"):
                        with ui.grid():
                            swatch("Item 1")
                            swatch("Item 2")

                    ui.heading("Pathological cell content", level=3)
                    ui.text(
                        "Emoji / multi-script and XSS-escape inputs "
                        "inside a cell.",
                        color="muted", size="xs",
                    )
                    with ui.card(padding="sm"):
                        with ui.grid(cols=2):
                            swatch("Ship 🚀 — שלום — 中文")
                            swatch("<script>alert(1)</script>")

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Common Grid shapes.",
                            color="muted", size="sm")

                    ui.heading("Responsive card list", level=3)
                    with ui.grid(cols={"base": 1, "sm": 2, "lg": 3},
                                 gap="md"):
                        for i in range(1, 7):
                            with ui.card(hoverable=True):
                                ui.heading(f"Item {i}", level=4)
                                ui.text("Body copy.",
                                        color="muted", size="sm")

                    ui.heading("Stats dashboard", level=3)
                    with ui.grid(cols={"base": 1, "sm": 2, "md": 4},
                                 gap="md"):
                        for (label, val, color) in (
                            ("Users",   "1 234", "primary"),
                            ("Revenue", "$12k",  "success"),
                            ("Errors",  "3",     "error"),
                            ("Uptime",  "99.97%","info"),
                        ):
                            with ui.card():
                                with ui.vstack(gap="xs"):
                                    ui.text(label, color="muted",
                                            size="xs")
                                    ui.heading(val, level=3,
                                               color=color)

                    ui.heading("Two-column form", level=3)
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with ui.form_field(label="First name"):
                            ui.input(placeholder="Ada")
                        with ui.form_field(label="Last name"):
                            ui.input(placeholder="Lovelace")
                        with ui.form_field(label="Email"):
                            ui.input(placeholder="ada@example.com", type="email")
                        with ui.form_field(label="Phone"):
                            ui.input(placeholder="+44 …", type="tel")

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Grid is a plain ``<div>`` by default — no "
                        "implicit landmark or table semantics. CSS "
                        "Grid doesn't carry ``role=\"grid\"``/``row``"
                        "/``cell`` automatically ; if you need a "
                        "data-grid semantic (sortable spreadsheet, "
                        "pivot table), use ``ui.table`` instead.",
                        color="muted", size="sm",
                    )
                    with ui.grid(cols={"base": 1, "sm": 3}, gap="md",
                                 aria_label="Project grid"):
                        for i in range(1, 4):
                            with ui.card():
                                ui.text(f"Project {i}")

            # ── Card 5 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every prop AND every escape hatch is wired "
                        "to a control ; the preview AND the emitted "
                        "HTML both refresh on every change. The "
                        "``cols=`` control accepts an int (``3``), a "
                        "JSON dict (``{\"base\": 1, \"md\": 3}``), or a "
                        "raw Tailwind string.",
                        color="muted", size="sm",
                    )
                    server_panel()
