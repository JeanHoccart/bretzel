"""``Combobox`` test bench — full 10-card gabarit.

Eight props : ``value`` / ``multiple`` / ``bulk_actions`` /
``empty_text`` / ``placeholder`` / ``disabled`` / ``required`` /
``color`` / ``size``. Four events : ``change`` / ``focus`` /
``blur`` / ``search``. ``BINDABLE_PROPS = ("value", "disabled")`` —
the picked value + lock flag get a dedicated Client playground card ;
the rest (multiple / bulk_actions / color / size / ...) stay
design-time.

Search filtering is built-in and non-configurable in v1 :
diacritics-insensitive, case-insensitive, whitespace-tokenised
(each token must match somewhere in the option's label or value).
Options keep their declared order — no scoring / re-ranking.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/combobox"


# Reasonably sized option list — exercises the search filter without
# blowing up the HTML. Mix of diacritics + multi-word labels so the
# tokenise-then-substring algorithm has something interesting to chew.
COUNTRIES = [
    ("fr", "France"),
    ("es", "España"),
    ("de", "Germany"),
    ("it", "Italia"),
    ("pt", "Portugal"),
    ("nl", "Nederland"),
    ("be", "Belgique"),
    ("ch", "Suisse"),
    ("at", "Österreich"),
    ("se", "Sverige"),
    ("no", "Norge"),
    ("dk", "Danmark"),
    ("fi", "Suomi"),
    ("pl", "Polska"),
    ("cz", "Česko"),
    ("gr", "Ελλάδα"),
    ("uk", "United Kingdom"),
    ("ie", "Ireland"),
    ("us", "United States"),
    ("ca", "Canada"),
    ("mx", "México"),
    ("br", "Brasil"),
    ("ar", "Argentina"),
    ("cl", "Chile"),
    ("jp", "日本"),
    ("cn", "中国"),
    ("kr", "대한민국"),
    ("au", "Australia"),
    ("nz", "New Zealand"),
]


SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]


# ── Playground state ──────────────────────────────────────────────────


class ComboboxPlayground(PageState):
    multiple:     bool = field(default=False)
    bulk_actions: bool = field(default=False)
    placeholder:  str  = field(default="Search countries…")
    empty_text:   str  = field(default="No results")
    disabled:     bool = field(default=False)
    required:     bool = field(default=False)
    color:        str  = field(default="primary")
    size:         str  = field(default="md")
    initial:      str  = field(default="fr")
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")


class ComboboxEvents(PageState):
    log: list = field(default_factory=list)


class ComboboxServerEvents(ClientState, persist="memory"):
    """Drives the server-events demo. ``value=ses.value`` →
    autoname → ``name="value"`` on the hidden input → handler
    receives ``value=`` via FormData."""

    value: str = field(default="")


class ComboboxClient(ClientState, persist="memory"):
    """Mirror of Combobox's BINDABLE_PROPS = ('value', 'disabled').

    ``picked`` binds the ``value`` prop (kept as ``picked`` — reused
    across the External-controls card's three modes, which predate
    the Client playground card and only exercise ``value``)."""

    picked:   str  = field(default="fr")
    disabled: bool = field(default=False)


class ComboboxMultiClient(ClientState, persist="memory"):
    picked: list = field(default_factory=lambda: ["fr", "de"])


class ComboboxClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


# ── Handlers ──────────────────────────────────────────────────────────


def log(name: str) -> None:
    state = ComboboxEvents()
    state.log = [*state.log, name]


def log_change(value: str = "") -> None: log(f"change(value={value!r})")
def log_focus()  -> None: log("focus")
def log_blur()   -> None: log("blur")
def log_search(query: str = "") -> None:
    if query:
        log(f"search(query={query!r})")


def log_close() -> None: log("close")


def clear_log() -> None:
    ComboboxEvents().log = []


def server_changed(state: ComboboxPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    pass


# ── Helpers ───────────────────────────────────────────────────────────


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: ComboboxPlayground) -> dict:
    kwargs: dict = {
        "options": COUNTRIES,
        "multiple": state.multiple,
        "bulk_actions": state.bulk_actions,
        "placeholder": state.placeholder,
        "empty_text": state.empty_text,
        "disabled": state.disabled,
        "required": state.required,
        "color": state.color,
        "size": state.size,
    }
    if state.multiple:
        kwargs["value"] = [
            v.strip() for v in state.initial.split(",") if v.strip()
        ]
    else:
        kwargs["value"] = state.initial
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


# ──────────────────────────────────────────────────────────────────────
# Refreshable panels
# ──────────────────────────────────────────────────────────────────────


@refreshable(deps=[ComboboxPlayground])
def server_panel() -> None:
    state = ComboboxPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("multiple"):
            ui.switch(checked=state.multiple,
                      on_change=server_changed)
        with control("bulk_actions (multiple only)"):
            ui.switch(checked=state.bulk_actions,
                      on_change=server_changed)
        with control("placeholder"):
            ui.input(value=state.placeholder,
                     on_change=server_changed)
        with control("empty_text"):
            ui.input(value=state.empty_text,
                     on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled,
                      on_change=server_changed)
        with control("required"):
            ui.switch(checked=state.required,
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control(
            "initial (single : 'fr' / multi : 'fr,de,es')"
        ):
            ui.input(value=state.initial,
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!w-72",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id,
                     placeholder="country-picker",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Pick a country",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="--ring: 4px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=country",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Search and pick",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    with ui.flex(justify="center"):
        ui.combobox(**kwargs)

    ui.divider()

    emitted_html_block(
        "Emitted HTML — the controls grid drives this snapshot live",
        serialize_html(ui.combobox(**kwargs)),
    )


@refreshable(deps=[ComboboxEvents])
def events_panel() -> None:
    state = ComboboxEvents()

    ui.text(
        "Combobox exposes five events : ``on_change`` (pick), "
        "``on_focus`` / ``on_blur`` (input focus), ``on_search`` "
        "(every keystroke — fires the query string via a second "
        "hidden input named ``query``), and ``on_close`` (the panel "
        "shut). One instance per event below — a single Combobox "
        "carries only one server ``hx-post``.",
        color="muted", size="sm",
    )
    ui.text(
        "``on_close`` is the one that fires ONCE for a whole session "
        "of ticking : the picks live client-side while the panel is "
        "open, and land in a single request on the way out. That is "
        "how ``ui.datatable`` applies a column filter. It needs "
        "``hx-include`` to carry the value — a ``<div>`` posts no "
        "descendant field on its own.",
        color="muted", size="sm",
    )

    ses = ComboboxServerEvents()
    with ui.flex(wrap=True, gap="md", justify="center"):
        ui.combobox(
            options=COUNTRIES,
            value=ses.value,
            placeholder="change",
            on_change=log_change,
        )
        ui.combobox(options=COUNTRIES, placeholder="focus",
                    on_focus=log_focus)
        ui.combobox(options=COUNTRIES, placeholder="blur",
                    on_blur=log_blur)
        ui.combobox(options=COUNTRIES, placeholder="search",
                    on_search=log_search)
        ui.combobox(
            options=COUNTRIES, multiple=True, bulk_actions=True,
            id="cb-close", placeholder="Search countries…",
            trigger=ui.button("close (tick, then shut)",
                              variant="soft", icon_left="list-filter"),
            on_close=log_close,
            attrs={"hx-include": "#cb-close input[type=hidden]"},
        )

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 12)",
                color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)

    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-12:]), 1):
                ui.text(f"{i}. {evt}",
                        color="muted", size="sm",
                        classes="font-mono")
    else:
        ui.text("(no events yet — interact with the combobox above)",
                color="muted", size="sm")

    ui.divider()

    representative = ui.combobox(
        options=COUNTRIES[:5],
        value=ses.value,
        on_change=log_change,
    )
    emitted_html_block(
        "Emitted HTML (Combobox with value-binding + on_change "
        "+ on_search)",
        serialize_html(representative),
    )


# ──────────────────────────────────────────────────────────────────────
# Page
# ──────────────────────────────────────────────────────────────────────


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Combobox", level=1)
            ui.text(
                "Search-as-you-type select. Two modes : single (one "
                "pick) and multiple (list of picks rendered as "
                "removable pills inside the trigger). Filter is "
                "built-in : diacritics-insensitive + whitespace-"
                "tokenised + substring match. Options keep their "
                "declared order. Imperative API : ``.set`` / "
                "``.clear`` / ``.focus`` / ``.blur`` + ``.select_all`` "
                "/ ``.deselect_all`` (multi).",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every variant × size. "
                            "Type to filter — try 'fra' (matches "
                            "France), 'na ca' (Canada via tokens), "
                            "'ost' (matches Österreich via "
                            "diacritics-insensitive normalize).",
                            color="muted", size="sm")

                    ui.heading("Single", level=3)
                    ui.combobox(options=COUNTRIES,
                                value="fr",
                                placeholder="Pick a country")

                    ui.heading("Multiple (no bulk actions)", level=3)
                    ui.combobox(options=COUNTRIES,
                                value=["fr", "de"],
                                multiple=True,
                                placeholder="Pick countries")

                    ui.heading(
                        "Multiple + bulk_actions (Select all / "
                        "Clear in the panel header)",
                        level=3,
                    )
                    ui.combobox(options=COUNTRIES,
                                value=["fr", "de", "it"],
                                multiple=True,
                                bulk_actions=True,
                                placeholder="Pick countries")

                    ui.heading(
                        "trigger= (the filter shape : open, then tick)",
                        level=3,
                    )
                    ui.text(
                        "By default the search field IS the trigger — a "
                        "combobox is driven by typing. Pass trigger= and "
                        "the roles split : your component opens the "
                        "panel, and the search field moves to the top of "
                        "it. Same list, same bulk actions ; you open it "
                        "and tick instead of typing at it.",
                        size="sm", color="muted",
                    )
                    ui.combobox(options=COUNTRIES,
                                value=["fr", "de", "it"],
                                multiple=True,
                                bulk_actions=True,
                                placeholder="Search countries…",
                                trigger=ui.button("Country",
                                                  variant="soft",
                                                  icon_left="list-filter"))

                    ui.heading("render= — the option's body", level=3)
                    with ui.vstack():
                        ui.text('The component keeps the wrapper: data-value, the'
                            ' click, aria-selected and above all the filter '
                            '(bz-show). The callback fills the inside.',
                                color="muted", size="xs")
                        ui.combobox(options=COUNTRIES,
                                    placeholder='Type to filter…',
                                    render=lambda v, l: ui.badge(
                                        label=l, color="primary"))
                        ui.text('Two limits: the trigger and the pills show the '
                            'TEXT label, and the filter searches that same '
                            "label — type 'fr'.",
                                color="muted", size="xs")

                    ui.heading("Sizes (xs → xl)", level=3)
                    with ui.vstack(gap="md"):
                        for s in ui.each(SIZES):
                            with ui.vstack(gap="xs"):
                                ui.text(s, color="muted", size="xs")
                                ui.combobox(
                                    options=COUNTRIES[:8],
                                    value="fr",
                                    size=s,
                                    placeholder=f"Size {s}",
                                )

                    ui.heading("Colors", level=3)
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        for c in ui.each(COLORS):
                            with ui.vstack(gap="xs"):
                                ui.text(c, color="muted", size="xs")
                                ui.combobox(
                                    options=COUNTRIES[:5],
                                    value="fr",
                                    color=c,
                                )

                    ui.heading("Disabled / required", level=3)
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("disabled", color="muted", size="xs")
                            ui.combobox(options=COUNTRIES[:4],
                                        value="fr", disabled=True)
                        with ui.vstack(gap="xs"):
                            ui.text("required", color="muted", size="xs")
                            ui.combobox(options=COUNTRIES[:4],
                                        required=True,
                                        placeholder="Required")

                    ui.heading("empty_text", level=3)
                    ui.combobox(options=COUNTRIES,
                                placeholder="Type 'zzzz' to see it",
                                empty_text='No result')

                    ui.heading("name (form field key)", level=3)
                    ui.combobox(options=COUNTRIES[:4], name="country")

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs and exotic combinations.",
                            color="muted", size="sm")

                    ui.heading("Empty options", level=3)
                    ui.combobox(options=[],
                                placeholder="Nothing to pick")

                    ui.heading("One option only", level=3)
                    ui.combobox(options=[("a", "Alpha")], value="a")

                    ui.heading("Initial value not in options", level=3)
                    ui.combobox(options=COUNTRIES[:5],
                                value="zz",
                                placeholder="Hidden value")

                    ui.heading(
                        "Multi with initial values not in options",
                        level=3,
                    )
                    ui.combobox(options=COUNTRIES[:5],
                                value=["zz", "yy"],
                                multiple=True)

                    ui.heading("Disabled option", level=3)
                    ui.combobox(
                        options=[
                            {"value": "a", "label": "Active"},
                            {"value": "b", "label": "Banned",
                             "disabled": True},
                            {"value": "c", "label": "Available"},
                        ],
                    )

                    ui.heading(
                        "Emoji + multi-script labels", level=3,
                    )
                    ui.combobox(options=COUNTRIES,
                                value="jp",
                                placeholder="Try : '日' or 'kor'")

                    ui.heading(
                        "Diacritics-insensitive search (try 'esp', "
                        "'ost', 'oster')", level=3,
                    )
                    ui.combobox(options=COUNTRIES,
                                placeholder="Type without accents")

                    ui.heading(
                        "Tokenized search (try 'new zea', 'united "
                        "king', 'united states')", level=3,
                    )
                    ui.combobox(options=COUNTRIES,
                                placeholder="Two words = AND match")

                    ui.heading(
                        "HTML-special chars in label (XSS escape)",
                        level=3,
                    )
                    ui.combobox(
                        options=[
                            ("a", "<script>alert(1)</script>"),
                            ("b", "Safe label"),
                        ],
                        placeholder="Try selecting the script-like",
                    )

                    ui.heading("Custom empty_text", level=3)
                    ui.combobox(options=COUNTRIES,
                                placeholder="Type 'zzzz' to see it",
                                empty_text='No country found')

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Common patterns combining Combobox with "
                            "other components.",
                            color="muted", size="sm")

                    ui.heading("Inside a Form", level=3)
                    with ui.form():
                        with ui.vstack():
                            ui.combobox(options=COUNTRIES,
                                        value="fr",
                                        placeholder="Country")
                            ui.combobox(
                                options=[("en", "English"),
                                         ("fr", 'French'),
                                         ("es", "Español")],
                                value="en",
                                placeholder="Language",
                            )
                            with ui.hstack(justify="end"):
                                ui.button("Submit", type="submit",
                                          color="primary")

                    ui.heading("Inside a Card", level=3)
                    with ui.card():
                        with ui.vstack():
                            ui.text("Profile setup",
                                    color="muted", size="sm")
                            ui.combobox(options=COUNTRIES,
                                        value=["fr", "de"],
                                        multiple=True,
                                        bulk_actions=True,
                                        placeholder="Visited countries")

                    ui.heading("Multi with many initial picks", level=3)
                    ui.combobox(
                        options=COUNTRIES,
                        value=[c[0] for c in COUNTRIES[:8]],
                        multiple=True,
                        bulk_actions=True,
                    )

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Trigger wears ``role=\"combobox\"`` + "
                        "``aria-haspopup=\"listbox\"`` + reactive "
                        "``aria-expanded``. The panel wears "
                        "``role=\"listbox\"`` and each option "
                        "``role=\"option\"`` with reactive "
                        "``aria-selected``. Keyboard : Arrows nav "
                        "VISIBLE options (skips filtered-out), Enter "
                        "picks, Escape closes, Backspace on empty "
                        "input pops the last pill (multi).",
                        color="muted", size="sm",
                    )
                    ui.combobox(options=COUNTRIES,
                                placeholder="Test keyboard nav")

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every prop AND every escape hatch wired to "
                        "a control ; preview AND emitted HTML refresh "
                        "on every change.",
                        color="muted", size="sm",
                    )
                    server_panel()

            # ── Card 7 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    events_panel()

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of Combobox's ``BINDABLE_PROPS = "
                        "('value', 'disabled')`` contract. Both flip "
                        "live via ``bz-attr:value`` / "
                        "``bz-attr:disabled`` — no network "
                        "round-trip. Visual axes (multiple / "
                        "bulk_actions / color / size) stay "
                        "design-time.",
                        color="muted", size="sm",
                    )
                    client = ComboboxClient(key="playground")
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("value"):
                            ui.combobox(value=client.picked,
                                        options=COUNTRIES)
                        with control("disabled"):
                            ui.switch(checked=client.disabled)

                    ui.divider()

                    with ui.flex(justify="center", align="center"):
                        ui.combobox(value=client.picked,
                                    options=COUNTRIES,
                                    disabled=client.disabled,
                                    placeholder="Client-bound combobox")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — bz-attr:value on value, "
                        "bz-attr:disabled on disabled.",
                        serialize_html(
                            ui.combobox(
                                value=client.picked,
                                options=COUNTRIES,
                                disabled=client.disabled,
                                placeholder="Client-bound combobox",
                            )
                        ),
                    )

            # ── Card 9 — External controls — the 3 modes ────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes",
                               level=2)
                    ui.text(
                        "Same scenario played three ways.",
                        color="muted", size="sm",
                    )

                    # Mode 1 — Imperative only
                    ui.heading("Mode 1 — Imperative only", level=3)
                    ui.text(
                        "No ClientState. The combobox owns its value "
                        "in client scope. Sibling buttons call "
                        "``.set / .clear / .focus / .select_all``.",
                        color="muted", size="sm",
                    )
                    m1 = ui.combobox(options=COUNTRIES,
                                     multiple=True,
                                     placeholder="Imperative")
                    with ui.hstack(wrap=True, gap="sm"):
                        # ⚠️ `open` / `close` / `toggle` added on
                        # 2026-09-03, at the same time as on the six
                        # pickers. Combobox is the SAME shape — an
                        # anchored panel carrying a value — and it had
                        # only the field half. Giving them to the others
                        # without giving them to it would have made two
                        # conventions for one shape.
                        ui.button("Ouvrir", on_click=m1.open())
                        ui.button("Fermer", variant="outline",
                                  on_click=m1.close())
                        ui.button("Basculer", variant="outline",
                                  on_click=m1.toggle())
                        ui.button("Set [fr, de]",
                                  on_click=m1.set(["fr", "de"]))
                        ui.button("Select all", color="success",
                                  on_click=m1.select_all())
                        ui.button("Clear", variant="outline",
                                  on_click=m1.clear())
                        ui.button("Focus", variant="ghost",
                                  on_click=m1.focus())
                        ui.button("Blur", variant="ghost",
                                  on_click=m1.blur())

                    ui.divider()

                    # Mode 2 — ClientBinding only
                    ui.heading("Mode 2 — ClientBinding only", level=3)
                    ui.text(
                        "The binding is the single source of truth — "
                        "another component (e.g. a label) can read or "
                        "react to the pick.",
                        color="muted", size="sm",
                    )
                    bound = ComboboxClient(key="binding_only")
                    with ui.vstack(gap="sm"):
                        with ui.hstack(align="center", gap="sm"):
                            ui.text("Picked :", color="muted", size="sm")
                            ui.code(bound.picked, lang="text")
                        ui.combobox(options=COUNTRIES,
                                    value=bound.picked,
                                    placeholder="Type to filter")
                        with ui.hstack(wrap=True, gap="sm"):
                            ui.button("Force fr",
                                      on_click=bound.picked.set("fr"))
                            ui.button("Force jp",
                                      on_click=bound.picked.set("jp"))
                            ui.button("Clear", variant="ghost",
                                      on_click=bound.picked.set(""))

                    ui.divider()

                    # Mode 3 — Both write-through
                    ui.heading("Mode 3 — Both (write-through)",
                               level=3)
                    ui.text(
                        'A binding supplied AND ``.set()`` called on the '
                            'instance. The framework detects the binding and '
                            'delegates to ``binding.set(v)`` — single source '
                            'of truth preserved.',
                        color="muted", size="sm",
                    )
                    both = ComboboxClient(key="both")
                    m3 = ui.combobox(options=COUNTRIES,
                                     value=both.picked)
                    with ui.hstack(wrap=True, gap="sm"):
                        ui.button("Set 'de' via combo.set()",
                                  on_click=m3.set("de"))
                        ui.button("Set 'es' via binding.set()",
                                  on_click=both.picked.set("es"))
                        ui.button("Focus via combo.focus()",
                                  variant="ghost",
                                  on_click=m3.focus())

                    ui.divider()

                    # Bonus — multi with array binding
                    ui.heading(
                        "Bonus — multi with array binding",
                        level=3,
                    )
                    multi = ComboboxMultiClient(key="multi")
                    mult_cb = ui.combobox(
                        options=COUNTRIES,
                        value=multi.picked,
                        multiple=True,
                        bulk_actions=True,
                    )
                    with ui.hstack(wrap=True, gap="sm"):
                        ui.button("Select all",
                                  on_click=mult_cb.select_all())
                        ui.button("Clear", variant="outline",
                                  on_click=mult_cb.clear())

                    ui.divider()

                    preview = ui.combobox(options=COUNTRIES[:5],
                                          value=bound.picked)
                    emitted_html_block(
                        "Emitted HTML — Mode 2 (binding only) : "
                        "``get value`` reads the bound path ; "
                        "sibling ``binding.set()`` writes back "
                        "without a round-trip.",
                        serialize_html(preview),
                    )

            # ── Card 10 — Client events ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text(
                        "All four events wired to client expressions "
                        "that push onto a ClientState list. Zero "
                        "network ; the log below re-renders via "
                        "bz-text on every push.",
                        color="muted", size="sm",
                    )
                    cevents = ComboboxClientEvents()
                    # change → push the new selection (JSON-stringified
                    # array for multi, raw string for single — that's
                    # what the relocated hidden input carries).
                    _new_value = ClientExpression("$event.target.value")
                    _new_query = ClientExpression("$event.target.value")
                    with ui.flex(justify="center"):
                        ui.combobox(
                            options=COUNTRIES[:8],
                            placeholder="Pick anything",
                            on_change=cevents.log.push(_new_value),
                            on_focus=cevents.log.push("focus"),
                            on_blur=cevents.log.push("blur"),
                            on_search=cevents.log.push(_new_query),
                        )

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text(
                            "Live log (client-reactive — no refresh)",
                            color="muted", size="sm",
                        )
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    ui.divider()

                    log_text = ClientExpression(
                        '($bz.state.ComboboxClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — @change relocated onto the "
                        "hidden input ; the client expression pushes "
                        "the picked value onto the bound list.",
                        serialize_html(
                            ui.combobox(
                                options=COUNTRIES[:3],
                                placeholder="Pick anything",
                                on_change=cevents.log.push(_new_value),
                            )
                        ),
                    )
