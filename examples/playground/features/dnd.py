"""``Dropzone`` / ``Draggable`` / ``drag_each`` test bench.

Follows ``.claude/bretzel/playground-pattern.md``'s template. Applicable
sections: §1 Reference, §2 Edge cases / Composability / A11y (no `Slots`
— the family has no named slot), §3 Server playground, §4 Server events,
§6 Client events. **No §5** (`BINDABLE_PROPS` is empty on both sides: a
zone carries no value) and no §7 (no imperative API).

What this page exercises and no other playground page does: the complete
optimistic loop — the browser moves the card BEFORE any request, the drop
posts a ``Move``, the handler mutates or refuses, and the morph re-pairs
the moved node instead of recreating it. The refusal has no code path of
its own: the card that comes back is the server render contradicting the
optimistic DOM.
"""

from bretzel import refreshable, ui
from bretzel.components import Move
from bretzel.render import serialize_html
from bretzel.state import ClientState, PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/dnd"

COLORS = ["primary", "secondary", "success", "warning", "error", "info", "muted"]
MOVE_MODES = ["none", "server", "client"]


# ───────────────────────────────────────────────────────────────────────
# State
# ───────────────────────────────────────────────────────────────────────


class DndPlayground(PageState):
    """§3 — one field per prop, plus the universal escape hatches and
    modifiers, as the template requires."""

    # Props Dropzone.
    name:    str = field(default="bench")
    accepts: str = field(default="")
    locked:  bool = field(default=False)
    color:   str = field(default="primary")
    # Draggable props (carried by drag_each).
    group:    str = field(default="")
    handle:   bool = field(default=False)
    disabled: bool = field(default=False)
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible: str = field(default="on")
    tooltip: str = field(default="")
    # Event-handler shape.
    on_move_mode: str = field(default="none")
    # The data the bench reorders.
    items: list = field(default_factory=lambda: ["Alpha", "Bravo", "Charlie"])


class DndEvents(PageState):
    """§4 — the server event log."""

    log:   list = field(default_factory=list)
    items: list = field(default_factory=lambda: ["Un", "Deux", "Trois"])


class Board(PageState):
    """§2 Composability — two zones swapping cards, and a server refusal
    to make the snap-back demonstrable."""

    todo:    list = field(default_factory=lambda: ['Write the spec',
                                                   'Re-read the scoping'])
    done:    list = field(default_factory=lambda: ['Pick the events'])
    refused: int = field(default=0)


#: The demo's business rule. A CAPACITY, chosen because it is
#: **reversible**: the first version refused to leave "Done", which
#: trapped every card for good — and a bench one cannot come back from
#: reads as a failure, not as a rule. A ceiling is understood at the
#: first refusal and is undone by taking a card out.
DONE_CAPACITY = 2


class Locked(PageState):
    """§2 Edge cases — the bin: it accepts, it returns nothing."""

    kept: list = field(default_factory=lambda: ["Ne sort jamais"])
    free: list = field(default_factory=lambda: ["Peut partir"])


class Preview(PageState):
    """§2 Edge cases — two chairs, and a drop that SWAPS."""

    chair_l: list = field(default_factory=lambda: ["Jeanne"])
    chair_r: list = field(default_factory=lambda: ["Theo"])


class DndClientEvents(ClientState, persist="memory"):
    """§6 — the client log, written with no round trip at all."""

    log: list = field(default_factory=list)


# ───────────────────────────────────────────────────────────────────────
# Handlers (module scope — adressables en ``module::qualname``)
# ───────────────────────────────────────────────────────────────────────


def apply_move(columns: dict[str, list], m: Move) -> bool:
    """Remove from one zone, insert into the other. Mutates ``columns``
    in place and returns ``True`` if something moved.

    ``to_index`` is read from the DOM AFTER the optimistic move, so it
    already names the final position: we remove first, insert next,
    without correcting the index. A reorder within a single zone is the
    case where ``from_zone == to_zone`` — not another piece of code.

    ⚠️ This function carried the comment "written ONCE" while TWO
    handlers rewrote the same block just below. It is true now: all FOUR
    callers go through here (reorder_bench, log_move, move_card,
    move_locked).
    """
    source, target = columns.get(m.from_zone), columns.get(m.to_zone)
    if source is None or target is None:
        return False
    if not (0 <= m.from_index < len(source)):
        return False
    target.insert(min(m.to_index, len(target)), source.pop(m.from_index))
    return True


def reorder_bench(m: Move) -> None:
    state = DndPlayground()
    columns = {m.from_zone: list(state.items)}
    if apply_move(columns, m):
        state.items = columns[m.from_zone]


def log_move(m: Move) -> None:
    state = DndEvents()
    columns = {m.from_zone: list(state.items)}
    if apply_move(columns, m):
        state.items = columns[m.from_zone]
    state.log = [
        f"move · {m.item_key} : {m.from_index} → {m.to_index}"
        f"' (same zone: '{m.same_zone})",
        *state.log,
    ][:8]


def move_card(m: Move) -> None:
    """A move between zones, with a real refusal.

    The refusal does not raise and calls nothing: it does not mutate. The
    render that follows returns the previous order, and the morph puts
    the card back.
    """
    state = Board()
    # Refusing, here, is mutating nothing — not raising, not calling a
    # `reject()`. The render that follows returns the previous order and
    # the morph brings the card back.
    if (m.to_zone == "done" and not m.same_zone
            and len(state.done) >= DONE_CAPACITY):
        state.refused = state.refused + 1
        return

    columns = {"todo": list(state.todo), "done": list(state.done)}
    if apply_move(columns, m):
        state.todo, state.done = columns["todo"], columns["done"]


def swap_chair(m: Move) -> None:
    """A zone holding ONE element: the drop SWAPS.

    It is this file's only handler that does not insert. It is there for
    that: to show the case where an insertion gap would be a lie —
    nothing slides between two neighbours, somebody is displaced.
    """
    state = Preview()
    zones = {"chair_l": list(state.chair_l), "chair_r": list(state.chair_r)}
    source, cible = zones.get(m.from_zone), zones.get(m.to_zone)
    if source is None or cible is None or source is cible or not source:
        return
    occupant = cible.pop(0) if cible else None
    cible.append(source.pop(0))
    if occupant is not None:
        source.append(occupant)
    state.chair_l, state.chair_r = zones["chair_l"], zones["chair_r"]


def reset_board() -> None:
    """Reset the bench. A bench where a state cannot be undone is a bench
    one can only try once."""
    state = Board()
    state.todo = ['Write the spec', 'Re-read the scoping']
    state.done = ['Pick the events']
    state.refused = 0


def move_locked(m: Move) -> None:
    state = Locked()
    columns = {"kept": list(state.kept), "free": list(state.free)}
    if apply_move(columns, m):
        state.kept, state.free = columns["kept"], columns["free"]


def server_changed(state: DndPlayground) -> None:
    """A typed parameter — the dispatcher hydrates the changed control's
    value into ``state`` (coerced + persisted). No ``**kwargs``, no
    ``setattr``, no ``name=`` to set by hand: it is every bench page's
    idiom, and an example stays in tier 1."""


def clear_log() -> None:
    DndEvents().log = []


# ───────────────────────────────────────────────────────────────────────
# Template helpers (allowed at module scope)
# ───────────────────────────────────────────────────────────────────────


def parse_extra_attrs(blob: str) -> dict:
    """``k=v`` per line → dict. Lines with no ``=`` are ignored."""
    out: dict = {}
    for line in (blob or "").splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            if key:
                out[key] = value.strip()
    return out


def control(label: str) -> object:
    """A labelled control cell: the prop's name in grey above whatever
    the caller puts in the ``with``."""
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


def build_preview(state: DndPlayground) -> object:
    """State → kwargs. An empty string means "kwarg absent"."""
    attrs = parse_extra_attrs(state.extra_attrs)
    if state.aria_label:
        attrs["aria-label"] = state.aria_label

    kwargs: dict = {
        "name": state.name or None,
        "locked": state.locked,
        "color": state.color,
    }
    if state.accepts:
        kwargs["accepts"] = [g.strip() for g in state.accepts.split(",") if g.strip()]
    if state.classes:
        kwargs["classes"] = state.classes
    if state.custom_id:
        kwargs["id"] = state.custom_id
    if state.style:
        kwargs["style"] = state.style
    if attrs:
        kwargs["attrs"] = attrs
    if state.tooltip:
        kwargs["tooltip"] = state.tooltip
    kwargs["visible"] = state.visible != "off"

    if state.on_move_mode == "server":
        kwargs["on_move"] = reorder_bench
    elif state.on_move_mode == "client":
        kwargs["on_move"] = "console.log('move')"

    zone = ui.dropzone(**kwargs)
    with zone, ui.vstack(gap="sm"):
        for label in ui.drag_each(
            state.items,
            group=state.group or None,
            handle=state.handle,
            disabled=(lambda _row: True) if state.disabled else None,
        ):
            with ui.card(padding="sm"):
                ui.text(label)
    return zone


def card(label: str) -> None:
    with ui.card(padding="sm"):
        ui.text(label)


# ───────────────────────────────────────────────────────────────────────
# §3 — Server playground
# ───────────────────────────────────────────────────────────────────────


@refreshable(deps=[DndPlayground])
def server_playground() -> None:
    state = DndPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("name"):
            ui.input(value=state.name, on_change=server_changed)
        with control("accepts"):
            ui.input(value=state.accepts, on_change=server_changed)
        with control("group"):
            ui.input(value=state.group, on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c.title()) for c in COLORS],
                      on_change=server_changed)
        with control("on_move"):
            ui.select(value=state.on_move_mode,
                      options=[(m, m.title()) for m in MOVE_MODES],
                      on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "On"), ("off", "Off")],
                      on_change=server_changed)
        with control("locked"):
            ui.switch(checked=state.locked, label="locked",
                      on_change=server_changed)
        with control("handle"):
            ui.switch(checked=state.handle, label="handle",
                      on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, label="disabled",
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, on_change=server_changed)
        with control("custom_id"):
            ui.input(value=state.custom_id, on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, on_change=server_changed)
        with control("aria_label"):
            ui.input(value=state.aria_label, on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, on_change=server_changed)
        with control("attrs (k=v par ligne)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        on_change=server_changed)

    ui.divider()
    # A LIVE instance, one for the HTML block — cf. ``client_events``'s
    # comment: ``serialize_html`` detaches its argument.
    build_preview(state)
    emitted_html_block("Emitted HTML", serialize_html(build_preview(state)))


# ───────────────────────────────────────────────────────────────────────
# §4 — Server events
# ───────────────────────────────────────────────────────────────────────


@refreshable(deps=[DndEvents])
def server_events() -> None:
    state = DndEvents()
    with ui.dropzone(name="events", on_move=log_move), ui.vstack(gap="sm"):
        for label in ui.drag_each(state.items):
            card(label)

    ui.button('Clear the log', on_click=clear_log, variant="ghost", size="sm")
    with ui.vstack(gap="xs"):
        for line in state.log or ["(aucun event)"]:
            ui.text(line, size="sm", color="muted")

    representative = ui.dropzone(name="sample", on_move=log_move)
    with representative:
        with ui.draggable(key="a"):
            ui.text("A")
    emitted_html_block(
        'Emitted HTML (Dropzone with a server on_move)',
        serialize_html(representative),
    )


# ───────────────────────────────────────────────────────────────────────
# §6 — Client events
# ───────────────────────────────────────────────────────────────────────


def client_events() -> None:
    log = DndClientEvents()

    # ⚠️ TWO instances, and it is not duplication: ``serialize_html``
    # DETACHES what it is given (its docstring says so — otherwise the
    # component would render twice). So serialising the demo zone made it
    # disappear from the page: the card showed only a code block, with
    # nothing to grab. The stand-in is there for the HTML, the live zone
    # for the gesture — it is what the §4 card already does.
    with ui.dropzone(name="client", on_move=log.log.push("move")):
        with ui.vstack(gap="sm"):
            for label in ui.drag_each(["Un", "Deux", "Trois"]):
                card(label)
    ui.text("Journal client (aucun aller-retour) :", size="sm", color="muted")
    ui.text(log.log, size="sm", color="muted")

    representative = ui.dropzone(name="client_sample", on_move=log.log.push("move"))
    with representative:
        with ui.draggable(key="a"):
            ui.text("A")
    emitted_html_block(
        'Emitted HTML (Dropzone with a client on_move)',
        serialize_html(representative),
    )


# ───────────────────────────────────────────────────────────────────────
# §2 — Composability / Edge cases
# ───────────────────────────────────────────────────────────────────────


@refreshable(deps=[Board])
def composability() -> None:
    state = Board()
    with ui.grid(cols=2, gap="md"):
        for key, title, rows in [("todo", 'To do', state.todo),
                                 ("done", 'Done', state.done)]:
            with ui.vstack(gap="sm"):
                ui.heading(title, level=4)
                with ui.dropzone(name=key, accepts=["card"], on_move=move_card):
                    with ui.vstack(gap="sm"):
                        for label in ui.drag_each(rows, group="card", handle=True):
                            card(label)
    with ui.hstack(gap="sm", align="center"):
        ui.text(
            f"'“Done” accepts '{DONE_CAPACITY}' cards at most — server refusal: '{state.refused}",
            size="sm", color="muted",
        )
        ui.button('Reset', on_click=reset_board,
                  variant="ghost", size="sm")


@refreshable(deps=[Locked])
def edge_cases() -> None:
    state = Locked()
    with ui.grid(cols=2, gap="md"):
        with ui.vstack(gap="sm"):
            ui.heading("locked=True — rien ne sort", level=4)
            with ui.dropzone(name="kept", accepts=["any"], locked=True,
                             color="error", on_move=move_locked):
                with ui.vstack(gap="sm"):
                    for label in ui.drag_each(state.kept, group="any"):
                        card(label)
        with ui.vstack(gap="sm"):
            ui.heading("zone libre", level=4)
            with ui.dropzone(name="free", accepts=["any"], color="success",
                             on_move=move_locked):
                with ui.vstack(gap="sm"):
                    for label in ui.drag_each(state.free, group="any"):
                        card(label)


@refreshable(deps=[Preview])
def apercu_en_vol() -> None:
    """What the gesture SHOWS: the item in flight becomes a SLOT.

    ⚠️ This bench compared two columns — the default on one side, the
    proposal on the other — until 2026-09-13. The proposal IS the default
    since: keeping the comparison would show the same thing twice. What
    is left here is the case the default does NOT cover.

    A zone holding ONE element: the drop swaps. Nothing slides between
    two neighbours, somebody is displaced — and the thin slot, which
    narrates an insertion, then has nothing right to say.
    """
    state = Preview()
    with ui.hstack(gap="lg"):
        for zone_name, occupants in (("chair_l", list(state.chair_l)),
                                    ("chair_r", list(state.chair_r))):
            with (
                ui.dropzone(name=zone_name, accepts=["chair"],
                            holds="one", on_move=swap_chair,
                            color="primary"),
                ui.vstack(gap="none", align="center", justify="center",
                          classes="min-h-24 w-28 rounded-lg border "
                                  "border-dashed border-text/25 p-2"),
            ):
                for who in ui.drag_each(occupants, group="chair"):
                    with ui.vstack(gap="xs", align="center"):
                        ui.avatar(name=who, size="lg", shape="circle")
                        ui.text(who, size="sm")
    ui.text(
        'holds="one": the zone says it holds only ONE occupant. The '
            'gesture then stops sliding the card into it — it would hold two '
            'for the duration of the hover, and that is what "takes up an '
            'enormous amount of space" — and marks it as OVERWRITABLE: a '
            'solid outline and a ring, where a zone accepting an insertion '
            'stays dashed. The drop still reaches the handler, which decides '
            'to swap or to refuse.',
        color="muted", size="sm",
    )


# ───────────────────────────────────────────────────────────────────────
# Page
# ───────────────────────────────────────────────────────────────────────


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Drag & drop", level=1)
        ui.text(
            'Three bricks: ui.dropzone (the zone), ui.draggable (a '
                'grabbable item) and ui.drag_each (the sugar that wraps a '
                'list). The gesture is Pointer Events — mouse: drag after ~5 '
                'px; touch: long press ~250 ms. The server stays the truth: a'
                ' handler that mutates nothing brings the card back.',
            color="muted",
        )

        # ── §1 Reference ────────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Reference", level=2)
            ui.text("Balayage visuel de chaque prop.", color="muted", size="sm")

            ui.heading('Basic — a list that reorders itself', level=3)
            with ui.dropzone(name="ref_basic"), ui.vstack(gap="sm"):
                for label in ui.drag_each(["Alpha", "Bravo", "Charlie"]):
                    card(label)

            ui.heading("handle=True", level=3)
            ui.text(
                'The whole card becomes inert: only the handle catches. A'
                    ' restriction, not the default gesture.',
                color="muted", size="sm",
            )
            with ui.dropzone(name="ref_handle"), ui.vstack(gap="sm"):
                for label in ui.drag_each(['With a handle', "Idem", "Idem"],
                                          handle=True):
                    card(label)

            ui.heading('disabled — one predicate per item', level=3)
            ui.text(
                '⚠️ disabled means “cannot be grabbed”, NOT “does not '
                    'move”. Drag a free card past the middle one: it cannot '
                    'be picked up, but its index changes — going past a '
                    'neighbour is exactly what reordering a list is. The same'
                    ' semantics as Sortable.js and dnd-kit.',
                color="muted", size="sm",
            )
            with ui.dropzone(name="ref_disabled"), ui.vstack(gap="sm"):
                for label in ui.drag_each(
                    ["Libre", 'Not typeable', "Libre"],
                    disabled=lambda row: row == 'Not typeable',
                ):
                    card(label)

            ui.heading('ui.draggable placed by hand', level=3)
            ui.text(
                'Without drag_each: the component in an ordinary loop. '
                    'key= becomes mandatory again — no each supplies it — and'
                    ' every prop is passed explicitly.',
                color="muted", size="sm",
            )
            with ui.dropzone(name="ref_manual"), ui.vstack(gap="sm"):
                for label, is_locked in [("Un", False), ("Deux", False),
                                         ('Not typeable', True)]:
                    with ui.draggable(key=label, group="manual", handle=True,
                                      disabled=is_locked, color="info"):
                        card(label)

            ui.heading('color — visible only DURING a gesture', level=3)
            ui.text(
                'The zone is transparent at rest; the tint arrives with '
                    'data-bz-drop-ok, which only the drag sets. Grab a card '
                    'to see it.',
                color="muted", size="sm",
            )
            with ui.grid(cols=4, gap="sm"):
                for tint in COLORS[:4]:
                    with ui.vstack(gap="xs"):
                        ui.text(tint, size="sm", color="muted")
                        with ui.dropzone(name=f"ref_{tint}", color=tint):
                            with ui.vstack(gap="sm"):
                                for label in ui.drag_each([tint], key=str):
                                    card(label)

        # ── §2 Edge cases ───────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Edge cases", level=2)
            ui.text(
                'accepts= decides what comes IN, locked= what goes OUT — '
                    'two doors, two props. The red zone accepts everything '
                    'its group allows and gives nothing back.',
                color="muted", size="sm",
            )
            edge_cases()

            ui.heading("Zone vide", level=3)
            ui.text(
                'A zone with no item keeps a minimum height, otherwise it'
                    ' would collapse to zero and become impossible to aim at.',
                color="muted", size="sm",
            )
            ui.dropzone(name="empty", accepts=["any"], on_move=move_locked)

            ui.heading('A zone holding ONE element', level=3)
            ui.text(
                'The theme reduces the in-flight item to a slot — that is'
                    ' the default, visible in every list on this page. But a '
                    'slot tells a story of INSERTION: on a zone holding a '
                    'single occupant, the drop swaps, and there is nothing to'
                    ' insert.',
                color="muted", size="sm",
            )
            apercu_en_vol()

            ui.heading('Two independent lists', level=3)
            ui.text(
                'None declares accepts=: each only receives ITS OWN '
                    'items. Without that default, they would swap cards '
                    'because nobody declared anything.',
                color="muted", size="sm",
            )
            with ui.grid(cols=2, gap="md"):
                for zone_name, rows in [("iso_a", ["A1", "A2"]),
                                        ("iso_b", ["B1", "B2"])]:
                    with ui.dropzone(name=zone_name), ui.vstack(gap="sm"):
                        for label in ui.drag_each(rows):
                            card(label)

        # ── §2 Composability ────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Composability", level=2)
            ui.text(
                'Two zones exchanging cards — the kanban is a recipe, not'
                    ' a component. “Done” only accepts two cards: the third '
                    'is REFUSED by the server, which mutates nothing, and it '
                    'is the morph that brings it back — no undo code '
                    'anywhere. Taking a card out frees the space.',
                color="muted", size="sm",
            )
            composability()

        # ── §2 A11y ─────────────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("A11y", level=2)
            ui.text(
                'The handle is a focusable role=button (Tab reaches it) '
                    'and carries an aria-label. It is at least 24×24 px — the'
                    ' WCAG 2.2 § 2.5.8 floor — because a 16 px grip is '
                    'unusable with a finger. No affordance is gated on '
                    ':hover: hovering does not exist on a coarse pointer.',
                color="muted", size="sm",
            )
            with ui.dropzone(name="a11y"), ui.vstack(gap="sm"):
                for label in ui.drag_each(['Tab to reach me', "Puis moi"],
                                          handle=True):
                    card(label)
            ui.text(
                'Escape during a drag cancels and puts the card back '
                    'where it came from.',
                color="muted", size="sm",
            )

        # ── §3 Server playground ────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server playground", level=2)
            ui.text('Every prop, every escape hatch, live.',
                    color="muted", size="sm")
            server_playground()

        # ── §4 Server events ────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server events", level=2)
            ui.text(
                "move is the family's only event. The handler receives a "
                    'typed Move — item_key, from_zone, to_zone, from_index, '
                    'to_index — through the EventPayload injection rule.',
                color="muted", size="sm",
            )
            server_events()

        # ── §6 Client events ────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Client events", level=2)
            ui.text(
                'The same event, as a client expression: zero round '
                    'trips, and the server learns nothing of the move.',
                color="muted", size="sm",
            )
            client_events()
