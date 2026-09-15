"""Actions — server actions."""

from bretzel import page, ui

from examples.docs.features.shell import shell


@page("/actions-server", layout=shell, title="Server actions")
def actions_server_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Server actions", level=1, size="3xl")
            ui.text(
                "When an interaction changes the source of truth, pass a Python "
                "function—a handler—to `on_<event>=`. The round trip changes "
                "state on the server.",
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Attach a handler", level=2)
                    ui.text(
                        "Every interactive component exposes events (`click`, "
                        "`change`, `input`, `focus`, `blur`, `submit`, …). Attach "
                        "a function with `on_<event>=`.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "def save() -> None:\n"
                        "    ...\n"
                        "\n"
                        'ui.button("Save", on_click=save)\n',
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("What `on_<event>=` accepts", level=2)
                    ui.text(
                        "Bretzel resolves a handler by its import path "
                        "(`module::function`), not from a per-page table. It must "
                        "therefore be addressable.",
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("form", label="Form"),
                            ui.column("ok", label="Accepted?"),
                        ],
                        rows=[
                            {"form": "Module-level function (on_click=save)", "ok": "Yes"},
                            {"form": "@staticmethod / @classmethod", "ok": "Yes"},
                            {"form": "functools.partial(handler, arg)",
                             "ok": "Yes — to pass an argument"},
                            {"form": "Lambda (on_click=lambda: …)",
                             "ok": "No — render error"},
                            {"form": "Closure (function defined inside another function)",
                             "ok": "No — render error"},
                            {"form": "Instance method", "ok": "No — not addressable"},
                        ],
                        size="sm",
                    )
                    ui.text(
                        "A lambda or closure has no stable import path, which is why "
                        "Bretzel rejects it while rendering.",
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text(
                            "This is the server path (a function). `on_<event>=` "
                            "also accepts a string, evaluated on the client without "
                            "a handler—see",
                            color="muted", size="sm",
                        )
                        ui.link("Client actions", href="/actions-client")
                        ui.text(".", color="muted", size="sm")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Pass an argument — functools.partial", level=2)
                    ui.text(
                        "To give an argument to a handler (typically a row id), use "
                        "`partial`. The arguments travel with the request.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "from functools import partial\n"
                        "\n"
                        "def delete_item(item_id: str) -> None:\n"
                        "    ...\n"
                        "\n"
                        "# one row per item, each with its id:\n"
                        'ui.icon_button("trash-2",\n'
                        "               on_click=partial(delete_item, item_id))\n",
                        lang="python",
                    )
                    ui.text(
                        "Arguments must be JSON-serializable: str, int, float, bool, "
                        "None, list, or dict.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Read form data", level=2)
                    ui.text(
                        "Choose one of three approaches:",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "from bretzel.state import get\n"
                        "\n"
                        "# 1. a parameter named after a field → forwarded\n"
                        "def submit(title: str) -> None:\n"
                        "    ...\n"
                        "\n"
                        "# 2. a State-typed parameter → hydrated from the form\n"
                        "def save(form: Draft) -> None:\n"
                        "    # form.title and form.price are already filled and validated\n"
                        "    ...\n"
                        "\n"
                        "# 3. get() → one raw field, on demand\n"
                        "def other() -> None:\n"
                        '    note = get("note")\n',
                        lang="python",
                    )
                    ui.text(
                        "You do not write `name=` yourself: `ui.input(value=draft.title)` "
                        "derives the `title` field automatically (see Components).",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Prevent duplicate submissions — @idempotent",
                               level=2)
                    ui.text(
                        "For a sensitive action (a payment or creation), `@idempotent` "
                        "ensures that a duplicate submission from the same render runs "
                        "only once; the second gets a 204.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "from bretzel import idempotent\n"
                        "\n"
                        "@idempotent\n"
                        "def charge_card() -> None:\n"
                        "    ...\n",
                        lang="python",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="xs"):
                    ui.heading("Next", level=3)
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text("What renders again after a handler:",
                                color="muted", size="sm")
                        ui.link("Server reactivity →", href="/reactivity-server")
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text("Act without a round trip:",
                                color="muted", size="sm")
                        ui.link("Client actions →", href="/actions-client")
