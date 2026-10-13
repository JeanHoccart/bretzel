"""The board — Conway's Game of Life on a 40 × 40 torus.

The server computes, the browser draws : the live cells travel in the
``Board`` client state, :func:`step` answers with the next generation,
and each cell's ``classes=`` binding re-colours it. The cells are
rendered once, with the page.
"""

from __future__ import annotations

import random
from collections import Counter
from functools import partial

from bretzel import page, ui
from bretzel.state import ClientBinding, ClientState, field
from examples.life.features.shell import shell

# ── Routing ──────────────────────────────────────────────────────────
PATH = "/"

# ── The grid ─────────────────────────────────────────────────────────
SIZE = 40
CELLS = SIZE * SIZE
TICK_SECONDS = 0.2
DENSITY = 0.25    # share of live cells drawn by Random
LIVE = "bg-text!"  # the text colour contrasts with the surface in both themes

# Gosper's glider gun, the first pattern known to grow forever.
GOSPER_GUN = """
........................O...........
......................O.O...........
............OO......OO............OO
...........O...O....OO............OO
OO........O.....O...OO..............
OO........O...O.OO....O.O...........
..........O.....O.......O...........
...........O...O....................
............OO......................
"""


def cells_of(picture: str, top: int, left: int) -> list[int]:
    """Indices of the ``O`` marks of ``picture``, drawn from (top, left)."""
    return [
        (top + row) * SIZE + left + col
        for row, line in enumerate(picture.strip().splitlines())
        for col, mark in enumerate(line)
        if mark == "O"
    ]


def glider_gun() -> list[int]:
    return cells_of(GOSPER_GUN, top=1, left=2)


def neighbours_of(cell: int) -> tuple[int, ...]:
    """The eight neighbours of ``cell`` — edges wrap around (a torus)."""
    row, col = divmod(cell, SIZE)
    return tuple(
        ((row + dr) % SIZE) * SIZE + (col + dc) % SIZE
        for dr in (-1, 0, 1)
        for dc in (-1, 0, 1)
        if dr or dc
    )


NEIGHBOURS = tuple(neighbours_of(cell) for cell in range(CELLS))


def next_generation(alive: set[int]) -> set[int]:
    """Birth on 3 neighbours, survival on 2 or 3."""
    counts = Counter(n for cell in alive for n in NEIGHBOURS[cell])
    return {
        cell for cell, n in counts.items()
        if n == 3 or (n == 2 and cell in alive)
    }


# ── State ────────────────────────────────────────────────────────────


class Board(ClientState):
    """The live cells and the generation count, written by the server only."""

    alive: list[int] = field(default_factory=glider_gun)
    generation: int = field(default=0)


class Play(ClientState):
    """The run/pause gate — a client signal, so Pause stops the
    ``ui.interval`` with no round trip.

    Not a field of ``Board`` : a server write sends the WHOLE client
    state back, so a Pause clicked while a tick is in flight would be
    undone by that tick's response.
    """

    active: bool = field(default=False)


# ── Logic (handlers) ─────────────────────────────────────────────────


def live_cells(board: Board) -> set[int]:
    """The posted live cells, minus anything off the grid.

    The list comes back from the browser : the server does not trust it.
    """
    return {cell for cell in board.alive if 0 <= cell < CELLS}


def step() -> None:
    """One generation — fired by ``ui.interval`` while playing, or by Step."""
    board = Board()
    board.alive = sorted(next_generation(live_cells(board)))
    board.generation += 1


def toggle(cell: int) -> None:
    board = Board()
    board.alive = sorted(live_cells(board) ^ {cell})


def randomize() -> None:
    board = Board()
    board.alive = [cell for cell in range(CELLS) if random.random() < DENSITY]
    board.generation = 0


def clear() -> None:
    board = Board()
    board.alive = []
    board.generation = 0


# ── UI ───────────────────────────────────────────────────────────────


def stat(label: str, value: ClientBinding) -> None:
    with ui.vstack(gap="none", align="end"):
        ui.text(label, size="xs", color="muted")
        ui.text(value, weight="semibold", classes="tabular-nums")


@page(PATH, layout=shell, title="Life")
def life_page() -> None:
    board = Board()
    play = Play()
    alive = board.alive

    ui.interval(on_tick=step, seconds=TICK_SECONDS, active=play.active)

    with ui.vstack(gap="md", align="center", classes="w-fit"):
        with ui.hstack(justify="between", align="end", classes="w-full"):
            ui.heading("Game of Life", level=1, size="lg")
            with ui.hstack(gap="lg"):
                stat("Generation", board.generation)
                stat("Alive", alive.length())

        # Cells in whole pixels : at a fractional width the 1 px gaps
        # round to 1 or 2 px. The classes are written whole, since the
        # production stylesheet only holds the classes it reads here ;
        # ``gap-px!`` beats the grid's default ``gap-4``.
        with ui.grid(
            classes="grid-cols-[repeat(40,7px)] sm:grid-cols-[repeat(40,10px)] "
                    "gap-px! p-px rounded-box bg-text/10",
        ):
            for cell in range(CELLS):
                ui.card(
                    padding="none",
                    on_click=partial(toggle, cell),
                    classes=alive.contains(cell).then_else(LIVE, ""),
                    slots={"root": "aspect-square rounded-xs! border-0! cursor-pointer"},
                )

        # Step and Clear also pause : both mean "look at this board".
        with ui.hstack(gap="sm", justify="center", wrap=True):
            ui.button(
                "Play", icon_left="play", color="success",
                on_click=play.active.set(True), visible=~play.active,
            )
            ui.button(
                "Pause", icon_left="pause", color="warning",
                on_click=play.active.set(False), visible=play.active,
            )
            ui.button(
                "Step", icon_left="skip-forward", variant="soft",
                on_click=[step, play.active.set(False)],
            )
            ui.button(
                "Random", icon_left="shuffle", variant="soft",
                on_click=randomize,
            )
            ui.button(
                "Clear", icon_left="eraser", variant="soft",
                on_click=[clear, play.active.set(False)],
            )
