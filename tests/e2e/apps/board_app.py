"""Dedicated e2e fixture — a card board whose per-card menu is teleported.

This is NOT ``examples/kanban`` : it is a stable, test-owned app whose only
job is to exercise the contract ``tests/e2e/test_dropdown_action.py``
asserts on. Migrated off the example on 2026-08-16 — same reason as
``todo_app.py`` and ``counter_app.py``, and the coupling was live :
``examples/kanban/main.py`` was touched the very day of the migration.

The contract under test, and why it needs a real browser
---------------------------------------------------------
A ``dropdown`` panel is **teleported** under ``<body>``. Its items carry a
server action, so their ``hx-post`` must be processed by htmx *after every
re-projection* — not just the first. The regression this guards (traps.md
§ « Teleported ``hx-post`` mort après un refresh ») made the FIRST Move
fire and every later one die silently : the refresh re-projected the panel
clone with ``scan`` only, never ``htmx.process``, so the click ran the
client-side close and nothing else. Both paths return 200 ; only a browser
that clicks twice sees the difference.

Structural contract with the test — do not reshape casually :

- each column heading is an ``<h3>`` whose PARENT holds a ``<span>`` badge
  carrying the count (the test parses that text) ;
- the trigger exposes ``aria-haspopup="menu"`` ;
- the items read ``Move`` and ``Delete`` ;
- the handlers are named ``move_task`` / ``delete_task`` — the test matches
  the POST url against those names ;
- **``To do`` seeds exactly 2 cards** : the test waits for that badge to
  drop to ``1`` to know the board swap has landed before the second move.
"""

from __future__ import annotations

from functools import partial

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import SessionState, field

COLUMNS = [("todo", "To do"), ("doing", "In progress"), ("done", "Done")]
NEXT = {"todo": "doing", "doing": "done", "done": "todo"}


def seed_tasks() -> list[dict]:
    """Two ``todo``, one ``doing`` — see the structural contract above.

    Ids are STABLE, never ``uuid4`` : a ``default_factory`` on a server
    state is re-evaluated on every request until the first mutation
    persists it, so random ids would be re-minted at each render and the
    Move/Delete button ids would never match the store at handler time.
    The action would fail from the very first click, for a reason having
    nothing to do with the bug under test.
    """
    raw = [
        ("Design the landing hero", "todo"),
        ("Write API docs", "todo"),
        ("Wire the checkout flow", "doing"),
    ]
    return [
        {"id": f"seed-task-{i}", "title": title, "column": column}
        for i, (title, column) in enumerate(raw)
    ]


class BoardStore(SessionState):
    """Per-cookie board — a fresh browser context starts from the seed."""

    tasks: list[dict] = field(default_factory=seed_tasks)


def move_task(task_id: str) -> None:
    store = BoardStore()
    store.tasks = [
        {**t, "column": NEXT[t["column"]]} if t["id"] == task_id else t
        for t in store.tasks
    ]


def delete_task(task_id: str) -> None:
    store = BoardStore()
    store.tasks = [t for t in store.tasks if t["id"] != task_id]


def task_card(task: dict) -> None:
    with ui.card(padding="sm"):
        with ui.hstack(justify="between", align="start", gap="sm"):
            ui.text(task["title"], weight="medium", size="sm")
            # The teleported panel : this is the whole point of the fixture.
            with ui.dropdown(
                trigger=ui.icon_button(
                    "ellipsis-vertical", variant="ghost", size="xs",
                    tooltip="Actions",
                ),
            ):
                ui.dropdown_item(
                    label="Move →", icon_left="arrow-right",
                    on_click=partial(move_task, task["id"]),
                )
                ui.dropdown_item(
                    label="Delete", icon_left="trash-2", color="error",
                    on_click=partial(delete_task, task["id"]),
                )


@refreshable(deps=[BoardStore])
def board() -> None:
    """Refreshing this zone re-projects every teleported panel clone —
    which is exactly the moment the guarded bug used to strike."""
    tasks = BoardStore().tasks
    with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
        for col_key, col_label in COLUMNS:
            col_tasks = [t for t in tasks if t["column"] == col_key]
            with ui.vstack(gap="sm", classes="bg-text/5 rounded-lg p-3 min-h-40"):
                with ui.hstack(justify="between", align="center"):
                    ui.heading(col_label, level=3, size="sm")
                    ui.badge(
                        str(len(col_tasks)), variant="soft",
                        color="muted", size="xs",
                    )
                for task in ui.each(col_tasks, key="id"):
                    task_card(task)


@page("/")
def home() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("Sprint board", level=1, size="2xl")
        board()


app = Bretzel(
    secret_key="e2e-board-fixture-secret",
    title="e2e fixture · board",
    mode="dev",
)
app.include(__name__)
