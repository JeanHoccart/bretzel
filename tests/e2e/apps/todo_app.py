"""Dedicated e2e fixture — a minimal TODO app the browser suite drives.

This is NOT ``examples/todo`` : it is a stable, test-owned app whose only
job is to exercise the framework contracts ``tests/e2e/test_todo.py``
asserts on, so the example is free to evolve for demo reasons without ever
breaking e2e again (that coupling is exactly what silently killed the old
suite — see ``tests/consistency/test_fixture_apps_import``).

Contracts covered, one primitive each :

- **Server action round-trip** — add / toggle / delete mutate ``TodoStore``
  (SessionState) then ``refresh`` the zones that read it.
- **Server validator** — an empty label is rejected server-side (the
  authoritative gate, independent of the HTML5 ``required``).
- **Pure-client filter** — ``Filter`` (ClientState) drives each row's
  ``visible=`` expression ; flipping the tab is zero round-trip.
- **Persistence** — the list lives in SessionState (survives reload),
  the filter in ``persist="session"`` (survives reload, per-tab).
- **Isolation** — SessionState is keyed by cookie, so a fresh browser
  context sees an empty list.
- **Icon-only affordance** — the delete button is an ``icon_button`` with
  an accessible name via ``tooltip``.
"""

from __future__ import annotations

from functools import partial

from bretzel import Bretzel, page, refresh, refreshable, ui
from bretzel.state import ClientState, PageState, SessionState, field

# ───────────────────────────────────────────────────────────────────────────
# State
# ───────────────────────────────────────────────────────────────────────────


class TodoStore(SessionState):
    """Per-cookie task list. Session scope → fresh browser context = empty."""

    items: list[dict] = field(default_factory=list)
    seq: int = field(default=0)  # monotonic id source (deterministic — no random factory)


class AddForm(PageState):
    """Hydrated from the add form's submission."""

    label: str = field(default='')


class Filter(ClientState, persist="session"):
    """Pure-client filter tab. sessionStorage → survives reload, per-tab.

    ``mode`` is only ever set client-side to a known value by the filter
    buttons, so no server-side validator is needed here.
    """

    mode: str = field(default='all')


# ───────────────────────────────────────────────────────────────────────────
# Handlers (all module-level — resolved via sys.modules)
# ───────────────────────────────────────────────────────────────────────────


def add(form: AddForm) -> None:
    label = form.label.strip()
    if not label:
        return  # server-authoritative reject — empty state stays
    store = TodoStore()
    store.seq += 1
    store.items = [*store.items, {"id": str(store.seq), "label": label, "done": False}]
    refresh(todo_list)
    refresh(remaining)


def toggle(task_id: str) -> None:
    store = TodoStore()
    store.items = [
        {**it, "done": not it["done"]} if it["id"] == task_id else it
        for it in store.items
    ]
    refresh(todo_list)
    refresh(remaining)


def delete(task_id: str) -> None:
    store = TodoStore()
    store.items = [it for it in store.items if it["id"] != task_id]
    refresh(todo_list)
    refresh(remaining)


# ───────────────────────────────────────────────────────────────────────────
# Render
# ───────────────────────────────────────────────────────────────────────────


def row_visible(done: bool):
    """Client expression : a row shows iff the filter tab matches its state."""
    mode = Filter().mode
    expected = "completed" if done else "active"
    return (mode == "all") | (mode == expected)


def render_row(it: dict) -> None:
    with ui.hstack(gap="sm", align="center", visible=row_visible(it["done"])):
        ui.checkbox(checked=it["done"], on_change=partial(toggle, it["id"]))
        ui.text(it["label"], size="sm", classes="flex-1")
        ui.icon_button(
            "trash-2",
            on_click=partial(delete, it["id"]),
            tooltip="Delete task",
            # Icon-only button : ``tooltip`` gives a visual label but no
            # accessible NAME, so set one explicitly for role-based queries
            # and screen readers.
            attrs={"aria-label": "Delete task"},
            variant="ghost",
            size="sm",
            color="error",
        )


@refreshable(deps=[TodoStore])
def todo_list() -> None:
    items = TodoStore().items
    if not items:
        ui.text("No tasks yet — add one above.", color="muted")
        return
    with ui.vstack(gap="xs"):
        for it in ui.each(items, key="id"):
            render_row(it)


@refreshable(deps=[TodoStore])
def remaining() -> None:
    active = sum(1 for it in TodoStore().items if not it["done"])
    word = "task" if active == 1 else "tasks"
    ui.text(f"{active} {word} remaining", size="sm", color="muted")


@page("/")
def home() -> None:
    form = AddForm()
    flt = Filter()
    with ui.vstack(gap="lg", classes="max-w-md mx-auto py-8 px-6"):
        ui.heading("Todo", level=1, size="2xl")

        with ui.form(on_submit=add), ui.hstack(gap="sm", align="center"):
            ui.input(
                value=form.label,
                placeholder="What needs doing?",
                required=True,
                classes="flex-1",
            )
            ui.button("Add", type="submit", color="primary")

        with ui.hstack(gap="sm", align="center"):
            ui.button("All", on_click=flt.mode.set("all"), variant="ghost", size="sm")
            ui.button(
                "Active", on_click=flt.mode.set("active"), variant="ghost", size="sm"
            )
            ui.button(
                "Completed",
                on_click=flt.mode.set("completed"),
                variant="ghost",
                size="sm",
            )

        todo_list()
        remaining()


# ───────────────────────────────────────────────────────────────────────────
# App
# ───────────────────────────────────────────────────────────────────────────


app = Bretzel(
    secret_key="dev-e2e-todo-fixture-secret",
    title="Bretzel · e2e todo fixture",
    mode="dev",
)
app.include(__name__)


if __name__ == "__main__":
    app.run(port=8000)
