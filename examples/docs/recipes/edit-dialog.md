# Edit a row in a dialog

> Show my ten customers in a table, with an Edit button on each row that opens a dialog where I change the customer and save.

Save it as `app.py`, run `bretzel dev app:app` and open http://127.0.0.1:8000.

```python
"""Customers in a table; each row opens a dialog that edits it."""

import sys
from functools import partial

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import AppState, PageState, field


def sample_customers() -> list[dict]:
    people = [
        ("Ada Lovelace", "London"), ("Alan Turing", "Manchester"),
        ("Grace Hopper", "New York"), ("Katherine Johnson", "Hampton"),
        ("Linus Torvalds", "Portland"), ("Margaret Hamilton", "Boston"),
        ("Barbara Liskov", "Cambridge"), ("Dennis Ritchie", "Murray Hill"),
        ("Radia Perlman", "Seattle"), ("Ken Thompson", "Atlanta"),
    ]
    return [
        {"id": number, "name": name, "city": city,
         "email": f"{name.split()[0].lower()}@example.com"}
        for number, (name, city) in enumerate(people, start=1)
    ]


class Customers(AppState):
    """The customers, the same for every visitor. In a real app: your database."""

    rows: list[dict] = field(default_factory=sample_customers)


class Draft(PageState):
    """The dialog: which customer, what is typed, and whether it shows."""

    customer_id: int = field(default=0)
    name: str = field(default="")
    email: str = field(default="")
    city: str = field(default="")
    open: bool = field(default=False)


def edit(customer_id: int) -> None:
    row = next(row for row in Customers().rows if row["id"] == customer_id)
    draft = Draft()
    draft.customer_id = customer_id
    draft.name = row["name"]
    draft.email = row["email"]
    draft.city = row["city"]
    draft.open = True


def close(draft: Draft) -> None:
    draft.open = False


def save(draft: Draft) -> None:
    name = str(draft.name).strip()
    if not name:
        ui.notification("A customer needs a name.", color="warning")
        return
    changes = {"name": name, "email": str(draft.email).strip(), "city": str(draft.city).strip()}
    with Customers.lock() as customers:
        customers.rows = [
            {**row, **changes} if row["id"] == draft.customer_id else row
            for row in customers.rows
        ]
    draft.open = False
    ui.notification(f"{name} saved.", color="success")


def edit_button(value, row: dict):
    return ui.button("Edit", size="sm", variant="soft", icon_left="pencil",
                     on_click=partial(edit, row["id"]))


@refreshable
def customer_table() -> None:
    ui.table(
        columns=[
            ui.column("name", label="Name"),
            ui.column("email", label="Email"),
            ui.column("city", label="City"),
            ui.column("", align="right", render=edit_button),
        ],
        rows=Customers().rows,
        row_key="id",
    )


@refreshable
def edit_dialog() -> None:
    draft = Draft()
    dialog = ui.dialog(open=draft.open, title="Edit customer", width="sm", on_close=close)
    with dialog, ui.form(on_submit=save), ui.vstack(gap="md"):
        with ui.form_field(label="Name", required=True):
            ui.input(value=draft.name)
        with ui.form_field(label="Email"):
            ui.input(value=draft.email, type="email")
        with ui.form_field(label="City"):
            ui.input(value=draft.city)
        with ui.hstack(gap="sm", justify="end"):
            ui.button("Cancel", variant="ghost", on_click=dialog.close())
            ui.button("Save", type="submit", color="primary", icon_left="save")


@page("/", title="Customers")
def home() -> None:
    with ui.container(width="lg", classes="py-8"), ui.vstack(gap="lg"):
        ui.heading("Customers", level=1)
        customer_table()
    edit_dialog()


app = Bretzel(title="Customers")
app.include(sys.modules[__name__])
```

## Why it works

- One dialog serves every row. `Draft` is a `PageState`: `edit` stores which customer and its values, so the dialog opens filled. A dialog whose content is known at render (a confirmation) needs no state at all: `dialog.open()` and `dialog.close()`.
- **The trap: only a `@refreshable` redraws.** The table and the dialog each live in one, so when `save` changes `Customers` and `Draft`, both follow. A dialog written straight in the page stays as it was first drawn: closed.
- A state field is declared with `field(default=...)`; a bare `open: bool = False` is refused at import.
- The row's id travels with `functools.partial(edit, row["id"])`; a lambda is refused as a handler.
- `save` rewrites the list inside `Customers.lock()`: two people saving at the same moment both keep their edit.
