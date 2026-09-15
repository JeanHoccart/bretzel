"""The complete first path: from zero to a changed Bretzel page."""

from bretzel import page, ui

from examples.docs.features.shell import shell

PATH = "/quickstart"


@page(PATH, layout=shell, title="Start in 5 minutes")
def quickstart_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="xl"):
            with ui.vstack(gap="sm", classes="max-w-4xl"):
                with ui.hstack(align="center", gap="sm", wrap=True):
                    ui.badge("Quickstart", color="primary", variant="soft")
                    ui.badge("5 minutes", color="muted", variant="outline")
                ui.heading("Your first Bretzel application", level=1, size="4xl")
                ui.text(
                    "Create the project, start the server, then change a page. "
                    "You will walk through the essential loop: describe the "
                    "interface in Python and watch the browser follow.",
                    color="muted", size="lg",
                )

            with ui.card(color="warning"):
                with ui.vstack(gap="sm"):
                    ui.heading("Before the first PyPI release", level=2, size="lg")
                    ui.text(
                        "Bretzel is still in early alpha. To try it today, install "
                        "from GitHub. After the first release, this command becomes "
                        "simply `pip install bretzel`.",
                        size="sm",
                    )
                    ui.code(
                        'python -m pip install "bretzel @ '
                        'git+https://github.com/JeanHoccart/bretzel.git"',
                        lang="bash",
                    )

            with ui.grid(cols=2, gap="lg", classes="max-lg:grid-cols-1"):
                with ui.card():
                    with ui.vstack(gap="md"):
                        ui.badge("1", color="primary")
                        ui.heading("Create the project", level=2)
                        ui.code(
                            "bretzel new hello-bretzel\n"
                            "cd hello-bretzel\n"
                            "python -m venv .venv",
                            lang="bash",
                        )
                        ui.text(
                            "`bretzel new` creates a minimal application in a new "
                            "directory. It refuses to overwrite an existing directory.",
                            color="muted", size="sm",
                        )

                with ui.card():
                    with ui.vstack(gap="md"):
                        ui.badge("2", color="primary")
                        ui.heading("Activate the environment", level=2)
                        ui.text("Windows PowerShell", weight="semibold", size="sm")
                        ui.code(".\\.venv\\Scripts\\Activate.ps1", lang="powershell")
                        ui.text("macOS or Linux", weight="semibold", size="sm")
                        ui.code("source .venv/bin/activate", lang="bash")

                with ui.card():
                    with ui.vstack(gap="md"):
                        ui.badge("3", color="primary")
                        ui.heading("Install and run", level=2)
                        ui.code(
                            "python -m pip install -e .\n"
                            "bretzel dev",
                            lang="bash",
                        )
                        ui.text(
                            "Open `http://127.0.0.1:8000`. `bretzel dev` watches "
                            "your files and restarts the application after every change.",
                            color="muted", size="sm",
                        )

                with ui.card():
                    with ui.vstack(gap="md"):
                        ui.badge("4", color="primary")
                        ui.heading("Change the page", level=2)
                        ui.text(
                            "Open `app/features/home.py`, change the heading, and save. "
                            "The browser reloads the application.",
                            color="muted", size="sm",
                        )
                        ui.code(
                            'ui.heading("My first Bretzel", level=1, size="4xl")',
                            lang="python",
                        )

            with ui.card(color="primary"):
                with ui.vstack(gap="md"):
                    ui.heading("What the generator created", level=2)
                    ui.code(
                        "hello-bretzel/\n"
                        "├── app/\n"
                        "│   ├── main.py              # configures the application\n"
                        "│   └── features/\n"
                        "│       └── home.py          # your first page\n"
                        "├── pyproject.toml\n"
                        "└── README.md",
                        lang="text",
                    )
                    with ui.hstack(gap="sm", wrap=True):
                        ui.button(
                            "Understand the model", href="/how",
                            icon_right="arrow-right",
                        )
                        ui.button(
                            "Read the configuration", href="/config",
                            variant="outline",
                        )
