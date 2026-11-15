"""TOPIC — Drag and drop.

Two components and one object: one declares the zone that ACCEPTS, the
element that IS PICKED UP, and the handler receives what comes from
where and where it goes.

``accepts=`` controls entry from another zone; by default a zone only
reorders its own items. ``locked=`` controls exit, ``holds="one"`` controls
capacity, and ``terminal=True`` marks an action target such as an archive.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell

PATH = "/drag"


@page(PATH, layout=shell, title="Drag and drop · Bretzel docs",
      description="Drag and drop in Python with Bretzel: ui.draggable and ui.dropzone, and a Move object that the server applies or refuses.")
def drag_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading('Drag and drop', level=1, size="3xl")
            ui.text(
                'Reordering a list, dragging a card from one column to '
                'another. The browser makes the gesture, the server '
                'receives the result — and it is the server that decides '
                'whether to apply it.',
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('The two halves', level=2)
                    ui.text(
                        '`ui.dropzone` is the region that accepts; '
                        '`ui.draggable` wraps an item one can grab. Both '
                        'are CONTAINERS: their content is written inside a'
                        ' `with`.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        "with ui.dropzone(name=\"todo\", accepts=[\"task\"],\n"
                        "                 on_move=move_task):\n"
                        "    for t in ui.each(tasks, key=\"id\"):\n"
                        "        with ui.draggable(key=str(t.id), group=\"task\"), ui.card():\n"
                        "            ui.text(t.title)\n",
                        lang="python",
                    )
                    ui.alert(
                        'A zone always lets its own cards be reordered. '
                        'To receive a card from another zone, list its '
                        '`group=` in `accepts=`. With no `accepts=`, '
                        'unrelated zones cannot exchange cards.',
                        color="info", title='Entry is explicit',
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Four drop behaviors', level=2)
                    ui.table(
                        columns=[ui.column("mode", label="Mode"),
                                 ui.column("behavior", label="During the drag")],
                        rows=[
                            {"mode": "Reorder in one zone",
                             "behavior": "The card moves between its neighbors; no `accepts=` is needed."},
                            {"mode": "Move between zones",
                             "behavior": "The destination lists the card's `group=` in `accepts=`."},
                            {"mode": "Single place",
                             "behavior": '`holds="one"` previews replacement without inserting a second card.'},
                            {"mode": "Action target",
                             "behavior": '`terminal=True` reports the drop without inserting the card; use it for archive or delete.'},
                        ],
                        size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('What the handler receives', level=2)
                    ui.text(
                        'A single object, `Move`, with five fields. It '
                        'says everything needed to apply OR refuse the '
                        'gesture — and refusing is a normal case.',
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("champ", label="Field"),
                            ui.column("dit", label="What it says"),
                        ],
                        rows=[
                            {"champ": "item_key",
                             "dit": "the moved item's key — the "
                                    "`ui.draggable(key=…)`'s"},
                            {"champ": "from_zone",
                             "dit": "the departure zone's `name=`"},
                            {"champ": "to_zone",
                             "dit": "the arrival zone's `name=`"},
                            {"champ": "from_index",
                             "dit": 'its original position in the zone'},
                            {"champ": "to_index",
                             "dit": 'the position aimed at on arrival'},
                        ],
                        size="sm",
                    )
                    ui.code(
                        'from bretzel.components import Move\n\ndef on_drop(move: Move) -> None:\n    """What a drop applies — or refuses."""\n    if not move.to_zone.startswith("column-"):\n        return                 # refused, without a word\n    task_id = int(move.item_key)\n    move_in_database(task_id, move.to_zone,\n                     move.to_index)\n',
                        lang="python",
                    )
                    ui.text(
                        '`item_key` is a STRING — that is what the DOM '
                        'carries. A numeric key converts back on arrival, '
                        'and an `int()` that raises on an unexpected value'
                        ' is better than a move made at random.',
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Controlling entry and exit', level=2)
                    ui.text(
                        '`accepts=` controls entry from another zone. '
                        '`locked=True` prevents cards from leaving a zone; '
                        'it can still receive cards. For an archive, combine '
                        '`accepts=`, `locked=True`, and `terminal=True`. '
                        'The handler applies or refuses the action.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        "with ui.dropzone(name=\"archive\", accepts=[\"task\"],\n"
                        "                 locked=True, terminal=True,\n"
                        "                 on_move=archive_task):\n"
                        "    ...\n",
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('The handle', level=2)
                    ui.text(
                        '`handle=True` on the `ui.draggable`: the item is '
                        'no longer grabbed anywhere, but by a dedicated '
                        'area. To be taken as soon as the card itself '
                        'contains controls — without it, dragging on a '
                        'button moves the card instead of clicking.',
                        color="muted", size="sm",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading('A real case, in the repository', level=2)
                    ui.text(
                        '`examples/kanban` lets you reorder cards, move '
                        'them between columns, and archive them in a '
                        'terminal zone. The server enforces each column’s '
                        'work-in-progress limit.',
                        color="muted", size="sm",
                    )
