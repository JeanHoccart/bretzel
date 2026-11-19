# A list shared live

> Two people should see the same to-do list, and what one adds, ticks or deletes should show up on the other's screen right away.

Save it as `app.py`, run `bretzel dev app:app`, and open http://127.0.0.1:8000 in two windows.

```python
"""A task list shared by everyone who opens it, live in every window."""

import sys
from functools import partial

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import AppState, PageState, field


class Tasks(AppState):
    """One list on the server, the same for every visitor."""

    items: list[dict] = field(default_factory=list)


class NewTask(PageState):
    label: str = field(default="")


def add(new: NewTask) -> None:
    label = str(new.label).strip()
    if not label:
        return
    with Tasks.lock() as tasks:
        number = max((task["id"] for task in tasks.items), default=0) + 1
        tasks.items = [*tasks.items, {"id": number, "label": label, "done": False}]
    new.label = ""


def toggle(task_id: int) -> None:
    with Tasks.lock() as tasks:
        tasks.items = [
            {**task, "done": not task["done"]} if task["id"] == task_id else task
            for task in tasks.items
        ]


def remove(task_id: int) -> None:
    with Tasks.lock() as tasks:
        tasks.items = [task for task in tasks.items if task["id"] != task_id]


@refreshable
def task_list() -> None:
    items = Tasks().items
    with ui.vstack(gap="sm"):
        if not items:
            ui.text("Nothing to do yet.", color="muted")
        for task in ui.each(items, key="id"):
            with ui.hstack(justify="between", align="center"):
                ui.checkbox(label=task["label"], checked=task["done"],
                            on_change=partial(toggle, task["id"]))
                ui.icon_button("trash-2", variant="ghost", size="sm", tooltip="Delete",
                               on_click=partial(remove, task["id"]))


@refreshable
def new_task_form() -> None:
    with ui.form(on_submit=add), ui.hstack(gap="sm"):
        ui.input(value=NewTask().label, placeholder="A new task", classes="flex-1")
        ui.button("Add", type="submit", icon_left="plus")


@page("/", title="Shared tasks")
def home() -> None:
    with ui.container(width="sm", classes="py-8"), ui.vstack(gap="lg"):
        ui.heading("Shared tasks", level=1)
        new_task_form()
        task_list()


app = Bretzel(title="Shared tasks")
app.include(sys.modules[__name__])
```

## Why it works

- `Tasks` is an `AppState`: one copy on the server for every visitor. The page subscribes to what its zones read, so when another window changes `Tasks`, `task_list` redraws here through the live stream (SSE). There is nothing to publish and no dependency to declare.
- **The trap: two people writing at once.** Each change rewrites the list inside `Tasks.lock()`, which re-reads it fresh. Without the lock, two deletions at the same moment put back what the other one removed.
- A list is reassigned, never changed in place: `tasks.items.append(...)` would redraw nothing.
- `ui.each(items, key="id")` keeps each row's identity when the list moves, so a tick stays on its task.
- The tasks live in memory, and a restart forgets them; `Bretzel(state_url="sqlite:///tasks.db")` keeps them.
